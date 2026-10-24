// Petits éléments d'interface partagés (thème clair / sombre)
export const carte = dark =>
  `rounded-2xl border p-6 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`;
export const champ = dark =>
  `w-full px-3 py-2 rounded-xl border text-sm outline-none ${dark
    ? "bg-gray-700 border-gray-600 text-white focus:border-foret-500"
    : "bg-gray-50 border-gray-200 text-gray-900 focus:border-foret-500"}`;
export const etiquette = dark => `block text-xs mb-1 ${dark ? "text-gray-400" : "text-gray-500"}`;
export const titre = dark => `text-lg font-bold ${dark ? "text-white" : "text-gray-900"}`;
export const texteDiscret = dark => `text-xs ${dark ? "text-gray-400" : "text-gray-500"}`;
export const boutonPrincipal =
  "px-4 py-2 bg-foret-600 hover:bg-foret-700 text-white text-sm font-semibold rounded-xl disabled:opacity-50";
export const boutonSecondaire = dark =>
  `px-3 py-1.5 rounded-lg text-xs font-medium ${dark ? "bg-gray-700 hover:bg-gray-600 text-gray-200"
    : "bg-gray-100 hover:bg-gray-200 text-gray-700"}`;
export const COULEURS_NIVEAU = {
  Critique: "bg-red-500", "Élevé": "bg-orange-500", Moyen: "bg-yellow-500", Faible: "bg-green-500",
};

export function formaterFcfa(v) {
  const x = Number(v);
  if (!isFinite(x)) return "--";
  if (Math.abs(x) >= 1e9) return (x / 1e9).toFixed(1).replace(".", ",") + " Mds";
  if (Math.abs(x) >= 1e6) return (x / 1e6).toFixed(1).replace(".", ",") + " M";
  return x.toLocaleString("fr-FR");
}

export function formaterDate(v) {
  if (!v) return "";
  const d = new Date(v);
  return isNaN(d) ? String(v) : d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

// Synthèse vocale du navigateur (aucune donnée envoyée à un serveur).
// Accepte un texte ou une liste (résumé puis commentaire) : lus à la suite, phrase par phrase
// (Chrome coupe les énoncés de plus de ~15 secondes). L'état est diffusé par l'événement
// « voicebank:lecture » (detail = true pendant la lecture, false à la fin).
function signalerLecture(enCours) {
  try { window.dispatchEvent(new CustomEvent("voicebank:lecture", { detail: enCours })); } catch (e) { /* rien */ }
}

export function decouperPhrases(texte) {
  // Coupe après . ! ? … suivi d'une majuscule : « et à Douala ? » ou… reste d'un seul tenant.
  return String(texte || "").split(/(?<=[.!?…])\s+(?=[A-ZÀ-ÖØ-Þ«"0-9])/).map(p => p.trim()).filter(Boolean);
}

export function lireAVoixHaute(textes) {
  try {
    const phrases = (Array.isArray(textes) ? textes : [textes]).flatMap(decouperPhrases);
    if (!phrases.length || !window.speechSynthesis) return false;
    window.speechSynthesis.cancel();
    const voix = window.speechSynthesis.getVoices().find(v => v.lang && v.lang.toLowerCase().startsWith("fr"));
    phrases.forEach((phrase, i) => {
      const u = new SpeechSynthesisUtterance(phrase);
      u.lang = "fr-FR";
      u.rate = 1.02;
      if (voix) u.voice = voix;
      if (i === phrases.length - 1) u.onend = u.onerror = () => signalerLecture(false);
      window.speechSynthesis.speak(u);
    });
    signalerLecture(true);
    return true;
  } catch (e) {
    return false;
  }
}

export function arreterLecture() {
  try { window.speechSynthesis?.cancel(); } catch (e) { /* rien */ }
  signalerLecture(false);
}
