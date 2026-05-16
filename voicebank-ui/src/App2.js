// VOICEBANK ANALYTICS — Interface React v3
// Auteur : Nguebou Temgoua Rayan
// Onglets : Tableau de bord | Historique avec sélection & export PDF

import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { jsPDF } from "jspdf";
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import {
  Mic, MicOff, Sun, Moon, RefreshCw,
  Database, Download, Trash2, History,
  LayoutDashboard, ChevronUp, ChevronDown,
  CheckSquare, Square, FileText, Clock, Calendar,
  Search, AlertTriangle, TrendingUp, Users,
} from "lucide-react";

const API         = "http://localhost:8000";
const CLE_STORAGE = "voicebank_historique";
const COULEURS    = ["#3B82F6","#10B981","#F59E0B","#EF4444","#8B5CF6","#06B6D4","#F97316","#84CC16"];

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
    if (val > 1_000_000) return (val/1_000_000).toFixed(1) + "M";
    if (val > 1_000)     return (val/1_000).toFixed(1) + "k";
    return val.toLocaleString("fr");
  }
  return String(val ?? "");
}

function formaterDate(iso) {
  if (!iso) return "--";
  const d = new Date(iso);
  return d.toLocaleDateString("fr-FR", { day:"2-digit", month:"2-digit", year:"numeric" });
}

function formaterHeure(iso) {
  if (!iso) return "--";
  const d = new Date(iso);
  return d.toLocaleTimeString("fr-FR", { hour:"2-digit", minute:"2-digit", second:"2-digit" });
}

// ════════════════════════════════════════
// HOOK API
// ════════════════════════════════════════

function useAPI() {
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur]         = useState(null);

  const appeler = useCallback(async (methode, url, data = null, options = {}) => {
    setChargement(true); setErreur(null);
    try {
      const config = { method: methode, url: `${API}${url}`, ...options };
      if (data) config.data = data;
      const res = await axios(config);
      return res.data;
    } catch (e) {
      const msg = e.response?.data?.detail || e.message;
      setErreur(msg); return null;
    } finally {
      setChargement(false);
    }
  }, []);

  return { appeler, chargement, erreur };
}

// ════════════════════════════════════════
// BOUTON MICRO
// ════════════════════════════════════════

function BoutonMicro({ onTranscription, dark }) {
  const [statut, setStatut] = useState("idle");
  const mediaRecRef = useRef(null);
  const chunksRef   = useRef([]);
  const timerRef    = useRef(null);

  const demarrer = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus" : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm" : "audio/ogg";
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      recorder.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = async () => {
        clearTimeout(timerRef.current);
        setStatut("processing");
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const formData = new FormData();
        const ext = mimeType.includes("webm") ? "webm" : "ogg";
        formData.append("fichier", blob, `audio.${ext}`);
        try {
          const res = await axios.post(`${API}/vocal/transcrire`, formData, {
            headers: { "Content-Type": "multipart/form-data" }, timeout: 30000,
          });
          if (res.data?.texte?.trim()) onTranscription(res.data.texte.trim());
          else alert("Aucun texte détecté. Parle plus fort.");
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
      alert("Microphone inaccessible.");
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
        className={`relative w-14 h-14 rounded-full flex items-center justify-center shadow-lg transition-all disabled:opacity-60 ${
          statut === "recording" ? "bg-red-500 hover:bg-red-600 scale-110" : "bg-blue-600 hover:bg-blue-700"
        }`}
      >
        {statut === "recording" && (
          <span className="absolute inset-0 rounded-full bg-red-400 animate-ping opacity-50" />
        )}
        {statut === "processing" ? <RefreshCw size={20} className="text-white animate-spin" />
          : statut === "recording" ? <MicOff size={20} className="text-white" />
          : <Mic size={20} className="text-white" />}
      </button>
      <span className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
        {statut === "recording" ? "🔴 En cours..." : statut === "processing" ? "⏳ Transcription..." : "Cliquer pour parler"}
      </span>
    </div>
  );
}

// ════════════════════════════════════════
// GRAPHIQUE DYNAMIQUE
// ════════════════════════════════════════

function GraphiqueDynamique({ colonnes, data, dark }) {
  const type     = detecterTypeGraphique(colonnes, data);
  const cleNum   = trouverCleNumerique(data[0] || {});
  const cleCateg = trouverCleCateg(data[0] || {});
  const axisStyle = { fill: dark ? "#9CA3AF" : "#6B7280", fontSize: 11 };
  const tooltipStyle = {
    contentStyle: { backgroundColor: dark ? "#1F2937" : "#fff", border:"none", borderRadius:8, fontSize:12 },
    labelStyle: { color: dark ? "#fff" : "#111" },
  };

  if (type === "kpi") return (
    <div className="grid grid-cols-2 gap-3 mt-3">
      {Object.entries(data[0]).map(([k, v]) => (
        <div key={k} className={`rounded-xl p-4 text-center ${dark ? "bg-gray-700" : "bg-gray-50"}`}>
          <p className={`text-xs mb-1 ${dark ? "text-gray-400" : "text-gray-500"}`}>{k}</p>
          <p className={`text-xl font-bold ${dark ? "text-white" : "text-gray-900"}`}>{formaterValeur(v)}</p>
        </div>
      ))}
    </div>
  );

  if (type === "pie" && cleCateg) {
    const pieData = data.slice(0,8).map(row => ({
      name: String(row[cleCateg] || "").slice(0,20),
      value: Number(row[cleNum] || Object.values(row).find(v => typeof v==="number") || 1),
    }));
    return (
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={75}
            label={({name}) => name.slice(0,10)}>
            {pieData.map((_,i) => <Cell key={i} fill={COULEURS[i%COULEURS.length]} />)}
          </Pie>
          <Tooltip {...tooltipStyle} />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (type === "line" && cleNum) {
    const cleDateKey = colonnes.find(c => c.toLowerCase().includes("date") || c.toLowerCase().includes("mois"));
    return (
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data.slice(0,50)}>
          <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
          <XAxis dataKey={cleDateKey} tick={axisStyle} tickFormatter={v => String(v).slice(0,10)} />
          <YAxis tick={axisStyle} tickFormatter={formaterValeur} />
          <Tooltip {...tooltipStyle} formatter={formaterValeur} />
          <Line type="monotone" dataKey={cleNum} stroke="#3B82F6" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  if (type === "bar" && cleNum && cleCateg) return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data.slice(0,20)} layout="vertical">
        <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
        <XAxis type="number" tick={axisStyle} tickFormatter={formaterValeur} />
        <YAxis type="category" dataKey={cleCateg} tick={axisStyle} width={90}
          tickFormatter={v => String(v).slice(0,12)} />
        <Tooltip {...tooltipStyle} formatter={formaterValeur} />
        <Bar dataKey={cleNum} radius={[0,4,4,0]}>
          {data.slice(0,20).map((_,i) => <Cell key={i} fill={COULEURS[i%COULEURS.length]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );

  if (type === "area" && cleNum && cleCateg) return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data.slice(0,50)}>
        <CartesianGrid strokeDasharray="3 3" stroke={dark ? "#374151" : "#F3F4F6"} />
        <XAxis dataKey={cleCateg} tick={axisStyle} />
        <YAxis tick={axisStyle} tickFormatter={formaterValeur} />
        <Tooltip {...tooltipStyle} formatter={formaterValeur} />
        <Area type="monotone" dataKey={cleNum} stroke="#3B82F6" fill="#3B82F620" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );

  // Table par défaut
  return (
    <div className="overflow-x-auto max-h-52 mt-2">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className={dark ? "bg-gray-700/80" : "bg-gray-100"}>
            {colonnes.slice(0,7).map(c => (
              <th key={c} className={`text-left px-3 py-2 font-semibold border-b ${dark ? "border-gray-600 text-gray-300" : "border-gray-200 text-gray-600"}`}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.slice(0,30).map((row,i) => (
            <tr key={i} className={`transition-colors ${dark ? "hover:bg-gray-700/50 border-gray-700/50" : "hover:bg-gray-50 border-gray-100"} border-b`}>
              {colonnes.slice(0,7).map(c => (
                <td key={c} className={`px-3 py-2 ${dark ? "text-gray-300" : "text-gray-700"}`}>
                  {String(row[c] ?? "").slice(0,30)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ════════════════════════════════════════
// ONGLET TABLEAU DE BORD — SAISIE
// ════════════════════════════════════════

function OngletDashboard({ dark, onPoserQuestion, chargement, erreur }) {
  const [question, setQuestion] = useState("");

  const suggestions = [
    "Top 10 clients par solde",
    "Crédits en défaut",
    "Transactions frauduleuses par banque",
    "Alertes critiques",
    "Clients diaspora France",
    "Volume transactions par ville",
    "Nombre de clients par banque",
    "Crédits en retard",
  ];

  const envoyer = (texte) => {
    const q = (texte || question).trim();
    if (!q) return;
    setQuestion("");
    onPoserQuestion(q);
  };

  return (
    <div className="space-y-6">
      {/* Zone de saisie */}
      <div className={`rounded-2xl border p-6 ${dark ? "border-slate-800 bg-slate-900/60" : "border-slate-200 bg-white shadow-sm"}`}>
        <h2 className={`text-sm font-semibold uppercase tracking-widest mb-5 ${dark ? "text-blue-400" : "text-blue-600"}`}>
          Poser une question
        </h2>
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center">
          <BoutonMicro onTranscription={t => envoyer(t)} dark={dark} />
          <div className="flex-1 flex gap-3">
            <input
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => e.key === "Enter" && envoyer()}
              placeholder="Posez votre question en français…"
              className={`flex-1 rounded-xl border px-4 py-3 text-sm outline-none transition-all ${
                dark ? "border-slate-700 bg-slate-800 text-white placeholder-slate-500 focus:border-blue-500"
                     : "border-slate-200 bg-slate-50 text-slate-900 placeholder-slate-400 focus:border-blue-500"
              }`}
            />
            <button
              onClick={() => envoyer()}
              disabled={chargement || !question.trim()}
              className="px-5 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-xl transition-all flex items-center gap-2"
            >
              {chargement ? <RefreshCw size={16} className="animate-spin" /> : <Search size={16} />}
              Analyser
            </button>
          </div>
        </div>

        {/* Suggestions */}
        <div className="mt-5 flex flex-wrap gap-2">
          {suggestions.map(label => (
            <button key={label} onClick={() => envoyer(label)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-all ${
                dark ? "border-slate-700 bg-slate-800 text-slate-300 hover:border-blue-500 hover:text-blue-400"
                     : "border-slate-200 bg-white text-slate-600 hover:border-blue-500 hover:text-blue-600"
              }`}>
              {label}
            </button>
          ))}
        </div>

        {erreur && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400">
            <AlertTriangle size={14} />
            {erreur}
          </div>
        )}
      </div>

      {/* Guide */}
      <div className={`rounded-2xl border p-5 ${dark ? "border-slate-800 bg-slate-900/40" : "border-slate-200 bg-slate-50"}`}>
        <h3 className={`text-xs font-semibold uppercase tracking-widest mb-3 ${dark ? "text-slate-400" : "text-slate-500"}`}>
          Guide rapide
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { icon: Mic, label: "Voix ou texte", desc: "Posez votre question en français." },
            { icon: History, label: "Historique", desc: "Retrouvez toutes vos analyses dans l'onglet Historique." },
            { icon: FileText, label: "Rapport PDF", desc: "Sélectionnez des entrées et exportez un rapport." },
          ].map(({ icon: Icon, label, desc }) => (
            <div key={label} className={`rounded-xl p-4 ${dark ? "bg-slate-800/60" : "bg-white border border-slate-200"}`}>
              <div className="flex items-center gap-2 mb-1.5">
                <Icon size={14} className="text-blue-500" />
                <span className={`text-xs font-semibold ${dark ? "text-white" : "text-slate-800"}`}>{label}</span>
              </div>
              <p className={`text-xs ${dark ? "text-slate-400" : "text-slate-500"}`}>{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════
// CARTE RÉSULTAT MINIATURE (dans historique)
// ════════════════════════════════════════

function CarteResultatMini({ item, dark, selectionne, onBasculer }) {
  const [ouvert, setOuvert] = useState(false);

  const badgeSource = {
    rag:    { label: "RAG",    cls: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300" },
    rule:   { label: "Règle",  cls: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" },
    gemini: { label: "Gemini", cls: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
  }[item.source] || { label: item.source, cls: "bg-gray-100 text-gray-600" };

  return (
    <div className={`rounded-2xl border transition-all duration-200 overflow-hidden ${
      selectionne
        ? dark ? "border-blue-500 bg-blue-900/20 shadow-md shadow-blue-500/10" : "border-blue-400 bg-blue-50/80 shadow-md shadow-blue-100"
        : dark ? "border-slate-700 bg-slate-800/60 hover:border-slate-600" : "border-slate-200 bg-white hover:border-slate-300 shadow-sm"
    }`}>
      {/* En-tête cliquable (sélection) */}
      <div
        className="flex items-start gap-4 p-4 cursor-pointer"
        onClick={() => onBasculer(item.id)}
      >
        {/* Checkbox personnalisée */}
        <div className={`mt-0.5 flex-shrink-0 w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all ${
          selectionne ? "bg-blue-600 border-blue-600" : dark ? "border-slate-600" : "border-slate-300"
        }`}>
          {selectionne && <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 12 12" stroke="currentColor" strokeWidth={2.5}><path d="M2 6l3 3 5-5"/></svg>}
        </div>

        {/* Contenu */}
        <div className="flex-1 min-w-0">
          <p className={`font-semibold text-sm leading-snug ${dark ? "text-white" : "text-slate-900"}`}>
            {item.question}
          </p>

          {/* Meta ligne 1 */}
          <div className="flex flex-wrap items-center gap-3 mt-2">
            <span className={`inline-flex items-center gap-1 text-xs ${dark ? "text-slate-400" : "text-slate-500"}`}>
              <Calendar size={11} /> {formaterDate(item.timestamp)}
            </span>
            <span className={`inline-flex items-center gap-1 text-xs ${dark ? "text-slate-400" : "text-slate-500"}`}>
              <Clock size={11} /> {formaterHeure(item.timestamp)}
            </span>
            <span className={`inline-flex items-center gap-1 text-xs ${dark ? "text-slate-400" : "text-slate-500"}`}>
              <TrendingUp size={11} /> {item.duree_ms}ms
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badgeSource.cls}`}>
              {badgeSource.label}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              dark ? "bg-slate-700 text-slate-300" : "bg-slate-100 text-slate-600"
            }`}>
              {item.total} ligne{item.total !== 1 ? "s" : ""} · {item.colonnes?.length || 0} col.
            </span>
          </div>

          {/* SQL raccourci */}
          <div className={`mt-2 text-xs font-mono truncate px-2 py-1 rounded-lg ${dark ? "bg-slate-700/60 text-blue-300" : "bg-slate-100 text-blue-600"}`}>
            {item.sql?.slice(0, 120)}{item.sql?.length > 120 ? "…" : ""}
          </div>
        </div>

        {/* Toggle expand */}
        <button
          onClick={e => { e.stopPropagation(); setOuvert(!ouvert); }}
          className={`mt-0.5 flex-shrink-0 p-1.5 rounded-lg transition-colors ${
            dark ? "hover:bg-slate-700 text-slate-400" : "hover:bg-slate-100 text-slate-400"
          }`}
        >
          {ouvert ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </button>
      </div>

      {/* Détails expandables */}
      {ouvert && (
        <div className={`border-t px-4 pb-4 pt-3 ${dark ? "border-slate-700/60" : "border-slate-100"}`}>
          {/* SQL complet */}
          <div className="mb-3">
            <p className={`text-xs font-semibold mb-1.5 ${dark ? "text-slate-400" : "text-slate-500"}`}>Requête SQL</p>
            <pre className={`text-xs p-3 rounded-xl overflow-x-auto whitespace-pre-wrap ${dark ? "bg-slate-900 text-blue-300" : "bg-slate-50 text-blue-700 border border-slate-200"}`}>
              {item.sql}
            </pre>
          </div>

          {/* Visualisation */}
          {item.data && item.data.length > 0 ? (
            <div>
              <p className={`text-xs font-semibold mb-2 ${dark ? "text-slate-400" : "text-slate-500"}`}>
                Résultats — {item.total} lignes
              </p>
              <GraphiqueDynamique colonnes={item.colonnes} data={item.data} dark={dark} />
            </div>
          ) : (
            <p className={`text-xs ${dark ? "text-slate-500" : "text-slate-400"}`}>Aucun résultat pour cette requête.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════
// ONGLET HISTORIQUE
// ════════════════════════════════════════

function OngletHistorique({ historique, dark, onVider }) {
  const [selection, setSelection] = useState(new Set());
  const [generationPDF, setGenerationPDF] = useState(false);
  const [filtre, setFiltre] = useState("tous");
  const [recherche, setRecherche] = useState("");

  // Filtrage
  const historiqueFiltré = historique.filter(item => {
    const matchRecherche = !recherche || item.question.toLowerCase().includes(recherche.toLowerCase());
    const matchFiltre = filtre === "tous" || item.source === filtre;
    return matchRecherche && matchFiltre;
  });

  const basculerSelection = (id) => {
    setSelection(prev => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  const toutSelectionner = () => {
    if (selection.size === historiqueFiltré.length && historiqueFiltré.length > 0) {
      setSelection(new Set());
    } else {
      setSelection(new Set(historiqueFiltré.map(i => i.id)));
    }
  };

  const genererPDF = async () => {
    if (selection.size === 0) return;
    setGenerationPDF(true);

    try {
      const pdf = new jsPDF({ orientation:"portrait", unit:"mm", format:"a4" });
      const selectedItems = historique.filter(item => selection.has(item.id));
      const now = new Date();
      const pageH = pdf.internal.pageSize.getHeight();
      const margin = 15;
      const maxW = 180;

      // ── Page de couverture ──────────────────────────
      // Fond bleu en-tête
      pdf.setFillColor(37, 99, 235);
      pdf.rect(0, 0, 210, 55, "F");

      pdf.setTextColor(255, 255, 255);
      pdf.setFont(undefined, "bold");
      pdf.setFontSize(22);
      pdf.text("VoiceBank Analytics", margin, 22);

      pdf.setFont(undefined, "normal");
      pdf.setFontSize(12);
      pdf.text("Rapport d'Analyse — Historique des Requêtes", margin, 32);

      pdf.setFontSize(9);
      pdf.text(`Généré le ${now.toLocaleString("fr-FR")}`, margin, 42);
      pdf.text(`${selection.size} entrée${selection.size > 1 ? "s" : ""} sélectionnée${selection.size > 1 ? "s" : ""}`, margin, 49);

      // Résumé
      pdf.setTextColor(0, 0, 0);
      pdf.setFontSize(10);
      pdf.setFont(undefined, "bold");
      pdf.text("Résumé du rapport", margin, 68);

      pdf.setDrawColor(37, 99, 235);
      pdf.setLineWidth(0.5);
      pdf.line(margin, 70, 195, 70);

      pdf.setFont(undefined, "normal");
      pdf.setFontSize(9);
      pdf.setTextColor(80, 80, 80);
      const totalResultats = selectedItems.reduce((s, i) => s + (i.total || 0), 0);
      const moy = selectedItems.length > 0 ? Math.round(selectedItems.reduce((s,i) => s + (i.duree_ms||0), 0) / selectedItems.length) : 0;
      pdf.text(`• Nombre de requêtes : ${selection.size}`, margin, 78);
      pdf.text(`• Total de lignes retournées : ${totalResultats.toLocaleString("fr")}`, margin, 84);
      pdf.text(`• Durée moyenne d'exécution : ${moy}ms`, margin, 90);

      const sources = {};
      selectedItems.forEach(i => { sources[i.source] = (sources[i.source]||0)+1; });
      let yS = 96;
      Object.entries(sources).forEach(([src, nb]) => {
        pdf.text(`• Source ${src} : ${nb} requête${nb>1?"s":""}`, margin, yS);
        yS += 6;
      });

      let yPos = yS + 10;

      // ── Entrées ─────────────────────────────────────
      selectedItems.forEach((item, index) => {
        if (yPos > pageH - 40) { pdf.addPage(); yPos = margin; }

        // Bandeau numéro
        pdf.setFillColor(245, 247, 250);
        pdf.rect(margin - 2, yPos - 4, maxW + 4, 8, "F");
        pdf.setDrawColor(37, 99, 235);
        pdf.setLineWidth(0.3);
        pdf.rect(margin - 2, yPos - 4, maxW + 4, 8);

        pdf.setFont(undefined, "bold");
        pdf.setFontSize(10);
        pdf.setTextColor(37, 99, 235);
        pdf.text(`[ ${index + 1} ] Question`, margin, yPos + 1);
        yPos += 10;

        // Question
        pdf.setFont(undefined, "bold");
        pdf.setFontSize(10);
        pdf.setTextColor(0, 0, 0);
        const qLines = pdf.splitTextToSize(item.question, maxW);
        pdf.text(qLines, margin, yPos);
        yPos += qLines.length * 5 + 2;

        // Méta
        const dateStr = new Date(item.timestamp).toLocaleString("fr-FR");
        pdf.setFont(undefined, "normal");
        pdf.setFontSize(8);
        pdf.setTextColor(100, 100, 100);
        pdf.text(`📅 ${dateStr}   ⏱ ${item.duree_ms}ms   🔍 ${item.source.toUpperCase()}   📊 ${item.total} résultats · ${item.colonnes?.length||0} colonnes`, margin, yPos);
        yPos += 6;

        // SQL
        if (yPos > pageH - 30) { pdf.addPage(); yPos = margin; }
        pdf.setFont(undefined, "bold");
        pdf.setFontSize(8);
        pdf.setTextColor(37, 99, 235);
        pdf.text("Requête SQL :", margin, yPos);
        yPos += 4;

        pdf.setFont("courier", "normal");
        pdf.setFontSize(7.5);
        pdf.setTextColor(40, 40, 40);
        const sqlLines = pdf.splitTextToSize(item.sql || "", maxW);
        // fond code
        const hCode = sqlLines.length * 3.2 + 4;
        if (yPos + hCode > pageH - 15) { pdf.addPage(); yPos = margin; }
        pdf.setFillColor(248, 250, 252);
        pdf.rect(margin - 1, yPos - 1, maxW + 2, hCode, "F");
        pdf.text(sqlLines, margin + 1, yPos + 2);
        yPos += hCode + 3;

        // Aperçu données
        if (item.data && item.data.length > 0) {
          if (yPos > pageH - 20) { pdf.addPage(); yPos = margin; }
          pdf.setFont(undefined, "bold");
          pdf.setFontSize(8);
          pdf.setTextColor(37, 99, 235);
          pdf.text("Aperçu des données (3 premières lignes) :", margin, yPos);
          yPos += 4;

          pdf.setFont("courier", "normal");
          pdf.setFontSize(7);
          pdf.setTextColor(60, 60, 60);
          const preview = item.data.slice(0,3).map(row =>
            Object.values(row).map(v => String(v).slice(0,20)).join(" | ").slice(0,90)
          );
          preview.forEach(line => {
            if (yPos > pageH - 15) { pdf.addPage(); yPos = margin; }
            pdf.text(line, margin, yPos);
            yPos += 4;
          });
          yPos += 2;
        }

        // Séparateur
        if (yPos > pageH - 20) { pdf.addPage(); yPos = margin; }
        pdf.setDrawColor(220, 220, 220);
        pdf.setLineWidth(0.3);
        pdf.line(margin, yPos, 195, yPos);
        yPos += 8;
      });

      // Footer sur chaque page
      const totalPages = pdf.internal.getNumberOfPages();
      for (let p = 1; p <= totalPages; p++) {
        pdf.setPage(p);
        pdf.setFontSize(7.5);
        pdf.setFont(undefined, "normal");
        pdf.setTextColor(160, 160, 160);
        pdf.text("VoiceBank Analytics — Rapport confidentiel", margin, pageH - 7);
        pdf.text(`Page ${p} / ${totalPages}`, 195, pageH - 7, { align: "right" });
      }

      const filename = `VoiceBank_Rapport_${now.toISOString().slice(0,10)}_${String(now.getHours()).padStart(2,"0")}h${String(now.getMinutes()).padStart(2,"0")}.pdf`;
      pdf.save(filename);
    } catch (e) {
      console.error("Erreur PDF:", e);
      alert("Erreur lors de la génération du PDF.");
    } finally {
      setGenerationPDF(false);
    }
  };

  const toutsSélectionnés = historiqueFiltré.length > 0 && selection.size === historiqueFiltré.length;

  return (
    <div className="space-y-5">
      {/* Barre d'outils */}
      <div className={`rounded-2xl border p-4 ${dark ? "border-slate-800 bg-slate-900/60" : "border-slate-200 bg-white shadow-sm"}`}>
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          {/* Recherche */}
          <div className="relative flex-1">
            <Search size={14} className={`absolute left-3 top-1/2 -translate-y-1/2 ${dark ? "text-slate-500" : "text-slate-400"}`} />
            <input
              value={recherche}
              onChange={e => setRecherche(e.target.value)}
              placeholder="Rechercher dans l'historique…"
              className={`w-full pl-9 pr-4 py-2.5 text-sm rounded-xl border outline-none transition-all ${
                dark ? "bg-slate-800 border-slate-700 text-white placeholder-slate-500 focus:border-blue-500"
                     : "bg-slate-50 border-slate-200 text-slate-900 placeholder-slate-400 focus:border-blue-500"
              }`}
            />
          </div>

          {/* Filtres source */}
          <div className="flex gap-1.5">
            {["tous","rag","rule","gemini"].map(f => (
              <button key={f} onClick={() => setFiltre(f)}
                className={`text-xs px-3 py-2 rounded-xl font-medium transition-all ${
                  filtre === f
                    ? "bg-blue-600 text-white shadow-sm"
                    : dark ? "bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700"
                           : "bg-slate-100 text-slate-600 hover:bg-slate-200 border border-slate-200"
                }`}>
                {f === "tous" ? "Tous" : f === "rag" ? "RAG" : f === "rule" ? "Règle" : "Gemini"}
              </button>
            ))}
          </div>
        </div>

        {/* Actions sélection */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-700/30">
          <div className="flex items-center gap-3">
            <button
              onClick={toutSelectionner}
              className={`flex items-center gap-2 text-xs font-medium px-3 py-2 rounded-xl transition-all ${
                dark ? "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                     : "bg-slate-100 hover:bg-slate-200 text-slate-600 border border-slate-200"
              }`}
            >
              {toutsSélectionnés
                ? <CheckSquare size={13} className="text-blue-500" />
                : <Square size={13} />}
              {toutsSélectionnés ? "Tout désélectionner" : "Tout sélectionner"}
            </button>

            {selection.size > 0 && (
              <span className={`text-xs font-semibold px-3 py-1.5 rounded-xl bg-blue-600/10 text-blue-500 border border-blue-500/20`}>
                {selection.size} sélectionné{selection.size > 1 ? "s" : ""}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onVider}
              className={`flex items-center gap-1.5 text-xs px-3 py-2 rounded-xl font-medium transition-all ${
                dark ? "bg-red-900/30 hover:bg-red-900/50 text-red-400 border border-red-900/40"
                     : "bg-red-50 hover:bg-red-100 text-red-600 border border-red-200"
              }`}
            >
              <Trash2 size={13} />
              Vider
            </button>

            <button
              onClick={genererPDF}
              disabled={selection.size === 0 || generationPDF}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl font-semibold text-sm transition-all ${
                selection.size === 0 || generationPDF
                  ? "opacity-40 cursor-not-allowed bg-blue-600 text-white"
                  : "bg-blue-600 hover:bg-blue-700 active:scale-95 text-white shadow-md shadow-blue-500/20"
              }`}
            >
              {generationPDF
                ? <RefreshCw size={14} className="animate-spin" />
                : <Download size={14} />}
              {generationPDF ? "Génération…" : `Télécharger PDF${selection.size > 0 ? ` (${selection.size})` : ""}`}
            </button>
          </div>
        </div>
      </div>

      {/* Légende */}
      {historiqueFiltré.length > 0 && (
        <p className={`text-xs ${dark ? "text-slate-500" : "text-slate-400"}`}>
          {historiqueFiltré.length} entrée{historiqueFiltré.length > 1 ? "s" : ""} · Cliquez sur une carte pour la sélectionner, sur ↓ pour voir les détails.
        </p>
      )}

      {/* Liste des entrées */}
      {historiqueFiltré.length === 0 ? (
        <div className={`rounded-2xl border p-16 text-center ${dark ? "border-slate-800 bg-slate-900/40" : "border-slate-200 bg-white"}`}>
          <History size={36} className={`mx-auto mb-3 ${dark ? "text-slate-600" : "text-slate-300"}`} />
          <p className={`text-sm font-medium ${dark ? "text-slate-400" : "text-slate-500"}`}>
            {historique.length === 0 ? "Aucun historique pour le moment." : "Aucun résultat pour ce filtre."}
          </p>
          <p className={`text-xs mt-1 ${dark ? "text-slate-600" : "text-slate-400"}`}>
            {historique.length === 0 ? "Posez une question depuis le tableau de bord." : "Modifiez votre recherche ou filtre."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {historiqueFiltré.map(item => (
            <CarteResultatMini
              key={item.id}
              item={item}
              dark={dark}
              selectionne={selection.has(item.id)}
              onBasculer={basculerSelection}
            />
          ))}
        </div>
      )}

      {/* Aide PDF */}
      {historiqueFiltré.length > 0 && (
        <div className={`rounded-xl p-4 text-xs ${dark ? "bg-blue-900/20 border border-blue-800/30 text-blue-300" : "bg-blue-50 border border-blue-200 text-blue-700"}`}>
          💡 <strong>Astuce :</strong> Sélectionnez plusieurs entrées et cliquez sur <em>Télécharger PDF</em> pour générer un rapport professionnel avec la requête SQL, les métadonnées et un aperçu des données pour chaque entrée.
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════
// APP PRINCIPALE
// ════════════════════════════════════════

export default function App() {
  const [dark, setDark]           = useState(true);
  const [onglet, setOnglet]       = useState("dashboard");
  const [historique, setHistorique] = useState([]);
  const { appeler, chargement, erreur } = useAPI();

  // Restaurer historique
  useEffect(() => {
    try {
      const saved = localStorage.getItem(CLE_STORAGE);
      if (saved) setHistorique(JSON.parse(saved));
    } catch {}
  }, []);

  // Sauvegarder historique
  useEffect(() => {
    try { localStorage.setItem(CLE_STORAGE, JSON.stringify(historique)); } catch {}
  }, [historique]);

  const poserQuestion = async (texte) => {
    const res = await appeler("post", "/vocal/question", { texte, langue: "fr" });
    if (!res) return;

    const nouvelItem = {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      question: texte,
      sql: res.sql || "",
      source: res.source || "unknown",
      colonnes: res.colonnes || [],
      total: res.total ?? (Array.isArray(res.data) ? res.data.length : 0),
      data: res.data || [],
      duree_ms: res.duree_ms ?? 0,
    };

    setHistorique(prev => [nouvelItem, ...prev]);
    // Basculer vers l'historique pour voir le résultat
    setOnglet("historique");
  };

  const toutEffacer = () => {
    if (window.confirm("Supprimer tout l'historique ?")) {
      setHistorique([]);
      localStorage.removeItem(CLE_STORAGE);
    }
  };

  const tabs = [
    { id: "dashboard",  label: "Tableau de bord", icon: LayoutDashboard },
    { id: "historique", label: "Historique",        icon: History,
      badge: historique.length > 0 ? historique.length : null },
  ];

  return (
    <div className={`${dark ? "bg-slate-950 text-white" : "bg-slate-50 text-slate-900"} min-h-screen`}>

      {/* HEADER */}
      <header className={`sticky top-0 z-20 border-b backdrop-blur-md ${dark ? "border-slate-800 bg-slate-950/95" : "border-slate-200 bg-white/95"}`}>
        <div className="mx-auto max-w-5xl px-6">
          <div className="flex items-center justify-between py-4">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-2xl bg-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                <Database size={18} className="text-white" />
              </div>
              <div>
                <p className={`text-sm font-bold ${dark ? "text-white" : "text-slate-900"}`}>VoiceBank Analytics</p>
                <p className={`text-xs ${dark ? "text-slate-400" : "text-slate-500"}`}>Nguebou Temgoua Rayan · v3</p>
              </div>
            </div>

            {/* Navigation onglets (desktop) */}
            <nav className="hidden sm:flex items-center gap-1 bg-slate-800/40 rounded-2xl p-1">
              {tabs.map(({ id, label, icon: Icon, badge }) => (
                <button
                  key={id}
                  onClick={() => setOnglet(id)}
                  className={`relative flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                    onglet === id
                      ? "bg-blue-600 text-white shadow-md"
                      : dark ? "text-slate-400 hover:text-white hover:bg-slate-700/50"
                             : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                  }`}
                >
                  <Icon size={14} />
                  {label}
                  {badge && (
                    <span className={`text-xs px-1.5 py-0.5 rounded-full font-semibold ${
                      onglet === id ? "bg-white/20 text-white" : "bg-blue-600 text-white"
                    }`}>
                      {badge > 99 ? "99+" : badge}
                    </span>
                  )}
                </button>
              ))}
            </nav>

            {/* Bouton thème */}
            <button
              onClick={() => setDark(!dark)}
              className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition-all ${
                dark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              {dark ? <Sun size={15} /> : <Moon size={15} />}
              <span className="hidden sm:inline">{dark ? "Clair" : "Sombre"}</span>
            </button>
          </div>

          {/* Navigation mobile */}
          <div className="flex sm:hidden gap-1 pb-3">
            {tabs.map(({ id, label, icon: Icon, badge }) => (
              <button
                key={id}
                onClick={() => setOnglet(id)}
                className={`relative flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium transition-all ${
                  onglet === id
                    ? "bg-blue-600 text-white"
                    : dark ? "text-slate-400 bg-slate-800/50" : "text-slate-600 bg-slate-100"
                }`}
              >
                <Icon size={13} />
                {label}
                {badge && (
                  <span className={`text-xs px-1 rounded-full ${onglet === id ? "bg-white/25 text-white" : "bg-blue-600 text-white"}`}>
                    {badge}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* MAIN */}
      <main className="mx-auto max-w-5xl px-6 py-8">
        {/* Indicateur de chargement global */}
        {chargement && (
          <div className="fixed top-20 right-6 z-30 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-medium shadow-xl shadow-blue-500/20">
            <RefreshCw size={14} className="animate-spin" />
            Analyse en cours…
          </div>
        )}

        {onglet === "dashboard" && (
          <OngletDashboard
            dark={dark}
            onPoserQuestion={poserQuestion}
            chargement={chargement}
            erreur={erreur}
          />
        )}

        {onglet === "historique" && (
          <OngletHistorique
            historique={historique}
            dark={dark}
            onVider={toutEffacer}
          />
        )}
      </main>
    </div>
  );
}
