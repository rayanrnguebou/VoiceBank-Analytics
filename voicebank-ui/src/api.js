// VOICEBANK ANALYTICS — client HTTP authentifié
import axios from "axios";
import { LANGUE, tx } from "./i18n";

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
  config.headers["Accept-Language"] = LANGUE;      // messages de l'API dans la langue de l'interface
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
      if (lireSession()) noterMotifDeconnexion(tx("Ta session a expiré ou a été fermée. Reconnecte-toi."));
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
    doitConfigurer2fa: !!data.doit_configurer_2fa,
    expire: Date.now() + data.expire_dans_min * 60 * 1000,
  };
  ecrireSession(session);
  return session;
}

export async function connexion(nom, motDePasse) {
  // Délai long : sur l'offre gratuite de Render, l'API peut mettre ~1 min à se réveiller.
  const { data } = await http.post("/auth/login", { nom, mot_de_passe: motDePasse }, { timeout: 90000 });
  return suiteConnexion(data);
}

// Double authentification active : pas encore de session, il faut le code à 6 chiffres
function suiteConnexion(data) {
  if (data.double_auth) return { etape2fa: { jeton: data.jeton_2fa, utilisateur: data.utilisateur } };
  return appliquerJeton(data);
}

// Connexion avec un compte d'entreprise (Google, Microsoft) : le vérificateur PKCE reste dans l'onglet.
export async function demarrerSSO(fournisseur) {
  const { data } = await http.get(`/auth/sso/${fournisseur}/debut`, { timeout: 90000 });
  try { sessionStorage.setItem("voicebank_sso", JSON.stringify({ f: fournisseur, v: data.verificateur })); } catch (e) { /* rien */ }
  window.location.assign(data.url);
}

export async function terminerSSO(code, etat) {
  let s = null;
  try { s = JSON.parse(sessionStorage.getItem("voicebank_sso") || "null"); sessionStorage.removeItem("voicebank_sso"); } catch (e) { /* rien */ }
  if (!s) throw new Error(tx("Connexion commencée dans un autre onglet ou expirée : recommence."));
  const { data } = await http.post(`/auth/sso/${s.f}/fin`, { code, etat, verificateur: s.v }, { timeout: 90000 });
  return suiteConnexion(data);
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
  if (Array.isArray(d)) return tx("Données invalides");
  if (e?.code === "ECONNABORTED") return tx("Le serveur met trop de temps à répondre");
  if (!e?.response && !e?.isAxiosError && e?.message) return e.message;
  if (!e?.response) return tx("API injoignable. Vérifie qu'elle est démarrée.");
  return tx("Erreur inattendue");
}
