// Brancher le logiciel bancaire : clés d'API et exemple d'appel du score de fraude en temps réel.
// L'administrateur de l'organisation crée les clés ; les autres voient la carte avec la marche à suivre.
import { useCallback, useEffect, useState } from "react";
import { KeyRound, Copy, Check, Plug, Eye, ShieldCheck, FlaskConical, Globe } from "lucide-react";
import { http, API, messageErreur } from "../api";
import { carte, champ, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";
import { LOCALE, tx } from "../i18n";

function Copier({ texte, dark }) {
  const [ok, setOk] = useState(false);
  return (
    <button type="button" onClick={() => { navigator.clipboard?.writeText(texte).then(() => { setOk(true); setTimeout(() => setOk(false), 1500); }).catch(() => {}); }}
      className={`${boutonSecondaire(dark)} inline-flex items-center gap-1`}>{ok ? <Check size={12} /> : <Copy size={12} />}{ok ? tx("Copié") : tx("Copier")}</button>
  );
}

export function ClesApi({ source, dark, categories = [], onMesDonnees, onChange }) {
  const [cles, setCles] = useState(null);
  const [nom, setNom] = useState("");
  const [test, setTest] = useState(false);
  const [mode, setMode] = useState("observation");
  const [ips, setIps] = useState("");
  const [editionIps, setEditionIps] = useState(null);   // { id, valeur }
  const [nouvelle, setNouvelle] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [refus, setRefus] = useState(null);
  const charger = useCallback(() => {
    http.get(`/sources/${source.id}/cles-api`, { silencieux: true }).then(r => setCles(r.data.data))
      .catch(e => { if (e.response?.status === 403) setRefus(messageErreur(e)); else setErreur(messageErreur(e)); });
  }, [source.id]);
  useEffect(() => { charger(); }, [charger]);

  const creer = async e => {
    e.preventDefault(); setErreur(null);
    try {
      const r = await http.post(`/sources/${source.id}/cles-api`, { nom, test, mode, ips_autorisees: ips || null });
      setNouvelle(r.data.data); setNom(""); setIps(""); charger(); onChange?.();
    } catch (x) { setErreur(messageErreur(x)); }
  };
  const modifier = async (id, corps) => {
    setErreur(null);
    try { await http.patch(`/sources/${source.id}/cles-api/${id}`, corps); setEditionIps(null); charger(); onChange?.(); }
    catch (x) { setErreur(messageErreur(x)); }
  };
  const pastille = couleur => `inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ${couleur}`;
  const revoquer = async id => {
    try { await http.post(`/sources/${source.id}/cles-api/${id}/revoquer`); charger(); onChange?.(); } catch (x) { setErreur(messageErreur(x)); }
  };
  const exemple = `curl -X POST ${API}/api/v1/operations/score \\
  -H "Authorization: Bearer ${nouvelle?.cle || "vb_…"}" \\
  -H "Content-Type: application/json" \\
  -d '{"reference": "OP-2026-0001", "montant": 250000, "heure": 14${categories.slice(0, 2).map(c => `, "categories": {"${c.colonne}": "${c.valeurs[0]}"}`).slice(0, 1).join("")}}'`;

  return (
    <div className={`${carte(dark)} ${onMesDonnees ? "" : "mt-4"}`}>
      <h2 className={`${titre(dark)} flex items-center gap-2`}><Plug size={18} />{" "}{tx("Brancher votre logiciel bancaire")}</h2>
      <p className={`${texteDiscret(dark)} mt-1`}>
        {tx("Votre logiciel envoie chaque opération avant de la valider ; VoiceBank répond en moins d'une seconde : accepter, vérifier ou bloquer, avec les raisons. Les opérations à vérifier ou à bloquer arrivent aussi dans « Alertes de fraude » pour l'équipe.")}
      </p>
      {refus && (
        <div className={`mt-4 rounded-xl p-4 text-sm ${dark ? "bg-gray-700/50 text-gray-200" : "bg-gray-50 text-gray-700"}`}>
          <p>{refus}</p>
          <ol className="mt-2 list-decimal pl-5 space-y-1 text-xs">
            <li>{tx("Branchez la base de votre organisation dans « Mes données » (administrateur de l'organisation).")}</li>
            <li>{tx("Choisissez-la dans « Données interrogées », puis revenez ici : créez une clé et donnez-la à votre prestataire informatique.")}</li>
            <li>{tx("Votre logiciel appelle l'adresse ci-dessous avant de valider chaque opération.")}</li>
          </ol>
          {onMesDonnees && <button onClick={onMesDonnees} className={`${boutonPrincipal} mt-3`}>{tx("Mes données")}</button>}
        </div>
      )}
      {nouvelle && (
        <div role="status" className="mt-4 rounded-xl border border-laiton-400/40 bg-laiton-400/10 p-4">
          <p className="text-sm font-semibold">{tx("Clé « {nom} » créée : copiez-la maintenant, elle ne sera plus jamais affichée.", { nom: nouvelle.nom })}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <code className={`text-xs break-all rounded-lg px-2 py-1 ${dark ? "bg-gray-900" : "bg-white"}`}>{nouvelle.cle}</code>
            <Copier texte={nouvelle.cle} dark={dark} />
          </div>
        </div>
      )}
      {!refus && <form onSubmit={creer} className="mt-4 space-y-2">
        <div className="flex flex-wrap gap-2">
          <input value={nom} onChange={e => setNom(e.target.value)} required minLength={2} maxLength={80}
            placeholder={tx("Nom de la clé (ex. : Logiciel Amplitude, agence de Douala)")} aria-label={tx("Nom de la clé")}
            className={`${champ(dark)} flex-1 min-w-[14rem]`} />
          <select value={test ? "test" : "reelle"} onChange={e => setTest(e.target.value === "test")} aria-label={tx("Type de clé")} className={champ(dark)}>
            <option value="reelle">{tx("Clé réelle")}</option>
            <option value="test">{tx("Clé de test (aucune alerte)")}</option>
          </select>
          <select value={mode} onChange={e => setMode(e.target.value)} aria-label={tx("Mode")} className={champ(dark)}>
            <option value="observation">{tx("Observation : noter sans bloquer (conseillé au début)")}</option>
            <option value="actif">{tx("Actif : la décision s'applique")}</option>
          </select>
        </div>
        <div className="flex flex-wrap gap-2">
          <input value={ips} onChange={e => setIps(e.target.value)} maxLength={1000}
            placeholder={tx("Adresses IP autorisées, facultatif (ex. : 41.202.10.5, 41.202.0.0/16)")} aria-label={tx("Adresses IP autorisées")}
            className={`${champ(dark)} flex-1 min-w-[14rem]`} />
          <button type="submit" className={boutonPrincipal}><KeyRound size={14} className="inline mr-1" />{tx("Créer une clé")}</button>
        </div>
        <p className={`${texteDiscret(dark)} text-xs`}>
          {tx("Observation : votre logiciel reçoit toujours « accepter », et la décision de VoiceBank est notée à côté. Comparez quelques jours, puis activez le blocage. Clé de test : pour la recette chez le prestataire, elle répond comme en réel sans créer d'alerte. Adresses IP : seuls vos serveurs peuvent utiliser la clé, même si elle fuite.")}
        </p>
      </form>}
      {erreur && <p role="alert" className="mt-2 text-xs text-red-500">{erreur}</p>}
      {cles?.length > 0 && (
        <ul className="mt-4 space-y-2">
          {cles.map(c => (
            <li key={c.id} className={`rounded-xl px-3 py-2 text-sm ${dark ? "bg-gray-700/50" : "bg-gray-50"} ${c.revoquee ? "opacity-50" : ""}`}>
              <div className="flex flex-wrap items-center gap-2">
                <KeyRound size={14} className="text-laiton-500" />
                <span className="font-medium">{c.nom}</span>
                <code className={texteDiscret(dark)}>{c.prefixe}…</code>
                {c.test && <span className={pastille("bg-purple-500/15 text-purple-600 dark:text-purple-300")}><FlaskConical size={11} />{tx("Test")}</span>}
                {c.mode === "observation"
                  ? <span className={pastille("bg-amber-500/15 text-amber-700 dark:text-amber-300")}><Eye size={11} />{tx("Observation")}</span>
                  : <span className={pastille("bg-emerald-500/15 text-emerald-700 dark:text-emerald-300")}><ShieldCheck size={11} />{tx("Actif")}</span>}
                <span className={texteDiscret(dark)}>{tx("{x} appel(s)", { x: c.nb_appels.toLocaleString(LOCALE) })}
                  {c.derniere_utilisation ? tx(" · dernier le {x}", { x: formaterDate(c.derniere_utilisation) }) : ""}</span>
                {c.revoquee ? <span className={`${texteDiscret(dark)} ml-auto`}>{tx("révoquée")}</span> : (
                  <span className="ml-auto flex flex-wrap gap-2">
                    <button onClick={() => modifier(c.id, { mode: c.mode === "observation" ? "actif" : "observation" })} className={boutonSecondaire(dark)}>
                      {c.mode === "observation" ? tx("Activer le blocage") : tx("Repasser en observation")}</button>
                    <button onClick={() => setEditionIps({ id: c.id, valeur: c.ips_autorisees || "" })} className={boutonSecondaire(dark)}>{tx("Adresses IP")}</button>
                    <button onClick={() => revoquer(c.id)} className={boutonSecondaire(dark)}>{tx("Révoquer")}</button>
                  </span>)}
              </div>
              <p className={`${texteDiscret(dark)} mt-1 text-xs flex items-center gap-1`}><Globe size={11} />{" "}
                {c.ips_autorisees ? tx("Autorisée seulement depuis : {x}", { x: c.ips_autorisees }) : tx("Utilisable depuis toutes les adresses IP")}</p>
              {editionIps?.id === c.id && (
                <form className="mt-2 flex flex-wrap gap-2" onSubmit={e => { e.preventDefault(); modifier(c.id, { changer_ips: true, ips_autorisees: editionIps.valeur }); }}>
                  <input value={editionIps.valeur} onChange={e => setEditionIps({ id: c.id, valeur: e.target.value })} maxLength={1000} autoFocus
                    placeholder={tx("Vide = toutes les adresses")} aria-label={tx("Adresses IP autorisées")} className={`${champ(dark)} flex-1 min-w-[14rem]`} />
                  <button type="submit" className={boutonPrincipal}>{tx("Enregistrer")}</button>
                  <button type="button" onClick={() => setEditionIps(null)} className={boutonSecondaire(dark)}>{tx("Annuler")}</button>
                </form>)}
            </li>
          ))}
        </ul>
      )}
      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-medium">{tx("Exemple d'appel")}</summary>
        <div className="mt-2 flex justify-end"><Copier texte={exemple} dark={dark} /></div>
        <pre className={`mt-1 overflow-x-auto rounded-xl p-3 text-xs ${dark ? "bg-gray-900 text-gray-200" : "bg-gray-900 text-gray-100"}`}>{exemple}</pre>
        <p className={`${texteDiscret(dark)} mt-2`}>{tx("Réponse : decision (accepter, verifier, bloquer), niveau, score de 0 à 1, raisons, recommandation. Colonnes non envoyées : valeur la plus courante de la base, indiquée dans « valeurs_supposees ».")}{" "}
          {tx("En observation, decision vaut toujours « accepter » et decision_voicebank donne l'avis de VoiceBank ; mode indique actif, observation ou test.")}</p>
      </details>
    </div>
  );
}
