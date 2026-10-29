// « Bien démarrer » : guide l'administrateur d'une nouvelle organisation jusqu'à une première réponse utile.
import { useState, useEffect } from "react";
import { CircleCheck, Circle, X, Rocket } from "lucide-react";
import { http } from "../api";
import { tx } from "../i18n";

export default function Demarrage({ dark, utilisateur, acces, nbSources, nbQuestions, allerA }) {
  const cle = `voicebank_demarrage_${utilisateur}`;
  const [masque, setMasque] = useState(() => { try { return localStorage.getItem(cle) === "non"; } catch (e) { return false; } });
  const [membres, setMembres] = useState(null);
  useEffect(() => {
    http.get("/organisation").then(r => setMembres(r.data.data.membres.length)).catch(() => {});
  }, []);
  const etapes = [
    { fait: nbSources > 0, titre: tx("Brancher les données de l'organisation"), texte: tx("Base PostgreSQL, MySQL, SQL Server ou fichiers Excel / CSV."), page: "donnees", action: tx("Mes données") },
    { fait: !!acces?.source_defaut, titre: tx("Choisir la base par défaut"), texte: tx("Tous les membres arrivent directement dessus."), page: "donnees", action: tx("Définir") },
    { fait: (membres || 0) > 1, titre: tx("Inviter l'équipe"), texte: tx("Chaque analyste reçoit un e-mail pour activer son compte."), page: "organisation", action: tx("Inviter") },
    { fait: nbQuestions > 0, titre: tx("Poser une première question"), texte: tx("Par exemple : « Montant total par mois »."), page: null },
  ];
  const faites = etapes.filter(e => e.fait).length;
  if (masque || faites === etapes.length) return null;
  const fermer = () => { setMasque(true); try { localStorage.setItem(cle, "non"); } catch (e) { /* rien */ } };
  return (
    <div className={`rounded-2xl border p-5 mb-6 ${dark ? "bg-foret-900/30 border-foret-700" : "bg-foret-50 border-foret-200"}`}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h2 className={`font-bold flex items-center gap-2 ${dark ? "text-white" : "text-gray-900"}`}><Rocket size={17} className="text-laiton-400" />{" "}{tx("Bien démarrer")}</h2>
          <p className={`text-xs ${dark ? "text-gray-400" : "text-gray-600"}`}>{tx("{faites} étape", { faites })}{faites > 1 ? "s" : ""}{" "}{tx("sur {length} : quelques minutes pour mettre VoiceBank au service de ton organisation.", { length: etapes.length })}</p>
        </div>
        <button onClick={fermer} aria-label={tx("Masquer le guide")} className="opacity-60 hover:opacity-100"><X size={15} /></button>
      </div>
      <ol className="grid sm:grid-cols-2 gap-2">
        {etapes.map((e, i) => (
          <li key={e.titre} className={`flex items-start gap-3 p-3 rounded-xl ${dark ? "bg-gray-800/60" : "bg-white"}`}>
            {e.fait ? <CircleCheck size={18} className="text-emerald-500 flex-shrink-0 mt-0.5" /> : <Circle size={18} className="text-gray-400 flex-shrink-0 mt-0.5" />}
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium ${e.fait ? "line-through opacity-60" : ""}`}>{i + 1}. {e.titre}</p>
              <p className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>{e.texte}</p>
            </div>
            {!e.fait && e.page && (
              <button onClick={() => allerA(e.page)} className="px-2.5 py-1 rounded-lg bg-foret-600 hover:bg-foret-700 text-white text-xs font-semibold flex-shrink-0">{e.action}</button>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
