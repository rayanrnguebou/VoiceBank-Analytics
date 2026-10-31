// Double authentification : code à 6 chiffres d'une application (Google Authenticator, Microsoft Authenticator…).
import { useState, useEffect, useCallback } from "react";
import { ShieldCheck, Smartphone, Copy, Check, Download, KeyRound, LifeBuoy } from "lucide-react";
import { useAPI } from "../useAPI";
import { appliquerJeton, http, messageErreur } from "../api";
import { Logo } from "./BarreLaterale";
import { champ, etiquette, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";
import { tx } from "../i18n";
import { AttenteApprobation, SectionTelephones } from "./Approbation";

const CHAMP_SOMBRE = "w-full px-4 py-3 rounded-xl bg-gray-700 border border-gray-600 text-white text-sm outline-none focus:border-foret-500";

function CodesSecours({ codes, dark, onTermine }) {
  const [copie, setCopie] = useState(false);
  const [note, setNote] = useState(false);
  const texte = `${tx("Codes de secours VoiceBank Analytics (chacun ne sert qu'une fois)")}\n\n${codes.join("\n")}\n`;
  const copier = () => { navigator.clipboard?.writeText(texte).then(() => setCopie(true)).catch(() => {}); };
  const telecharger = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([texte], { type: "text/plain" }));
    a.download = "voicebank-codes-de-secours.txt";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return (
    <div className="space-y-3">
      <p className="text-sm text-emerald-500 flex items-center gap-2"><ShieldCheck size={16} />{" "}{tx("Double authentification active.")}</p>
      <p className={`text-sm ${dark ? "text-gray-300" : "text-gray-700"}`}>
        {tx("Garde ces")}{" "}<strong>{tx("codes de secours")}</strong>{" "}{tx("en lieu sûr (gestionnaire de mots de passe, papier sous clé) : si tu perds ton téléphone, chacun remplace une fois le code de l'application. Ils ne seront plus affichés.")}
      </p>
      <ul aria-label={tx("Codes de secours")} className={`grid grid-cols-2 gap-2 p-3 rounded-lg font-mono text-sm ${dark ? "bg-gray-800 text-gray-100" : "bg-gray-100 text-gray-900"}`}>
        {codes.map(c => <li key={c}>{c}</li>)}
      </ul>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={copier} className={boutonSecondaire(dark)}>
          {copie ? <Check size={14} className="inline -mt-0.5 mr-1" /> : <Copy size={14} className="inline -mt-0.5 mr-1" />}{copie ? tx("Copiés") : tx("Copier")}
        </button>
        <button type="button" onClick={telecharger} className={boutonSecondaire(dark)}>
          <Download size={14} className="inline -mt-0.5 mr-1" />{tx("Télécharger")}
        </button>
      </div>
      <label className={`flex items-center gap-2 text-sm ${dark ? "text-gray-300" : "text-gray-700"}`}>
        <input type="checkbox" checked={note} onChange={e => setNote(e.target.checked)} />{" "}{tx("J'ai mis mes codes de secours en lieu sûr")}
      </label>
      <button type="button" disabled={!note} onClick={onTermine} className={`${boutonPrincipal} disabled:opacity-50`}>{tx("Terminer")}</button>
    </div>
  );
}

// Activation : QR code à scanner, puis premier code pour vérifier
export function ActivationDoubleAuth({ dark = true, sombre = false, onActive, onAnnuler }) {
  const { appeler, chargement, erreur } = useAPI();
  const [prep, setPrep] = useState(null);
  const [code, setCode] = useState("");
  const [resultat, setResultat] = useState(null);

  useEffect(() => { appeler("post", "/auth/2fa/preparer").then(r => r && setPrep(r)); }, [appeler]);

  const valider = async e => {
    e.preventDefault();
    const r = await appeler("post", "/auth/2fa/activer", { code: code.replace(/\s/g, "") });
    if (r) setResultat(r);
  };

  if (resultat) {
    return <CodesSecours codes={resultat.codes_secours} dark={dark}
      onTermine={() => onActive(appliquerJeton(resultat))} />;
  }
  const lib = sombre ? "block text-xs text-gray-400 mb-1" : etiquette(dark);
  return (
    <form onSubmit={valider} className="space-y-3">
      <ol className={`text-sm space-y-1 list-decimal pl-5 ${dark ? "text-gray-300" : "text-gray-700"}`}>
        <li>{tx("Installe une application d'authentification (Google Authenticator, Microsoft Authenticator, Authy…).")}</li>
        <li>{tx("Scanne ce QR code avec l'application.")}</li>
        <li>{tx("Saisis le code à 6 chiffres qu'elle affiche.")}</li>
      </ol>
      {prep ? (
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(prep.qr_svg)}`} alt={tx("QR code à scanner avec l'application d'authentification")}
            className="w-44 h-44 rounded-lg bg-white p-1" />
          <div className="min-w-0">
            <p className={texteDiscret(dark)}>{tx("Impossible de scanner ? Saisis cette clé dans l'application :")}</p>
            <p className={`font-mono text-sm break-all mt-1 ${dark ? "text-gray-100" : "text-gray-900"}`} aria-label={tx("Clé secrète")}>{prep.secret}</p>
          </div>
        </div>
      ) : !erreur && <p className={texteDiscret(dark)}>{tx("Préparation…")}</p>}
      <label className="block">
        <span className={lib}>{tx("Code à 6 chiffres")}</span>
        <input value={code} onChange={e => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code"
          pattern="[0-9 ]{6,7}" maxLength={7} required className={sombre ? CHAMP_SOMBRE : champ(dark)} />
      </label>
      {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={chargement || !prep} className={`${boutonPrincipal} disabled:opacity-50`}>
          <ShieldCheck size={15} className="inline -mt-0.5 mr-1" />{" "}{tx("Activer")}
        </button>
        {onAnnuler && <button type="button" onClick={onAnnuler} className={boutonSecondaire(dark)}>{sombre ? tx("Se déconnecter") : tx("Annuler")}</button>}
      </div>
    </form>
  );
}

// Administrateur sans double authentification : écran plein avant tout le reste
export function EcranDoubleAuthObligatoire({ session, onTermine, onDeconnexion }) {
  return (
    <div className="min-h-screen bg-foret-950 flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-lg bg-gray-900 border border-foret-800 rounded-2xl p-8 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <Logo />
          <div>
            <h1 className="text-white font-bold">{tx("Protège ton compte")}</h1>
            <p className="text-gray-400 text-xs">{session.utilisateur}</p>
          </div>
        </div>
        <p className="text-sm text-gray-300 mb-5">
          {tx("Ton compte gère des données bancaires (bases branchées, clés d'API ou membres) : il doit utiliser la")}{" "}<strong>{tx("double authentification")}</strong>{" "}{tx(": en plus du mot de passe, un code à 6 chiffres donné par une application de ton téléphone. Un mot de passe volé ne suffit alors plus.")}
        </p>
        <ActivationDoubleAuth sombre onActive={onTermine} onAnnuler={onDeconnexion} />
      </div>
    </div>
  );
}

// Connexion : deuxième étape (code de l'application ou code de secours)
export function SaisieCodeConnexion({ etape, onConnecte, onAnnuler }) {
  const [code, setCode] = useState("");
  const [secours, setSecours] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const valider = async e => {
    e.preventDefault();
    setErreur(null); setEnvoi(true);
    try {
      const { data } = await http.post("/auth/2fa/connexion", { jeton_2fa: etape.jeton, code: code.trim() }, { timeout: 90000 });
      onConnecte(appliquerJeton(data));
    } catch (err) {
      setErreur(messageErreur(err)); setCode("");
    } finally { setEnvoi(false); }
  };
  return (
    <form onSubmit={valider} className="space-y-4">
      <p className="text-sm text-gray-300 flex items-start gap-2">
        {secours ? <LifeBuoy size={16} className="mt-0.5 text-laiton-300" /> : <Smartphone size={16} className="mt-0.5 text-laiton-300" />}
        {secours ? tx("Saisis un de tes codes de secours (ex. ABCD-EFGH). Il ne servira qu'une fois.")
          : tx("Saisis le code à 6 chiffres affiché par ton application d'authentification.")}
      </p>
      <label className="block">
        <span className="block text-xs text-gray-400 mb-1">{secours ? tx("Code de secours") : tx("Code à 6 chiffres")}</span>
        <input autoFocus value={code} onChange={e => setCode(e.target.value)} required
          inputMode={secours ? "text" : "numeric"} autoComplete="one-time-code" maxLength={secours ? 12 : 7}
          className={CHAMP_SOMBRE} />
      </label>
      {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
      <button type="submit" disabled={envoi} className="w-full flex items-center justify-center gap-2 py-3 bg-foret-600 hover:bg-foret-700 text-white font-semibold rounded-xl disabled:opacity-50">
        <KeyRound size={15} /> {envoi ? tx("Vérification…") : tx("Valider")}
      </button>
      <div className="flex justify-between text-xs">
        <button type="button" onClick={() => { setSecours(!secours); setCode(""); setErreur(null); }} className="text-foret-300 hover:underline">
          {secours ? tx("Utiliser l'application") : tx("Téléphone perdu ? Code de secours")}
        </button>
        <button type="button" onClick={onAnnuler} className="text-gray-400 hover:underline">{tx("Annuler")}</button>
      </div>
    </form>
  );
}

// Étape après le mot de passe : notification sur le téléphone si un téléphone est enregistré, sinon code à 6 chiffres
export function EtapeDoubleAuth({ etape, onConnecte, onAnnuler }) {
  const [code, setCode] = useState(!etape.approbation);
  return code ? <SaisieCodeConnexion etape={etape} onConnecte={onConnecte} onAnnuler={onAnnuler} />
    : <AttenteApprobation etape={etape} onConnecte={onConnecte} onCode={() => setCode(true)} />;
}

// Réglages du compte : état, activation, nouveaux codes de secours, désactivation (si non obligatoire)
export function SectionDoubleAuth({ dark, onSession }) {
  const { appeler, chargement, erreur, setErreur } = useAPI();
  const [etat, setEtat] = useState(null);
  const [mode, setMode] = useState(null);         // activer | codes | desactiver
  const [code, setCode] = useState("");
  const [mdp, setMdp] = useState("");
  const [codes, setCodes] = useState(null);

  const charger = useCallback(() => { http.get("/auth/2fa").then(r => setEtat(r.data)).catch(() => {}); }, []);
  useEffect(charger, [charger]);
  if (!etat) return null;

  const fermer = () => { setMode(null); setCode(""); setMdp(""); setErreur(null); charger(); };
  const nouveauxCodes = async e => {
    e.preventDefault();
    const r = await appeler("post", "/auth/2fa/codes-secours", { code: code.trim() });
    if (r) setCodes(r.codes_secours);
  };
  const desactiver = async e => {
    e.preventDefault();
    const r = await appeler("post", "/auth/2fa/desactiver", { mot_de_passe: mdp, code: code.trim() });
    if (r) { onSession(appliquerJeton(r)); fermer(); }
  };

  return (
    <section aria-labelledby="titre-2fa" className={`mb-5 pb-5 border-b ${dark ? "border-gray-700" : "border-gray-200"}`}>
      <h3 id="titre-2fa" className={`text-sm font-semibold flex items-center gap-2 mb-1 ${dark ? "text-white" : "text-gray-900"}`}>
        <Smartphone size={15} />{" "}{tx("Double authentification")}
      </h3>
      {codes ? <CodesSecours codes={codes} dark={dark} onTermine={() => { setCodes(null); fermer(); }} />
        : mode === "activer" ? <ActivationDoubleAuth dark={dark} onAnnuler={fermer} onActive={s => { onSession(s); fermer(); }} />
        : mode ? (
          <form onSubmit={mode === "codes" ? nouveauxCodes : desactiver} className="space-y-2">
            {mode === "desactiver" && (
              <label className="block"><span className={etiquette(dark)}>{tx("Mot de passe")}</span>
                <input type="password" value={mdp} onChange={e => setMdp(e.target.value)} required autoComplete="current-password" className={champ(dark)} /></label>
            )}
            <label className="block"><span className={etiquette(dark)}>{tx("Code de l'application")}</span>
              <input value={code} onChange={e => setCode(e.target.value)} required inputMode="numeric" autoComplete="one-time-code" maxLength={12} className={champ(dark)} /></label>
            {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
            <div className="flex gap-2">
              <button type="submit" disabled={chargement} className={boutonPrincipal}>
                {mode === "codes" ? tx("Générer de nouveaux codes") : tx("Désactiver")}</button>
              <button type="button" onClick={fermer} className={boutonSecondaire(dark)}>{tx("Annuler")}</button>
            </div>
          </form>
        ) : etat.active ? (
          <>
            <p className={texteDiscret(dark)}>
              {tx("Active depuis le {x} · {codes_secours_restants} code(s) de secours restant(s)", { x: formaterDate(etat.date_activation), codes_secours_restants: etat.codes_secours_restants })}
              {etat.requise ? tx(" · obligatoire pour ton rôle") : ""}
            </p>
            <div className="flex flex-wrap gap-2 mt-2">
              <button type="button" onClick={() => setMode("codes")} className={boutonSecondaire(dark)}>{tx("Nouveaux codes de secours")}</button>
              {!etat.requise && <button type="button" onClick={() => setMode("desactiver")} className={boutonSecondaire(dark)}>{tx("Désactiver")}</button>}
            </div>
            <SectionTelephones dark={dark} />
          </>
        ) : (
          <>
            <p className={texteDiscret(dark)}>{tx("Un code à 6 chiffres de ton téléphone en plus du mot de passe : un mot de passe volé ne suffit plus.")}</p>
            <button type="button" onClick={() => setMode("activer")} className={`${boutonPrincipal} mt-2`}>{tx("Activer")}</button>
          </>
        )}
    </section>
  );
}
