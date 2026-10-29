// Suivi des alertes (statut, personne assignée, commentaires), fiches des modèles, rapports PDF et notifications.
import { useState, useEffect, useCallback } from "react";
import { UserRound, MessageSquare, History, FileDown, BellRing, ClipboardCheck, ShieldCheck, TriangleAlert, Gauge, Save } from "lucide-react";
import { http } from "../api";
import { useAPI } from "../useAPI";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";
import { LOCALE, tx } from "../i18n";

export const STATUTS = {
  nouvelle: { libelle: tx("Nouvelle"), couleur: "bg-sky-500/15 text-sky-600 dark:text-sky-300" },
  en_cours: { libelle: tx("En cours"), couleur: "bg-amber-500/15 text-amber-600" },
  fraude_confirmee: { libelle: tx("Fraude confirmée"), couleur: "bg-red-500/15 text-red-600" },
  fausse_alerte: { libelle: tx("Fausse alerte"), couleur: "bg-gray-500/15 text-gray-500" },
  resolue: { libelle: tx("Résolue"), couleur: "bg-emerald-500/15 text-emerald-600" },
};
export const OUVERTS = ["nouvelle", "en_cours"];

export function ChipStatut({ statut }) {
  const s = STATUTS[statut];
  if (!s) return null;
  return <span className={`text-[11px] px-1.5 py-0.5 rounded font-medium whitespace-nowrap ${s.couleur}`}>{s.libelle}</span>;
}

// ── Traitement d'une alerte ────────────────────────────────────────────
export function SuiviAlerte({ source, idSuivi, dark, onChange }) {
  const lecture = useAPI();
  const action = useAPI();
  const [d, setD] = useState(null);
  const [commentaire, setCommentaire] = useState("");
  const charger = useCallback(() => {
    lecture.appeler("get", `/sources/${source.id}/alertes/${idSuivi}`).then(r => r && setD(r));
  }, [lecture.appeler, source.id, idSuivi]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  const envoyer = async corps => {
    const r = await action.appeler("post", `/sources/${source.id}/alertes/${idSuivi}`, corps);
    if (r) {
      setD(x => ({ ...x, data: r.data }));
      setCommentaire("");
      onChange && onChange(r.data);
    }
  };

  if (lecture.erreur) return <p className="text-sm text-red-500">{lecture.erreur}</p>;
  if (!d) return <p className={texteDiscret(dark)}>{tx("Chargement du suivi…")}</p>;
  const a = d.data;
  const ouvert = OUVERTS.includes(a.statut);
  const verdict = statut => {
    if (!commentaire.trim()) { action.setErreur(tx("Explique ton verdict en une phrase dans le commentaire : il sert de retour au modèle et de trace pour l'audit.")); return; }
    envoyer({ statut, commentaire });
  };
  return (
    <div className={`mt-3 rounded-xl border p-4 space-y-3 ${dark ? "border-gray-600 bg-gray-800/60" : "border-gray-200 bg-white"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck size={15} className="text-foret-500" />
        <span className="text-sm font-semibold">{tx("Suivi de l'alerte")}</span>
        <ChipStatut statut={a.statut} />
        <span className={texteDiscret(dark)}>{tx("détectée le {x}", { x: formaterDate(a.date_detection) })}</span>
      </div>
      {d.peut_traiter ? (
        <>
          <div className="grid sm:grid-cols-2 gap-3">
            <label>
              <span className={`${etiquette(dark)} flex items-center gap-1`}><UserRound size={12} />{" "}{tx("Assignée à")}</span>
              <select aria-label={tx("Assigner l'alerte")} value={a.assigne_a || ""} disabled={action.chargement}
                onChange={e => envoyer(e.target.value ? { assigne_a: e.target.value } : { desassigner: true })} className={champ(dark)}>
                <option value="">{tx("Personne")}</option>
                {d.assignables.map(p => <option key={p.nom} value={p.nom}>{p.nom_complet}</option>)}
              </select>
            </label>
            <label>
              <span className={`${etiquette(dark)} flex items-center gap-1`}><MessageSquare size={12} />{" "}{tx("Commentaire (obligatoire pour un verdict)")}</span>
              <textarea value={commentaire} onChange={e => setCommentaire(e.target.value)} rows={2} maxLength={2000}
                placeholder={tx("Ex. : client joint par téléphone, opération confirmée.")} className={champ(dark)} />
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            {ouvert ? (
              <>
                <button disabled={action.chargement} onClick={() => verdict("fraude_confirmee")}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-700 text-white disabled:opacity-50">{tx("Fraude confirmée")}</button>
                <button disabled={action.chargement} onClick={() => verdict("fausse_alerte")} className={boutonSecondaire(dark)}>{tx("Fausse alerte")}</button>
                <button disabled={action.chargement} onClick={() => envoyer({ statut: "resolue", commentaire: commentaire || undefined })}
                  className={boutonSecondaire(dark)}>{tx("Résolue")}</button>
              </>
            ) : (
              <button disabled={action.chargement} onClick={() => envoyer({ statut: "en_cours", commentaire: commentaire || undefined })}
                className={boutonSecondaire(dark)}>{tx("Rouvrir")}</button>
            )}
            <button disabled={action.chargement || !commentaire.trim()} onClick={() => envoyer({ commentaire })}
              className={boutonSecondaire(dark)}>{tx("Ajouter le commentaire")}</button>
          </div>
          {action.erreur && <p role="alert" className="text-sm text-red-500">{action.erreur}</p>}
        </>
      ) : (
        <p className={`${texteDiscret(dark)} [overflow-wrap:anywhere]`}>{tx("Ton rôle permet de consulter les alertes, pas de les traiter.")}{a.assigne_a ? tx(" Assignée à {assigne_a}.", { assigne_a: a.assigne_a }) : ""}</p>
      )}
      {a.historique.length > 0 && (
        <div>
          <p className={`${etiquette(dark)} flex items-center gap-1`}><History size={12} />{" "}{tx("Historique")}</p>
          <ol className="space-y-1.5">
            {a.historique.map((h, i) => (
              <li key={i} className="text-xs flex flex-wrap gap-x-2 gap-y-0.5 min-w-0">
                <span className={`${texteDiscret(dark)} whitespace-nowrap`}>{formaterDate(h.date_commentaire)}</span>
                <span className="font-medium min-w-0 [overflow-wrap:anywhere]">{h.auteur}</span>
                <span className={`min-w-0 [overflow-wrap:anywhere] ${h.nature === "commentaire" ? "" : texteDiscret(dark)}`}>{h.texte}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

// ── Rapport PDF ────────────────────────────────────────────────────────
export function BoutonsRapport({ source, dark }) {
  const [en, setEn] = useState(null);
  const [erreur, setErreur] = useState(null);
  const telecharger = async periode => {
    setEn(periode); setErreur(null);
    try {
      const r = await http.get(`/sources/${source.id}/rapport`, { params: { periode }, responseType: "blob", timeout: 120000 });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = (r.headers["content-disposition"] || "").match(/filename="([^"]+)"/)?.[1] || `rapport_${periode}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setErreur(tx("Rapport indisponible pour le moment.")); }
    finally { setEn(null); }
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      {[["semaine", tx("Rapport de la semaine")], ["mois", tx("Rapport du mois")]].map(([p, l]) => (
        <button key={p} onClick={() => telecharger(p)} disabled={!!en} className={`${boutonSecondaire(dark)} flex items-center gap-1.5`}>
          <FileDown size={13} /> {en === p ? tx("Préparation…") : tx("{l} (PDF)", { l })}
        </button>
      ))}
      {erreur && <span className="text-xs text-red-500">{erreur}</span>}
    </div>
  );
}

// ── Fiche des modèles ─────────────────────────────────────────────────
const ETATS_DERIVE = {
  stable: [tx("Stable"), "text-emerald-600 bg-emerald-500/10"],
  a_surveiller: [tx("À surveiller"), "text-amber-600 bg-amber-500/10"],
  forte: [tx("Dérive forte"), "text-red-600 bg-red-500/10"],
};

function Ligne({ libelle, children, dark }) {
  return (
    <div className="grid sm:grid-cols-[11rem_1fr] gap-x-4 gap-y-0.5 py-2 border-b last:border-0 border-gray-500/15">
      <span className={texteDiscret(dark)}>{libelle}</span>
      <div className="text-sm min-w-0">{children}</div>
    </div>
  );
}

function FicheModele({ f, dark }) {
  if (!f) return null;
  if (f.indisponible && !f.nom) return null;
  const don = f.donnees || {};
  const fia = f.fiabilite || {};
  const der = f.derive || {};
  return (
    <div className={carte(dark)}>
      <h2 className={`${titre(dark)} flex items-center gap-2`}><ClipboardCheck size={18} className="text-foret-500" /> {f.nom}</h2>
      <p className={`${texteDiscret(dark)} mb-3`}>{f.objectif}</p>
      {f.indisponible && <p className="text-sm text-amber-600 mb-3">{f.indisponible}</p>}
      <Ligne libelle={tx("Méthode")} dark={dark}>{f.methode}</Ligne>
      <Ligne libelle={tx("Données")} dark={dark}>
        {tx("« {table} » · {x} lignes", { table: don.table, x: Number(don.operations ?? don.credits ?? 0).toLocaleString(LOCALE) })}
        {don.periode ? tx(" · du {x} au {x2}", { x: new Date(don.periode[0]).toLocaleDateString(LOCALE), x2: new Date(don.periode[1]).toLocaleDateString(LOCALE) }) : ""}
        {don.variables?.length > 0 && <span className={`block ${texteDiscret(dark)}`}>{tx("Variables :")}{" "}{don.variables.join(", ")}</span>}
        {don.donnees_personnelles && <span className={`block ${texteDiscret(dark)}`}>{tx("Données personnelles : {donnees_personnelles}", { donnees_personnelles: don.donnees_personnelles })}</span>}
      </Ligne>
      <Ligne libelle={tx("Apprentissage")} dark={dark}>
        {f.appris_le ? tx("Le {x}", { x: formaterDate(f.appris_le) }) : tx("Date non enregistrée")}{f.reapprentissage ? ` · ${f.reapprentissage}` : ""}
      </Ligne>
      {f.seuils?.length > 0 && (
        <Ligne libelle={tx("Seuils d'alerte")} dark={dark}>
          {f.seuils.map(s => <span key={s.niveau} className="block">{tx(s.niveau)} : {s.regle || tx("rang ≥ {rang} ({part})", { rang: Number(s.rang).toLocaleString(LOCALE), part: s.part })}</span>)}
        </Ligne>
      )}
      <Ligne libelle={tx("Fiabilité")} dark={dark}>
        {fia.explication || (fia.auc == null && !fia.fraudes_connues ? tx("Pas de fraudes ou de défauts connus dans la base pour la mesurer : vos verdicts sur les alertes la mesureront.") : "—")}
        {fia.avertissement && <span className="block text-amber-600 text-xs mt-1">{fia.avertissement}</span>}
      </Ligne>
      {f.verdicts && (
        <Ligne libelle={tx("Vos verdicts")} dark={dark}>
          {f.verdicts.verdicts
            ? tx("{verdicts} alerte(s) jugée(s) · {x} % de vraies fraudes", { verdicts: f.verdicts.verdicts, x: Math.round((f.verdicts.precision || 0) * 100) })
            : tx("Aucun verdict pour l'instant : classe les alertes (fraude confirmée / fausse alerte) pour mesurer la précision.")}
          {f.verdicts.notification && <span className={`block ${texteDiscret(dark)}`}>{tx("E-mails immédiats :")}{" "}{f.verdicts.notification.niveaux.map(n => tx(n)).join(tx(" et "))} · {f.verdicts.notification.raison}</span>}
        </Ligne>
      )}
      {der.etat && (
        <Ligne libelle={tx("Dérive des données")} dark={dark}>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded ${ETATS_DERIVE[der.etat][1]}`}>{ETATS_DERIVE[der.etat][0]}</span>
          <span className="block mt-1">{der.detail}</span>
          <span className={`block ${texteDiscret(dark)}`}>
            {tx("{periode_recente} comparés aux précédents · indice PSI", { periode_recente: der.periode_recente })}{" "}{String(der.indice).replace(".", ",")}{" "}{tx("(stable sous 0,1 ; forte au-delà de 0,25)")}
          </span>
        </Ligne>
      )}
      {f.limites?.length > 0 && (
        <Ligne libelle={tx("Limites")} dark={dark}>
          <ul className="list-disc pl-4 space-y-0.5">{f.limites.map(l => <li key={l}>{l}</li>)}</ul>
        </Ligne>
      )}
    </div>
  );
}

export function PanelFiches({ source, dark }) {
  const { appeler, chargement, erreur } = useAPI();
  const [d, setD] = useState(null);
  useEffect(() => {
    setD(null);
    appeler("get", `/sources/${source ? source.id : 0}/modeles`, null, { timeout: 120000 }).then(r => r && setD(r.data));
  }, [appeler, source]);
  if (erreur) return <p className="text-sm text-red-500">{erreur}</p>;
  if (!d || chargement) return <p className={texteDiscret(dark)}>{tx("Préparation des fiches…")}</p>;
  return (
    <div className="space-y-4">
      <div className={`${carte(dark)} flex gap-3`}>
        <Gauge size={18} className="text-laiton-400 flex-shrink-0 mt-0.5" />
        <p className={`text-sm ${dark ? "text-gray-300" : "text-gray-700"}`}>
          {tx("Ces fiches décrivent chaque modèle d'IA utilisé sur")}{" "}{source ? `« ${source.nom} »` : tx("la démonstration")}{" "}{tx(": données, méthode, seuils, fiabilité mesurée et dérive. Elles servent à la conformité (validation des modèles) et à savoir quelle confiance accorder aux alertes.")}
        </p>
      </div>
      <FicheModele f={d.operations} dark={dark} />
      <FicheModele f={d.credits} dark={dark} />
    </div>
  );
}

// ── Préférences de notification ───────────────────────────────────────
const CHOIX = [
  ["alertes_critiques", tx("Alertes graves, dès qu'elles sont détectées"), tx("Les opérations les plus atypiques de vos bases (règle ajustée selon vos verdicts).")],
  ["resume_quotidien", tx("Résumé du matin (7 h)"), tx("Nouvelles alertes des dernières 24 h, alertes à traiter, celles qui vous sont assignées.")],
  ["rapport_hebdo", tx("Rapport hebdomadaire (PDF, le lundi)"), tx("Synthèse, points d'attention, alertes ouvertes, portefeuille de crédits.")],
  ["rapport_mensuel", tx("Rapport mensuel (PDF, le 1er du mois)"), tx("Le même rapport sur le mois, pour la direction et la conformité.")],
];

export function PanelNotifications({ dark }) {
  const lecture = useAPI();
  const ecriture = useAPI();
  const [d, setD] = useState(null);
  const [ok, setOk] = useState(false);
  useEffect(() => { lecture.appeler("get", "/notifications").then(r => r && setD(r)); }, [lecture.appeler]); // eslint-disable-line react-hooks/exhaustive-deps
  if (lecture.erreur) return <p className="text-sm text-red-500">{lecture.erreur}</p>;
  if (!d) return <p className={texteDiscret(dark)}>{tx("Chargement…")}</p>;
  const enregistrer = async () => {
    setOk(false);
    if (await ecriture.appeler("post", "/notifications", d.data)) setOk(true);
  };
  return (
    <div className={`${carte(dark)} max-w-2xl`}>
      <h2 className={`${titre(dark)} flex items-center gap-2`}><BellRing size={18} className="text-laiton-400" />{" "}{tx("Ce que je reçois par e-mail")}</h2>
      <p className={`${texteDiscret(dark)} mb-4`}>
        {d.email ? tx("Envois à {email}.", { email: d.email }) : tx("Aucune adresse e-mail sur ton compte : ajoute-en une pour recevoir ces envois.")}
        {d.email && !d.envoi_possible && tx(" L'envoi d'e-mails n'est pas encore configuré sur le serveur.")}
        {tx("{x}La surveillance des bases de ton organisation tourne chaque heure.", { x: " " })}
      </p>
      <div className="space-y-2">
        {CHOIX.map(([cle, libelle, aide]) => (
          <label key={cle} className={`flex items-start gap-3 p-3 rounded-xl cursor-pointer ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
            <input type="checkbox" className="mt-1" checked={!!d.data[cle]} onChange={e => { setOk(false); setD({ ...d, data: { ...d.data, [cle]: e.target.checked } }); }} />
            <span>
              <span className="text-sm font-medium block">{libelle}</span>
              <span className={texteDiscret(dark)}>{aide}</span>
            </span>
          </label>
        ))}
      </div>
      <div className="flex items-center gap-3 mt-4">
        <button onClick={enregistrer} disabled={ecriture.chargement} className={`${boutonPrincipal} flex items-center gap-2`}><Save size={15} />{" "}{tx("Enregistrer")}</button>
        {ok && <span className="text-sm text-emerald-500">{tx("Préférences enregistrées.")}</span>}
        {ecriture.erreur && <span className="text-sm text-red-500">{ecriture.erreur}</span>}
      </div>
    </div>
  );
}

export function NoteDemo({ dark }) {
  return (
    <p className={`${texteDiscret(dark)} flex items-center gap-1.5`}><TriangleAlert size={12} />{" "}{tx("Le suivi (statut, assignation, verdicts) concerne les bases de ton organisation.")}</p>
  );
}
