// Mon organisation : abonnement partagé, membres, invitations par e-mail (administrateur de l'organisation).
import { useState, useEffect, useCallback } from "react";
import {
  Building2, UserPlus, Mail, RotateCcw, UserX, UserCheck, ShieldCheck, Clock, Copy, Check, Users, Pencil, X,
} from "lucide-react";
import { useAPI } from "../useAPI";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";

const STATUTS = {
  actif: ["Actif", "bg-emerald-500/15 text-emerald-600"],
  invitation_en_attente: ["Invitation envoyée", "bg-laiton-400/20 text-laiton-700"],
  invitation_expiree: ["Invitation expirée", "bg-amber-500/15 text-amber-600"],
  desactive: ["Désactivé", "bg-gray-500/15 text-gray-500"],
};

function Badge({ statut }) {
  const [texte, style] = STATUTS[statut] || [statut, ""];
  return <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${style}`}>{texte}</span>;
}

function MotDePasseTransmis({ dark, info, onFermer }) {
  const [copie, setCopie] = useState(false);
  return (
    <div className={`mt-4 p-4 rounded-xl border ${dark ? "border-amber-500/40 bg-amber-500/10" : "border-amber-300 bg-amber-50"}`}>
      <p className="text-sm font-semibold mb-1">E-mail non envoyé : transmets ces informations à {info.nom}</p>
      {info.erreur_envoi && <p className="text-xs text-red-500 mb-2">{info.erreur_envoi}</p>}
      <p className="text-sm">Identifiant : <code>{info.nom}</code></p>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-sm">Mot de passe provisoire :</span>
        <code className="px-2 py-1 rounded bg-black/10 font-mono">{info.mot_de_passe_provisoire}</code>
        <button onClick={() => { navigator.clipboard?.writeText(info.mot_de_passe_provisoire); setCopie(true); }}
          className={boutonSecondaire(dark)} aria-label="Copier le mot de passe">{copie ? <Check size={13} /> : <Copy size={13} />}</button>
      </div>
      <p className={`${texteDiscret(dark)} mt-2`}>Valable {info.valable_heures} h, affiché une seule fois. La personne le changera à sa première connexion.</p>
      <button onClick={onFermer} className={`${boutonSecondaire(dark)} mt-3`}>J'ai transmis le mot de passe</button>
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

  const charger = useCallback(() => {
    lecture.appeler("get", "/organisation").then(r => r && setO(r.data));
  }, [lecture.appeler]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  const resultat = (res, quoi) => {
    if (!res) return;
    if (res.invitation_envoyee) { setSucces(`${quoi} : e-mail d'invitation envoyé à ${res.email}.`); setInfo(null); }
    else { setInfo(res); setSucces(null); }
    charger();
  };
  const inviter = async e => {
    e.preventDefault();
    const res = await action.appeler("post", "/organisation/membres", { ...f, email: f.email.trim() });
    if (res) setF({ nom_complet: "", email: "", role_org: "analyste" });
    resultat(res, "Membre ajouté");
  };
  const renvoyer = async m => resultat(await action.appeler("post", `/organisation/membres/${encodeURIComponent(m.nom)}/inviter`), "Invitation renvoyée");
  const modifier = async (m, corps, message) => {
    if (message && !window.confirm(message)) return;
    const res = await action.appeler("post", `/organisation/membres/${encodeURIComponent(m.nom)}/modifier`, corps);
    if (res) { setSucces(null); charger(); }
  };
  const enregistrerNom = async e => {
    e.preventDefault();
    if (await action.appeler("post", "/organisation/nom", { nom: renommer })) { setRenommer(null); charger(); }
  };

  if (lecture.erreur) return <p className="text-sm text-red-500">{lecture.erreur}</p>;
  if (!o) return <p className={texteDiscret(dark)}>Chargement…</p>;
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
                  aria-label="Nom de l'organisation" className={champ(dark)} autoFocus />
                <button className={boutonPrincipal}>Enregistrer</button>
                <button type="button" onClick={() => setRenommer(null)} className={boutonSecondaire(dark)} aria-label="Annuler"><X size={14} /></button>
              </form>
            ) : (
              <h2 className={`${titre(dark)} flex items-center gap-2`}>
                <Building2 size={20} strokeWidth={1.75} /> {o.nom}
                {o.peut_gerer && <button onClick={() => setRenommer(o.nom)} className="p-1 rounded hover:bg-black/5" aria-label="Renommer l'organisation"><Pencil size={13} /></button>}
              </h2>
            )}
            <p className={`${texteDiscret(dark)} mt-1`}>
              {o.type === "particulier" ? "Abonnement personnel" : "Organisation"} · ton rôle : {o.mon_role === "admin" ? "administrateur" : "analyste"}
            </p>
          </div>
          {o.mon_role === "admin" && <button onClick={onAbonnement} className={boutonSecondaire(dark)}>Gérer l'abonnement</button>}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
          <div className={`p-3 rounded-xl ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
            <p className={texteDiscret(dark)}>Formule</p>
            <p className="font-semibold flex items-center gap-1.5 mt-0.5">
              <ShieldCheck size={15} className={o.active ? "text-emerald-500" : "text-red-500"} />{o.formule_libelle || "—"}
            </p>
          </div>
          <div className={`p-3 rounded-xl ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
            <p className={texteDiscret(dark)}>Abonnement partagé jusqu'au</p>
            <p className={`font-semibold flex items-center gap-1.5 mt-0.5 ${o.active ? "" : "text-red-500"}`}>
              <Clock size={15} /> {o.abonnement_fin ? formaterDate(o.abonnement_fin) : "—"}{!o.active && " (échu)"}
            </p>
          </div>
          <div className={`p-3 rounded-xl ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
            <p className={texteDiscret(dark)}>Comptes utilisés</p>
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
          Ton abonnement personnel comprend un seul compte. Pour inviter des collègues qui partageront l'abonnement, choisis une
          formule <strong>Organisation</strong> lors de ton prochain renouvellement.
        </div>
      )}

      {o.peut_gerer && (
        <div className={carte(dark)}>
          <h2 className={`${titre(dark)} flex items-center gap-2 mb-1`}><UserPlus size={19} strokeWidth={1.75} /> Inviter un membre</h2>
          <p className={`${texteDiscret(dark)} mb-4`}>
            {o.email_disponible
              ? "La personne reçoit un e-mail pour activer son compte et choisir son mot de passe. Elle partage l'abonnement de l'organisation."
              : "L'envoi d'e-mails n'est pas configuré : un mot de passe provisoire s'affichera, à transmettre à la personne."}
            {" "}Un analyste interroge les données ; un administrateur gère aussi les membres, l'abonnement et les bases connectées.
          </p>
          <form onSubmit={inviter} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto_auto] gap-3 items-end">
            <label>
              <span className={etiquette(dark)}>Nom complet</span>
              <input value={f.nom_complet} onChange={e => setF({ ...f, nom_complet: e.target.value })} required minLength={2} maxLength={120}
                autoComplete="off" className={champ(dark)} />
            </label>
            <label>
              <span className={etiquette(dark)}>E-mail professionnel</span>
              <input type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} required maxLength={64}
                autoComplete="off" className={champ(dark)} />
            </label>
            <label>
              <span className={etiquette(dark)}>Rôle</span>
              <select value={f.role_org} onChange={e => setF({ ...f, role_org: e.target.value })} className={champ(dark)}>
                <option value="analyste">Analyste</option>
                <option value="admin">Administrateur</option>
              </select>
            </label>
            <button type="submit" disabled={action.chargement || plein || !o.active} className={`${boutonPrincipal} flex items-center gap-1.5 justify-center`}>
              <Mail size={14} /> {action.chargement ? "Envoi…" : "Inviter"}
            </button>
          </form>
          {plein && <p className="text-xs text-amber-600 mt-2">Limite de ta formule atteinte ({o.limite_comptes} comptes) : désactive un compte ou passe à une formule supérieure.</p>}
          {succes && <p role="status" className="text-sm text-emerald-500 mt-3">{succes}</p>}
          {action.erreur && <p role="alert" className="text-sm text-red-500 mt-3">{action.erreur}</p>}
          {info && <MotDePasseTransmis dark={dark} info={info} onFermer={() => setInfo(null)} />}
        </div>
      )}

      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-3`}>Membres ({o.membres.length})</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className={`text-xs ${texteDiscret(dark)}`}>
              <th className="text-left p-2">Membre</th><th className="text-left p-2">Rôle</th><th className="text-left p-2">Statut</th>
              <th className="text-left p-2">Dernière connexion</th>{o.peut_gerer && <th className="text-right p-2">Actions</th>}
            </tr></thead>
            <tbody>
              {o.membres.map(m => (
                <tr key={m.nom} className={ligne}>
                  <td className="p-2">
                    <p className="font-medium">{m.nom_complet || m.nom}{m.moi && <span className={`${texteDiscret(dark)} font-normal`}> (toi)</span>}</p>
                    <p className={texteDiscret(dark)}>{m.email || m.nom}</p>
                  </td>
                  <td className="p-2">{m.role_org === "admin" ? "Administrateur" : "Analyste"}</td>
                  <td className="p-2"><Badge statut={m.statut} /></td>
                  <td className="p-2 text-xs">{m.derniere_connexion ? formaterDate(m.derniere_connexion) : "—"}</td>
                  {o.peut_gerer && (
                    <td className="p-2">
                      {!m.moi && (
                        <div className="flex flex-wrap justify-end gap-1.5">
                          {m.actif && m.statut !== "actif" && (
                            <button onClick={() => renvoyer(m)} className={`${boutonSecondaire(dark)} flex items-center gap-1`} title="Renvoyer l'invitation">
                              <RotateCcw size={12} /> Renvoyer
                            </button>
                          )}
                          {m.actif && (
                            <button onClick={() => modifier(m, { role_org: m.role_org === "admin" ? "analyste" : "admin" },
                              `${m.role_org === "admin" ? "Retirer les droits d'administrateur à" : "Nommer administrateur"} ${m.nom_complet || m.nom} ?`)}
                              className={boutonSecondaire(dark)}>{m.role_org === "admin" ? "→ Analyste" : "→ Admin"}</button>
                          )}
                          {m.actif ? (
                            <button onClick={() => modifier(m, { actif: false }, `Désactiver ${m.nom_complet || m.nom} ? Sa session sera fermée et une place se libère.`)}
                              className={`${boutonSecondaire(dark)} flex items-center gap-1`}><UserX size={12} /> Désactiver</button>
                          ) : (
                            <button onClick={() => modifier(m, { actif: true })} className={`${boutonSecondaire(dark)} flex items-center gap-1`}>
                              <UserCheck size={12} /> Réactiver</button>
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
      </div>
    </div>
  );
}
