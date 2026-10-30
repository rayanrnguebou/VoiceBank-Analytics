// Page d'accueil publique : « Vous êtes… » visiteur (essai gratuit) ou organisation (connexion).
import { useState, useEffect } from "react";
import {
  Lock, Sparkles, Building2, UserRound, AudioLines, ShieldAlert, Landmark, RefreshCw, Circle, CircleCheck, ArrowRight,
  Mail, KeyRound, ArrowLeft,
} from "lucide-react";
import AntiRobot, { CLE_SITE } from "../AntiRobot";
import { http, connexion, inscriptionEssai, messageErreur, lireMotifDeconnexion, appliquerJeton, demarrerSSO, terminerSSO } from "../api";
import { Logo } from "./BarreLaterale";
import { reglesMotDePasse } from "./Comptes";
import { Prix } from "./Abonnement";
import { SelecteurDevise } from "../devise";
import { BandeauAnnonce } from "../maintenance";
import { SaisieCodeConnexion } from "./DoubleAuth";
import { PAGE_ETAT } from "../etatService";
import { LANGUE, tx } from "../i18n";
import SelecteurLangue from "../SelecteurLangue";

const CHAMP = "w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-white text-sm outline-none focus:border-foret-500";
const LIB = "block text-xs text-gray-400 mb-1";
const BOUTON = "w-full flex items-center justify-center gap-2 py-3 bg-foret-600 hover:bg-foret-700 text-white font-semibold rounded-xl disabled:opacity-50";

// Mot de passe oublié : 1) identifiant ou e-mail → code à 6 chiffres par e-mail ; 2) code + nouveau mot de passe
function MotDePasseOublie({ identifiantInitial, onRetour }) {
  const [etape, setEtape] = useState("demande");
  const [identifiant, setIdentifiant] = useState(identifiantInitial || "");
  const [code, setCode] = useState("");
  const [nouveau, setNouveau] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [info, setInfo] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const regles = reglesMotDePasse(nouveau, identifiant.split("@")[0]);
  const [captcha, setCaptcha] = useState(null);

  const demander = async (e) => {
    e?.preventDefault();
    setErreur(null); setEnvoi(true);
    try {
      const r = await http.post("/auth/oubli", { identifiant: identifiant.trim(), captcha });
      setInfo(r.data.message); setEtape("code");
    } catch (err) { setErreur(messageErreur(err)); }
    finally { setEnvoi(false); }
  };
  const confirmer = async (e) => {
    e.preventDefault();
    if (nouveau !== confirmation) { setErreur(tx("Les deux saisies ne correspondent pas")); return; }
    setErreur(null); setEnvoi(true);
    try {
      const r = await http.post("/auth/oubli/confirmer", { identifiant: identifiant.trim(), code: code.trim(), nouveau });
      onRetour(r.data.message, identifiant.trim());
    } catch (err) { setErreur(messageErreur(err)); setCode(""); }
    finally { setEnvoi(false); }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm font-semibold flex items-center gap-2"><KeyRound size={15} className="text-laiton-300" />{" "}{tx("Mot de passe oublié")}</p>
      {etape === "demande" ? (
        <form onSubmit={demander} className="space-y-4">
          <p className="text-xs text-gray-400">{tx("Indique ton identifiant ou ton e-mail : tu recevras un code à 6 chiffres, valable 15 minutes.")}</p>
          <label className="block">
            <span className={LIB}>{tx("Identifiant ou e-mail")}</span>
            <input value={identifiant} onChange={e => setIdentifiant(e.target.value)} autoComplete="username" required
              minLength={3} maxLength={64} className={CHAMP} />
          </label>
          <AntiRobot onJeton={setCaptcha} />
          {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
          <button type="submit" disabled={envoi || (CLE_SITE && !captcha)} className={BOUTON}><Mail size={15} /> {envoi ? tx("Envoi…") : tx("Recevoir un code")}</button>
        </form>
      ) : (
        <form onSubmit={confirmer} className="space-y-3">
          <p role="status" className="text-xs text-emerald-400">{info}</p>
          <input type="text" autoComplete="username" value={identifiant} readOnly hidden />
          <label className="block">
            <span className={LIB}>{tx("Code reçu par e-mail")}</span>
            <input value={code} onChange={e => setCode(e.target.value.replace(/[^0-9]/g, "").slice(0, 6))} inputMode="numeric"
              autoComplete="one-time-code" required minLength={6} maxLength={6} placeholder="123456"
              className={`${CHAMP} tracking-[0.4em] font-mono text-center text-lg`} />
          </label>
          <label className="block">
            <span className={LIB}>{tx("Nouveau mot de passe")}</span>
            <input type="password" value={nouveau} onChange={e => setNouveau(e.target.value)} autoComplete="new-password"
              required maxLength={72} className={CHAMP} />
          </label>
          {nouveau && (
            <ul className="space-y-0.5">
              {regles.map(r => (
                <li key={r.texte} className={`flex items-center gap-1.5 text-xs ${r.ok ? "text-emerald-400" : "text-gray-500"}`}>
                  {r.ok ? <CircleCheck size={12} /> : <Circle size={12} />} {r.texte}
                </li>
              ))}
            </ul>
          )}
          <label className="block">
            <span className={LIB}>{tx("Confirme le nouveau mot de passe")}</span>
            <input type="password" value={confirmation} onChange={e => setConfirmation(e.target.value)} autoComplete="new-password"
              required maxLength={72} className={CHAMP} />
          </label>
          {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
          <button type="submit" disabled={envoi || code.length !== 6 || !regles.every(r => r.ok) || nouveau !== confirmation}
            className={BOUTON}><KeyRound size={15} /> {envoi ? tx("Enregistrement…") : tx("Changer le mot de passe")}</button>
          <button type="button" onClick={() => (CLE_SITE ? (setCaptcha(null), setEtape("demande")) : demander())} disabled={envoi} className="text-xs text-foret-300 hover:underline">
            {tx("Pas reçu ? Renvoyer un code")}
          </button>
        </form>
      )}
      <button type="button" onClick={() => onRetour(null)} className="flex items-center gap-1 text-xs text-gray-400 hover:text-white">
        <ArrowLeft size={12} />{" "}{tx("Retour à la connexion")}
      </button>
    </div>
  );
}

// Lien d'invitation reçu par e-mail : la personne choisit son mot de passe puis est connectée
function ActivationInvitation({ jeton, compte, onConnecte, onAnnuler }) {
  const [nouveau, setNouveau] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const regles = reglesMotDePasse(nouveau, compte.split("@")[0]);
  const valider = async e => {
    e.preventDefault();
    if (nouveau !== confirmation) { setErreur(tx("Les deux saisies ne correspondent pas")); return; }
    setErreur(null); setEnvoi(true);
    try {
      const r = await http.post("/auth/invitation", { identifiant: compte, jeton, nouveau });
      window.history.replaceState(null, "", window.location.pathname);
      onConnecte(appliquerJeton(r.data));
    } catch (err) { setErreur(messageErreur(err)); }
    finally { setEnvoi(false); }
  };
  return (
    <form onSubmit={valider} className="space-y-3">
      <p className="text-sm font-semibold flex items-center gap-2"><KeyRound size={15} className="text-laiton-300" />{" "}{tx("Activer ton compte")}</p>
      <p className="text-xs text-gray-400">{tx("Bienvenue ! Choisis ton mot de passe pour")}{" "}<strong className="text-gray-200">{compte}</strong>{tx(". Toi seul le connaîtras.")}</p>
      <input type="text" autoComplete="username" value={compte} readOnly hidden />
      <label className="block">
        <span className={LIB}>{tx("Mot de passe")}</span>
        <input type="password" value={nouveau} onChange={e => setNouveau(e.target.value)} autoComplete="new-password" required maxLength={72} className={CHAMP} />
      </label>
      {nouveau && (
        <ul className="space-y-0.5">
          {regles.map(r => (
            <li key={r.texte} className={`flex items-center gap-1.5 text-xs ${r.ok ? "text-emerald-400" : "text-gray-500"}`}>
              {r.ok ? <CircleCheck size={12} /> : <Circle size={12} />} {r.texte}
            </li>
          ))}
        </ul>
      )}
      <label className="block">
        <span className={LIB}>{tx("Confirme le mot de passe")}</span>
        <input type="password" value={confirmation} onChange={e => setConfirmation(e.target.value)} autoComplete="new-password" required maxLength={72} className={CHAMP} />
      </label>
      {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
      <button type="submit" disabled={envoi || !regles.every(r => r.ok) || nouveau !== confirmation} className={BOUTON}>
        <KeyRound size={15} /> {envoi ? tx("Activation…") : tx("Activer mon compte")}
      </button>
      <button type="button" onClick={onAnnuler} className="flex items-center gap-1 text-xs text-gray-400 hover:text-white">
        <ArrowLeft size={12} />{" "}{tx("J'ai déjà un compte")}
      </button>
    </form>
  );
}

const NOMS_SSO = { google: "Google", microsoft: "Microsoft" };

function LogoSSO({ f }) {
  if (f === "microsoft") {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <rect x="0" y="0" width="7.5" height="7.5" fill="#f25022" /><rect x="8.5" y="0" width="7.5" height="7.5" fill="#7fba00" />
        <rect x="0" y="8.5" width="7.5" height="7.5" fill="#00a4ef" /><rect x="8.5" y="8.5" width="7.5" height="7.5" fill="#ffb900" />
      </svg>
    );
  }
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#4285F4" d="M45.1 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h11.8c-.5 2.8-2.1 5.1-4.4 6.7v5.5h7.1c4.2-3.8 6.6-9.5 6.6-16.2z" />
      <path fill="#34A853" d="M24 46c5.9 0 10.9-2 14.5-5.3l-7.1-5.5c-2 1.3-4.5 2.1-7.4 2.1-5.7 0-10.5-3.8-12.2-9H4.5v5.7C8.1 41.1 15.5 46 24 46z" />
      <path fill="#FBBC05" d="M11.8 28.3c-.4-1.3-.7-2.7-.7-4.3s.3-3 .7-4.3V14H4.5C3 17 2 20.4 2 24s1 7 2.5 10l7.3-5.7z" />
      <path fill="#EA4335" d="M24 10.7c3.2 0 6.1 1.1 8.4 3.3l6.3-6.3C34.9 4.1 29.9 2 24 2 15.5 2 8.1 6.9 4.5 14l7.3 5.7c1.7-5.2 6.5-9 12.2-9z" />
    </svg>
  );
}

function BoutonsSSO({ fournisseurs }) {
  const [envoi, setEnvoi] = useState(null);
  const [erreur, setErreur] = useState(null);
  if (!fournisseurs?.length) return null;
  const aller = async f => {
    setEnvoi(f); setErreur(null);
    try { await demarrerSSO(f); } catch (err) { setErreur(messageErreur(err)); setEnvoi(null); }
  };
  return (
    <div className="space-y-2">
      {fournisseurs.map(f => (
        <button key={f} type="button" onClick={() => aller(f)} disabled={!!envoi}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-white text-gray-900 text-sm font-medium hover:bg-gray-100 disabled:opacity-60">
          <LogoSSO f={f} /> {envoi === f ? tx("Redirection…") : tx("Continuer avec {x}", { x: NOMS_SSO[f] || f })}
        </button>
      ))}
      {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
      <p className="flex items-center gap-3 text-xs text-gray-500 pt-1">
        <span className="h-px flex-1 bg-gray-700" />{" "}{tx("ou avec ton mot de passe")}{" "}<span className="h-px flex-1 bg-gray-700" />
      </p>
    </div>
  );
}

function RetourSSO({ onConnecte, onEchec }) {
  const [erreur, setErreur] = useState(null);
  const [etape, setEtape] = useState(null);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    window.history.replaceState(null, "", "/");
    if (q.get("error") || !q.get("code") || !q.get("state")) {
      setErreur(q.get("error") === "access_denied" ? tx("Connexion annulée.") : tx("Connexion interrompue : recommence."));
      return;
    }
    terminerSSO(q.get("code"), q.get("state")).then(r => (r.etape2fa ? setEtape(r.etape2fa) : onConnecte(r)))
      .catch(err => setErreur(messageErreur(err)));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (etape) return <SaisieCodeConnexion etape={etape} onConnecte={onConnecte} onAnnuler={onEchec} />;
  if (!erreur) {
    return <p role="status" className="flex items-center gap-2 text-sm text-gray-300"><RefreshCw size={14} className="animate-spin" />{" "}{tx("Connexion en cours…")}</p>;
  }
  return (
    <div className="space-y-3">
      <p role="alert" className="text-sm text-red-400">{erreur}</p>
      <button type="button" onClick={onEchec} className="text-xs text-foret-300 hover:underline">{tx("Retour à la connexion")}</button>
    </div>
  );
}

function Connexion({ onConnecte, oubliDisponible, sso, message }) {
  const [oubli, setOubli] = useState(false);
  const [etape, setEtape] = useState(null);
  const [succes, setSucces] = useState(null);
  const [nom, setNom] = useState("");
  const [mdp, setMdp] = useState("");
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  const valider = async (e) => {
    e.preventDefault();
    setErreur(null); setEnvoi(true);
    try {
      const r = await connexion(nom.trim(), mdp);
      if (r.etape2fa) { setEtape(r.etape2fa); setMdp(""); } else onConnecte(r);
    }
    catch (err) { setErreur(messageErreur(err)); setMdp(""); }
    finally { setEnvoi(false); }
  };

  if (etape) return <SaisieCodeConnexion etape={etape} onConnecte={onConnecte} onAnnuler={() => setEtape(null)} />;
  if (oubli) {
    return <MotDePasseOublie identifiantInitial={nom} onRetour={(message, identifiant) => {
      setOubli(false); setSucces(message); if (identifiant) setNom(identifiant); setMdp(""); setErreur(null);
    }} />;
  }
  return (
    <form onSubmit={valider} className="space-y-4">
      {(succes || message) && <p role="status" className="text-sm text-emerald-400">{succes || message}</p>}
      <BoutonsSSO fournisseurs={sso} />
      <label className="block">
        <span className={LIB}>{tx("Identifiant ou e-mail")}</span>
        <input value={nom} onChange={e => setNom(e.target.value)} autoComplete="username" required maxLength={64} className={CHAMP} />
      </label>
      <label className="block">
        <span className={LIB}>{tx("Mot de passe")}</span>
        <input type="password" value={mdp} onChange={e => setMdp(e.target.value)} autoComplete="current-password"
          required maxLength={128} className={CHAMP} />
      </label>
      {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
      <button type="submit" disabled={envoi} className={BOUTON}>
        <Lock size={15} /> {envoi ? tx("Connexion…") : tx("Se connecter")}
      </button>
      {oubliDisponible ? (
        <button type="button" onClick={() => { setOubli(true); setSucces(null); }} className="text-xs text-foret-300 hover:underline">
          {tx("Mot de passe oublié ?")}
        </button>
      ) : (
        <p className="text-xs text-gray-500">{tx("Mot de passe oublié ? Demande à l'administrateur de ton organisation de le réinitialiser.")}</p>
      )}
      <p className="text-xs text-gray-500">
        {tx("Les comptes d'une organisation sont créés par son administrateur. Pas encore cliente ? Commence par l'essai gratuit, puis abonne ton organisation.")}
      </p>
    </form>
  );
}

function Essai({ onConnecte, formules }) {
  const [f, setF] = useState({ nom_complet: "", email: "", mot_de_passe: "", profil: "professionnel", site_web: "" });
  const [accepte, setAccepte] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const regles = reglesMotDePasse(f.mot_de_passe, f.email.split("@")[0]);
  const maj = cle => e => setF({ ...f, [cle]: e.target.value });
  const [captcha, setCaptcha] = useState(null);

  const valider = async (e) => {
    e.preventDefault();
    setErreur(null); setEnvoi(true);
    try { onConnecte(await inscriptionEssai({ ...f, email: f.email.trim(), accepte_conditions: accepte, captcha })); }
    catch (err) { setErreur(messageErreur(err)); }
    finally { setEnvoi(false); }
  };

  return (
    <form onSubmit={valider} className="space-y-3">
      <label className="block">
        <span className={LIB}>{tx("Nom complet")}</span>
        <input value={f.nom_complet} onChange={maj("nom_complet")} required minLength={2} maxLength={120} autoComplete="name" className={CHAMP} />
      </label>
      <label className="block">
        <span className={LIB}>{tx("E-mail (ce sera ton identifiant)")}</span>
        <input type="email" value={f.email} onChange={maj("email")} required maxLength={64} autoComplete="email" className={CHAMP} />
      </label>
      <label className="block">
        <span className={LIB}>{tx("Tu es…")}</span>
        <select value={f.profil} onChange={maj("profil")} className={CHAMP}>
          <option value="professionnel">{tx("Professionnel de la banque / finance")}</option>
          <option value="entreprise">{tx("Représentant d'une entreprise")}</option>
          <option value="recruteur">{tx("Recruteur")}</option>
          <option value="etudiant">{tx("Étudiant")}</option>
          <option value="autre">{tx("Autre")}</option>
        </select>
      </label>
      <label className="block">
        <span className={LIB}>{tx("Mot de passe")}</span>
        <input type="password" value={f.mot_de_passe} onChange={maj("mot_de_passe")} required maxLength={72}
          autoComplete="new-password" className={CHAMP} />
      </label>
      {f.mot_de_passe && (
        <ul className="space-y-0.5">
          {regles.map(r => (
            <li key={r.texte} className={`flex items-center gap-1.5 text-xs ${r.ok ? "text-emerald-400" : "text-gray-500"}`}>
              {r.ok ? <CircleCheck size={12} /> : <Circle size={12} />} {r.texte}
            </li>
          ))}
        </ul>
      )}
      {/* Piège à robots : invisible pour les humains */}
      <input type="text" name="site_web" value={f.site_web} onChange={maj("site_web")} tabIndex={-1} autoComplete="off"
        aria-hidden="true" className="absolute -left-[9999px] w-px h-px opacity-0" />
      <label className="flex items-start gap-2 text-xs text-gray-400">
        <input type="checkbox" checked={accepte} onChange={e => setAccepte(e.target.checked)} required className="mt-0.5" />
        <span>{tx("J'accepte que mes nom et e-mail soient conservés pour gérer mon compte. Les données affichées pendant l'essai sont fictives ; je ne peux rien modifier.")}</span>
      </label>
      <AntiRobot onJeton={setCaptcha} />
      {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
      <button type="submit" disabled={envoi || !accepte || !regles.every(r => r.ok) || (CLE_SITE && !captcha)} className={BOUTON}>
        <Sparkles size={15} /> {envoi ? tx("Création…") : (formules ? tx("Démarrer l'essai gratuit ({n} jours)", { n: formules.essai_jours }) : tx("Démarrer l'essai gratuit"))}
      </button>
    </form>
  );
}

export default function EcranAccueil({ onConnecte, annonce }) {
  const [motif] = useState(() => lireMotifDeconnexion());
  const [profil, setProfil] = useState(() => (motif || window.location.pathname === "/connexion-sso" || new URLSearchParams(window.location.search).get("paiement")) ? "organisation" : null);
  const [serveur, setServeur] = useState("verification");
  const [formules, setFormules] = useState(null);
  const [oubliDisponible, setOubliDisponible] = useState(false);
  const [sso, setSso] = useState([]);
  const [retourSso, setRetourSso] = useState(() => window.location.pathname === "/connexion-sso");
  const [deblocage, setDeblocage] = useState(null);

  // Lien « Autoriser cet appareil » reçu par e-mail (compte protégé après une attaque)
  useEffect(() => {
    const jeton = new URLSearchParams(window.location.search).get("deblocage");
    if (!jeton) return;
    window.history.replaceState(null, "", window.location.pathname);
    setProfil("organisation");
    http.post("/auth/deblocage", { jeton }, { timeout: 90000 })
      .then(r => setDeblocage({ ok: true, texte: r.data.message }))
      .catch(err => setDeblocage({ ok: false, texte: messageErreur(err) }));
  }, []);
  const [invitation, setInvitation] = useState(() => {
    const q = new URLSearchParams(window.location.search);
    return q.get("invitation") && q.get("compte") ? { jeton: q.get("invitation"), compte: q.get("compte") } : null;
  });

  // Sur l'offre gratuite de Render, l'API s'endort : on la réveille dès l'arrivée sur la page.
  useEffect(() => {
    let fini = false;
    const lent = setTimeout(() => !fini && setServeur("reveil"), 2500);
    http.get("/health", { timeout: 90000, silencieux: true })
      .then(() => {
        setServeur("pret");
        http.get("/auth/options").then(r => { setOubliDisponible(!!r.data.oubli_par_email); setSso(r.data.sso || []); }).catch(() => {});
        return http.get("/abonnement/formules");
      })
      .then(r => r && setFormules(r.data))
      .catch(() => setServeur(s => (s === "pret" ? s : "injoignable")))
      .finally(() => { fini = true; clearTimeout(lent); });
    return () => clearTimeout(lent);
  }, []);

  const choix = (id, Icone, titre, texte) => (
    <button type="button" onClick={() => setProfil(id)} aria-pressed={profil === id}
      className={`text-left p-4 rounded-xl border transition-colors ${profil === id
        ? "border-laiton-400 bg-laiton-400/10" : "border-gray-700 hover:border-gray-500 bg-gray-800/50"}`}>
      <Icone size={20} className={profil === id ? "text-laiton-300" : "text-gray-400"} />
      <p className="text-sm font-semibold text-white mt-2">{titre}</p>
      <p className="text-xs text-gray-400 mt-0.5">{texte}</p>
    </button>
  );
  const prixMin = formules?.formules?.[0];

  return (
    <div className="min-h-screen bg-foret-950 text-white flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-5xl grid lg:grid-cols-[1.1fr_1fr] gap-10 items-center">
        <section>
          <div className="flex items-center gap-3 mb-8">
            <Logo />
            <p className="font-semibold">{tx("VoiceBank Analytics")}</p>
            <SelecteurLangue className="ml-auto" />
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold leading-tight">
            {tx("Interroge tes données bancaires")}{" "}<span className="text-laiton-300">{tx("à la voix")}</span>.
          </h1>
          <p className="text-foret-100/70 mt-4 max-w-md">
            {tx("Pose une question en français, obtiens la réponse chiffrée, le graphique et une analyse parlée : fraude, crédit, clients, en quelques secondes.")}
          </p>
          <ul className="mt-6 space-y-3 text-sm text-foret-100/80">
            <li className="flex items-center gap-3"><AudioLines size={18} className="text-laiton-300" />{" "}{tx("Assistant vocal et mode conversation")}</li>
            <li className="flex items-center gap-3"><ShieldAlert size={18} className="text-laiton-300" />{" "}{tx("Détection de fraude par IA (Isolation Forest + XGBoost)")}</li>
            <li className="flex items-center gap-3"><Landmark size={18} className="text-laiton-300" />{" "}{tx("Score de crédit expliqué, facteur par facteur")}</li>
          </ul>
          {prixMin && (
            <p className="mt-6 text-sm text-foret-100/60">
              {tx("Essai gratuit {essai_jours} jours, puis à partir de{x}", { essai_jours: formules.essai_jours, x: " " })}
              <strong className="text-white"><Prix fcfa={prixMin.prix} dark /> / {prixMin.libelle.toLowerCase()}</strong>
              {tx("{x}— MTN MoMo, Orange Money ou carte.{x2}", { x: " ", x2: " " })}
              <SelecteurDevise compact className="ml-1 text-xs px-1.5 py-0.5 rounded bg-gray-800 border border-gray-700 text-gray-200" />
            </p>
          )}
        </section>

        <section className="bg-gray-900 border border-foret-800 rounded-2xl p-6 sm:p-8 shadow-2xl">
          <BandeauAnnonce annonce={annonce} />
          {!invitation && !retourSso && (
            <>
              <h2 className="font-semibold mb-3">{tx("Tu es…")}</h2>
              <div className="grid grid-cols-2 gap-3 mb-6">
                {choix("visiteur", UserRound, tx("Visiteur"), tx("Je découvre l'outil : essai gratuit, sans engagement"))}
                {choix("organisation", Building2, tx("Organisation"), tx("J'ai un compte, ou mon entreprise est cliente"))}
              </div>
            </>
          )}
          {motif && <p className="text-sm text-amber-400 mb-4">{motif}</p>}
          {deblocage && !deblocage.ok && <p role="alert" className="text-sm text-red-400 mb-4">{deblocage.texte}</p>}
          {serveur === "reveil" && (
            <p className="flex items-center gap-2 text-xs text-laiton-300 mb-4" role="status">
              <RefreshCw size={12} className="animate-spin" />{" "}{tx("Démarrage du serveur… jusqu'à une minute après une période sans visite.")}
            </p>
          )}
          {serveur === "injoignable" && (
            <p className="text-xs text-amber-400 mb-4" role="status">
              {tx("Le serveur ne répond pas pour le moment : une mise à jour est sans doute en cours. Réessaie dans une minute.")}
            </p>
          )}
          {retourSso && <RetourSSO onConnecte={onConnecte} onEchec={() => setRetourSso(false)} />}
          {invitation && (
            <ActivationInvitation jeton={invitation.jeton} compte={invitation.compte} onConnecte={onConnecte}
              onAnnuler={() => { setInvitation(null); setProfil("organisation"); window.history.replaceState(null, "", window.location.pathname); }} />
          )}
          {!invitation && profil === "visiteur" && <Essai onConnecte={onConnecte} formules={formules} />}
          {!invitation && !retourSso && profil === "organisation" && <Connexion onConnecte={onConnecte} oubliDisponible={oubliDisponible} sso={sso} message={deblocage?.ok ? deblocage.texte : null} />}
          {!invitation && !profil && (
            <p className="text-sm text-gray-400 flex items-center gap-2">
              <ArrowRight size={14} />{" "}{tx("Choisis ton profil pour continuer.")}
            </p>
          )}
          {!invitation && profil === "visiteur" && (
            <button type="button" onClick={() => setProfil("organisation")} className="mt-4 text-xs text-foret-300 hover:underline">
              {tx("Déjà un compte ? Se connecter")}
            </button>
          )}
          <p className="mt-6 text-[11px] text-gray-500">
            <a href={`/confidentialite/${LANGUE === "en" ? "#en" : ""}`} className="hover:underline">{tx("Politique de confidentialité")}</a>
            {PAGE_ETAT && <>{" · "}<a href={PAGE_ETAT} target="_blank" rel="noopener noreferrer" className="hover:underline">{tx("État du service")}</a></>}
          </p>
        </section>
      </div>
    </div>
  );
}
