// VOICEBANK ANALYTICS — Interface React v2
// Auteur : Nguebou Temgoua Rayan
// Ajout : Onglet Historique avec sélection et export PDF avec diagrammes

import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from "recharts";
import {
  Mic, MicOff, Sun, Moon, RefreshCw, Send,
  Database, Activity, Users, CreditCard,
  ShieldAlert, TrendingUp, ExternalLink,
  Trash2, ChevronDown, ChevronUp, Download,
  History, CheckSquare, Square, FileText
} from "lucide-react";

// ════════════════════════════════════════
// CONFIGURATION
// ════════════════════════════════════════

// const API          = "http://localhost:8000";
const API = (process.env.REACT_APP_API_URL || "http://localhost:8000").replace(/\/$/, "");
const POWER_BI_URL = "https://app.powerbi.com/Redirect?action=OpenApp&appId=717f0c68-b0c5-414c-bc70-284cbb74faba&ctid=2cbedfc8-117c-4769-8801-ad6ec8ca9c7e&experience=power-bi";
const COULEURS     = ["#3B82F6","#10B981","#F59E0B","#EF4444","#8B5CF6","#06B6D4","#F97316","#84CC16","#EC4899","#14B8A6"];
const CLE_STORAGE  = "voicebank_historique";

// ════════════════════════════════════════
// UTILITAIRES
// ════════════════════════════════════════

function detecterTypeGraphique(colonnes, data) {
  if (!data || data.length === 0) return "table";
  const cols = colonnes.map(c => c.toLowerCase());
  const aDate   = cols.some(c => c.includes("date") || c.includes("mois"));
  const aNombre = cols.some(c => c.includes("count") || c.includes("nb_") || c.includes("total") || c.includes("montant") || c.includes("solde") || c.includes("volume"));
  const aCateg  = cols.some(c => c.includes("banque") || c.includes("ville") || c.includes("statut") || c.includes("type") || c.includes("pays") || c.includes("canal"));
  if (data.length === 1) return "kpi";
  if (aDate && aNombre) return "line";
  if (aCateg && aNombre && data.length <= 15) return "bar";
  if (aCateg && data.length <= 8 && !aNombre) return "pie";
  if (aNombre && data.length > 15) return "area";
  return "table";
}

function trouverCleNumerique(row) {
  const priorites = ["montant_fcfa","solde_fcfa","nb_clients","nb_transactions","total","count","volume","score"];
  for (const p of priorites)
    for (const k of Object.keys(row))
      if (k.toLowerCase().includes(p)) return k;
  return Object.keys(row).find(k => typeof row[k] === "number" && !isNaN(row[k]));
}

function trouverCleCateg(row) {
  const priorites = ["banque","ville","statut","type","pays","canal","nom","prenom"];
  for (const p of priorites)
    for (const k of Object.keys(row))
      if (k.toLowerCase().includes(p)) return k;
  return Object.keys(row).find(k => typeof row[k] === "string");
}

function formaterValeur(val) {
  if (typeof val === "number") {
    if (val > 1_000_000) return (val / 1_000_000).toFixed(1) + "M";
    if (val > 1_000)     return (val / 1_000).toFixed(1) + "k";
    return val.toLocaleString("fr");
  }
  return String(val ?? "");
}

// ════════════════════════════════════════
// HOOK API
// ════════════════════════════════════════

function useAPI() {
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur]         = useState(null);

  const appeler = useCallback(async (methode, url, data = null, options = {}) => {
    setChargement(true);
    setErreur(null);
    try {
      const config = { method: methode, url: `${API}${url}`, ...options };
      if (data) config.data = data;
      const res = await axios(config);
      return res.data;
    } catch (e) {
      setErreur(e.response?.data?.detail || e.message);
      return null;
    } finally {
      setChargement(false);
    }
  }, []);

  return { appeler, chargement, erreur };
}

// ════════════════════════════════════════
// COMPOSANT — ALERTES FRAUDE
// ════════════════════════════════════════

function PanelAlertes({ dark }) {
  const { appeler } = useAPI();
  const [alertes, setAlertes] = useState([]);
  const [filtre, setFiltre]   = useState("Critique");

  useEffect(() => {
    appeler("get", `/alertes/fraude?niveau=${filtre}&limit=8`).then(res => {
      if (res) setAlertes(res.data);
    });
  }, [filtre]);

  const couleurNiveau = {
    Critique: "text-red-500 bg-red-100",
    Élevé:    "text-orange-500 bg-orange-100",
    Moyen:    "text-yellow-600 bg-yellow-100",
    Faible:   "text-green-600 bg-green-100",
  };

  return (
    <div className={`rounded-2xl border p-6 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
      <div className="flex items-center justify-between mb-4">
        <h2 className={`text-lg font-bold ${dark ? "text-white" : "text-gray-900"}`}>🚨 Alertes Fraude</h2>
        <div className="flex gap-1">
          {["Critique","Élevé","Moyen"].map(n => (
            <button key={n} onClick={() => setFiltre(n)}
              className={`text-xs px-2.5 py-1 rounded-full transition-all ${filtre === n ? "bg-blue-600 text-white" : dark ? "bg-gray-700 text-gray-300" : "bg-gray-100 text-gray-600"}`}>
              {n}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-2">
        {alertes.length === 0 ? (
          <p className={`text-sm text-center py-4 ${dark ? "text-gray-500" : "text-gray-400"}`}>Aucune alerte {filtre}</p>
        ) : alertes.map((a, i) => (
          <div key={i} className={`flex items-center justify-between p-3 rounded-xl ${dark ? "bg-gray-700" : "bg-gray-50"}`}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${couleurNiveau[a.niveau_alerte] || "text-gray-500 bg-gray-100"}`}>{a.niveau_alerte}</span>
                <span className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>Score : {(a.score_anomalie * 100).toFixed(0)}%</span>
              </div>
              <p className={`text-xs truncate ${dark ? "text-gray-300" : "text-gray-600"}`}>{a.motif || "Comportement inhabituel"}</p>
              <p className={`text-xs ${dark ? "text-gray-500" : "text-gray-400"}`}>{a.banque} · {a.ville}</p>
            </div>
            <div className="text-right ml-2">
              <p className={`text-sm font-bold ${dark ? "text-white" : "text-gray-900"}`}>{a.montant_fcfa ? (a.montant_fcfa / 1000000).toFixed(1) + "M" : "--"}</p>
              <p className={`text-xs ${dark ? "text-gray-500" : "text-gray-400"}`}>FCFA</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

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
    const cle = m.mois ? new Date(m.mois).toLocaleDateString("fr", { month: "short", year: "2-digit" }) : "";
    if (!parMois[cle]) parMois[cle] = { mois: cle, transactions: 0, fraudes: 0 };
    parMois[cle].transactions += m.nb_transactions || 0;
    parMois[cle].fraudes      += m.nb_fraudes      || 0;
  });
  const dataMois = Object.values(parMois).slice(0, 12);
  const axisStyle = { fill: dark ? "#9CA3AF" : "#6B7280", fontSize: 11 };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className={`rounded-2xl border p-5 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
        <h3 className={`text-sm font-bold mb-4 ${dark ? "text-white" : "text-gray-900"}`}>Clients par banque</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={dataClients}>
            <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
            <XAxis dataKey="name" tick={axisStyle} />
            <YAxis tick={axisStyle} />
            <Tooltip contentStyle={{ backgroundColor: dark ? "#1F2937" : "#fff", border: "none", borderRadius: 8 }} labelStyle={{ color: dark ? "#fff" : "#111" }} />
            <Bar dataKey="clients" fill="#3B82F6" radius={[4,4,0,0]} name="Total" />
            <Bar dataKey="diaspora" fill="#10B981" radius={[4,4,0,0]} name="Diaspora" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className={`rounded-2xl border p-5 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
        <h3 className={`text-sm font-bold mb-4 ${dark ? "text-white" : "text-gray-900"}`}>Transactions mensuelles</h3>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={dataMois}>
            <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
            <XAxis dataKey="mois" tick={axisStyle} />
            <YAxis tick={axisStyle} />
            <Tooltip contentStyle={{ backgroundColor: dark ? "#1F2937" : "#fff", border: "none", borderRadius: 8 }} />
            <Line type="monotone" dataKey="transactions" stroke="#3B82F6" strokeWidth={2} dot={false} name="Total" />
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

function GraphiqueDynamique({ colonnes, data, question, dark }) {
  const type     = detecterTypeGraphique(colonnes, data);
  const cleNum   = trouverCleNumerique(data[0] || {});
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
    const cleDateKey = colonnes.find(c => c.toLowerCase().includes("date") || c.toLowerCase().includes("mois"));
    return (
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data.slice(0, 50)}>
          <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
          <XAxis dataKey={cleDateKey} tick={axisStyle} tickFormatter={v => String(v).slice(0, 10)} />
          <YAxis tick={axisStyle} tickFormatter={formaterValeur} />
          <Tooltip {...tooltipStyle} formatter={formaterValeur} />
          <Line type="monotone" dataKey={cleNum} stroke="#3B82F6" strokeWidth={2} dot={false} />
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
          <Area type="monotone" dataKey={cleNum} stroke="#3B82F6" fill="#3B82F620" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    );
  }
  if (type === "bar" && cleNum && cleCateg) {
    return (
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data.slice(0, 20)} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
          <XAxis type="number" tick={axisStyle} tickFormatter={formaterValeur} />
          <YAxis type="category" dataKey={cleCateg} tick={axisStyle} width={100} tickFormatter={v => String(v).slice(0, 14)} />
          <Tooltip {...tooltipStyle} formatter={formaterValeur} />
          <Bar dataKey={cleNum} radius={[0,4,4,0]}>
            {data.slice(0,20).map((_, i) => <Cell key={i} fill={COULEURS[i % COULEURS.length]} />)}
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
              <th key={c} className={`text-left px-3 py-2 font-medium ${dark ? "text-gray-300" : "text-gray-600"}`}>{c}</th>
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

function GraphiquePourPDF({ colonnes, data }) {
  const type     = detecterTypeGraphique(colonnes, data);
  const cleNum   = trouverCleNumerique(data[0] || {});
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
        <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={({name}) => name.slice(0,14)}>
          {pieData.map((_, i) => <Cell key={i} fill={COULEURS[i % COULEURS.length]} />)}
        </Pie>
        <Tooltip {...tooltipStyle} />
      </PieChart>
    );
  }
  if (type === "line" && cleNum) {
    const cleDateKey = colonnes.find(c => c.toLowerCase().includes("date") || c.toLowerCase().includes("mois"));
    return (
      <LineChart width={540} height={240} data={data.slice(0, 50)}>
        <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
        <XAxis dataKey={cleDateKey} tick={axisStyle} tickFormatter={v => String(v).slice(0, 10)} />
        <YAxis tick={axisStyle} tickFormatter={formaterValeur} />
        <Tooltip {...tooltipStyle} formatter={formaterValeur} />
        <Line type="monotone" dataKey={cleNum} stroke="#3B82F6" strokeWidth={2} dot={false} />
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
        <Area type="monotone" dataKey={cleNum} stroke="#3B82F6" fill="#DBEAFE" strokeWidth={2} />
      </AreaChart>
    );
  }
  if (type === "bar" && cleNum && cleCateg) {
    return (
      <BarChart width={540} height={240} data={data.slice(0, 15)} layout="vertical">
        <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
        <XAxis type="number" tick={axisStyle} tickFormatter={formaterValeur} />
        <YAxis type="category" dataKey={cleCateg} tick={axisStyle} width={110} tickFormatter={v => String(v).slice(0, 16)} />
        <Tooltip {...tooltipStyle} formatter={formaterValeur} />
        <Bar dataKey={cleNum} radius={[0,4,4,0]}>
          {data.slice(0,15).map((_, i) => <Cell key={i} fill={COULEURS[i % COULEURS.length]} />)}
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
            <th key={c} style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600, color: "#374151", borderBottom: "1px solid #E5E7EB" }}>{c}</th>
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

function CarteResultat({ item, dark, onSupprimer }) {
  const [ouvert, setOuvert] = useState(true);

  return (
    <div className={`rounded-2xl border mb-4 overflow-hidden transition-all ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
      <div
        className={`flex items-center justify-between px-5 py-3 cursor-pointer ${dark ? "hover:bg-gray-700" : "hover:bg-gray-50"}`}
        onClick={() => setOuvert(!ouvert)}
      >
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-medium truncate ${dark ? "text-white" : "text-gray-900"}`}>{item.question}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>{item.total} résultats · {item.duree_ms}ms</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${item.source === "rag" ? "bg-green-100 text-green-700" : "bg-blue-100 text-blue-700"}`}>
              {item.source === "rag" ? "RAG" : "Gemini"}
            </span>
            <span className={`text-xs ${dark ? "text-gray-500" : "text-gray-400"}`}>{new Date(item.timestamp).toLocaleTimeString("fr")}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 ml-3">
          <button onClick={e => { e.stopPropagation(); onSupprimer(item.id); }}
            className={`p-1.5 rounded-lg ${dark ? "hover:bg-gray-600 text-gray-400" : "hover:bg-gray-100 text-gray-400"}`}>
            <Trash2 size={13} />
          </button>
          {ouvert ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>
      {ouvert && item.data && item.data.length > 0 && (
        <div className="px-5 pb-5">
          <code className={`text-xs block mb-3 truncate ${dark ? "text-blue-300" : "text-blue-600"}`}>{item.sql}</code>
          <GraphiqueDynamique colonnes={item.colonnes} data={item.data} question={item.question} dark={dark} />
        </div>
      )}
      {ouvert && (!item.data || item.data.length === 0) && (
        <div className={`px-5 pb-5 text-sm ${dark ? "text-gray-400" : "text-gray-500"}`}>Aucun résultat trouvé pour cette question.</div>
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
      pdf.setFillColor(30, 64, 175);
      pdf.rect(0, 0, pageW, 32, "F");

      pdf.setTextColor(255, 255, 255);
      pdf.setFontSize(16);
      pdf.setFont("helvetica", "bold");
      pdf.text("VoiceBank Analytics", margin, 13);

      pdf.setFontSize(9);
      pdf.setFont("helvetica", "normal");
      pdf.text("Rapport d'historique des requêtes", margin, 20);
      pdf.text(`Généré le ${now.toLocaleDateString("fr-FR")} à ${now.toLocaleTimeString("fr-FR", { hour:"2-digit", minute:"2-digit" })}`, margin, 27);

      // Compteur à droite
      pdf.setFontSize(9);
      pdf.text(`${selection.size} entrée${selection.size > 1 ? "s" : ""}`, pageW - margin, 20, { align: "right" });

      let y = 42;

      for (let idx = 0; idx < selectedItems.length; idx++) {
        const item = selectedItems[idx];

        // ── Nouvelle page si nécessaire ──
        if (y > pageH - 70) { pdf.addPage(); y = 18; }

        // ── Numéro + fond de section ──
        pdf.setFillColor(241, 245, 249);
        pdf.roundedRect(margin, y, cW, 10, 2, 2, "F");

        pdf.setTextColor(30, 64, 175);
        pdf.setFontSize(8);
        pdf.setFont("helvetica", "bold");
        pdf.text(`# ${idx + 1}`, margin + 3, y + 7);

        pdf.setTextColor(17, 24, 39);
        pdf.setFontSize(10);
        const lignesQ = pdf.splitTextToSize(item.question, cW - 16);
        pdf.text(lignesQ, margin + 10, y + 7);
        y += 10 + (lignesQ.length - 1) * 5 + 4;

        // ── Métadonnées ──
        const dateStr = new Date(item.timestamp).toLocaleString("fr-FR");
        pdf.setFontSize(8);
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(107, 114, 128);
        pdf.text(`📅  ${dateStr}`, margin, y);
        pdf.text(`⏱  ${item.duree_ms} ms`, margin + 55, y);

        const sourceBadge = item.source === "rag" ? "RAG" : item.source === "rule" ? "Règle" : "Gemini";
        pdf.setTextColor(255, 255, 255);
        const badgeColor = item.source === "rag" ? [16, 185, 129] : item.source === "rule" ? [245, 158, 11] : [59, 130, 246];
        pdf.setFillColor(...badgeColor);
        pdf.roundedRect(margin + 78, y - 4, 18, 6, 1, 1, "F");
        pdf.setFontSize(7);
        pdf.text(sourceBadge, margin + 87, y, { align: "center" });
        y += 7;

        // ── Requête SQL ──
        if (y > pageH - 50) { pdf.addPage(); y = 18; }
        pdf.setTextColor(59, 130, 246);
        pdf.setFontSize(7.5);
        pdf.setFont("helvetica", "bold");
        pdf.text("Requête SQL :", margin, y);
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
        pdf.text(`Résultats : ${item.total} ligne${item.total > 1 ? "s" : ""}  ·  ${item.colonnes?.length || 0} colonne${(item.colonnes?.length || 0) > 1 ? "s" : ""}`, margin, y);
        y += 6;

        // ── Capture du graphique ──
        const chartEl = chartRefs.current[item.id];
        if (chartEl && item.data && item.data.length > 0) {
          try {
            if (y > pageH - 75) { pdf.addPage(); y = 18; }

            pdf.setFont("helvetica", "bold");
            pdf.setFontSize(8);
            pdf.setTextColor(59, 130, 246);
            pdf.text("Visualisation :", margin, y);
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
            pdf.text("[Aperçu graphique indisponible — données tabulaires ci-dessous]", margin, y);
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
          cols.forEach((c, ci) => pdf.text(String(c).slice(0, 16), margin + ci * colW + 2, y + 4));
          y += 5.5;

          previewRows.forEach((row, ri) => {
            if (y > pageH - 12) return;
            pdf.setFillColor(ri % 2 === 0 ? 249 : 243, ri % 2 === 0 ? 250 : 244, ri % 2 === 0 ? 251 : 246);
            pdf.rect(margin, y, cW, 5, "F");
            pdf.setTextColor(31, 41, 55);
            pdf.setFont("helvetica", "normal");
            cols.forEach((c, ci) => pdf.text(String(row[c] ?? "").slice(0, 16), margin + ci * colW + 2, y + 3.8));
            y += 5;
          });
          if (item.total > 5) {
            pdf.setFontSize(7);
            pdf.setTextColor(156, 163, 175);
            pdf.setFont("helvetica", "italic");
            pdf.text(`… et ${item.total - 5} ligne${item.total - 5 > 1 ? "s" : ""} supplémentaire${item.total - 5 > 1 ? "s" : ""}`, margin, y + 4);
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
        pdf.text("VoiceBank Analytics — Rapport confidentiel", margin, pageH - 4);
        pdf.text(`Page ${p} / ${totalPages}`, pageW - margin, pageH - 4, { align: "right" });
      }

      const nomFichier = `VoiceBank_Rapport_${now.toISOString().slice(0, 10)}_${now.getHours()}h${now.getMinutes()}.pdf`;
      pdf.save(nomFichier);
    } catch (err) {
      console.error("Erreur PDF :", err);
      alert("Erreur lors de la génération du PDF. Vérifiez que jspdf et html2canvas sont installés :\nnpm install jspdf html2canvas");
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
            <GraphiquePourPDF colonnes={item.colonnes} data={item.data} />
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
                ? <CheckSquare size={15} className="text-blue-500" />
                : partielSelection
                ? <CheckSquare size={15} className="text-blue-400 opacity-60" />
                : <Square size={15} />
              }
              {toutSelectionne ? "Désélectionner tout" : "Tout sélectionner"}
            </button>

            {selection.size > 0 && (
              <span className={`text-sm font-medium px-3 py-1.5 rounded-xl ${dark ? "bg-blue-900/40 text-blue-300" : "bg-blue-50 text-blue-700"}`}>
                {selection.size} sélectionné{selection.size > 1 ? "s" : ""}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Recherche */}
            <input
              value={recherche}
              onChange={e => setRecherche(e.target.value)}
              placeholder="Rechercher..."
              className={`text-sm px-3 py-2 rounded-xl border outline-none transition-all w-48 ${
                dark ? "bg-gray-700 border-gray-600 text-white placeholder-gray-500 focus:border-blue-500" : "bg-gray-50 border-gray-200 text-gray-900 focus:border-blue-400"
              }`}
            />

            {/* Effacer tout */}
            <button
              onClick={onToutEffacer}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm transition-all ${dark ? "text-red-400 hover:bg-red-900/20" : "text-red-500 hover:bg-red-50"}`}
            >
              <Trash2 size={14} /> Vider
            </button>

            {/* Télécharger PDF */}
            <button
              onClick={genererPDF}
              disabled={selection.size === 0 || generationPDF}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all shadow-md ${
                selection.size === 0 || generationPDF
                  ? "opacity-40 cursor-not-allowed bg-gray-400 text-white"
                  : "bg-blue-600 hover:bg-blue-700 active:scale-95 text-white shadow-blue-500/30"
              }`}
            >
              {generationPDF
                ? <><RefreshCw size={14} className="animate-spin" /> Génération…</>
                : <><Download size={14} /> Rapport PDF {selection.size > 0 ? `(${selection.size})` : ""}</>
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
            {recherche ? "Aucune requête ne correspond à votre recherche" : "Aucun historique pour le moment"}
          </p>
          <p className={`text-xs mt-1 ${dark ? "text-gray-600" : "text-gray-300"}`}>
            {!recherche && "Posez une question pour commencer"}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {historiqueFiltre.map((item) => {
            const date    = new Date(item.timestamp);
            const dateStr = date.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
            const heurStr = date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
            const sel     = selection.has(item.id);
            const type    = detecterTypeGraphique(item.colonnes || [], item.data || []);

            const typeIcon = type === "bar" ? "📊" : type === "line" ? "📈" : type === "pie" ? "🥧" : type === "area" ? "📉" : type === "kpi" ? "🎯" : "📋";

            return (
              <div
                key={item.id}
                onClick={() => basculer(item.id)}
                className={`group rounded-2xl border cursor-pointer transition-all duration-200 ${
                  sel
                    ? dark
                      ? "border-blue-500 bg-blue-900/20 shadow-lg shadow-blue-900/20"
                      : "border-blue-400 bg-blue-50 shadow-lg shadow-blue-100"
                    : dark
                      ? "border-gray-700 bg-gray-800 hover:border-gray-600 hover:bg-gray-750"
                      : "border-gray-200 bg-white hover:border-gray-300 hover:shadow-md"
                }`}
              >
                <div className="flex items-start gap-4 p-4">
                  {/* Checkbox */}
                  <div className={`mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 transition-all ${
                    sel
                      ? "bg-blue-600 border-blue-600"
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
                      <span className="text-base">{typeIcon}</span>
                      <p className={`font-semibold text-sm leading-snug truncate flex-1 ${dark ? "text-white" : "text-gray-900"}`}>
                        {item.question}
                      </p>
                    </div>

                    {/* Ligne 2 : Métadonnées */}
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-2">
                      <span className={`flex items-center gap-1 text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
                        <span className="opacity-60">📅</span> {dateStr}
                      </span>
                      <span className={`flex items-center gap-1 text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
                        <span className="opacity-60">🕐</span> {heurStr}
                      </span>
                      <span className={`flex items-center gap-1 text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
                        <span className="opacity-60">⏱</span> {item.duree_ms} ms
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        item.source === "rag"
                          ? dark ? "bg-emerald-900/40 text-emerald-400" : "bg-emerald-100 text-emerald-700"
                          : item.source === "rule"
                          ? dark ? "bg-amber-900/40 text-amber-400" : "bg-amber-100 text-amber-700"
                          : dark ? "bg-blue-900/40 text-blue-400" : "bg-blue-100 text-blue-700"
                      }`}>
                        {item.source === "rag" ? "🔄 RAG" : item.source === "rule" ? "⚡ Règle" : "🤖 Gemini"}
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
                        {item.total} ligne{item.total !== 1 ? "s" : ""}
                      </span>
                      <span className={`text-xs ${dark ? "text-gray-500" : "text-gray-400"}`}>
                        {item.colonnes?.length || 0} colonne{(item.colonnes?.length || 0) !== 1 ? "s" : ""}
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
          <Download size={12} />
          Sélectionne les requêtes à inclure dans le rapport, puis clique sur <strong className="ml-0.5">Rapport PDF</strong>. Le PDF contiendra la question, la requête SQL, la date/heure et le diagramme ou tableau correspondant.
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════
// COMPOSANT — BOUTON MICRO
// ════════════════════════════════════════

function BoutonMicro({ onTranscription, dark }) {
  const [statut, setStatut] = useState("idle");
  const mediaRecRef         = useRef(null);
  const chunksRef           = useRef([]);
  const timerRef            = useRef(null);

  const demarrer = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/ogg";

      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      recorder.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = async () => {
        clearTimeout(timerRef.current);
        setStatut("processing");
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const formData = new FormData();
        formData.append("fichier", blob, `audio.${mimeType.includes("webm") ? "webm" : "ogg"}`);
        try {
          const res = await axios.post(`${API}/vocal/transcrire`, formData, {
            headers: { "Content-Type": "multipart/form-data" }, timeout: 30000,
          });
          if (res.data?.texte?.trim()) onTranscription(res.data.texte.trim());
          else alert("Aucun texte détecté. Parle plus fort ou plus clairement.");
        } catch (e) {
          alert(`Erreur Whisper: ${e.response?.data?.detail || e.message}`);
        }
        stream.getTracks().forEach(t => t.stop());
        setStatut("idle");
      };
      recorder.start(100);
      mediaRecRef.current = recorder;
      setStatut("recording");
      timerRef.current = setTimeout(() => arreter(), 8000);
    } catch (e) {
      alert("Microphone inaccessible. Autorise le micro dans ton navigateur.");
      setStatut("idle");
    }
  };

  const arreter = () => {
    clearTimeout(timerRef.current);
    if (mediaRecRef.current?.state === "recording") mediaRecRef.current.stop();
    setStatut(s => s === "recording" ? "processing" : s);
  };

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        onClick={statut === "recording" ? arreter : demarrer}
        disabled={statut === "processing"}
        className={`relative w-16 h-16 rounded-full flex items-center justify-center transition-all shadow-lg disabled:opacity-60 ${
          statut === "recording" ? "bg-red-500 hover:bg-red-600 scale-110" : "bg-blue-600 hover:bg-blue-700"
        }`}
      >
        {statut === "recording" && <span className="absolute inset-0 rounded-full bg-red-400 animate-ping opacity-50" />}
        {statut === "processing" ? <RefreshCw size={22} className="text-white animate-spin" />
          : statut === "recording" ? <MicOff size={22} className="text-white" />
          : <Mic size={22} className="text-white" />}
      </button>
      <span className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
        {statut === "recording" ? "🔴 Enregistrement..." : statut === "processing" ? "⏳ Transcription..." : "Cliquer pour parler"}
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
// APP PRINCIPALE
// ════════════════════════════════════════

export default function App() {
  const [dark, setDark]             = useState(true);
  const [question, setQuestion]     = useState("");
  const [historique, setHistorique] = useState([]);
  const [dashboard, setDashboard]   = useState(null);
  const [onglet, setOnglet]         = useState("graphiques");
  const [stats, setStats]           = useState(null);
  const { appeler, chargement }     = useAPI();

useEffect(() => {
    try {
      const saved = localStorage.getItem(CLE_STORAGE);
      if (saved) setHistorique(JSON.parse(saved));
    } catch (e) {}

    appeler("get", "/dashboard").then(res => {
      if (res?.data) setDashboard(res.data);
    });
    appeler("get", "/stats/global").then(res => {
      if (res?.data) setStats(res.data);
    });
  }, [appeler]); // ← ajoute appeler ici

useEffect(() => {
    appeler("get", `/alertes/fraude?niveau=${filtre}&limit=8`).then(res => {
      if (res) setAlertes(res.data);
    });
  }, [filtre, appeler]); // ← ajoute appeler

  const poserQuestion = async (texte, clearInput = true) => {
    const q = (texte || question).trim();
    if (!q) return;
    if (clearInput) setQuestion("");

    const res = await appeler("post", "/vocal/question", { texte: q, langue: "fr" });
    if (!res) { alert("Impossible de récupérer le résultat. Vérifie que l'API fonctionne."); return; }

    const nouvelItem = {
      id: Date.now(), timestamp: new Date().toISOString(),
      question: q, sql: res.sql, source: res.source,
      colonnes: res.colonnes, total: res.total,
      data: res.data, duree_ms: res.duree_ms,
    };
    setHistorique(prev => [nouvelItem, ...prev]);
  };

  const supprimerItem = (id) => setHistorique(prev => prev.filter(item => item.id !== id));

  const toutEffacer = () => {
    if (window.confirm("Supprimer tout l'historique ?")) {
      setHistorique([]);
      localStorage.removeItem(CLE_STORAGE);
    }
  };

  const kpis = dashboard ? [
    { titre: "Clients",        valeur: Number(dashboard.total_clients || 0).toLocaleString("fr"),       icone: Users,       couleur: "#3B82F6" },
    { titre: "Transactions",   valeur: Number(dashboard.total_transactions || 0).toLocaleString("fr"),   icone: Activity,    couleur: "#10B981" },
    { titre: "Fraudes",        valeur: Number(dashboard.total_fraudes || 0).toLocaleString("fr"),        icone: ShieldAlert, couleur: "#EF4444" },
    { titre: "Crédits actifs", valeur: Number(dashboard.encours_credit_fcfa || 0) > 0
        ? (Number(dashboard.encours_credit_fcfa) / 1_000_000_000).toFixed(1) + " Mds FCFA" : "--",
      icone: CreditCard, couleur: "#F59E0B" },
  ] : [];

  const suggestions = [
    "Top 10 clients par solde",
    "Credits en defaut",
    "Transactions frauduleuses par banque",
    "Alertes critiques",
    "Clients diaspora France",
    "Volume transactions par ville",
  ];

  const ONGLETS = [
    { id: "graphiques", label: "Graphiques" },
    { id: "alertes",    label: "Alertes" },
    { id: "historique", label: `Historique${historique.length > 0 ? ` (${historique.length})` : ""}` },
  ];

  return (
    <div className={`min-h-screen transition-colors duration-300 ${dark ? "bg-gray-900" : "bg-gray-50"}`}>

      {/* ── Header ───────────────────────────────────────── */}
      <header className={`sticky top-0 z-20 border-b px-6 py-3 flex items-center justify-between backdrop-blur-md ${
        dark ? "bg-gray-900/90 border-gray-700" : "bg-white/90 border-gray-200"
      }`}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <Database size={15} className="text-white" />
          </div>
          <div>
            <h1 className={`text-sm font-bold ${dark ? "text-white" : "text-gray-900"}`}>VoiceBank Analytics</h1>
            <p className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>Nguebou Temgoua Rayan</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => window.open(POWER_BI_URL, "_blank")}
            className="flex items-center gap-1.5 px-3 py-2 bg-yellow-500 hover:bg-yellow-600 text-white text-xs font-medium rounded-xl transition-all">
            <TrendingUp size={13} /> Power BI <ExternalLink size={11} />
          </button>
          <button onClick={() => setDark(!dark)}
            className={`p-2 rounded-xl transition-all ${dark ? "bg-gray-700 hover:bg-gray-600 text-gray-300" : "bg-gray-100 hover:bg-gray-200 text-gray-600"}`}>
            {dark ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-6">

        {/* ── KPIs ─────────────────────────────────────── */}
        {kpis.length > 0 && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            {kpis.map((k, i) => <KpiCard key={i} {...k} dark={dark} />)}
          </div>
        )}

        {/* ── Zone saisie ──────────────────────────────── */}
        <div className={`rounded-2xl border p-5 mb-6 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
          <div className="flex items-center gap-4 mb-4">
            <BoutonMicro onTranscription={texte => poserQuestion(texte)} dark={dark} />
            <div className="flex-1">
              <div className="flex gap-2">
                <input
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && poserQuestion()}
                  placeholder="Pose ta question en français..."
                  className={`flex-1 px-4 py-3 rounded-xl border text-sm outline-none transition-all ${
                    dark ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400 focus:border-blue-500"
                         : "bg-gray-50 border-gray-200 text-gray-900 focus:border-blue-500"
                  }`}
                />
                <button onClick={() => poserQuestion()} disabled={chargement || !question.trim()}
                  className="px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl transition-all disabled:opacity-50">
                  {chargement ? <RefreshCw size={15} className="animate-spin" /> : <Send size={15} />}
                </button>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {suggestions.map(s => (
              <button key={s} onClick={() => poserQuestion(s)} disabled={chargement}
                className={`text-xs px-3 py-1.5 rounded-full border transition-all hover:scale-105 disabled:opacity-50 ${
                  dark ? "border-gray-600 text-gray-300 hover:border-blue-500 hover:text-blue-400"
                       : "border-gray-200 text-gray-600 hover:border-blue-400 hover:text-blue-600"
                }`}>
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* ── Résultats des questions ───────────────────── */}
        {historique.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className={`text-sm font-bold ${dark ? "text-white" : "text-gray-900"}`}>
                Résultats ({historique.length})
              </h2>
              <button onClick={toutEffacer}
                className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all ${
                  dark ? "text-gray-400 hover:bg-gray-700" : "text-gray-500 hover:bg-gray-100"
                }`}>
                <Trash2 size={12} /> Tout effacer
              </button>
            </div>
            {historique.map(item => (
              <CarteResultat key={item.id} item={item} dark={dark} onSupprimer={supprimerItem} />
            ))}
          </div>
        )}

        {historique.length === 0 && (
          <div className={`text-center py-16 ${dark ? "text-gray-500" : "text-gray-400"}`}>
            <Mic size={40} className="mx-auto mb-3 opacity-30" />
            <p className="text-sm">Pose une question vocale ou texte pour voir les résultats</p>
            <p className="text-xs mt-1">Les résultats s'accumulent ici avec leurs graphiques</p>
          </div>
        )}

        {/* ── Onglets Graphiques / Alertes / Historique ── */}
        {dashboard && (
          <div className="mt-8">
            <div className="flex gap-2 mb-4">
              {ONGLETS.map(o => (
                <button
                  key={o.id}
                  onClick={() => setOnglet(o.id)}
                  className={`px-4 py-2 rounded-lg font-medium text-sm transition-all ${
                    onglet === o.id
                      ? "bg-blue-600 text-white shadow-md shadow-blue-500/20"
                      : dark ? "bg-gray-700 text-gray-300 hover:bg-gray-600" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                  }`}
                >
                  {o.id === "historique" && <History size={13} className="inline mr-1.5 -mt-0.5" />}
                  {o.label}
                </button>
              ))}
            </div>

            {onglet === "graphiques" && <PanelGraphiques dark={dark} stats={stats} />}
            {onglet === "alertes"    && <PanelAlertes dark={dark} />}
            {onglet === "historique" && (
              <PanelHistorique
                historique={historique}
                dark={dark}
                onSupprimerItem={supprimerItem}
                onToutEffacer={toutEffacer}
              />
            )}
          </div>
        )}

        {/* ── Footer ───────────────────────────────────── */}
        <footer className={`mt-12 py-6 text-center text-xs ${dark ? "text-gray-500" : "text-gray-400"}`}>
          &copy; {new Date().getFullYear()} VoiceBank Analytics. Tous droits réservés. By Rayan NT.
        </footer>
      </main>
    </div>
  );
}