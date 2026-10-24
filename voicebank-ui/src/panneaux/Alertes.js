// Alertes de fraude : consultation et traitement (décision + commentaire, tracés dans l'audit)
import { useState, useEffect, useCallback } from "react";
import { ShieldAlert, CircleCheck, CircleX } from "lucide-react";
import { useAPI } from "../useAPI";
import { carte, champ, titre, texteDiscret, boutonSecondaire, formaterFcfa, formaterDate } from "../ui";

const NIVEAUX = ["Tous", "Critique", "Élevé", "Moyen"];
const COULEUR_NIVEAU = {
  Critique: "text-red-600 bg-red-100", "Élevé": "text-orange-600 bg-orange-100",
  Moyen: "text-yellow-700 bg-yellow-100", Faible: "text-green-700 bg-green-100",
};

function LigneAlerte({ a, dark, onTraitee }) {
  const { appeler, chargement, erreur } = useAPI();
  const [ouvert, setOuvert] = useState(false);
  const [commentaire, setCommentaire] = useState("");

  const decider = async (decision) => {
    const res = await appeler("post", `/alertes/${a.id_alerte}/traiter`, { decision, commentaire: commentaire || null });
    if (res) onTraitee();
  };

  return (
    <div className={`p-3 rounded-xl ${dark ? "bg-gray-700" : "bg-gray-50"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${COULEUR_NIVEAU[a.niveau_alerte] || "bg-gray-100 text-gray-600"}`}>{a.niveau_alerte}</span>
            <span className={texteDiscret(dark)}>Score {(a.score_anomalie * 100).toFixed(0)} %</span>
            <span className={texteDiscret(dark)}>{a.id_transaction}</span>
          </div>
          <p className={`text-xs truncate ${dark ? "text-gray-300" : "text-gray-600"}`}>{a.motif || "Comportement inhabituel"}</p>
          <p className={texteDiscret(dark)}>{[a.banque, a.ville, a.type_transaction].filter(Boolean).join(" · ")}</p>
        </div>
        <div className="text-right">
          <p className={`text-sm font-bold ${dark ? "text-white" : "text-gray-900"}`}>{a.montant_fcfa ? formaterFcfa(a.montant_fcfa) : "--"}</p>
          <p className={texteDiscret(dark)}>FCFA</p>
        </div>
      </div>

      {a.traitee ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${a.decision === "Fraude confirmée" ? "bg-red-500 text-white" : "bg-emerald-500 text-white"}`}>
            {a.decision === "Fraude confirmée" ? <CircleX size={12} /> : <CircleCheck size={12} />}
            {a.decision || "Traitée"}
          </span>
          <span className={texteDiscret(dark)}>par {a.traitee_par || "?"} · {formaterDate(a.date_traitement)}</span>
          {a.commentaire && <span className={`text-xs italic ${dark ? "text-gray-300" : "text-gray-600"}`}>« {a.commentaire} »</span>}
        </div>
      ) : !ouvert ? (
        <button onClick={() => setOuvert(true)} className={`mt-2 ${boutonSecondaire(dark)}`}>Traiter</button>
      ) : (
        <div className="mt-2 space-y-2">
          <input value={commentaire} onChange={e => setCommentaire(e.target.value)} maxLength={1000}
            placeholder="Commentaire (facultatif) : client joint, carte bloquée…" className={champ(dark)} />
          <div className="flex flex-wrap gap-2">
            <button disabled={chargement} onClick={() => decider("Fraude confirmée")}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500 hover:bg-red-600 text-white disabled:opacity-50">Fraude confirmée</button>
            <button disabled={chargement} onClick={() => decider("Faux positif")}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-50">Faux positif</button>
            <button onClick={() => setOuvert(false)} className={boutonSecondaire(dark)}>Annuler</button>
          </div>
          {erreur && <p className="text-xs text-red-500">{erreur}</p>}
        </div>
      )}
    </div>
  );
}

export default function PanelAlertes({ dark, onChange }) {
  const { appeler } = useAPI();
  const [alertes, setAlertes] = useState([]);
  const [niveau, setNiveau]   = useState("Critique");
  const [traitees, setTraitees] = useState(false);
  const [stats, setStats]     = useState(null);

  const charger = useCallback(() => {
    const params = new URLSearchParams({ limit: "20", traitee: String(traitees) });
    if (niveau !== "Tous") params.set("niveau", niveau);
    appeler("get", `/alertes/fraude?${params}`).then(res => setAlertes(res ? res.data : []));
    appeler("get", "/alertes/stats").then(res => res && setStats(res));
  }, [appeler, niveau, traitees]);

  useEffect(() => { charger(); }, [charger]);

  const pastille = actif => `text-xs px-2.5 py-1 rounded-full transition-all ${actif
    ? "bg-foret-600 text-white" : dark ? "bg-gray-700 text-gray-300" : "bg-gray-100 text-gray-600"}`;

  return (
    <div className={carte(dark)}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
        <h2 className={`${titre(dark)} flex items-center gap-2`}><ShieldAlert size={19} strokeWidth={1.75} className="text-red-500" /> Alertes fraude</h2>
        <div className="flex gap-1">
          <button className={pastille(!traitees)} onClick={() => setTraitees(false)}>À traiter</button>
          <button className={pastille(traitees)} onClick={() => setTraitees(true)}>Traitées</button>
        </div>
      </div>
      {stats && (
        <p className={`${texteDiscret(dark)} mb-3`}>
          {Number(stats.a_traiter).toLocaleString("fr-FR")} à traiter · {Number(stats.confirmees).toLocaleString("fr-FR")} fraudes confirmées · {Number(stats.faux_positifs).toLocaleString("fr-FR")} faux positifs
        </p>
      )}
      <div className="flex flex-wrap gap-1 mb-4">
        {NIVEAUX.map(n => <button key={n} className={pastille(niveau === n)} onClick={() => setNiveau(n)}>{n}</button>)}
      </div>
      <div className="space-y-2">
        {alertes.length === 0
          ? <p className={`text-sm text-center py-4 ${dark ? "text-gray-500" : "text-gray-400"}`}>Aucune alerte {traitees ? "traitée" : "à traiter"}{niveau !== "Tous" ? ` (${niveau})` : ""}</p>
          : alertes.map(a => <LigneAlerte key={a.id_alerte} a={a} dark={dark} onTraitee={() => { charger(); onChange && onChange(); }} />)}
      </div>
    </div>
  );
}
