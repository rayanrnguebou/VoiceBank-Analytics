// Comptes : changement de mot de passe (tous) et gestion des comptes (administrateur).
// Pas d'inscription libre : c'est l'administrateur qui crée les comptes, avec un mot de passe
// provisoire (affiché une seule fois, valable 72 h) que la personne change à sa première connexion.
import { useState, useEffect, useCallback } from "react";
import {
  KeyRound, UserPlus, Copy, Check, RotateCcw, Lock, ShieldCheck, UserX, UserCheck, X, Circle, CircleCheck, Mail, Smartphone,
} from "lucide-react";
import { useAPI } from "../useAPI";
import { appliquerJeton, http } from "../api";
import { Logo } from "./BarreLaterale";
import { SectionDoubleAuth } from "./DoubleAuth";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";
import { tx } from "../i18n";

// Même règles que l'API (app/securite.py) : affichées en direct pour guider la saisie.
export function reglesMotDePasse(mdp, nom) {
  const familles = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(r => r.test(mdp)).length;
  return [
    { ok: mdp.length >= 12, texte: tx("Au moins 12 caractères") },
    { ok: familles >= 3, texte: tx("Trois types parmi : minuscules, majuscules, chiffres, symboles") },
    { ok: !!mdp && !mdp.toLowerCase().includes((nom || "").toLowerCase()), texte: tx("Ne contient pas l'identifiant") },
  ];
}

export function FormulaireMotDePasse({ dark, session, force, onTermine, onAnnuler }) {
  const { appeler, chargement, erreur, setErreur } = useAPI();
  const [actuel, setActuel] = useState("");
  const [nouveau, setNouveau] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const regles = reglesMotDePasse(nouveau, session.utilisateur);
  const valide = regles.every(r => r.ok) && nouveau === confirmation && actuel;

  const envoyer = async (e) => {
    e.preventDefault();
    if (nouveau !== confirmation) { setErreur(tx("Les deux saisies ne correspondent pas")); return; }
    const res = await appeler("post", "/auth/mot-de-passe", { actuel, nouveau });
    if (res) onTermine(appliquerJeton(res));
  };

  const style = force
    ? "w-full px-4 py-3 rounded-xl bg-gray-700 border border-gray-600 text-white text-sm outline-none focus:border-foret-500"
    : champ(dark);
  const lib = force ? "block text-xs text-gray-400 mb-1" : etiquette(dark);

  return (
    <form onSubmit={envoyer} className="space-y-3">
      {/* Champ caché : aide les gestionnaires de mots de passe à associer le bon compte */}
      <input type="text" autoComplete="username" value={session.utilisateur} readOnly hidden />
      <label className="block">
        <span className={lib}>{force ? tx("Mot de passe provisoire") : tx("Mot de passe actuel")}</span>
        <input type="password" value={actuel} onChange={e => setActuel(e.target.value)} autoComplete="current-password"
          required maxLength={128} className={style} />
      </label>
      <label className="block">
        <span className={lib}>{tx("Nouveau mot de passe")}</span>
        <input type="password" value={nouveau} onChange={e => setNouveau(e.target.value)} autoComplete="new-password"
          required maxLength={72} className={style} />
      </label>
      <ul className="space-y-1" aria-label={tx("Règles du mot de passe")}>
        {regles.map(r => (
          <li key={r.texte} className={`flex items-center gap-1.5 text-xs ${r.ok ? "text-emerald-500" : force || dark ? "text-gray-400" : "text-gray-500"}`}>
            {r.ok ? <CircleCheck size={13} /> : <Circle size={13} />} {r.texte}
          </li>
        ))}
      </ul>
      <label className="block">
        <span className={lib}>{tx("Confirme le nouveau mot de passe")}</span>
        <input type="password" value={confirmation} onChange={e => setConfirmation(e.target.value)} autoComplete="new-password"
          required maxLength={72} className={style} />
      </label>
      {confirmation && nouveau !== confirmation && <p className="text-xs text-amber-500">{tx("Les deux saisies ne correspondent pas")}</p>}
      {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
      <div className="flex gap-2 pt-1">
        <button type="submit" disabled={chargement || !valide}
          className={force ? "flex-1 flex items-center justify-center gap-2 py-3 bg-foret-600 hover:bg-foret-700 text-white font-semibold rounded-xl disabled:opacity-50" : boutonPrincipal}>
          <KeyRound size={15} className={force ? "" : "inline -mt-0.5 mr-1"} /> {chargement ? tx("Enregistrement…") : tx("Enregistrer")}
        </button>
        <button type="button" onClick={onAnnuler}
          className={force ? "px-4 py-3 rounded-xl text-sm text-gray-300 hover:bg-gray-800" : boutonSecondaire(dark)}>
          {force ? tx("Se déconnecter") : tx("Annuler")}
        </button>
      </div>
    </form>
  );
}

// Première connexion : écran plein, rien d'autre n'est accessible avant le changement.
export function EcranMotDePasseProvisoire({ session, onTermine, onDeconnexion }) {
  return (
    <div className="min-h-screen bg-foret-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-gray-900 border border-foret-800 rounded-2xl p-8 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <Logo />
          <div>
            <h1 className="text-white font-bold">{tx("Bienvenue, {utilisateur}", { utilisateur: session.utilisateur })}</h1>
            <p className="text-gray-400 text-xs">{tx("Première connexion")}</p>
          </div>
        </div>
        <p className="text-sm text-gray-300 mb-5">
          {tx("Ton mot de passe est provisoire. Choisis-en un personnel : toi seul le connaîtras, même l'administrateur ne pourra pas le voir.")}
        </p>
        <FormulaireMotDePasse session={session} force onTermine={onTermine} onAnnuler={onDeconnexion} />
      </div>
    </div>
  );
}

export function FenetreMotDePasse({ dark, session, onTermine, onFermer }) {
  const [fait, setFait] = useState(false);
  useEffect(() => {
    const echap = e => e.key === "Escape" && onFermer();
    window.addEventListener("keydown", echap);
    return () => window.removeEventListener("keydown", echap);
  }, [onFermer]);
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4" onClick={onFermer}>
      <div role="dialog" aria-modal="true" aria-labelledby="titre-mdp" onClick={e => e.stopPropagation()}
        className={`w-full max-w-md max-h-[92vh] overflow-y-auto ${carte(dark)}`}>
        <div className="flex items-center justify-between mb-4">
          <h2 id="titre-mdp" className={`${titre(dark)} flex items-center gap-2`}><KeyRound size={18} />{" "}{tx("Sécurité de mon compte")}</h2>
          <button onClick={onFermer} aria-label={tx("Fermer")} className={boutonSecondaire(dark)}><X size={14} /></button>
        </div>
        <SectionDoubleAuth dark={dark} onSession={onTermine} />
        <EmailRecuperation dark={dark} session={session} />
        {fait ? (
          <div className="space-y-3">
            <p className="text-sm text-emerald-500 flex items-center gap-2"><ShieldCheck size={16} />{" "}{tx("Mot de passe changé.")}</p>
            <p className={texteDiscret(dark)}>{tx("Tes autres sessions ouvertes (autres onglets ou appareils) ont été déconnectées.")}</p>
            <button onClick={onFermer} className={boutonPrincipal}>{tx("Fermer")}</button>
          </div>
        ) : (
          <FormulaireMotDePasse dark={dark} session={session} onAnnuler={onFermer}
            onTermine={s => { setFait(true); onTermine(s); }} />
        )}
      </div>
    </div>
  );
}

// Adresse e-mail de récupération (comptes internes) : permet de recevoir un code si le mot de passe est oublié
function EmailRecuperation({ dark, session }) {
  const { appeler, chargement, erreur } = useAPI();
  const [infos, setInfos] = useState(null);
  const [edition, setEdition] = useState(false);
  const [email, setEmail] = useState("");
  const [mdp, setMdp] = useState("");
  useEffect(() => {
    http.get("/auth/moi").then(r => setInfos(r.data)).catch(() => {});
  }, []);
  if (!infos || ["visiteur", "client"].includes(infos.role)) return null;
  const enregistrer = async (e) => {
    e.preventDefault();
    const res = await appeler("post", "/auth/email", { mot_de_passe: mdp, email: email.trim() || null });
    if (res) { setInfos({ ...infos, email: res.email }); setEdition(false); setMdp(""); }
  };
  return (
    <div className={`mb-5 p-3 rounded-xl text-sm ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
      <p className={`flex items-center gap-2 font-medium ${dark ? "text-gray-200" : "text-gray-800"}`}>
        <Mail size={15} />{" "}{tx("E-mail de récupération")}
      </p>
      {!edition ? (
        <div className="flex flex-wrap items-center justify-between gap-2 mt-1">
          <span className={texteDiscret(dark)}>
            {infos.email ? infos.email : tx("Aucune adresse : en cas d'oubli, seul l'administrateur pourra te débloquer.")}
          </span>
          <button type="button" onClick={() => { setEmail(infos.email || ""); setEdition(true); }} className={boutonSecondaire(dark)}>
            {infos.email ? tx("Modifier") : tx("Ajouter")}
          </button>
        </div>
      ) : (
        <form onSubmit={enregistrer} className="space-y-2 mt-2">
          <input type="text" autoComplete="username" value={session.utilisateur} readOnly hidden />
          <label className="block">
            <span className={etiquette(dark)}>{tx("Adresse e-mail (vide pour la retirer)")}</span>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} maxLength={64} autoComplete="email" className={champ(dark)} />
          </label>
          <label className="block">
            <span className={etiquette(dark)}>{tx("Mot de passe actuel (pour confirmer)")}</span>
            <input type="password" value={mdp} onChange={e => setMdp(e.target.value)} required maxLength={128}
              autoComplete="current-password" className={champ(dark)} />
          </label>
          {erreur && <p role="alert" className="text-sm text-red-500">{erreur}</p>}
          <div className="flex gap-2">
            <button type="submit" disabled={chargement} className={boutonPrincipal}>{chargement ? tx("Enregistrement…") : tx("Enregistrer l'adresse")}</button>
            <button type="button" onClick={() => setEdition(false)} className={boutonSecondaire(dark)}>{tx("Annuler")}</button>
          </div>
        </form>
      )}
      {!infos.oubli_par_email && infos.email && (
        <p className="text-xs text-amber-500 mt-2">{tx("L'envoi d'e-mails n'est pas encore configuré sur le serveur.")}</p>
      )}
    </div>
  );
}

// ── Mot de passe provisoire : affiché une seule fois ───────────────
function MotDePasseAffiche({ dark, info, onFermer }) {
  const [copie, setCopie] = useState(false);
  const copier = async () => {
    try { await navigator.clipboard.writeText(info.mot_de_passe_provisoire); setCopie(true); } catch (e) { /* rien */ }
  };
  return (
    <div className={`p-4 rounded-xl border-l-4 border-laiton-400 ${dark ? "bg-foret-900/50" : "bg-foret-50"}`}>
      <p className={`text-sm font-semibold mb-2 ${dark ? "text-white" : "text-gray-900"}`}>
        {tx("Mot de passe provisoire de")}{" "}<span className="font-mono">{info.nom}</span>
      </p>
      <div className="flex items-center gap-2 mb-2">
        <code className={`flex-1 px-3 py-2 rounded-lg font-mono text-base tracking-wide select-all ${dark ? "bg-gray-900 text-laiton-300" : "bg-white text-foret-800"}`}>
          {info.mot_de_passe_provisoire}
        </code>
        <button onClick={copier} className={boutonSecondaire(dark)} aria-label={tx("Copier le mot de passe")}>
          {copie ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
        </button>
      </div>
      <p className={texteDiscret(dark)}>
        {tx("Affiché une seule fois et valable {valable_heures} h. Transmets-le par un autre canal que l'identifiant (de vive voix, par téléphone…). La personne devra le changer à sa première connexion.", { valable_heures: info.valable_heures })}
      </p>
      <button onClick={onFermer} className={`mt-3 ${boutonSecondaire(dark)}`}>{tx("C'est noté, masquer")}</button>
    </div>
  );
}

const BADGE = "text-[11px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap";

function Statut({ c }) {
  if (!c.actif) return <span className={`${BADGE} bg-gray-500/15 text-gray-500`}>{tx("Désactivé")}</span>;
  if (c.verrouille) return <span className={`${BADGE} bg-red-500/15 text-red-500`} title={tx("Nombreux mots de passe erronés depuis plusieurs adresses : seules ses adresses habituelles sont acceptées")}>{tx("Protégé (attaque)")}</span>;
  if (c.provisoire_expire) return <span className={`${BADGE} bg-amber-500/15 text-amber-600`}>{tx("Mot de passe provisoire expiré")}</span>;
  if (c.doit_changer_mdp) return <span className={`${BADGE} bg-amber-500/15 text-amber-600`}>{tx("Première connexion en attente")}</span>;
  return <span className={`${BADGE} bg-emerald-500/15 text-emerald-600`}>{tx("Actif")}</span>;
}

export function PanelComptes({ dark, session }) {
  const liste = useAPI();
  const action = useAPI();
  const [donnees, setDonnees] = useState(null);
  const [nom, setNom] = useState("");
  const [role, setRole] = useState("analyste");
  const [email, setEmail] = useState("");
  const [provisoire, setProvisoire] = useState(null);

  const charger = useCallback(() => {
    liste.appeler("get", "/admin/utilisateurs").then(r => r && setDonnees(r));
  }, [liste.appeler]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  const creer = async (e) => {
    e.preventDefault();
    const res = await action.appeler("post", "/admin/utilisateurs", { nom: nom.trim().toLowerCase(), role, email: email.trim() || null });
    if (res) { setProvisoire(res); setNom(""); setRole("analyste"); setEmail(""); charger(); }
  };
  const reinitialiser = async (c) => {
    if (!window.confirm(tx("Générer un nouveau mot de passe provisoire pour {nom} ? Ses sessions en cours seront fermées.", { nom: c.nom }))) return;
    const res = await action.appeler("post", `/admin/utilisateurs/${encodeURIComponent(c.nom)}/reinitialiser`);
    if (res) { setProvisoire(res); charger(); }
  };
  const modifier = async (c, corps, message) => {
    if (message && !window.confirm(message)) return;
    const res = await action.appeler("post", `/admin/utilisateurs/${encodeURIComponent(c.nom)}/modifier`, corps);
    if (res) charger();
  };

  const gestion = donnees?.gestion_comptes && !donnees?.lecture_seule;
  const comptes = donnees?.data || [];

  return (
    <div className="space-y-4">
      {donnees?.lecture_seule && (
        <div className={`p-4 rounded-xl text-sm ${dark ? "bg-foret-900/40 text-foret-100" : "bg-foret-50 text-foret-900"}`}>
          {tx("Démonstration : voici comment l'administrateur gère les comptes de son organisation (création avec mot de passe provisoire, blocage, désactivation). Les noms sont anonymisés et les actions désactivées.")}
        </div>
      )}
      {donnees && !donnees.gestion_comptes && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-600 text-sm">
          {tx("Les comptes sont encore lus dans la configuration (VOICEBANK_USERS). Mets la base à jour avec")}
          <code className="mx-1">{tx("docker compose exec postgres sh /voicebank_securite/migrer.sh")}</code>
          {tx("puis redémarre l'API pour gérer les comptes ici.")}
        </div>
      )}

      {gestion && (
        <div className={carte(dark)}>
          <h2 className={`${titre(dark)} flex items-center gap-2 mb-1`}><UserPlus size={19} strokeWidth={1.75} />{" "}{tx("Créer un compte")}</h2>
          <p className={`${texteDiscret(dark)} mb-4`}>
            {tx("Pas d'inscription libre : seuls les comptes créés ici peuvent se connecter. Un analyste consulte les données (noms des clients masqués) ; un administrateur gère aussi les comptes, les corrections et l'audit.")}
          </p>
          <form onSubmit={creer} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto_auto] gap-3 items-end">
            <label>
              <span className={etiquette(dark)}>{tx("Identifiant")}</span>
              <input value={nom} onChange={e => setNom(e.target.value)} required minLength={3} maxLength={32}
                pattern={"[a-zA-Z0-9][a-zA-Z0-9._\\-]{2,31}"} placeholder={tx("ex. jean.mballa")} autoComplete="off"
                title={tx("3 à 32 caractères : lettres, chiffres, point, tiret, souligné")} className={champ(dark)} />
            </label>
            <label>
              <span className={etiquette(dark)}>{tx("E-mail (facultatif)")}</span>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} maxLength={64} autoComplete="off"
                placeholder={tx("pour « mot de passe oublié »")} className={champ(dark)} />
            </label>
            <label>
              <span className={etiquette(dark)}>{tx("Rôle")}</span>
              <select value={role} onChange={e => setRole(e.target.value)} className={champ(dark)}>
                <option value="analyste">{tx("Analyste")}</option>
                <option value="admin">{tx("Administrateur")}</option>
              </select>
            </label>
            <button type="submit" disabled={action.chargement} className={boutonPrincipal}>{tx("Créer")}</button>
          </form>
          {action.erreur && <p className="text-sm text-red-500 mt-3">{action.erreur}</p>}
          {provisoire && <div className="mt-4"><MotDePasseAffiche dark={dark} info={provisoire} onFermer={() => setProvisoire(null)} /></div>}
        </div>
      )}

      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-3`}>{tx("Comptes ({length})", { length: comptes.length })}</h2>
        {liste.erreur && <p className="text-sm text-red-500">{liste.erreur}</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
              <th className="text-left p-2">{tx("Identifiant")}</th><th className="text-left p-2">{tx("Rôle")}</th>
              <th className="text-left p-2">{tx("Statut")}</th><th className="text-left p-2">{tx("Dernière connexion")}</th>
              {gestion && <th className="text-right p-2">{tx("Actions")}</th>}
            </tr></thead>
            <tbody>
              {comptes.map(c => {
                const moi = c.nom === session.utilisateur;
                return (
                  <tr key={c.nom} className={`border-t ${dark ? "border-gray-700" : "border-gray-100"} ${c.actif ? "" : "opacity-60"}`}>
                    <td className="p-2">
                      <span className="font-medium">{c.nom}</span>{moi && <span className={`${texteDiscret(dark)} ml-1`}>{tx("(toi)")}</span>}
                      {c.cree_par && <p className={texteDiscret(dark)}>{tx("créé par {cree_par}", { cree_par: c.cree_par })}{c.date_creation ? ` le ${formaterDate(c.date_creation)}` : ""}</p>}
                    </td>
                    <td className="p-2">
                      {c.role === "visiteur" ? <span>{tx("Essai gratuit")}</span>
                        : c.role === "client" ? (
                          <span>{{ admin: tx("Admin"), analyste: tx("Analyste"), lecteur: tx("Lecteur"), auditeur: tx("Auditeur") }[c.role_org] || tx("Membre")}{" "}{tx("client")}
                            {c.organisation && <span className={`block ${texteDiscret(dark)}`}>{c.organisation}</span>}</span>
                        ) : gestion && !moi && c.actif ? (
                        <select value={c.role} aria-label={tx("Rôle de {nom}", { nom: c.nom })} className={`${champ(dark)} w-auto py-1`}
                          onChange={e => modifier(c, { role: e.target.value },
                            (e.target.value === "admin" ? tx("Passer {nom} en administrateur ? Il devra se reconnecter.", { nom: c.nom }) : tx("Passer {nom} en analyste ? Il devra se reconnecter.", { nom: c.nom })))}>
                          <option value="analyste">{tx("Analyste")}</option><option value="admin">{tx("Administrateur")}</option>
                        </select>
                      ) : (c.role === "admin" ? tx("Administrateur") : tx("Analyste"))}
                    </td>
                    <td className="p-2">
                      <div className="flex flex-wrap gap-1"><Statut c={c} />
                        {c.double_auth && <span className={`${BADGE} bg-foret-500/15 text-foret-500`} title={tx("Double authentification active")}>{tx("2FA")}</span>}</div>
                    </td>
                    <td className={`p-2 ${texteDiscret(dark)}`}>{c.derniere_connexion ? formaterDate(c.derniere_connexion) : tx("Jamais")}</td>
                    {gestion && (
                      <td className="p-2">
                        <div className="flex justify-end gap-1.5">
                          {c.actif && (
                            <button onClick={() => reinitialiser(c)} disabled={action.chargement} title={tx("Nouveau mot de passe provisoire (débloque aussi le compte)")}
                              className={`${boutonSecondaire(dark)} flex items-center gap-1`}>
                              {c.verrouille ? <Lock size={13} /> : <RotateCcw size={13} />}{" "}{tx("Réinitialiser")}
                            </button>
                          )}
                          {c.verrouille && (
                            <button onClick={() => action.appeler("post", `/admin/utilisateurs/${encodeURIComponent(c.nom)}/debloquer`).then(r => r && charger())}
                              disabled={action.chargement} title={tx("Lever la protection et effacer les blocages d'adresses")}
                              className={`${boutonSecondaire(dark)} flex items-center gap-1`}><Lock size={13} />{" "}{tx("Débloquer")}</button>
                          )}
                          {c.double_auth && !moi && (
                            <button onClick={() => window.confirm(tx("Réinitialiser la double authentification de {nom} (téléphone perdu) ? Il devra la réactiver à sa prochaine connexion.", { nom: c.nom }))
                              && action.appeler("post", `/admin/utilisateurs/${encodeURIComponent(c.nom)}/double-auth/reinitialiser`).then(r => r && charger())}
                              disabled={action.chargement} className={`${boutonSecondaire(dark)} flex items-center gap-1`}>
                              <Smartphone size={13} />{" "}{tx("Réinit. 2FA")}</button>
                          )}
                          {!moi && (c.actif ? (
                            <button onClick={() => modifier(c, { actif: false }, tx("Désactiver {nom} ? Il est déconnecté immédiatement ; son historique est conservé.", { nom: c.nom }))}
                              disabled={action.chargement} className={`${boutonSecondaire(dark)} flex items-center gap-1 text-red-500`}>
                              <UserX size={13} />{" "}{tx("Désactiver")}
                            </button>
                          ) : (
                            <button onClick={() => modifier(c, { actif: true })} disabled={action.chargement}
                              className={`${boutonSecondaire(dark)} flex items-center gap-1`}>
                              <UserCheck size={13} />{" "}{tx("Réactiver")}
                            </button>
                          ))}
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className={`${texteDiscret(dark)} mt-3`}>
          {tx("Aucun compte n'est supprimé : un compte désactivé garde son historique dans l'audit. Après 5 mots de passe faux, seule l'adresse de l'essayeur est bloquée (pas le compte).")}
        </p>
      </div>
    </div>
  );
}
