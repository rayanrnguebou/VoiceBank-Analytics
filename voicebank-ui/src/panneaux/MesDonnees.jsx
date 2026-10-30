// Mes données personnelles (loi camerounaise n° 2024/017) : télécharger tout ce que VoiceBank garde sur le compte,
// et effacer son compte (mot de passe + mot « SUPPRIMER »).
import { useState, useEffect } from "react";
import { Download, Trash2, FileText } from "lucide-react";
import { useAPI } from "../useAPI";
import { http, messageErreur, deconnexion, noterMotifDeconnexion } from "../api";
import { champ, etiquette, texteDiscret, boutonPrincipal, boutonSecondaire } from "../ui";
import { tx } from "../i18n";

export function SectionMesDonnees({ dark }) {
  const { appeler, chargement, erreur, setErreur } = useAPI();
  const [etat, setEtat] = useState(null);
  const [telechargement, setTelechargement] = useState(null);     // null | "en_cours" | message d'erreur
  const [effacer, setEffacer] = useState(false);
  const [mdp, setMdp] = useState("");
  const [mot, setMot] = useState("");

  useEffect(() => { http.get("/moi/effacement").then(r => setEtat(r.data)).catch(() => {}); }, []);
  if (!etat) return null;

  const telecharger = async () => {
    setTelechargement("en_cours");
    try {
      const r = await http.get("/moi/donnees", { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(r.data);
      a.download = `voicebank_mes_donnees_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      setTelechargement(null);
    } catch (e) {
      setTelechargement(messageErreur(e));
    }
  };

  const confirmer = async e => {
    e.preventDefault();
    const r = await appeler("post", "/moi/supprimer", { mot_de_passe: mdp, confirmation: mot });
    if (r) {
      noterMotifDeconnexion(tx("Ton compte et tes données personnelles ont été effacés. Merci d'avoir utilisé VoiceBank."));
      deconnexion();
      window.dispatchEvent(new Event("voicebank:deconnexion"));
    }
  };

  const c = etat.conservation || {};
  return (
    <section aria-labelledby="titre-mes-donnees" className={`mt-5 pt-5 border-t ${dark ? "border-gray-700" : "border-gray-200"}`}>
      <h3 id="titre-mes-donnees" className={`text-sm font-semibold flex items-center gap-2 mb-1 ${dark ? "text-white" : "text-gray-900"}`}>
        <FileText size={15} />{" "}{tx("Mes données personnelles")}
      </h3>
      <p className={texteDiscret(dark)}>
        {tx("Tu peux télécharger tout ce que VoiceBank garde sur ton compte (profil, questions posées, paiements, connexions).")}{" "}
        <a href="/confidentialite/" target="_blank" rel="noopener noreferrer" className="underline">{tx("Politique de confidentialité")}</a>
      </p>
      <button type="button" onClick={telecharger} disabled={telechargement === "en_cours"}
        className={`${boutonSecondaire(dark)} mt-2 flex items-center gap-1`}>
        <Download size={13} />{" "}{telechargement === "en_cours" ? tx("Préparation…") : tx("Télécharger mes données")}
      </button>
      {telechargement && telechargement !== "en_cours" && <p role="alert" className="text-sm text-red-400 mt-1">{telechargement}</p>}

      <div className="mt-4">
        {!etat.possible ? (
          <p className={texteDiscret(dark)}>{tx("Effacement du compte :")}{" "}{etat.raison}</p>
        ) : !effacer ? (
          <button type="button" onClick={() => setEffacer(true)} className={`${boutonSecondaire(dark)} flex items-center gap-1 text-red-500`}>
            <Trash2 size={13} />{" "}{tx("Supprimer mon compte")}
          </button>
        ) : (
          <form onSubmit={confirmer} className={`space-y-2 p-3 rounded-xl border ${dark ? "border-red-900 bg-red-950/30" : "border-red-200 bg-red-50"}`}>
            <p className={`text-sm ${dark ? "text-gray-200" : "text-gray-800"}`}>
              {tx("Ton profil, tes questions, tes préférences, ta double authentification et, si tu es seul dans ton organisation, ses bases connectées seront effacés. C'est définitif.")}
            </p>
            <p className={texteDiscret(dark)}>
              {tx("Conservés au titre de la loi : paiements et facturation ({paiements}), journal d'activité ({audit}), sous un identifiant anonyme.",
                  { paiements: c.paiements || "10 ans", audit: c.journal_audit || "5 ans" })}
            </p>
            <label className="block"><span className={etiquette(dark)}>{tx("Mot de passe")}</span>
              <input type="password" value={mdp} onChange={e => setMdp(e.target.value)} required autoComplete="current-password" className={champ(dark)} /></label>
            <label className="block"><span className={etiquette(dark)}>{tx("Tape SUPPRIMER pour confirmer")}</span>
              <input value={mot} onChange={e => setMot(e.target.value)} required autoComplete="off" className={champ(dark)} /></label>
            {erreur && <p role="alert" className="text-sm text-red-400">{erreur}</p>}
            <div className="flex gap-2">
              <button type="submit" disabled={chargement || !["SUPPRIMER", "DELETE"].includes(mot.trim().toUpperCase())}
                className={`${boutonPrincipal} !bg-red-600 hover:!bg-red-700`}>{tx("Effacer définitivement")}</button>
              <button type="button" onClick={() => { setEffacer(false); setMdp(""); setMot(""); setErreur(null); }}
                className={boutonSecondaire(dark)}>{tx("Annuler")}</button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
