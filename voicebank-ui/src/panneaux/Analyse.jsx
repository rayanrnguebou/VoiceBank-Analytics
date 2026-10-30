// Tableau de bord (indicateurs) et barre de choix de la base analysée.
import { useState, useEffect } from "react";
import { Choix } from "../ChampListe";
import ChampsEtablissement, { PAYS_MODELE } from "./ChampsEtablissement";
import ResultatRisque from "./Explication";
import { useDevise } from "../devise";
import { useAPI } from "../useAPI";
import { SelecteurSource } from "./TableauSource";
import { LOCALE, tx } from "../i18n";

export function KpiCard({ titre, valeur, icone: Icone, couleur, dark }) {
  return (
    <div className={`rounded-2xl p-4 border ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
      <div className="flex items-center justify-between mb-2">
        <span className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>{titre}</span>
        <div className="p-1.5 rounded-lg" style={{ backgroundColor: couleur + "20" }}>
          <Icone size={15} style={{ color: couleur }} />
        </div>
      </div>
      <p className={`text-xl font-bold ${dark ? "text-white" : "text-gray-900"}`}>{valeur}</p>
    </div>
  );
}

// ════════════════════════════════════════
// COMPOSANT — ANALYSE D'UNE TRANSACTION (modèle IA de fraude)
// ════════════════════════════════════════

export function PanelAnalyse({ dark }) {
  const devise = useDevise();
  const { appeler, chargement, erreur } = useAPI();
  const [ref, setRef]       = useState(null);
  const [form, setForm]     = useState({ montant_fcfa: 250000, est_internationale: "Non", heure: "14:00" });
  const [resultat, setResultat] = useState(null);
  const [infos, setInfos]   = useState(null);

  useEffect(() => {
    appeler("get", "/ia/modeles").then(res => res && setInfos(res.fraude));
    appeler("get", "/ia/referentiel").then(res => {
      if (!res?.data) return;
      setRef(res.data);
      setForm(f => ({
        ...f,
        type_transaction: res.data.type_transaction?.[0], canal: res.data.canal?.[0],
        banque: res.data.banque?.[0], ville: res.data.ville?.[0],
      }));
    });
  }, [appeler]);

  const analyser = async (e) => {
    e.preventDefault();
    setResultat(null);
    const { pays, ...operation } = form;     // le pays sert à proposer banques et villes ; « Internationale » le traduit pour le modèle
    const res = await appeler("post", "/ia/analyser-transaction", {
      ...operation, montant_fcfa: Number(form.montant_fcfa), heure: form.heure || null,
    });
    if (res) setResultat(res);
  };

  const champ = `w-full px-3 py-2 rounded-xl border text-sm outline-none ${
    dark ? "bg-gray-700 border-gray-600 text-white focus:border-foret-500" : "bg-gray-50 border-gray-200 text-gray-900 focus:border-foret-500"}`;
  const etiquette = `block text-xs mb-1 ${dark ? "text-gray-400" : "text-gray-500"}`;
  const listes = [["type_transaction", tx("Type")], ["canal", tx("Canal")]];

  return (
    <div className={`rounded-2xl border p-6 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
      <h2 className={`text-lg font-bold mb-1 ${dark ? "text-white" : "text-gray-900"}`}>{tx("Analyser une transaction")}</h2>
      <p className={`text-xs mb-1 ${dark ? "text-gray-400" : "text-gray-500"}`}>
        {tx("Le modèle d'IA compare l'opération aux habitudes observées (montant, heure, canal, lieu…), explique son score et indique la conduite à tenir.")}
      </p>
      {infos && (
        <p className={`text-xs mb-4 ${infos.remarque ? "text-amber-500" : dark ? "text-gray-500" : "text-gray-400"}`}>
          {infos.remarque || (infos.date_entrainement
            ? tx("Modèle entraîné le {date} sur {n} transactions", { date: new Date(infos.date_entrainement).toLocaleDateString(LOCALE), n: Number(infos.nb_transactions).toLocaleString(LOCALE) })
              + (infos.fiabilite ? tx(" · fiabilité {fiabilite} (AUC {auc})", { fiabilite: tx(infos.fiabilite), auc: Number(infos.auc_xgboost).toLocaleString(LOCALE) }) : "") + "."
            : "")}
        </p>
      )}
      {!ref ? (
        <p className={`text-sm ${dark ? "text-gray-400" : "text-gray-500"}`}>{erreur || tx("Chargement du modèle…")}</p>
      ) : (
        <form onSubmit={analyser} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label>
            <span className={etiquette}>{tx("Montant ({libelle})", { libelle: devise.libelle })}</span>
            <input type="number" min="0" step="any" required
              value={form.montant_fcfa === "" ? "" : Math.round(devise.convertir(form.montant_fcfa) * 100) / 100}
              onChange={e => setForm({ ...form, montant_fcfa: e.target.value === "" ? "" : devise.versFcfa(e.target.value) })} className={champ} />
          </label>
          {listes.map(([cle, nom]) => (
            <label key={cle}>
              <span className={etiquette}>{nom}</span>
              <Choix dark={dark} required valeur={form[cle] || ""} onChange={v => setForm(f => ({ ...f, [cle]: v }))} options={ref[cle] || []} />
            </label>
          ))}
          <ChampsEtablissement dark={dark} valeurs={form} connues={{ banque: ref.banque, ville: ref.ville }}
            maj={m => setForm(f => ({ ...f, ...m, ...(m.pays ? { est_internationale: m.pays === PAYS_MODELE ? "Non" : "Oui" } : {}) }))} />
          <label>
            <span className={etiquette}>{tx("Internationale")}</span>
            <select value={form.est_internationale} onChange={e => setForm({ ...form, est_internationale: e.target.value })} className={champ}>
              <option value="Non">{tx("Non")}</option><option value="Oui">{tx("Oui")}</option>
            </select>
          </label>
          <label>
            <span className={etiquette}>{tx("Heure de l'opération")}</span>
            <input type="time" value={form.heure} onChange={e => setForm({ ...form, heure: e.target.value })} className={champ} />
          </label>
          <div className="sm:col-span-2 flex items-center gap-3">
            <button type="submit" disabled={chargement}
              className="px-4 py-2 bg-foret-600 hover:bg-foret-700 text-white text-sm font-semibold rounded-xl disabled:opacity-50">
              {chargement ? tx("Analyse…") : tx("Analyser")}
            </button>
            {erreur && <span className="text-sm text-red-500">{erreur}</span>}
          </div>
        </form>
      )}
      <ResultatRisque resultat={resultat} dark={dark} type="fraude" />
    </div>
  );
}

// Pages de risque : base analysée (celle de l'organisation, ou la démonstration fictive)
export function BarreSourceRisque({ dark, sourceActive, sourcesPretes, externe, onChoisir, onMesDonnees }) {
  if (sourcesPretes.length > 0 || sourceActive) {
    return (
      <div className={`mb-4 flex flex-wrap items-center gap-3 p-3 rounded-xl border ${dark ? "border-gray-700 bg-gray-800/60" : "border-gray-200 bg-white"}`}>
        <SelecteurSource dark={dark} sourceActive={sourceActive} sourcesPretes={sourcesPretes} onChoisir={onChoisir} />
        <span className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
          {sourceActive ? tx("Modèles appris sur cette base.") : tx("Démonstration : banque fictive, modèles pré-entraînés.")}
        </span>
      </div>
    );
  }
  if (!externe) return null;
  return (
    <div className={`mb-4 flex flex-wrap items-center gap-3 p-3 rounded-xl border text-sm ${dark ? "border-laiton-400/30 bg-laiton-400/5 text-gray-300" : "border-amber-200 bg-amber-50 text-gray-700"}`}>
      <span>{tx("Démonstration sur une banque fictive. Branche ta base ou tes fichiers pour analyser tes propres opérations et crédits.")}</span>
      <button onClick={onMesDonnees} className="ml-auto px-3 py-1.5 rounded-lg bg-foret-600 hover:bg-foret-700 text-white text-xs font-semibold">{tx("Mes données")}</button>
    </div>
  );
}

// ════════════════════════════════════════
// ÉCRAN DE CONNEXION
// ════════════════════════════════════════

// ════════════════════════════════════════
// APP PRINCIPALE
// ════════════════════════════════════════
