// Score de crédit expliqué : évaluer une demande, ou repérer les crédits en cours les plus risqués
import { useState, useEffect } from "react";
import { useAPI } from "../useAPI";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, COULEURS_NIVEAU, formaterFcfa } from "../ui";

export function Explication({ resultat, dark }) {
  if (!resultat) return null;
  const max = Math.max(...resultat.facteurs.map(f => Math.abs(f.impact)), 0.01);
  return (
    <div className={`mt-4 p-4 rounded-xl ${dark ? "bg-gray-700" : "bg-gray-50"}`}>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <span className={`text-xs font-semibold text-white px-2.5 py-1 rounded-full ${COULEURS_NIVEAU[resultat.niveau_risque] || "bg-gray-500"}`}>
          Risque {resultat.niveau_risque}
        </span>
        <span className={`text-sm font-bold ${dark ? "text-white" : "text-gray-900"}`}>
          Probabilité de défaut : {(resultat.probabilite_defaut * 100).toFixed(1)} %
        </span>
        <span className={texteDiscret(dark)}>Score IA {resultat.score_ia}/850</span>
      </div>
      <p className={`${texteDiscret(dark)} mb-2`}>Ce qui explique ce score :</p>
      <div className="space-y-1.5">
        {resultat.facteurs.map(f => (
          <div key={f.variable} className="flex items-center gap-2">
            <span className={`text-xs w-48 flex-shrink-0 truncate ${dark ? "text-gray-300" : "text-gray-700"}`}>{f.variable}</span>
            <div className={`flex-1 h-2 rounded-full overflow-hidden ${dark ? "bg-gray-600" : "bg-gray-200"}`}>
              <div className={`h-full ${f.impact > 0 ? "bg-red-500" : "bg-emerald-500"}`}
                style={{ width: `${(Math.abs(f.impact) / max) * 100}%` }} />
            </div>
            <span className={`text-xs w-32 text-right ${f.impact > 0 ? "text-red-500" : "text-emerald-500"}`}>{f.effet}</span>
          </div>
        ))}
      </div>
      {resultat.avertissement && <p className="text-xs text-amber-500 mt-2">{resultat.avertissement}</p>}
    </div>
  );
}

const DEMANDE_INITIALE = {
  montant_fcfa: 10000000, mensualite_fcfa: 350000, revenu_annuel_fcfa: 9000000, score_credit: 650,
  taux_interet_pct: 12, duree_mois: 36, est_diaspora: "Non",
};

export default function PanelCredit({ dark }) {
  const api = useAPI();
  const liste = useAPI();
  const detail = useAPI();
  const [ref, setRef] = useState(null);
  const [form, setForm] = useState(DEMANDE_INITIALE);
  const [resultat, setResultat] = useState(null);
  const [risques, setRisques] = useState(null);
  const [selection, setSelection] = useState(null);

  useEffect(() => {
    api.appeler("get", "/ia/credit/referentiel").then(res => {
      if (!res?.data) return;
      setRef(res.data);
      setForm(f => ({ ...f, type_credit: res.data.type_credit?.[0], garantie: res.data.garantie?.[0], banque: res.data.banque?.[0] }));
    });
    liste.appeler("get", "/ia/credits-a-risque?limit=10").then(res => res && setRisques(res));
  }, [api.appeler, liste.appeler]); // eslint-disable-line react-hooks/exhaustive-deps

  const evaluer = async (e) => {
    e.preventDefault();
    setResultat(null);
    const nums = ["montant_fcfa", "mensualite_fcfa", "revenu_annuel_fcfa", "score_credit", "taux_interet_pct", "duree_mois"];
    const corps = { ...form };
    nums.forEach(k => { corps[k] = Number(corps[k]); });
    const res = await api.appeler("post", "/ia/score-credit", corps);
    if (res) setResultat(res);
  };

  const ouvrir = async (id) => {
    setSelection({ id, resultat: null });
    const res = await detail.appeler("get", `/ia/score-credit/${encodeURIComponent(id)}`);
    if (res) setSelection({ id, resultat: res });
  };

  const nombres = [
    ["montant_fcfa", "Montant (FCFA)"], ["mensualite_fcfa", "Mensualité (FCFA)"], ["revenu_annuel_fcfa", "Revenu annuel (FCFA)"],
    ["score_credit", "Score historique (300-850)"], ["taux_interet_pct", "Taux d'intérêt (%)"], ["duree_mois", "Durée (mois)"],
  ];

  return (
    <div className="space-y-4">
      <div className={carte(dark)}>
        <h2 className={titre(dark)}>Évaluer une demande de crédit</h2>
        <p className={`${texteDiscret(dark)} mb-4`}>Probabilité de défaut estimée par XGBoost, avec les facteurs qui l'expliquent (contributions SHAP).</p>
        {!ref ? <p className={texteDiscret(dark)}>{api.erreur || "Chargement du modèle…"}</p> : (
          <form onSubmit={evaluer} className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {nombres.map(([cle, nom]) => (
              <label key={cle}>
                <span className={etiquette(dark)}>{nom}</span>
                <input type="number" step="any" min="0" required value={form[cle]}
                  onChange={e => setForm({ ...form, [cle]: e.target.value })} className={champ(dark)} />
              </label>
            ))}
            {[["type_credit", "Type de crédit"], ["garantie", "Garantie"], ["banque", "Banque"]].map(([cle, nom]) => (
              <label key={cle}>
                <span className={etiquette(dark)}>{nom}</span>
                <select value={form[cle] || ""} onChange={e => setForm({ ...form, [cle]: e.target.value })} className={champ(dark)}>
                  {(ref[cle] || []).map(v => <option key={v}>{v}</option>)}
                </select>
              </label>
            ))}
            <label>
              <span className={etiquette(dark)}>Client de la diaspora</span>
              <select value={form.est_diaspora} onChange={e => setForm({ ...form, est_diaspora: e.target.value })} className={champ(dark)}>
                <option>Non</option><option>Oui</option>
              </select>
            </label>
            <div className="sm:col-span-3 flex items-center gap-3">
              <button type="submit" disabled={api.chargement} className={boutonPrincipal}>{api.chargement ? "Calcul…" : "Évaluer"}</button>
              {api.erreur && <span className="text-sm text-red-500">{api.erreur}</span>}
            </div>
          </form>
        )}
        <Explication resultat={resultat} dark={dark} />
      </div>

      <div className={carte(dark)}>
        <h2 className={titre(dark)}>Crédits en cours les plus à risque</h2>
        <p className={`${texteDiscret(dark)} mb-4`}>
          {risques ? `Anticipation des défauts sur ${risques.analyses.toLocaleString("fr-FR")} crédits en cours. ` : ""}Clique sur un crédit pour voir l'explication.
        </p>
        {liste.erreur && <p className="text-sm text-red-500">{liste.erreur}</p>}
        <div className="space-y-2">
          {(risques?.data || []).map(c => (
            <div key={c.id_credit}>
              <button onClick={() => ouvrir(c.id_credit)}
                className={`w-full flex items-center justify-between gap-3 p-3 rounded-xl text-left ${dark ? "bg-gray-700 hover:bg-gray-600" : "bg-gray-50 hover:bg-gray-100"}`}>
                <div className="min-w-0">
                  <p className={`text-sm font-medium ${dark ? "text-white" : "text-gray-900"}`}>{c.id_credit} · {c.type_credit}</p>
                  <p className={texteDiscret(dark)}>{c.banque} · {formaterFcfa(c.montant_fcfa)} FCFA · {c.duree_mois} mois</p>
                </div>
                <span className={`text-xs font-semibold text-white px-2.5 py-1 rounded-full flex-shrink-0 ${COULEURS_NIVEAU[c.niveau_risque] || "bg-gray-500"}`}>
                  {(c.probabilite_defaut * 100).toFixed(0)} %
                </span>
              </button>
              {selection?.id === c.id_credit && (selection.resultat
                ? <Explication resultat={selection.resultat} dark={dark} />
                : <p className={`${texteDiscret(dark)} p-2`}>{detail.erreur || "Calcul…"}</p>)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
