// VOICEBANK ANALYTICS — Interface React v2
// Auteur : Nguebou Temgoua Rayan
// Corrections : historique avec sélection et export PDF

import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { jsPDF } from "jspdf";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer
} from "recharts";
import {
  Mic, MicOff, Sun, Moon, RefreshCw, Send,
  Database, ExternalLink,
  Trash2, ChevronDown, ChevronUp, Download
} from "lucide-react";

const API         = "http://localhost:8000";
const CLE_STORAGE = "voicebank_historique";
const COULEURS    = ["#3B82F6","#10B981","#F59E0B","#EF4444","#8B5CF6","#06B6D4","#F97316","#84CC16","#EC4899","#14B8A6"];

function detecterTypeGraphique(colonnes, data) {
  if (!data || data.length === 0) return "table";
  const cols = colonnes.map(c => c.toLowerCase());
  const aDate  = cols.some(c => c.includes("date") || c.includes("mois"));
  const aNombre = cols.some(c => c.includes("count") || c.includes("nb_") || c.includes("total") || c.includes("montant") || c.includes("solde") || c.includes("volume"));
  const aCateg = cols.some(c => c.includes("banque") || c.includes("ville") || c.includes("statut") || c.includes("type") || c.includes("pays") || c.includes("canal"));
  if (data.length === 1) return "kpi";
  if (aDate && aNombre) return "line";
  if (aCateg && aNombre && data.length <= 15) return "bar";
  if (aCateg && data.length <= 8 && !aNombre) return "pie";
  if (aNombre && data.length > 15) return "area";
  return "table";
}

function trouverCleNumerique(row) {
  const priorites = ["montant_fcfa","solde_fcfa","nb_clients","nb_transactions","total","count","volume","score"];
  for (const p of priorites) {
    for (const k of Object.keys(row)) {
      if (k.toLowerCase().includes(p)) return k;
    }
  }
  return Object.keys(row).find(k => typeof row[k] === "number" && !isNaN(row[k]));
}

function trouverCleCateg(row) {
  const priorites = ["banque","ville","statut","type","pays","canal","nom","prenom"];
  for (const p of priorites) {
    for (const k of Object.keys(row)) {
      if (k.toLowerCase().includes(p)) return k;
    }
  }
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
      const msg = e.response?.data?.detail || e.message;
      setErreur(msg);
      return null;
    } finally {
      setChargement(false);
    }
  }, []);

  return { appeler, chargement, erreur };
}

// ════════════════════════════════════════
// COMPOSANT — HISTORIQUE AVEC SÉLECTION ET PDF
// ════════════════════════════════════════

function HistoriquePanel({ historique, dark }) {
  const [selection, setSelection] = useState(new Set());
  const [generationPDF, setGenerationPDF] = useState(false);

  const basculerSelection = (id) => {
    const newSelection = new Set(selection);
    if (newSelection.has(id)) {
      newSelection.delete(id);
    } else {
      newSelection.add(id);
    }
    setSelection(newSelection);
  };

  const basculerTous = () => {
    if (selection.size === historique.length) {
      setSelection(new Set());
    } else {
      setSelection(new Set(historique.map(item => item.id)));
    }
  };

  const genererPDF = async () => {
    if (selection.size === 0) {
      alert("Sélectionne au moins un historique à exporter.");
      return;
    }

    setGenerationPDF(true);
    try {
      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4'
      });

      const selectedItems = historique.filter(item => selection.has(item.id));
      const now = new Date();
      const dateRapport = now.toLocaleString('fr-FR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });

      pdf.setFontSize(16);
      pdf.setFont(undefined, 'bold');
      pdf.text('VoiceBank Analytics — Rapport d\'Historique', 15, 15);

      pdf.setFontSize(10);
      pdf.setFont(undefined, 'normal');
      pdf.text(`Généré le : ${dateRapport}`, 15, 25);
      pdf.text(`Entrées sélectionnées : ${selection.size}`, 15, 32);

      let yPos = 40;
      const pageHeight = pdf.internal.pageSize.getHeight();
      const margin = 15;
      const maxWidth = 180;

      selectedItems.forEach((item, index) => {
        if (yPos > pageHeight - 30) {
          pdf.addPage();
          yPos = margin;
        }

        pdf.setFont(undefined, 'bold');
        pdf.setFontSize(11);
        pdf.setTextColor(59, 130, 246);
        pdf.text(`[${index + 1}] Question`, margin, yPos);
        yPos += 6;

        pdf.setFont(undefined, 'normal');
        pdf.setFontSize(10);
        pdf.setTextColor(0, 0, 0);
        const questions = pdf.splitTextToSize(item.question, maxWidth);
        pdf.text(questions, margin, yPos);
        yPos += questions.length * 4 + 2;

        const dateItem = new Date(item.timestamp);
        const dateHeureStr = dateItem.toLocaleString('fr-FR', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit'
        });
        pdf.setFontSize(9);
        pdf.setTextColor(107, 114, 128);
        pdf.text(`📅 ${dateHeureStr}`, margin, yPos);
        yPos += 5;

        pdf.text(`⏱️ ${item.duree_ms}ms | 🔍 Source: ${item.source}`, margin, yPos);
        yPos += 5;

        pdf.setFont(undefined, 'bold');
        pdf.setFontSize(9);
        pdf.setTextColor(59, 130, 246);
        pdf.text('Requête SQL :', margin, yPos);
        yPos += 4;

        pdf.setFont(undefined, 'normal');
        pdf.setFontSize(8);
        pdf.setTextColor(55, 65, 81);
        const sqlLines = pdf.splitTextToSize(item.sql, maxWidth);
        pdf.text(sqlLines, margin, yPos);
        yPos += sqlLines.length * 3 + 2;

        pdf.setFont(undefined, 'bold');
        pdf.setFontSize(9);
        pdf.setTextColor(59, 130, 246);
        pdf.text(`Résultats : ${item.total} lignes`, margin, yPos);
        yPos += 4;

        if (item.data && item.data.length > 0) {
          pdf.setFont(undefined, 'normal');
          pdf.setFontSize(8);
          pdf.setTextColor(0, 0, 0);
          const previewLines = item.data.slice(0, 3).map(row => {
            const vals = Object.values(row).map(v => String(v).substring(0, 20)).join(' | ');
            return vals.substring(0, 80);
          });
          pdf.text(previewLines, margin, yPos);
          yPos += previewLines.length * 3 + 4;
        }

        pdf.setDrawColor(200, 200, 200);
        pdf.line(margin, yPos, 195, yPos);
        yPos += 6;
      });

      pdf.setFontSize(8);
      pdf.setTextColor(150, 150, 150);
      pdf.text('VoiceBank Analytics © 2024 — Rapport généré automatiquement', 15, pageHeight - 10);

      const filename = `VoiceBank_Historique_${now.toISOString().slice(0, 10)}_${now.getHours()}h${now.getMinutes()}m.pdf`;
      pdf.save(filename);
    } catch (error) {
      console.error('Erreur génération PDF:', error);
      alert('Erreur lors de la génération du PDF.');
    } finally {
      setGenerationPDF(false);
    }
  };

  return (
    <div className={`rounded-2xl border p-6 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
      <div className="flex items-center justify-between mb-6">
        <h2 className={`text-lg font-bold ${dark ? "text-white" : "text-gray-900"}`}>
          📋 Historique complet
        </h2>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={selection.size === historique.length && historique.length > 0}
              onChange={basculerTous}
              className="w-4 h-4 rounded"
            />
            <span className={`text-sm ${dark ? "text-gray-300" : "text-gray-600"}`}>
              {selection.size > 0 ? `${selection.size}/${historique.length}` : "Tous"}
            </span>
          </label>
          <button
            onClick={genererPDF}
            disabled={selection.size === 0 || generationPDF}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all ${
              selection.size === 0 || generationPDF
                ? "opacity-50 cursor-not-allowed"
                : "bg-blue-600 hover:bg-blue-700 text-white"
            }`}
          >
            <Download size={15} />
            {generationPDF ? "Génération..." : `Rapport PDF (${selection.size})`}
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <div className="space-y-3">
          {historique.length === 0 ? (
            <div className={`text-center py-8 ${dark ? "text-gray-500" : "text-gray-400"}`}>
              <p className="text-sm">Aucun historique pour le moment</p>
            </div>
          ) : (
            historique.map((item) => {
              const dateItem = new Date(item.timestamp);
              const dateStr = dateItem.toLocaleDateString('fr-FR');
              const heureStr = dateItem.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
              const estSelectionnee = selection.has(item.id);

              return (
                <div
                  key={item.id}
                  className={`p-4 rounded-lg border transition-all cursor-pointer ${
                    estSelectionnee
                      ? dark ? "bg-blue-900/30 border-blue-600" : "bg-blue-50 border-blue-400"
                      : dark ? "bg-gray-700 border-gray-600 hover:bg-gray-650" : "bg-gray-50 border-gray-200 hover:bg-gray-100"
                  }`}
                  onClick={() => basculerSelection(item.id)}
                >
                  <div className="flex items-start gap-4">
                    <input
                      type="checkbox"
                      checked={estSelectionnee}
                      onChange={() => basculerSelection(item.id)}
                      className="w-5 h-5 mt-1 rounded cursor-pointer"
                    />

                    <div className="flex-1 min-w-0">
                      <p className={`font-medium text-sm truncate ${dark ? "text-white" : "text-gray-900"}`}>
                        {item.question}
                      </p>

                      <div className={`flex items-center gap-4 text-xs mt-2 ${dark ? "text-gray-400" : "text-gray-500"}`}>
                        <span>📅 {dateStr}</span>
                        <span>🕐 {heureStr}</span>
                        <span>⏱️ {item.duree_ms}ms</span>
                        <span className={`px-2 py-0.5 rounded-full ${
                          item.source === 'rag'
                            ? dark ? "bg-purple-900 text-purple-300" : "bg-purple-100 text-purple-700"
                            : item.source === 'rule'
                            ? dark ? "bg-green-900 text-green-300" : "bg-green-100 text-green-700"
                            : dark ? "bg-blue-900 text-blue-300" : "bg-blue-100 text-blue-700"
                        }`}>
                          {item.source === 'rag' ? '🔄 RAG' : item.source === 'rule' ? '⚡ Règle' : '🤖 Gemini'}
                        </span>
                      </div>

                      <p className={`text-xs mt-2 truncate font-mono ${dark ? "text-gray-500" : "text-gray-400"}`}>
                        SQL: {item.sql.substring(0, 100)}...
                      </p>

                      <p className={`text-xs mt-1 ${dark ? "text-gray-400" : "text-gray-500"}`}>
                        📊 {item.total} lignes • {item.colonnes?.length || 0} colonnes
                      </p>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {historique.length > 0 && (
        <div className={`mt-4 p-3 rounded-lg text-xs ${dark ? "bg-gray-700 text-gray-300" : "bg-gray-100 text-gray-600"}`}>
          💡 Sélectionne les historiques à inclure dans le rapport PDF. Les rapports contiennent la question, la requête SQL, la date/heure et un aperçu des résultats.
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
  const [question, setQuestion]   = useState("");
  const [historique, setHistorique] = useState([]);
  const [onglet, setOnglet]       = useState("historique");
  const { appeler, chargement }   = useAPI();

  useEffect(() => {
    try {
      const sauvegarde = localStorage.getItem(CLE_STORAGE);
      if (sauvegarde) setHistorique(JSON.parse(sauvegarde));
    } catch (e) {}
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(CLE_STORAGE, JSON.stringify(historique));
    } catch (e) {}
  }, [historique]);

  const poserQuestion = async (texte, clearInput = true) => {
    const q = (texte || question).trim();
    if (!q) return;
    if (clearInput) setQuestion("");

    const res = await appeler("post", "/vocal/question", { texte: q, langue: "fr" });
    if (!res) {
      alert("Impossible de récupérer le résultat. Vérifie que l'API fonctionne.");
      return;
    }

    const nouvelItem = {
      id        : Date.now(),
      timestamp : new Date().toISOString(),
      question  : q,
      sql       : res.sql,
      source    : res.source,
      colonnes  : res.colonnes,
      total     : res.total,
      data      : res.data,
      duree_ms  : res.duree_ms,
    };

    setHistorique(prev => [nouvelItem, ...prev]);
  };

  const toutEffacer = () => {
    setHistorique([]);
    localStorage.removeItem(CLE_STORAGE);
  };

  return (
    <div className={`min-h-screen transition-colors duration-300 ${dark ? "bg-gray-900" : "bg-gray-50"}`}>

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
        <button
          onClick={() => setDark(!dark)}
          className={`p-2 rounded-xl transition-all ${dark ? "bg-gray-700 hover:bg-gray-600 text-gray-300" : "bg-gray-100 hover:bg-gray-200 text-gray-600"}`}
        >
          {dark ? <Sun size={15} /> : <Moon size={15} />}
        </button>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-6">

        <div className={`rounded-2xl border p-5 mb-6 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
          <div className="flex gap-2 mb-4">
            <input
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => e.key === "Enter" && poserQuestion()}
              placeholder="Pose ta question en français..."
              className={`flex-1 px-4 py-3 rounded-xl border text-sm outline-none transition-all ${
                dark
                  ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400 focus:border-blue-500"
                  : "bg-gray-50 border-gray-200 text-gray-900 focus:border-blue-500"
              }`}
            />
            <button
              onClick={() => poserQuestion()}
              disabled={chargement || !question.trim()}
              className="px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl transition-all disabled:opacity-50"
            >
              {chargement ? <RefreshCw size={15} className="animate-spin" /> : <Send size={15} />}
            </button>
          </div>
        </div>

        <HistoriquePanel historique={historique} dark={dark} />

        <footer className={`mt-12 py-6 text-center text-xs ${dark ? "text-gray-500" : "text-gray-400"}`}>
          &copy; {new Date().getFullYear()} VoiceBank Analytics. Tous droits réservés. By Rayan NT.
        </footer>   
      </main>
    </div>
  );
}
