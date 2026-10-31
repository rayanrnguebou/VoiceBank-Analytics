// Cookies et stockage sur l'appareil : bandeau au premier passage, choix modifiable à tout moment
// (« Gérer les cookies » en bas de page). VoiceBank ne pose aucun cookie publicitaire ni traceur :
// seul l'envoi de rapports d'erreurs anonymes (Sentry) est facultatif et attend l'accord de l'utilisateur.
// Refuser est aussi simple qu'accepter ; le choix est redemandé au bout de 6 mois.
import { useEffect, useRef, useState } from "react";
import { Cookie, ShieldCheck, X } from "lucide-react";
import { LANGUE, tx } from "./i18n";
import { demarrerAlertesErreurs } from "./alertesErreurs";

const CLE = "voicebank_consentement";
const VERSION = 1;
const DUREE_MS = 182 * 24 * 3600 * 1000;          // environ 6 mois
const EVENEMENT = "voicebank-cookies";
export const EVENEMENT_CHOISI = "voicebank-cookies-choisis";

export function lireConsentement() {
  try {
    const c = JSON.parse(localStorage.getItem(CLE) || "null");
    if (!c || c.version !== VERSION || !c.date || Date.now() - new Date(c.date).getTime() > DUREE_MS) return null;
    return c;
  } catch (e) {
    return null;
  }
}

function enregistrer(erreurs) {
  const precedent = lireConsentement();
  const c = { version: VERSION, erreurs: !!erreurs, date: new Date().toISOString() };
  try { localStorage.setItem(CLE, JSON.stringify(c)); } catch (e) { /* stockage indisponible : on redemandera */ }
  if (c.erreurs) demarrerAlertesErreurs();
  else if (precedent?.erreurs) {
    // Retrait de l'accord : on arrête tout envoi immédiatement
    import("@sentry/browser").then(S => S.getClient()?.close()).catch(() => {});
  }
  window.dispatchEvent(new Event(EVENEMENT_CHOISI));      // la présentation des applications peut s'afficher
  return c;
}

// Ouvre le panneau de réglage depuis n'importe quel lien « Gérer les cookies »
export function ouvrirGestionCookies() {
  window.dispatchEvent(new Event(EVENEMENT));
}

export function LienCookies({ className = "hover:underline" }) {
  return <button type="button" onClick={ouvrirGestionCookies} className={className}>{tx("Gérer les cookies")}</button>;
}

const NECESSAIRES = [
  ["Connexion", "ta session, effacée à la fermeture de l'onglet"],
  ["Sécurité", "l'identifiant de cet appareil (« Mes appareils ») et, si tu l'as activée, l'approbation par téléphone"],
  ["Tes choix", "langue, voix, mode conversation, base de données choisie, ce choix de cookies et le fait que tu as déjà un compte"],
];

export function BandeauCookies() {
  const [ouvert, setOuvert] = useState(() => lireConsentement() === null);
  const [details, setDetails] = useState(false);
  const [erreurs, setErreurs] = useState(() => !!lireConsentement()?.erreurs);
  const titre = useRef(null);

  useEffect(() => {
    const ouvrir = () => { setErreurs(!!lireConsentement()?.erreurs); setDetails(true); setOuvert(true); };
    window.addEventListener(EVENEMENT, ouvrir);
    return () => window.removeEventListener(EVENEMENT, ouvrir);
  }, []);
  useEffect(() => { if (ouvert) titre.current?.focus(); }, [ouvert, details]);

  if (!ouvert) return null;
  const choisir = v => { enregistrer(v); setOuvert(false); setDetails(false); };
  const bouton = "flex-1 min-w-[8.5rem] px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-laiton-400";
  const neutre = `${bouton} border border-white/25 text-white hover:bg-white/10`;

  return (
    <div className="fixed inset-x-0 bottom-0 z-[60] p-3 sm:p-5 pointer-events-none">
      <section role="dialog" aria-modal="false" aria-labelledby="cookies-titre"
        className="pointer-events-auto mx-auto max-h-[88vh] max-w-2xl overflow-y-auto rounded-2xl border border-laiton-400/30 bg-[#0E332D] text-gray-100 shadow-2xl">
        <div className="p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 grid h-9 w-9 flex-shrink-0 place-items-center rounded-xl bg-laiton-400/15 text-laiton-300">
              <Cookie size={18} aria-hidden="true" />
            </span>
            <div className="flex-1">
              <h2 id="cookies-titre" ref={titre} tabIndex={-1} className="text-base font-semibold text-white focus:outline-none">
                {details ? tx("Gérer les cookies") : tx("Ta vie privée, tes choix")}
              </h2>
              <p className="mt-1 text-sm leading-relaxed text-gray-300">
                {tx("VoiceBank n'utilise aucun cookie publicitaire, aucun traceur et ne revend aucune donnée. Seul ce qui est nécessaire au service est gardé sur ton appareil. Avec ton accord, des rapports d'erreurs anonymes nous aident à corriger les bugs plus vite.")}
              </p>
            </div>
            {details && lireConsentement() && (
              <button type="button" onClick={() => { setOuvert(false); setDetails(false); }} aria-label={tx("Fermer")}
                className="rounded-lg p-1 text-gray-400 hover:text-white"><X size={18} /></button>
            )}
          </div>

          {details && (
            <div className="mt-4 space-y-3">
              <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="flex items-center gap-2 text-sm font-semibold text-white">
                    <ShieldCheck size={15} className="text-emerald-400" aria-hidden="true" />{tx("Strictement nécessaires")}
                  </p>
                  <span className="whitespace-nowrap rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-medium text-emerald-300">{tx("Toujours actifs")}</span>
                </div>
                <ul className="mt-2 space-y-1 text-xs text-gray-300">
                  {NECESSAIRES.map(([t, d]) => <li key={t}><strong className="text-gray-100">{tx(t)}</strong>{LANGUE === "en" ? ": " : " : "}{tx(d)}</li>)}
                </ul>
              </div>
              <label className="flex cursor-pointer items-start justify-between gap-4 rounded-xl border border-white/10 bg-white/5 p-4">
                <span>
                  <span className="block text-sm font-semibold text-white">{tx("Rapports d'erreurs anonymes")}</span>
                  <span className="mt-1 block text-xs text-gray-300">
                    {tx("En cas de plantage, une description technique part chez notre prestataire Sentry : jamais ton nom, ton adresse IP, ce que tu tapes ni tes données bancaires.")}
                  </span>
                </span>
                <input type="checkbox" role="switch" checked={erreurs} onChange={e => setErreurs(e.target.checked)}
                  aria-label={tx("Rapports d'erreurs anonymes")} className="peer sr-only" />
                <span aria-hidden="true" className={`relative mt-0.5 h-6 w-11 flex-shrink-0 rounded-full transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-laiton-400 ${erreurs ? "bg-laiton-400" : "bg-white/20"}`}>
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${erreurs ? "left-[1.375rem]" : "left-0.5"}`} />
                </span>
              </label>
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" onClick={() => choisir(false)} className={neutre}>{tx("Tout refuser")}</button>
            {details
              ? <button type="button" onClick={() => choisir(erreurs)} className={neutre}>{tx("Enregistrer mes choix")}</button>
              : <button type="button" onClick={() => setDetails(true)} className={neutre}>{tx("Personnaliser")}</button>}
            <button type="button" onClick={() => choisir(true)}
              className={`${bouton} bg-laiton-400 text-[#0E332D] hover:bg-laiton-300`}>{tx("Tout accepter")}</button>
          </div>
          <p className="mt-3 text-[11px] text-gray-400">
            <a href={`/confidentialite/${LANGUE === "en" ? "#cookies-en" : "#cookies"}`} target="_blank" rel="noopener noreferrer"
              className="underline hover:text-gray-200">{tx("Détail des cookies et du stockage")}</a>
            {" · "}{tx("Tu peux changer d'avis à tout moment avec « Gérer les cookies » en bas de page.")}
          </p>
        </div>
      </section>
    </div>
  );
}
