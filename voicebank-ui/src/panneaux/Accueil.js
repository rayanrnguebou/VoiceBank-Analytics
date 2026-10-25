// Page d'accueil publique : « Vous êtes… » visiteur (essai gratuit) ou organisation (connexion).
import { useState, useEffect } from "react";
import {
  Lock, Sparkles, Building2, UserRound, AudioLines, ShieldAlert, Landmark, RefreshCw, Circle, CircleCheck, ArrowRight,
} from "lucide-react";
import { http, API, connexion, inscriptionEssai, messageErreur, lireMotifDeconnexion } from "../api";
import { Logo } from "./BarreLaterale";
import { reglesMotDePasse } from "./Comptes";

const CHAMP = "w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-white text-sm outline-none focus:border-foret-500";
const LIB = "block text-xs text-gray-400 mb-1";
const BOUTON = "w-full flex items-center justify-center gap-2 py-3 bg-foret-600 hover:bg-foret-700 text-white font-semibold rounded-xl disabled:opacity-50";

function Connexion({ onConnecte }) {
  const [nom, setNom] = useState("");
  const [mdp, setMdp] = useState("");
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  const valider = async (e) => {
    e.preventDefault();
    setErreur(null); setEnvoi(true);
    try { onConnecte(await connexion(nom.trim(), mdp)); }
    catch (err) { setErreur(messageErreur(err)); setMdp(""); }
    finally { setEnvoi(false); }
  };

  return (
    <form onSubmit={valider} className="space-y-4">
      <label className="block">
        <span className={LIB}>Identifiant ou e-mail</span>
        <input value={nom} onChange={e => setNom(e.target.value)} autoComplete="username" required maxLength={64} className={CHAMP} />
      </label>
      <label className="block">
        <span className={LIB}>Mot de passe</span>
        <input type="password" value={mdp} onChange={e => setMdp(e.target.value)} autoComplete="current-password"
          required maxLength={128} className={CHAMP} />
      </label>
      {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
      <button type="submit" disabled={envoi} className={BOUTON}>
        <Lock size={15} /> {envoi ? "Connexion…" : "Se connecter"}
      </button>
      <p className="text-xs text-gray-500">
        Les comptes d'une organisation sont créés par son administrateur. Pas encore cliente ? Commence par l'essai gratuit,
        puis abonne ton organisation.
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

  const valider = async (e) => {
    e.preventDefault();
    setErreur(null); setEnvoi(true);
    try { onConnecte(await inscriptionEssai({ ...f, email: f.email.trim(), accepte_conditions: accepte })); }
    catch (err) { setErreur(messageErreur(err)); }
    finally { setEnvoi(false); }
  };

  return (
    <form onSubmit={valider} className="space-y-3">
      <label className="block">
        <span className={LIB}>Nom complet</span>
        <input value={f.nom_complet} onChange={maj("nom_complet")} required minLength={2} maxLength={120} autoComplete="name" className={CHAMP} />
      </label>
      <label className="block">
        <span className={LIB}>E-mail (ce sera ton identifiant)</span>
        <input type="email" value={f.email} onChange={maj("email")} required maxLength={64} autoComplete="email" className={CHAMP} />
      </label>
      <label className="block">
        <span className={LIB}>Tu es…</span>
        <select value={f.profil} onChange={maj("profil")} className={CHAMP}>
          <option value="professionnel">Professionnel de la banque / finance</option>
          <option value="entreprise">Représentant d'une entreprise</option>
          <option value="recruteur">Recruteur</option>
          <option value="etudiant">Étudiant</option>
          <option value="autre">Autre</option>
        </select>
      </label>
      <label className="block">
        <span className={LIB}>Mot de passe</span>
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
        <span>J'accepte que mes nom et e-mail soient conservés pour gérer mon compte. Les données affichées pendant l'essai
          sont fictives ; je ne peux rien modifier.</span>
      </label>
      {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
      <button type="submit" disabled={envoi || !accepte || !regles.every(r => r.ok)} className={BOUTON}>
        <Sparkles size={15} /> {envoi ? "Création…" : `Démarrer l'essai gratuit${formules ? ` (${formules.essai_jours} jours)` : ""}`}
      </button>
    </form>
  );
}

export default function EcranAccueil({ onConnecte }) {
  const [motif] = useState(() => lireMotifDeconnexion());
  const [profil, setProfil] = useState(() => (motif || new URLSearchParams(window.location.search).get("paiement")) ? "organisation" : null);
  const [serveur, setServeur] = useState("verification");
  const [formules, setFormules] = useState(null);

  // Sur l'offre gratuite de Render, l'API s'endort : on la réveille dès l'arrivée sur la page.
  useEffect(() => {
    let fini = false;
    const lent = setTimeout(() => !fini && setServeur("reveil"), 2500);
    http.get("/health", { timeout: 90000 })
      .then(() => { setServeur("pret"); return http.get("/abonnement/formules"); })
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
            <p className="font-semibold">VoiceBank Analytics</p>
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold leading-tight">
            Interroge tes données bancaires <span className="text-laiton-300">à la voix</span>.
          </h1>
          <p className="text-foret-100/70 mt-4 max-w-md">
            Pose une question en français, obtiens la réponse chiffrée, le graphique et une analyse parlée : fraude,
            crédit, clients, en quelques secondes.
          </p>
          <ul className="mt-6 space-y-3 text-sm text-foret-100/80">
            <li className="flex items-center gap-3"><AudioLines size={18} className="text-laiton-300" /> Assistant vocal et mode conversation</li>
            <li className="flex items-center gap-3"><ShieldAlert size={18} className="text-laiton-300" /> Détection de fraude par IA (Isolation Forest + XGBoost)</li>
            <li className="flex items-center gap-3"><Landmark size={18} className="text-laiton-300" /> Score de crédit expliqué, facteur par facteur</li>
          </ul>
          {prixMin && (
            <p className="mt-6 text-sm text-foret-100/60">
              Essai gratuit {formules.essai_jours} jours, puis à partir de{" "}
              <strong className="text-white">{prixMin.prix.toLocaleString("fr-FR")} FCFA / {prixMin.libelle.toLowerCase()}</strong>
              {" "}— MTN MoMo, Orange Money ou carte.
            </p>
          )}
        </section>

        <section className="bg-gray-900 border border-foret-800 rounded-2xl p-6 sm:p-8 shadow-2xl">
          <h2 className="font-semibold mb-3">Tu es…</h2>
          <div className="grid grid-cols-2 gap-3 mb-6">
            {choix("visiteur", UserRound, "Visiteur", "Je découvre l'outil : essai gratuit, sans engagement")}
            {choix("organisation", Building2, "Organisation", "J'ai un compte, ou mon entreprise est cliente")}
          </div>
          {motif && <p className="text-sm text-amber-400 mb-4">{motif}</p>}
          {serveur === "reveil" && (
            <p className="flex items-center gap-2 text-xs text-laiton-300 mb-4" role="status">
              <RefreshCw size={12} className="animate-spin" /> Démarrage du serveur… jusqu'à une minute après une période sans visite.
            </p>
          )}
          {serveur === "injoignable" && (
            <p className="text-xs text-red-400 mb-4" role="status">Serveur injoignable ({API}). Réessaie dans un instant.</p>
          )}
          {profil === "visiteur" && <Essai onConnecte={onConnecte} formules={formules} />}
          {profil === "organisation" && <Connexion onConnecte={onConnecte} />}
          {!profil && (
            <p className="text-sm text-gray-400 flex items-center gap-2">
              <ArrowRight size={14} /> Choisis ton profil pour continuer.
            </p>
          )}
          {profil === "visiteur" && (
            <button type="button" onClick={() => setProfil("organisation")} className="mt-4 text-xs text-foret-300 hover:underline">
              Déjà un compte ? Se connecter
            </button>
          )}
        </section>
      </div>
    </div>
  );
}
