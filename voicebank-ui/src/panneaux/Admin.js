// Outils d'amélioration continue : signaler / corriger une réponse, apprentissage (RAG),
// fiabilité mesurée et journal d'audit.
import { useState, useEffect, useCallback, useRef } from "react";
import { useAPI } from "../useAPI";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";

// ── Signaler une réponse fausse (tous les utilisateurs) ─────────────
export function FormulaireSignalement({ item, dark, onFermer }) {
  const { appeler, chargement, erreur } = useAPI();
  const [commentaire, setCommentaire] = useState("");
  const [envoye, setEnvoye] = useState(false);

  const envoyer = async () => {
    const res = await appeler("post", "/signalements", {
      question: item.question, sql: item.sql, source: item.source, commentaire: commentaire || null,
    });
    if (res) setEnvoye(true);
  };

  if (envoye) return <p className="text-xs text-emerald-500 mt-2">Merci, un administrateur va vérifier cette réponse.</p>;
  return (
    <div className="mt-3 space-y-2">
      <input value={commentaire} onChange={e => setCommentaire(e.target.value)} maxLength={1000} autoFocus
        placeholder="Qu'est-ce qui est faux ? (ex. : il manque le filtre sur Douala)" className={champ(dark)} />
      <div className="flex gap-2">
        <button onClick={envoyer} disabled={chargement} className={boutonPrincipal}>Envoyer le signalement</button>
        <button onClick={onFermer} className={boutonSecondaire(dark)}>Annuler</button>
      </div>
      {erreur && <p className="text-xs text-red-500">{erreur}</p>}
    </div>
  );
}

// ── Corriger une réponse (administrateur) : tester puis enregistrer dans le RAG ─────
export function EditeurCorrection({ question: q0, sql: sql0, idSignalement, dark, onTermine }) {
  const test = useAPI();
  const enreg = useAPI();
  const [question, setQuestion] = useState(q0 || "");
  const [sql, setSql] = useState(sql0 || "");
  const [apercu, setApercu] = useState(null);
  const [ok, setOk] = useState(false);

  const tester = async () => {
    setApercu(null);
    const res = await test.appeler("post", "/sql/executer", { sql });
    if (res) setApercu(res);
  };
  const enregistrer = async () => {
    const res = await enreg.appeler("post", "/vocal/corriger", { question, sql_correct: sql, id_signalement: idSignalement || null });
    if (res) { setOk(true); onTermine && onTermine(); }
  };

  if (ok) return <p className="text-xs text-emerald-500 mt-2">Correction enregistrée : la prochaine question similaire utilisera cette requête.</p>;
  return (
    <div className={`mt-3 p-3 rounded-xl space-y-2 ${dark ? "bg-gray-900/40" : "bg-blue-50"}`}>
      <label className="block">
        <span className={etiquette(dark)}>Question</span>
        <input value={question} onChange={e => setQuestion(e.target.value)} maxLength={500} className={champ(dark)} />
      </label>
      <label className="block">
        <span className={etiquette(dark)}>Requête SQL correcte (SELECT sur le schéma voicebank)</span>
        <textarea value={sql} onChange={e => { setSql(e.target.value); setApercu(null); }} rows={4} maxLength={5000}
          spellCheck={false} className={`${champ(dark)} font-mono text-xs`} />
      </label>
      <div className="flex flex-wrap gap-2">
        <button onClick={tester} disabled={test.chargement || !sql.trim()} className={boutonSecondaire(dark)}>
          {test.chargement ? "Test…" : "Tester la requête"}
        </button>
        <button onClick={enregistrer} disabled={!apercu || enreg.chargement || !question.trim()} className={boutonPrincipal}
          title={!apercu ? "Teste d'abord la requête" : ""}>Enregistrer la correction</button>
      </div>
      {test.erreur && <p className="text-xs text-red-500">{test.erreur}</p>}
      {enreg.erreur && <p className="text-xs text-red-500">{enreg.erreur}</p>}
      {apercu && (
        <div className="overflow-x-auto">
          <p className={`${texteDiscret(dark)} mb-1`}>{apercu.total} ligne(s) — aperçu :</p>
          <table className="text-xs w-full">
            <thead><tr>{apercu.colonnes.slice(0, 6).map(c => <th key={c} className={`text-left px-2 py-1 ${dark ? "text-gray-300" : "text-gray-600"}`}>{c}</th>)}</tr></thead>
            <tbody>{apercu.data.slice(0, 3).map((l, i) => (
              <tr key={i}>{apercu.colonnes.slice(0, 6).map(c => <td key={c} className={`px-2 py-1 ${dark ? "text-gray-400" : "text-gray-700"}`}>{String(l[c] ?? "").slice(0, 24)}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Onglet Apprentissage (admin) ─────────────────────
export function PanelApprentissage({ dark }) {
  const { appeler } = useAPI();
  const [signalements, setSignalements] = useState([]);
  const [corrections, setCorrections] = useState([]);
  const [edition, setEdition] = useState(null);

  const charger = useCallback(() => {
    appeler("get", "/signalements?statut=Ouvert").then(r => setSignalements(r ? r.data : []));
    appeler("get", "/rag/corrections?limit=100").then(r => setCorrections(r ? r.data : []));
  }, [appeler]);
  useEffect(() => { charger(); }, [charger]);

  const rejeter = async id => { if (await appeler("post", `/signalements/${id}/traiter`, { statut: "Rejeté" })) charger(); };
  const supprimer = async c => {
    if (!window.confirm(`Supprimer la correction « ${c.question} » ?`)) return;
    if (await appeler("post", `/rag/corrections/${c.id}/supprimer`)) charger();
  };

  return (
    <div className="space-y-4">
      <div className={carte(dark)}>
        <h2 className={titre(dark)}>Réponses signalées ({signalements.length})</h2>
        <p className={`${texteDiscret(dark)} mb-4`}>Corrige-les : la correction est enregistrée et réutilisée automatiquement (RAG).</p>
        {signalements.length === 0 && <p className={texteDiscret(dark)}>Aucun signalement en attente.</p>}
        <div className="space-y-2">
          {signalements.map(s => (
            <div key={s.id_signalement} className={`p-3 rounded-xl ${dark ? "bg-gray-700" : "bg-gray-50"}`}>
              <p className={`text-sm font-medium ${dark ? "text-white" : "text-gray-900"}`}>{s.question}</p>
              <p className={texteDiscret(dark)}>par {s.utilisateur} · {formaterDate(s.date_signalement)} · source {s.source || "?"}</p>
              {s.commentaire && <p className={`text-xs italic mt-1 ${dark ? "text-gray-300" : "text-gray-600"}`}>« {s.commentaire} »</p>}
              {edition === s.id_signalement ? (
                <EditeurCorrection question={s.question} sql={s.requete_sql} idSignalement={s.id_signalement} dark={dark}
                  onTermine={() => setTimeout(() => { setEdition(null); charger(); }, 1200)} />
              ) : (
                <div className="flex gap-2 mt-2">
                  <button onClick={() => setEdition(s.id_signalement)} className={boutonSecondaire(dark)}>Corriger</button>
                  <button onClick={() => rejeter(s.id_signalement)} className={boutonSecondaire(dark)}>Rejeter</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className={carte(dark)}>
        <div className="flex items-center justify-between mb-2">
          <h2 className={titre(dark)}>Corrections apprises ({corrections.length})</h2>
          <button onClick={() => setEdition("nouvelle")} className={boutonSecondaire(dark)}>+ Ajouter</button>
        </div>
        {edition === "nouvelle" && <EditeurCorrection dark={dark} onTermine={() => setTimeout(() => { setEdition(null); charger(); }, 1200)} />}
        <div className="divide-y divide-gray-500/20 mt-2">
          {corrections.map(c => (
            <div key={c.id} className="flex items-start justify-between gap-3 py-2">
              <div className="min-w-0">
                <p className={`text-sm ${dark ? "text-gray-200" : "text-gray-800"}`}>{c.question}</p>
                <p className={`text-xs font-mono truncate ${dark ? "text-gray-500" : "text-gray-400"}`}>{c.sql_correct}</p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className={texteDiscret(dark)}>{c.utilisee} util.</span>
                <button onClick={() => supprimer(c)} className="text-xs text-red-500 hover:underline">Supprimer</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Onglet Fiabilité (admin) ─────────────────────────
export function PanelFiabilite({ dark }) {
  const { appeler, erreur } = useAPI();
  const [etat, setEtat] = useState(null);
  const minuterie = useRef(null);

  const charger = useCallback(async () => {
    const r = await appeler("get", "/admin/evaluation");
    if (r) setEtat(r);
    return r;
  }, [appeler]);

  useEffect(() => {
    charger();
    return () => clearInterval(minuterie.current);
  }, [charger]);

  const suivre = () => {
    clearInterval(minuterie.current);
    minuterie.current = setInterval(async () => {
      const r = await charger();
      if (r && !r.en_cours) clearInterval(minuterie.current);
    }, 2000);
  };

  const lancer = async () => { if (await appeler("post", "/admin/evaluation")) { setEtat(e => ({ ...e, en_cours: true })); suivre(); } };

  const d = etat?.derniere;
  const details = d?.details || {};
  const erreursListe = (details.details || []).filter(x => x.statut !== "juste");
  const couleur = t => t >= 85 ? "text-emerald-500" : t >= 60 ? "text-amber-500" : "text-red-500";

  return (
    <div className={carte(dark)}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
        <h2 className={titre(dark)}>Fiabilité des réponses</h2>
        <button onClick={lancer} disabled={etat?.en_cours} className={boutonPrincipal}>
          {etat?.en_cours ? "Évaluation en cours…" : "Lancer l'évaluation"}
        </button>
      </div>
      <p className={`${texteDiscret(dark)} mb-4`}>
        {details.nb_questions || 50} questions de référence : on compare le résultat obtenu au résultat attendu.
      </p>
      {erreur && <p className="text-sm text-red-500">{erreur}</p>}
      {!d ? <p className={texteDiscret(dark)}>Aucune évaluation pour l'instant.</p> : (
        <>
          <div className="flex flex-wrap items-baseline gap-3 mb-4">
            <span className={`text-4xl font-bold ${couleur(Number(d.taux_reussite))}`}>{Number(d.taux_reussite).toFixed(1)} %</span>
            <span className={texteDiscret(dark)}>{d.nb_reussies}/{d.nb_questions} justes · {formaterDate(d.date_evaluation)} · Gemini {d.gemini_actif ? "actif" : "inactif"}</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            {[["Par catégorie", details.par_categorie], ["Par source", details.par_source]].map(([nom, groupe]) => (
              <div key={nom}>
                <p className={`text-xs font-semibold mb-1 ${dark ? "text-gray-300" : "text-gray-700"}`}>{nom}</p>
                {Object.entries(groupe || {}).filter(([, s]) => s.questions).map(([cle, s]) => (
                  <div key={cle} className="flex items-center gap-2 mb-1">
                    <span className={`text-xs w-28 ${dark ? "text-gray-400" : "text-gray-600"}`}>{cle}</span>
                    <div className={`flex-1 h-2 rounded-full overflow-hidden ${dark ? "bg-gray-700" : "bg-gray-200"}`}>
                      <div className="h-full bg-blue-500" style={{ width: `${s.taux || 0}%` }} />
                    </div>
                    <span className={texteDiscret(dark)}>{s.justes}/{s.questions}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
          {!d.gemini_actif && <p className="text-xs text-amber-500 mb-3">Sans clé Gemini, seules les questions couvertes par les règles et le RAG peuvent réussir.</p>}
          {erreursListe.length > 0 && (
            <details>
              <summary className={`text-xs cursor-pointer ${dark ? "text-gray-300" : "text-gray-700"}`}>{erreursListe.length} questions à améliorer</summary>
              <ul className="mt-2 space-y-1">
                {erreursListe.map(x => (
                  <li key={x.id} className={texteDiscret(dark)}>[{x.statut}] {x.question}</li>
                ))}
              </ul>
            </details>
          )}
          {etat.historique?.length > 1 && (
            <p className={`${texteDiscret(dark)} mt-3`}>Historique : {etat.historique.map(h => `${Number(h.taux_reussite).toFixed(0)} %`).join(" ← ")}</p>
          )}
        </>
      )}
    </div>
  );
}

// ── Onglet Audit (admin) ─────────────────────────────
const LIBELLES_ACTIONS = {
  connexion: "Connexion", connexion_refusee: "Connexion refusée", consultation_client: "Fiche client consultée",
  correction_rag: "Correction enregistrée", correction_supprimee: "Correction supprimée", signalement: "Réponse signalée",
  signalement_traite: "Signalement traité", alerte_traitee: "Alerte traitée", evaluation_lancee: "Évaluation lancée",
  score_credit: "Score de crédit consulté",
};

export function PanelAudit({ dark }) {
  const { appeler, erreur } = useAPI();
  const [donnees, setDonnees] = useState(null);
  const [action, setAction] = useState("");

  useEffect(() => {
    appeler("get", `/admin/audit?limit=200${action ? `&action=${encodeURIComponent(action)}` : ""}`).then(r => r && setDonnees(r));
  }, [appeler, action]);

  return (
    <div className="space-y-4">
      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-3`}>Activité des 30 derniers jours</h2>
        {erreur && <p className="text-sm text-red-500">{erreur}</p>}
        <div className="flex flex-wrap gap-3">
          {(donnees?.synthese_30j || []).map(s => (
            <div key={s.utilisateur || "?"} className={`px-4 py-3 rounded-xl ${dark ? "bg-gray-700" : "bg-gray-50"}`}>
              <p className={`text-sm font-semibold ${dark ? "text-white" : "text-gray-900"}`}>{s.utilisateur || "inconnu"}</p>
              <p className={texteDiscret(dark)}>{s.questions} questions · {s.taux_succes} % réussies</p>
            </div>
          ))}
        </div>
      </div>
      <div className={carte(dark)}>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <h2 className={titre(dark)}>Journal d'audit</h2>
          <select value={action} onChange={e => setAction(e.target.value)} className={`${champ(dark)} w-auto`}>
            <option value="">Toutes les actions</option>
            {Object.entries(LIBELLES_ACTIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="overflow-x-auto max-h-96">
          <table className="w-full text-xs">
            <thead><tr className={dark ? "text-gray-400" : "text-gray-500"}>
              <th className="text-left p-2">Date</th><th className="text-left p-2">Utilisateur</th>
              <th className="text-left p-2">Action</th><th className="text-left p-2">Détail</th><th className="text-left p-2">IP</th>
            </tr></thead>
            <tbody>
              {(donnees?.evenements || []).map(e => (
                <tr key={e.id_evenement} className={`border-t ${dark ? "border-gray-700 text-gray-300" : "border-gray-100 text-gray-700"}`}>
                  <td className="p-2 whitespace-nowrap">{formaterDate(e.date_evenement)}</td>
                  <td className="p-2">{e.utilisateur}</td>
                  <td className={`p-2 ${e.action === "connexion_refusee" ? "text-red-500" : ""}`}>{LIBELLES_ACTIONS[e.action] || e.action}</td>
                  <td className="p-2 font-mono">{e.detail && Object.keys(e.detail).length ? JSON.stringify(e.detail).slice(0, 80) : ""}</td>
                  <td className="p-2">{e.adresse_ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-3`}>Dernières questions posées</h2>
        <div className="space-y-1 max-h-72 overflow-y-auto">
          {(donnees?.questions || []).map((q, i) => (
            <p key={i} className={texteDiscret(dark)}>
              <span className={q.succes ? "text-emerald-500" : "text-red-500"}>{q.succes ? "✓" : "✗"}</span>{" "}
              {formaterDate(q.date_requete)} · <strong>{q.utilisateur || "?"}</strong> · {q.question} · {q.duree_ms} ms
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}
