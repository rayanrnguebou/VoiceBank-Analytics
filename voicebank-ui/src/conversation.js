// Mode conversation : après la réponse parlée, l'assistant écoute la réponse de l'utilisateur
// sans qu'il ait à cliquer. L'écoute s'arrête seule après un silence, ou si personne ne parle.
import { http } from "./api";
import { LOCALE_VOIX, tx } from "./i18n";

const Reconnaissance = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);

export const ECOUTE = {
  attenteParole: 7000,   // personne ne parle : on arrête d'écouter
  silenceFin: 1400,      // silence après avoir parlé : la réponse est terminée
  dureeMax: 20000,
  seuil: 0.025,          // niveau sonore considéré comme de la parole
};

function normaliser(texte) {
  return String(texte || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
}

const NON = new Set(["non", "non merci", "merci", "c est bon", "ca ira", "stop", "arrete", "rien", "plus tard",
  "pas maintenant", "au revoir", "ca suffit", "c est tout", "non c est bon", "non ca ira", "non c est tout",
  "pas besoin", "non pas besoin", "ca va", "non ca va", "merci c est tout", "merci beaucoup", "ce sera tout",
  "no", "no thanks", "no thank you", "nope", "not now", "later", "that s all", "that s it", "stop", "thanks", "thank you"]);
const OUI = new Set(["oui", "ouais", "ouai", "vas y", "d accord", "ok", "okay", "volontiers", "bien sur", "allez",
  "allez y", "parfait", "carrement", "absolument", "evidemment", "je veux bien", "avec plaisir", "exactement",
  "oui merci", "oui vas y", "oui allez y", "oui d accord", "oui s il te plait", "oui stp", "oui volontiers",
  "ok vas y", "d accord vas y", "oui je veux bien", "oui montre moi", "montre moi", "oui bien sur", "go",
  "yes", "yeah", "yep", "sure", "ok sure", "of course", "please", "yes please", "go ahead", "show me", "absolutely"]);

/** Classe la réponse orale : "vide", "non", "oui", ou "question" (avec le texte à poser). */
export function interpreterReponse(texte) {
  const t = normaliser(texte);
  if (!t) return { type: "vide" };
  if (NON.has(t)) return { type: "non" };
  if (OUI.has(t)) return { type: "oui" };
  const mots = t.split(" ");
  if (mots[0] === "non" && mots.length <= 4) return { type: "non" };
  if (["oui", "ouais", "ok", "okay"].includes(mots[0]) && mots.length <= 3) return { type: "oui" };
  // « Oui, et à Douala ? » : la vraie question suit le oui
  const question = String(texte).trim().replace(/^(oui|ouais|ok|okay|d'accord)[\s,.!]+/i, "");
  return { type: "question", texte: question.charAt(0).toUpperCase() + question.slice(1) };
}

async function transcrire(blob, extension, texteNavigateur) {
  const formData = new FormData();
  formData.append("fichier", blob, `audio.${extension}`);
  try {
    const res = await http.post("/vocal/transcrire", formData, { timeout: 60000 });
    return res.data?.texte?.trim() || texteNavigateur;
  } catch (e) {
    return texteNavigateur;   // Whisper indisponible : on garde le texte du navigateur
  }
}

/**
 * Écoute une réponse orale et la retourne en texte ("" si personne n'a parlé).
 * `controle.annuler()` arrête l'écoute sans rien retourner.
 */
export async function ecouterReponse({ onParole, onTexteEnDirect, onTranscription, controle = {} }) {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (e) {
    throw new Error(tx("Microphone inaccessible. Autorise le micro pour répondre à voix haute."));
  }
  const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"]
    .find(t => window.MediaRecorder?.isTypeSupported?.(t)) || "";
  const extension = mimeType.includes("webm") ? "webm" : mimeType.includes("ogg") ? "ogg" : "mp4";
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const morceaux = [];
  recorder.ondataavailable = e => { if (e.data.size > 0) morceaux.push(e.data); };

  // Niveau sonore, pour détecter le début et la fin de la parole
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = Ctx ? new Ctx() : null;
  const analyseur = ctx ? ctx.createAnalyser() : null;
  if (ctx) { analyseur.fftSize = 1024; ctx.createMediaStreamSource(stream).connect(analyseur); }
  const tampon = analyseur ? new Float32Array(analyseur.fftSize) : null;
  const niveau = () => {
    if (!analyseur) return 0;
    analyseur.getFloatTimeDomainData(tampon);
    let s = 0;
    for (let i = 0; i < tampon.length; i++) s += tampon[i] * tampon[i];
    return Math.sqrt(s / tampon.length);
  };

  // Texte en direct (Chrome, Edge, Safari)
  let texteDirect = "";
  let dernierTexte = 0;
  let rec = null;
  if (Reconnaissance) {
    try {
      rec = new Reconnaissance();
      rec.lang = LOCALE_VOIX; rec.interimResults = true; rec.continuous = true;
      rec.onresult = e => {
        let t = "";
        for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
        texteDirect = t.trim();
        dernierTexte = Date.now();
        onTexteEnDirect && onTexteEnDirect(texteDirect);
      };
      rec.onerror = () => {};
      rec.start();
    } catch (e) { rec = null; }
  }

  return new Promise((resolve) => {
    const debut = Date.now();
    let aParle = false;
    let dernierSon = Date.now();
    let annule = false;
    let minuterie = null;
    recorder.start(100);

    const terminer = () => {
      clearInterval(minuterie);
      try { rec && rec.stop(); } catch (e) { /* rien */ }
      if (recorder.state === "recording") recorder.stop(); else recorder.onstop();
    };
    controle.annuler = () => { annule = true; terminer(); };

    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      try { ctx && ctx.close(); } catch (e) { /* rien */ }
      if (annule || !aParle) { resolve(""); return; }
      onTranscription && onTranscription();
      resolve(await transcrire(new Blob(morceaux, { type: mimeType || "audio/webm" }), extension, texteDirect));
    };

    minuterie = setInterval(() => {
      const maintenant = Date.now();
      const parole = niveau() > ECOUTE.seuil || maintenant - dernierTexte < 300;
      if (parole) {
        dernierSon = maintenant;
        if (!aParle) { aParle = true; onParole && onParole(); }
      }
      const fini = aParle ? maintenant - dernierSon > ECOUTE.silenceFin : maintenant - debut > ECOUTE.attenteParole;
      if (fini || maintenant - debut > ECOUTE.dureeMax) terminer();
    }, 100);
  });
}
