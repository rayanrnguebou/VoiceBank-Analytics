// VOICEBANK ANALYTICS — client HTTP authentifié
import axios from "axios";

export const API = (process.env.REACT_APP_API_URL || "http://localhost:8000").replace(/\/$/, "");

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
    if (e.response?.status === 401 && !e.config?.url?.includes("/auth/login")) {
      ecrireSession(null);
      window.dispatchEvent(new Event("voicebank:deconnexion"));
    }
    return Promise.reject(e);
  }
);

export async function connexion(nom, motDePasse) {
  const { data } = await http.post("/auth/login", { nom, mot_de_passe: motDePasse });
  const session = {
    token: data.access_token, utilisateur: data.utilisateur, role: data.role,
    expire: Date.now() + data.expire_dans_min * 60 * 1000,
  };
  ecrireSession(session);
  return session;
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
