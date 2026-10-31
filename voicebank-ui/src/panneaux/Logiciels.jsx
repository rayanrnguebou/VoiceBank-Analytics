// Logiciels bancaires branchés sur VoiceBank : état (en ligne, hors ligne), et pour chacun un tableau de bord en
// direct : le parcours de chaque opération (logiciel → VoiceBank → décision), les chiffres du jour, les 24 dernières
// heures et le fil des appels, rafraîchi toutes les 4 secondes.
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Building2, Cpu, Pause, Play, Plug, ShieldCheck, ShieldAlert, ShieldX, Timer, Radio } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { http, messageErreur } from "../api";
import { useDevise } from "../devise";
import { carte, titre, texteDiscret, boutonSecondaire } from "../ui";
import { LOCALE, tx } from "../i18n";
import { ClesApi } from "./ClesApi";

const DECISIONS = {
  accepter: { libelle: "Acceptée", couleur: "#059669", classe: "bg-emerald-500/15 text-emerald-600", Icone: ShieldCheck },
  verifier: { libelle: "À vérifier", couleur: "#EA580C", classe: "bg-orange-500/15 text-orange-600", Icone: ShieldAlert },
  bloquer:  { libelle: "Bloquée", couleur: "#DC2626", classe: "bg-red-500/15 text-red-600", Icone: ShieldX },
};
const RAFRAICHIR_MS = 4000;

function depuis(iso) {
  if (!iso) return null;
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return tx("à l'instant");
  if (s < 3600) return tx("il y a {x} min", { x: Math.round(s / 60) });
  if (s < 86400) return tx("il y a {x} h", { x: Math.round(s / 3600) });
  return new Date(iso).toLocaleDateString(LOCALE);
}

export function Etat({ cle }) {
  if (cle.revoquee) return <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-gray-500/15 text-gray-500">{tx("Révoquée")}</span>;
  if (cle.en_ligne) return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600">
      <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full rounded-full bg-emerald-500 opacity-75 animate-ping" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" /></span>{tx("En ligne")}</span>
  );
  if (!cle.premiere_utilisation) return <span className="whitespace-nowrap text-[11px] font-semibold px-2 py-0.5 rounded-full bg-laiton-400/20 text-laiton-600">{tx("En attente du premier appel")}</span>;
  return <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-gray-500/15 text-gray-500">{tx("Hors ligne")}</span>;
}

function Chip({ decision, mode }) {
  const d = DECISIONS[decision] || DECISIONS.accepter;
  // En observation, rien n'a été bloqué : on montre ce que VoiceBank AURAIT décidé
  const libelle = mode === "observation" && decision !== "accepter"
    ? (decision === "bloquer" ? tx("Aurait bloqué") : tx("Aurait fait vérifier")) : tx(d.libelle);
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap text-[11px] font-semibold px-2 py-0.5 rounded-full ${d.classe} ${mode === "observation" && decision !== "accepter" ? "border border-dashed border-current" : ""}`}><d.Icone size={11} />{libelle}</span>;
}

function Mode({ cle }) {
  const base = "whitespace-nowrap text-[11px] font-semibold px-2 py-0.5 rounded-full";
  return <>
    {cle.test && <span className={`${base} bg-purple-500/15 text-purple-600`}>{tx("Test")}</span>}
    {cle.mode === "observation" && <span className={`${base} bg-amber-500/15 text-amber-700`}>{tx("Observation")}</span>}
  </>;
}

// Parcours d'une opération : une impulsion traverse le schéma à chaque nouvel appel
function Parcours({ nom, dernier, impulsion, dark }) {
  const d = dernier ? DECISIONS[dernier.decision] : null;
  const noeud = `relative z-10 flex flex-col items-center gap-1.5 rounded-2xl border px-3 py-3 text-center min-w-[7.5rem] ${dark ? "border-gray-600 bg-gray-800" : "border-gray-200 bg-white"}`;
  return (
    <div className={`relative rounded-2xl p-4 sm:p-6 ${dark ? "bg-gray-900/60" : "bg-gray-50"}`}>
      <style>{`
        @keyframes vbl-trajet { 0% { left: 0; opacity: 0; } 10% { opacity: 1; } 90% { opacity: 1; } 100% { left: 100%; opacity: 0; } }
        @keyframes vbl-eclat { 0% { transform: scale(.9); box-shadow: 0 0 0 0 var(--c); } 60% { transform: scale(1.04); box-shadow: 0 0 0 12px transparent; } 100% { transform: none; } }
        .vbl-trajet { animation: vbl-trajet 1.1s ease-in-out both; }
        .vbl-eclat { animation: vbl-eclat .7s ease-out 1.05s both; }
        @media (prefers-reduced-motion: reduce) { .vbl-trajet, .vbl-eclat { animation: none; } }
      `}</style>
      <div className="flex items-center justify-between gap-2">
        <div className={noeud}><Building2 size={20} className="text-foret-500" /><span className="text-xs font-semibold">{nom}</span>
          <span className={texteDiscret(dark)}>{tx("logiciel bancaire")}</span></div>
        <div className="relative h-1 flex-1 rounded-full bg-gradient-to-r from-foret-500/40 via-laiton-400/50 to-foret-500/40">
          {impulsion > 0 && <span key={impulsion} className="vbl-trajet absolute -top-1.5 h-4 w-4 -translate-x-1/2 rounded-full bg-laiton-400 shadow-[0_0_12px_#C9A13B]" />}
        </div>
        <div className={noeud}><Cpu size={20} className="text-laiton-500" /><span className="text-xs font-semibold">VoiceBank</span>
          <span className={texteDiscret(dark)}>{dernier ? tx("risque {x}", { x: tx(dernier.niveau).toLowerCase() }) : tx("analyse")}</span></div>
        <div className="relative h-1 flex-1 rounded-full bg-gradient-to-r from-laiton-400/50 to-foret-500/40">
          {impulsion > 0 && <span key={`b${impulsion}`} className="vbl-trajet absolute -top-1.5 h-4 w-4 -translate-x-1/2 rounded-full shadow-lg"
            style={{ background: d?.couleur, animationDelay: "0.55s" }} />}
        </div>
        <div key={`d${impulsion}`} className={`${noeud} vbl-eclat`} style={{ "--c": d?.couleur || "transparent", borderColor: d?.couleur }}>
          {d ? <d.Icone size={20} style={{ color: d.couleur }} /> : <ShieldCheck size={20} className="text-gray-400" />}
          <span className="text-xs font-semibold" style={{ color: d?.couleur }}>{d ? tx(d.libelle) : tx("Décision")}</span>
          <span className={texteDiscret(dark)}>{dernier ? tx("en {x} ms", { x: dernier.duree_ms }) : "—"}</span>
        </div>
      </div>
      {dernier && (
        <p className={`${texteDiscret(dark)} mt-3 text-center`}>
          {tx("Dernière opération : {ref} · {heure}", { ref: dernier.reference || tx("sans référence"), heure: new Date(dernier.date).toLocaleTimeString(LOCALE) })}
          {dernier.raisons?.[0] ? ` · ${dernier.raisons[0].detail}` : ""}
        </p>
      )}
    </div>
  );
}

function TableauLogiciel({ source, idCle, dark, onRetour }) {
  const devise = useDevise();
  const [d, setD] = useState(null);
  const [appels, setAppels] = useState([]);
  const [direct, setDirect] = useState(true);
  const [impulsion, setImpulsion] = useState(0);
  const [nouveaux, setNouveaux] = useState(new Set());
  const [erreur, setErreur] = useState(null);
  const dernierId = useRef(0);

  const charger = useCallback(async () => {
    try {
      const r = await http.get(`/sources/${source.id}/cles-api/${idCle}/activite`, { params: { apres: dernierId.current }, silencieux: true });
      const x = r.data.data;
      setD(x);
      if (x.appels.length) {
        const premier = dernierId.current === 0;
        dernierId.current = x.appels[0].id;
        setAppels(a => [...x.appels, ...a].slice(0, 100));
        if (!premier) { setImpulsion(n => n + 1); setNouveaux(new Set(x.appels.map(a => a.id))); }
      }
      setErreur(null);
    } catch (e) { setErreur(messageErreur(e)); }
  }, [source.id, idCle]);
  useEffect(() => { charger(); }, [charger]);
  useEffect(() => {
    if (!direct) return undefined;
    const t = setInterval(charger, RAFRAICHIR_MS);
    return () => clearInterval(t);
  }, [direct, charger]);

  if (!d) return <p className={texteDiscret(dark)}>{erreur || tx("Connexion au suivi en direct…")}</p>;
  const j = d.aujourdhui;
  const heures = d.par_heure.map(h => ({ ...h, h: new Date(h.heure).toLocaleTimeString(LOCALE, { hour: "2-digit" }) }));
  const tuile = (libelle, valeur, detail, couleur) => (
    <div className={`p-3 rounded-xl ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
      <p className={texteDiscret(dark)}>{libelle}</p>
      <p className="text-xl font-extrabold tabular-nums mt-0.5" style={{ color: couleur }}>{valeur}</p>
      {detail && <p className={`${texteDiscret(dark)} mt-0.5`}>{detail}</p>}
    </div>
  );
  return (
    <div className="space-y-4">
      <div className={carte(dark)}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <button onClick={onRetour} className={`${texteDiscret(dark)} inline-flex items-center gap-1 hover:underline`}><ArrowLeft size={13} />{tx("Tous les logiciels")}</button>
            <h2 className={`${titre(dark)} mt-1 flex flex-wrap items-center gap-2`}><Plug size={18} />{d.cle.nom}<Etat cle={d.cle} /><Mode cle={d.cle} /></h2>
            <p className={`${texteDiscret(dark)} mt-1`}>
              {d.cle.premiere_utilisation ? tx("Branché le {x}", { x: new Date(d.cle.premiere_utilisation).toLocaleString(LOCALE) }) : tx("Pas encore d'appel : la clé attend son premier appel.")}
              {d.cle.derniere_utilisation ? tx(" · dernier appel {x}", { x: depuis(d.cle.derniere_utilisation) }) : ""}
              {" · "}{tx("clé {x}…", { x: d.cle.prefixe })}
            </p>
          </div>
          <button onClick={() => setDirect(!direct)} className={`${boutonSecondaire(dark)} inline-flex items-center gap-1.5`} aria-pressed={direct}>
            {direct ? <><Radio size={13} className="text-red-500 animate-pulse" />{tx("En direct")}<Pause size={12} /></> : <><Play size={12} />{tx("Reprendre le direct")}</>}
          </button>
        </div>
        {d.cle.mode === "observation" && (
          <p role="note" className={`mt-4 text-xs rounded-lg px-3 py-2 ${dark ? "bg-amber-900/30 text-amber-200" : "bg-amber-50 text-amber-800"}`}>
            {tx("Mode observation : le logiciel reçoit toujours « accepter », rien n'est bloqué. Les chiffres ci-dessous montrent ce que VoiceBank aurait fait : comparez-les avec vos propres contrôles, puis activez le blocage dans la carte des clés.")}
          </p>)}
        {d.cle.test && (
          <p role="note" className={`mt-4 text-xs rounded-lg px-3 py-2 ${dark ? "bg-purple-900/30 text-purple-200" : "bg-purple-50 text-purple-800"}`}>
            {tx("Clé de test : les réponses sont réelles, mais aucune alerte n'est créée pour l'équipe.")}
          </p>)}
        <div className="mt-4"><Parcours nom={d.cle.nom} dernier={appels[0]} impulsion={impulsion} dark={dark} /></div>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mt-4">
          {tuile(tx("Appels aujourd'hui"), j.appels.toLocaleString(LOCALE), tx("{x} alerte(s) créée(s)", { x: j.alertes }))}
          {tuile(tx("Acceptées"), j.acceptees.toLocaleString(LOCALE), null, DECISIONS.accepter.couleur)}
          {tuile(d.cle.mode === "observation" ? tx("Aurait fait vérifier") : tx("À vérifier"), j.a_verifier.toLocaleString(LOCALE), devise.formaterValeur(j.montant_a_verifier, { compact: true }), DECISIONS.verifier.couleur)}
          {tuile(d.cle.mode === "observation" ? tx("Aurait bloqué") : tx("Bloquées"), j.bloquees.toLocaleString(LOCALE), devise.formaterValeur(j.montant_bloque, { compact: true }), DECISIONS.bloquer.couleur)}
          {tuile(tx("Temps de réponse"), j.duree_moyenne_ms != null ? tx("{x} ms", { x: Math.round(j.duree_moyenne_ms) }) : "--",
            j.duree_p95_ms != null ? tx("95 % en moins de {x} ms", { x: Math.round(j.duree_p95_ms) }) : null)}
        </div>
      </div>

      <div className={carte(dark)}>
        <h3 className={titre(dark)}>{tx("Décisions des 24 dernières heures")}</h3>
        <div className="h-48 mt-3">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={heures}>
              <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#E5E7EB"} vertical={false} />
              <XAxis dataKey="h" tick={{ fontSize: 10, fill: dark ? "#9CA3AF" : "#6B7280" }} interval={2} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: dark ? "#9CA3AF" : "#6B7280" }} width={32} />
              <Tooltip />
              {Object.entries(DECISIONS).map(([k, v]) => <Bar key={k} dataKey={k} name={tx(v.libelle)} stackId="a" fill={v.couleur} isAnimationActive={false} />)}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className={carte(dark)}>
        <h3 className={`${titre(dark)} flex items-center gap-2`}>{tx("Fil des opérations")}{direct && <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />}</h3>
        {appels.length === 0 ? (
          <p className={`${texteDiscret(dark)} mt-2`}>{tx("Aucun appel pour l'instant. Dès que le logiciel bancaire enverra une opération, elle apparaîtra ici en quelques secondes.")}</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className={`text-left ${texteDiscret(dark)}`}>
                <th className="py-2 pr-3 font-medium">{tx("Heure")}</th><th className="py-2 pr-3 font-medium">{tx("Référence")}</th>
                <th className="py-2 pr-3 font-medium text-right">{tx("Montant")}</th><th className="py-2 pr-3 font-medium">{tx("Décision")}</th>
                <th className="py-2 pr-3 font-medium">{tx("Raison principale")}</th><th className="py-2 font-medium text-right">{tx("Réponse")}</th>
              </tr></thead>
              <tbody>
                {appels.map(a => (
                  <tr key={a.id} className={`border-t transition-colors duration-[2000ms] ${dark ? "border-gray-700" : "border-gray-100"} ${nouveaux.has(a.id) ? "bg-laiton-400/15" : ""}`}>
                    <td className="py-2 pr-3 whitespace-nowrap tabular-nums">{new Date(a.date).toLocaleTimeString(LOCALE)}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{a.reference || "—"}</td>
                    <td className="py-2 pr-3 text-right tabular-nums whitespace-nowrap">{a.montant != null ? `${a.montant.toLocaleString(LOCALE)} ${["XAF", "XOF"].includes(a.devise) ? "FCFA" : a.devise || ""}` : "—"}</td>
                    <td className="py-2 pr-3"><Chip decision={a.decision} mode={a.mode} /></td>
                    <td className={`py-2 pr-3 ${texteDiscret(dark)}`}>{a.raisons?.[0]?.detail || tx("habituelle")}</td>
                    <td className={`py-2 text-right tabular-nums ${texteDiscret(dark)}`}>{tx("{x} ms", { x: a.duree_ms ?? "?" })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export function PanelLogiciels({ source, dark, onMesDonnees }) {
  const src = source || { id: 0 };
  const [liste, setListe] = useState(null);
  const [choisi, setChoisi] = useState(null);
  const charger = useCallback(() => {
    http.get(`/sources/${src.id}/logiciels`, { silencieux: true }).then(r => setListe(r.data.data)).catch(() => setListe([]));
  }, [src.id]);
  useEffect(() => {
    charger();
    const t = setInterval(charger, 15000);
    return () => clearInterval(t);
  }, [charger]);

  if (choisi) return <TableauLogiciel source={src} idCle={choisi} dark={dark} onRetour={() => { setChoisi(null); charger(); }} />;
  return (
    <div className="space-y-4">
      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} flex items-center gap-2`}><Plug size={18} />{" "}{tx("Logiciels branchés")}</h2>
        <p className={`${texteDiscret(dark)} mt-1`}>{tx("Chaque clé d'API correspond à un logiciel. Choisissez-en un pour suivre en direct les opérations qu'il fait vérifier.")}</p>
        {liste === null ? <p className={`${texteDiscret(dark)} mt-3`}>{tx("Chargement…")}</p> : liste.length === 0 ? (
          <p className={`${texteDiscret(dark)} mt-3`}>{tx("Aucun logiciel branché pour l'instant : créez une clé ci-dessous et donnez-la au logiciel bancaire.")}</p>
        ) : (
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3 mt-4">
            {liste.map(c => (
              <button key={c.id} onClick={() => setChoisi(c.id)} disabled={!c.premiere_utilisation && c.revoquee}
                className={`text-left rounded-2xl border p-4 transition hover:-translate-y-0.5 hover:shadow-md ${dark ? "border-gray-700 bg-gray-800/60 hover:border-laiton-400/50" : "border-gray-200 bg-white hover:border-laiton-400"} ${c.en_ligne ? "ring-1 ring-emerald-500/40" : ""}`}>
                <div className="flex items-start justify-between gap-2">
                  <span className="flex items-center gap-2 font-semibold"><Building2 size={16} className="text-foret-500" />{c.nom}</span>
                  <span className="flex flex-wrap justify-end gap-1"><Mode cle={c} /><Etat cle={c} /></span>
                </div>
                <p className={`${texteDiscret(dark)} mt-2`}>{tx("{x} appel(s)", { x: c.nb_appels.toLocaleString(LOCALE) })}
                  {c.derniere_utilisation ? tx(" · dernier {x}", { x: depuis(c.derniere_utilisation) }) : ""}</p>
                <p className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-foret-600"><Timer size={12} />{tx("Voir en direct")}</p>
              </button>
            ))}
          </div>
        )}
      </div>
      <ClesApi source={src} dark={dark} onMesDonnees={onMesDonnees} onChange={charger} />
    </div>
  );
}

