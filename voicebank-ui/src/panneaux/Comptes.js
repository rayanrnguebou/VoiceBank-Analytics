// Comptes : changement de mot de passe (tous) et gestion des comptes (administrateur).
// Pas d'inscription libre : c'est l'administrateur qui crée les comptes, avec un mot de passe
// provisoire (affiché une seule fois, valable 72 h) que la personne change à sa première connexion.
import { useState, useEffect, useCallback } from "react";
import {
  KeyRound, UserPlus, Copy, Check, RotateCcw, Lock, ShieldCheck, UserX, UserCheck, X, Circle, CircleCheck,
} from "lucide-react";
import { useAPI } from "../useAPI";
import { appliquerJeton } from "../api";
import { Logo } from "./BarreLaterale";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";

// Même règles que l'API (app/securite.py) : affichées en direct pour guider la saisie.
export function reglesMotDePasse(mdp, nom) {
  const familles = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(r => r.test(mdp)).length;
  return [
    { ok: mdp.length >= 12, texte: "Au moins 12 caractères" },
    { ok: familles >= 3, texte: "Trois types parmi : minuscules, majuscules, chiffres, symboles" },
    { ok: !!mdp && !mdp.toLowerCase().includes((nom || "").toLowerCase()), texte: "Ne contient pas l'identifiant" },
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
    if (nouveau !== confirmation) { setErreur("Les deux saisies ne correspondent pas"); return; }
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
        <span className={lib}>{force ? "Mot de passe provisoire" : "Mot de passe actuel"}</span>
        <input type="password" value={actuel} onChange={e => setActuel(e.target.value)} autoComplete="current-password"
          required maxLength={128} className={style} />
      </label>
      <label className="block">
        <span className={lib}>Nouveau mot de passe</span>
        <input type="password" value={nouveau} onChange={e => setNouveau(e.target.value)} autoComplete="new-password"
          required maxLength={72} className={style} />
      </label>
      <ul className="space-y-1" aria-label="Règles du mot de passe">
        {regles.map(r => (
          <li key={r.texte} className={`flex items-center gap-1.5 text-xs ${r.ok ? "text-emerald-500" : force || dark ? "text-gray-400" : "text-gray-500"}`}>
            {r.ok ? <CircleCheck size={13} /> : <Circle size={13} />} {r.texte}
          </li>
        ))}
      </ul>
      <label className="block">
        <span className={lib}>Confirme le nouveau mot de passe</span>
        <input type="password" value={confirmation} onChange={e => setConfirmation(e.target.value)} autoComplete="new-password"
          required maxLength={72} className={style} />
      </label>
      {confirmation && nouveau !== confirmation && <p className="text-xs text-amber-500">Les deux saisies ne correspondent pas</p>}
      {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
      <div className="flex gap-2 pt-1">
        <button type="submit" disabled={chargement || !valide}
          className={force ? "flex-1 flex items-center justify-center gap-2 py-3 bg-foret-600 hover:bg-foret-700 text-white font-semibold rounded-xl disabled:opacity-50" : boutonPrincipal}>
          <KeyRound size={15} className={force ? "" : "inline -mt-0.5 mr-1"} /> {chargement ? "Enregistrement…" : "Enregistrer"}
        </button>
        <button type="button" onClick={onAnnuler}
          className={force ? "px-4 py-3 rounded-xl text-sm text-gray-300 hover:bg-gray-800" : boutonSecondaire(dark)}>
          {force ? "Se déconnecter" : "Annuler"}
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
            <h1 className="text-white font-bold">Bienvenue, {session.utilisateur}</h1>
            <p className="text-gray-400 text-xs">Première connexion</p>
          </div>
        </div>
        <p className="text-sm text-gray-300 mb-5">
          Ton mot de passe est provisoire. Choisis-en un personnel : toi seul le connaîtras, même l'administrateur ne pourra pas le voir.
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
        className={`w-full max-w-md ${carte(dark)}`}>
        <div className="flex items-center justify-between mb-4">
          <h2 id="titre-mdp" className={`${titre(dark)} flex items-center gap-2`}><KeyRound size={18} /> Changer mon mot de passe</h2>
          <button onClick={onFermer} aria-label="Fermer" className={boutonSecondaire(dark)}><X size={14} /></button>
        </div>
        {fait ? (
          <div className="space-y-3">
            <p className="text-sm text-emerald-500 flex items-center gap-2"><ShieldCheck size={16} /> Mot de passe changé.</p>
            <p className={texteDiscret(dark)}>Tes autres sessions ouvertes (autres onglets ou appareils) ont été déconnectées.</p>
            <button onClick={onFermer} className={boutonPrincipal}>Fermer</button>
          </div>
        ) : (
          <FormulaireMotDePasse dark={dark} session={session} onAnnuler={onFermer}
            onTermine={s => { setFait(true); onTermine(s); }} />
        )}
      </div>
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
        Mot de passe provisoire de <span className="font-mono">{info.nom}</span>
      </p>
      <div className="flex items-center gap-2 mb-2">
        <code className={`flex-1 px-3 py-2 rounded-lg font-mono text-base tracking-wide select-all ${dark ? "bg-gray-900 text-laiton-300" : "bg-white text-foret-800"}`}>
          {info.mot_de_passe_provisoire}
        </code>
        <button onClick={copier} className={boutonSecondaire(dark)} aria-label="Copier le mot de passe">
          {copie ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
        </button>
      </div>
      <p className={texteDiscret(dark)}>
        Affiché une seule fois et valable {info.valable_heures} h. Transmets-le par un autre canal que l'identifiant
        (de vive voix, par téléphone…). La personne devra le changer à sa première connexion.
      </p>
      <button onClick={onFermer} className={`mt-3 ${boutonSecondaire(dark)}`}>C'est noté, masquer</button>
    </div>
  );
}

const BADGE = "text-[11px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap";

function Statut({ c }) {
  if (!c.actif) return <span className={`${BADGE} bg-gray-500/15 text-gray-500`}>Désactivé</span>;
  if (c.verrouille) return <span className={`${BADGE} bg-red-500/15 text-red-500`}>Bloqué 15 min</span>;
  if (c.provisoire_expire) return <span className={`${BADGE} bg-amber-500/15 text-amber-600`}>Mot de passe provisoire expiré</span>;
  if (c.doit_changer_mdp) return <span className={`${BADGE} bg-amber-500/15 text-amber-600`}>Première connexion en attente</span>;
  return <span className={`${BADGE} bg-emerald-500/15 text-emerald-600`}>Actif</span>;
}

export function PanelComptes({ dark, session }) {
  const liste = useAPI();
  const action = useAPI();
  const [donnees, setDonnees] = useState(null);
  const [nom, setNom] = useState("");
  const [role, setRole] = useState("analyste");
  const [provisoire, setProvisoire] = useState(null);

  const charger = useCallback(() => {
    liste.appeler("get", "/admin/utilisateurs").then(r => r && setDonnees(r));
  }, [liste.appeler]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  const creer = async (e) => {
    e.preventDefault();
    const res = await action.appeler("post", "/admin/utilisateurs", { nom: nom.trim().toLowerCase(), role });
    if (res) { setProvisoire(res); setNom(""); setRole("analyste"); charger(); }
  };
  const reinitialiser = async (c) => {
    if (!window.confirm(`Générer un nouveau mot de passe provisoire pour ${c.nom} ? Ses sessions en cours seront fermées.`)) return;
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
          Démonstration : voici comment l'administrateur gère les comptes de son organisation (création avec mot de passe
          provisoire, blocage, désactivation). Les noms sont anonymisés et les actions désactivées.
        </div>
      )}
      {donnees && !donnees.gestion_comptes && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-600 text-sm">
          Les comptes sont encore lus dans la configuration (VOICEBANK_USERS). Mets la base à jour avec
          <code className="mx-1">docker compose exec postgres sh /voicebank_securite/migrer.sh</code>
          puis redémarre l'API pour gérer les comptes ici.
        </div>
      )}

      {gestion && (
        <div className={carte(dark)}>
          <h2 className={`${titre(dark)} flex items-center gap-2 mb-1`}><UserPlus size={19} strokeWidth={1.75} /> Créer un compte</h2>
          <p className={`${texteDiscret(dark)} mb-4`}>
            Pas d'inscription libre : seuls les comptes créés ici peuvent se connecter.
            Un analyste consulte les données (noms des clients masqués) ; un administrateur gère aussi les comptes, les corrections et l'audit.
          </p>
          <form onSubmit={creer} className="grid grid-cols-1 sm:grid-cols-[1fr_auto_auto] gap-3 items-end">
            <label>
              <span className={etiquette(dark)}>Identifiant</span>
              <input value={nom} onChange={e => setNom(e.target.value)} required minLength={3} maxLength={32}
                pattern={"[a-zA-Z0-9][a-zA-Z0-9._\\-]{2,31}"} placeholder="ex. jean.mballa" autoComplete="off"
                title="3 à 32 caractères : lettres, chiffres, point, tiret, souligné" className={champ(dark)} />
            </label>
            <label>
              <span className={etiquette(dark)}>Rôle</span>
              <select value={role} onChange={e => setRole(e.target.value)} className={champ(dark)}>
                <option value="analyste">Analyste</option>
                <option value="admin">Administrateur</option>
              </select>
            </label>
            <button type="submit" disabled={action.chargement} className={boutonPrincipal}>Créer</button>
          </form>
          {action.erreur && <p className="text-sm text-red-500 mt-3">{action.erreur}</p>}
          {provisoire && <div className="mt-4"><MotDePasseAffiche dark={dark} info={provisoire} onFermer={() => setProvisoire(null)} /></div>}
        </div>
      )}

      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} mb-3`}>Comptes ({comptes.length})</h2>
        {liste.erreur && <p className="text-sm text-red-500">{liste.erreur}</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className={`text-xs ${dark ? "text-gray-400" : "text-gray-500"}`}>
              <th className="text-left p-2">Identifiant</th><th className="text-left p-2">Rôle</th>
              <th className="text-left p-2">Statut</th><th className="text-left p-2">Dernière connexion</th>
              {gestion && <th className="text-right p-2">Actions</th>}
            </tr></thead>
            <tbody>
              {comptes.map(c => {
                const moi = c.nom === session.utilisateur;
                return (
                  <tr key={c.nom} className={`border-t ${dark ? "border-gray-700" : "border-gray-100"} ${c.actif ? "" : "opacity-60"}`}>
                    <td className="p-2">
                      <span className="font-medium">{c.nom}</span>{moi && <span className={`${texteDiscret(dark)} ml-1`}>(toi)</span>}
                      {c.cree_par && <p className={texteDiscret(dark)}>créé par {c.cree_par}{c.date_creation ? ` le ${formaterDate(c.date_creation)}` : ""}</p>}
                    </td>
                    <td className="p-2">
                      {gestion && !moi && c.actif ? (
                        <select value={c.role} aria-label={`Rôle de ${c.nom}`} className={`${champ(dark)} w-auto py-1`}
                          onChange={e => modifier(c, { role: e.target.value },
                            `Passer ${c.nom} en ${e.target.value === "admin" ? "administrateur" : "analyste"} ? Il devra se reconnecter.`)}>
                          <option value="analyste">Analyste</option><option value="admin">Administrateur</option>
                        </select>
                      ) : (c.role === "admin" ? "Administrateur" : "Analyste")}
                    </td>
                    <td className="p-2"><Statut c={c} /></td>
                    <td className={`p-2 ${texteDiscret(dark)}`}>{c.derniere_connexion ? formaterDate(c.derniere_connexion) : "Jamais"}</td>
                    {gestion && (
                      <td className="p-2">
                        <div className="flex justify-end gap-1.5">
                          {c.actif && (
                            <button onClick={() => reinitialiser(c)} disabled={action.chargement} title="Nouveau mot de passe provisoire (débloque aussi le compte)"
                              className={`${boutonSecondaire(dark)} flex items-center gap-1`}>
                              {c.verrouille ? <Lock size={13} /> : <RotateCcw size={13} />} Réinitialiser
                            </button>
                          )}
                          {!moi && (c.actif ? (
                            <button onClick={() => modifier(c, { actif: false }, `Désactiver ${c.nom} ? Il est déconnecté immédiatement ; son historique est conservé.`)}
                              disabled={action.chargement} className={`${boutonSecondaire(dark)} flex items-center gap-1 text-red-500`}>
                              <UserX size={13} /> Désactiver
                            </button>
                          ) : (
                            <button onClick={() => modifier(c, { actif: true })} disabled={action.chargement}
                              className={`${boutonSecondaire(dark)} flex items-center gap-1`}>
                              <UserCheck size={13} /> Réactiver
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
          Aucun compte n'est supprimé : un compte désactivé garde son historique dans l'audit. Après 5 mots de passe faux, un compte est bloqué 15 minutes.
        </p>
      </div>
    </div>
  );
}
