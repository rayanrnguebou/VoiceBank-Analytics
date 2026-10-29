// Mon organisation : abonnement partagé, membres, invitations par e-mail (administrateur de l'organisation).
import { useState, useEffect, useCallback } from "react";
import {
  Building2, UserPlus, Mail, RotateCcw, UserX, UserCheck, ShieldCheck, Clock, Copy, Check, Users, Pencil, X, Database,
  ScrollText, Download, Smartphone,
} from "lucide-react";
import { useAPI } from "../useAPI";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate, telechargerCsv, nomFichier } from "../ui";
import { tx } from "../i18n";

// Rôles dans l'organisation : ce que chacun peut faire
export const ROLES_ORG = {
  admin: [tx("Administrateur"), tx("Gère les membres, l'abonnement et les bases ; traite les alertes.")],
  analyste: [tx("Analyste"), tx("Interroge les données et traite les alertes (assigner, commenter, verdict).")],
  lecteur: [tx("Lecteur"), tx("Consulte et interroge, sans traiter les alertes.")],
  auditeur: [tx("Auditeur"), tx("Consulte tout et lit le journal d'activité de l'organisation (contrôle interne).")],
};

const STATUTS = {
  actif: [tx("Actif"), "bg-emerald-500/15 text-emerald-600"],
  invitation_en_attente: [tx("Invitation envoyée"), "bg-laiton-400/20 text-laiton-700"],
  invitation_expiree: [tx("Invitation expirée"), "bg-amber-500/15 text-amber-600"],
  desactive: [tx("Désactivé"), "bg-gray-500/15 text-gray-500"],
};

function Badge({ statut }) {
  const [texte, style] = STATUTS[statut] || [statut, ""];
  return <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${style}`}>{texte}</span>;
}

function MotDePasseTransmis({ dark, info, onFermer }) {
  const [copie, setCopie] = useState(false);
  return (
    <div className={`mt-4 p-4 rounded-xl border ${dark ? "border-amber-500/40 bg-amber-500/10" : "border-amber-300 bg-amber-50"}`}>
      <p className="text-sm font-semibold mb-1">{tx("E-mail non envoyé : transmets ces informations à {nom}", { nom: info.nom })}</p>
      {info.erreur_envoi && <p className="text-xs text-red-500 mb-2">{info.erreur_envoi}</p>}
      <p className="text-sm">{tx("Identifiant :")}{" "}<code>{info.nom}</code></p>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-sm">{tx("Mot de passe provisoire :")}</span>
        <code className="px-2 py-1 rounded bg-black/10 font-mono">{info.mot_de_passe_provisoire}</code>
        <button onClick={() => { navigator.clipboard?.writeText(info.mot_de_passe_provisoire); setCopie(true); }}
          className={boutonSecondaire(dark)} aria-label={tx("Copier le mot de passe")}>{copie ? <Check size={13} /> : <Copy size={13} />}</button>
      </div>
      <p className={`${texteDiscret(dark)} mt-2`}>{tx("Valable {valable_heures} h, affiché une seule fois. La personne le changera à sa première connexion.", { valable_heures: info.valable_heures })}</p>
      <button onClick={onFermer} className={`${boutonSecondaire(dark)} mt-3`}>{tx("J'ai transmis le mot de passe")}</button>
    </div>
  );
}

export default function PanelOrganisation({ dark, onAbonnement }) {
  const lecture = useAPI();
  const action = useAPI();
  const [o, setO] = useState(null);
  const [f, setF] = useState({ nom_complet: "", email: "", role_org: "analyste" });
  const [info, setInfo] = useState(null);
  const [succes, setSucces] = useState(null);
  const [renommer, setRenommer] = useState(null);
  const [bases, setBases] = useState(null);           // { nom, ids } : choix des bases d'un membre en cours

  const charger = useCallback(() => {
    lecture.appeler("get", "/organisation").then(r => r && setO(r.data));
  }, [lecture.appeler]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  const resultat = (res, quoi) => {
    if (!res) return;
    if (res.invitation_envoyee) { setSucces(tx("{quoi} : e-mail d'invitation envoyé à {email}.", { quoi, email: res.email })); setInfo(null); }
    else { setInfo(res); setSucces(null); }
    charger();
  };
  const inviter = async e => {
    e.preventDefault();
    const res = await action.appeler("post", "/organisation/membres", { ...f, email: f.email.trim() });
    if (res) setF({ nom_complet: "", email: "", role_org: "analyste" });
    resultat(res, tx("Membre ajouté"));
  };
  const renvoyer = async m => resultat(await action.appeler("post", `/organisation/membres/${encodeURIComponent(m.nom)}/inviter`), tx("Invitation renvoyée"));
  const reinit2fa = async m => {
    if (!window.confirm(tx("Réinitialiser la double authentification de {x} (téléphone perdu) ? ", { x: m.nom_complet || m.nom })
      + tx("Sa session sera fermée et il la réactivera à sa prochaine connexion."))) return;
    const r = await action.appeler("post", `/organisation/membres/${encodeURIComponent(m.nom)}/double-auth/reinitialiser`);
    if (r) { setSucces(tx("Double authentification de {x} réinitialisée.", { x: m.nom_complet || m.nom })); setInfo(null); charger(); }
  };
  const modifier = async (m, corps, message) => {
    if (message && !window.confirm(message)) return;
    const res = await action.appeler("post", `/organisation/membres/${encodeURIComponent(m.nom)}/modifier`, corps);
    if (res) { setSucces(null); charger(); }
  };
  const changerRole = (m, role) => {
    if (role === m.role_org) return;
    const message = role === "admin" ? tx("Nommer {x} administrateur ? Il pourra gérer les membres, l'abonnement et les bases.", { x: m.nom_complet || m.nom })
      : m.role_org === "admin" ? tx("Retirer les droits d'administrateur à {x} ?", { x: m.nom_complet || m.nom }) : null;
    modifier(m, { role_org: role }, message);
  };
  const enregistrerBases = async () => {
    const res = await action.appeler("post", `/organisation/membres/${encodeURIComponent(bases.nom)}/bases`,
      { bases: bases.ids === null ? null : bases.ids });
    if (res) { setBases(null); setSucces(null); charger(); }
  };
  const enregistrerNom = async e => {
    e.preventDefault();
    if (await action.appeler("post", "/organisation/nom", { nom: renommer })) { setRenommer(null); charger(); }
  };

  if (lecture.erreur) return <p className="text-sm text-red-500">{lecture.erreur}</p>;
  if (!o) return <p className={texteDiscret(dark)}>{tx("Chargement…")}</p>;
  const plein = o.comptes_actifs >= o.limite_comptes;
  const ligne = `border-t ${dark ? "border-gray-700" : "border-gray-100"}`;

  return (
    <div className="space-y-4">
      <div className={carte(dark)}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {renommer !== null ? (
              <form onSubmit={enregistrerNom} className="flex items-center gap-2">
                <input value={renommer} onChange={e => setRenommer(e.target.value)} maxLength={150} minLength={2} required
                  aria-label={tx("Nom de l'organisation")} className={champ(dark)} autoFocus />
                <button className={boutonPrincipal}>{tx("Enregistrer")}</button>
                <button type="button" onClick={() => setRenommer(null)} className={boutonSecondaire(dark)} aria-label={tx("Annuler")}><X size={14} /></button>
              </form>
            ) : (
              <h2 className={`${titre(dark)} flex items-center gap-2`}>
                <Building2 size={20} strokeWidth={1.75} /> {o.nom}
                {o.peut_gerer && <button onClick={() => setRenommer(o.nom)} className="p-1 rounded hover:bg-black/5" aria-label={tx("Renommer l'organisation")}><Pencil size={13} /></button>}
              </h2>
            )}
            <p className={`${texteDiscret(dark)} mt-1`}>
              {o.type === "particulier" ? tx("Abonnement personnel") : tx("Organisation")}{" "}{tx("· ton rôle : {x}", { x: (ROLES_ORG[o.mon_role] || [o.mon_role])[0].toLowerCase() })}
            </p>
          </div>
          {o.mon_role === "admin" && <button onClick={onAbonnement} className={boutonSecondaire(dark)}>{tx("Gérer l'abonnement")}</button>}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
          <div className={`p-3 rounded-xl ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
            <p className={texteDiscret(dark)}>{tx("Formule")}</p>
            <p className="font-semibold flex items-center gap-1.5 mt-0.5">
              <ShieldCheck size={15} className={o.active ? "text-emerald-500" : "text-red-500"} />{o.formule_libelle || "—"}
            </p>
          </div>
          <div className={`p-3 rounded-xl ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
            <p className={texteDiscret(dark)}>{tx("Abonnement partagé jusqu'au")}</p>
            <p className={`font-semibold flex items-center gap-1.5 mt-0.5 ${o.active ? "" : "text-red-500"}`}>
              <Clock size={15} /> {o.abonnement_fin ? formaterDate(o.abonnement_fin) : "—"}{!o.active && tx(" (échu)")}
            </p>
          </div>
          <div className={`p-3 rounded-xl ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
            <p className={texteDiscret(dark)}>{tx("Comptes utilisés")}</p>
            <p className="font-semibold flex items-center gap-1.5 mt-0.5"><Users size={15} /> {o.comptes_actifs} / {o.limite_comptes}</p>
            <div className={`h-1.5 rounded-full mt-2 ${dark ? "bg-gray-600" : "bg-gray-200"}`}>
              <div className={`h-1.5 rounded-full ${plein ? "bg-amber-500" : "bg-foret-500"}`}
                style={{ width: `${Math.min(100, (100 * o.comptes_actifs) / Math.max(1, o.limite_comptes))}%` }} />
            </div>
          </div>
        </div>
      </div>

      {o.type === "particulier" && (
        <div className={`${carte(dark)} text-sm`}>
          {tx("Ton abonnement personnel comprend un seul compte. Pour inviter des collègues qui partageront l'abonnement, choisis une formule")}{" "}<strong>{tx("Organisation")}</strong>{" "}{tx("lors de ton prochain renouvellement.")}
        </div>
      )}

      {o.peut_gerer && (
        <div className={carte(dark)}>
          <h2 className={`${titre(dark)} flex items-center gap-2 mb-1`}><UserPlus size={19} strokeWidth={1.75} />{" "}{tx("Inviter un membre")}</h2>
          <p className={`${texteDiscret(dark)} mb-4`}>
            {o.email_disponible
              ? tx("La personne reçoit un e-mail pour activer son compte et choisir son mot de passe. Elle partage l'abonnement de l'organisation.")
              : tx("L'envoi d'e-mails n'est pas configuré : un mot de passe provisoire s'affichera, à transmettre à la personne.")}
          </p>
          <form onSubmit={inviter} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto_auto] gap-3 items-end">
            <label>
              <span className={etiquette(dark)}>{tx("Nom complet")}</span>
              <input value={f.nom_complet} onChange={e => setF({ ...f, nom_complet: e.target.value })} required minLength={2} maxLength={120}
                autoComplete="off" className={champ(dark)} />
            </label>
            <label>
              <span className={etiquette(dark)}>{tx("E-mail professionnel")}</span>
              <input type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} required maxLength={64}
                autoComplete="off" className={champ(dark)} />
            </label>
            <label>
              <span className={etiquette(dark)}>{tx("Rôle")}</span>
              <select aria-label={tx("Rôle du nouveau membre")} value={f.role_org} onChange={e => setF({ ...f, role_org: e.target.value })} className={champ(dark)}>
                {Object.entries(ROLES_ORG).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </label>
            <button type="submit" disabled={action.chargement || plein || !o.active} className={`${boutonPrincipal} flex items-center gap-1.5 justify-center`}>
              <Mail size={14} /> {action.chargement ? tx("Envoi…") : tx("Inviter")}
            </button>
          </form>
          <p className={`${texteDiscret(dark)} mt-2`}>{ROLES_ORG[f.role_org][0]} : {ROLES_ORG[f.role_org][1]}</p>
          {plein && <p className="text-xs text-amber-600 mt-2">{tx("Limite de ta formule atteinte ({limite_comptes} comptes) : désactive un compte ou passe à une formule supérieure.", { limite_comptes: o.limite_comptes })}</p>}
          {succes && <p role="status" className="text-sm text-emerald-500 mt-3">{succes}</p>}
          {action.erreur && <p role="alert" className="text-sm text-red-500 mt-3">{action.erreur}</p>}
          {info && <MotDePasseTransmis dark={dark} info={info} onFermer={() => setInfo(null)} />}
        </div>
      )}

      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-3`}>{tx("Membres ({length})", { length: o.membres.length })}</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className={`text-xs ${texteDiscret(dark)}`}>
              <th className="text-left p-2">{tx("Membre")}</th><th className="text-left p-2">{tx("Rôle")}</th>
              {o.peut_gerer && o.bases.length > 0 && <th className="text-left p-2">{tx("Bases")}</th>}
              <th className="text-left p-2">{tx("Statut")}</th>
              <th className="text-left p-2">{tx("Dernière connexion")}</th>{o.peut_gerer && <th className="text-right p-2">{tx("Actions")}</th>}
            </tr></thead>
            <tbody>
              {o.membres.map(m => (
                <tr key={m.nom} className={ligne}>
                  <td className="p-2">
                    <p className="font-medium">{m.nom_complet || m.nom}{m.moi && <span className={`${texteDiscret(dark)} font-normal`}>{" "}{tx("(toi)")}</span>}</p>
                    <p className={texteDiscret(dark)}>{m.email || m.nom}</p>
                  </td>
                  <td className="p-2">
                    {o.peut_gerer && !m.moi && m.actif ? (
                      <select aria-label={tx("Rôle de {x}", { x: m.nom_complet || m.nom })} value={m.role_org} onChange={e => changerRole(m, e.target.value)}
                        disabled={action.chargement} className={`${champ(dark)} w-auto py-1`} title={(ROLES_ORG[m.role_org] || ["", ""])[1]}>
                        {Object.entries(ROLES_ORG).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
                      </select>
                    ) : (ROLES_ORG[m.role_org] || [m.role_org])[0]}
                  </td>
                  {o.peut_gerer && o.bases.length > 0 && (
                    <td className="p-2 text-xs">
                      {m.role_org === "admin" ? <span className={texteDiscret(dark)}>{tx("Toutes (administrateur)")}</span> : (
                        <button onClick={() => setBases({ nom: m.nom, libelle: m.nom_complet || m.nom, ids: m.bases })}
                          className="flex items-center gap-1 hover:underline" aria-label={tx("Bases de {x}", { x: m.nom_complet || m.nom })}>
                          <Database size={12} /> {m.bases ? tx(m.bases.length > 1 ? "{n} bases sur {total}" : "{n} base sur {total}", { n: m.bases.length, total: o.bases.length }) : tx("Toutes")}
                        </button>
                      )}
                    </td>
                  )}
                  <td className="p-2">
                    <div className="flex flex-wrap gap-1"><Badge statut={m.statut} />
                      {m.double_auth && <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-foret-500/15 text-foret-500" title={tx("Double authentification active")}>{tx("2FA")}</span>}</div>
                  </td>
                  <td className="p-2 text-xs">{m.derniere_connexion ? formaterDate(m.derniere_connexion) : "—"}</td>
                  {o.peut_gerer && (
                    <td className="p-2">
                      {!m.moi && (
                        <div className="flex flex-wrap justify-end gap-1.5">
                          {m.actif && m.statut !== "actif" && (
                            <button onClick={() => renvoyer(m)} className={`${boutonSecondaire(dark)} flex items-center gap-1`} title={tx("Renvoyer l'invitation")}>
                              <RotateCcw size={12} />{" "}{tx("Renvoyer")}
                            </button>
                          )}
                          {m.double_auth && (
                            <button onClick={() => reinit2fa(m)} className={`${boutonSecondaire(dark)} flex items-center gap-1`}
                              title={tx("Téléphone perdu : le membre réactivera la double authentification")}><Smartphone size={12} />{" "}{tx("Réinit. 2FA")}</button>
                          )}
                          {m.actif ? (
                            <button onClick={() => modifier(m, { actif: false }, tx("Désactiver {x} ? Sa session sera fermée et une place se libère.", { x: m.nom_complet || m.nom }))}
                              className={`${boutonSecondaire(dark)} flex items-center gap-1`}><UserX size={12} />{" "}{tx("Désactiver")}</button>
                          ) : (
                            <button onClick={() => modifier(m, { actif: true })} className={`${boutonSecondaire(dark)} flex items-center gap-1`}>
                              <UserCheck size={12} />{" "}{tx("Réactiver")}</button>
                          )}
                        </div>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {bases && (
          <div role="dialog" aria-label={tx("Bases accessibles à {libelle}", { libelle: bases.libelle })}
            className={`mt-4 p-4 rounded-xl border ${dark ? "border-gray-600 bg-gray-700/40" : "border-gray-200 bg-gray-50"}`}>
            <p className="text-sm font-semibold mb-2">{tx("Bases accessibles à {libelle}", { libelle: bases.libelle })}</p>
            <label className="flex items-center gap-2 text-sm mb-2">
              <input type="radio" checked={bases.ids === null} onChange={() => setBases({ ...bases, ids: null })} />
              {tx("Toutes les bases de l'organisation (y compris les prochaines)")}
            </label>
            <label className="flex items-center gap-2 text-sm mb-1">
              <input type="radio" checked={bases.ids !== null} onChange={() => setBases({ ...bases, ids: bases.ids || [] })} />
              {tx("Seulement :")}
            </label>
            <div className="pl-6 grid sm:grid-cols-2 gap-1">
              {o.bases.map(b => (
                <label key={b.id} className={`flex items-center gap-2 text-sm ${bases.ids === null ? "opacity-50" : ""}`}>
                  <input type="checkbox" disabled={bases.ids === null} checked={bases.ids !== null && bases.ids.includes(b.id)}
                    onChange={e => setBases({ ...bases, ids: e.target.checked ? [...bases.ids, b.id] : bases.ids.filter(x => x !== b.id) })} />
                  {b.nom}
                </label>
              ))}
            </div>
            <p className={`${texteDiscret(dark)} mt-2`}>{tx("Une base non cochée devient invisible pour ce membre : ni données, ni alertes, ni e-mails.")}</p>
            <div className="flex gap-2 mt-3">
              <button onClick={enregistrerBases} disabled={action.chargement || (bases.ids !== null && bases.ids.length === 0)} className={boutonPrincipal}>{tx("Enregistrer")}</button>
              <button onClick={() => setBases(null)} className={boutonSecondaire(dark)}>{tx("Annuler")}</button>
            </div>
          </div>
        )}
        {!o.peut_gerer && action.erreur && <p role="alert" className="text-sm text-red-500 mt-3">{action.erreur}</p>}
      </div>
    </div>
  );
}

// ── Journal d'activité de l'organisation (administrateur et auditeur) ──
const ACTIONS = {
  connexion: tx("Connexion"), connexion_refusee: tx("Connexion refusée"), alerte_suivie: tx("Alerte traitée"),
  rapport_pdf: tx("Rapport PDF téléchargé"), source_supprimee: tx("Base supprimée"), source_defaut: tx("Base par défaut choisie"),
  membre_invite: tx("Membre invité"), membre_modifie: tx("Membre modifié"), acces_bases: tx("Accès aux bases modifié"),
  abonnement_paye: tx("Abonnement payé"), abonnement_commande: tx("Abonnement commandé"), mot_de_passe_change: tx("Mot de passe changé"),
};

export function PanelJournal({ dark }) {
  const { appeler, erreur } = useAPI();
  const [d, setD] = useState(null);
  const [vue, setVue] = useState("alertes");
  useEffect(() => { appeler("get", "/organisation/journal").then(r => r && setD(r)); }, [appeler]);
  if (erreur) return <p className="text-sm text-red-500">{erreur}</p>;
  if (!d) return <p className={texteDiscret(dark)}>{tx("Chargement…")}</p>;
  const exporter = () => vue === "alertes"
    ? telechargerCsv(nomFichier("journal alertes", "csv"), ["date", "auteur", "nature", "texte", "niveau", "operation", "base"], d.traitements_alertes)
    : telechargerCsv(nomFichier("journal activite", "csv"), ["date", "utilisateur", "action", "adresse_ip"], d.evenements);
  const ligne = `border-t ${dark ? "border-gray-700" : "border-gray-100"}`;
  return (
    <div className={carte(dark)}>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <h2 className={`${titre(dark)} flex items-center gap-2`}><ScrollText size={18} />{" "}{tx("Journal de l'organisation")}</h2>
          <p className={texteDiscret(dark)}>{tx("Qui a fait quoi et quand : traitement des alertes, connexions, bases, membres. Rien ne peut y être modifié.")}</p>
        </div>
        <button onClick={exporter} className={`${boutonSecondaire(dark)} flex items-center gap-1.5`}><Download size={13} />{" "}{tx("CSV")}</button>
      </div>
      <div role="tablist" className="flex gap-1 mb-3">
        {[["alertes", tx("Traitement des alertes ({length})", { length: d.traitements_alertes.length })], ["activite", tx("Activité ({length})", { length: d.evenements.length })]].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={vue === k} onClick={() => setVue(k)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium ${vue === k ? (dark ? "bg-gray-700 text-white" : "bg-foret-50 text-foret-800") : texteDiscret(dark)}`}>{l}</button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          {vue === "alertes" ? (
            <>
              <thead><tr className={`text-xs ${texteDiscret(dark)}`}><th className="text-left p-2">{tx("Date")}</th><th className="text-left p-2">{tx("Personne")}</th>
                <th className="text-left p-2">{tx("Base · opération")}</th><th className="text-left p-2">{tx("Action")}</th></tr></thead>
              <tbody>
                {d.traitements_alertes.map((t, i) => (
                  <tr key={i} className={ligne}>
                    <td className="p-2 text-xs whitespace-nowrap">{formaterDate(t.date)}</td>
                    <td className="p-2 text-xs [overflow-wrap:anywhere]">{t.auteur}</td>
                    <td className="p-2 text-xs">{t.base} · {t.operation} <span className={texteDiscret(dark)}>({tx(t.niveau)})</span></td>
                    <td className="p-2 text-xs">{t.texte}</td>
                  </tr>
                ))}
              </tbody>
            </>
          ) : (
            <>
              <thead><tr className={`text-xs ${texteDiscret(dark)}`}><th className="text-left p-2">{tx("Date")}</th><th className="text-left p-2">{tx("Personne")}</th>
                <th className="text-left p-2">{tx("Action")}</th><th className="text-left p-2">{tx("Adresse IP")}</th></tr></thead>
              <tbody>
                {d.evenements.map((e, i) => (
                  <tr key={i} className={ligne}>
                    <td className="p-2 text-xs whitespace-nowrap">{formaterDate(e.date)}</td>
                    <td className="p-2 text-xs [overflow-wrap:anywhere]">{e.utilisateur}</td>
                    <td className="p-2 text-xs">{ACTIONS[e.action] || e.action}</td>
                    <td className="p-2 text-xs">{e.adresse_ip || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </>
          )}
        </table>
        {(vue === "alertes" ? d.traitements_alertes : d.evenements).length === 0 && <p className={`${texteDiscret(dark)} p-2`}>{tx("Rien pour l'instant.")}</p>}
      </div>
    </div>
  );
}
