// Petit film de présentation (environ 30 s), dessiné en code : léger, net sur tous les écrans, traduit, sans fichier
// vidéo à télécharger. Une voix lit chaque scène (synthèse vocale du navigateur) dès que l'utilisateur active le son :
// les navigateurs interdisent le son automatique, le film démarre donc en muet avec ses sous-titres.
import { useEffect, useRef, useState } from "react";
import { BellRing, Check, Mic, ShieldCheck, SkipForward, Volume2, VolumeX } from "lucide-react";
import { LOCALE_VOIX, tx } from "./i18n";

export const SCENES = [
  { id: "accueil", duree: 4200, texte: "Bienvenue sur VoiceBank, la banque qui comprend ta voix." },
  { id: "voix", duree: 5600, texte: "Pose tes questions à la voix, en français ou en anglais : la réponse arrive en quelques secondes, avec ses graphiques." },
  { id: "fraude", duree: 5000, texte: "VoiceBank repère les opérations suspectes et t'alerte aussitôt." },
  { id: "approbation", duree: 5000, texte: "Pour te connecter, choisis simplement le bon nombre sur ton téléphone." },
  { id: "monde", duree: 5400, texte: "De Douala à Paris, d'Abidjan à Montréal, VoiceBank t'accompagne partout." },
];
export const TEXTE_FIN = "Disponible sur Android, iPhone et ordinateur. Installe-la dès maintenant !";

// ── Voix ────────────────────────────────────────────────────────────
function meilleureVoix() {
  const voix = window.speechSynthesis?.getVoices?.() || [];
  const langue = LOCALE_VOIX.slice(0, 2);
  const candidates = voix.filter(v => (v.lang || "").toLowerCase().startsWith(langue));
  const naturelle = /natural|neural|online|google|premium|enhanced|denise|henri|vivienne|eloise|amélie|thomas|aria|jenny|guy/i;
  return candidates.find(v => naturelle.test(v.name)) || candidates.find(v => v.lang === LOCALE_VOIX) || candidates[0] || null;
}

export function dire(texte, finie) {
  const s = window.speechSynthesis;
  if (!s || typeof window.SpeechSynthesisUtterance === "undefined") { finie?.(); return; }
  s.cancel();
  const u = new window.SpeechSynthesisUtterance(texte);
  u.lang = LOCALE_VOIX; u.rate = 1; u.pitch = 1;
  const v = meilleureVoix();
  if (v) u.voice = v;
  u.onend = () => finie?.(); u.onerror = () => finie?.();
  s.speak(u);
}

export function taire() {
  try { window.speechSynthesis?.cancel(); } catch (e) { /* rien */ }
}

// ── Scènes ──────────────────────────────────────────────────────────
const Apparait = ({ delai = 0, className = "", children }) => (
  <div className={`vbf-apparait ${className}`} style={{ animationDelay: `${delai}ms` }}>{children}</div>
);

function SceneAccueil() {
  const mots = ["Bienvenue", "Mbolo", "Akwaba", "Welcome", "Jambo", "Bienvenidos"];
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <div className="relative grid h-24 w-24 place-items-center">
        {[0, 1, 2].map(i => <span key={i} className="vbf-onde absolute inset-0 rounded-3xl border-2 border-laiton-400/60" style={{ animationDelay: `${i * 600}ms` }} />)}
        <span className="vbf-logo grid h-20 w-20 place-items-center rounded-3xl bg-laiton-400 text-4xl font-black text-[#0E332D] shadow-2xl">V</span>
      </div>
      <Apparait delai={500}><p className="mt-6 text-3xl font-extrabold tracking-tight sm:text-4xl">VoiceBank</p></Apparait>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        {mots.map((m, i) => (
          <Apparait key={m} delai={900 + i * 280}>
            <span className="rounded-full bg-white/10 px-3 py-1 text-sm font-semibold text-laiton-200">{m}</span>
          </Apparait>
        ))}
      </div>
    </div>
  );
}

function SceneVoix() {
  const question = tx("Combien de transactions à Douala ce mois-ci ?");
  const barres = [38, 62, 45, 80, 58, 92];
  return (
    <div className="grid h-full content-center items-center gap-4 sm:grid-cols-2 sm:gap-6">
      <div className="flex items-center justify-center gap-4 sm:flex-col">
        <div className="relative grid h-16 w-16 flex-shrink-0 place-items-center sm:h-24 sm:w-24">
          {[0, 1].map(i => <span key={i} className="vbf-pulse absolute inset-0 rounded-full bg-emerald-400/30" style={{ animationDelay: `${i * 700}ms` }} />)}
          <span className="relative grid h-14 w-14 place-items-center rounded-full bg-emerald-600 shadow-xl sm:h-20 sm:w-20"><Mic size={30} /></span>
        </div>
        <div className="flex h-10 items-end gap-1 sm:mt-4" aria-hidden="true">
          {Array.from({ length: 14 }, (_, i) => (
            <span key={i} className="vbf-son w-1.5 rounded-full bg-laiton-300" style={{ animationDelay: `${(i * 97) % 600}ms` }} />
          ))}
        </div>
      </div>
      <div className="space-y-3">
        <Apparait delai={300}>
          <p className="vbf-frappe rounded-2xl rounded-bl-sm bg-white/95 px-4 py-3 text-sm font-medium text-[#0E332D] shadow-lg"
            style={{ "--n": question.length }}>{question}</p>
        </Apparait>
        <Apparait delai={2300} className="rounded-2xl border border-white/10 bg-[#0A2621]/80 p-4 shadow-xl">
          <p className="text-xs text-gray-400">{tx("Réponse en 1,2 s")}</p>
          <p className="text-2xl font-extrabold">12 480 <span className="text-sm font-semibold text-emerald-300">+8 %</span></p>
          <div className="mt-2 flex h-10 items-end gap-1.5 sm:h-14">
            {barres.map((h, i) => (
              <span key={i} className="vbf-barre flex-1 rounded-t bg-gradient-to-t from-emerald-600 to-laiton-300"
                style={{ height: `${h}%`, animationDelay: `${2600 + i * 120}ms` }} />
            ))}
          </div>
        </Apparait>
      </div>
    </div>
  );
}

function SceneFraude() {
  return (
    <div className="flex h-full items-center justify-center gap-8">
      <div className="relative h-56 w-32 flex-shrink-0 rounded-[26px] border-[5px] border-[#081C18] bg-[#123F37] shadow-2xl sm:h-64 sm:w-36">
        <div className="vbf-notif absolute inset-x-2 top-6 rounded-xl bg-white p-2 text-[#0E332D] shadow-xl">
          <p className="flex items-center gap-1 text-[10px] font-bold text-red-600"><BellRing size={11} />{tx("Alerte critique")}</p>
          <p className="text-[11px] font-extrabold">2 500 000 FCFA</p>
          <p className="text-[9px] text-gray-500">{tx("Yaoundé · 3 h 12")}</p>
        </div>
      </div>
      <div className="relative grid h-28 w-28 place-items-center">
        <span className="vbf-alarme absolute inset-0 rounded-full bg-red-500/30" />
        <span className="vbf-bouclier relative grid h-24 w-24 place-items-center rounded-full shadow-2xl"><ShieldCheck size={44} /></span>
        <Apparait delai={3000} className="absolute -bottom-9 whitespace-nowrap rounded-full bg-emerald-500 px-3 py-1 text-xs font-bold">
          {tx("Opération bloquée")}
        </Apparait>
      </div>
    </div>
  );
}

function SceneApprobation() {
  return (
    <div className="flex h-full items-center justify-center gap-6 sm:gap-10">
      <Apparait className="w-40 sm:w-52">
        <div className="rounded-xl border-4 border-[#081C18] bg-[#0A2621] p-3 text-center shadow-2xl">
          <p className="text-[10px] text-gray-400">{tx("Choisis ce nombre")}</p>
          <p className="text-4xl font-black text-laiton-300">47</p>
        </div>
        <div className="mx-auto h-2 w-24 rounded-b-lg bg-[#081C18]" />
      </Apparait>
      <Apparait delai={600} className="h-52 w-28 rounded-[24px] border-[5px] border-[#081C18] bg-[#123F37] p-2 shadow-2xl">
        <p className="mt-3 text-center text-[10px] font-semibold">{tx("Connexion demandée")}</p>
        <div className="mt-3 space-y-2">
          {[12, 47, 83].map(n => (
            <span key={n} className={`block rounded-lg py-1.5 text-center text-sm font-bold ${n === 47 ? "vbf-choix" : "bg-white/10"}`}>{n}</span>
          ))}
        </div>
        <Apparait delai={2900} className="mt-3 flex justify-center">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-emerald-500"><Check size={18} /></span>
        </Apparait>
      </Apparait>
    </div>
  );
}

const VILLES = [["Dakar", 14, 40], ["Abidjan", 30, 66], ["Douala", 50, 70], ["Kinshasa", 60, 84], ["Paris", 46, 18], ["Montréal", 84, 22]];

function SceneMonde() {
  const [, dx, dy] = VILLES[2];
  return (
    <div className="relative h-full w-full">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden="true">
        {VILLES.filter(v => v[0] !== "Douala").map(([n, x, y], i) => (
          <path key={n} d={`M${dx} ${dy} Q ${(dx + x) / 2} ${Math.min(dy, y) - 18} ${x} ${y}`} pathLength="1"
            className="vbf-trace" fill="none" stroke="#E2C877" strokeWidth="0.45" strokeLinecap="round"
            style={{ animationDelay: `${400 + i * 450}ms` }} />
        ))}
      </svg>
      {VILLES.map(([n, x, y], i) => (
        <div key={n} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ left: `${x}%`, top: `${y}%` }}>
          <Apparait delai={n === "Douala" ? 0 : 400 + i * 400} className="flex flex-col items-center">
            <span className={`block rounded-full ${n === "Douala" ? "vbf-pulse-fixe h-4 w-4 bg-laiton-300" : "h-2.5 w-2.5 bg-emerald-300"}`} />
            <span className="mt-1 rounded bg-black/30 px-1.5 text-[11px] font-semibold sm:text-xs">{n}</span>
          </Apparait>
        </div>
      ))}
    </div>
  );
}

const DESSINS = { accueil: SceneAccueil, voix: SceneVoix, fraude: SceneFraude, approbation: SceneApprobation, monde: SceneMonde };

// ── Lecteur ─────────────────────────────────────────────────────────
export function Film({ onFin }) {
  const [etape, setEtape] = useState(0);
  const [son, setSon] = useState(false);
  const fin = useRef(onFin);
  fin.current = onFin;

  useEffect(() => {
    const scene = SCENES[etape];
    let tempsFini = false, voixFinie = !son, arretee = false;
    const suivante = () => {
      if (arretee || !tempsFini || !voixFinie) return;
      if (etape + 1 < SCENES.length) setEtape(etape + 1); else fin.current(son);
    };
    const t = setTimeout(() => { tempsFini = true; suivante(); }, scene.duree);
    // Garde-fou : une voix qui ne répond pas ne bloque jamais le film
    const g = son ? setTimeout(() => { voixFinie = true; suivante(); }, scene.duree + 9000) : null;
    if (son) dire(tx(scene.texte), () => { voixFinie = true; setTimeout(suivante, 350); });
    return () => { arretee = true; clearTimeout(t); clearTimeout(g); };
  }, [etape, son]);
  useEffect(() => taire, []);

  const Dessin = DESSINS[SCENES[etape].id];
  const basculerSon = () => { if (son) taire(); setSon(!son); };

  return (
    <div className="relative z-10 flex flex-col px-5 pb-16 pt-7 sm:px-8 sm:pb-20">
      <div className="flex gap-1.5" aria-hidden="true">
        {SCENES.map((s, i) => (
          <span key={s.id} className="h-1 flex-1 overflow-hidden rounded-full bg-white/20">
            <span className={`block h-full bg-laiton-300 ${i < etape ? "w-full" : i === etape ? "vbf-progression" : "w-0"}`}
              style={i === etape ? { animationDuration: `${s.duree}ms` } : undefined} />
          </span>
        ))}
      </div>
      <div key={etape} className="vbf-scene relative mt-5 h-[320px] sm:h-[300px]" role="img" aria-label={tx(SCENES[etape].texte)}>
        <Dessin />
      </div>
      <p className="mt-4 min-h-[3rem] text-center text-sm font-medium text-white drop-shadow sm:text-base" aria-hidden="true">
        <span key={etape} className="vbf-apparait inline-block rounded-lg bg-black/35 px-3 py-1.5">{tx(SCENES[etape].texte)}</span>
      </p>
      <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
        <button type="button" onClick={basculerSon}
          className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold ${son ? "bg-white/15 text-white hover:bg-white/25" : "vbf-appel bg-laiton-400 text-[#0E332D] hover:bg-laiton-300"}`}>
          {son ? <VolumeX size={16} /> : <Volume2 size={16} />}{son ? tx("Couper le son") : tx("Activer le son")}
        </button>
        <button type="button" onClick={() => { taire(); fin.current(son); }}
          className="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm font-semibold text-gray-100 hover:bg-white/20">
          <SkipForward size={16} />{tx("Passer la vidéo")}
        </button>
      </div>
    </div>
  );
}

export const STYLE_FILM = `
  @keyframes vbf-apparait { from { opacity: 0; transform: translateY(14px) scale(.96); } to { opacity: 1; transform: none; } }
  @keyframes vbf-onde { from { transform: scale(.9); opacity: .9; } to { transform: scale(1.9); opacity: 0; } }
  @keyframes vbf-logo { 0% { transform: scale(.2) rotate(-30deg); opacity: 0; } 60% { transform: scale(1.12) rotate(4deg); opacity: 1; } 100% { transform: none; } }
  @keyframes vbf-pulse { from { transform: scale(1); opacity: .8; } to { transform: scale(1.8); opacity: 0; } }
  @keyframes vbf-son { 0%, 100% { height: 18%; } 50% { height: 100%; } }
  @keyframes vbf-frappe { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0 0 0); } }
  @keyframes vbf-barre { from { transform: scaleY(0); } to { transform: scaleY(1); } }
  @keyframes vbf-notif { 0% { transform: translateY(-140%); opacity: 0; } 15%, 100% { transform: none; opacity: 1; } }
  @keyframes vbf-alarme { 0% { transform: scale(1); opacity: .9; } 100% { transform: scale(1.7); opacity: 0; } }
  @keyframes vbf-bouclier { 0%, 50% { background: #DC2626; } 62%, 100% { background: #059669; } }
  @keyframes vbf-choix { 0%, 45% { background: rgba(255,255,255,.1); transform: none; } 55% { transform: scale(.92); } 65%, 100% { background: #C9A13B; color: #0E332D; transform: scale(1.06); } }
  @keyframes vbf-trace { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
  @keyframes vbf-progression { from { width: 0; } to { width: 100%; } }
  @keyframes vbf-scene { from { opacity: 0; transform: scale(1.03); } to { opacity: 1; transform: none; } }
  @keyframes vbf-appel { 0%, 100% { box-shadow: 0 0 0 0 rgba(201,161,59,.6); } 50% { box-shadow: 0 0 0 10px rgba(201,161,59,0); } }
  .vbf-apparait { animation: vbf-apparait .6s cubic-bezier(.2,.8,.2,1) both; }
  .vbf-onde { animation: vbf-onde 1.8s ease-out infinite; }
  .vbf-logo { animation: vbf-logo .9s cubic-bezier(.2,.8,.2,1) both; }
  .vbf-pulse { animation: vbf-pulse 1.4s ease-out infinite; }
  .vbf-pulse-fixe { animation: vbf-appel 1.6s ease-in-out infinite; }
  .vbf-son { animation: vbf-son .7s ease-in-out infinite; height: 30%; }
  .vbf-frappe { animation: vbf-frappe 1.8s steps(var(--n), end) .5s both; }
  .vbf-barre { animation: vbf-barre .5s cubic-bezier(.2,.8,.2,1) both; transform-origin: bottom; }
  .vbf-notif { animation: vbf-notif 3.4s cubic-bezier(.2,.8,.2,1) .4s both; }
  .vbf-alarme { animation: vbf-alarme 1.1s ease-out 3; }
  .vbf-bouclier { animation: vbf-bouclier 3.4s ease both; }
  .vbf-choix { animation: vbf-choix 2.6s ease both; }
  .vbf-trace { stroke-dasharray: 1; stroke-dashoffset: 1; animation: vbf-trace 1.2s ease-out forwards; }
  .vbf-progression { width: 0; animation: vbf-progression linear forwards; }
  .vbf-scene { animation: vbf-scene .5s ease both; }
  .vbf-appel { animation: vbf-appel 1.6s ease-in-out infinite; }
`;

