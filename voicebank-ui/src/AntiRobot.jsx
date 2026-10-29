// Vérification anti-robot Cloudflare Turnstile (gratuite, le plus souvent invisible pour un humain).
// Affichée seulement si REACT_APP_TURNSTILE_SITE_KEY est défini ; le jeton obtenu est envoyé à l'API.
import { useEffect, useRef } from "react";
import { LANGUE, tx } from "./i18n";

export const CLE_SITE = import.meta.env.REACT_APP_TURNSTILE_SITE_KEY || "";
const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let chargement = null;

function chargerScript() {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (!chargement) {
    chargement = new Promise((ok, ko) => {
      const s = document.createElement("script");
      s.src = SCRIPT; s.async = true;
      s.onload = () => ok(window.turnstile);
      s.onerror = () => { chargement = null; ko(new Error(tx("Turnstile injoignable"))); };
      document.head.appendChild(s);
    });
  }
  return chargement;
}

export default function AntiRobot({ onJeton, theme = "dark" }) {
  const zone = useRef(null);
  useEffect(() => {
    if (!CLE_SITE) return undefined;
    let id = null, actif = true;
    chargerScript().then(t => {
      if (!actif || !zone.current) return;
      id = t.render(zone.current, {
        sitekey: CLE_SITE, theme, language: LANGUE, appearance: "interaction-only",
        callback: jeton => onJeton(jeton),
        "expired-callback": () => onJeton(null),
        "error-callback": () => onJeton(null),
      });
    }).catch(() => onJeton(null));
    return () => { actif = false; if (id !== null && window.turnstile) window.turnstile.remove(id); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!CLE_SITE) return null;
  return <div ref={zone} className="min-h-0" />;
}
