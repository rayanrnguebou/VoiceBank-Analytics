// Graphiques des réponses : type choisi d'après les données, version écran et version PDF, indicateurs.
import { libelleColonne } from "./devise";
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { LOCALE, tx } from "./i18n";

export const COULEURS     = ["#1F654D","#C9A13B","#3E6FB0","#B5523B","#6A8F3A","#7A5BA6","#2F9C95","#D08A2E","#5D6B66","#A43E6C"];
export const SOURCES = {
  rag:    { label: "RAG",    classe: "bg-emerald-100 text-emerald-700" },
  rule:   { label: tx("Règle"),  classe: "bg-amber-100 text-amber-700" },
  gemini: { label: "Gemini", classe: "bg-foret-100 text-foret-700" },
};

export function detecterTypeGraphique(colonnes, data) {
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

export function trouverCleNumerique(row, sql) {
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

export function trouverCleCateg(row) {
  const priorites = ["banque","ville","statut","type","pays","canal","nom","prenom"];
  // Mot entier : « nom » ne doit pas désigner la colonne « nombre »
  const contient = (k, p) => k.toLowerCase().split(/[^a-z0-9]+/).includes(p);
  for (const p of priorites)
    for (const k of Object.keys(row))
      if (contient(k, p) && typeof row[k] !== "number") return k;
  const cles = Object.keys(row);
  return cles.find(k => typeof row[k] === "string") || cles.find(k => /(^id_|_id$|^id$)/i.test(k));
}

export function formaterValeur(val) {
  if (typeof val === "number") {
    if (val > 1_000_000) return (val / 1_000_000).toFixed(1) + "M";
    if (val > 1_000)     return (val / 1_000).toFixed(1) + "k";
    return val.toLocaleString(LOCALE);
  }
  return String(val ?? "");
}

// ════════════════════════════════════════
// COMPOSANT — GRAPHIQUES DASHBOARD
// ════════════════════════════════════════

export function PanelGraphiques({ dark, stats }) {
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

export function GraphiqueDynamique({ colonnes, data, question, dark, sql, item }) {
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

export function GraphiquePourPDF({ colonnes, data, sql, item }) {
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
