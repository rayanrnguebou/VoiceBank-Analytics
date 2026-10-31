// Tableau de bord d'une base connectée : indicateurs et graphiques choisis par l'API d'après la structure
// de la base (clients, transactions, crédits, ventes…), montants dans la monnaie choisie.
import { useEffect, useState } from "react";
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import {
  Users, Activity, ShieldAlert, CreditCard, Wallet, ShoppingCart, Building2, Package, Table2, RefreshCw, Database,
} from "lucide-react";
import { http, messageErreur } from "../api";
import { LOCALE, tx } from "../i18n";

const ICONES = {
  clients: [Users, "#1F654D"], comptes: [Wallet, "#3E6FB0"], transactions: [Activity, "#3E6FB0"],
  ventes: [ShoppingCart, "#3E6FB0"], "crédits": [CreditCard, "#A9852A"], alertes: [ShieldAlert, "#EF4444"],
  agences: [Building2, "#6B7280"], produits: [Package, "#6B7280"],
};

const ATTENTE_COMPLET_MS = 10000;   // grande base : on revient chercher le calcul sur toutes les lignes
const ESSAIS_COMPLET = 90;           // soit 15 minutes au plus

export function useTableauSource(source, devise) {
  const [etat, setEtat] = useState({ id: null, donnees: null, chargement: false, erreur: null });
  const id = source?.id;
  useEffect(() => {
    if (!id) { setEtat({ id: null, donnees: null, chargement: false, erreur: null }); return; }
    let annule = false, minuteur = null, essais = 0;
    // Autre base : on efface aussitôt les chiffres de la précédente ; autre monnaie : on les garde le temps du calcul
    setEtat(e => ({ id, donnees: e.id === id ? e.donnees : null, chargement: true, erreur: null }));
    const charger = premier => http.get(`/sources/${id}/tableau`, { params: { devise }, timeout: 90000 })
      .then(r => {
        if (annule) return;
        const d = r.data.data;
        setEtat({ id, donnees: d, chargement: false, erreur: null });
        // Aperçu sur échantillon : le calcul sur toutes les lignes tourne sur le serveur, on l'affiche dès qu'il est prêt
        if (d && d.complet === false && essais++ < ESSAIS_COMPLET) minuteur = setTimeout(() => charger(false), ATTENTE_COMPLET_MS);
      })
      .catch(err => { if (!annule && premier) setEtat({ id, donnees: null, chargement: false, erreur: messageErreur(err) }); });
    charger(true);
    return () => { annule = true; clearTimeout(minuteur); };
  }, [id, devise]);
  return etat;
}

// Indicateurs au format des cartes du tableau de bord
export function kpisSource(donnees, devise) {
  return (donnees?.indicateurs || []).map(i => {
    const [icone, couleur] = i.titre === "Fraudes" ? ICONES.alertes
      : i.type === "montant" ? [CreditCard, "#A9852A"] : (ICONES[i.entite] || [Table2, "#1F654D"]);
    return {
      titre: i.echantillon ? tx("{titre} (échantillon)", { titre: i.titre }) : i.titre, icone, couleur,
      valeur: i.type === "montant" ? devise.formaterValeur(i.valeur, { compact: true }) : Number(i.valeur || 0).toLocaleString(LOCALE),
    };
  });
}

const libelleMois = l => {
  const [a, m] = String(l).split("-").map(Number);
  return a && m ? new Date(a, m - 1, 1).toLocaleDateString(LOCALE, { month: "short", year: "2-digit" }) : l;
};

export function SelecteurSource({ dark, sourceActive, sourcesPretes, onChoisir }) {
  if (!sourcesPretes.length && !sourceActive) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>{tx("Données interrogées :")}</span>
      <select aria-label={tx("Données interrogées")} value={sourceActive ? String(sourceActive.id) : ""}
        onChange={e => onChoisir(e.target.value ? sourcesPretes.find(x => String(x.id) === e.target.value) : null)}
        className={`text-xs px-2 py-1.5 rounded-lg border outline-none ${dark ? "bg-gray-700 border-gray-600" : "bg-gray-50 border-gray-200"}`}>
        <option value="">{tx("Base VoiceBank (démonstration)")}</option>
        {sourcesPretes.map(x => <option key={x.id} value={String(x.id)}>{x.nom} · {x.libelle_type}</option>)}
        {sourceActive && !sourcesPretes.some(x => x.id === sourceActive.id) && <option value={String(sourceActive.id)}>{sourceActive.nom}</option>}
      </select>
    </div>
  );
}

export function PanelTableauSource({ dark, etat, devise }) {
  const carte = `rounded-2xl border p-5 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`;
  const discret = `text-sm ${dark ? "text-gray-500" : "text-gray-400"}`;
  if (etat.chargement && !etat.donnees) {
    return <p className={`${discret} flex items-center gap-2`} role="status"><RefreshCw size={14} className="animate-spin" />{" "}{tx("Calcul du tableau de bord de ta base…")}</p>;
  }
  if (etat.erreur) return <p role="alert" className="text-sm text-red-500">{etat.erreur}</p>;
  const graphiques = etat.donnees?.graphiques || [];
  if (!graphiques.length) {
    return <p className={`${discret} flex items-center gap-2`}><Database size={14} />{" "}{tx("Pas assez de données datées ou catégorisées dans cette base pour tracer des graphiques. Pose une question à l'assistant.")}</p>;
  }
  const axe = { fill: dark ? "#9CA3AF" : "#6B7280", fontSize: 11 };
  const infobulle = { contentStyle: { backgroundColor: dark ? "#1F2937" : "#fff", border: "none", borderRadius: 8 },
                      labelStyle: { color: dark ? "#fff" : "#111" } };
  const couleurs = ["#1F654D", "#C9A13B", "#3E6FB0", "#EF4444"];
  const d = etat.donnees;
  return (
    <div className="space-y-3">
    {d?.complet === false && (
      <p role="status" className={`text-xs flex items-center gap-2 px-3 py-2 rounded-lg ${dark ? "bg-amber-900/30 text-amber-200" : "bg-amber-50 text-amber-800"}`}>
        <RefreshCw size={13} className={d.calcul_complet_en_cours ? "animate-spin" : ""} />{" "}
        {d.calcul_complet_en_cours
          ? tx("Aperçu rapide affiché. Calcul sur toutes les lignes en cours : le tableau se met à jour tout seul dès qu'il est prêt.")
          : tx("Aperçu rapide affiché, calculé sur un échantillon des lignes.")}
      </p>)}
    {d?.complet && d?.complet_le && (
      <p className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
        {tx("Calculé sur toutes les lignes le {date}.", { date: new Date(d.complet_le).toLocaleString(LOCALE, { dateStyle: "short", timeStyle: "short" }) })}
      </p>)}
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {graphiques.map((g, n) => {
        const montant = g.series.some(s => s.montant);
        const donnees = g.donnees.map(p => ({ ...p, label: g.temps ? libelleMois(p.label) : p.label }));
        const format = v => (montant ? devise.formaterValeur(v, { compact: true }) : Number(v).toLocaleString(LOCALE));
        const Graphique = g.type === "line" ? LineChart : BarChart;
        return (
          <section key={g.id} className={carte} aria-label={g.titre}>
            <h3 className={`text-sm font-bold ${g.echantillon ? "mb-1" : "mb-4"} ${dark ? "text-white" : "text-gray-900"}`}>{g.titre}</h3>
            {g.echantillon && <p className={`text-xs mb-3 ${dark ? "text-gray-400" : "text-gray-500"}`}>
              {tx("Grande table : calculé sur {x} lignes, pour un affichage rapide.", { x: Number(g.echantillon).toLocaleString(LOCALE) })}</p>}
            <ResponsiveContainer width="100%" height={220}>
              <Graphique data={donnees}>
                <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
                <XAxis dataKey="label" tick={axe} />
                <YAxis tick={axe} tickFormatter={v => (montant ? devise.formaterValeur(v, { compact: true }).replace(` ${devise.libelle}`, "") : v)} width={montant ? 60 : 40} />
                <Tooltip {...infobulle} formatter={v => format(v)} />
                {g.series.map(s => g.type === "line"
                  ? <Line key={s.cle} type="monotone" dataKey={s.cle} stroke={couleurs[n % 4]} strokeWidth={2} dot={false} name={s.nom} />
                  : <Bar key={s.cle} dataKey={s.cle} fill={couleurs[n % 4]} radius={[4, 4, 0, 0]} name={s.nom} />)}
              </Graphique>
            </ResponsiveContainer>
          </section>
        );
      })}
    </div>
    </div>
  );
}
