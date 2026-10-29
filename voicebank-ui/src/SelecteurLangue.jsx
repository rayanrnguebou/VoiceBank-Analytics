import { Languages } from "lucide-react";
import { LANGUE, LANGUES, changerLangue, tx } from "./i18n";

// Choix de la langue de l'interface (la page se recharge, la session est conservée)
export default function SelecteurLangue({ className = "", sombre = true }) {
  return (
    <label className={`inline-flex items-center gap-1.5 ${className}`}>
      <Languages size={14} aria-hidden="true" className={sombre ? "text-gray-400" : "text-gray-500"} />
      <select aria-label={tx("Langue")} value={LANGUE} onChange={e => changerLangue(e.target.value)}
        className={`text-xs rounded px-1.5 py-0.5 border ${sombre ? "bg-gray-800 border-gray-700 text-gray-200" : "bg-white border-gray-300 text-gray-700"}`}>
        {LANGUES.map(([code, nom]) => <option key={code} value={code}>{nom}</option>)}
      </select>
    </label>
  );
}
