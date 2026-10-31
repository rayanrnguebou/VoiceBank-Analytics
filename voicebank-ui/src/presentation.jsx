// Présentation animée « VoiceBank aussi sur ton téléphone » : à CHAQUE ouverture du site dans un navigateur (y compris
// un rechargement), pour tout le monde, avec ou sans compte, connecté ou non. Seule exception : l'application installée
// (Android, écran d'accueil), où proposer de l'installer n'aurait pas de sens. Le bandeau des cookies suit sa fermeture.
// Motifs : géométrie originale inspirée des tissus d'Afrique (ndop camerounais : losanges, damiers, cercles indigo),
// salutations africaines et internationales, silhouette de grande ville.
import { useEffect, useRef, useState } from "react";
import { Download, Monitor, Play, Share, Smartphone, SquarePlus, X } from "lucide-react";
import { tx } from "./i18n";
import { Film, STYLE_FILM, TEXTE_FIN, dire, taire } from "./film";

const PLAY_STORE = import.meta.env.REACT_APP_PLAY_STORE_URL || "";
export const EVENEMENT_FERMEE = "voicebank-presentation-fermee";

export const SALUTATIONS = ["Bienvenue", "Mbolo", "Akwaba", "Jambo", "Sannu", "Dalal ak jamm", "Welcome", "Bienvenidos", "Willkommen"];

// L'invitation d'installation du navigateur arrive tôt : on la garde dès le chargement du module
let invitation = null;
if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); invitation = e; });
}

export function appareil() {
  const ua = navigator.userAgent || "";
  if (/android/i.test(ua)) return "android";
  if (/iphone|ipad|ipod/i.test(ua) || (/macintosh/i.test(ua) && navigator.maxTouchPoints > 1)) return "ios";
  return "ordinateur";
}

export function applicationInstallee() {
  return window.matchMedia?.("(display-mode: standalone)").matches || navigator.standalone === true
    || (document.referrer || "").startsWith("android-app://");
}

export function doitPresenter() {
  // window.__voicebankSansPresentation : posé uniquement par les tests de bout en bout, pour ne pas couvrir leurs écrans
  return !applicationInstallee() && !window.__voicebankSansPresentation;
}

function Motif() {
  // Tuile de 48 px : losange laiton, damier indigo, cercle et points, comme les bandes d'un pagne ndop
  return (
    <svg aria-hidden="true" className="vb-motif absolute inset-0 h-full w-full opacity-[0.16]">
      <defs>
        <pattern id="vb-ndop" width="48" height="48" patternUnits="userSpaceOnUse">
          <path d="M24 4 L44 24 L24 44 L4 24 Z" fill="none" stroke="#E2C877" strokeWidth="1.5" />
          <path d="M24 14 L34 24 L24 34 L14 24 Z" fill="#3B4C9B" />
          <circle cx="24" cy="24" r="3" fill="#F0E1B0" />
          <rect x="0" y="0" width="6" height="6" fill="#3B4C9B" /><rect x="42" y="42" width="6" height="6" fill="#3B4C9B" />
          <circle cx="0" cy="48" r="2" fill="#E2C877" /><circle cx="48" cy="0" r="2" fill="#E2C877" />
        </pattern>
      </defs>
      <rect width="200%" height="200%" fill="url(#vb-ndop)" />
    </svg>
  );
}

function Ville() {
  // Silhouette inventée : tours, dômes, palmiers et pont — une grande ville d'Afrique autant que d'ailleurs
  return (
    <svg aria-hidden="true" viewBox="0 0 600 70" preserveAspectRatio="none" className="absolute inset-x-0 bottom-0 h-14 w-full text-[#0A2621]">
      <path fill="currentColor" d="M0 70 V48 h18 v-14 h12 v14 h10 V30 h16 v40 h6 V20 h14 v8 h6 v42 h10 V44 q14 -22 28 0 v26 h8 V36 h4 V24 h8 v12 h4 v34
        h12 V52 l10 -8 l10 8 v18 h8 V14 h6 V6 h4 v8 h6 v56 h10 V40 h20 v30 h6 V50 q4 -18 8 -26 q4 8 8 26 v20 h12 V34 h18 v36
        h6 V46 q22 -16 44 0 v24 h8 V26 h10 v-8 h8 v8 h10 v44 h10 V54 c20 -14 40 -14 60 0 V70 h10 V38 h14 v32 h8 V28 h18 v42 h6
        V48 h12 V70 Z" />
      <path fill="none" stroke="currentColor" strokeWidth="2" d="M470 44 q8 -14 0 -28 M470 16 q-10 0 -14 6 M470 16 q10 -2 14 4 M470 16 q-4 -8 -12 -8 M470 16 q6 -8 14 -6" />
    </svg>
  );
}

function Telephone() {
  return (
    <div className="vb-flotte relative mx-auto w-[150px] sm:w-[190px]">
      <div className="absolute -inset-6 rounded-full bg-laiton-400/20 blur-2xl" aria-hidden="true" />
      <div className="relative rounded-[28px] border-[6px] border-[#0A1F1B] bg-[#0A1F1B] shadow-2xl">
        <div className="absolute left-1/2 top-1.5 z-10 h-1.5 w-12 -translate-x-1/2 rounded-full bg-black/60" />
        <img src="/captures/telephone-assistant.png" alt={tx("L'assistant VoiceBank sur un téléphone")}
          className="block aspect-[780/1688] w-full rounded-[22px] object-cover" loading="lazy" />
      </div>
    </div>
  );
}

function Salutations() {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return undefined;
    const t = setInterval(() => setI(n => (n + 1) % SALUTATIONS.length), 1600);
    return () => clearInterval(t);
  }, []);
  return (
    <p className="h-8 overflow-hidden text-2xl font-bold tracking-tight text-laiton-300" aria-hidden="true">
      <span key={i} className="vb-salut inline-block">{SALUTATIONS[i]}</span>
    </p>
  );
}

function Action({ type, onFermer }) {
  const [etapes, setEtapes] = useState(false);
  const principal = "inline-flex items-center justify-center gap-2 rounded-xl bg-laiton-400 px-5 py-3 text-sm font-semibold text-[#0E332D] shadow-lg hover:bg-laiton-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-white";
  const installer = async () => {
    if (!invitation) { setEtapes(true); return; }
    invitation.prompt();
    const choix = await invitation.userChoice.catch(() => null);
    invitation = null;
    if (choix?.outcome === "accepted") onFermer();
  };
  if (type === "android" && PLAY_STORE) {
    return <a href={PLAY_STORE} target="_blank" rel="noopener noreferrer" className={principal}><Smartphone size={17} />{tx("Télécharger sur Google Play")}</a>;
  }
  if (type === "ios") {
    return (
      <ol className="space-y-2 text-sm text-gray-200">
        <li className="flex items-center gap-2"><span className="grid h-6 w-6 place-items-center rounded-full bg-white/10 text-xs font-bold">1</span>
          {tx("Touche")}<Share size={15} className="text-laiton-300" aria-label={tx("Partager")} />{tx("en bas de Safari")}</li>
        <li className="flex items-center gap-2"><span className="grid h-6 w-6 place-items-center rounded-full bg-white/10 text-xs font-bold">2</span>
          {tx("Choisis")}<SquarePlus size={15} className="text-laiton-300" aria-hidden="true" /><strong>{tx("Sur l'écran d'accueil")}</strong></li>
      </ol>
    );
  }
  return (
    <div className="space-y-2">
      <button type="button" onClick={installer} className={principal}>
        {type === "ordinateur" ? <Monitor size={17} /> : <Download size={17} />}
        {type === "ordinateur" ? tx("Installer sur cet ordinateur") : tx("Installer l'application")}
      </button>
      {etapes && (
        <p role="status" className="text-xs text-gray-300">
          {type === "android" ? tx("Ouvre le menu ⋮ de Chrome puis « Installer l'application ».")
            : tx("Clique sur l'icône « Installer » à droite de la barre d'adresse (Chrome ou Edge).")}
        </p>
      )}
    </div>
  );
}

const mouvementReduit = () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;

export function PresentationApplications() {
  const [ouvert, setOuvert] = useState(false);
  const [phase, setPhase] = useState(() => (mouvementReduit() ? "fin" : "film"));     // film, puis carte finale
  const titre = useRef(null);
  const type = appareil();

  useEffect(() => {
    if (doitPresenter()) setOuvert(true);
  }, []);
  useEffect(() => {
    if (!ouvert) return undefined;
    if (phase === "fin") titre.current?.focus();
    const echap = e => { if (e.key === "Escape") fermer(); };
    window.addEventListener("keydown", echap);
    return () => window.removeEventListener("keydown", echap);
  }, [ouvert, phase]);

  if (!ouvert) return null;
  function fermer() {
    taire();
    setOuvert(false);
    window.dispatchEvent(new Event(EVENEMENT_FERMEE));       // au tour du bandeau des cookies
  }
  const finFilm = son => { setPhase("fin"); if (son) dire(tx(TEXTE_FIN), undefined, "fin"); };
  const plateformes = [["android", "Android"], ["ios", "iPhone"], ["ordinateur", tx("Ordinateur")]];

  return (
    <div className="fixed inset-0 z-[55] grid place-items-center overflow-y-auto bg-black/60 p-3 backdrop-blur-sm" onClick={fermer}>
      <style>{`
        @keyframes vb-derive { from { transform: translate(0, 0); } to { transform: translate(-48px, -48px); } }
        @keyframes vb-flotte { 0%, 100% { transform: translateY(0) rotate(-3deg); } 50% { transform: translateY(-10px) rotate(-1deg); } }
        @keyframes vb-salut { from { opacity: 0; transform: translateY(70%); } to { opacity: 1; transform: translateY(0); } }
        @keyframes vb-entree { from { opacity: 0; transform: translateY(24px) scale(.97); } to { opacity: 1; transform: none; } }
        .vb-motif { animation: vb-derive 18s linear infinite; }
        .vb-flotte { animation: vb-flotte 6s ease-in-out infinite; }
        .vb-salut { animation: vb-salut .45s ease-out; }
        .vb-entree { animation: vb-entree .5s cubic-bezier(.2,.8,.2,1); }
        ${STYLE_FILM}
        @media (prefers-reduced-motion: reduce) { .vb-motif, .vb-flotte, .vb-salut, .vb-entree { animation: none; } }
      `}</style>
      <section role="dialog" aria-modal="true" aria-label={tx("VoiceBank, aussi dans ta poche")} onClick={e => e.stopPropagation()}
        className="vb-entree relative w-full max-w-3xl overflow-hidden rounded-3xl border border-laiton-400/30 bg-gradient-to-br from-[#0E332D] via-[#123F37] to-[#0B2A25] text-white shadow-2xl">
        <Motif />
        <Ville />
        <div className="absolute inset-x-0 top-0 h-1.5 bg-[repeating-linear-gradient(90deg,#C9A13B_0_18px,#3B4C9B_18px_30px,#F0E1B0_30px_36px,#1F654D_36px_54px)]" aria-hidden="true" />
        <button type="button" onClick={fermer} aria-label={tx("Fermer")}
          className="absolute right-3 top-4 z-20 rounded-full bg-black/30 p-1.5 text-gray-200 hover:bg-black/50 hover:text-white"><X size={18} /></button>

        {phase === "film" ? <Film onFin={finFilm} /> : (
        <div className="vb-entree relative z-10 grid gap-6 px-6 pb-20 pt-9 sm:grid-cols-[1.15fr_1fr] sm:items-center sm:px-10 sm:pb-24">
          <div>
            <Salutations />
            <h2 id="presentation-titre" ref={titre} tabIndex={-1} className="mt-2 text-2xl font-extrabold leading-tight focus:outline-none sm:text-3xl">
              {tx("VoiceBank, aussi dans ta poche")}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-gray-200 sm:text-base">
              {tx("Pose tes questions à la voix, reçois les alertes de fraude et approuve tes connexions d'un geste : la même banque intelligente, de Douala à Paris, sur ton téléphone comme sur ton ordinateur.")}
            </p>
            <ul className="mt-4 flex flex-wrap gap-2" aria-label={tx("Disponible sur")}>
              {plateformes.map(([cle, nom]) => (
                <li key={cle} className={`rounded-full px-3 py-1 text-xs font-medium ${cle === type ? "bg-laiton-400 text-[#0E332D]" : "bg-white/10 text-gray-200"}`}>{nom}</li>
              ))}
            </ul>
            <div className="mt-5"><Action type={type} onFermer={fermer} /></div>
            <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
              <button type="button" onClick={fermer} className="text-sm text-gray-300 underline-offset-4 hover:text-white hover:underline">
                {tx("Continuer sur le site")}
              </button>
              <button type="button" onClick={() => { taire(); setPhase("film"); }}
                className="inline-flex items-center gap-1.5 text-sm text-gray-300 hover:text-white">
                <Play size={14} />{tx("Revoir la vidéo")}
              </button>
            </div>
          </div>
          <div className="hidden sm:block"><Telephone /></div>
        </div>
        )}
      </section>
    </div>
  );
}
