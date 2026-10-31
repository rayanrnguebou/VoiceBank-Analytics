import "./compatibilite";            // en premier : complète les navigateurs anciens
import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";
import { demarrerAlertesErreurs } from "./alertesErreurs";
import { BandeauCookies, lireConsentement } from "./consentement";
import { PresentationApplications } from "./presentation";

// Rapports d'erreurs (Sentry) : seulement avec l'accord donné dans le bandeau des cookies
if (lireConsentement()?.erreurs) demarrerAlertesErreurs();

// Travailleur du site : notifications d'approbation et page « hors ligne » (application Android, écran d'accueil).
// Seulement sur le site construit : en développement, il gênerait le rechargement automatique.
// « serviceWorker » peut exister sans valeur (Firefox en navigation privée) : on vérifie la fonction elle-même.
if (import.meta.env.PROD && navigator.serviceWorker?.register) {
  window.addEventListener("load", () => { try { navigator.serviceWorker.register("/sw-approbation.js").catch(() => {}); } catch (e) { /* rien */ } });
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
    <BandeauCookies />
    <PresentationApplications />
  </React.StrictMode>
);
