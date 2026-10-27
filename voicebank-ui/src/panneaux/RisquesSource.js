// Fraude et crédit calculés sur la base connectée de l'organisation (modèles appris sur ses propres données).
import { useState, useEffect, Fragment } from "react";
import { ShieldAlert, ScanSearch, Landmark, Info, Download, ChevronDown, ChevronUp } from "lucide-react";
import { useAPI } from "../useAPI";
import { useDevise } from "../devise";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, COULEURS_NIVEAU } from "../ui";
import ResultatRisque from "./Explication";
import { telechargerCsv, nomFichier } from "../ui";

const pct = v => `${(Number(v) * 100).toFixed(1).replace(".", ",")} %`;

function Pastille({ niveau, children }) {
  return <span className={`text-[11px] font-semibold text-white px-2 py-0.5 rounded-full whitespace-nowrap ${COULEURS_NIVEAU[niveau] || "bg-gray-500"}`}>{children || niveau}</span>;
}

function Indisponible({ dark, message }) {
  return (
    <div className={`${carte(dark)} flex gap-3`}>
      <Info size={18} className="text-laiton-400 flex-shrink-0 mt-0.5" />
      <div>
        <p className={`text-sm ${dark ? "text-gray-200" : "text-gray-800"}`}>{message}</p>
        <p className={`${texteDiscret(dark)} mt-1`}>Choisis une autre base dans « Données interrogées », ou la démonstration.</p>
      </div>
    </div>
  );
}

// ── Opérations atypiques (page « Alertes de fraude ») ────────────────
export function PanelOperationsSource({ source, dark }) {
  const devise = useDevise();
  const { appeler, chargement, erreur } = useAPI();
  const [d, setD] = useState(null);
  const [ouvert, setOuvert] = useState(null);
  const [filtre, setFiltre] = useState("Tous");
  const [nbVisibles, setNbVisibles] = useState(15);
  useEffect(() => {
    setD(null);
    appeler("get", `/sources/${source.id}/risques/operations`, null, { params: { devise: devise.code }, timeout: 90000 }).then(r => r && setD(r.data));
  }, [appeler, source.id, devise.code]);

  if (erreur) return <Indisponible dark={dark} message={erreur} />;
  if (!d || chargement) return <p className={texteDiscret(dark)}>Apprentissage des habitudes de « {source.nom} »… (quelques secondes la première fois)</p>;
  const r = d.resume;
  const toutes = d.operations.filter(o => filtre === "Tous" || o.niveau_risque === filtre);
  const ops = toutes.slice(0, nbVisibles);
  const compte = n => d.operations.filter(o => n === "Tous" || o.niveau_risque === n).length;
  const exporter = () => telechargerCsv(nomFichier(`operations atypiques ${source.nom}`, "csv"),
    ["id", "date", "montant", "niveau", "score", "raisons", ...r.categories],
    d.operations.map(o => ({ id: o.id, date: o.date, montant: o.montant, niveau: o.niveau_risque, score: o.score,
      raisons: o.raisons.map(x => `${x.variable} : ${x.detail || x.valeur}`).join(" | "), ...o.categories })));
  return (
    <div className="space-y-4">
      <div className={carte(dark)}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className={`${titre(dark)} flex items-center gap-2`}><ShieldAlert size={19} className="text-red-500" /> Opérations atypiques</h2>
            <p className={`${texteDiscret(dark)} mt-1`}>
              Modèle appris sur {r.analysees.toLocaleString("fr-FR")} opérations récentes de « {r.titre} »
              {r.periode ? ` (du ${new Date(r.periode[0]).toLocaleDateString("fr-FR")} au ${new Date(r.periode[1]).toLocaleDateString("fr-FR")})` : ""} :
              montant, {r.categories.join(", ")}{r.heure_prise_en_compte ? ", heure" : ""}.
            </p>
          </div>
          <button onClick={exporter} className={`${boutonSecondaire(dark)} flex items-center gap-1.5`}><Download size={13} /> CSV</button>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
          {[["Opérations analysées", r.analysees.toLocaleString("fr-FR")], ["Très atypiques (2 %)", r.atypiques.toLocaleString("fr-FR")],
            ...(r.fraudes_connues ? [["Fraudes connues dans la base", r.fraudes_connues.toLocaleString("fr-FR")],
              ["Repérées par le modèle", `${String(r.fraudes_reperees_pct).replace(".", ",")} % (hasard : ${r.fraudes_hasard_pct} %)`]] : [])
          ].map(([t, v]) => (
            <div key={t} className={`p-3 rounded-xl ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
              <p className={texteDiscret(dark)}>{t}</p><p className="text-lg font-bold mt-0.5">{v}</p>
            </div>
          ))}
        </div>
      </div>
      <div className={carte(dark)}>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {["Tous", "Critique", "Élevé", "Moyen"].map(n => (
            <button key={n} onClick={() => { setFiltre(n); setNbVisibles(15); setOuvert(null); }}
              className={`px-3 py-1 rounded-full text-xs ${filtre === n ? "bg-foret-600 text-white" : dark ? "bg-gray-700 text-gray-300" : "bg-gray-100 text-gray-600"}`}>{n} ({compte(n)})</button>
          ))}
        </div>
        <div className="space-y-2">
          {ops.map((o, i) => (
            <div key={(o.id || "") + i} className={`rounded-xl ${dark ? "bg-gray-700/60" : "bg-gray-50"}`}>
              <button onClick={() => setOuvert(ouvert === i ? null : i)} className="w-full text-left p-3 flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Pastille niveau={o.niveau_risque} />
                    <span className={texteDiscret(dark)}>Plus atypique que {pct(o.score)} des opérations</span>
                    {o.id && <span className={`${texteDiscret(dark)} font-mono`}>{o.id}</span>}
                    {o.fraude_connue && <span className="text-[11px] px-1.5 py-0.5 rounded bg-red-500/15 text-red-500">fraude connue</span>}
                  </div>
                  <p className={`text-sm mt-1 ${dark ? "text-gray-200" : "text-gray-800"}`}>{o.raisons.map(x => x.detail || x.variable).join(" · ")}</p>
                  <p className={`${texteDiscret(dark)} truncate`}>{[o.date && new Date(o.date).toLocaleDateString("fr-FR"), ...Object.values(o.categories).filter(Boolean)].filter(Boolean).join(" · ")}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="font-bold tabular-nums">{devise.formaterValeur(o.montant)}</p>
                  {ouvert === i ? <ChevronUp size={14} className="ml-auto mt-1" /> : <ChevronDown size={14} className="ml-auto mt-1" />}
                </div>
              </button>
              {ouvert === i && (
                <div className="px-3 pb-3">
                  <ResultatRisque dark={dark} type="fraude" resultat={{ score_anomalie: o.score, niveau_risque: o.niveau_risque,
                    facteurs: o.raisons, recommandations: [o.recommandation] }} />
                </div>
              )}
            </div>
          ))}
          {ops.length === 0 && <p className={texteDiscret(dark)}>Aucune opération à ce niveau.</p>}
          {toutes.length > ops.length && (
            <button onClick={() => setNbVisibles(nbVisibles + 15)} className={`${boutonSecondaire(dark)} w-full`}>
              Afficher plus ({toutes.length - ops.length} restantes)
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Analyser une opération (page « Analyse de transaction ») ─────────
export function PanelAnalyseSource({ source, dark }) {
  const devise = useDevise();
  const form = useAPI();
  const calcul = useAPI();
  const [f, setF] = useState(null);
  const [v, setV] = useState({ montant: "", heure: "", categories: {} });
  const [res, setRes] = useState(null);
  useEffect(() => {
    setF(null); setRes(null);
    form.appeler("get", `/sources/${source.id}/risques/formulaire`, null, { params: { devise: devise.code }, timeout: 90000 }).then(r => {
      if (!r) return;
      setF(r.data);
      setV({ montant: Math.round(r.data.montant_habituel || 0), heure: r.data.heure ? "14:00" : "",
             categories: Object.fromEntries(r.data.categories.map(c => [c.colonne, c.valeurs[0]])) });
    });
  }, [form.appeler, source.id, devise.code]); // eslint-disable-line react-hooks/exhaustive-deps
  const analyser = async e => {
    e.preventDefault(); setRes(null);
    const r = await calcul.appeler("post", `/sources/${source.id}/risques/operation`, {
      montant: Number(v.montant), heure: v.heure ? Number(v.heure.split(":")[0]) : null, categories: v.categories, devise: devise.code });
    if (r) setRes(r.data);
  };
  if (form.erreur) return <Indisponible dark={dark} message={form.erreur} />;
  if (!f) return <p className={texteDiscret(dark)}>Apprentissage des habitudes de « {source.nom} »…</p>;
  return (
    <div className={carte(dark)}>
      <h2 className={`${titre(dark)} flex items-center gap-2`}><ScanSearch size={19} /> Analyser une opération</h2>
      <p className={`${texteDiscret(dark)} mb-4`}>
        L'opération est comparée aux habitudes de « {f.titre} » (montant habituel : {devise.formaterValeur(f.montant_habituel)}).
      </p>
      <form onSubmit={analyser} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label>
          <span className={etiquette(dark)}>Montant ({devise.libelle})</span>
          <input type="number" min="0" step="any" required value={v.montant} onChange={e => setV({ ...v, montant: e.target.value })} className={champ(dark)} />
        </label>
        {f.categories.map(c => (
          <label key={c.colonne}>
            <span className={etiquette(dark)}>{c.libelle}</span>
            <select value={v.categories[c.colonne] || ""} onChange={e => setV({ ...v, categories: { ...v.categories, [c.colonne]: e.target.value } })} className={champ(dark)}>
              {c.valeurs.map(x => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
        ))}
        {f.heure && (
          <label>
            <span className={etiquette(dark)}>Heure de l'opération</span>
            <input type="time" value={v.heure} onChange={e => setV({ ...v, heure: e.target.value })} className={champ(dark)} />
          </label>
        )}
        <div className="sm:col-span-2 flex items-center gap-3">
          <button type="submit" disabled={calcul.chargement} className={boutonPrincipal}>{calcul.chargement ? "Analyse…" : "Analyser"}</button>
          {calcul.erreur && <span className="text-sm text-red-500">{calcul.erreur}</span>}
        </div>
      </form>
      {res && <p className={`${texteDiscret(dark)} mt-4`}>{res.explication}</p>}
      <ResultatRisque resultat={res} dark={dark} type="fraude" />
    </div>
  );
}

// ── Portefeuille de crédits (page « Score de crédit ») ───────────────
export function PanelCreditSource({ source, dark }) {
  const devise = useDevise();
  const { appeler, chargement, erreur } = useAPI();
  const [d, setD] = useState(null);
  const [ouvert, setOuvert] = useState(null);
  useEffect(() => {
    setD(null);
    appeler("get", `/sources/${source.id}/risques/credits`, null, { params: { devise: devise.code }, timeout: 90000 }).then(r => r && setD(r.data));
  }, [appeler, source.id, devise.code]);
  if (erreur) return <Indisponible dark={dark} message={erreur} />;
  if (!d || chargement) return <p className={texteDiscret(dark)}>Analyse du portefeuille de « {source.nom} »…</p>;
  return (
    <div className="space-y-4">
      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} flex items-center gap-2`}><Landmark size={19} /> Portefeuille de crédits</h2>
        <p className={`${texteDiscret(dark)} mt-1`}>
          Table « {d.titre} », statut lu dans « {d.colonne_statut} ». Les défauts et retards sont reconnus d'après les valeurs de ce statut.
        </p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
          {[["Crédits", d.credits.toLocaleString("fr-FR")], ["En défaut ou en retard", d.defauts.toLocaleString("fr-FR")],
            ["Taux de défaut observé", pct(d.taux_defaut)], ["En cours", d.en_cours.toLocaleString("fr-FR")]].map(([t, x]) => (
            <div key={t} className={`p-3 rounded-xl ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
              <p className={texteDiscret(dark)}>{t}</p><p className="text-lg font-bold mt-0.5">{x}</p>
            </div>
          ))}
        </div>
      </div>

      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-1`}>Où se concentrent les défauts ?</h2>
        <p className={`${texteDiscret(dark)} mb-4`}>Taux de défaut par segment, comparé à la moyenne du portefeuille ({pct(d.taux_defaut)}).</p>
        <div className="grid lg:grid-cols-2 gap-5">
          {d.segments.map(s => (
            <div key={s.colonne + s.libelle}>
              <p className={`text-sm font-semibold mb-2 ${dark ? "text-gray-200" : "text-gray-800"}`}>{s.libelle}{s.monetaire && d.devise_base ? ` (${d.devise_base === "XAF" ? "FCFA" : d.devise_base})` : ""}</p>
              <div className="space-y-1.5">
                {s.groupes.map(g => (
                  <div key={g.valeur} className="grid grid-cols-[minmax(0,10rem)_1fr_auto] items-center gap-2 text-xs">
                    <span className="truncate" title={g.valeur}>{g.valeur}</span>
                    <div className={`h-2 rounded-full overflow-hidden ${dark ? "bg-gray-600" : "bg-gray-200"}`}>
                      <div className={`h-full ${g.taux_defaut > d.taux_defaut * 1.15 ? "bg-red-500" : g.taux_defaut < d.taux_defaut * 0.85 ? "bg-emerald-500" : "bg-laiton-400"}`}
                        style={{ width: `${Math.min(100, g.taux_defaut * 100)}%` }} />
                    </div>
                    <span className="tabular-nums w-24 text-right">{pct(g.taux_defaut)} <span className={texteDiscret(dark)}>({g.credits})</span></span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-1`}>Crédits en cours les plus à risque</h2>
        {d.modele ? (
          <>
            <p className={`${texteDiscret(dark)} mb-3`}>
              {d.modele.type} appris sur les {d.credits.toLocaleString("fr-FR")} crédits de la base
              {d.modele.auc ? ` (fiabilité ${d.modele.fiabilite} : AUC ${String(d.modele.auc).replace(".", ",")} en validation croisée)` : ""}.
              Le pourcentage est la probabilité de défaut estimée ; « ×2 » signifie deux fois le risque moyen du portefeuille. Clique sur un crédit pour voir pourquoi.
            </p>
            {d.modele.avertissement && (
              <p className="text-xs mb-3 p-2.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/30">{d.modele.avertissement}</p>
            )}
            <div className="space-y-2">
              {d.a_risque.map((c, i) => (
                <Fragment key={(c.id || "") + i}>
                  <button onClick={() => setOuvert(ouvert === i ? null : i)}
                    className={`w-full flex items-center justify-between gap-3 p-3 rounded-xl text-left ${dark ? "bg-gray-700 hover:bg-gray-600" : "bg-gray-50 hover:bg-gray-100"}`}>
                    <div className="min-w-0">
                      <p className="text-sm font-medium">
                        Crédit <span className="font-mono">{c.id || i + 1}</span>
                        {c.montant != null && <span className="ml-2 tabular-nums">{devise.formaterValeur(c.montant)}</span>}
                      </p>
                      <p className={`${texteDiscret(dark)} truncate`}>
                        {[...Object.entries(c.valeurs || {}).filter(([, x]) => x).map(([k, x]) => `${k} : ${x}`),
                          c.facteurs?.[0] && c.facteurs[0].impact > 0 ? `surtout : ${c.facteurs[0].variable.toLowerCase()}` : null].filter(Boolean).join(" · ")}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {c.risque_relatif != null && <span className={`${texteDiscret(dark)} tabular-nums`}>×{String(c.risque_relatif).replace(".", ",")}</span>}
                      <Pastille niveau={c.niveau_risque}>{pct(c.probabilite_defaut)}</Pastille>
                    </div>
                  </button>
                  {ouvert === i && <ResultatRisque dark={dark} type="credit" resultat={{ ...c,
                    facteurs: c.facteurs.map(x => ({ ...x, detail: x.detail ? `${x.valeur} (${x.detail})` : x.valeur })),
                    recommandations: c.recommandations || [] }} />}
                </Fragment>
              ))}
            </div>
          </>
        ) : (
          <p className={`${texteDiscret(dark)}`}>
            Pas assez de défauts connus (15 au moins) pour apprendre un modèle fiable sur cette base : les taux de défaut par segment
            ci-dessus restent valables pour orienter le suivi.
          </p>
        )}
      </div>
    </div>
  );
}
