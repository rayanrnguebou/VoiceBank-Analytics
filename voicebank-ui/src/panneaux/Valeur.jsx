// « Valeur créée » : ce que VoiceBank a rapporté sur la période, avec la façon dont chaque chiffre est calculé.
import { useEffect, useState } from "react";
import { TrendingUp, HandCoins, ShieldCheck, Clock, Percent, Info, History, Landmark } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { useAPI } from "../useAPI";
import { useDevise } from "../devise";
import { carte, titre, texteDiscret } from "../ui";
import { LOCALE, tx } from "../i18n";

const PERIODES = [[30, "30 jours"], [90, "3 mois"], [365, "12 mois"]];

function Indicateur({ dark, Icone, couleur, libelle, valeur, detail }) {
  return (
    <div className={`p-4 rounded-2xl border ${dark ? "border-gray-700 bg-gray-800" : "border-gray-200 bg-white shadow-sm"}`}>
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-lg" style={{ background: `${couleur}22`, color: couleur }}><Icone size={16} /></span>
        <p className={texteDiscret(dark)}>{libelle}</p>
      </div>
      <p className="mt-2 text-2xl font-extrabold tabular-nums">{valeur}</p>
      <p className={`${texteDiscret(dark)} mt-1`}>{detail}</p>
    </div>
  );
}

const VERDICTS = { bon: ["Concluant", "bg-emerald-500/15 text-emerald-600"], moyen: ["Utile, à confirmer", "bg-laiton-400/20 text-laiton-600"],
  faible: ["Peu concluant", "bg-gray-500/15 text-gray-500"] };

function Verdict({ v }) {
  const [l, c] = VERDICTS[v] || VERDICTS.faible;
  return <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${c}`}>{tx(l)}</span>;
}

const jour = d => new Date(d).toLocaleDateString(LOCALE);

// Ce que VoiceBank aurait repéré sur les données passées de l'organisation (preuve chiffrée, sans tricher)
export function PreuveHistorique({ id, dark }) {
  const devise = useDevise();
  const { appeler, erreur } = useAPI();
  const [h, setH] = useState(null);
  useEffect(() => {
    setH(null);
    appeler("get", `/sources/${id}/test-historique`, null, { params: { devise: devise.code }, timeout: 120000 }).then(r => r && setH(r.data));
  }, [appeler, id, devise.code]);
  const f = x => devise.formaterValeur(x, { compact: true });
  const boite = `rounded-xl p-4 ${dark ? "bg-gray-700/50" : "bg-gray-50"}`;
  const c = h?.credits, fr = h?.fraude;
  return (
    <div className={carte(dark)}>
      <h3 className={`${titre(dark)} flex items-center gap-2`}><History size={18} className="text-foret-500" />{" "}{tx("Test sur votre historique")}</h3>
      <p className={`${texteDiscret(dark)} mt-1`}>{tx("Ce que VoiceBank aurait repéré dans vos données passées, mesuré sans tricher : le modèle ne voit jamais la réponse qu'on lui demande de trouver.")}</p>
      {erreur && <p className="text-sm text-red-500 mt-3">{erreur}</p>}
      {!h && !erreur && <p className={`${texteDiscret(dark)} mt-3`}>{tx("Rejeu de l'historique…")}</p>}
      {h && (
        <div className="grid lg:grid-cols-2 gap-3 mt-4">
          <div className={boite}>
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold flex items-center gap-1.5"><Landmark size={15} />{tx("Défauts de crédit")}</p>
              {!c.indisponible && <Verdict v={c.verdict} />}
            </div>
            {c.indisponible ? <p className={`${texteDiscret(dark)} mt-2`}>{c.indisponible}</p> : (
              <>
                <p className="text-sm mt-2 leading-relaxed">
                  {tx("Appris sur les {a} crédits les plus anciens, le modèle a classé les {t} plus récents comme s'il les découvrait. Parmi les 20 % qu'il jugeait les plus risqués, {x} % ont réellement fait défaut, contre {m} % en moyenne.",
                    { a: c.apprentissage.toLocaleString(LOCALE), t: c.test.toLocaleString(LOCALE), x: String(c.taux_defaut_cible_pct).replace(".", ","), m: String(c.taux_defaut_moyen_pct).replace(".", ",") })}
                </p>
                <div className="grid grid-cols-3 gap-2 mt-3 text-center">
                  <div><p className="text-xl font-extrabold">{c.defauts_reperes}/{c.defauts_test}</p><p className={texteDiscret(dark)}>{tx("défauts repérés")}</p></div>
                  <div><p className="text-xl font-extrabold">{c.montant_repere != null ? f(c.montant_repere) : "--"}</p><p className={texteDiscret(dark)}>{tx("montant en défaut repéré")}</p></div>
                  <div><p className="text-xl font-extrabold">{String(c.auc).replace(".", ",")}</p><p className={texteDiscret(dark)}>{tx("AUC (0,5 = hasard)")}</p></div>
                </div>
                {c.periode_test && <p className={`${texteDiscret(dark)} mt-2`}>{tx("Apprentissage : {a} → {b} · test : {c} → {d}", { a: jour(c.periode_apprentissage[0]), b: jour(c.periode_apprentissage[1]), c: jour(c.periode_test[0]), d: jour(c.periode_test[1]) })}</p>}
                {c.verdict === "faible" && <p className="text-xs text-amber-600 mt-2">{tx("Les colonnes de cette base prédisent mal les défauts : ne vous fiez pas à ce classement, appuyez-vous sur les taux de défaut par segment.")}</p>}
              </>
            )}
          </div>
          <div className={boite}>
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold flex items-center gap-1.5"><ShieldCheck size={15} />{tx("Fraudes")}</p>
              {!fr.indisponible && <Verdict v={fr.verdict} />}
            </div>
            {fr.indisponible ? <p className={`${texteDiscret(dark)} mt-2`}>{fr.indisponible}</p> : (
              <>
                <p className="text-sm mt-2 leading-relaxed">
                  {tx("En ne regardant que les 5 % d'opérations les plus atypiques sur {n}, VoiceBank retrouve {x} des {k} fraudes connues ({p} %, contre 5 % au hasard). Le détecteur n'a jamais vu les étiquettes de fraude.",
                    { n: fr.operations.toLocaleString(LOCALE), x: fr.fraudes_reperees, k: fr.fraudes_connues, p: String(fr.fraudes_reperees_pct).replace(".", ",") })}
                </p>
                <div className="grid grid-cols-2 gap-2 mt-3 text-center">
                  <div><p className="text-xl font-extrabold">{f(fr.montant_repere)}</p><p className={texteDiscret(dark)}>{tx("montant fraudé repéré")}</p></div>
                  <div><p className="text-xl font-extrabold">{fr.montant_repere_pct == null ? "--" : `${String(fr.montant_repere_pct).replace(".", ",")} %`}</p><p className={texteDiscret(dark)}>{tx("du montant total fraudé")}</p></div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function PanelValeur({ source, dark }) {
  const devise = useDevise();
  const { appeler, erreur } = useAPI();
  const [jours, setJours] = useState(30);
  const [v, setV] = useState(null);
  const id = source?.id || 0;
  useEffect(() => {
    setV(null);
    appeler("get", `/sources/${id}/valeur`, null, { params: { jours, devise: devise.code } }).then(r => r && setV(r.data));
  }, [appeler, id, jours, devise.code]);

  if (erreur) return <p className="text-sm text-red-500">{erreur}</p>;
  if (!v) return <p className={texteDiscret(dark)}>{tx("Calcul de la valeur créée…")}</p>;
  const f = x => devise.formaterValeur(x, { compact: true });
  const series = v.par_semaine.map(s => ({ semaine: new Date(s.semaine).toLocaleDateString(LOCALE, { day: "2-digit", month: "2-digit" }), montant: s.montant }));
  return (
    <div className="space-y-4">
      <div className={`${carte(dark)} relative overflow-hidden`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className={`${texteDiscret(dark)} flex items-center gap-1.5`}><TrendingUp size={14} className="text-emerald-500" />
              {tx("Valeur créée pour « {nom} » depuis le {x}", { nom: source?.nom || tx("Démonstration VoiceBank"), x: new Date(v.depuis).toLocaleDateString(LOCALE) })}</p>
            <p className="mt-1 text-4xl font-black tabular-nums text-emerald-500">{f(v.total)}</p>
            <p className={`${texteDiscret(dark)} mt-1`}>{tx("Argent récupéré + fraude évitée, plus {h} h de travail d'analyse épargnées.", { h: v.heures_gagnees.toLocaleString(LOCALE) })}</p>
          </div>
          <div role="tablist" aria-label={tx("Période")} className="flex gap-1">
            {PERIODES.map(([j, l]) => (
              <button key={j} role="tab" aria-selected={jours === j} onClick={() => setJours(j)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${jours === j ? "bg-foret-600 text-white" : dark ? "bg-gray-700 text-gray-300" : "bg-gray-100 text-gray-600"}`}>{tx(l)}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <Indicateur dark={dark} Icone={HandCoins} couleur="#059669" libelle={tx("Argent récupéré")} valeur={f(v.recupere)}
          detail={tx("Paiements saisis dans les dossiers ; {y} dossier(s) réglé(s)", { y: v.dossiers_regles.toLocaleString(LOCALE) })} />
        <Indicateur dark={dark} Icone={ShieldCheck} couleur="#DC2626" libelle={tx("Fraude évitée")} valeur={f(v.fraude_evitee)}
          detail={tx("{x} fraude(s) confirmée(s) sur {y} alerte(s) traitée(s)", { x: v.fraudes_confirmees, y: v.alertes_traitees })} />
        <Indicateur dark={dark} Icone={Clock} couleur="#3E6FB0" libelle={tx("Temps gagné")} valeur={tx("{x} h", { x: v.heures_gagnees.toLocaleString(LOCALE) })}
          detail={tx("{x} questions répondues × {m} min (hypothèse)", { x: v.questions.toLocaleString(LOCALE), m: v.minutes_par_question })} />
        <Indicateur dark={dark} Icone={Percent} couleur="#C9A13B" libelle={tx("Taux de récupération")}
          valeur={v.taux_recuperation == null ? "--" : `${(v.taux_recuperation * 100).toFixed(1).replace(".", ",")} %`}
          detail={tx("Récupéré ÷ (récupéré + reste à recouvrer : {x})", { x: f(v.reste_a_recouvrer) })} />
      </div>
      <div className={carte(dark)}>
        <h3 className={titre(dark)}>{tx("Argent récupéré par semaine")}</h3>
        {series.length ? (
          <div className="h-56 mt-3">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={series}>
                <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#E5E7EB"} vertical={false} />
                <XAxis dataKey="semaine" tick={{ fontSize: 11, fill: dark ? "#9CA3AF" : "#6B7280" }} />
                <YAxis tick={{ fontSize: 11, fill: dark ? "#9CA3AF" : "#6B7280" }} tickFormatter={x => devise.formaterValeur(x, { compact: true })} width={80} />
                <Tooltip formatter={x => devise.formaterValeur(x)} />
                <Bar dataKey="montant" name={tx("Récupéré")} fill="#059669" radius={[6, 6, 0, 0]} maxBarSize={56} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : <p className={`${texteDiscret(dark)} mt-2`}>{tx("Aucun paiement enregistré sur la période : ils apparaîtront ici dès les premiers dossiers réglés.")}</p>}
        <p className={`${texteDiscret(dark)} mt-4 flex gap-1.5`}><Info size={13} className="flex-shrink-0 mt-0.5" />
          {tx("Chaque chiffre vient de l'activité réelle enregistrée dans VoiceBank : paiements saisis dans les dossiers de recouvrement, alertes confirmées comme fraudes, questions répondues. Seul le temps gagné repose sur une hypothèse, affichée ci-dessus.")}</p>
      </div>
      <PreuveHistorique id={id} dark={dark} />
    </div>
  );
}
