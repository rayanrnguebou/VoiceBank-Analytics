// Page d'état publique (UptimeRobot, gratuite) : adresse donnée par REACT_APP_PAGE_ETAT_URL. Sans elle, aucun lien.
const URL_BRUTE = import.meta.env.REACT_APP_PAGE_ETAT_URL || "";
export const PAGE_ETAT = /^https:\/\//.test(URL_BRUTE) ? URL_BRUTE : "";
