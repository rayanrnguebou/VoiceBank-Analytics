// Approbation sur le téléphone (double authentification par notification, avec choix du nombre).
// - AttenteApprobation : l'ordinateur affiche le nombre et attend la réponse du téléphone.
// - EcranApprobation : le téléphone (ouvert depuis la notification) montre la demande et trois nombres.
// - SectionTelephones : enregistrer ce téléphone / retirer un téléphone (Sécurité de mon compte).
import { useState, useEffect, useCallback, useRef } from "react";
import { BellRing, Smartphone, ShieldCheck, ShieldX, Trash2 } from "lucide-react";
import { http, appliquerJeton, messageErreur } from "../api";
import { Logo } from "./BarreLaterale";
import { champ, etiquette, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";
import { tx } from "../i18n";

const CLE_SECRET = "voicebank_approbation_secret";
export const lireSecret = () => { try { return localStorage.getItem(CLE_SECRET); } catch (e) { return null; } };
const ecrireSecret = s => { try { s ? localStorage.setItem(CLE_SECRET, s) : localStorage.removeItem(CLE_SECRET); } catch (e) { /* rien */ } };

// ── Ordinateur : « Choisis 47 sur ton téléphone » ─────────────────────
export function AttenteApprobation({ etape, onConnecte, onCode }) {
  const [demande, setDemande] = useState(null);
  const [statut, setStatut] = useState("envoi");      // envoi | attente | refusee | expiree | erreur
  const [message, setMessage] = useState(null);
  const [ici, setIci] = useState(false);              // cet appareil est lui-même un téléphone d'approbation du compte
  const minuteur = useRef(null);

  const demander = useCallback(async () => {
    setStatut("envoi"); setMessage(null); setIci(false);
    try {
      const { data } = await http.post("/auth/2fa/approbation/demander", { jeton_2fa: etape.jeton }, { silencieux: true });
      setDemande(data); setStatut("attente");
      // Connexion depuis le téléphone enregistré lui-même : pas besoin d'aller dans la notification
      const secret = lireSecret();
      if (secret) {
        http.post(`/approbation/${encodeURIComponent(data.id)}`, { secret }, { silencieux: true })
          .then(r => setIci(r.data?.statut === "attente")).catch(() => {});
      }
    } catch (e) { setStatut("erreur"); setMessage(messageErreur(e)); }
  }, [etape.jeton]);
  const approuverIci = async () => {
    try {
      await http.post(`/approbation/${encodeURIComponent(demande.id)}/repondre`, { secret: lireSecret(), nombre: demande.nombre },
        { silencieux: true });
      setIci(false);
    } catch (e) { setMessage(messageErreur(e)); }
  };
  useEffect(() => { demander(); }, [demander]);

  useEffect(() => {
    if (statut !== "attente" || !demande) return undefined;
    const suivre = async () => {
      try {
        const { data } = await http.post("/auth/2fa/approbation/etat", { jeton_2fa: etape.jeton, id_demande: demande.id },
          { silencieux: true });
        if (data.access_token) { clearInterval(minuteur.current); onConnecte(appliquerJeton(data)); return; }
        if (data.statut === "expiree") { setStatut("expiree"); }
        else if (data.statut === "mauvais_nombre" || data.statut === "pas_moi" || data.statut === "refusee") {
          setStatut("refusee");
          setMessage(data.statut === "mauvais_nombre" ? tx("Mauvais nombre choisi sur le téléphone : connexion refusée.")
            : tx("Connexion refusée depuis le téléphone."));
        }
      } catch (e) { setStatut("erreur"); setMessage(messageErreur(e)); }
    };
    minuteur.current = setInterval(suivre, 2000);
    return () => clearInterval(minuteur.current);
  }, [statut, demande, etape.jeton, onConnecte]);

  return (
    <div className="space-y-4 text-center">
      <p className="text-sm text-gray-300 flex items-center justify-center gap-2">
        <BellRing size={16} className="text-laiton-300" />{" "}{tx("Approuve la connexion sur ton téléphone")}
      </p>
      {statut === "attente" && demande && (
        <>
          <p className="text-xs text-gray-400">{tx("Touche la notification VoiceBank sur ton téléphone, puis choisis ce nombre :")}</p>
          <p className="text-6xl font-bold text-white tracking-wider" aria-live="polite" aria-label={tx("Nombre à choisir : {n}", { n: demande.nombre })}>
            {demande.nombre}</p>
          <p className="text-xs text-gray-500">{tx("En attente de ton téléphone… (2 minutes au plus)")}</p>
          {ici && (
            <button type="button" onClick={approuverIci}
              className="w-full py-3 bg-foret-600 hover:bg-foret-700 text-white font-semibold rounded-xl">
              {tx("C'est moi : approuver sur cet appareil")}</button>
          )}
        </>
      )}
      {statut === "envoi" && <p className="text-xs text-gray-400">{tx("Envoi de la notification…")}</p>}
      {(statut === "refusee" || statut === "expiree" || statut === "erreur") && (
        <>
          <p role="alert" className="text-sm text-red-400">{statut === "expiree" ? tx("La demande a expiré.") : message}</p>
          <button type="button" onClick={demander} className="w-full py-3 bg-foret-600 hover:bg-foret-700 text-white font-semibold rounded-xl">
            {tx("Renvoyer la notification")}</button>
        </>
      )}
      <button type="button" onClick={onCode} className="text-xs text-foret-300 hover:underline">
        {tx("Utiliser plutôt le code à 6 chiffres")}</button>
    </div>
  );
}

// ── Téléphone : écran ouvert depuis la notification ───────────────────
export function EcranApprobation({ idDemande, onFermer, superpose = false }) {
  const secret = lireSecret();
  const [d, setD] = useState(null);
  const [erreur, setErreur] = useState(secret ? null : tx("Ce téléphone n'est pas enregistré pour approuver les connexions."));
  const [resultat, setResultat] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    if (!secret) return;
    http.post(`/approbation/${encodeURIComponent(idDemande)}`, { secret }, { silencieux: true })
      .then(r => setD(r.data)).catch(e => setErreur(messageErreur(e)));
  }, [idDemande, secret]);

  const repondre = async corps => {
    setEnvoi(true);
    try {
      const { data } = await http.post(`/approbation/${encodeURIComponent(idDemande)}/repondre`, { secret, ...corps }, { silencieux: true });
      setResultat(corps.refuser ? "pas_moi" : data.statut);
    } catch (e) { setErreur(messageErreur(e)); } finally { setEnvoi(false); }
  };

  return (
    <div className={`${superpose ? "fixed inset-0 z-[60] overflow-y-auto" : "min-h-screen"} bg-[#0B1F17] flex items-center justify-center px-4 py-6 text-white`}
      role={superpose ? "dialog" : undefined} aria-modal={superpose || undefined} aria-label={tx("Connexion demandée")}>
      <div className="w-full max-w-sm bg-gray-900/60 border border-white/10 rounded-2xl p-6 space-y-5 text-center">
        <div className="flex items-center justify-center gap-2"><Logo /><span className="font-bold">VoiceBank</span></div>
        <h1 className="text-lg font-bold">{tx("Connexion demandée")}</h1>
        {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
        {resultat === "approuvee" && <p role="status" className="text-emerald-400 flex items-center justify-center gap-2"><ShieldCheck size={18} />{" "}{tx("Connexion approuvée. Tu peux fermer cette page.")}</p>}
        {resultat === "refusee" && <p role="alert" className="text-red-400">{tx("Ce n'était pas le bon nombre : la connexion est refusée. Recommence depuis l'ordinateur.")}</p>}
        {resultat === "pas_moi" && <p role="alert" className="text-red-400 flex items-center justify-center gap-2"><ShieldX size={18} />{" "}{tx("Connexion bloquée. Change ton mot de passe : quelqu'un le connaît.")}</p>}
        {d && !resultat && (d.statut !== "attente" ? (
          <p className="text-sm text-gray-300">{d.statut === "expiree" ? tx("Cette demande a expiré.") : tx("Cette demande a déjà reçu une réponse.")}</p>
        ) : (
          <>
            <dl className="text-sm text-left bg-white/5 rounded-xl p-3 space-y-1">
              <div className="flex justify-between gap-3"><dt className="text-gray-400">{tx("Compte")}</dt><dd className="truncate">{d.compte}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-gray-400">{tx("Appareil")}</dt><dd>{d.navigateur}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-gray-400">{tx("Adresse IP")}</dt><dd>{d.adresse_ip || "—"}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-gray-400">{tx("Heure")}</dt><dd>{formaterDate(d.date)}</dd></div>
            </dl>
            <p className="text-sm text-gray-300">{tx("Touche le nombre affiché sur l'ordinateur :")}</p>
            <div className="grid grid-cols-3 gap-3">
              {d.choix.map(n => (
                <button key={n} type="button" disabled={envoi} onClick={() => repondre({ nombre: n })}
                  className="py-5 text-3xl font-bold rounded-xl bg-foret-600 hover:bg-foret-700 disabled:opacity-50">{n}</button>
              ))}
            </div>
            <button type="button" disabled={envoi} onClick={() => repondre({ refuser: true })}
              className="w-full py-3 rounded-xl border border-red-500/60 text-red-300 hover:bg-red-500/10">{tx("Ce n'était pas moi")}</button>
          </>
        ))}
        {resultat === "approuvee" && !superpose && <p className="text-xs text-gray-400">{tx("Retourne sur l'appareil où tu te connectes : il s'ouvre tout seul.")}</p>}
        <button type="button" onClick={onFermer}
          className={resultat ? "w-full py-3 rounded-xl bg-white/10 hover:bg-white/15 text-sm" : "text-xs text-gray-400 hover:underline"}>
          {superpose ? tx("Fermer") : resultat ? tx("Terminé") : tx("Ouvrir VoiceBank")}</button>
      </div>
    </div>
  );
}

// ── Réglages : téléphones qui approuvent les connexions ──────────────
function nomAppareil() {
  const ua = navigator.userAgent;
  const os = /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Android/.test(ua) ? "Android"
    : /Windows/.test(ua) ? "Windows" : /Mac OS X/.test(ua) ? "Mac" : "Linux";
  const nav = /Edg\//.test(ua) ? "Edge" : /SamsungBrowser/.test(ua) ? "Samsung Internet" : /Firefox\//.test(ua) ? "Firefox"
    : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : tx("Navigateur");
  return `${nav} · ${os}`;
}

const base64UrlVersOctets = b64 => {
  const brut = atob((b64 + "=".repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(brut, c => c.charCodeAt(0));
};

export function notificationsPossibles() {
  return typeof window !== "undefined" && !!navigator.serviceWorker?.register && "PushManager" in window && "Notification" in window;
}
const iosHorsEcranAccueil = () => /iPhone|iPad/.test(navigator.userAgent) && !window.matchMedia?.("(display-mode: standalone)").matches
  && !navigator.standalone;

export function SectionTelephones({ dark }) {
  const [liste, setListe] = useState(null);
  const [ajout, setAjout] = useState(false);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const charger = useCallback(() => { http.get("/auth/approbation/telephones").then(r => setListe(r.data.data)).catch(() => {}); }, []);
  useEffect(charger, [charger]);
  if (!liste) return null;
  const ceTelephone = !!lireSecret();

  const enregistrer = async e => {
    e.preventDefault();
    setErreur(null); setEnvoi(true);
    try {
      if (!notificationsPossibles()) throw new Error(tx("Ce navigateur ne sait pas recevoir de notifications."));
      if (iosHorsEcranAccueil()) throw new Error(tx("Sur iPhone : ajoute d'abord VoiceBank à l'écran d'accueil (Partager → Sur l'écran d'accueil), puis ouvre-le depuis l'icône."));
      const permission = await Notification.requestPermission();
      if (permission !== "granted") throw new Error(tx("Notifications refusées : autorise-les pour VoiceBank dans les réglages du téléphone."));
      const { data } = await http.get("/auth/approbation/cle");
      const enregistrement = await navigator.serviceWorker.register("/sw-approbation.js");
      await navigator.serviceWorker.ready;
      const ancien = await enregistrement.pushManager.getSubscription();
      if (ancien) await ancien.unsubscribe();
      const abonnement = await enregistrement.pushManager.subscribe({ userVisibleOnly: true,
        applicationServerKey: base64UrlVersOctets(data.cle_publique) });
      const r = await http.post("/auth/approbation/telephones", { code: code.trim(), nom: nomAppareil(), abonnement: abonnement.toJSON() });
      ecrireSecret(r.data.secret);
      setAjout(false); setCode("");
      setMessage(tx("Ce téléphone approuvera désormais tes connexions."));
      charger();
    } catch (err) {
      setErreur(err?.response ? messageErreur(err) : err.message);
    } finally { setEnvoi(false); }
  };
  const retirer = async t => {
    try { await http.post(`/auth/approbation/telephones/${t.id}/retirer`); charger(); } catch (e) { setErreur(messageErreur(e)); }
  };

  return (
    <div className={`mt-4 pt-4 border-t ${dark ? "border-gray-700" : "border-gray-200"}`}>
      <p className={`text-sm font-medium flex items-center gap-2 ${dark ? "text-gray-200" : "text-gray-800"}`}>
        <BellRing size={14} />{" "}{tx("Approuver depuis mon téléphone")}
      </p>
      <p className={texteDiscret(dark)}>
        {tx("Au lieu de taper le code, tu reçois une notification et tu touches le nombre affiché sur l'ordinateur. Le code à 6 chiffres reste toujours possible.")}
      </p>
      {liste.length > 0 && (
        <ul className="mt-2 space-y-1">
          {liste.map(t => (
            <li key={t.id} className={`flex items-center justify-between gap-2 text-sm px-3 py-2 rounded-lg ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
              <span><Smartphone size={13} className="inline mr-1" />{t.nom}
                <span className={`block ${texteDiscret(dark)}`}>{tx("ajouté le {date}", { date: formaterDate(t.date_ajout) })}</span></span>
              <button type="button" onClick={() => retirer(t)} aria-label={tx("Retirer {nom}", { nom: t.nom })}
                className={`${boutonSecondaire(dark)} flex items-center gap-1`}><Trash2 size={12} />{" "}{tx("Retirer")}</button>
            </li>
          ))}
        </ul>
      )}
      {!ajout ? (
        <button type="button" onClick={() => { setAjout(true); setMessage(null); }} className={`${boutonSecondaire(dark)} mt-2`}>
          {ceTelephone ? tx("Réenregistrer ce téléphone") : tx("Utiliser cet appareil pour approuver")}</button>
      ) : (
        <form onSubmit={enregistrer} className="mt-2 space-y-2">
          <p className={texteDiscret(dark)}>{tx("Fais-le sur ton téléphone (VoiceBank ouvert depuis l'icône de l'écran d'accueil sur iPhone).")}</p>
          <label className="block"><span className={etiquette(dark)}>{tx("Code de l'application")}</span>
            <input value={code} onChange={e => setCode(e.target.value)} required inputMode="numeric" autoComplete="one-time-code"
              maxLength={12} className={champ(dark)} /></label>
          <div className="flex gap-2">
            <button type="submit" disabled={envoi} className={boutonPrincipal}>{envoi ? tx("Activation…") : tx("Activer les notifications")}</button>
            <button type="button" onClick={() => { setAjout(false); setErreur(null); }} className={boutonSecondaire(dark)}>{tx("Annuler")}</button>
          </div>
        </form>
      )}
      {message && <p role="status" className="text-sm text-emerald-500 mt-2">{message}</p>}
      {erreur && <p role="alert" className="text-sm text-red-400 mt-2">{erreur}</p>}
    </div>
  );
}
