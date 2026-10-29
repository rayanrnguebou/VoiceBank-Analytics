// Abonnements : formules, informations de facturation, paiement (page NotchPay), suivi.
import { useState, useEffect, useCallback } from "react";
import { Sparkles, Building2, UserRound, CreditCard, ShieldCheck, CircleCheck, Clock, Smartphone, Lock, Mail, Send } from "lucide-react";
import { useAPI } from "../useAPI";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";
import { useDevise, SelecteurDevise } from "../devise";
import ChampListe from "../ChampListe";
import { NOMS_PAYS, indicatif } from "../listes";
import { useReferentiel } from "../referentiel";
import { LOCALE, tx } from "../i18n";

// Les abonnements sont facturés en FCFA (mobile money) ; dans une autre monnaie, on montre l'équivalent.
const fcfa = n => `${Number(n || 0).toLocaleString(LOCALE)} FCFA`;

export function Prix({ fcfa: montant, dark, grand = false }) {
  const devise = useDevise();
  if (devise.fcfa) {
    return grand
      ? <>{Number(montant).toLocaleString(LOCALE)}<span className="text-sm font-medium">{" "}{tx("FCFA")}</span></>
      : <>{fcfa(montant)}</>;
  }
  const equiv = devise.formater(montant);
  return grand ? (
    <>≈ {equiv.replace(` ${devise.libelle}`, "")}<span className="text-sm font-medium"> {devise.libelle}</span>
      <span className={`block text-xs font-normal ${dark ? "text-gray-400" : "text-gray-500"}`}>{tx("soit {x}", { x: fcfa(montant) })}</span></>
  ) : <>≈ {equiv} ({fcfa(montant)})</>;
}

export function dureeRestante(secondes) {
  const s = Math.max(0, Number(secondes) || 0);
  const j = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (j > 0) return tx("{j} j {h} h", { j, h });
  if (h > 0) return `${h} h ${m} min`;
  return `${m} min`;
}

// Bandeau en haut de l'application pour les visiteurs et abonnés : discret, sauf à l'approche de l'échéance
export function BandeauAcces({ acces, dark, onChoisir }) {
  if (!acces || acces.type === "interne") return null;
  const essai = acces.type === "essai";
  const bientot = acces.expire || (acces.secondes_restantes || 0) < 7 * 86400;
  const gere = acces.gere_abonnement !== false;
  return (
    <div className={`mb-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-2 rounded-xl border text-xs ${
      essai || bientot ? "bg-laiton-400/10 border-laiton-400/40" : dark ? "bg-gray-800/50 border-gray-700" : "bg-white border-gray-200"}`}>
      <span className="flex items-center gap-1.5 font-semibold text-sm">
        {essai ? <Sparkles size={14} className="text-laiton-400" /> : <ShieldCheck size={14} className="text-emerald-500" />}
        {essai ? tx("Essai gratuit") : tx("Abonnement {formule}", { formule: tx(acces.formule || "") }).trim()}
        {acces.organisation && !essai && <span className="font-normal">· {acces.organisation}</span>}
      </span>
      <span className={`${texteDiscret(dark)} flex items-center gap-1`}><Clock size={12} /> {acces.expire ? tx("terminé") : tx("{duree} restants", { duree: dureeRestante(acces.secondes_restantes) })}</span>
      <span className={texteDiscret(dark)}>{tx("{questions_jour}/{quota_questions} questions aujourd'hui", { questions_jour: acces.questions_jour, quota_questions: acces.quota_questions })}</span>
      {essai && <span className={`${texteDiscret(dark)} flex items-center gap-1`}><Lock size={12} />{" "}{tx("Démonstration en lecture seule")}</span>}
      {gere && (essai || bientot) ? (
        <button onClick={onChoisir} className="ml-auto px-3 py-1 rounded-lg bg-foret-600 hover:bg-foret-700 text-white text-xs font-semibold">
          {essai ? tx("Choisir une formule") : tx("Prolonger")}
        </button>
      ) : gere ? (
        <button onClick={onChoisir} className={`ml-auto ${texteDiscret(dark)} hover:underline`}>{tx("Gérer l'abonnement")}</button>
      ) : (
        <span className={`ml-auto ${texteDiscret(dark)}`}>{tx("Géré par l'administrateur de l'organisation")}</span>
      )}
    </div>
  );
}

const SECTEURS = [["banque", tx("Banque")], ["microfinance", tx("Microfinance (EMF)")], ["assurance", tx("Assurance")],
  ["fintech", tx("Fintech / mobile money")], ["administration", tx("Administration")], ["autre", tx("Autre")]];

function Champ({ dark, libelle, valeur, onChange, requis = true, ...props }) {
  return (
    <label className="block">
      <span className={etiquette(dark)}>{libelle}{requis ? "" : tx(" (facultatif)")}</span>
      <input value={valeur || ""} onChange={e => onChange(e.target.value)} required={requis} className={champ(dark)} {...props} />
    </label>
  );
}

// Pays (liste), ville (toutes les localités du pays, saisie libre acceptée) ; l'indicatif suit le pays
function ChampsLieu({ dark, valeurs, maj }) {
  const villes = useReferentiel("villes", valeurs.pays);
  const changerPays = pays => {
    const ancien = indicatif(valeurs.pays), nouveau = indicatif(pays);
    const tel = (valeurs.telephone || "").trim();
    const suite = { ...valeurs, pays, ville: pays === valeurs.pays ? valeurs.ville : "" };
    if (nouveau) {
      if (!tel || tel === `+${ancien}`) suite.telephone = `+${nouveau} `;                       // vide ou indicatif seul
      else if (ancien && tel.startsWith(`+${ancien} `)) suite.telephone = `+${nouveau} ${tel.slice(ancien.length + 2)}`;
    }
    maj(suite);
  };
  return (
    <>
      <label className="block"><span className={etiquette(dark)}>{tx("Pays")}</span>
        <ChampListe dark={dark} valeur={valeurs.pays} onChange={changerPays} options={NOMS_PAYS} required placeholder={tx("Tape les premières lettres…")} /></label>
      <label className="block"><span className={etiquette(dark)}>{tx("Ville")}</span>
        <ChampListe dark={dark} valeur={valeurs.ville} onChange={v => maj({ ...valeurs, ville: v })} options={villes.options}
          libre required maxLength={60} placeholder={villes.options.length ? tx("Tape les premières lettres…") : tx("Ta ville")} /></label>
    </>
  );
}

// Raison sociale : pour une banque ou une microfinance, les établissements du pays sont proposés (saisie libre)
function RaisonSociale({ dark, orga, maj }) {
  const financier = ["banque", "microfinance"].includes(orga.secteur);
  const banques = useReferentiel("banques", financier ? orga.pays : null);
  if (!financier) return <Champ dark={dark} libelle={tx("Raison sociale")} valeur={orga.raison_sociale} onChange={maj} maxLength={150} />;
  return (
    <label className="block"><span className={etiquette(dark)}>{tx("Raison sociale")}</span>
      <ChampListe dark={dark} valeur={orga.raison_sociale || ""} onChange={maj} options={banques.options} libre required maxLength={150}
        placeholder={tx("Nom ou sigle de l'établissement{pays}…", { pays: orga.pays ? ` (${orga.pays})` : "" })} /></label>
  );
}

function FormulaireCommande({ dark, formule, compte, onAnnuler }) {
  const { appeler, chargement, erreur } = useAPI();
  const [type, setType] = useState("organisation");
  const [orga, setOrga] = useState({ secteur: "microfinance", taille: "11-50", pays: "Cameroun", telephone: "+237 ", email: compte?.email || "",
    responsable: compte?.nom_complet || "" });
  const [perso, setPerso] = useState({ pays: "Cameroun", telephone: "+237 ", email: compte?.email || "", nom_complet: compte?.nom_complet || "" });
  const [accepte, setAccepte] = useState(false);
  const o = k => v => setOrga({ ...orga, [k]: v });
  const p = k => v => setPerso({ ...perso, [k]: v });
  const tel = pays => ({ type: "tel", pattern: "\\+?[0-9 ]{8,20}", maxLength: 20,
    placeholder: indicatif(pays) === "237" ? tx("+237 6XX XX XX XX") : indicatif(pays) ? `+${indicatif(pays)} …` : tx("+237 6XX XX XX XX") });

  const payer = async (e) => {
    e.preventDefault();
    const nettoie = obj => Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== "" && v != null));
    const res = await appeler("post", "/abonnement/commander", {
      formule: formule.code, type_client: type, accepte_conditions: accepte,
      ...(type === "organisation" ? { organisation: nettoie(orga) } : { particulier: nettoie(perso) }),
    });
    // Redirection vers la page de paiement sécurisée (NotchPay) ; retour automatique ensuite.
    if (res?.url_paiement) window.location.assign(res.url_paiement);
  };

  return (
    <form onSubmit={payer} className={`${carte(dark)} space-y-4`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={titre(dark)}>{tx("Formule {libelle} —", { libelle: formule.libelle })}{" "}<Prix fcfa={formule.prix} dark={dark} /></h2>
        <button type="button" onClick={onAnnuler} className={boutonSecondaire(dark)}>{tx("Changer de formule")}</button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {[["organisation", Building2, tx("Une organisation"), tx("Banque, EMF, entreprise…")],
          ["particulier", UserRound, tx("Un particulier"), tx("Consultant, étudiant, indépendant…")]].map(([id, Icone, t, d]) => (
          <button type="button" key={id} onClick={() => setType(id)} aria-pressed={type === id}
            className={`text-left p-3 rounded-xl border ${type === id ? "border-laiton-400 bg-laiton-400/10"
              : dark ? "border-gray-700" : "border-gray-200"}`}>
            <Icone size={18} /><p className="text-sm font-semibold mt-1">{t}</p><p className={texteDiscret(dark)}>{d}</p>
          </button>
        ))}
      </div>

      {type === "organisation" ? (
        <div className="grid sm:grid-cols-2 gap-3">
          <RaisonSociale dark={dark} orga={orga} maj={o("raison_sociale")} />
          <label className="block"><span className={etiquette(dark)}>{tx("Secteur")}</span>
            <select value={orga.secteur} onChange={e => o("secteur")(e.target.value)} className={champ(dark)}>
              {SECTEURS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select></label>
          <label className="block"><span className={etiquette(dark)}>{tx("Effectif")}</span>
            <select value={orga.taille} onChange={e => o("taille")(e.target.value)} className={champ(dark)}>
              {["1-10", "11-50", "51-250", "250+"].map(v => <option key={v}>{v}</option>)}
            </select></label>
          <ChampsLieu dark={dark} valeurs={orga} maj={setOrga} />
          <Champ dark={dark} libelle={tx("Nom du responsable")} valeur={orga.responsable} onChange={o("responsable")} maxLength={120} />
          <Champ dark={dark} libelle={tx("Fonction")} valeur={orga.fonction} onChange={o("fonction")} maxLength={80} placeholder={tx("ex. Directeur des risques")} />
          <Champ dark={dark} libelle={tx("E-mail professionnel")} valeur={orga.email} onChange={o("email")} type="email" maxLength={254} />
          <Champ dark={dark} libelle={tx("Téléphone")} valeur={orga.telephone} onChange={o("telephone")} {...tel(orga.pays)} />
          <Champ dark={dark} libelle={tx("NIU (n° contribuable)")} valeur={orga.niu} onChange={o("niu")} requis={false} maxLength={30} />
          <Champ dark={dark} libelle="RCCM" valeur={orga.rccm} onChange={o("rccm")} requis={false} maxLength={40} />
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-3">
          <Champ dark={dark} libelle={tx("Nom complet")} valeur={perso.nom_complet} onChange={p("nom_complet")} maxLength={120} />
          <Champ dark={dark} libelle={tx("Profession")} valeur={perso.profession} onChange={p("profession")} maxLength={80} />
          <ChampsLieu dark={dark} valeurs={perso} maj={setPerso} />
          <Champ dark={dark} libelle={tx("E-mail")} valeur={perso.email} onChange={p("email")} type="email" maxLength={254} />
          <Champ dark={dark} libelle={tx("Téléphone")} valeur={perso.telephone} onChange={p("telephone")} {...tel(perso.pays)} />
        </div>
      )}

      <label className={`flex items-start gap-2 text-xs ${dark ? "text-gray-300" : "text-gray-600"}`}>
        <input type="checkbox" checked={accepte} onChange={e => setAccepte(e.target.checked)} required className="mt-0.5" />
        <span>{tx("J'accepte les conditions de vente : accès de {duree_jours} jour", { duree_jours: formule.duree_jours })}{formule.duree_jours > 1 ? "s" : ""}{" "}{tx("dès le paiement, sans reconduction automatique. Mes informations servent uniquement à la facturation.")}</span>
      </label>
      {erreur && <p role="alert" className="text-sm text-red-500">{erreur}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={chargement || !accepte} className={`${boutonPrincipal} flex items-center gap-2`}>
          <CreditCard size={15} /> {chargement ? tx("Préparation…") : tx("Payer {x}", { x: fcfa(formule.prix) })}
        </button>
        <span className={`${texteDiscret(dark)} flex items-center gap-1`}>
          <Smartphone size={12} />{" "}{tx("MTN MoMo, Orange Money ou carte, sur la page sécurisée de NotchPay · débité en FCFA")}
        </span>
      </div>
    </form>
  );
}

export function PanelAbonnement({ dark, acces, utilisateur }) {
  const { appeler, erreur } = useAPI();
  const [offre, setOffre] = useState(null);
  const [moi, setMoi] = useState(null);
  const [choisie, setChoisie] = useState(null);

  useEffect(() => {
    appeler("get", "/abonnement/formules").then(r => r && setOffre(r));
    appeler("get", "/abonnement/moi").then(r => r && setMoi(r));
  }, [appeler]);

  const compte = { email: utilisateur?.includes("@") ? utilisateur : "", nom_complet: acces?.nom_complet || "" };
  const indisponible = offre?.paiement === "indisponible";

  if (acces && acces.gere_abonnement === false) {
    return (
      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} flex items-center gap-2 mb-2`}><Building2 size={19} />{" "}{tx("Abonnement de {organisation}", { organisation: acces.organisation })}</h2>
        <p className={`text-sm ${dark ? "text-gray-300" : "text-gray-700"}`}>
          {acces.expire
            ? tx("L'abonnement de ton organisation est arrivé à échéance. Préviens son administrateur : dès qu'il le renouvelle, tous les membres retrouvent l'accès.")
            : tx("Ton accès est inclus dans l'abonnement {formule} de ton organisation, valable jusqu'au {fin}.", { formule: tx(acces.formule || ""), fin: formaterDate(acces.fin) })}
        </p>
        <p className={`${texteDiscret(dark)} mt-2`}>{tx("Seul l'administrateur de l'organisation gère l'abonnement et les paiements.")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {acces?.expire && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-600 text-sm">
          {acces.type === "essai" ? tx("Ton essai gratuit est terminé.") : tx("Ton abonnement est arrivé à échéance.")}{" "}{tx("Choisis une formule pour retrouver l'accès à l'outil.")}
        </div>
      )}
      {erreur && <p className="text-sm text-red-500">{erreur}</p>}
      {choisie ? (
        <FormulaireCommande dark={dark} formule={choisie} compte={compte} onAnnuler={() => setChoisie(null)} />
      ) : (
        <div className={carte(dark)}>
          <h2 className={titre(dark)}>{tx("Choisis ta formule")}</h2>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <p className={texteDiscret(dark)}>{tx("Sans engagement ni reconduction automatique. Un nouvel achat s'ajoute à la durée restante.")}</p>
            <SelecteurDevise compact className={`text-xs px-2 py-1.5 rounded-lg border outline-none ${dark ? "bg-gray-700 border-gray-600" : "bg-gray-50 border-gray-200"}`} />
          </div>
          {indisponible && (
            <p className="mb-4 text-sm text-amber-600">{tx("Le paiement en ligne sera ouvert très bientôt.")}</p>
          )}
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {(offre?.formules || []).map(f => (
              <div key={f.code} className={`relative p-4 rounded-xl border flex flex-col ${f.code === "mois"
                ? "border-laiton-400 bg-laiton-400/5" : dark ? "border-gray-700" : "border-gray-200"}`}>
                {f.code === "mois" && <span className="absolute -top-2.5 left-4 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-laiton-400 text-foret-900">{tx("Populaire")}</span>}
                <p className="text-sm font-semibold">{f.libelle}</p>
                <p className="text-2xl font-bold mt-1"><Prix fcfa={f.prix} dark={dark} grand /></p>
                <p className={texteDiscret(dark)}>{tx("{duree_jours} jour", { duree_jours: f.duree_jours })}{f.duree_jours > 1 ? "s" : ""}{f.economie_pct > 0 ? ` · −${f.economie_pct} %` : ""}</p>
                <ul className={`mt-3 mb-4 space-y-1 text-xs ${dark ? "text-gray-300" : "text-gray-600"}`}>
                  <li className="flex gap-1.5"><CircleCheck size={13} className="text-emerald-500 flex-shrink-0" />{" "}{tx("Organisation : jusqu'à {comptes_organisation} comptes", { comptes_organisation: f.comptes_organisation })}</li>
                  <li className="flex gap-1.5"><CircleCheck size={13} className="text-emerald-500 flex-shrink-0" />{" "}{tx("Jusqu'à {quota_client} questions par jour et par compte", { quota_client: offre.quota_client })}</li>
                  <li className="flex gap-1.5"><CircleCheck size={13} className="text-emerald-500 flex-shrink-0" />{" "}{tx("Fraude, crédit, rapports PDF / CSV")}</li>
                  <li className="flex gap-1.5"><CircleCheck size={13} className="text-emerald-500 flex-shrink-0" />{" "}{tx("Mode conversation")}</li>
                </ul>
                <button onClick={() => setChoisie(f)} disabled={indisponible} className={`mt-auto ${boutonPrincipal}`}>{tx("Choisir")}</button>
              </div>
            ))}
          </div>
        </div>
      )}
      {moi?.paiements?.length > 0 && (
        <div className={carte(dark)}>
          <h2 className={`${titre(dark)} mb-3`}>{tx("Mes paiements")}</h2>
          <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[520px]">
            <thead><tr className={`text-xs ${texteDiscret(dark)}`}><th className="text-left p-2">{tx("Date")}</th><th className="text-left p-2">{tx("Formule")}</th>
              <th className="text-left p-2">{tx("Montant")}</th><th className="text-left p-2">{tx("Statut")}</th><th className="text-left p-2">{tx("Valable jusqu'au")}</th></tr></thead>
            <tbody>
              {moi.paiements.map(p => (
                <tr key={p.reference} className={`border-t ${dark ? "border-gray-700" : "border-gray-100"}`}>
                  <td className="p-2">{formaterDate(p.date_creation)}</td><td className="p-2">{tx(p.formule)}</td>
                  <td className="p-2">{fcfa(p.montant)}</td>
                  <td className="p-2">{{ paye: tx("Payé"), en_attente: tx("En attente"), echoue: tx("Échoué"), annule: tx("Annulé") }[p.statut] || p.statut}</td>
                  <td className="p-2">{p.abonnement_fin ? formaterDate(p.abonnement_fin) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}

// Diagnostic de l'envoi d'e-mails (Brevo / SMTP) : affiche la raison exacte d'un échec
function TestEmail({ dark }) {
  const { appeler, chargement, erreur, setErreur } = useAPI();
  const [dest, setDest] = useState("");
  const [ok, setOk] = useState(null);
  const envoyer = async e => {
    e.preventDefault(); setOk(null); setErreur(null);
    const r = await appeler("post", "/admin/email-test", { destinataire: dest.trim() || null });
    if (r) setOk(r.message);
  };
  return (
    <div className={carte(dark)}>
      <h2 className={`${titre(dark)} flex items-center gap-2 mb-1`}><Mail size={18} />{" "}{tx("Envoi d'e-mails")}</h2>
      <p className={`${texteDiscret(dark)} mb-3`}>{tx("Codes de vérification, invitations des membres et reçus de paiement. Envoie un e-mail de test : en cas d'échec, la raison exacte s'affiche (clé Brevo, adresse IP non autorisée, expéditeur non validé…).")}</p>
      <form onSubmit={envoyer} className="flex flex-wrap gap-2">
        <input type="email" value={dest} onChange={e => setDest(e.target.value)} placeholder={tx("Adresse (vide : ton e-mail de récupération)")}
          className={`${champ(dark)} flex-1 min-w-[220px]`} />
        <button disabled={chargement} className={`${boutonPrincipal} flex items-center gap-1.5`}><Send size={14} /> {chargement ? tx("Envoi…") : tx("Envoyer un test")}</button>
      </form>
      {ok && <p className="text-sm text-emerald-500 mt-2" role="status">{ok}</p>}
      {erreur && <p className="text-sm text-red-500 mt-2" role="alert">{erreur}</p>}
    </div>
  );
}

// ── Suivi des abonnements et des organisations clientes (administrateur de la plateforme) ──
export function PanelAbonnements({ dark }) {
  const { appeler, erreur } = useAPI();
  const [d, setD] = useState(null);
  const [orgs, setOrgs] = useState(null);
  const charger = useCallback(() => {
    appeler("get", "/admin/abonnements").then(r => r && setD(r));
    appeler("get", "/admin/organisations").then(r => r && setOrgs(r.data));
  }, [appeler]);
  useEffect(() => { charger(); }, [charger]);
  const s = d?.synthese || {};
  const tuiles = [[tx("Visiteurs inscrits"), s.visiteurs], [tx("Essais en cours"), s.essais_en_cours],
    [tx("Abonnés actifs"), s.abonnes_actifs], [tx("Revenus encaissés"), fcfa(s.revenus)]];
  return (
    <div className="space-y-4">
      {erreur && <p className="text-sm text-red-500">{erreur}</p>}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {tuiles.map(([t, v]) => (
          <div key={t} className={carte(dark)}><p className={texteDiscret(dark)}>{t}</p><p className="text-xl font-bold mt-1">{v ?? "–"}</p></div>
        ))}
      </div>
      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-3`}>{tx("Organisations clientes (")}{orgs?.length ?? "…"})</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className={texteDiscret(dark)}>
              <th className="text-left p-2">{tx("Organisation")}</th><th className="text-left p-2">{tx("Type")}</th><th className="text-left p-2">{tx("Formule")}</th>
              <th className="text-left p-2">{tx("Comptes")}</th><th className="text-left p-2">{tx("Administrateur(s)")}</th>
              <th className="text-left p-2">{tx("Jusqu'au")}</th><th className="text-left p-2">{tx("Total payé")}</th></tr></thead>
            <tbody>
              {(orgs || []).map(o => (
                <tr key={o.id_org} className={`border-t ${dark ? "border-gray-700" : "border-gray-100"}`}>
                  <td className="p-2 font-medium">{o.nom}</td>
                  <td className="p-2">{o.type_org === "particulier" ? tx("Particulier") : tx("Organisation")}</td>
                  <td className="p-2">{o.formule || "—"}</td>
                  <td className="p-2 tabular-nums">{o.membres}/{o.limite_comptes}</td>
                  <td className="p-2">{o.administrateurs || "—"}</td>
                  <td className={`p-2 whitespace-nowrap ${o.active ? "" : "text-red-500"}`}>{o.abonnement_fin ? formaterDate(o.abonnement_fin) : "—"}</td>
                  <td className="p-2 whitespace-nowrap">{fcfa(o.total_paye)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <TestEmail dark={dark} />
      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-1`}>{tx("Paiements")}</h2>
        <p className={`${texteDiscret(dark)} mb-3`}>{tx("Mode de paiement :")}{" "}{{ reel: tx("NotchPay (réel)"), test: tx("NotchPay (test)"),
          simulation: tx("simulation locale"), indisponible: tx("non configuré (NOTCHPAY_PUBLIC_KEY)") }[d?.paiement] || "…"}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className={texteDiscret(dark)}>
              <th className="text-left p-2">{tx("Date")}</th><th className="text-left p-2">{tx("Compte")}</th><th className="text-left p-2">{tx("Client")}</th>
              <th className="text-left p-2">{tx("Formule")}</th><th className="text-left p-2">{tx("Montant")}</th><th className="text-left p-2">{tx("Statut")}</th>
              <th className="text-left p-2">{tx("Jusqu'au")}</th></tr></thead>
            <tbody>
              {(d?.paiements || []).map(p => {
                const i = p.informations || {};
                return (
                  <tr key={p.reference} className={`border-t ${dark ? "border-gray-700" : "border-gray-100"}`}>
                    <td className="p-2 whitespace-nowrap">{formaterDate(p.date_creation)}</td>
                    <td className="p-2">{p.utilisateur}</td>
                    <td className="p-2">{p.type_client === "organisation"
                      ? `${i.raison_sociale || ""} (${i.secteur || ""}, ${i.ville || ""}) — ${i.responsable || ""}, ${i.telephone || ""}`
                      : `${i.nom_complet || ""} (${i.profession || ""}, ${i.ville || ""}) — ${i.telephone || ""}`}</td>
                    <td className="p-2">{tx(p.formule)}</td><td className="p-2 whitespace-nowrap">{fcfa(p.montant)}</td>
                    <td className={`p-2 ${p.statut === "paye" ? "text-emerald-500" : p.statut === "en_attente" ? "" : "text-red-500"}`}>{p.statut}</td>
                    <td className="p-2 whitespace-nowrap">{p.abonnement_fin ? formaterDate(p.abonnement_fin) : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
