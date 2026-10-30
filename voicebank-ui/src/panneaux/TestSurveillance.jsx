// Administration → Maintenance : vérifier que la surveillance fonctionne (erreur de test envoyée à Sentry depuis
// l'API et depuis l'interface) et retrouver la page d'état publique.
import { useState } from "react";
import { BellRing, ExternalLink } from "lucide-react";
import { http, messageErreur } from "../api";
import { alertesInterfaceActives, envoyerErreurTestInterface } from "../alertesErreurs";
import { PAGE_ETAT } from "../etatService";
import { carte, titre, texteDiscret, boutonPrincipal } from "../ui";
import { tx } from "../i18n";

export function CarteSurveillance({ dark, utilisateur }) {
  const [resultats, setResultats] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  const tester = async () => {
    setEnvoi(true);
    const res = {};
    try {
      const r = await http.post("/admin/sentry/test");
      res.api = { ok: true, texte: tx("erreur de test envoyée (n° {id}).", { id: (r.data.evenement || "").slice(0, 8) }) };
    } catch (e) {
      res.api = { ok: false, texte: messageErreur(e) };
    }
    if (!alertesInterfaceActives) {
      res.interface = { ok: false, texte: tx("non configurée : renseigne REACT_APP_SENTRY_DSN sur Render (voicebank-ui).") };
    } else {
      try {
        const id = await envoyerErreurTestInterface(utilisateur || "admin");
        res.interface = { ok: true, texte: tx("erreur de test envoyée (n° {id}).", { id: String(id || "").slice(0, 8) }) };
      } catch (e) {
        res.interface = { ok: false, texte: tx("envoi impossible ({message}).", { message: e.message }) };
      }
    }
    setResultats(res);
    setEnvoi(false);
  };

  const ligne = (nom, r) => (
    <li className={r.ok ? "text-emerald-500" : "text-red-400"}><strong>{nom} :</strong>{" "}{r.texte}</li>
  );

  return (
    <div className={carte(dark)}>
      <h2 className={`${titre(dark)} flex items-center gap-2 mb-1`}><BellRing size={18} />{" "}{tx("Surveillance du service")}</h2>
      <p className={`${texteDiscret(dark)} mb-4`}>
        {tx("Envoie une erreur de test à Sentry, depuis l'API et depuis l'interface : un e-mail de Sentry doit arriver dans les minutes qui suivent. Rien n'est cassé, l'application continue normalement.")}
      </p>
      <button onClick={tester} disabled={envoi} className={boutonPrincipal}>{envoi ? tx("Envoi…") : tx("Envoyer une erreur de test")}</button>
      {resultats && <ul role="status" className="mt-3 space-y-1 text-sm">{ligne(tx("API"), resultats.api)}{ligne(tx("Interface"), resultats.interface)}</ul>}
      <p className={`${texteDiscret(dark)} mt-4`}>
        {PAGE_ETAT ? (
          <a href={PAGE_ETAT} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline">
            {tx("Page d'état publique (UptimeRobot)")}<ExternalLink size={12} /></a>
        ) : tx("Page d'état publique : crée-la sur UptimeRobot puis renseigne REACT_APP_PAGE_ETAT_URL (voir README).")}
      </p>
    </div>
  );
}
