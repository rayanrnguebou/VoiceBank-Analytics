// Résultat d'un modèle de risque (fraude ou crédit) : niveau, ce qui l'explique, et que faire.
import { CircleAlert, CircleCheck, ArrowUpRight, ArrowDownRight, ListChecks } from "lucide-react";
import { COULEURS_NIVEAU, texteDiscret } from "../ui";
import { tx } from "../i18n";

export default function ResultatRisque({ resultat, dark, type = "credit" }) {
  if (!resultat) return null;
  const facteurs = resultat.facteurs || [];
  const max = Math.max(...facteurs.map(f => Math.abs(f.impact)), 0.01);
  const pct = type === "fraude" ? resultat.score_anomalie : resultat.probabilite_defaut;
  const couleur = COULEURS_NIVEAU[resultat.niveau_risque] || "bg-gray-500";
  const texte = dark ? "text-gray-200" : "text-gray-800";
  return (
    <div className={`mt-4 rounded-xl overflow-hidden border ${dark ? "border-gray-600 bg-gray-700/60" : "border-gray-200 bg-gray-50"}`}>
      <div className="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className={`text-xs font-semibold text-white px-2.5 py-1 rounded-full ${couleur}`}>{tx("Risque {niveau_risque}", { niveau_risque: tx(resultat.niveau_risque) })}</span>
          <span className={`text-sm font-bold ${dark ? "text-white" : "text-gray-900"}`}>
            {type === "fraude" ? tx("Score de fraude") : tx("Probabilité de défaut")} : {(pct * 100).toFixed(1).replace(".", ",")} %
          </span>
          {type === "credit" && <span className={texteDiscret(dark)}>{tx("Score IA {score_ia}/850", { score_ia: resultat.score_ia })}</span>}
        </div>
        <div className={`h-2 rounded-full overflow-hidden mt-3 ${dark ? "bg-gray-600" : "bg-gray-200"}`}>
          <div className={`h-full ${couleur}`} style={{ width: `${Math.min(100, pct * 100)}%` }} />
        </div>
      </div>

      {facteurs.length > 0 && (
        <div className={`px-4 pb-4`}>
          <p className={`text-xs font-semibold uppercase tracking-wide mb-2 ${dark ? "text-gray-400" : "text-gray-500"}`}>{tx("Ce qui explique ce résultat")}</p>
          <ul className="space-y-2">
            {facteurs.map(f => (
              <li key={f.variable} className="grid grid-cols-[1fr_auto] sm:grid-cols-[minmax(0,14rem)_1fr_auto] items-center gap-x-3 gap-y-1">
                <span className={`text-sm ${texte} min-w-0`}>
                  {f.variable}{(f.detail || f.valeur) ? <span className={`${texteDiscret(dark)} ml-1`}>· {f.detail || f.valeur}</span> : null}
                </span>
                <div className={`hidden sm:block h-2 rounded-full overflow-hidden ${dark ? "bg-gray-600" : "bg-gray-200"}`}>
                  <div className={`h-full ${f.impact > 0 ? "bg-red-500" : "bg-emerald-500"}`} style={{ width: `${(Math.abs(f.impact) / max) * 100}%` }} />
                </div>
                <span className={`text-xs flex items-center gap-0.5 justify-end whitespace-nowrap ${f.impact > 0 ? "text-red-500" : "text-emerald-500"}`}>
                  {f.impact > 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{f.effet}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {resultat.recommandations?.length > 0 && (
        <div className={`px-4 py-3 border-t ${dark ? "border-gray-600 bg-gray-800/60" : "border-gray-200 bg-white"}`}>
          <p className={`text-xs font-semibold uppercase tracking-wide mb-2 flex items-center gap-1.5 ${dark ? "text-laiton-300" : "text-foret-700"}`}>
            <ListChecks size={14} />{" "}{tx("Que faire ?")}
          </p>
          <ul className="space-y-1.5">
            {resultat.recommandations.map((r, i) => (
              <li key={i} className={`text-sm flex gap-2 ${texte}`}>
                {i === 0 && resultat.niveau_risque !== "Faible"
                  ? <CircleAlert size={15} className="text-amber-500 flex-shrink-0 mt-0.5" />
                  : <CircleCheck size={15} className="text-emerald-500 flex-shrink-0 mt-0.5" />}
                <span className={i === 0 ? "font-medium" : ""}>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {resultat.avertissement && <p className="text-xs text-amber-500 px-4 pb-3">{resultat.avertissement}</p>}
    </div>
  );
}
