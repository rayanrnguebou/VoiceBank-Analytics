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
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => { navigator.serviceWorker.register("/sw-approbation.js").catch(() => {}); });
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
    <BandeauCookies />
    <PresentationApplications />
  </React.StrictMode>
);
