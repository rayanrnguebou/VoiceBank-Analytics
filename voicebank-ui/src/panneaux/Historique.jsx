// Historique des questions : cartes de résultat, recherche, sélection, export PDF et CSV.
import { useState, useRef } from "react";
import { useLectureSeule, TITRE_LECTURE_SEULE } from "../lectureSeule";
import { FormulaireSignalement, EditeurCorrection } from "./Admin";
import { lireAVoixHaute, telechargerCsv, nomFichier } from "../ui";
import { RefreshCw, Trash2, ChevronDown, ChevronUp, Download, History, CheckSquare, Square, FileText, AlertTriangle, Volume2, Flag, Wrench, CornerDownRight, Calendar, Clock, Timer, ChartColumn, ChartLine, ChartPie, ChartArea, Gauge, Table2, BookCheck, Zap, Sparkles } from "lucide-react";
import { LOCALE, tx } from "../i18n";
import { SOURCES, detecterTypeGraphique, GraphiqueDynamique, GraphiquePourPDF } from "../graphiques";

export const CLE_STORAGE  = "voicebank_historique";
export const MAX_HISTORIQUE = 30;      // entrées conservées
export const MAX_LIGNES_HISTO = 200;   // lignes de données gardées par entrée

// Historique en sessionStorage (effacé à la fermeture de l'onglet et à la déconnexion) :
// il contient des données clients, il ne doit pas rester dans le navigateur.
export function chargerHistorique(utilisateur) {
  try { return JSON.parse(sessionStorage.getItem(`${CLE_STORAGE}_${utilisateur}`) || "[]"); }
  catch (e) { return []; }
}
export function sauverHistorique(utilisateur, historique) {
  try {
    const compact = historique.slice(0, MAX_HISTORIQUE)
      .map(h => ({ ...h, data: (h.data || []).slice(0, MAX_LIGNES_HISTO) }));
    sessionStorage.setItem(`${CLE_STORAGE}_${utilisateur}`, JSON.stringify(compact));
  } catch (e) { /* quota dépassé ou stockage indisponible */ }
}

// ════════════════════════════════════════
// UTILITAIRES
// ════════════════════════════════════════

export function CarteResultat({ item, dark, onSupprimer, role }) {
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

export function PanelHistorique({ historique, dark, onSupprimerItem, onToutEffacer }) {
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
