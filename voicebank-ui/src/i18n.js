// Langue de l'interface : français (texte de référence, écrit dans le code) ou anglais (traductions/en.json).
// tx("Texte français {n}", { n }) renvoie le texte dans la langue choisie. Changer de langue recharge la page :
// la session (onglet) est conservée.
import en from "./traductions/en.json";

const CLE = "voicebank_langue";
export const LANGUES = [["fr", "Français"], ["en", "English"]];

function lireLangue() {
  try {
    const l = localStorage.getItem(CLE);
    if (l === "fr" || l === "en") return l;
  } catch (e) { /* stockage indisponible */ }
  // Par défaut : français (public principal), même si le navigateur est en anglais ; ?lang=en force l'anglais
  try {
    const q = new URLSearchParams(window.location.search).get("lang");
    if (q === "en" || q === "fr") { localStorage.setItem(CLE, q); return q; }
  } catch (e) { /* rien */ }
  return "fr";
}

export const LANGUE = lireLangue();
export const LOCALE = LANGUE === "en" ? "en-GB" : "fr-FR";          // nombres et dates
export const LOCALE_VOIX = LANGUE === "en" ? "en-US" : "fr-FR";     // reconnaissance et synthèse vocales

if (typeof document !== "undefined") document.documentElement.lang = LANGUE;

export function tx(texte, variables) {
  let s = LANGUE === "en" ? (en[texte] ?? texte) : texte;
  if (variables) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in variables && variables[k] != null ? String(variables[k]) : m));
  return s;
}

export function changerLangue(langue) {
  if (langue === LANGUE) return;
  try { localStorage.setItem(CLE, langue); } catch (e) { /* rien */ }
  window.location.reload();
}
