// Recouvrement des crédits en retard : liste priorisée, relances (appel, SMS, WhatsApp avec le message prêt),
// promesses de paiement, paiements reçus, statut et assignation. Les coordonnées viennent de la base connectée.
import { useCallback, useEffect, useMemo, useState } from "react";
import { HandCoins, Phone, MessageSquare, Send, CalendarClock, Banknote, UserRound, ChevronDown, ChevronUp, Download,
  Settings2, Info, Search, ShieldAlert } from "lucide-react";
import { useAPI } from "../useAPI";
import { useDevise } from "../devise";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate,
  telechargerCsv, nomFichier } from "../ui";
import { LOCALE, tx } from "../i18n";

const COULEURS_STATUT = {
  a_contacter: "bg-red-500/15 text-red-600", contacte: "bg-sky-500/15 text-sky-600",
  promesse: "bg-laiton-400/20 text-laiton-600", paiement_partiel: "bg-emerald-500/15 text-emerald-600",
  regle: "bg-emerald-600 text-white", injoignable: "bg-gray-500/15 text-gray-500",
  contentieux: "bg-purple-500/15 text-purple-600", irrecouvrable: "bg-gray-700 text-white",
};
const ONGLETS = [["ouverts", "En cours"], ["promesse", "Promesses"], ["clos", "Clos"], ["tous", "Tous"]];
const pct = v => `${Math.round(Number(v) * 100)} %`;

export function ChipStatutDossier({ statut, libelle }) {
  return <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${COULEURS_STATUT[statut] || ""}`}>{tx(libelle)}</span>;
}

function Tuile({ dark, libelle, valeur, detail, accent }) {
  return (
    <div className={`p-3 rounded-xl ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
      <p className={texteDiscret(dark)}>{libelle}</p>
      <p className={`text-lg font-bold mt-0.5 tabular-nums ${accent || ""}`}>{valeur}</p>
      {detail && <p className={`${texteDiscret(dark)} mt-0.5`}>{detail}</p>}
    </div>
  );
}

function Reglages({ source, reglages, dark, onFini }) {
  const { appeler, chargement, erreur } = useAPI();
  const [r, setR] = useState(reglages);
  const enregistrer = async () => { if (await appeler("post", `/sources/${source}/recouvrement-reglages`, r)) onFini(); };
  return (
    <div className={`mt-4 rounded-xl border p-4 space-y-3 ${dark ? "border-gray-600" : "border-gray-200"}`}>
      <p className="text-sm font-semibold">{tx("Message de relance")}</p>
      <label className="block">
        <span className={etiquette(dark)}>{tx("Comment payer (indiqué dans chaque relance)")}</span>
        <input value={r.paiement} onChange={e => setR({ ...r, paiement: e.target.value })} maxLength={300} className={champ(dark)}
          placeholder={tx("Ex. : Orange Money marchand 123456, MTN MoMo 650 00 00 00 ou https://pay.exemple.cm")} />
      </label>
      <label className="block">
        <span className={etiquette(dark)}>{tx("Signature")}</span>
        <input value={r.signature} onChange={e => setR({ ...r, signature: e.target.value })} maxLength={120} className={champ(dark)}
          placeholder={tx("Ex. : Service recouvrement, Coopérative du Moungo")} />
      </label>
      <label className="block">
        <span className={etiquette(dark)}>{tx("Modèle ({client}, {reference}, {montant}, {paiement}, {signature})")}</span>
        <textarea value={r.modele} onChange={e => setR({ ...r, modele: e.target.value })} rows={3} maxLength={800} className={champ(dark)} />
      </label>
      {erreur && <p role="alert" className="text-xs text-red-500">{erreur}</p>}
      <div className="flex gap-2">
        <button onClick={enregistrer} disabled={chargement} className={boutonPrincipal}>{tx("Enregistrer")}</button>
        <button onClick={onFini} className={boutonSecondaire(dark)}>{tx("Annuler")}</button>
      </div>
    </div>
  );
}

function Dossier({ source, d, liste, dark, onMaj }) {
  const devise = useDevise();
  const lecture = useAPI();
  const action = useAPI();
  const [historique, setHistorique] = useState(null);
  const [message, setMessage] = useState(d.message);
  const [formulaire, setFormulaire] = useState(null);       // promesse | paiement | statut | null
  const [montant, setMontant] = useState("");
  const [datePromesse, setDatePromesse] = useState("");
  const [statut, setStatut] = useState("injoignable");
  const [note, setNote] = useState("");
  const [commentaire, setCommentaire] = useState("");
  const charger = useCallback(() => {
    lecture.appeler("get", `/sources/${source}/recouvrement/${d.id}`).then(r => r && setHistorique(r.historique));
  }, [lecture.appeler, source, d.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  const envoyer = async corps => {
    const r = await action.appeler("post", `/sources/${source}/recouvrement/${d.id}`, corps);
    if (r) {
      setHistorique(r.data.historique); setFormulaire(null); setMontant(""); setNote(""); setDatePromesse(""); setCommentaire("");
      onMaj(r.data);
    }
    return r;
  };
  // Le lien s'ouvre (téléphone, SMS, WhatsApp) et la relance est notée dans l'historique
  const relancer = nature => () => { if (liste.peut_traiter) envoyer({ nature, texte: nature === "appel" ? null : message }); };
  const enc = encodeURIComponent(message);
  const montantNombre = Number(String(montant).replace(/\s/g, "").replace(",", "."));
  const lien = "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold";

  return (
    <div className="px-3 pb-4 pt-1 space-y-3">
      {liste.contact && d.numero ? (
        <div className={`rounded-xl border p-3 space-y-2 ${dark ? "border-gray-600" : "border-gray-200 bg-white"}`}>
          <label className="block">
            <span className={etiquette(dark)}>{tx("Message (modifiable avant l'envoi)")}</span>
            <textarea value={message} onChange={e => setMessage(e.target.value)} rows={3} maxLength={900} className={champ(dark)} />
          </label>
          <div className="flex flex-wrap gap-2">
            <a href={`tel:+${d.numero}`} onClick={relancer("appel")} className={`${lien} bg-foret-600 hover:bg-foret-700 text-white`}>
              <Phone size={13} />{tx("Appeler")}</a>
            <a href={`sms:+${d.numero}?body=${enc}`} onClick={relancer("sms")} className={`${lien} ${dark ? "bg-gray-700 text-gray-100" : "bg-gray-100 text-gray-800"}`}>
              <MessageSquare size={13} />{tx("SMS")}</a>
            <a href={`https://wa.me/${d.numero}?text=${enc}`} target="_blank" rel="noopener noreferrer" onClick={relancer("whatsapp")}
              className={`${lien} bg-[#25D366] hover:bg-[#1ebe5b] text-white`}><Send size={13} />{tx("WhatsApp")}</a>
            <span className={`${texteDiscret(dark)} self-center`}>+{d.numero}</span>
          </div>
        </div>
      ) : (
        <p className={`${texteDiscret(dark)} flex items-center gap-1.5`}><Info size={13} />
          {liste.masquees ? tx("Coordonnées masquées pour cette base : désactive le masquage dans « Mes données » pour relancer depuis ici.")
            : tx("Pas de téléphone pour ce client dans la base.")}</p>
      )}

      {liste.peut_traiter && (
        <>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => setFormulaire(formulaire === "promesse" ? null : "promesse")} className={boutonSecondaire(dark)}>
              <CalendarClock size={12} className="inline mr-1" />{tx("Promesse de paiement")}</button>
            <button onClick={() => setFormulaire(formulaire === "paiement" ? null : "paiement")} className={boutonSecondaire(dark)}>
              <Banknote size={12} className="inline mr-1" />{tx("Paiement reçu")}</button>
            <button onClick={() => setFormulaire(formulaire === "statut" ? null : "statut")} className={boutonSecondaire(dark)}>
              {tx("Changer le statut")}</button>
            <label className="flex items-center gap-1.5">
              <UserRound size={13} className="text-gray-400" />
              <select aria-label={tx("Assigner le dossier")} value={d.assigne_a || ""} disabled={action.chargement}
                onChange={e => envoyer(e.target.value ? { nature: "assignation", assigne_a: e.target.value } : { nature: "assignation", desassigner: true })}
                className={`${champ(dark)} !py-1 !text-xs w-auto`}>
                <option value="">{tx("Non assigné")}</option>
                {liste.assignables.map(p => <option key={p.nom} value={p.nom}>{p.nom_complet}</option>)}
              </select>
            </label>
          </div>
          {formulaire && (
            <div className={`grid sm:grid-cols-3 gap-2 items-end rounded-xl p-3 ${dark ? "bg-gray-700/40" : "bg-gray-50"}`}>
              {formulaire === "statut" ? (
                <label><span className={etiquette(dark)}>{tx("Nouveau statut")}</span>
                  <select value={statut} onChange={e => setStatut(e.target.value)} className={champ(dark)}>
                    {Object.entries(liste.statuts).map(([k, v]) => <option key={k} value={k}>{tx(v)}</option>)}
                  </select></label>
              ) : (
                <label><span className={etiquette(dark)}>{formulaire === "promesse" ? tx("Montant promis ({x})", { x: liste.devise_base })
                  : tx("Montant reçu ({x})", { x: liste.devise_base })}</span>
                  <input inputMode="decimal" value={montant} onChange={e => setMontant(e.target.value)} className={champ(dark)} /></label>
              )}
              {formulaire === "promesse" && (
                <label><span className={etiquette(dark)}>{tx("Date promise")}</span>
                  <input type="date" value={datePromesse} onChange={e => setDatePromesse(e.target.value)} className={champ(dark)} /></label>
              )}
              <label className={formulaire === "promesse" ? "" : "sm:col-span-1"}><span className={etiquette(dark)}>{tx("Note")}</span>
                <input value={note} onChange={e => setNote(e.target.value)} maxLength={500} className={champ(dark)}
                  placeholder={formulaire === "statut" ? tx("Motif (obligatoire pour contentieux ou irrécouvrable)") : tx("Facultatif")} /></label>
              <button disabled={action.chargement} className={`${boutonPrincipal} sm:col-span-3 justify-self-start`} onClick={() => envoyer(
                formulaire === "statut" ? { nature: "statut", statut, texte: note }
                  : { nature: formulaire, montant: montantNombre || null, date_promesse: datePromesse || null, texte: note })}>
                {tx("Enregistrer")}</button>
            </div>
          )}
          <div className="flex gap-2">
            <input value={commentaire} onChange={e => setCommentaire(e.target.value)}
              placeholder={tx("Ajouter un commentaire…")} maxLength={2000} className={champ(dark)} aria-label={tx("Commentaire")} />
            <button disabled={!commentaire.trim() || action.chargement} onClick={() => envoyer({ nature: "commentaire", texte: commentaire })}
              className={boutonSecondaire(dark)}>{tx("Ajouter")}</button>
          </div>
        </>
      )}
      {action.erreur && <p role="alert" className="text-xs text-red-500">{action.erreur}</p>}

      <div>
        <p className={`${etiquette(dark)} mt-1`}>{tx("Historique")}</p>
        {!historique ? <p className={texteDiscret(dark)}>{tx("Chargement…")}</p> : historique.length === 0
          ? <p className={texteDiscret(dark)}>{tx("Aucune action pour l'instant.")}</p> : (
          <ol className="space-y-1.5">
            {historique.map((h, i) => (
              <li key={i} className="text-xs flex gap-2">
                <span className={`${texteDiscret(dark)} whitespace-nowrap`}>{formaterDate(h.date)}</span>
                <span className={dark ? "text-gray-200" : "text-gray-800"}>{h.texte}</span>
                <span className={texteDiscret(dark)}>— {h.auteur}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
      {d.montant_recupere > 0 && (
        <p className={texteDiscret(dark)}>{tx("Déjà récupéré : {x}", { x: devise.formaterValeur(d.montant_recupere) })}</p>
      )}
    </div>
  );
}

export function PanelRecouvrement({ source, dark, onValeur }) {
  const devise = useDevise();
  const { appeler, chargement, erreur } = useAPI();
  const [d, setD] = useState(null);
  const [onglet, setOnglet] = useState("ouverts");
  const [etape, setEtape] = useState("toutes");
  const [cherche, setCherche] = useState("");
  const [ouvert, setOuvert] = useState(null);
  const [reglages, setReglages] = useState(false);
  const [nb, setNb] = useState(20);
  const id = source?.id || 0;

  const charger = useCallback(() => {
    appeler("get", `/sources/${id}/recouvrement`, null, { params: { statut: onglet, devise: devise.code }, timeout: 90000 })
      .then(r => r && setD(r));
  }, [appeler, id, onglet, devise.code]);
  useEffect(() => { setOuvert(null); setNb(20); charger(); }, [charger]);

  const visibles = useMemo(() => {
    if (!d) return [];
    const q = cherche.trim().toLowerCase();
    return d.dossiers.filter(x => (etape === "toutes" || x.etape === etape)
      && (!q || `${x.ref} ${x.client || ""}`.toLowerCase().includes(q)));
  }, [d, etape, cherche]);

  if (erreur && !d) return (
    <div className={`${carte(dark)} flex gap-3`}>
      <Info size={18} className="text-laiton-400 flex-shrink-0 mt-0.5" />
      <p className={`text-sm ${dark ? "text-gray-200" : "text-gray-800"}`}>{erreur}</p>
    </div>
  );
  if (!d) return <p className={texteDiscret(dark)}>{tx("Lecture des crédits en retard…")}</p>;
  const r = d.resume;
  const maj = (i, a) => setD(x => ({ ...x, dossiers: x.dossiers.map(o => (o.id === i ? {
    ...o, statut: a.statut, libelle_statut: d.statuts[a.statut], assigne_a: a.assigne_a, montant_recupere: o.montant_recupere,
    promesse_date: a.promesse_date } : o)) }));
  const exporter = () => telechargerCsv(nomFichier(`recouvrement ${source?.nom || "demonstration"}`, "csv"),
    ["priorite", "reference", "client", "telephone", "etape", "jours_retard", "reste_du", "recupere", "statut", "assigne_a", "promesse_date"],
    visibles.map((x, i) => ({ priorite: i + 1, reference: x.ref, client: x.client || "", telephone: x.telephone || "", etape: x.etape,
      jours_retard: x.jours_retard ?? "", reste_du: x.reste, recupere: x.montant_recupere, statut: x.libelle_statut,
      assigne_a: x.assigne_a || "", promesse_date: x.promesse_date || "" })));
  const chance = c => (c.source === "equipe" ? tx("{x} (taux réel de l'équipe)", { x: pct(c.taux) }) : tx("{x} (repère prudent)", { x: pct(c.taux) }));

  return (
    <div className="space-y-4">
      <div className={carte(dark)}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className={`${titre(dark)} flex items-center gap-2`}><HandCoins size={19} className="text-laiton-500" />{" "}{tx("Crédits à recouvrer")}</h2>
            <p className={`${texteDiscret(dark)} mt-1`}>
              {tx("Table « {table} » : crédits en retard ou en défaut, montant « {montant} »", { table: d.table, montant: d.colonne_montant || "—" })}
              {d.colonne_echeance ? tx(", retard compté depuis « {x} »", { x: d.colonne_echeance }) : ""}.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {onValeur && <button onClick={onValeur} className={boutonSecondaire(dark)}>{tx("Valeur créée")}</button>}
            {d.peut_traiter && <button onClick={() => setReglages(!reglages)} className={boutonSecondaire(dark)}>
              <Settings2 size={12} className="inline mr-1" />{tx("Message de relance")}</button>}
            <button onClick={exporter} className={`${boutonSecondaire(dark)} flex items-center gap-1.5`}><Download size={13} />{" "}{tx("CSV")}</button>
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
          <Tuile dark={dark} libelle={tx("Reste à recouvrer")} valeur={devise.formaterValeur(r.reste_du, { compact: true })}
            detail={tx("{x} dossiers en cours", { x: r.ouverts.toLocaleString(LOCALE) })} />
          <Tuile dark={dark} libelle={tx("Récupéré")} valeur={devise.formaterValeur(r.recupere, { compact: true })} accent="text-emerald-500"
            detail={tx("{x} dossiers réglés", { x: r.regles.toLocaleString(LOCALE) })} />
          <Tuile dark={dark} libelle={tx("Promesses en cours")} valeur={devise.formaterValeur(r.montant_promis, { compact: true })}
            detail={r.promesses_depassees ? tx("{x} échéance(s) dépassée(s)", { x: r.promesses_depassees }) : tx("{x} promesse(s)", { x: r.promesses })}
            accent={r.promesses_depassees ? "text-orange-500" : ""} />
          <Tuile dark={dark} libelle={tx("Relances faites")} valeur={r.relances.toLocaleString(LOCALE)}
            detail={tx("{x} dossier(s) sans responsable", { x: r.non_assignes.toLocaleString(LOCALE) })} />
        </div>
        <p className={`${texteDiscret(dark)} mt-3`}>
          {tx("Ordre de passage : reste dû × chance de récupération. Retard : {a} ; défaut : {b}.", { a: chance(d.chances.retard), b: chance(d.chances.defaut) })}
        </p>
        {d.masquees && (
          <p className="mt-3 text-xs flex items-start gap-1.5 text-amber-600"><ShieldAlert size={14} className="flex-shrink-0" />
            {tx("Les données personnelles de cette base sont masquées : noms et téléphones ne s'affichent pas, les relances directes sont désactivées.")}</p>
        )}
        {reglages && <Reglages source={id} reglages={d.reglages} dark={dark} onFini={() => { setReglages(false); charger(); }} />}
      </div>

      <div className={carte(dark)}>
        <div role="tablist" aria-label={tx("Dossiers")} className={`flex flex-wrap gap-1 mb-3 pb-3 border-b ${dark ? "border-gray-700" : "border-gray-200"}`}>
          {ONGLETS.map(([k, l]) => (
            <button key={k} role="tab" aria-selected={onglet === k} onClick={() => setOnglet(k)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium ${onglet === k ? (dark ? "bg-gray-700 text-white" : "bg-foret-50 text-foret-800") : texteDiscret(dark)}`}>
              {tx(l)}</button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          {[["toutes", "Toutes"], ["retard", "Retard"], ["defaut", "Défaut"]].map(([k, l]) => (
            <button key={k} onClick={() => setEtape(k)}
              className={`px-3 py-1 rounded-full text-xs ${etape === k ? "bg-foret-600 text-white" : dark ? "bg-gray-700 text-gray-300" : "bg-gray-100 text-gray-600"}`}>{tx(l)}</button>
          ))}
          <label className="relative ml-auto w-full sm:w-64">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input value={cherche} onChange={e => setCherche(e.target.value)} placeholder={tx("Référence ou client")}
              aria-label={tx("Chercher un dossier")} className={`${champ(dark)} !pl-8`} />
          </label>
        </div>
        {chargement && <p className={texteDiscret(dark)}>{tx("Mise à jour…")}</p>}
        <div className="space-y-2">
          {visibles.slice(0, nb).map((x, i) => (
            <div key={x.id} className={`rounded-xl ${dark ? "bg-gray-700/60" : "bg-gray-50"}`}>
              <button onClick={() => setOuvert(ouvert === x.id ? null : x.id)} aria-expanded={ouvert === x.id}
                className="w-full text-left p-3 flex items-start gap-3">
                <span className={`mt-0.5 grid h-7 w-7 flex-shrink-0 place-items-center rounded-full text-xs font-bold ${i < 3 && onglet === "ouverts" ? "bg-laiton-400 text-foret-900" : dark ? "bg-gray-600" : "bg-gray-200"}`}>{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`text-sm font-semibold ${dark ? "text-white" : "text-gray-900"}`}>{x.client || x.ref}</span>
                    <span className={`${texteDiscret(dark)} font-mono`}>{x.ref}</span>
                    <span className={`text-[11px] px-1.5 py-0.5 rounded ${x.etape === "defaut" ? "bg-red-500/15 text-red-500" : "bg-orange-500/15 text-orange-500"}`}>
                      {x.etape === "defaut" ? tx("Défaut") : tx("Retard")}{x.jours_retard > 0 ? tx(" · {x} j", { x: x.jours_retard }) : ""}</span>
                    <ChipStatutDossier statut={x.statut} libelle={x.libelle_statut} />
                    {x.promesse_depassee && <span className="text-[11px] text-orange-500">{tx("promesse dépassée")}</span>}
                  </div>
                  <p className={`${texteDiscret(dark)} mt-0.5`}>
                    {[x.assigne_a ? tx("→ {x}", { x: x.assigne_a }) : tx("non assigné"),
                      x.relances ? tx("{x} relance(s)", { x: x.relances }) : tx("jamais relancé"),
                      x.promesse_date ? tx("promis le {x}", { x: new Date(x.promesse_date).toLocaleDateString(LOCALE) }) : null].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="font-bold tabular-nums">{devise.formaterValeur(x.reste)}</p>
                  {ouvert === x.id ? <ChevronUp size={14} className="ml-auto mt-1" /> : <ChevronDown size={14} className="ml-auto mt-1" />}
                </div>
              </button>
              {ouvert === x.id && <Dossier source={id} d={x} liste={d} dark={dark} onMaj={a => { maj(x.id, a); charger(); }} />}
            </div>
          ))}
          {visibles.length === 0 && <p className={texteDiscret(dark)}>{onglet === "ouverts" ? tx("Aucun dossier en cours : tout est à jour.") : tx("Aucun dossier ici.")}</p>}
          {visibles.length > nb && (
            <button onClick={() => setNb(nb + 20)} className={`${boutonSecondaire(dark)} w-full`}>
              {tx("Afficher plus ({x} restants)", { x: visibles.length - nb })}</button>
          )}
        </div>
      </div>
    </div>
  );
}
