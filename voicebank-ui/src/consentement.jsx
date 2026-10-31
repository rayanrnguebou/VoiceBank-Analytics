// Cookies et stockage sur l'appareil : bandeau au premier passage, choix modifiable à tout moment
// (« Gérer les cookies » en bas de page). VoiceBank ne pose aucun cookie publicitaire ni traceur :
// seul l'envoi de rapports d'erreurs anonymes (Sentry) est facultatif et attend l'accord de l'utilisateur.
// Refuser est aussi simple qu'accepter ; le choix est redemandé au bout de 6 mois.
import { useEffect, useRef, useState } from "react";
import { ShieldCheck, X } from "lucide-react";
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

// Biscuit dessiné : il apparaît, se fait croquer (la bouchée grandit) et laisse tomber quelques miettes
function BiscuitAnime() {
  return (
    <svg viewBox="0 0 44 44" className="vbc-biscuit h-9 w-9" aria-hidden="true">
      <defs>
        <mask id="vbc-croque">
          <rect width="44" height="44" fill="white" />
          <circle className="vbc-bouchee" cx="38" cy="7" r="0" fill="black" />
          <circle className="vbc-bouchee" cx="31" cy="3" r="0" fill="black" style={{ animationDelay: "120ms" }} />
        </mask>
      </defs>
      <g mask="url(#vbc-croque)">
        <circle cx="22" cy="22" r="18" fill="#C9A13B" />
        <circle cx="22" cy="22" r="18" fill="none" stroke="#86691F" strokeWidth="1.5" />
        {[[15, 15, 2.6], [26, 13, 2], [13, 26, 2.2], [24, 25, 2.8], [30, 31, 2], [19, 33, 1.8]].map(([x, y, r]) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill="#4A3418" />
        ))}
      </g>
      {[[36, 14, 0], [39, 18, 200], [33, 17, 400]].map(([x, y, d]) => (
        <circle key={x} className="vbc-miette" cx={x} cy={y} r="1.2" fill="#C9A13B" style={{ animationDelay: `${1100 + d}ms` }} />
      ))}
    </svg>
  );
}

const STYLE_COOKIES = `
  @keyframes vbc-entree { 0% { opacity: 0; transform: translateY(110%) scale(.96); } 60% { opacity: 1; transform: translateY(-6px) scale(1.01); } 100% { transform: none; } }
  @keyframes vbc-sortie { to { opacity: 0; transform: translateY(40px) scale(.97); } }
  @keyframes vbc-biscuit { 0% { transform: scale(0) rotate(-120deg); } 70% { transform: scale(1.15) rotate(10deg); } 100% { transform: none; } }
  @keyframes vbc-bouchee { to { r: 8px; } }
  @keyframes vbc-miette { 0% { opacity: 0; transform: none; } 15% { opacity: 1; } 100% { opacity: 0; transform: translate(4px, 22px); } }
  @keyframes vbc-deplie { from { opacity: 0; max-height: 0; transform: translateY(-6px); } to { opacity: 1; max-height: 640px; transform: none; } }
  @keyframes vbc-ligne { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: none; } }
  @keyframes vbc-reflet { 0%, 70% { transform: translateX(-120%) skewX(-20deg); } 100% { transform: translateX(260%) skewX(-20deg); } }
  .vbc-entree { animation: vbc-entree .7s cubic-bezier(.2,.9,.25,1) .25s both; }
  .vbc-sortie { animation: vbc-sortie .28s ease-in forwards; }
  .vbc-biscuit { animation: vbc-biscuit .8s cubic-bezier(.2,.9,.25,1) .5s both; }
  .vbc-bouchee { animation: vbc-bouchee .25s ease-out 1s forwards; }
  .vbc-miette { opacity: 0; animation: vbc-miette 1.1s ease-in forwards; }
  .vbc-deplie { animation: vbc-deplie .45s cubic-bezier(.2,.8,.2,1) both; overflow: hidden; }
  .vbc-ligne { animation: vbc-ligne .4s ease-out both; }
  .vbc-reflet::after { content: ""; position: absolute; inset: 0; width: 40%; background: linear-gradient(90deg, transparent, rgba(255,255,255,.45), transparent); animation: vbc-reflet 3.2s ease-in-out 1.5s infinite; }
  @media (prefers-reduced-motion: reduce) { .vbc-entree, .vbc-sortie, .vbc-biscuit, .vbc-miette, .vbc-deplie, .vbc-ligne, .vbc-reflet::after { animation: none; opacity: 1; } .vbc-bouchee { animation: none; r: 8px; } .vbc-miette { opacity: 0; } .vbc-sortie { opacity: 0; } }
`;

export function BandeauCookies() {
  const [ouvert, setOuvert] = useState(() => lireConsentement() === null);
  const [details, setDetails] = useState(false);
  const [erreurs, setErreurs] = useState(() => !!lireConsentement()?.erreurs);
  const [sortie, setSortie] = useState(false);
  const titre = useRef(null);

  useEffect(() => {
    const ouvrir = () => { setErreurs(!!lireConsentement()?.erreurs); setDetails(true); setSortie(false); setOuvert(true); };
    window.addEventListener(EVENEMENT, ouvrir);
    return () => window.removeEventListener(EVENEMENT, ouvrir);
  }, []);
  useEffect(() => { if (ouvert) titre.current?.focus(); }, [ouvert, details]);

  if (!ouvert) return null;
  // Sortie animée, puis le bandeau disparaît (le choix est enregistré tout de suite)
  const fermer = () => { setSortie(true); setTimeout(() => { setOuvert(false); setDetails(false); setSortie(false); }, 280); };
  const choisir = v => { enregistrer(v); fermer(); };
  const bouton = "relative overflow-hidden flex-1 min-w-[8.5rem] px-4 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 hover:-translate-y-0.5 active:translate-y-0 active:scale-[.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-laiton-400";
  const neutre = `${bouton} border border-white/25 text-white hover:bg-white/10`;

  return (
    <div className="fixed inset-x-0 bottom-0 z-[60] p-3 sm:p-5 pointer-events-none">
      <style>{STYLE_COOKIES}</style>
      <section role="dialog" aria-modal="false" aria-labelledby="cookies-titre"
        className={`${sortie ? "vbc-sortie" : "vbc-entree"} pointer-events-auto mx-auto max-w-2xl`}>
        <div className="max-h-[88vh] overflow-y-auto rounded-2xl border border-laiton-400/30 bg-[#0E332D] text-gray-100 shadow-2xl">
        <div className="p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 grid h-11 w-11 flex-shrink-0 place-items-center rounded-xl bg-laiton-400/10">
              <BiscuitAnime />
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
              <button type="button" onClick={fermer} aria-label={tx("Fermer")}
                className="rounded-lg p-1 text-gray-400 hover:text-white"><X size={18} /></button>
            )}
          </div>

          {details && (
            <div className="vbc-deplie mt-4 space-y-3">
              <div className="vbc-ligne rounded-xl border border-white/10 bg-white/5 p-4" style={{ animationDelay: "120ms" }}>
                <div className="flex items-center justify-between gap-3">
                  <p className="flex items-center gap-2 text-sm font-semibold text-white">
                    <ShieldCheck size={15} className="text-emerald-400" aria-hidden="true" />{tx("Strictement nécessaires")}
                  </p>
                  <span className="whitespace-nowrap rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-medium text-emerald-300">{tx("Toujours actifs")}</span>
                </div>
                <ul className="mt-2 space-y-1 text-xs text-gray-300">
                  {NECESSAIRES.map(([t, d], i) => <li key={t} className="vbc-ligne" style={{ animationDelay: `${220 + i * 90}ms` }}><strong className="text-gray-100">{tx(t)}</strong>{LANGUE === "en" ? ": " : " : "}{tx(d)}</li>)}
                </ul>
              </div>
              <label className="vbc-ligne flex cursor-pointer items-start justify-between gap-4 rounded-xl border border-white/10 bg-white/5 p-4 transition-colors hover:border-laiton-400/40" style={{ animationDelay: "320ms" }}>
                <span>
                  <span className="block text-sm font-semibold text-white">{tx("Rapports d'erreurs anonymes")}</span>
                  <span className="mt-1 block text-xs text-gray-300">
                    {tx("En cas de plantage, une description technique part chez notre prestataire Sentry : jamais ton nom, ton adresse IP, ce que tu tapes ni tes données bancaires.")}
                  </span>
                </span>
                <input type="checkbox" role="switch" checked={erreurs} onChange={e => setErreurs(e.target.checked)}
                  aria-label={tx("Rapports d'erreurs anonymes")} className="peer sr-only" />
                <span aria-hidden="true" className={`relative mt-0.5 h-6 w-11 flex-shrink-0 rounded-full transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-laiton-400 ${erreurs ? "bg-laiton-400" : "bg-white/20"}`}>
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all duration-300 ease-[cubic-bezier(.3,1.6,.5,1)] ${erreurs ? "left-[1.375rem]" : "left-0.5"}`} />
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
              className={`${bouton} vbc-reflet bg-laiton-400 text-[#0E332D] shadow-lg shadow-laiton-400/20 hover:bg-laiton-300`}>{tx("Tout accepter")}</button>
          </div>
          <p className="mt-3 text-[11px] text-gray-400">
            <a href={`/confidentialite/${LANGUE === "en" ? "#cookies-en" : "#cookies"}`} target="_blank" rel="noopener noreferrer"
              className="underline hover:text-gray-200">{tx("Détail des cookies et du stockage")}</a>
            {" · "}{tx("Tu peux changer d'avis à tout moment avec « Gérer les cookies » en bas de page.")}
          </p>
        </div>
        </div>
      </section>
    </div>
  );
}
