// VOICEBANK ANALYTICS — client HTTP authentifié
import axios from "axios";

export const API = (import.meta.env.REACT_APP_API_URL || "http://localhost:8000").replace(/\/$/, "");

// Le jeton est gardé en sessionStorage : il disparaît à la fermeture de l'onglet.
const CLE_JETON = "voicebank_jeton";

export function lireSession() {
  try {
    const s = JSON.parse(sessionStorage.getItem(CLE_JETON) || "null");
    if (s && s.expire > Date.now()) return s;
  } catch (e) { /* stockage indisponible */ }
  return null;
}

function ecrireSession(s) {
  try {
    if (s) sessionStorage.setItem(CLE_JETON, JSON.stringify(s));
    else sessionStorage.removeItem(CLE_JETON);
  } catch (e) { /* stockage indisponible */ }
}

export const http = axios.create({ baseURL: API, timeout: 30000 });

http.interceptors.request.use(config => {
  const s = lireSession();
  if (s) config.headers.Authorization = `Bearer ${s.token}`;
  return config;
});

http.interceptors.response.use(
  r => r,
  e => {
    if (e.response?.status === 402) window.dispatchEvent(new Event("voicebank:acces-expire"));
    // Maintenance décidée par l'administrateur : page dédiée avec son message
    if (e.response?.status === 503 && e.response?.data?.maintenance) {
      window.dispatchEvent(new CustomEvent("voicebank:maintenance", { detail: e.response.data }));
    }
    // Serveur injoignable ou en cours de redémarrage (mise à jour sur Render) : bandeau de reconnexion
    if (!e.response && e.code !== "ECONNABORTED" && e.code !== "ERR_CANCELED") {
      window.dispatchEvent(new Event("voicebank:injoignable"));
    }
    if ([502, 504].includes(e.response?.status)) {
      window.dispatchEvent(new Event("voicebank:injoignable"));
    }
    if (e.response?.status === 401 && !e.config?.url?.includes("/auth/login") && !e.config?.url?.includes("/auth/essai")) {
      if (lireSession()) noterMotifDeconnexion("Ta session a expiré ou a été fermée. Reconnecte-toi.");
      ecrireSession(null);
      window.dispatchEvent(new Event("voicebank:deconnexion"));
    }
    return Promise.reject(e);
  }
);

// Réponse de /auth/login ou /auth/mot-de-passe -> session enregistrée
export function appliquerJeton(data) {
  const session = {
    token: data.access_token, utilisateur: data.utilisateur, role: data.role,
    doitChangerMdp: !!data.doit_changer_mot_de_passe,
    expire: Date.now() + data.expire_dans_min * 60 * 1000,
  };
  ecrireSession(session);
  return session;
}

export async function connexion(nom, motDePasse) {
  // Délai long : sur l'offre gratuite de Render, l'API peut mettre ~1 min à se réveiller.
  const { data } = await http.post("/auth/login", { nom, mot_de_passe: motDePasse }, { timeout: 90000 });
  return appliquerJeton(data);
}

export async function inscriptionEssai(corps) {
  const { data } = await http.post("/auth/essai", corps, { timeout: 90000 });
  return appliquerJeton(data);
}

export async function renouvelerJeton() {
  const { data } = await http.post("/auth/renouveler");
  return appliquerJeton(data);
}

// Motif de la dernière déconnexion automatique, affiché sur l'écran de connexion
export function noterMotifDeconnexion(motif) {
  try { sessionStorage.setItem("voicebank_motif", motif); } catch (e) { /* rien */ }
}
export function lireMotifDeconnexion() {
  try {
    const m = sessionStorage.getItem("voicebank_motif");
    sessionStorage.removeItem("voicebank_motif");
    return m;
  } catch (e) { return null; }
}

export function deconnexion() {
  ecrireSession(null);
}

export function messageErreur(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return "Données invalides";
  if (e?.code === "ECONNABORTED") return "Le serveur met trop de temps à répondre";
  if (!e?.response) return "API injoignable. Vérifie qu'elle est démarrée.";
  return "Erreur inattendue";
}
