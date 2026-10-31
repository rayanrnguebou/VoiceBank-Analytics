// Bouton micro : dictée en direct (navigateur) puis transcription finale (Whisper).
import { useState, useEffect, useRef, useCallback } from "react";
import { http, messageErreur } from "../api";
import { Mic, MicOff, RefreshCw } from "lucide-react";
import { LOCALE_VOIX, tx } from "../i18n";

export const ReconnaissanceVocale = typeof window !== "undefined"
  ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
export const DUREE_MAX_ENREGISTREMENT_MS = 12000;

export function BoutonMicro({ onDebut, onTexteEnDirect, onTranscription, onErreur, dark }) {
  const [statut, setStatut] = useState("idle");
  const mediaRecRef         = useRef(null);
  const chunksRef           = useRef([]);
  const timerRef            = useRef(null);
  const reconnaissanceRef   = useRef(null);
  const texteDirectRef      = useRef("");

  const arreter = useCallback(() => {
    clearTimeout(timerRef.current);
    try { reconnaissanceRef.current?.stop(); } catch (e) { /* déjà arrêtée */ }
    if (mediaRecRef.current?.state === "recording") mediaRecRef.current.stop();
  }, []);

  const demarrerDicteeDirecte = () => {
    texteDirectRef.current = "";
    if (!ReconnaissanceVocale) return;
    try {
      const rec = new ReconnaissanceVocale();
      rec.lang = LOCALE_VOIX;
      rec.interimResults = true;
      rec.continuous = true;
      rec.onresult = (e) => {
        let texte = "";
        for (let i = 0; i < e.results.length; i++) texte += e.results[i][0].transcript;
        texteDirectRef.current = texte.trim();
        onTexteEnDirect(texteDirectRef.current);
      };
      rec.onerror = () => { /* aperçu seulement : Whisper prendra le relais */ };
      rec.start();
      reconnaissanceRef.current = rec;
    } catch (e) {
      reconnaissanceRef.current = null;
    }
  };

  const demarrer = async () => {
    // Navigateur sans enregistrement audio (anciens iPhone, certains navigateurs intégrés) : message clair
    if (!navigator.mediaDevices?.getUserMedia || typeof window.MediaRecorder === "undefined") {
      onErreur(tx("Ce navigateur ne permet pas d'enregistrer la voix : écris ta question, ou ouvre VoiceBank dans Chrome, Safari récent, Edge ou Firefox."));
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      onErreur(tx("Microphone inaccessible. Autorise le micro dans ton navigateur."));
      return;
    }
    const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"]
      .find(t => window.MediaRecorder.isTypeSupported?.(t)) || "";
    let recorder;
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    } catch (e) {
      stream.getTracks().forEach(t => t.stop());
      onErreur(tx("Ce navigateur ne permet pas d'enregistrer la voix : écris ta question, ou ouvre VoiceBank dans Chrome, Safari récent, Edge ou Firefox."));
      return;
    }
    const type = mimeType || recorder.mimeType || "audio/mp4";
    const extension = type.includes("webm") ? "webm" : type.includes("ogg") ? "ogg" : "mp4";
    chunksRef.current = [];
    recorder.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      setStatut("processing");
      const formData = new FormData();
      formData.append("fichier", new Blob(chunksRef.current, { type }), `audio.${extension}`);
      const texteDirect = texteDirectRef.current;
      try {
        // Délai long : le Whisper local peut devoir charger son modèle à la 1re utilisation
        const res = await http.post("/vocal/transcrire", formData, { timeout: 120000 });
        if (res.data?.texte?.trim()) onTranscription(res.data.texte.trim());
        else if (texteDirect) onTranscription(texteDirect);
        else onErreur(tx("Aucun texte détecté. Parle plus fort ou plus clairement."));
      } catch (e) {
        if (texteDirect) {
          onTranscription(texteDirect);
          onErreur(tx("Transcription serveur impossible ({x}) : texte du navigateur conservé, vérifie-le avant d'envoyer.", { x: messageErreur(e) }));
        } else {
          onErreur(tx("Transcription impossible : {x}", { x: messageErreur(e) }));
        }
      }
      setStatut("idle");
    };
    recorder.start(100);
    mediaRecRef.current = recorder;
    setStatut("recording");
    onDebut();
    demarrerDicteeDirecte();
    timerRef.current = setTimeout(arreter, DUREE_MAX_ENREGISTREMENT_MS);
  };

  useEffect(() => () => {
    clearTimeout(timerRef.current);
    try { reconnaissanceRef.current?.abort(); } catch (e) { /* rien */ }
  }, []);

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        onClick={statut === "recording" ? arreter : demarrer}
        disabled={statut === "processing"}
        aria-label={statut === "recording" ? tx("Arrêter l'enregistrement") : tx("Poser une question à voix haute")}
        className={`relative w-16 h-16 rounded-full flex items-center justify-center transition-all shadow-lg disabled:opacity-60 ${
          statut === "recording" ? "bg-red-500 hover:bg-red-600 scale-110" : "bg-foret-600 hover:bg-foret-700"
        }`}
      >
        {statut === "recording" && <span className="absolute inset-0 rounded-full bg-red-400 animate-ping opacity-50" />}
        {statut === "processing" ? <RefreshCw size={22} className="text-white animate-spin" />
          : statut === "recording" ? <MicOff size={22} className="text-white" />
          : <Mic size={22} className="text-white" />}
      </button>
      <span className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
        {statut === "recording" ? tx("Parle… clique pour finir") : statut === "processing" ? tx("Finalisation…") : tx("Cliquer pour parler")}
      </span>
    </div>
  );
}

// ════════════════════════════════════════
// COMPOSANT — KPI CARD
// ════════════════════════════════════════
