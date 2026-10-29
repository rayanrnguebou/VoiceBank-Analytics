// VOICEBANK ANALYTICS — Interface React v3
// Auteur : Nguebou Temgoua Rayan
// v3 : connexion sécurisée, corrections de bugs, analyse de transaction IA

import { useState, useEffect, useRef, useCallback } from "react";
import { http, lireSession, deconnexion, messageErreur, appliquerJeton } from "./api";
import EcranAccueil from "./panneaux/Accueil";
import { BandeauAcces, PanelAbonnement, PanelAbonnements } from "./panneaux/Abonnement";
import { LectureSeule, useLectureSeule, TITRE_LECTURE_SEULE } from "./lectureSeule";
import PanelSources from "./panneaux/Connecteur";
import PanelOrganisation, { PanelJournal } from "./panneaux/Organisation";
import { Choix } from "./ChampListe";
import ChampsEtablissement, { PAYS_MODELE } from "./panneaux/ChampsEtablissement";
import { PanelFiches, PanelNotifications } from "./panneaux/Surveillance";
import ResultatRisque from "./panneaux/Explication";
import { PanelOperationsSource, PanelAnalyseSource, PanelCreditSource } from "./panneaux/RisquesSource";
import Demarrage from "./panneaux/Demarrage";
import { useMaintenance, EcranMaintenance, BandeauAnnonce, BandeauReconnexion, PanelMaintenance } from "./maintenance";
import { FournisseurDevise, useDevise, SelecteurDevise, libelleColonne } from "./devise";
import { useSessionActive } from "./session";
import { useAPI } from "./useAPI";
import PanelAlertes from "./panneaux/Alertes";
import { useTableauSource, kpisSource, SelecteurSource, PanelTableauSource } from "./panneaux/TableauSource";
import PanelCredit from "./panneaux/Credit";
import BarreLaterale from "./panneaux/BarreLaterale";
import { FormulaireSignalement, EditeurCorrection, PanelApprentissage, PanelFiabilite, PanelAudit } from "./panneaux/Admin";
import { EcranMotDePasseProvisoire, FenetreMotDePasse, PanelComptes } from "./panneaux/Comptes";
import { EcranDoubleAuthObligatoire } from "./panneaux/DoubleAuth";
import { lireAVoixHaute, arreterLecture, telechargerCsv, nomFichier } from "./ui";
import { ecouterReponse, interpreterReponse } from "./conversation";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from "recharts";
import {
  Mic, MicOff, Sun, Moon, RefreshCw, Send,
  Activity, Users, CreditCard,
  ShieldAlert, Trash2, ChevronDown, ChevronUp, Download,
  History, CheckSquare, Square, FileText, AlertTriangle, X,
  Volume2, VolumeX, Flag, Wrench, Menu, MessagesSquare, CornerDownRight, Calendar, Clock, Timer,
  ChartColumn, ChartLine, ChartPie, ChartArea, Gauge, Table2, BookCheck, Zap, Sparkles,
} from "lucide-react";
import { LANGUE, LOCALE, LOCALE_VOIX, tx } from "./i18n";

// ════════════════════════════════════════
// CONFIGURATION
// ════════════════════════════════════════

const COULEURS     = ["#1F654D","#C9A13B","#3E6FB0","#B5523B","#6A8F3A","#7A5BA6","#2F9C95","#D08A2E","#5D6B66","#A43E6C"];
const CLE_STORAGE  = "voicebank_historique";
const MAX_HISTORIQUE = 30;      // entrées conservées
const MAX_LIGNES_HISTO = 200;   // lignes de données gardées par entrée

const SOURCES = {
  rag:    { label: "RAG",    classe: "bg-emerald-100 text-emerald-700" },
  rule:   { label: tx("Règle"),  classe: "bg-amber-100 text-amber-700" },
  gemini: { label: "Gemini", classe: "bg-foret-100 text-foret-700" },
};

// Historique en sessionStorage (effacé à la fermeture de l'onglet et à la déconnexion) :
// il contient des données clients, il ne doit pas rester dans le navigateur.
function chargerHistorique(utilisateur) {
  try { return JSON.parse(sessionStorage.getItem(`${CLE_STORAGE}_${utilisateur}`) || "[]"); }
  catch (e) { return []; }
}
function sauverHistorique(utilisateur, historique) {
  try {
    const compact = historique.slice(0, MAX_HISTORIQUE)
      .map(h => ({ ...h, data: (h.data || []).slice(0, MAX_LIGNES_HISTO) }));
    sessionStorage.setItem(`${CLE_STORAGE}_${utilisateur}`, JSON.stringify(compact));
  } catch (e) { /* quota dépassé ou stockage indisponible */ }
}

// ════════════════════════════════════════
// UTILITAIRES
// ════════════════════════════════════════

function detecterTypeGraphique(colonnes, data) {
  if (!data || data.length === 0) return "table";
  const cols = colonnes.map(c => c.toLowerCase());
  const aDate   = cols.some(c => c.includes("date") || c.includes("mois"));
  const aNombre = cols.some(c => c.includes("count") || c.includes("nb_") || c.includes("total") || c.includes("montant") || c.includes("solde") || c.includes("volume")
    || c === "nombre" || c.startsWith("moyenne") || c.startsWith("maximum") || c.startsWith("minimum"));
  const aCateg  = cols.some(c => c.includes("banque") || c.includes("ville") || c.includes("statut") || c.includes("type") || c.includes("pays") || c.includes("canal"));
  if (data.length === 1) return "kpi";
  if (aDate && aNombre) return "line";
  if (aCateg && aNombre && data.length <= 15) return "bar";
  if (aCateg && data.length <= 8 && !aNombre) return "pie";
  if (aNombre && data.length > 15) return "area";
  // Bases connectées (noms de colonnes inconnus) : une catégorie et une valeur → barres
  const ligne = data[0];
  const nums = colonnes.filter(c => typeof ligne[c] === "number");
  const categ = colonnes.find(c => typeof ligne[c] === "string") || (/(^id_|_id$|^id$)/i.test(colonnes[0]) ? colonnes[0] : null);
  if (categ && nums.some(c => c !== categ) && data.length <= 20 && colonnes.length <= 4) return "bar";
  return "table";
}

function trouverCleNumerique(row, sql) {
  const categ = trouverCleCateg(row);
  // La colonne de tri de la requête est celle que l'utilisateur veut comparer (ORDER BY nb_fraudes…)
  const tri = /order\s+by\s+(?:\w+\.)?"?(\w+)"?/i.exec(sql || "");
  if (tri) {
    const cle = Object.keys(row).find(k => k.toLowerCase() === tri[1].toLowerCase());
    if (cle && typeof row[cle] === "number") return cle;
  }
  const priorites = ["montant_fcfa","solde_fcfa","nb_clients","nb_transactions","total","count","volume","score",
    "nombre","moyenne","maximum","minimum"];
  for (const p of priorites)
    for (const k of Object.keys(row))
      if (k.toLowerCase().includes(p)) return k;
  return Object.keys(row).find(k => k !== categ && typeof row[k] === "number" && !isNaN(row[k]))
    || Object.keys(row).find(k => typeof row[k] === "number" && !isNaN(row[k]));
}

function trouverCleCateg(row) {
  const priorites = ["banque","ville","statut","type","pays","canal","nom","prenom"];
  // Mot entier : « nom » ne doit pas désigner la colonne « nombre »
  const contient = (k, p) => k.toLowerCase().split(/[^a-z0-9]+/).includes(p);
  for (const p of priorites)
    for (const k of Object.keys(row))
      if (contient(k, p) && typeof row[k] !== "number") return k;
  const cles = Object.keys(row);
  return cles.find(k => typeof row[k] === "string") || cles.find(k => /(^id_|_id$|^id$)/i.test(k));
}

function formaterValeur(val) {
  if (typeof val === "number") {
    if (val > 1_000_000) return (val / 1_000_000).toFixed(1) + "M";
    if (val > 1_000)     return (val / 1_000).toFixed(1) + "k";
    return val.toLocaleString(LOCALE);
  }
  return String(val ?? "");
}

// ════════════════════════════════════════
// HOOK API
// ════════════════════════════════════════

// ════════════════════════════════════════
// COMPOSANT — GRAPHIQUES DASHBOARD
// ════════════════════════════════════════

function PanelGraphiques({ dark, stats }) {
  if (!stats) return null;
  const { clients_par_banque = [], transactions_mois = [] } = stats || {};

  const dataClients = (clients_par_banque || []).slice(0, 6).map(b => ({
    name: b.banque?.replace(" Cameroun","").replace("Société Générale","SG") || "",
    clients: b.nb_clients,
    diaspora: b.nb_diaspora,
  }));

  const parMois = {};
  (transactions_mois || []).forEach(m => {
    const cle = m.mois ? new Date(m.mois).toLocaleDateString(LOCALE, { month: "short", year: "2-digit" }) : "";
    if (!parMois[cle]) parMois[cle] = { mois: cle, transactions: 0, fraudes: 0 };
    parMois[cle].transactions += m.nb_transactions || 0;
    parMois[cle].fraudes      += m.nb_fraudes      || 0;
  });
  const dataMois = Object.values(parMois).slice(-12);  // l'API renvoie les mois en ordre chronologique
  const axisStyle = { fill: dark ? "#9CA3AF" : "#6B7280", fontSize: 11 };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className={`rounded-2xl border p-5 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
        <h3 className={`text-sm font-bold mb-4 ${dark ? "text-white" : "text-gray-900"}`}>{tx("Clients par banque")}</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={dataClients}>
            <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
            <XAxis dataKey="name" tick={axisStyle} />
            <YAxis tick={axisStyle} />
            <Tooltip contentStyle={{ backgroundColor: dark ? "#1F2937" : "#fff", border: "none", borderRadius: 8 }} labelStyle={{ color: dark ? "#fff" : "#111" }} />
            <Bar dataKey="clients" fill="#1F654D" radius={[4,4,0,0]} name="Total" />
            <Bar dataKey="diaspora" fill="#C9A13B" radius={[4,4,0,0]} name="Diaspora" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className={`rounded-2xl border p-5 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
        <h3 className={`text-sm font-bold mb-4 ${dark ? "text-white" : "text-gray-900"}`}>{tx("Transactions mensuelles")}</h3>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={dataMois}>
            <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
            <XAxis dataKey="mois" tick={axisStyle} />
            <YAxis tick={axisStyle} />
            <Tooltip contentStyle={{ backgroundColor: dark ? "#1F2937" : "#fff", border: "none", borderRadius: 8 }} />
            <Line type="monotone" dataKey="transactions" stroke="#1F654D" strokeWidth={2} dot={false} name="Total" />
            <Line type="monotone" dataKey="fraudes" stroke="#EF4444" strokeWidth={2} dot={false} name="Fraudes" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ════════════════════════════════════════
// COMPOSANT — GRAPHIQUE DYNAMIQUE (affiché dans l'UI)
// ════════════════════════════════════════

function GraphiqueDynamique({ colonnes, data, question, dark, sql, item }) {
  const type     = detecterTypeGraphique(colonnes, data);
  const cleNum   = trouverCleNumerique(data[0] || {}, sql);
  const cleCateg = trouverCleCateg(data[0] || {});
  const axisStyle = { fill: dark ? "#9CA3AF" : "#6B7280", fontSize: 11 };
  const tooltipStyle = {
    contentStyle: { backgroundColor: dark ? "#1F2937" : "#fff", border: "none", borderRadius: 8, fontSize: 12 },
    labelStyle: { color: dark ? "#fff" : "#111" },
  };

  if (type === "kpi") {
    return (
      <div className="grid grid-cols-2 gap-3">
        {Object.entries(data[0]).map(([k, v]) => (
          <div key={k} className={`rounded-xl p-4 text-center ${dark ? "bg-gray-700" : "bg-gray-50"}`}>
            <p className={`text-xs mb-1 ${dark ? "text-gray-400" : "text-gray-500"}`}>{k}</p>
            <p className={`text-xl font-bold ${dark ? "text-white" : "text-gray-900"}`}>{formaterValeur(v)}</p>
          </div>
        ))}
      </div>
    );
  }
  if (type === "pie" && cleCateg) {
    const pieData = data.slice(0, 8).map(row => ({
      name: String(row[cleCateg] || "").slice(0, 20),
      value: Number(row[cleNum] || Object.values(row).find(v => typeof v === "number") || 1),
    }));
    return (
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({name}) => name.slice(0,12)}>
            {pieData.map((_, i) => <Cell key={i} fill={COULEURS[i % COULEURS.length]} />)}
          </Pie>
          <Tooltip {...tooltipStyle} />
        </PieChart>
      </ResponsiveContainer>
    );
  }
  if (type === "line" && cleNum) {
    // Séries « annee / mois » des bases connectées : axe 2025-01, 2025-02…
    if (colonnes.includes("annee") && colonnes.includes("mois")) {
      data = data.map(l => ({ ...l, periode: `${l.annee}-${String(l.mois).padStart(2, "0")}` }));
    }
    const cleDateKey = data[0]?.periode ? "periode" : colonnes.find(c => c.toLowerCase().includes("date") || c.toLowerCase().includes("mois"));
    return (
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data.slice(0, 50)}>
          <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
          <XAxis dataKey={cleDateKey} tick={axisStyle} tickFormatter={v => String(v).slice(0, 10)} />
          <YAxis tick={axisStyle} tickFormatter={formaterValeur} />
          <Tooltip {...tooltipStyle} formatter={formaterValeur} />
          <Line type="monotone" dataKey={cleNum} stroke="#1F654D" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    );
  }
  if (type === "area" && cleNum && cleCateg) {
    return (
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data.slice(0, 50)}>
          <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
          <XAxis dataKey={cleCateg} tick={axisStyle} />
          <YAxis tick={axisStyle} tickFormatter={formaterValeur} />
          <Tooltip {...tooltipStyle} formatter={formaterValeur} />
          <Area type="monotone" dataKey={cleNum} stroke="#1F654D" fill="#1F654D20" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    );
  }
  if (type === "bar" && cleNum && cleCateg) {
    return (
      // Une seule mesure comparée entre catégories : une seule couleur, la première barre en laiton
      <ResponsiveContainer width="100%" height={Math.max(180, Math.min(data.length, 20) * 30 + 40)}>
        <BarChart data={data.slice(0, 20)} layout="vertical" margin={{ left: 8, right: 16 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={dark ? "#2D3532" : "#E9EDEB"} />
          <XAxis type="number" tick={axisStyle} tickFormatter={formaterValeur} />
          <YAxis type="category" dataKey={cleCateg} tick={axisStyle} width={170} interval={0}
            tickFormatter={v => { const t = String(v); return t.length > 26 ? t.slice(0, 25) + "…" : t; }} />
          <Tooltip {...tooltipStyle} formatter={formaterValeur} cursor={{ fill: dark ? "#ffffff10" : "#0000000a" }} />
          <Bar dataKey={cleNum} radius={[0, 4, 4, 0]} barSize={18}>
            {data.slice(0, 20).map((_, i) => <Cell key={i} fill={i === 0 ? "#C9A13B" : dark ? "#4A9277" : "#1F654D"} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }
  return (
    <div className="overflow-x-auto max-h-64">
      <table className="w-full text-xs">
        <thead>
          <tr className={dark ? "bg-gray-700" : "bg-gray-50"}>
            {colonnes.slice(0, 7).map(c => (
              <th key={c} className={`text-left px-3 py-2 font-medium ${dark ? "text-gray-300" : "text-gray-600"}`}>{libelleColonne(c, item)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className={`border-t ${dark ? "border-gray-700" : "border-gray-100"}`}>
              {colonnes.slice(0, 7).map(c => (
                <td key={c} className={`px-3 py-2 ${dark ? "text-gray-300" : "text-gray-700"}`}>{String(row[c] ?? "").slice(0, 30)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ════════════════════════════════════════
// COMPOSANT — GRAPHIQUE POUR PDF (dimensions fixes, fond blanc)
// ════════════════════════════════════════

function GraphiquePourPDF({ colonnes, data, sql, item }) {
  const type     = detecterTypeGraphique(colonnes, data);
  const cleNum   = trouverCleNumerique(data[0] || {}, sql);
  const cleCateg = trouverCleCateg(data[0] || {});
  const axisStyle = { fill: "#374151", fontSize: 11 };
  const tooltipStyle = { contentStyle: { backgroundColor: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 } };

  if (type === "kpi") {
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, padding: 8 }}>
        {Object.entries(data[0]).map(([k, v]) => (
          <div key={k} style={{ background: "#F3F4F6", borderRadius: 8, padding: "12px 16px", minWidth: 120, textAlign: "center" }}>
            <div style={{ fontSize: 11, color: "#6B7280", marginBottom: 4 }}>{k}</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: "#111827" }}>{formaterValeur(v)}</div>
          </div>
        ))}
      </div>
    );
  }
  if (type === "pie" && cleCateg) {
    const pieData = data.slice(0, 8).map(row => ({
      name: String(row[cleCateg] || "").slice(0, 20),
      value: Number(row[cleNum] || Object.values(row).find(v => typeof v === "number") || 1),
    }));
    return (
      <PieChart width={500} height={240}>
        <Pie isAnimationActive={false} data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={({name}) => name.slice(0,14)}>
          {pieData.map((_, i) => <Cell key={i} fill={COULEURS[i % COULEURS.length]} />)}
        </Pie>
        <Tooltip {...tooltipStyle} />
      </PieChart>
    );
  }
  if (type === "line" && cleNum) {
    // Séries « annee / mois » des bases connectées : axe 2025-01, 2025-02…
    if (colonnes.includes("annee") && colonnes.includes("mois")) {
      data = data.map(l => ({ ...l, periode: `${l.annee}-${String(l.mois).padStart(2, "0")}` }));
    }
    const cleDateKey = data[0]?.periode ? "periode" : colonnes.find(c => c.toLowerCase().includes("date") || c.toLowerCase().includes("mois"));
    return (
      <LineChart width={540} height={240} data={data.slice(0, 50)}>
        <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
        <XAxis dataKey={cleDateKey} tick={axisStyle} tickFormatter={v => String(v).slice(0, 10)} />
        <YAxis tick={axisStyle} tickFormatter={formaterValeur} />
        <Tooltip {...tooltipStyle} formatter={formaterValeur} />
        <Line isAnimationActive={false} type="monotone" dataKey={cleNum} stroke="#1F654D" strokeWidth={2} dot={false} />
      </LineChart>
    );
  }
  if (type === "area" && cleNum && cleCateg) {
    return (
      <AreaChart width={540} height={240} data={data.slice(0, 50)}>
        <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
        <XAxis dataKey={cleCateg} tick={axisStyle} />
        <YAxis tick={axisStyle} tickFormatter={formaterValeur} />
        <Tooltip {...tooltipStyle} formatter={formaterValeur} />
        <Area isAnimationActive={false} type="monotone" dataKey={cleNum} stroke="#1F654D" fill="#D5E7E0" strokeWidth={2} />
      </AreaChart>
    );
  }
  if (type === "bar" && cleNum && cleCateg) {
    return (
      <BarChart width={540} height={Math.max(160, Math.min(data.length, 15) * 24 + 40)} data={data.slice(0, 15)} layout="vertical">
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E9EDEB" />
        <XAxis type="number" tick={axisStyle} tickFormatter={formaterValeur} />
        <YAxis type="category" dataKey={cleCateg} tick={axisStyle} width={150} interval={0} tickFormatter={v => String(v).slice(0, 24)} />
        <Tooltip {...tooltipStyle} formatter={formaterValeur} />
        <Bar isAnimationActive={false} dataKey={cleNum} radius={[0,4,4,0]} barSize={14}>
          {data.slice(0,15).map((_, i) => <Cell key={i} fill={i === 0 ? "#C9A13B" : "#1F654D"} />)}
        </Bar>
      </BarChart>
    );
  }
  // Tableau
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
      <thead>
        <tr style={{ background: "#F3F4F6" }}>
          {colonnes.slice(0, 7).map(c => (
            <th key={c} style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600, color: "#374151", borderBottom: "1px solid #E5E7EB" }}>{libelleColonne(c, item)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.slice(0, 20).map((row, i) => (
          <tr key={i} style={{ borderBottom: "1px solid #F3F4F6", background: i % 2 === 0 ? "#fff" : "#F9FAFB" }}>
            {colonnes.slice(0, 7).map(c => (
              <td key={c} style={{ padding: "5px 10px", color: "#1F2937" }}>{String(row[c] ?? "").slice(0, 28)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ════════════════════════════════════════
// COMPOSANT — CARTE RÉSULTAT
// ════════════════════════════════════════

function CarteResultat({ item, dark, onSupprimer, role }) {
  const lectureSeule = useLectureSeule();
  const [ouvert, setOuvert] = useState(true);
  const [action, setAction] = useState(null);   // "signaler" | "corriger"
  const discret = `text-xs ${dark ? "text-gray-400" : "text-gray-500"}`;

  return (
    <div className={`rounded-2xl border mb-4 overflow-hidden transition-all ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
      <div
        className={`flex items-center justify-between px-5 py-3 cursor-pointer ${dark ? "hover:bg-gray-700" : "hover:bg-gray-50"}`}
        onClick={() => setOuvert(!ouvert)}
      >
        <div className="flex-1 min-w-0">
          {item.suite && item.question_precedente && (
            <p className={`flex items-center gap-1 text-xs truncate ${dark ? "text-foret-300" : "text-foret-700"}`}><CornerDownRight size={12} />{" "}{tx("suite de « {question_precedente} »", { question_precedente: item.question_precedente })}</p>
          )}
          {(item.nom_source || (item.devise && item.devise !== "XAF" && item.colonnes_monetaires?.length > 0)) && (
            <p className={`text-xs truncate ${dark ? "text-laiton-300" : "text-laiton-600"}`}>
              {[item.nom_source && tx("Base : {nom_source}", { nom_source: item.nom_source }),
                item.devise && item.colonnes_monetaires?.length > 0 && tx("Montants en {devise}", { devise: item.devise === "XAF" || item.devise === "XOF" ? "FCFA" : item.devise })]
                .filter(Boolean).join(" · ")}
            </p>
          )}
          <p className={`text-sm font-medium truncate ${dark ? "text-white" : "text-gray-900"}`}>{item.question}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className={discret}>{tx("{total} résultats · {duree_ms}ms", { total: item.total, duree_ms: item.duree_ms })}</span>
            <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${(SOURCES[item.source] || SOURCES.gemini).classe}`}>
              {item.source === "rag" ? <BookCheck size={11} /> : item.source === "rule" ? <Zap size={11} /> : <Sparkles size={11} />}
              {(SOURCES[item.source] || SOURCES.gemini).label}
            </span>
            <span className={`text-xs ${dark ? "text-gray-500" : "text-gray-400"}`}>{new Date(item.timestamp).toLocaleTimeString(LOCALE)}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 ml-3">
          {item.data && item.data.length > 0 && (
            <button onClick={e => { e.stopPropagation(); telechargerCsv(nomFichier(item.question, "csv"), item.colonnes, item.data); }}
              aria-label={tx("Exporter en CSV (Excel)")} title={item.total > item.data.length
                ? tx("Exporter en CSV (Excel) — {length} premières lignes", { length: item.data.length }) : tx("Exporter en CSV (Excel)")}
              className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs ${dark ? "hover:bg-gray-600 text-gray-300" : "hover:bg-gray-100 text-gray-500"}`}>
              <Download size={13} />{" "}{tx("CSV")}
            </button>
          )}
          <button onClick={e => { e.stopPropagation(); onSupprimer(item.id); }} aria-label={tx("Supprimer ce résultat")}
            className={`p-1.5 rounded-lg ${dark ? "hover:bg-gray-600 text-gray-400" : "hover:bg-gray-100 text-gray-400"}`}>
            <Trash2 size={13} />
          </button>
          {ouvert ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>
      {item.resume && (
        <div className={`mx-5 mb-3 flex items-start gap-2 p-3 rounded-xl border-l-4 border-laiton-400 ${dark ? "bg-foret-900/50 text-foret-50" : "bg-foret-50 text-foret-900"}`}>
          <p className="text-sm flex-1">{item.resume}</p>
          <button onClick={() => lireAVoixHaute([item.resume, item.commentaire])} aria-label={tx("Lire la réponse et l'analyse à voix haute")}
            title={item.commentaire ? tx("Écouter la réponse et l'analyse") : tx("Écouter")}
            className={`p-1.5 rounded-lg flex-shrink-0 ${dark ? "hover:bg-foret-800/40" : "hover:bg-foret-100"}`}>
            <Volume2 size={15} />
          </button>
        </div>
      )}
      {item.avertissement && (
        <div className="mx-5 mb-3 flex items-start gap-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-500 text-xs">
          <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
          <span>{item.avertissement}</span>
        </div>
      )}
      {ouvert && item.data && item.data.length > 0 && (
        <div className="px-5 pb-3">
          <code className={`text-xs block mb-3 truncate ${dark ? "text-foret-300" : "text-foret-600"}`}>{item.sql}</code>
          <GraphiqueDynamique colonnes={item.colonnes} data={item.data} question={item.question} dark={dark} sql={item.sql} item={item} />
        </div>
      )}
      {ouvert && (!item.data || item.data.length === 0) && (
        <div className={`px-5 pb-3 text-sm ${dark ? "text-gray-400" : "text-gray-500"}`}>{tx("Aucun résultat trouvé pour cette question.")}</div>
      )}
      {ouvert && !item.nom_source && (
        <div className="px-5 pb-4">
          <div className="flex flex-wrap gap-3">
            <button onClick={() => setAction(action === "signaler" ? null : "signaler")} disabled={lectureSeule}
              title={lectureSeule ? TITRE_LECTURE_SEULE : undefined}
              className={`flex items-center gap-1 text-xs hover:underline disabled:opacity-50 disabled:no-underline ${dark ? "text-gray-400" : "text-gray-500"}`}>
              <Flag size={12} />{" "}{tx("Réponse incorrecte ?")}
            </button>
            {role === "admin" && (
              <button onClick={() => setAction(action === "corriger" ? null : "corriger")}
                className={`flex items-center gap-1 text-xs hover:underline ${dark ? "text-foret-300" : "text-foret-600"}`}>
                <Wrench size={12} />{" "}{tx("Corriger la requête")}
              </button>
            )}
          </div>
          {action === "signaler" && <FormulaireSignalement item={item} dark={dark} onFermer={() => setAction(null)} />}
          {action === "corriger" && <EditeurCorrection question={item.question} sql={item.sql} dark={dark} />}
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════
// COMPOSANT — ONGLET HISTORIQUE
// ════════════════════════════════════════

function PanelHistorique({ historique, dark, onSupprimerItem, onToutEffacer }) {
  const [selection, setSelection]       = useState(new Set());
  const [generationPDF, setGenerationPDF] = useState(false);
  const [recherche, setRecherche]       = useState("");
  const chartRefs = useRef({});

  const historiqueFiltre = historique.filter(item =>
    item.question.toLowerCase().includes(recherche.toLowerCase())
  );

  const basculer = (id) => {
    setSelection(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const basculerTous = () => {
    if (selection.size === historiqueFiltre.length) {
      setSelection(new Set());
    } else {
      setSelection(new Set(historiqueFiltre.map(i => i.id)));
    }
  };

  // ── Génération PDF avec capture des graphiques ──────
  const genererPDF = async () => {
    if (selection.size === 0) return;
    setGenerationPDF(true);

    try {
      const { jsPDF } = await import("jspdf");
      const html2canvas = (await import("html2canvas")).default;

      const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
      const selectedItems = historique.filter(item => selection.has(item.id));
      const now = new Date();
      const pageW  = pdf.internal.pageSize.getWidth();
      const pageH  = pdf.internal.pageSize.getHeight();
      const margin = 14;
      const cW     = pageW - margin * 2;

      // ── En-tête ──────────────────────────────────────
      // Bande bleue
      pdf.setFillColor(14, 51, 45);
      pdf.rect(0, 0, pageW, 32, "F");

      pdf.setTextColor(255, 255, 255);
      pdf.setFontSize(16);
      pdf.setFont("helvetica", "bold");
      pdf.text(tx("VoiceBank Analytics"), margin, 13);

      pdf.setFontSize(9);
      pdf.setFont("helvetica", "normal");
      pdf.text(tx("Rapport d'historique des requêtes"), margin, 20);
      pdf.text(tx("Généré le {date} à {heure}", { date: now.toLocaleDateString(LOCALE), heure: now.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" }) }), margin, 27);

      // Compteur à droite
      pdf.setFontSize(9);
      pdf.text(tx(selection.size > 1 ? "{n} entrées" : "{n} entrée", { n: selection.size }), pageW - margin, 20, { align: "right" });

      let y = 42;

      for (let idx = 0; idx < selectedItems.length; idx++) {
        const item = selectedItems[idx];

        // ── Nouvelle page si nécessaire ──
        if (y > pageH - 70) { pdf.addPage(); y = 18; }

        // ── Numéro + fond de section ──
        pdf.setFillColor(241, 245, 249);
        pdf.roundedRect(margin, y, cW, 10, 2, 2, "F");

        pdf.setTextColor(31, 101, 77);
        pdf.setFontSize(8);
        pdf.setFont("helvetica", "bold");
        pdf.text(`# ${idx + 1}`, margin + 3, y + 7);

        pdf.setTextColor(17, 24, 39);
        pdf.setFontSize(10);
        const lignesQ = pdf.splitTextToSize(item.question, cW - 16);
        pdf.text(lignesQ, margin + 10, y + 7);
        y += 10 + (lignesQ.length - 1) * 5 + 4;

        // ── Métadonnées ──
        const dateStr = new Date(item.timestamp).toLocaleString(LOCALE);
        pdf.setFontSize(8);
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(107, 114, 128);
        pdf.text(tx("Date : {dateStr}", { dateStr }), margin, y);
        pdf.text(tx("Durée : {duree_ms} ms", { duree_ms: item.duree_ms }), margin + 55, y);

        const sourceBadge = item.source === "rag" ? "RAG" : item.source === "rule" ? tx("Règle") : "Gemini";
        pdf.setTextColor(255, 255, 255);
        const badgeColor = item.source === "rag" ? [16, 185, 129] : item.source === "rule" ? [245, 158, 11] : [59, 130, 246];
        pdf.setFillColor(...badgeColor);
        pdf.roundedRect(margin + 78, y - 4, 18, 6, 1, 1, "F");
        pdf.setFontSize(7);
        pdf.text(sourceBadge, margin + 87, y, { align: "center" });
        y += 7;

        // ── Résumé ──
        if (item.resume) {
          pdf.setFont("helvetica", "italic");
          pdf.setFontSize(8.5);
          pdf.setTextColor(31, 101, 77);
          const lignesResume = pdf.splitTextToSize(item.resume, cW);
          pdf.text(lignesResume, margin, y);
          y += lignesResume.length * 4 + 2;
        }

        // ── Requête SQL ──
        if (y > pageH - 50) { pdf.addPage(); y = 18; }
        pdf.setTextColor(59, 130, 246);
        pdf.setFontSize(7.5);
        pdf.setFont("helvetica", "bold");
        pdf.text(tx("Requête SQL :"), margin, y);
        y += 4;

        pdf.setFont("courier", "normal");
        pdf.setFontSize(7);
        pdf.setTextColor(55, 65, 81);
        const lignesSQL = pdf.splitTextToSize(item.sql || "", cW);
        const maxLignesSQL = Math.min(lignesSQL.length, 4);
        pdf.text(lignesSQL.slice(0, maxLignesSQL), margin, y);
        y += maxLignesSQL * 3.5 + 3;

        // ── Compteur résultats ──
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(8);
        pdf.setTextColor(17, 24, 39);
        pdf.text(tx("Résultats : {lignes} ligne(s)  ·  {colonnes} colonne(s)", { lignes: item.total, colonnes: item.colonnes?.length || 0 }), margin, y);
        y += 6;

        // ── Capture du graphique ──
        const chartEl = chartRefs.current[item.id];
        if (chartEl && item.data && item.data.length > 0) {
          try {
            if (y > pageH - 75) { pdf.addPage(); y = 18; }

            pdf.setFont("helvetica", "bold");
            pdf.setFontSize(8);
            pdf.setTextColor(59, 130, 246);
            pdf.text(tx("Visualisation :"), margin, y);
            y += 4;

            const canvas = await html2canvas(chartEl, {
              scale: 2,
              backgroundColor: "#ffffff",
              logging: false,
              useCORS: true,
            });

            const imgData = canvas.toDataURL("image/png");
            const maxImgH = 65;
            const imgW = cW;
            const imgH = Math.min((canvas.height * imgW) / canvas.width, maxImgH);

            if (y + imgH > pageH - 15) { pdf.addPage(); y = 18; }

            // Cadre léger autour de l'image
            pdf.setDrawColor(229, 231, 235);
            pdf.setLineWidth(0.3);
            pdf.roundedRect(margin, y, imgW, imgH, 2, 2);
            pdf.addImage(imgData, "PNG", margin, y, imgW, imgH);
            y += imgH + 5;
          } catch (e) {
            // Fallback tableau texte si html2canvas échoue
            pdf.setFont("helvetica", "italic");
            pdf.setFontSize(7.5);
            pdf.setTextColor(156, 163, 175);
            pdf.text(tx("[Aperçu graphique indisponible — données tabulaires ci-dessous]"), margin, y);
            y += 5;
          }
        }

        // ── Aperçu données (tableau texte, max 5 lignes) ──
        if (item.data && item.data.length > 0 && item.colonnes?.length > 0) {
          if (y > pageH - 30) { pdf.addPage(); y = 18; }

          const previewRows = item.data.slice(0, 5);
          const cols = item.colonnes.slice(0, 5);
          const colW = cW / cols.length;

          pdf.setFont("helvetica", "bold");
          pdf.setFontSize(7);
          pdf.setTextColor(255, 255, 255);
          pdf.setFillColor(51, 65, 85);
          pdf.rect(margin, y, cW, 5.5, "F");
          const yEntete = y;
          cols.forEach((c, ci) => pdf.text(String(c).slice(0, 16), margin + ci * colW + 2, yEntete + 4));
          y += 5.5;

          for (let ri = 0; ri < previewRows.length; ri++) {
            if (y > pageH - 12) break;
            const row = previewRows[ri];
            const yLigne = y;
            pdf.setFillColor(ri % 2 === 0 ? 249 : 243, ri % 2 === 0 ? 250 : 244, ri % 2 === 0 ? 251 : 246);
            pdf.rect(margin, yLigne, cW, 5, "F");
            pdf.setTextColor(31, 41, 55);
            pdf.setFont("helvetica", "normal");
            cols.forEach((c, ci) => pdf.text(String(row[c] ?? "").slice(0, 16), margin + ci * colW + 2, yLigne + 3.8));
            y += 5;
          }
          if (item.total > 5) {
            pdf.setFontSize(7);
            pdf.setTextColor(156, 163, 175);
            pdf.setFont("helvetica", "italic");
            pdf.text(tx("… et {n} ligne(s) supplémentaire(s)", { n: item.total - 5 }), margin, y + 4);
            y += 8;
          } else {
            y += 3;
          }
        }

        // ── Séparateur ──
        pdf.setDrawColor(226, 232, 240);
        pdf.setLineWidth(0.4);
        pdf.line(margin, y + 3, pageW - margin, y + 3);
        y += 10;
      }

      // ── Pied de page ──────────────────────────────────
      const totalPages = pdf.internal.getNumberOfPages();
      for (let p = 1; p <= totalPages; p++) {
        pdf.setPage(p);
        pdf.setFillColor(241, 245, 249);
        pdf.rect(0, pageH - 10, pageW, 10, "F");
        pdf.setFontSize(7);
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(100, 116, 139);
        pdf.text(tx("VoiceBank Analytics — Rapport confidentiel"), margin, pageH - 4);
        pdf.text(tx("Page {p} / {totalPages}", { p, totalPages }), pageW - margin, pageH - 4, { align: "right" });
      }

      const nomFichier = tx("VoiceBank_Rapport_{x}_{x2}h{x3}.pdf", { x: now.toISOString().slice(0, 10), x2: now.getHours(), x3: now.getMinutes() });
      pdf.save(nomFichier);
    } catch (err) {
      console.error("Erreur PDF :", err);
      alert(tx("Erreur lors de la génération du PDF."));
    } finally {
      setGenerationPDF(false);
    }
  };

  const toutSelectionne = historiqueFiltre.length > 0 && selection.size === historiqueFiltre.length;
  const partielSelection = selection.size > 0 && selection.size < historiqueFiltre.length;

  return (
    <div>
      {/* Conteneurs graphiques cachés pour capture PDF */}
      <div style={{ position: "fixed", left: "-9999px", top: 0, pointerEvents: "none", zIndex: -1 }}>
        {historique.filter(item => selection.has(item.id) && item.data?.length > 0).map(item => (
          <div
            key={item.id}
            ref={el => { if (el) chartRefs.current[item.id] = el; }}
            style={{ width: 560, background: "#ffffff", padding: 16, fontFamily: "sans-serif" }}
          >
            <GraphiquePourPDF colonnes={item.colonnes} data={item.data} sql={item.sql} item={item} />
          </div>
        ))}
      </div>

      {/* ── Barre d'outils ─────────────────────────────── */}
      <div className={`rounded-2xl border p-5 mb-4 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={basculerTous}
              className={`flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-all ${
                dark ? "bg-gray-700 hover:bg-gray-600 text-gray-200" : "bg-gray-100 hover:bg-gray-200 text-gray-700"
              }`}
            >
              {toutSelectionne
                ? <CheckSquare size={15} className="text-foret-500" />
                : partielSelection
                ? <CheckSquare size={15} className="text-foret-400 opacity-60" />
                : <Square size={15} />
              }
              {toutSelectionne ? tx("Désélectionner tout") : tx("Tout sélectionner")}
            </button>

            {selection.size > 0 && (
              <span className={`text-sm font-medium px-3 py-1.5 rounded-xl ${dark ? "bg-foret-900/40 text-foret-300" : "bg-foret-50 text-foret-700"}`}>
                {tx("{size} sélectionné", { size: selection.size })}{selection.size > 1 ? "s" : ""}
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Recherche */}
            <input
              value={recherche}
              onChange={e => setRecherche(e.target.value)}
              placeholder={tx("Rechercher...")}
              className={`text-sm px-3 py-2 rounded-xl border outline-none transition-all w-full sm:w-48 ${
                dark ? "bg-gray-700 border-gray-600 text-white placeholder-gray-500 focus:border-foret-500" : "bg-gray-50 border-gray-200 text-gray-900 focus:border-foret-400"
              }`}
            />

            {/* Effacer tout */}
            <button
              onClick={onToutEffacer}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm transition-all ${dark ? "text-red-400 hover:bg-red-900/20" : "text-red-500 hover:bg-red-50"}`}
            >
              <Trash2 size={14} />{" "}{tx("Vider")}
            </button>

            {/* Télécharger PDF */}
            <button
              onClick={genererPDF}
              disabled={selection.size === 0 || generationPDF}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all shadow-md ${
                selection.size === 0 || generationPDF
                  ? "opacity-40 cursor-not-allowed bg-gray-400 text-white"
                  : "bg-foret-600 hover:bg-foret-700 active:scale-95 text-white shadow-foret-500/30"
              }`}
            >
              {generationPDF
                ? <><RefreshCw size={14} className="animate-spin" />{" "}{tx("Génération…")}</>
                : <><Download size={14} />{" "}{tx("Rapport PDF")}{" "}{selection.size > 0 ? `(${selection.size})` : ""}</>
              }
            </button>
          </div>
        </div>
      </div>

      {/* ── Liste historique ───────────────────────────── */}
      {historiqueFiltre.length === 0 ? (
        <div className={`rounded-2xl border p-16 text-center ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
          <History size={40} className={`mx-auto mb-3 opacity-20 ${dark ? "text-gray-400" : "text-gray-500"}`} />
          <p className={`text-sm ${dark ? "text-gray-500" : "text-gray-400"}`}>
            {recherche ? tx("Aucune requête ne correspond à votre recherche") : tx("Aucun historique pour le moment")}
          </p>
          <p className={`text-xs mt-1 ${dark ? "text-gray-600" : "text-gray-300"}`}>
            {!recherche && tx("Posez une question pour commencer")}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {historiqueFiltre.map((item) => {
            const date    = new Date(item.timestamp);
            const dateStr = date.toLocaleDateString(LOCALE, { day: "2-digit", month: "short", year: "numeric" });
            const heurStr = date.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
            const sel     = selection.has(item.id);
            const type    = detecterTypeGraphique(item.colonnes || [], item.data || []);

            const IconeType = { bar: ChartColumn, line: ChartLine, pie: ChartPie, area: ChartArea, kpi: Gauge }[type] || Table2;

            return (
              <div
                key={item.id}
                onClick={() => basculer(item.id)}
                className={`group rounded-2xl border cursor-pointer transition-all duration-200 ${
                  sel
                    ? dark
                      ? "border-foret-500 bg-foret-900/20 shadow-lg shadow-foret-900/20"
                      : "border-foret-400 bg-foret-50 shadow-lg shadow-foret-100"
                    : dark
                      ? "border-gray-700 bg-gray-800 hover:border-gray-600 hover:bg-gray-750"
                      : "border-gray-200 bg-white hover:border-gray-300 hover:shadow-md"
                }`}
              >
                <div className="flex items-start gap-4 p-4">
                  {/* Checkbox */}
                  <div className={`mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 transition-all ${
                    sel
                      ? "bg-foret-600 border-foret-600"
                      : dark ? "border-gray-600 bg-gray-700" : "border-gray-300 bg-white"
                  }`}>
                    {sel && (
                      <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                        <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </div>

                  {/* Contenu principal */}
                  <div className="flex-1 min-w-0">
                    {/* Ligne 1 : Question */}
                    <div className="flex items-center gap-2 mb-1.5">
                      <IconeType size={16} strokeWidth={1.75} className={`flex-shrink-0 ${dark ? "text-gray-400" : "text-gray-500"}`} aria-hidden="true" />
                      <p className={`font-semibold text-sm leading-snug truncate flex-1 ${dark ? "text-white" : "text-gray-900"}`}>
                        {item.question}
                      </p>
                    </div>

                    {/* Ligne 2 : Métadonnées */}
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-2">
                      <span className={`flex items-center gap-1 text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
                        <Calendar size={12} aria-hidden="true" /> {dateStr}
                      </span>
                      <span className={`flex items-center gap-1 text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
                        <Clock size={12} aria-hidden="true" /> {heurStr}
                      </span>
                      <span className={`flex items-center gap-1 text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
                        <Timer size={12} aria-hidden="true" /> {tx("{duree_ms} ms", { duree_ms: item.duree_ms })}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        item.source === "rag"
                          ? dark ? "bg-emerald-900/40 text-emerald-400" : "bg-emerald-100 text-emerald-700"
                          : item.source === "rule"
                          ? dark ? "bg-amber-900/40 text-amber-400" : "bg-amber-100 text-amber-700"
                          : dark ? "bg-foret-900/40 text-foret-400" : "bg-foret-100 text-foret-700"
                      }`}>
                        <span className="inline-flex items-center gap-1">
                          {item.source === "rag" ? <><BookCheck size={11} />{" "}{tx("RAG")}</> : item.source === "rule" ? <><Zap size={11} />{" "}{tx("Règle")}</> : <><Sparkles size={11} />{" "}{tx("Gemini")}</>}
                        </span>
                      </span>
                    </div>

                    {/* Ligne 3 : SQL tronqué */}
                    <p className={`text-xs font-mono truncate ${dark ? "text-gray-500" : "text-gray-400"}`}>
                      {(item.sql || "").slice(0, 110)}{(item.sql || "").length > 110 ? "…" : ""}
                    </p>

                    {/* Ligne 4 : Stats résultats */}
                    <div className="flex items-center gap-3 mt-1.5">
                      <span className={`flex items-center gap-1 text-xs font-medium ${dark ? "text-gray-300" : "text-gray-600"}`}>
                        <FileText size={11} />
                        {tx("{total} ligne", { total: item.total })}{item.total !== 1 ? "s" : ""}
                      </span>
                      <span className={`text-xs ${dark ? "text-gray-500" : "text-gray-400"}`}>
                        {tx("{x} colonne", { x: item.colonnes?.length || 0 })}{(item.colonnes?.length || 0) !== 1 ? "s" : ""}
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${dark ? "bg-gray-700 text-gray-400" : "bg-gray-100 text-gray-500"}`}>
                        {type.toUpperCase()}
                      </span>
                    </div>
                  </div>

                  {/* Bouton supprimer */}
                  <button
                    onClick={e => { e.stopPropagation(); onSupprimerItem(item.id); }}
                    className={`opacity-0 group-hover:opacity-100 p-2 rounded-xl transition-all flex-shrink-0 ${dark ? "hover:bg-red-900/30 text-gray-500 hover:text-red-400" : "hover:bg-red-50 text-gray-400 hover:text-red-500"}`}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Info bas de page ────────────────────────────── */}
      {historiqueFiltre.length > 0 && (
        <div className={`mt-4 p-3 rounded-xl text-xs flex items-center gap-2 ${dark ? "bg-gray-800/50 text-gray-500 border border-gray-700" : "bg-gray-50 text-gray-400 border border-gray-200"}`}>
          <Download size={12} className="flex-shrink-0" />
          <p>{tx("Sélectionne les requêtes à inclure, puis clique sur")}{" "}<strong>{tx("Rapport PDF")}</strong>{tx(". Le PDF contient la question, le résumé, la requête SQL, la date et le graphique ou le tableau.")}</p>
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════
// COMPOSANT — BOUTON MICRO
// ════════════════════════════════════════

// Dictée en direct : reconnaissance vocale du navigateur (Chrome, Edge, Safari) pour afficher
// le texte pendant qu'on parle. Le texte définitif vient ensuite de Whisper (Groq ou local),
// plus fiable. Sur Firefox (pas de reconnaissance native), le texte arrive à la fin.
const ReconnaissanceVocale = typeof window !== "undefined"
  ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
const DUREE_MAX_ENREGISTREMENT_MS = 12000;

function BoutonMicro({ onDebut, onTexteEnDirect, onTranscription, onErreur, dark }) {
  const [statut, setStatut] = useState("idle");
  const mediaRecRef         = useRef(null);
  const chunksRef           = useRef([]);
  const timerRef            = useRef(null);
  const reconnaissanceRef   = useRef(null);
  const texteDirectRef      = useRef("");

  const arreter = useCallback(() => {
    clearTimeout(timerRef.current);
    try { reconnaissanceRef.current?.stop(); } catch (e) { /* déjà arrêtée */ }
    if (mediaRecRef.current?.state === "recording") mediaRecRef.current.stop();
  }, []);

  const demarrerDicteeDirecte = () => {
    texteDirectRef.current = "";
    if (!ReconnaissanceVocale) return;
    try {
      const rec = new ReconnaissanceVocale();
      rec.lang = LOCALE_VOIX;
      rec.interimResults = true;
      rec.continuous = true;
      rec.onresult = (e) => {
        let texte = "";
        for (let i = 0; i < e.results.length; i++) texte += e.results[i][0].transcript;
        texteDirectRef.current = texte.trim();
        onTexteEnDirect(texteDirectRef.current);
      };
      rec.onerror = () => { /* aperçu seulement : Whisper prendra le relais */ };
      rec.start();
      reconnaissanceRef.current = rec;
    } catch (e) {
      reconnaissanceRef.current = null;
    }
  };

  const demarrer = async () => {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      onErreur(tx("Microphone inaccessible. Autorise le micro dans ton navigateur."));
      return;
    }
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm"
      : MediaRecorder.isTypeSupported("audio/ogg") ? "audio/ogg" : "audio/mp4";
    const extension = mimeType.includes("webm") ? "webm" : mimeType.includes("ogg") ? "ogg" : "mp4";

    const recorder = new MediaRecorder(stream, { mimeType });
    chunksRef.current = [];
    recorder.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      setStatut("processing");
      const formData = new FormData();
      formData.append("fichier", new Blob(chunksRef.current, { type: mimeType }), `audio.${extension}`);
      const texteDirect = texteDirectRef.current;
      try {
        // Délai long : le Whisper local peut devoir charger son modèle à la 1re utilisation
        const res = await http.post("/vocal/transcrire", formData, { timeout: 120000 });
        if (res.data?.texte?.trim()) onTranscription(res.data.texte.trim());
        else if (texteDirect) onTranscription(texteDirect);
        else onErreur(tx("Aucun texte détecté. Parle plus fort ou plus clairement."));
      } catch (e) {
        if (texteDirect) {
          onTranscription(texteDirect);
          onErreur(tx("Transcription serveur impossible ({x}) : texte du navigateur conservé, vérifie-le avant d'envoyer.", { x: messageErreur(e) }));
        } else {
          onErreur(tx("Transcription impossible : {x}", { x: messageErreur(e) }));
        }
      }
      setStatut("idle");
    };
    recorder.start(100);
    mediaRecRef.current = recorder;
    setStatut("recording");
    onDebut();
    demarrerDicteeDirecte();
    timerRef.current = setTimeout(arreter, DUREE_MAX_ENREGISTREMENT_MS);
  };

  useEffect(() => () => {
    clearTimeout(timerRef.current);
    try { reconnaissanceRef.current?.abort(); } catch (e) { /* rien */ }
  }, []);

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        onClick={statut === "recording" ? arreter : demarrer}
        disabled={statut === "processing"}
        aria-label={statut === "recording" ? tx("Arrêter l'enregistrement") : tx("Poser une question à voix haute")}
        className={`relative w-16 h-16 rounded-full flex items-center justify-center transition-all shadow-lg disabled:opacity-60 ${
          statut === "recording" ? "bg-red-500 hover:bg-red-600 scale-110" : "bg-foret-600 hover:bg-foret-700"
        }`}
      >
        {statut === "recording" && <span className="absolute inset-0 rounded-full bg-red-400 animate-ping opacity-50" />}
        {statut === "processing" ? <RefreshCw size={22} className="text-white animate-spin" />
          : statut === "recording" ? <MicOff size={22} className="text-white" />
          : <Mic size={22} className="text-white" />}
      </button>
      <span className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
        {statut === "recording" ? tx("Parle… clique pour finir") : statut === "processing" ? tx("Finalisation…") : tx("Cliquer pour parler")}
      </span>
    </div>
  );
}

// ════════════════════════════════════════
// COMPOSANT — KPI CARD
// ════════════════════════════════════════

function KpiCard({ titre, valeur, icone: Icone, couleur, dark }) {
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

function PanelAnalyse({ dark }) {
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
function BarreSourceRisque({ dark, sourceActive, sourcesPretes, externe, onChoisir, onMesDonnees }) {
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

export default function App() {
  const [session, setSession] = useState(() => lireSession());

  useEffect(() => {
    const surDeconnexion = () => setSession(null);
    window.addEventListener("voicebank:deconnexion", surDeconnexion);
    return () => window.removeEventListener("voicebank:deconnexion", surDeconnexion);
  }, []);

  const seDeconnecter = useCallback(() => {
    arreterLecture();
    if (session) sessionStorage.removeItem(`${CLE_STORAGE}_${session.utilisateur}`);
    deconnexion();
    setSession(null);
  }, [session]);

  // Maintenance : page dédiée pour tous, sauf l'administrateur de la plateforme (qui peut se connecter)
  const maintenance = useMaintenance();
  const [accesAdmin, setAccesAdmin] = useState(false);
  const bloque = maintenance.active && session?.role !== "admin" && !(accesAdmin && !session);

  return (
    <FournisseurDevise>
      <BandeauReconnexion />
      {bloque ? <EcranMaintenance etat={maintenance} onAccesAdmin={session ? undefined : () => setAccesAdmin(true)} />
        : !session ? <EcranAccueil onConnecte={setSession} annonce={maintenance.annonce} />
        : session.doitChangerMdp
          ? <EcranMotDePasseProvisoire session={session} onTermine={setSession} onDeconnexion={seDeconnecter} />
        : session.doitConfigurer2fa
          ? <EcranDoubleAuthObligatoire session={session} onTermine={setSession} onDeconnexion={seDeconnecter} />
          : <Tableau key={session.utilisateur} session={session} onDeconnexion={seDeconnecter} onSession={setSession}
              maintenance={maintenance} />}
    </FournisseurDevise>
  );
}

function Tableau({ session, onDeconnexion, onSession, maintenance }) {
  const devise = useDevise();
  const { resteMs, rester } = useSessionActive({ session, onSession, onDeconnexion });
  const [fenetreMdp, setFenetreMdp] = useState(false);
  const [dark, setDark]             = useState(true);
  const [question, setQuestion]     = useState("");
  const [dictee, setDictee]         = useState(false);
  const champQuestionRef            = useRef(null);
  const [historique, setHistorique] = useState(() => chargerHistorique(session.utilisateur));
  const [dashboard, setDashboard]   = useState(null);
  const [onglet, setOnglet]         = useState("assistant");
  const [menuOuvert, setMenuOuvert] = useState(false);
  const [compteurs, setCompteurs]   = useState({ alertes: 0, signalements: 0 });
  const [stats, setStats]           = useState(null);
  const [message, setMessage]       = useState(null);
  const [info, setInfo]             = useState(null);
  const [parle, setParle]           = useState(false);
  // Source interrogée : null = base VoiceBank ; sinon une base / des fichiers de l'organisation
  const [sourceActive, setSourceActive] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("voicebank_source") || "null"); } catch (e) { return null; }
  });
  const [sourcesPretes, setSourcesPretes] = useState([]);
  const [ecoute, setEcoute]         = useState(null);        // null | "attente" | "parole" | "transcription"
  const [conversation, setConversation] = useState(() => {
    try { return localStorage.getItem("voicebank_conversation") !== "non"; } catch (e) { return true; }
  });
  const ecouteRef  = useRef(null);       // contrôle de l'écoute en cours (annuler)
  const poserRef   = useRef(null);       // dernière version de poserQuestion (contexte à jour)
  const ongletRef  = useRef("assistant");
  const [voix, setVoix]             = useState(() => {
    try { return localStorage.getItem("voicebank_voix") !== "non"; } catch (e) { return true; }
  });
  // Deux canaux séparés : le chargement du tableau de bord ne doit jamais bloquer une question.
  const { appeler } = useAPI();
  const { appeler: appelerQuestion, chargement, erreur } = useAPI();
  const estAdmin = session.role === "admin";
  const externe = session.role === "visiteur" || session.role === "client";
  // Administration de la plateforme : l'administrateur, et les visiteurs en essai (démonstration en lecture seule).
  // Les membres d'une organisation cliente ne voient que leur organisation.
  const voitAdmin = estAdmin || session.role === "visiteur";
  const [acces, setAcces] = useState(null);
  const rafraichirAcces = useCallback(() => {
    http.get("/auth/moi").then(r => setAcces(r.data.acces)).catch(() => {});
  }, []);
  useEffect(() => { rafraichirAcces(); }, [rafraichirAcces, session.role]);
  useEffect(() => {
    const surExpiration = () => rafraichirAcces();
    window.addEventListener("voicebank:acces-expire", surExpiration);
    return () => window.removeEventListener("voicebank:acces-expire", surExpiration);
  }, [rafraichirAcces]);

  // Retour de la page de paiement : ?paiement=<référence> → vérification par le serveur
  useEffect(() => {
    const ref = new URLSearchParams(window.location.search).get("paiement");
    if (!ref) return;
    let essais = 0, fini = false;
    const verifier = async () => {
      try {
        const { data } = await http.get(`/abonnement/verifier/${encodeURIComponent(ref)}`);
        if (data.statut === "paye") {
          fini = true;
          if (data.jeton) onSession(appliquerJeton(data.jeton));
          setInfo(tx("Paiement confirmé : abonnement {formule} actif jusqu'au {x}. Merci !", { formule: data.formule, x: new Date(data.abonnement_fin).toLocaleDateString(LOCALE) }));
          rafraichirAcces();
        } else if (data.statut === "en_attente" && ++essais < 10) {
          setInfo(tx("Paiement en cours de confirmation…"));
          setTimeout(verifier, 3000);
          return;
        } else {
          fini = true;
          setMessage(data.statut === "en_attente" ? tx("Paiement pas encore confirmé. Il s'activera automatiquement dès réception.")
            : tx("Le paiement n'a pas abouti. Tu peux réessayer depuis la page Abonnement."));
          if (data.statut === "en_attente") setInfo(null);
        }
      } catch (e) {
        fini = true;
        setMessage(messageErreur(e));
      }
      if (fini) window.history.replaceState(null, "", window.location.pathname);
    };
    verifier();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const arreterEcoute = useCallback(() => {
    ecouteRef.current?.annuler?.();
    ecouteRef.current = null;
    setEcoute(null);
  }, []);

  const basculerVoix = () => {
    setVoix(v => {
      try { localStorage.setItem("voicebank_voix", v ? "non" : "oui"); } catch (e) { /* rien */ }
      if (v) { arreterLecture(); arreterEcoute(); }
      return !v;
    });
  };

  const basculerConversation = () => {
    setConversation(c => {
      try { localStorage.setItem("voicebank_conversation", c ? "non" : "oui"); } catch (e) { /* rien */ }
      if (c) arreterEcoute();
      return !c;
    });
  };

  // Mode conversation : la relance (« Veux-tu voir… ? ») vient d'être lue, on écoute la réponse.
  const ecouterLaReponse = async (relance, essai = 1) => {
    if (ongletRef.current !== "assistant") return;
    const controle = {};
    ecouteRef.current = controle;
    setEcoute("attente");
    let texte = "";
    try {
      texte = await ecouterReponse({
        controle,
        onParole: () => setEcoute("parole"),
        onTexteEnDirect: t => setQuestion(t),
        onTranscription: () => setEcoute("transcription"),
      });
    } catch (e) {
      setMessage(e.message);
    }
    if (ecouteRef.current !== controle) return;     // écoute annulée entre-temps
    ecouteRef.current = null;
    setEcoute(null);
    const reponse = interpreterReponse(texte);
    if (reponse.type === "vide") { setQuestion(""); return; }
    if (reponse.type === "non") { setQuestion(""); lireAVoixHaute(tx("D'accord. Je reste à ta disposition.")); return; }
    if (reponse.type === "oui") {
      setQuestion("");
      if (relance?.question) poserRef.current(relance.question);
      else if (essai === 1) lireAVoixHaute(tx("Je t'écoute."), { onFin: () => ecouterLaReponse(null, 2) });
      return;
    }
    poserRef.current(reponse.texte);
  };

  useEffect(() => {
    const surLecture = e => setParle(!!e.detail);
    window.addEventListener("voicebank:lecture", surLecture);
    return () => { window.removeEventListener("voicebank:lecture", surLecture); arreterLecture(); };
  }, []);

  useEffect(() => {
    appeler("get", "/dashboard").then(res => { if (res?.data) setDashboard(res.data); });
    appeler("get", "/stats/global").then(res => { if (res?.data) setStats(res.data); });
  }, [appeler]);

  const allerA = useCallback(id => {
    setOnglet(id); ongletRef.current = id; window.scrollTo(0, 0);
    if (id !== "assistant") arreterEcoute();
  }, [arreterEcoute]);
  useEffect(() => () => ecouteRef.current?.annuler?.(), []);

  // Compteurs de la barre latérale : alertes à traiter, signalements en attente (admin)
  const rafraichirCompteurs = useCallback(() => {
    appeler("get", "/alertes/stats").then(r => r && setCompteurs(c => ({ ...c, alertes: Number(r.a_traiter) || 0 })));
    if (voitAdmin) appeler("get", "/signalements?statut=Ouvert&limit=200")
      .then(r => r && setCompteurs(c => ({ ...c, signalements: r.total || 0 })));
  }, [appeler, voitAdmin]);
  useEffect(() => { rafraichirCompteurs(); }, [rafraichirCompteurs]);

  useEffect(() => { sauverHistorique(session.utilisateur, historique); }, [historique, session.utilisateur]);
  useEffect(() => { if (erreur) setMessage(erreur); }, [erreur]);

  const poserQuestion = async (texte, sourceForcee) => {
    const q = (texte ?? question).trim();
    if (!q || chargement) return;
    const src = sourceForcee !== undefined ? sourceForcee : sourceActive;
    if (ecouteRef.current) arreterEcoute();
    setQuestion("");
    setMessage(null);
    // Contexte = dernière question (moins de 15 min) : permet « et à Douala ? ».
    // C'est l'API qui décide si la nouvelle question est une suite ou une question complète.
    const derniere = historique[0];
    const contexte = derniere && derniere.sql && Date.now() - new Date(derniere.timestamp).getTime() < 15 * 60 * 1000
      ? { question: derniere.question, sql: derniere.sql } : null;
    // Base de l'organisation (connecteur) ou base VoiceBank principale
    const res = src
      ? await appelerQuestion("post", `/sources/${src.id}/question`, { texte: q, devise: devise.code }, { timeout: 90000 })
      : await appelerQuestion("post", "/vocal/question", { texte: q, langue: LANGUE, devise: devise.code,
          contexte: contexte && !historique[0]?.nom_source ? contexte : null });
    if (!res) return;  // le message d'erreur est affiché via `erreur`
    if (externe) setAcces(a => a ? { ...a, questions_jour: a.questions_jour + 1 } : a);
    setHistorique(prev => [{
      id: Date.now(), timestamp: new Date().toISOString(),
      question: q, sql: res.sql, source: res.source,
      colonnes: res.colonnes, total: res.total,
      data: res.data, duree_ms: res.duree_ms, avertissement: res.avertissement || null,
      resume: res.resume || null, commentaire: res.commentaire || null, relance: res.relance || null,
      suite: !!res.suite, question_precedente: res.question_precedente || null, nom_source: src ? src.nom : null,
      devise: res.devise || "XAF", colonnes_monetaires: res.colonnes_monetaires || [],
    }, ...prev].slice(0, MAX_HISTORIQUE));
    // Le résumé (affiché) est lu en premier, puis l'analyse plus poussée et la relance
    // (uniquement à l'oral). En mode conversation, on écoute ensuite la réponse, sans clic.
    if (voix && res.resume) {
      const relance = res.relance;
      lireAVoixHaute([res.resume, res.commentaire, relance?.texte], {
        onFin: conversation && relance ? () => ecouterLaReponse(relance) : undefined,
      });
    }
  };
  poserRef.current = poserQuestion;

  const choisirSource = useCallback(async (s, question, garderPage = false) => {
    let choix = null;
    if (s && !s.demo) {
      choix = { id: s.id, nom: s.nom, suggestions: s.profil?.suggestions || [] };
      if (!choix.suggestions.length) {
        try { choix.suggestions = (await http.get(`/sources/${s.id}`)).data.data.profil?.suggestions || []; } catch (e) { /* rien */ }
      }
    }
    setSourceActive(choix);
    try { sessionStorage.setItem("voicebank_source", JSON.stringify(choix)); } catch (e) { /* rien */ }
    if (!garderPage) { setOnglet("assistant"); ongletRef.current = "assistant"; window.scrollTo(0, 0); }
    if (question) setTimeout(() => poserRef.current(question, choix), 0);
  }, []);

  useEffect(() => {
    http.get("/sources").then(r => setSourcesPretes(r.data.data.filter(x => !x.demo && x.statut === "pret"))).catch(() => {});
  }, [onglet]);

  // Base par défaut de l'organisation : appliquée à l'arrivée, tant que la personne n'a rien choisi elle-même
  useEffect(() => {
    let dejaChoisi = false;
    try { dejaChoisi = sessionStorage.getItem("voicebank_source") !== null; } catch (e) { /* rien */ }
    if (!dejaChoisi && acces?.source_defaut) choisirSource(acces.source_defaut, null, true);
  }, [acces?.source_defaut?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const supprimerItem = (id) => setHistorique(prev => prev.filter(item => item.id !== id));
  const toutEffacer = () => {
    if (window.confirm(tx("Supprimer tout l'historique ?"))) setHistorique([]);
  };

  const tableauSource = useTableauSource(sourceActive, devise.code);
  const kpis = sourceActive ? kpisSource(tableauSource.donnees, devise) : dashboard ? [
    { titre: tx("Clients"),        valeur: Number(dashboard.total_clients || 0).toLocaleString(LOCALE),       icone: Users,       couleur: "#1F654D" },
    { titre: tx("Transactions"),   valeur: Number(dashboard.total_transactions || 0).toLocaleString(LOCALE),   icone: Activity,    couleur: "#3E6FB0" },
    { titre: tx("Fraudes"),        valeur: Number(dashboard.total_fraudes || 0).toLocaleString(LOCALE),        icone: ShieldAlert, couleur: "#EF4444" },
    { titre: tx("Crédits en cours"), valeur: Number(dashboard.encours_credit_fcfa || 0) > 0
        ? devise.formater(dashboard.encours_credit_fcfa, { compact: true }) : "--",
      icone: CreditCard, couleur: "#A9852A" },
  ] : [];

  const suggestions = sourceActive?.suggestions?.length ? sourceActive.suggestions.slice(0, 6) : [
    tx("Top 10 clients par solde"),
    tx("Crédits en défaut"),
    tx("Transactions frauduleuses par banque"),
    tx("Alertes critiques"),
    tx("Clients diaspora France"),
    tx("Volume transactions par ville"),
  ];

  const PAGES = {
    assistant:     { titre: tx("Assistant vocal"),        sousTitre: tx("Pose une question sur tes données, à la voix ou au clavier") },
    donnees:       { titre: tx("Mes données"),            sousTitre: tx("Brancher, diagnostiquer et interroger les données de ton organisation") },
    tableau:       { titre: tx("Tableau de bord"),         sousTitre: sourceActive ? tx("Vue d'ensemble de « {nom} », calculée d'après sa structure", { nom: sourceActive.nom })
                                                                       : tx("Vue d'ensemble des clients, des transactions et des crédits") },
    alertes:       { titre: tx("Alertes de fraude"),       sousTitre: sourceActive ? tx("Opérations atypiques de « {nom} »", { nom: sourceActive.nom }) : tx("Alertes à vérifier et décisions prises") },
    analyse:       { titre: tx("Analyse de transaction"),  sousTitre: tx("Estimer le risque de fraude d'une opération") },
    credit:        { titre: tx("Score de crédit"),         sousTitre: sourceActive ? tx("Portefeuille de crédits de « {nom} »", { nom: sourceActive.nom }) : tx("Risque de défaut d'une demande ou d'un crédit en cours") },
    historique:    { titre: tx("Historique"),              sousTitre: tx("Questions de la session et rapport PDF") },
    modeles:       { titre: tx("Fiche des modèles"),       sousTitre: sourceActive ? tx("Modèles d'IA appris sur « {nom} » : données, fiabilité, dérive", { nom: sourceActive.nom }) : tx("Modèles d'IA de la démonstration : données, fiabilité, limites") },
    journal:       { titre: tx("Journal de l'organisation"), sousTitre: tx("Traitement des alertes et activité des membres") },
    notifications: { titre: tx("Notifications"),           sousTitre: tx("Alertes, résumé du matin et rapports PDF reçus par e-mail") },
    apprentissage: { titre: tx("Apprentissage"),           sousTitre: tx("Réponses signalées et corrections enregistrées") },
    fiabilite:     { titre: tx("Fiabilité"),               sousTitre: tx("Taux de bonnes réponses sur les questions de référence") },
    audit:         { titre: tx("Audit"),                   sousTitre: tx("Qui a fait quoi, et quand") },
    comptes:       { titre: tx("Comptes"),                 sousTitre: tx("Qui peut se connecter, avec quels droits") },
    abonnement:    { titre: tx("Abonnement"),              sousTitre: tx("Formules, paiement et factures") },
    maintenance:   { titre: tx("Maintenance"),             sousTitre: tx("Mettre le service en maintenance et prévenir les utilisateurs") },
    organisation:  { titre: acces?.type_organisation === "particulier" ? tx("Mon compte") : tx("Mon organisation"),
                     sousTitre: acces?.organisation ? tx("{organisation} : membres et abonnement partagé", { organisation: acces.organisation }) : tx("Membres et abonnement partagé") },
    abonnements:   { titre: tx("Abonnements"),             sousTitre: tx("Visiteurs, abonnés et paiements reçus") },
  };
  // Essai ou abonnement échu : seule la page Abonnement reste accessible.
  const page = acces?.expire ? "abonnement" : PAGES[onglet] ? onglet : "assistant";

  return (
    <div className={`min-h-screen flex ${dark ? "bg-gray-950 text-gray-100" : "bg-gray-50 text-gray-900"}`}>
      <BarreLaterale
        page={page} allerA={allerA} estAdmin={estAdmin} voitAdmin={voitAdmin} externe={externe} session={session} acces={acces}
        nbHistorique={historique.length} compteurs={compteurs}
        ouverte={menuOuvert} onFermer={() => setMenuOuvert(false)} onDeconnexion={onDeconnexion}
        onMotDePasse={() => setFenetreMdp(true)}
      />
      {resteMs !== null && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4">
          <div role="alertdialog" aria-modal="true" aria-labelledby="titre-inactivite"
            className={`w-full max-w-sm rounded-2xl border p-6 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}>
            <h2 id="titre-inactivite" className="text-lg font-bold flex items-center gap-2 mb-2"><Timer size={18} />{" "}{tx("Toujours là ?")}</h2>
            <p className={`text-sm mb-4 ${dark ? "text-gray-300" : "text-gray-600"}`}>
              {tx("Sans activité, tu seras déconnecté dans")}{" "}<strong>{tx("{x} s", { x: Math.ceil(resteMs / 1000) })}</strong>{tx(", pour protéger les données des clients.")}
            </p>
            <div className="flex gap-2">
              <button onClick={rester} autoFocus className="px-4 py-2 bg-foret-600 hover:bg-foret-700 text-white text-sm font-semibold rounded-xl">{tx("Rester connecté")}</button>
              <button onClick={onDeconnexion} className={`px-4 py-2 rounded-xl text-sm ${dark ? "hover:bg-gray-700" : "hover:bg-gray-100"}`}>{tx("Se déconnecter")}</button>
            </div>
          </div>
        </div>
      )}
      {fenetreMdp && (
        <FenetreMotDePasse dark={dark} session={session} onTermine={onSession} onFermer={() => setFenetreMdp(false)} />
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        {/* ── Barre du haut ─────────────────────────────── */}
        <header className={`sticky top-0 z-20 border-b px-4 sm:px-8 py-3 flex items-center gap-3 backdrop-blur-md ${
          dark ? "bg-gray-950/85 border-gray-800" : "bg-gray-50/85 border-gray-200"}`}>
          <button onClick={() => setMenuOuvert(true)} aria-label={tx("Ouvrir le menu")}
            className={`lg:hidden p-2 rounded-lg ${dark ? "hover:bg-gray-800" : "hover:bg-gray-200"}`}>
            <Menu size={18} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold leading-tight truncate">{PAGES[page].titre}</h1>
            <p className={`text-xs truncate ${dark ? "text-gray-400" : "text-gray-500"}`}>{PAGES[page].sousTitre}</p>
          </div>
          {parle && (
            <button onClick={arreterLecture} aria-label={tx("Arrêter la lecture")} title={tx("Arrêter la lecture")}
              className={`flex items-center gap-2 pl-2.5 pr-3 py-1.5 rounded-full text-xs font-medium ${
                dark ? "bg-laiton-400/15 text-laiton-300 hover:bg-laiton-400/25" : "bg-laiton-200/70 text-laiton-600 hover:bg-laiton-200"}`}>
              <span className="flex items-end gap-0.5 h-3" aria-hidden="true">
                {[0, 1, 2].map(i => <span key={i} className="w-0.5 bg-current rounded-full animate-pulse"
                  style={{ height: `${[60, 100, 70][i]}%`, animationDelay: `${i * 150}ms` }} />)}
              </span>
              <span className="hidden sm:inline">{tx("Lecture")}</span>
              <Square size={11} fill="currentColor" />
            </button>
          )}
          {ecoute && (
            <button onClick={arreterEcoute} aria-label={tx("Arrêter l'écoute")} title={tx("Arrêter l'écoute")}
              className="flex items-center gap-2 pl-2.5 pr-3 py-1.5 rounded-full text-xs font-medium bg-red-500/15 text-red-500 hover:bg-red-500/25">
              <span className="relative flex w-2 h-2" aria-hidden="true">
                <span className="absolute inset-0 rounded-full bg-red-500 animate-ping opacity-75" />
                <span className="relative w-2 h-2 rounded-full bg-red-500" />
              </span>
              <span>{ecoute === "transcription" ? tx("Je réfléchis…") : ecoute === "parole" ? tx("Je t'écoute…") : tx("À toi…")}</span>
              <Square size={11} fill="currentColor" />
            </button>
          )}
          <SelecteurDevise compact className={`text-xs px-2 py-1.5 rounded-lg border outline-none ${dark
            ? "bg-gray-900 border-gray-700 text-gray-200" : "bg-white border-gray-200 text-gray-700"}`} />
          {voix && (
            <button onClick={basculerConversation} aria-pressed={conversation}
              aria-label={conversation ? tx("Désactiver le mode conversation") : tx("Activer le mode conversation")}
              title={conversation ? tx("Mode conversation : je t'écoute après chaque réponse") : tx("Mode conversation désactivé")}
              className={`p-2 rounded-lg transition-colors ${conversation
                ? (dark ? "text-laiton-300 hover:bg-gray-800" : "text-laiton-600 hover:bg-gray-200")
                : (dark ? "text-gray-500 hover:bg-gray-800" : "text-gray-400 hover:bg-gray-200")}`}>
              <MessagesSquare size={17} />
            </button>
          )}
          <button onClick={basculerVoix} aria-label={voix ? tx("Désactiver la réponse vocale") : tx("Activer la réponse vocale")}
            title={voix ? tx("Réponse vocale activée") : tx("Réponse vocale désactivée")}
            className={`p-2 rounded-lg transition-colors ${dark ? "text-gray-300 hover:bg-gray-800" : "text-gray-600 hover:bg-gray-200"}`}>
            {voix ? <Volume2 size={17} /> : <VolumeX size={17} />}
          </button>
          <button onClick={() => setDark(!dark)} aria-label={tx("Changer de thème")} title={dark ? tx("Thème clair") : tx("Thème sombre")}
            className={`p-2 rounded-lg transition-colors ${dark ? "text-gray-300 hover:bg-gray-800" : "text-gray-600 hover:bg-gray-200"}`}>
            {dark ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </header>

        <LectureSeule.Provider value={externe}>
        <main className="w-full max-w-5xl mx-auto px-4 sm:px-8 py-6 flex-1">
          {maintenance?.active && estAdmin && (
            <div role="status" className="mb-4 px-4 py-3 rounded-xl border border-amber-500/50 bg-amber-500/10 text-amber-500 text-sm flex flex-wrap items-center gap-2">
              <strong>{tx("Maintenance en cours :")}</strong>{" "}{tx("les utilisateurs voient la page de maintenance, toi seul as accès.")}
              <button onClick={() => allerA("maintenance")} className="underline">{tx("Gérer")}</button>
            </div>
          )}
          <BandeauAnnonce annonce={maintenance?.annonce} sombre={dark} />
          {page !== "abonnement" && <BandeauAcces acces={acces} dark={dark} onChoisir={() => allerA("abonnement")} />}
          {info && (
            <div role="status" className="mb-4 flex items-start gap-2 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 text-sm">
              <span className="flex-1">{info}</span>
              <button onClick={() => setInfo(null)} aria-label={tx("Fermer")}><X size={14} /></button>
            </div>
          )}
          {message && (
            <div role="alert" className="mb-4 flex items-start gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-500 text-sm">
              <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" />
              <span className="flex-1">{message}</span>
              <button onClick={() => setMessage(null)} aria-label={tx("Fermer")}><X size={14} /></button>
            </div>
          )}

          {page === "assistant" && (
            <>
              {acces?.role_org === "admin" && acces?.type_organisation === "organisation" && (
                <Demarrage dark={dark} utilisateur={session.utilisateur} acces={acces} nbSources={sourcesPretes.length}
                  nbQuestions={historique.length} allerA={allerA} />
              )}
              {kpis.length > 0 && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
                  {kpis.map((k, i) => <KpiCard key={i} {...k} dark={dark} />)}
                </div>
              )}
              {/* ── Zone saisie ──────────────────────────────── */}
              <div className={`rounded-2xl border p-5 mb-6 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
                {(sourcesPretes.length > 0 || sourceActive) && (
                  <div className="mb-4">
                    <SelecteurSource dark={dark} sourceActive={sourceActive} sourcesPretes={sourcesPretes} onChoisir={s => choisirSource(s)} />
                  </div>
                )}
                <div className="flex items-center gap-4 mb-4">
                  <BoutonMicro
                    onDebut={() => { arreterEcoute(); arreterLecture(); setMessage(null); setQuestion(""); setDictee(true); }}
                    onTexteEnDirect={texte => setQuestion(texte)}
                    onTranscription={texte => {
                      // Le texte final remplace l'aperçu ; on laisse l'utilisateur le relire puis valider.
                      setDictee(false);
                      setQuestion(texte);
                      setTimeout(() => champQuestionRef.current?.focus(), 0);
                    }}
                    onErreur={msg => { setDictee(false); setMessage(msg); }}
                    dark={dark}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex gap-2">
                      <input
                        ref={champQuestionRef}
                        aria-label={tx("Question")}
                        value={question}
                        onChange={e => { if (ecouteRef.current) arreterEcoute(); setQuestion(e.target.value); }}
                        onKeyDown={e => e.key === "Enter" && poserQuestion()}
                        placeholder={dictee || ecoute ? tx("Je t'écoute…") : tx("Pose ta question en français...")}
                        maxLength={500}
                        className={`flex-1 min-w-0 px-4 py-3 rounded-xl border text-sm outline-none transition-all ${
                          dark ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400 focus:border-foret-500"
                               : "bg-gray-50 border-gray-200 text-gray-900 focus:border-foret-500"
                        }`}
                      />
                      <button onClick={() => poserQuestion()} disabled={chargement || !question.trim()} aria-label={tx("Envoyer")}
                        className="px-4 py-3 bg-foret-600 hover:bg-foret-700 text-white rounded-xl transition-all disabled:opacity-50">
                        {chargement ? <RefreshCw size={15} className="animate-spin" /> : <Send size={15} />}
                      </button>
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {suggestions.map(s => (
                    <button key={s} onClick={() => poserQuestion(s)} disabled={chargement}
                      className={`text-xs px-3 py-1.5 rounded-full border transition-all hover:scale-105 disabled:opacity-50 ${
                        dark ? "border-gray-600 text-gray-300 hover:border-foret-500 hover:text-foret-400"
                             : "border-gray-200 text-gray-600 hover:border-foret-400 hover:text-foret-600"
                      }`}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              {/* ── Résultats des questions ───────────────────── */}
              {historique.length > 0 ? (
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className={`text-sm font-bold ${dark ? "text-white" : "text-gray-900"}`}>
                      {tx("Résultats ({length})", { length: historique.length })}
                    </h2>
                    <button onClick={toutEffacer}
                      className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all ${
                        dark ? "text-gray-400 hover:bg-gray-700" : "text-gray-500 hover:bg-gray-100"
                      }`}>
                      <Trash2 size={12} />{" "}{tx("Tout effacer")}
                    </button>
                  </div>
                  {historique.slice(0, 5).map(item => (
                    <CarteResultat key={item.id} item={item} dark={dark} onSupprimer={supprimerItem} role={session.role} />
                  ))}
                  {historique.length > 5 && (
                    <button onClick={() => allerA("historique")}
                      className={`text-xs mb-2 ${dark ? "text-foret-400" : "text-foret-600"}`}>
                      {tx("Voir les {x} autres dans l'historique", { x: historique.length - 5 })}
                    </button>
                  )}
                </div>
              ) : (
                <div className={`text-center py-16 ${dark ? "text-gray-500" : "text-gray-400"}`}>
                  <Mic size={40} className="mx-auto mb-3 opacity-30" />
                  <p className="text-sm">{tx("Pose une question vocale ou texte pour voir les résultats")}</p>
                  <p className="text-xs mt-1">{tx("Les résultats s'accumulent ici avec leurs graphiques")}</p>
                </div>
              )}

            </>
          )}
          {page === "tableau" && (
            <>
              {(sourcesPretes.length > 0 || sourceActive) && (
                <div className="mb-4">
                  <SelecteurSource dark={dark} sourceActive={sourceActive} sourcesPretes={sourcesPretes} onChoisir={s => choisirSource(s, null, true)} />
                </div>
              )}
              {kpis.length > 0 && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
                  {kpis.map((k, i) => <KpiCard key={i} {...k} dark={dark} />)}
                </div>
              )}
              {sourceActive
                ? <PanelTableauSource dark={dark} etat={tableauSource} devise={devise} />
                : stats
                  ? <PanelGraphiques dark={dark} stats={stats} />
                  : <p className={`text-sm ${dark ? "text-gray-500" : "text-gray-400"}`}>{tx("Statistiques indisponibles.")}</p>}
            </>
          )}
          {page === "donnees"    && <PanelSources dark={dark} onInterroger={choisirSource} onAbonnement={() => allerA("abonnement")} />}
          {["alertes", "analyse", "credit"].includes(page) && (
            <BarreSourceRisque dark={dark} sourceActive={sourceActive} sourcesPretes={sourcesPretes} externe={externe}
              onChoisir={s => choisirSource(s, null, true)} onMesDonnees={() => allerA("donnees")} />
          )}
          {page === "alertes"    && (sourceActive ? <PanelOperationsSource key={sourceActive.id} source={sourceActive} dark={dark} />
                                                  : <PanelAlertes dark={dark} onChange={rafraichirCompteurs} />)}
          {page === "analyse"    && (sourceActive ? <PanelAnalyseSource key={sourceActive.id} source={sourceActive} dark={dark} />
                                                  : <PanelAnalyse dark={dark} />)}
          {page === "credit"     && (sourceActive ? <PanelCreditSource key={sourceActive.id} source={sourceActive} dark={dark} />
                                                  : <PanelCredit dark={dark} />)}
          {page === "modeles"    && <PanelFiches key={sourceActive ? sourceActive.id : 0} source={sourceActive} dark={dark} />}
          {page === "notifications" && <PanelNotifications dark={dark} />}
          {page === "historique" && (
            <PanelHistorique historique={historique} dark={dark} onSupprimerItem={supprimerItem} onToutEffacer={toutEffacer} />
          )}
          {voitAdmin && page === "apprentissage" && <PanelApprentissage dark={dark} onChange={rafraichirCompteurs} />}
          {voitAdmin && page === "fiabilite"     && <PanelFiabilite dark={dark} />}
          {voitAdmin && page === "audit"         && <PanelAudit dark={dark} />}
          {voitAdmin && page === "comptes"       && <PanelComptes dark={dark} session={session} />}
          {externe && page === "abonnement"      && <PanelAbonnement dark={dark} acces={acces} utilisateur={session.utilisateur} />}
          {externe && page === "organisation"    && <PanelOrganisation dark={dark} onAbonnement={() => allerA("abonnement")} />}
          {externe && page === "journal"         && <PanelJournal dark={dark} />}
          {estAdmin && page === "abonnements"    && <PanelAbonnements dark={dark} />}
          {estAdmin && page === "maintenance"    && <PanelMaintenance dark={dark} />}
        </main>
        </LectureSeule.Provider>

        <footer className={`px-4 sm:px-8 py-4 text-xs ${dark ? "text-gray-600" : "text-gray-400"}`}>
          {tx("© {x} VoiceBank Analytics — Rayan Nguebou Temgoua", { x: new Date().getFullYear() })}
          {" · "}<a href={`/confidentialite/${LANGUE === "en" ? "#en" : ""}`} target="_blank" rel="noopener" className="hover:underline">{tx("Politique de confidentialité")}</a>
        </footer>
      </div>
    </div>
  );
}
