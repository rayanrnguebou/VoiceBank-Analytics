// Maintenance : page « en maintenance », bandeau d'annonce, bandeau « reconnexion » pendant une mise à jour,
// et réglages pour l'administrateur de la plateforme.
import { useState, useEffect, useCallback, useRef } from "react";
import { Wrench, RefreshCw, CalendarClock, X, Power, Megaphone, WifiOff } from "lucide-react";
import { http } from "./api";
import { Logo } from "./panneaux/BarreLaterale";
import { useAPI } from "./useAPI";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire } from "./ui";
import { LOCALE, tx } from "./i18n";

const heure = v => {
  if (!v) return null;
  const d = new Date(v);
  if (isNaN(d)) return null;
  const memeJour = d.toDateString() === new Date().toDateString();
  return memeJour
    ? tx("aujourd'hui à {heure}", { heure: d.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" }) })
    : d.toLocaleString(LOCALE, { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
};

// État public : maintenance en cours, annonce. Rafraîchi toutes les minutes et dès qu'une requête répond « maintenance ».
export function useMaintenance() {
  const [etat, setEtat] = useState({ active: false, annonce: null, message: null, fin_prevue: null });
  const verifier = useCallback(() => {
    http.get("/maintenance", { timeout: 20000, silencieux: true }).then(r => setEtat(r.data)).catch(() => {});
  }, []);
  useEffect(() => {
    verifier();
    const t = setInterval(verifier, 60000);
    const surMaintenance = e => setEtat(x => ({ ...x, active: true, message: e.detail?.detail || x.message,
                                                 fin_prevue: e.detail?.fin_prevue ?? x.fin_prevue }));
    window.addEventListener("voicebank:maintenance", surMaintenance);
    window.addEventListener("voicebank:maintenance-maj", verifier);       // réglage changé par l'administrateur
    return () => {
      clearInterval(t);
      window.removeEventListener("voicebank:maintenance", surMaintenance);
      window.removeEventListener("voicebank:maintenance-maj", verifier);
    };
  }, [verifier]);
  return { ...etat, verifier };
}

export function EcranMaintenance({ etat, onAccesAdmin }) {
  const [verif, setVerif] = useState(false);
  // Vérifie toutes les 20 s si le service est revenu
  useEffect(() => {
    const t = setInterval(() => etat.verifier(), 20000);
    return () => clearInterval(t);
  }, [etat]);
  const retour = heure(etat.fin_prevue);
  return (
    <div className="min-h-screen bg-foret-950 text-white flex items-center justify-center px-4">
      <div className="w-full max-w-lg text-center" role="alert">
        <div className="flex items-center justify-center gap-3 mb-10"><Logo /><span className="font-semibold">{tx("VoiceBank Analytics")}</span></div>
        <div className="mx-auto w-16 h-16 rounded-2xl bg-laiton-400/15 flex items-center justify-center mb-6">
          <Wrench size={30} className="text-laiton-300" />
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold">{tx("Maintenance en cours")}</h1>
        <p className="text-foret-100/80 mt-4 leading-relaxed">{etat.message}</p>
        {retour && (
          <p className="mt-5 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 text-sm text-foret-100">
            <CalendarClock size={15} className="text-laiton-300" />{" "}{tx("Retour prévu {retour}", { retour })}
          </p>
        )}
        <p className="mt-6 text-xs text-foret-100/50 flex items-center justify-center gap-1.5">
          <RefreshCw size={12} className="animate-spin" />{" "}{tx("Cette page se met à jour toute seule dès que le service revient.")}
        </p>
        <div className="mt-8 flex items-center justify-center gap-4 text-xs">
          <button onClick={() => { setVerif(true); etat.verifier(); setTimeout(() => setVerif(false), 1500); }}
            className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/15">{verif ? tx("Vérification…") : tx("Réessayer maintenant")}</button>
          {onAccesAdmin && <button onClick={onAccesAdmin} className="text-foret-100/50 hover:text-white hover:underline">{tx("Accès administrateur")}</button>}
        </div>
      </div>
    </div>
  );
}

// Bandeau « maintenance prévue » (fermable pour la session)
export function BandeauAnnonce({ annonce, sombre = true }) {
  const cle = annonce ? `voicebank_annonce_${annonce.message}_${annonce.debut}` : null;
  const [ferme, setFerme] = useState(() => { try { return cle && sessionStorage.getItem(cle) === "1"; } catch (e) { return false; } });
  if (!annonce || ferme) return null;
  if (annonce.fin && !isNaN(new Date(annonce.fin)) && new Date(annonce.fin) < new Date()) return null;   // déjà passée
  const quand = annonce.debut ? `${heure(annonce.debut)}${annonce.fin ? ` → ${new Date(annonce.fin).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" })}` : ""}` : null;
  return (
    <div role="status" className={`flex items-start gap-3 px-4 py-3 rounded-xl border text-sm mb-4 ${sombre
      ? "bg-laiton-400/10 border-laiton-400/40 text-foret-50" : "bg-amber-50 border-amber-300 text-amber-900"}`}>
      <Megaphone size={16} className="text-laiton-400 flex-shrink-0 mt-0.5" />
      <p className="flex-1"><strong>{tx("Maintenance prévue")}{quand ? ` ${quand}` : ""}.</strong> {annonce.message}</p>
      <button onClick={() => { setFerme(true); try { sessionStorage.setItem(cle, "1"); } catch (e) { /* rien */ } }}
        aria-label={tx("Masquer l'annonce")} className="opacity-60 hover:opacity-100"><X size={14} /></button>
    </div>
  );
}

// Serveur injoignable (redémarrage, mise à jour sur Render, coupure réseau) : bandeau et reconnexion automatique
export function BandeauReconnexion() {
  const [perdu, setPerdu] = useState(false);
  const minuteur = useRef(null);
  useEffect(() => {
    const surPerte = () => setPerdu(true);
    window.addEventListener("voicebank:injoignable", surPerte);
    return () => window.removeEventListener("voicebank:injoignable", surPerte);
  }, []);
  useEffect(() => {
    if (!perdu) return;
    const essayer = () => http.get("/health", { timeout: 15000, silencieux: true }).then(() => setPerdu(false)).catch(() => {});
    minuteur.current = setInterval(essayer, 8000);
    essayer();
    return () => clearInterval(minuteur.current);
  }, [perdu]);
  if (!perdu) return null;
  return (
    <div role="status" className="fixed top-3 left-1/2 -translate-x-1/2 z-50 max-w-[calc(100%-2rem)] flex items-center gap-3 px-4 py-2.5 rounded-xl
      bg-gray-900/95 border border-laiton-400/40 text-white text-sm shadow-2xl">
      <WifiOff size={16} className="text-laiton-300 flex-shrink-0" />
      <span>{tx("Le serveur ne répond pas : mise à jour ou redémarrage en cours.")}{" "}<span className="text-gray-400">{tx("Reconnexion automatique…")}</span></span>
      <RefreshCw size={14} className="animate-spin text-gray-400 flex-shrink-0" />
    </div>
  );
}

// Calcul long en cours (analyse de risques, rapport…) : on le dit, pour que personne ne croie à une panne
export function IndicateurCalcul() {
  const [n, setN] = useState(0);
  useEffect(() => {
    const surLent = e => setN(e.detail);
    window.addEventListener("voicebank:lent", surLent);
    return () => window.removeEventListener("voicebank:lent", surLent);
  }, []);
  if (!n) return null;
  return (
    <div role="status" aria-live="polite" className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 max-w-[calc(100%-2rem)] flex items-center gap-3 px-4 py-2.5 rounded-xl
      bg-gray-900/95 border border-laiton-400/40 text-white text-sm shadow-2xl">
      <RefreshCw size={14} className="animate-spin text-laiton-300 flex-shrink-0" />
      <span>{tx("Calcul en cours sur le serveur…")}{" "}
        <span className="text-gray-400">{tx("Les analyses peuvent prendre jusqu'à une minute ; les visites suivantes sont immédiates.")}</span></span>
    </div>
  );
}

const versLocal = v => (v ? String(v).slice(0, 16) : "");

// Réglages (administrateur de la plateforme)
export function PanelMaintenance({ dark }) {
  const { appeler, chargement, erreur } = useAPI();
  const [e, setE] = useState(null);
  const [f, setF] = useState(null);
  const [enregistre, setEnregistre] = useState(false);
  const charger = useCallback(() => {
    appeler("get", "/admin/maintenance").then(r => {
      if (!r) return;
      setE(r);
      setF({ active: r.active, message: r.message || "", fin_prevue: versLocal(r.fin_prevue),
             annonce_message: r.annonce?.message || "", annonce_debut: versLocal(r.annonce?.debut), annonce_fin: versLocal(r.annonce?.fin) });
    });
  }, [appeler]);
  useEffect(() => { charger(); }, [charger]);
  const enregistrer = async (corps) => {
    const r = await appeler("post", "/admin/maintenance", {
      ...corps, fin_prevue: corps.fin_prevue || null, annonce_message: corps.annonce_message || null,
      annonce_debut: corps.annonce_debut || null, annonce_fin: corps.annonce_fin || null });
    if (r) {
      setEnregistre(true); setTimeout(() => setEnregistre(false), 2500); charger();
      window.dispatchEvent(new Event("voicebank:maintenance-maj"));
    }
  };
  if (!f) return <p className={texteDiscret(dark)}>{erreur || tx("Chargement…")}</p>;
  const maj = k => ev => setF({ ...f, [k]: ev.target.value });
  return (
    <div className="space-y-4">
      <div className={`${carte(dark)} ${e?.active ? "border-amber-500/60" : ""}`}>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-1">
          <h2 className={`${titre(dark)} flex items-center gap-2`}><Wrench size={19} />{" "}{tx("Mode maintenance")}</h2>
          <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${e?.active ? "bg-amber-500/20 text-amber-500" : "bg-emerald-500/15 text-emerald-500"}`}>
            {e?.active ? tx("Maintenance en cours") : tx("Service ouvert")}
          </span>
        </div>
        <p className={`${texteDiscret(dark)} mb-4`}>
          {tx("Activée, elle affiche à tous les utilisateurs une page « Maintenance en cours » avec ton message et bloque leurs requêtes. Toi, tu restes connecté et tu peux tout utiliser. Les paiements (webhook NotchPay) continuent d'arriver.")}
        </p>
        <label className="block mb-3">
          <span className={etiquette(dark)}>{tx("Message affiché aux utilisateurs")}</span>
          <textarea value={f.message} onChange={maj("message")} maxLength={500} rows={3} className={champ(dark)} />
        </label>
        <label className="block mb-4 max-w-xs">
          <span className={etiquette(dark)}>{tx("Retour prévu (facultatif)")}</span>
          <input type="datetime-local" value={f.fin_prevue} onChange={maj("fin_prevue")} className={champ(dark)} />
        </label>
        <div className="flex flex-wrap gap-2">
          {e?.active ? (
            <button onClick={() => enregistrer({ ...f, active: false })} disabled={chargement} className={`${boutonPrincipal} flex items-center gap-1.5`}>
              <Power size={14} />{" "}{tx("Terminer la maintenance")}
            </button>
          ) : (
            <button onClick={() => window.confirm(tx("Activer la maintenance ? Les utilisateurs connectés verront aussitôt la page de maintenance."))
              && enregistrer({ ...f, active: true })} disabled={chargement}
              className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-semibold rounded-xl disabled:opacity-50 flex items-center gap-1.5">
              <Power size={14} />{" "}{tx("Activer la maintenance")}
            </button>
          )}
          {e?.active && <button onClick={() => enregistrer({ ...f, active: true })} disabled={chargement} className={boutonSecondaire(dark)}>{tx("Mettre à jour le message")}</button>}
        </div>
      </div>

      <div className={carte(dark)}>
        <h2 className={`${titre(dark)} flex items-center gap-2 mb-1`}><Megaphone size={18} />{" "}{tx("Annoncer une maintenance")}</h2>
        <p className={`${texteDiscret(dark)} mb-4`}>{tx("Un bandeau prévient tous les utilisateurs à l'avance (page d'accueil et application). Il disparaît tout seul après l'heure de fin.")}</p>
        <label className="block mb-3">
          <span className={etiquette(dark)}>{tx("Message de l'annonce")}</span>
          <input value={f.annonce_message} onChange={maj("annonce_message")} maxLength={300}
            placeholder={tx("Ex. : le service sera indisponible pendant une heure pour une mise à jour.")} className={champ(dark)} />
        </label>
        <div className="grid sm:grid-cols-2 gap-3 mb-4 max-w-xl">
          <label><span className={etiquette(dark)}>{tx("Début")}</span>
            <input type="datetime-local" value={f.annonce_debut} onChange={maj("annonce_debut")} className={champ(dark)} /></label>
          <label><span className={etiquette(dark)}>{tx("Fin")}</span>
            <input type="datetime-local" value={f.annonce_fin} onChange={maj("annonce_fin")} className={champ(dark)} /></label>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => enregistrer({ ...f, active: !!e?.active })} disabled={chargement || !f.annonce_message.trim()} className={boutonPrincipal}>
            {tx("Publier l'annonce")}</button>
          {e?.annonce && <button onClick={() => enregistrer({ ...f, active: !!e?.active, annonce_message: "" })} disabled={chargement}
            className={boutonSecondaire(dark)}>{tx("Retirer l'annonce")}</button>}
        </div>
        {f.annonce_message.trim() && <div className="mt-4"><p className={`${texteDiscret(dark)} mb-1`}>{tx("Aperçu :")}</p>
          <BandeauAnnonce key={f.annonce_message + f.annonce_debut} annonce={{ message: f.annonce_message, debut: f.annonce_debut, fin: f.annonce_fin }} sombre={dark} /></div>}
      </div>
      {enregistre && <p role="status" className="text-sm text-emerald-500">{tx("Enregistré.")}</p>}
      {erreur && <p role="alert" className="text-sm text-red-500">{erreur}</p>}
    </div>
  );
}
