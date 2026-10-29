// Mes appareils : sessions ouvertes ces 30 derniers jours, déconnexion à distance d'un appareil ou de tous les autres.
import { useState, useEffect, useCallback } from "react";
import { MonitorSmartphone, LogOut } from "lucide-react";
import { useAPI } from "../useAPI";
import { appliquerJeton, http } from "../api";
import { texteDiscret, boutonSecondaire, formaterDate } from "../ui";
import { tx } from "../i18n";

export function SectionAppareils({ dark, onSession }) {
  const { appeler, chargement, erreur } = useAPI();
  const [liste, setListe] = useState(null);
  const [message, setMessage] = useState(null);

  const charger = useCallback(() => { http.get("/moi/sessions").then(r => setListe(r.data.data)).catch(() => {}); }, []);
  useEffect(charger, [charger]);
  if (!liste) return null;

  const deconnecter = async s => {
    if (await appeler("post", `/moi/sessions/${encodeURIComponent(s.id)}/deconnecter`)) {
      setMessage(tx("{appareil} est déconnecté.", { appareil: s.appareil }));
      charger();
    }
  };
  const deconnecterAutres = async () => {
    if (!window.confirm(tx("Déconnecter tous les autres appareils ? Ils devront se reconnecter avec le mot de passe."))) return;
    const r = await appeler("post", "/moi/sessions/deconnecter-autres");
    if (r) {
      onSession?.(appliquerJeton(r));
      setMessage(tx("Les autres appareils sont déconnectés."));
      charger();
    }
  };
  const actives = liste.filter(s => s.active && !s.courante);

  return (
    <section aria-labelledby="titre-appareils" className={`mb-5 pb-5 border-b ${dark ? "border-gray-700" : "border-gray-200"}`}>
      <h3 id="titre-appareils" className={`text-sm font-semibold flex items-center gap-2 mb-1 ${dark ? "text-white" : "text-gray-900"}`}>
        <MonitorSmartphone size={15} />{" "}{tx("Mes appareils")}
      </h3>
      <p className={texteDiscret(dark)}>{tx("Connexions des 30 derniers jours. Un e-mail te prévient quand un nouvel appareil se connecte.")}</p>
      <ul className="mt-2 space-y-1.5">
        {liste.map(s => (
          <li key={s.id} className={`flex items-center justify-between gap-2 text-sm px-3 py-2 rounded-lg ${dark ? "bg-gray-700/50" : "bg-gray-50"}`}>
            <span className="min-w-0">
              <span className={`font-medium ${dark ? "text-gray-100" : "text-gray-800"}`}>{s.appareil}</span>
              {s.courante && <span className="ml-2 text-xs text-emerald-500">{tx("cet appareil")}</span>}
              <span className={`block ${texteDiscret(dark)}`}>
                {s.adresse_ip || tx("adresse inconnue")} · {tx("dernière activité le {date}", { date: formaterDate(s.derniere_activite) })}
                {!s.active && ` · ${tx("terminée")}`}
              </span>
            </span>
            {s.active && !s.courante && (
              <button type="button" onClick={() => deconnecter(s)} disabled={chargement}
                className={`${boutonSecondaire(dark)} flex items-center gap-1 flex-shrink-0`}>
                <LogOut size={13} />{" "}{tx("Déconnecter")}
              </button>
            )}
          </li>
        ))}
      </ul>
      {actives.length > 0 && (
        <button type="button" onClick={deconnecterAutres} disabled={chargement}
          className={`${boutonSecondaire(dark)} mt-2 text-red-500`}>{tx("Déconnecter les autres appareils")}</button>
      )}
      {message && <p role="status" className="text-sm text-emerald-500 mt-2">{message}</p>}
      {erreur && <p role="alert" className="text-sm text-red-400 mt-2">{erreur}</p>}
    </section>
  );
}
