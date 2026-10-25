// Abonnements : formules, informations de facturation, paiement (page NotchPay), suivi.
import { useState, useEffect, useCallback } from "react";
import { Sparkles, Building2, UserRound, CreditCard, ShieldCheck, CircleCheck, Clock, Smartphone, Lock } from "lucide-react";
import { useAPI } from "../useAPI";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";
import { useDevise, SelecteurDevise } from "../devise";

// Les abonnements sont facturés en FCFA (mobile money) ; dans une autre monnaie, on montre l'équivalent.
const fcfa = n => `${Number(n || 0).toLocaleString("fr-FR")} FCFA`;

export function Prix({ fcfa: montant, dark, grand = false }) {
  const devise = useDevise();
  if (devise.fcfa) {
    return grand
      ? <>{Number(montant).toLocaleString("fr-FR")}<span className="text-sm font-medium"> FCFA</span></>
      : <>{fcfa(montant)}</>;
  }
  const equiv = devise.formater(montant);
  return grand ? (
    <>≈ {equiv.replace(` ${devise.libelle}`, "")}<span className="text-sm font-medium"> {devise.libelle}</span>
      <span className={`block text-xs font-normal ${dark ? "text-gray-400" : "text-gray-500"}`}>soit {fcfa(montant)}</span></>
  ) : <>≈ {equiv} ({fcfa(montant)})</>;
}

export function dureeRestante(secondes) {
  const s = Math.max(0, Number(secondes) || 0);
  const j = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (j > 0) return `${j} j ${h} h`;
  if (h > 0) return `${h} h ${m} min`;
  return `${m} min`;
}

// Bandeau en haut de l'application pour les visiteurs et abonnés
export function BandeauAcces({ acces, dark, onChoisir }) {
  if (!acces || acces.type === "interne") return null;
  const essai = acces.type === "essai";
  return (
    <div className={`mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 rounded-xl border text-sm ${
      essai ? "bg-laiton-400/10 border-laiton-400/40" : dark ? "bg-foret-900/40 border-foret-700" : "bg-foret-50 border-foret-200"}`}>
      <span className="flex items-center gap-2 font-semibold">
        {essai ? <Sparkles size={15} className="text-laiton-400" /> : <ShieldCheck size={15} className="text-emerald-500" />}
        {essai ? "Essai gratuit" : `Abonnement ${acces.formule || ""}`}
      </span>
      <span className={texteDiscret(dark)}><Clock size={12} className="inline -mt-0.5" /> {acces.expire ? "terminé" : `${dureeRestante(acces.secondes_restantes)} restants`}</span>
      <span className={texteDiscret(dark)}>{acces.questions_jour}/{acces.quota_questions} questions aujourd'hui</span>
      <span className={`${texteDiscret(dark)} flex items-center gap-1`}><Lock size={12} /> Lecture seule (données de démonstration)</span>
      <button onClick={onChoisir} className="ml-auto px-3 py-1.5 rounded-lg bg-foret-600 hover:bg-foret-700 text-white text-xs font-semibold">
        {essai ? "Choisir une formule" : "Prolonger"}
      </button>
    </div>
  );
}

const SECTEURS = [["banque", "Banque"], ["microfinance", "Microfinance (EMF)"], ["assurance", "Assurance"],
  ["fintech", "Fintech / mobile money"], ["administration", "Administration"], ["autre", "Autre"]];

function Champ({ dark, libelle, valeur, onChange, requis = true, ...props }) {
  return (
    <label className="block">
      <span className={etiquette(dark)}>{libelle}{requis ? "" : " (facultatif)"}</span>
      <input value={valeur || ""} onChange={e => onChange(e.target.value)} required={requis} className={champ(dark)} {...props} />
    </label>
  );
}

function FormulaireCommande({ dark, formule, compte, onAnnuler }) {
  const { appeler, chargement, erreur } = useAPI();
  const [type, setType] = useState("organisation");
  const [orga, setOrga] = useState({ secteur: "microfinance", taille: "11-50", pays: "Cameroun", email: compte?.email || "",
    responsable: compte?.nom_complet || "" });
  const [perso, setPerso] = useState({ pays: "Cameroun", email: compte?.email || "", nom_complet: compte?.nom_complet || "" });
  const [accepte, setAccepte] = useState(false);
  const o = k => v => setOrga({ ...orga, [k]: v });
  const p = k => v => setPerso({ ...perso, [k]: v });
  const tel = { type: "tel", pattern: "\\+?[0-9 ]{8,20}", placeholder: "+237 6XX XX XX XX", maxLength: 20 };

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
        <h2 className={titre(dark)}>Formule {formule.libelle} — <Prix fcfa={formule.prix} dark={dark} /></h2>
        <button type="button" onClick={onAnnuler} className={boutonSecondaire(dark)}>Changer de formule</button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {[["organisation", Building2, "Une organisation", "Banque, EMF, entreprise…"],
          ["particulier", UserRound, "Un particulier", "Consultant, étudiant, indépendant…"]].map(([id, Icone, t, d]) => (
          <button type="button" key={id} onClick={() => setType(id)} aria-pressed={type === id}
            className={`text-left p-3 rounded-xl border ${type === id ? "border-laiton-400 bg-laiton-400/10"
              : dark ? "border-gray-700" : "border-gray-200"}`}>
            <Icone size={18} /><p className="text-sm font-semibold mt-1">{t}</p><p className={texteDiscret(dark)}>{d}</p>
          </button>
        ))}
      </div>

      {type === "organisation" ? (
        <div className="grid sm:grid-cols-2 gap-3">
          <Champ dark={dark} libelle="Raison sociale" valeur={orga.raison_sociale} onChange={o("raison_sociale")} maxLength={150} />
          <label className="block"><span className={etiquette(dark)}>Secteur</span>
            <select value={orga.secteur} onChange={e => o("secteur")(e.target.value)} className={champ(dark)}>
              {SECTEURS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select></label>
          <label className="block"><span className={etiquette(dark)}>Effectif</span>
            <select value={orga.taille} onChange={e => o("taille")(e.target.value)} className={champ(dark)}>
              {["1-10", "11-50", "51-250", "250+"].map(v => <option key={v}>{v}</option>)}
            </select></label>
          <Champ dark={dark} libelle="Pays" valeur={orga.pays} onChange={o("pays")} maxLength={60} />
          <Champ dark={dark} libelle="Ville" valeur={orga.ville} onChange={o("ville")} maxLength={60} />
          <Champ dark={dark} libelle="Nom du responsable" valeur={orga.responsable} onChange={o("responsable")} maxLength={120} />
          <Champ dark={dark} libelle="Fonction" valeur={orga.fonction} onChange={o("fonction")} maxLength={80} placeholder="ex. Directeur des risques" />
          <Champ dark={dark} libelle="E-mail professionnel" valeur={orga.email} onChange={o("email")} type="email" maxLength={254} />
          <Champ dark={dark} libelle="Téléphone" valeur={orga.telephone} onChange={o("telephone")} {...tel} />
          <Champ dark={dark} libelle="NIU (n° contribuable)" valeur={orga.niu} onChange={o("niu")} requis={false} maxLength={30} />
          <Champ dark={dark} libelle="RCCM" valeur={orga.rccm} onChange={o("rccm")} requis={false} maxLength={40} />
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-3">
          <Champ dark={dark} libelle="Nom complet" valeur={perso.nom_complet} onChange={p("nom_complet")} maxLength={120} />
          <Champ dark={dark} libelle="Profession" valeur={perso.profession} onChange={p("profession")} maxLength={80} />
          <Champ dark={dark} libelle="Pays" valeur={perso.pays} onChange={p("pays")} maxLength={60} />
          <Champ dark={dark} libelle="Ville" valeur={perso.ville} onChange={p("ville")} maxLength={60} />
          <Champ dark={dark} libelle="E-mail" valeur={perso.email} onChange={p("email")} type="email" maxLength={254} />
          <Champ dark={dark} libelle="Téléphone" valeur={perso.telephone} onChange={p("telephone")} {...tel} />
        </div>
      )}

      <label className={`flex items-start gap-2 text-xs ${dark ? "text-gray-300" : "text-gray-600"}`}>
        <input type="checkbox" checked={accepte} onChange={e => setAccepte(e.target.checked)} required className="mt-0.5" />
        <span>J'accepte les conditions de vente : accès de {formule.duree_jours} jour{formule.duree_jours > 1 ? "s" : ""} dès
          le paiement, sans reconduction automatique. Mes informations servent uniquement à la facturation.</span>
      </label>
      {erreur && <p role="alert" className="text-sm text-red-500">{erreur}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={chargement || !accepte} className={`${boutonPrincipal} flex items-center gap-2`}>
          <CreditCard size={15} /> {chargement ? "Préparation…" : `Payer ${fcfa(formule.prix)}`}
        </button>
        <span className={`${texteDiscret(dark)} flex items-center gap-1`}>
          <Smartphone size={12} /> MTN MoMo, Orange Money ou carte, sur la page sécurisée de NotchPay · débité en FCFA
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

  return (
    <div className="space-y-4">
      {acces?.expire && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-600 text-sm">
          {acces.type === "essai" ? "Ton essai gratuit est terminé." : "Ton abonnement est arrivé à échéance."} Choisis une
          formule pour retrouver l'accès à l'outil.
        </div>
      )}
      {erreur && <p className="text-sm text-red-500">{erreur}</p>}
      {choisie ? (
        <FormulaireCommande dark={dark} formule={choisie} compte={compte} onAnnuler={() => setChoisie(null)} />
      ) : (
        <div className={carte(dark)}>
          <h2 className={titre(dark)}>Choisis ta formule</h2>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <p className={texteDiscret(dark)}>Sans engagement ni reconduction automatique. Un nouvel achat s'ajoute à la durée restante.</p>
            <SelecteurDevise compact className={`text-xs px-2 py-1.5 rounded-lg border outline-none ${dark ? "bg-gray-700 border-gray-600" : "bg-gray-50 border-gray-200"}`} />
          </div>
          {indisponible && (
            <p className="mb-4 text-sm text-amber-600">Le paiement en ligne sera ouvert très bientôt.</p>
          )}
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {(offre?.formules || []).map(f => (
              <div key={f.code} className={`relative p-4 rounded-xl border flex flex-col ${f.code === "mois"
                ? "border-laiton-400 bg-laiton-400/5" : dark ? "border-gray-700" : "border-gray-200"}`}>
                {f.code === "mois" && <span className="absolute -top-2.5 left-4 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-laiton-400 text-foret-900">Populaire</span>}
                <p className="text-sm font-semibold">{f.libelle}</p>
                <p className="text-2xl font-bold mt-1"><Prix fcfa={f.prix} dark={dark} grand /></p>
                <p className={texteDiscret(dark)}>{f.duree_jours} jour{f.duree_jours > 1 ? "s" : ""}{f.economie_pct > 0 ? ` · −${f.economie_pct} %` : ""}</p>
                <ul className={`mt-3 mb-4 space-y-1 text-xs ${dark ? "text-gray-300" : "text-gray-600"}`}>
                  <li className="flex gap-1.5"><CircleCheck size={13} className="text-emerald-500 flex-shrink-0" /> Jusqu'à {offre.quota_client} questions par jour</li>
                  <li className="flex gap-1.5"><CircleCheck size={13} className="text-emerald-500 flex-shrink-0" /> Fraude, crédit, rapports PDF / CSV</li>
                  <li className="flex gap-1.5"><CircleCheck size={13} className="text-emerald-500 flex-shrink-0" /> Mode conversation</li>
                </ul>
                <button onClick={() => setChoisie(f)} disabled={indisponible} className={`mt-auto ${boutonPrincipal}`}>Choisir</button>
              </div>
            ))}
          </div>
        </div>
      )}
      {moi?.paiements?.length > 0 && (
        <div className={carte(dark)}>
          <h2 className={`${titre(dark)} mb-3`}>Mes paiements</h2>
          <table className="w-full text-sm">
            <thead><tr className={`text-xs ${texteDiscret(dark)}`}><th className="text-left p-2">Date</th><th className="text-left p-2">Formule</th>
              <th className="text-left p-2">Montant</th><th className="text-left p-2">Statut</th><th className="text-left p-2">Valable jusqu'au</th></tr></thead>
            <tbody>
              {moi.paiements.map(p => (
                <tr key={p.reference} className={`border-t ${dark ? "border-gray-700" : "border-gray-100"}`}>
                  <td className="p-2">{formaterDate(p.date_creation)}</td><td className="p-2">{p.formule}</td>
                  <td className="p-2">{fcfa(p.montant)}</td>
                  <td className="p-2">{{ paye: "Payé", en_attente: "En attente", echoue: "Échoué", annule: "Annulé" }[p.statut] || p.statut}</td>
                  <td className="p-2">{p.abonnement_fin ? formaterDate(p.abonnement_fin) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Suivi des abonnements (administrateur de l'organisation) ─────────
export function PanelAbonnements({ dark }) {
  const { appeler, erreur } = useAPI();
  const [d, setD] = useState(null);
  const charger = useCallback(() => { appeler("get", "/admin/abonnements").then(r => r && setD(r)); }, [appeler]);
  useEffect(() => { charger(); }, [charger]);
  const s = d?.synthese || {};
  const tuiles = [["Visiteurs inscrits", s.visiteurs], ["Essais en cours", s.essais_en_cours],
    ["Abonnés actifs", s.abonnes_actifs], ["Revenus encaissés", fcfa(s.revenus)]];
  return (
    <div className="space-y-4">
      {erreur && <p className="text-sm text-red-500">{erreur}</p>}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {tuiles.map(([t, v]) => (
          <div key={t} className={carte(dark)}><p className={texteDiscret(dark)}>{t}</p><p className="text-xl font-bold mt-1">{v ?? "–"}</p></div>
        ))}
      </div>
      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-1`}>Paiements</h2>
        <p className={`${texteDiscret(dark)} mb-3`}>Mode de paiement : {{ reel: "NotchPay (réel)", test: "NotchPay (test)",
          simulation: "simulation locale", indisponible: "non configuré (NOTCHPAY_PUBLIC_KEY)" }[d?.paiement] || "…"}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className={texteDiscret(dark)}>
              <th className="text-left p-2">Date</th><th className="text-left p-2">Compte</th><th className="text-left p-2">Client</th>
              <th className="text-left p-2">Formule</th><th className="text-left p-2">Montant</th><th className="text-left p-2">Statut</th>
              <th className="text-left p-2">Jusqu'au</th></tr></thead>
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
                    <td className="p-2">{p.formule}</td><td className="p-2 whitespace-nowrap">{fcfa(p.montant)}</td>
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
