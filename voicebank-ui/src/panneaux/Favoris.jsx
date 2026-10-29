// Questions favorites : étoile sur une réponse pour la garder, relance en un clic, envoi chaque lundi par e-mail.
import { useState, useEffect, useCallback } from "react";
import { Star, Mail, X } from "lucide-react";
import { http, messageErreur } from "../api";
import { tx } from "../i18n";

const cle = (question, idSource) => `${idSource || 0}|${question.trim().toLowerCase()}`;

export function useFavoris(actif) {
  const [liste, setListe] = useState([]);
  const [erreur, setErreur] = useState(null);
  const charger = useCallback(() => {
    if (!actif) return;
    http.get("/favoris", { silencieux: true }).then(r => setListe(r.data.data)).catch(() => {});
  }, [actif]);
  useEffect(charger, [charger]);

  const agir = async action => {
    setErreur(null);
    try { await action(); charger(); return true; } catch (e) { setErreur(messageErreur(e)); return false; }
  };
  const trouve = (question, idSource) => liste.find(f => cle(f.question, f.id_source) === cle(question, idSource));
  return {
    liste, erreur, trouve,
    basculer: (question, idSource, devise) => {
      const f = trouve(question, idSource);
      return agir(() => f ? http.post(`/favoris/${f.id}/supprimer`)
        : http.post("/favoris", { question, id_source: idSource || 0, devise: devise || "XAF" }));
    },
    envoi: (f, envoiHebdo) => agir(() => http.post(`/favoris/${f.id}`, { envoi_hebdo: envoiHebdo })),
    supprimer: f => agir(() => http.post(`/favoris/${f.id}/supprimer`)),
  };
}

// Étoile dans l'en-tête d'une réponse
export function BoutonFavori({ actif, onClick, dark }) {
  return (
    <button onClick={e => { e.stopPropagation(); onClick(); }} aria-pressed={actif}
      aria-label={actif ? tx("Retirer des favoris") : tx("Ajouter aux favoris")} title={actif ? tx("Retirer des favoris") : tx("Ajouter aux favoris")}
      className={`p-1.5 rounded-lg ${dark ? "hover:bg-gray-600" : "hover:bg-gray-100"} ${actif ? "text-laiton-400" : dark ? "text-gray-400" : "text-gray-400"}`}>
      <Star size={13} fill={actif ? "currentColor" : "none"} />
    </button>
  );
}

// Favoris de la base choisie, sous la zone de saisie
export function BarreFavoris({ favoris, idSource, onPoser, desactive, dark }) {
  const [ouvert, setOuvert] = useState(null);       // favori dont les réglages sont affichés
  const ici = favoris.liste.filter(f => (f.id_source || 0) === (idSource || 0));
  if (!ici.length) return null;
  return (
    <div className="mt-4">
      <p className={`text-xs mb-2 flex items-center gap-1 ${dark ? "text-gray-400" : "text-gray-500"}`}>
        <Star size={12} />{" "}{tx("Mes favoris")}
      </p>
      <ul className="flex flex-wrap gap-2">
        {ici.map(f => (
          <li key={f.id} className={`flex items-center rounded-full border text-xs ${dark ? "border-laiton-700 text-gray-200" : "border-laiton-300 text-gray-700"}`}>
            <button onClick={() => onPoser(f.question)} disabled={desactive} className="pl-3 pr-1 py-1.5 hover:underline disabled:opacity-50">
              {f.question}</button>
            {f.envoi_hebdo && <Mail size={11} className="text-laiton-500" aria-label={tx("envoyé chaque lundi")} />}
            <button onClick={() => setOuvert(ouvert === f.id ? null : f.id)} aria-expanded={ouvert === f.id}
              aria-label={tx("Réglages du favori « {question} »", { question: f.question })} className="px-2 py-1.5 opacity-70 hover:opacity-100">⋯</button>
            {ouvert === f.id && (
              <span className="flex items-center gap-2 pr-2">
                <label className="flex items-center gap-1 cursor-pointer">
                  <input type="checkbox" checked={f.envoi_hebdo} onChange={e => favoris.envoi(f, e.target.checked)} />
                  {tx("chaque lundi par e-mail")}
                </label>
                <button onClick={() => favoris.supprimer(f)} aria-label={tx("Retirer « {question} » des favoris", { question: f.question })}
                  className="text-red-400 hover:text-red-500"><X size={12} /></button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {favoris.erreur && <p role="alert" className="text-xs text-red-400 mt-1">{favoris.erreur}</p>}
    </div>
  );
}
