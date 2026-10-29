// Sécurité de session : déconnexion après inactivité, et jeton renouvelé tant qu'on est actif.
import { useState, useEffect, useRef, useCallback } from "react";
import { renouvelerJeton, noterMotifDeconnexion } from "./api";
import { tx } from "./i18n";

export const INACTIVITE_MS = 15 * 60 * 1000;        // déconnexion après 15 min sans activité
export const AVERTISSEMENT_MS = 60 * 1000;           // prévenir 1 min avant
const RENOUVELER_AVANT_MS = 10 * 60 * 1000;          // renouveler le jeton 10 min avant son expiration
const EVENEMENTS = ["mousemove", "mousedown", "keydown", "touchstart", "scroll", "voicebank:lecture"];

export function useSessionActive({ session, onSession, onDeconnexion }) {
  const derniere = useRef(Date.now());
  const enCours = useRef(false);
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const [resteMs, setResteMs] = useState(null);       // non nul : avertissement affiché

  const rester = useCallback(() => { derniere.current = Date.now(); setResteMs(null); }, []);

  useEffect(() => {
    let precedent = 0;
    const activite = () => {
      const t = Date.now();
      if (t - precedent > 1000) { derniere.current = t; precedent = t; }
    };
    EVENEMENTS.forEach(e => window.addEventListener(e, activite, { passive: true }));

    const verifier = async () => {
      const maintenant = Date.now();
      const inactif = maintenant - derniere.current;
      if (inactif >= INACTIVITE_MS) {
        noterMotifDeconnexion(tx("Déconnecté après 15 minutes d'inactivité, pour protéger les données."));
        onDeconnexion();
        return;
      }
      setResteMs(inactif >= INACTIVITE_MS - AVERTISSEMENT_MS ? INACTIVITE_MS - inactif : null);
      const s = sessionRef.current;
      if (s && !enCours.current && inactif < 5 * 60 * 1000 && s.expire - maintenant < RENOUVELER_AVANT_MS) {
        enCours.current = true;
        try { onSession(await renouvelerJeton()); } catch (e) { /* un 401 déconnecte déjà */ }
        enCours.current = false;
      }
    };
    const minuterie = setInterval(verifier, 1000);
    return () => {
      clearInterval(minuterie);
      EVENEMENTS.forEach(e => window.removeEventListener(e, activite));
    };
  }, [onSession, onDeconnexion]);

  return { resteMs, rester };
}
