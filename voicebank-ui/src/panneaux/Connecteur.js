// « Mes données » : brancher la base ou les fichiers de son organisation, comprendre leur structure,
// diagnostiquer leur qualité, puis les interroger en français depuis l'assistant.
import { useState, useEffect, useCallback, useRef } from "react";
import {
  Database, FileSpreadsheet, Server, Plus, RefreshCw, Trash2, Search, ShieldCheck, ShieldAlert, Lock,
  CircleAlert, TriangleAlert, Info, ChevronDown, ChevronUp, Upload, Link2, Sparkles, ArrowLeft, Copy, Check,
  Star,
} from "lucide-react";
import { useAPI } from "../useAPI";
import { http } from "../api";
import { carte, champ, etiquette, titre, texteDiscret, boutonPrincipal, boutonSecondaire, formaterDate } from "../ui";
import { useDevise } from "../devise";

const ICONES = { postgresql: Database, mysql: Database, sqlserver: Server, fichier: FileSpreadsheet, demo: Sparkles };
const LIB_ROLES = {
  identifiant: "Identifiant", montant: "Montant", quantite: "Quantité", taux: "Taux", score: "Score", date: "Date",
  statut: "Statut", categorie: "Catégorie", geographie: "Lieu", drapeau_fraude: "Fraude", texte: "Texte",
  mesure: "Mesure", secret: "Secret",
};
const LIB_DOMAINES = { banque: "Banque", microfinance: "Microfinance", assurance: "Assurance", commerce: "Commerce",
  "générique": "Données générales" };
const AIDE_LECTURE_SEULE = {
  postgresql: `CREATE ROLE voicebank_lecture LOGIN PASSWORD 'mot-de-passe-long';
GRANT CONNECT ON DATABASE ma_base TO voicebank_lecture;
GRANT USAGE ON SCHEMA public TO voicebank_lecture;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO voicebank_lecture;`,
  mysql: `CREATE USER 'voicebank_lecture'@'%' IDENTIFIED BY 'mot-de-passe-long';
GRANT SELECT ON ma_base.* TO 'voicebank_lecture'@'%';`,
  sqlserver: `CREATE LOGIN voicebank_lecture WITH PASSWORD = 'mot-de-passe-long';
USE ma_base;
CREATE USER voicebank_lecture FOR LOGIN voicebank_lecture;
ALTER ROLE db_datareader ADD MEMBER voicebank_lecture;`,
};

function Jauge({ score, dark }) {
  if (score == null) return null;
  const couleur = score >= 85 ? "#10B981" : score >= 65 ? "#C9A13B" : "#EF4444";
  const r = 22, c = 2 * Math.PI * r;
  return (
    <div className="relative w-14 h-14 flex-shrink-0" title={`Qualité des données : ${score}/100`}>
      <svg viewBox="0 0 56 56" className="w-14 h-14 -rotate-90">
        <circle cx="28" cy="28" r={r} fill="none" stroke={dark ? "#2D3532" : "#E9EDEB"} strokeWidth="5" />
        <circle cx="28" cy="28" r={r} fill="none" stroke={couleur} strokeWidth="5" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - score / 100)} />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-bold">{score}</span>
    </div>
  );
}

function BlocCode({ code, dark }) {
  const [copie, setCopie] = useState(false);
  return (
    <div className="relative">
      <pre className={`text-xs p-3 rounded-lg overflow-x-auto ${dark ? "bg-gray-900 text-foret-200" : "bg-gray-100 text-foret-900"}`}>{code}</pre>
      <button type="button" aria-label="Copier" onClick={async () => { try { await navigator.clipboard.writeText(code); setCopie(true); } catch (e) { /* rien */ } }}
        className={`absolute top-2 right-2 ${boutonSecondaire(dark)}`}>{copie ? <Check size={12} /> : <Copy size={12} />}</button>
    </div>
  );
}

// ── Assistant de connexion ─────────────────────────────────────────────
function NouvelleSource({ dark, types, onCree, onAnnuler }) {
  const test = useAPI();
  const envoi = useAPI();
  const [type, setType] = useState(null);
  const [f, setF] = useState({ nom: "", hote: "", port: "", base: "", utilisateur: "", mot_de_passe: "", ssl: "prefere", schema: "" });
  const [resultat, setResultat] = useState(null);
  const [fichiers, setFichiers] = useState([]);
  const [aide, setAide] = useState(false);
  const entree = useRef(null);
  const maj = k => e => { setF({ ...f, [k]: e.target.value }); setResultat(null); };
  const corps = () => ({
    type_source: type, hote: f.hote.trim(), port: f.port ? Number(f.port) : null, base: f.base.trim(),
    utilisateur: f.utilisateur.trim(), mot_de_passe: f.mot_de_passe, ssl: f.ssl, ...(f.schema.trim() ? { schema: f.schema.trim() } : {}),
  });
  const tester = async () => { setResultat(await test.appeler("post", "/sources/tester", corps())); };
  const connecter = async (e) => {
    e.preventDefault();
    if (type === "fichier") {
      const donnees = new FormData();
      donnees.append("nom", f.nom.trim());
      fichiers.forEach(x => donnees.append("fichiers", x));
      const r = await envoi.appeler("post", "/sources/fichiers", donnees, { timeout: 120000 });
      if (r) onCree(r.id);
    } else {
      const r = await envoi.appeler("post", "/sources", { nom: f.nom.trim(), ...corps() }, { timeout: 60000 });
      if (r) onCree(r.id);
    }
  };
  const portDefaut = types.find(t => t.code === type)?.port;

  if (!type) {
    return (
      <div className={carte(dark)}>
        <div className="flex items-center justify-between mb-4">
          <h2 className={titre(dark)}>Connecter tes données</h2>
          <button onClick={onAnnuler} className={boutonSecondaire(dark)}>Annuler</button>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[["postgresql", "PostgreSQL", "Base PostgreSQL accessible sur Internet"],
            ["mysql", "MySQL / MariaDB", "Très courant dans les logiciels de gestion"],
            ["sqlserver", "SQL Server", "Fréquent dans les banques et grandes structures"],
            ["fichier", "Excel / CSV", "Dépose tes fichiers, sans accès serveur"]].map(([code, lib, desc]) => {
            const Icone = ICONES[code];
            return (
              <button key={code} onClick={() => setType(code)}
                className={`text-left p-4 rounded-xl border transition-colors ${dark ? "border-gray-700 hover:border-laiton-400" : "border-gray-200 hover:border-laiton-400"}`}>
                <Icone size={22} className="text-laiton-400" />
                <p className="text-sm font-semibold mt-2">{lib}</p>
                <p className={texteDiscret(dark)}>{desc}</p>
              </button>
            );
          })}
        </div>
        <p className={`${texteDiscret(dark)} mt-4 flex items-start gap-2`}>
          <ShieldCheck size={14} className="flex-shrink-0 mt-0.5 text-emerald-500" />
          Lecture seule : VoiceBank n'écrit jamais dans ta base. Les identifiants sont chiffrés, les données personnelles
          masquées et jamais envoyées à l'IA, et toi seul peux interroger cette source.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={connecter} className={`${carte(dark)} space-y-4`}>
      <div className="flex items-center justify-between">
        <h2 className={`${titre(dark)} flex items-center gap-2`}>
          <button type="button" onClick={() => { setType(null); setResultat(null); }} aria-label="Retour" className={boutonSecondaire(dark)}><ArrowLeft size={14} /></button>
          {type === "fichier" ? "Importer des fichiers" : `Connecter une base ${types.find(t => t.code === type)?.libelle || ""}`}
        </h2>
        <button type="button" onClick={onAnnuler} className={boutonSecondaire(dark)}>Annuler</button>
      </div>
      <label className="block">
        <span className={etiquette(dark)}>Nom de la source</span>
        <input value={f.nom} onChange={maj("nom")} required minLength={2} maxLength={80} placeholder="ex. Base de production, Export du mois…" className={champ(dark)} />
      </label>

      {type === "fichier" ? (
        <div>
          <div onClick={() => entree.current?.click()} onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); setFichiers([...e.dataTransfer.files].slice(0, 5)); }}
            className={`cursor-pointer p-6 rounded-xl border-2 border-dashed text-center ${dark ? "border-gray-600 hover:border-laiton-400" : "border-gray-300 hover:border-laiton-400"}`}>
            <Upload size={22} className="mx-auto text-laiton-400" />
            <p className="text-sm mt-2">Dépose tes fichiers ici ou clique pour choisir</p>
            <p className={texteDiscret(dark)}>CSV ou Excel .xlsx · 5 fichiers, 10 Mo chacun au plus · chaque feuille devient une table</p>
            <input ref={entree} type="file" multiple accept=".csv,.txt,.xlsx" className="hidden" aria-label="Fichiers"
              onChange={e => setFichiers([...e.target.files].slice(0, 5))} />
          </div>
          {fichiers.length > 0 && (
            <ul className="mt-2 space-y-1">{fichiers.map(x => <li key={x.name} className="text-xs flex items-center gap-2"><FileSpreadsheet size={12} /> {x.name} · {(x.size / 1024).toFixed(0)} Ko</li>)}</ul>
          )}
        </div>
      ) : (
        <>
          <div className="grid sm:grid-cols-3 gap-3">
            <label className="sm:col-span-2"><span className={etiquette(dark)}>Adresse du serveur</span>
              <input value={f.hote} onChange={maj("hote")} required maxLength={253} placeholder="ex. db.mabanque.cm" className={champ(dark)} /></label>
            <label><span className={etiquette(dark)}>Port</span>
              <input type="number" min={1} max={65535} value={f.port} onChange={maj("port")} placeholder={String(portDefaut || "")} className={champ(dark)} /></label>
            <label><span className={etiquette(dark)}>Base de données</span>
              <input value={f.base} onChange={maj("base")} required maxLength={128} className={champ(dark)} /></label>
            <label><span className={etiquette(dark)}>Utilisateur (lecture seule)</span>
              <input value={f.utilisateur} onChange={maj("utilisateur")} required maxLength={128} autoComplete="off" className={champ(dark)} /></label>
            <label><span className={etiquette(dark)}>Mot de passe</span>
              <input type="password" value={f.mot_de_passe} onChange={maj("mot_de_passe")} maxLength={256} autoComplete="new-password" className={champ(dark)} /></label>
            <label><span className={etiquette(dark)}>Chiffrement SSL</span>
              <select value={f.ssl} onChange={maj("ssl")} className={champ(dark)}>
                <option value="prefere">Si disponible</option><option value="exige">Exigé</option><option value="desactive">Désactivé</option>
              </select></label>
            {type !== "mysql" && (
              <label><span className={etiquette(dark)}>Schéma (facultatif)</span>
                <input value={f.schema} onChange={maj("schema")} maxLength={128} pattern="[A-Za-z0-9_]+" placeholder={type === "sqlserver" ? "dbo" : "public"} className={champ(dark)} /></label>
            )}
          </div>
          <button type="button" onClick={() => setAide(!aide)} className={`text-xs flex items-center gap-1 ${dark ? "text-foret-300" : "text-foret-700"}`}>
            {aide ? <ChevronUp size={12} /> : <ChevronDown size={12} />} Comment créer un compte en lecture seule ?
          </button>
          {aide && (
            <div className="space-y-2">
              <p className={texteDiscret(dark)}>À faire exécuter par l'administrateur de la base, puis autoriser l'adresse du serveur VoiceBank dans le pare-feu :</p>
              <BlocCode code={AIDE_LECTURE_SEULE[type]} dark={dark} />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={tester} disabled={test.chargement || !f.hote || !f.base || !f.utilisateur} className={`${boutonSecondaire(dark)} flex items-center gap-1`}>
              <Link2 size={13} /> {test.chargement ? "Test…" : "Tester la connexion"}
            </button>
            {test.erreur && <span className="text-sm text-red-500">{test.erreur}</span>}
            {resultat && (
              <span className="text-sm text-emerald-500 flex items-center gap-1"><Check size={14} /> Connecté · version {resultat.version} · {resultat.tables} table(s)</span>
            )}
          </div>
          {resultat?.avertissement && (
            <p className="text-xs p-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-600 flex gap-2"><TriangleAlert size={14} className="flex-shrink-0" /> {resultat.avertissement}</p>
          )}
        </>
      )}
      {envoi.erreur && <p role="alert" className="text-sm text-red-500">{envoi.erreur}</p>}
      <button type="submit" disabled={envoi.chargement || (type === "fichier" ? !fichiers.length : !resultat)} className={boutonPrincipal}>
        {envoi.chargement ? "Connexion…" : type === "fichier" ? "Importer et analyser" : "Connecter et analyser"}
      </button>
      {type !== "fichier" && !resultat && <p className={texteDiscret(dark)}>Teste d'abord la connexion.</p>}
    </form>
  );
}

// ── Détail : diagnostic, carte des données, relations ─────────────────
const ICONE_GRAVITE = { critique: CircleAlert, attention: TriangleAlert, info: Info };
const COULEUR_GRAVITE = { critique: "text-red-500", attention: "text-amber-500", info: "text-sky-500" };

function TableProfil({ t, dark }) {
  const [ouvert, setOuvert] = useState(false);
  return (
    <div className={`rounded-xl border ${dark ? "border-gray-700" : "border-gray-200"}`}>
      <button onClick={() => setOuvert(!ouvert)} className="w-full flex items-center justify-between gap-3 p-3 text-left">
        <div className="min-w-0">
          <p className="text-sm font-semibold truncate">{t.nom} {t.entite && <span className={`${texteDiscret(dark)} font-normal`}>· {t.entite}</span>}</p>
          <p className={texteDiscret(dark)}>{t.erreur || `${Number(t.lignes ?? 0).toLocaleString("fr-FR")} lignes · ${t.colonnes.length} colonnes${t.cle_primaire?.length ? ` · clé ${t.cle_primaire[0]}` : ""}`}</p>
        </div>
        {ouvert ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      {ouvert && (
        <div className="overflow-x-auto px-3 pb-3">
          <table className="w-full text-xs">
            <thead><tr className={texteDiscret(dark)}><th className="text-left p-1.5">Colonne</th><th className="text-left p-1.5">Rôle détecté</th>
              <th className="text-left p-1.5">Vides</th><th className="text-left p-1.5">Aperçu</th></tr></thead>
            <tbody>
              {t.colonnes.map(c => (
                <tr key={c.nom} className={`border-t ${dark ? "border-gray-700" : "border-gray-100"}`}>
                  <td className="p-1.5 font-mono">{c.nom}</td>
                  <td className="p-1.5 whitespace-nowrap">
                    <span className={`px-1.5 py-0.5 rounded ${c.role === "secret" ? "bg-red-500/15 text-red-500" : dark ? "bg-gray-700" : "bg-gray-100"}`}>{LIB_ROLES[c.role] || c.role}</span>
                    {c.pii && <span className="ml-1 inline-flex items-center gap-0.5 text-amber-600" title="Donnée personnelle : masquée, jamais envoyée à l'IA"><Lock size={11} /> {c.pii.replace("_", " ")}</span>}
                  </td>
                  <td className="p-1.5">{c.nulls_pct == null ? "—" : `${c.nulls_pct} %`}</td>
                  <td className={`p-1.5 ${texteDiscret(dark)}`}>
                    {c.valeurs ? c.valeurs.slice(0, 4).map(v => v.valeur).join(", ")
                      : c.min != null ? `${Number(c.min).toLocaleString("fr-FR")} → ${Number(c.max).toLocaleString("fr-FR")}`
                      : c.date_min ? `${c.date_min} → ${c.date_max}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MonnaieSource({ d, dark }) {
  const { liste } = useDevise();
  const [choix, setChoix] = useState(d.devise_choisie || "");
  const [ok, setOk] = useState(false);
  if (d.demo) return null;
  const changer = async (e) => {
    const v = e.target.value;
    setChoix(v); setOk(false);
    try { await http.post(`/sources/${d.id}/devise`, { devise: v || null }); setOk(true); } catch (err) { /* rien */ }
  };
  return (
    <label className={`flex flex-wrap items-center gap-2 mt-3 ${texteDiscret(dark)}`}>
      Les montants de cette base sont en
      <select value={choix} onChange={changer} aria-label="Monnaie de la base"
        className={`text-xs px-2 py-1 rounded-lg border outline-none ${dark ? "bg-gray-700 border-gray-600 text-gray-200" : "bg-gray-50 border-gray-200"}`}>
        <option value="">détection automatique ({d.devise_detectee || "XAF par défaut"})</option>
        {liste.map(x => <option key={x.code} value={x.code}>{x.nom}</option>)}
      </select>
      {ok && <Check size={13} className="text-emerald-500" />}
      <span>— l'affichage suit la monnaie choisie en haut de l'écran.</span>
    </label>
  );
}

function DetailSource({ dark, id, onRetour, onInterroger }) {
  const { appeler, erreur } = useAPI();
  const [d, setD] = useState(null);
  const [onglet, setOnglet] = useState("diagnostic");
  useEffect(() => { appeler("get", `/sources/${id}`, null, { timeout: 120000 }).then(r => r && setD(r.data)); }, [appeler, id]);
  if (!d) return <div className={carte(dark)}><p className={texteDiscret(dark)}>{erreur || "Analyse de la base…"}</p></div>;
  const p = d.profil || {};
  const r = p.resume || {};
  const onglets = [["diagnostic", `Diagnostic (${(p.diagnostics || []).length})`], ["carte", `Carte des données (${r.tables || 0})`],
    ["relations", `Relations (${(p.relations || []).length})`], ["questions", "Questions suggérées"]];
  return (
    <div className="space-y-4">
      <div className={carte(dark)}>
        <button onClick={onRetour} className={`${boutonSecondaire(dark)} mb-3 flex items-center gap-1`}><ArrowLeft size={13} /> Mes données</button>
        <div className="flex flex-wrap items-center gap-4">
          <Jauge score={p.score_qualite} dark={dark} />
          <div className="flex-1 min-w-0">
            <h2 className={titre(dark)}>{d.nom}</h2>
            <p className={texteDiscret(dark)}>{d.libelle_type} · {LIB_DOMAINES[p.domaine] || p.domaine} · analysée le {formaterDate(p.date_analyse)}</p>
            <p className="text-sm mt-1">{r.tables} tables · {Number(r.lignes || 0).toLocaleString("fr-FR")} lignes · {r.colonnes} colonnes ·{" "}
              {r.relations} relations · <span className="text-amber-600">{r.donnees_personnelles} données personnelles protégées</span></p>
          </div>
          <button onClick={() => onInterroger(d)} className={`${boutonPrincipal} flex items-center gap-2`}><Search size={15} /> Interroger cette base</button>
        </div>
        <MonnaieSource d={d} dark={dark} />
        <div className="flex flex-wrap gap-1 mt-4">
          {onglets.map(([k, l]) => (
            <button key={k} onClick={() => setOnglet(k)} className={`text-xs px-3 py-1.5 rounded-full ${onglet === k
              ? "bg-foret-600 text-white" : dark ? "bg-gray-700 text-gray-300" : "bg-gray-100 text-gray-600"}`}>{l}</button>
          ))}
        </div>
      </div>

      {onglet === "diagnostic" && (
        <div className={carte(dark)}>
          {(p.diagnostics || []).length === 0 ? <p className="text-sm text-emerald-500">Aucun problème détecté.</p> : (
            <ul className="space-y-2">
              {p.diagnostics.map((x, i) => {
                const Icone = ICONE_GRAVITE[x.gravite];
                return (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <Icone size={15} className={`flex-shrink-0 mt-0.5 ${COULEUR_GRAVITE[x.gravite]}`} />
                    <span><span className="font-mono text-xs">{x.table}{x.colonne ? `.${x.colonne}` : ""}</span> — {x.message}</span>
                  </li>
                );
              })}
            </ul>
          )}
          <p className={`${texteDiscret(dark)} mt-3`}>Analyse faite sur un échantillon de 500 lignes par table et quelques comptages, en lecture seule.</p>
        </div>
      )}
      {onglet === "carte" && <div className="space-y-2">{(p.tables || []).map(t => <TableProfil key={t.nom} t={t} dark={dark} />)}</div>}
      {onglet === "relations" && (
        <div className={carte(dark)}>
          {(p.relations || []).length === 0 ? <p className={texteDiscret(dark)}>Aucune relation trouvée.</p> : (
            <ul className="space-y-1.5 text-sm">
              {p.relations.map((x, i) => (
                <li key={i} className="font-mono text-xs">
                  {x.de}.{x.colonne} → {x.vers}.{x.colonne_cible}
                  <span className={`${texteDiscret(dark)} font-sans`}> · {x.deduite ? "déduite des noms" : "déclarée"}{x.orphelins ? ` · ${x.orphelins} orpheline(s)` : ""}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {onglet === "questions" && (
        <div className={carte(dark)}>
          <p className={`${texteDiscret(dark)} mb-3`}>Questions adaptées à cette base. Clique pour la poser dans l'assistant :</p>
          <div className="flex flex-wrap gap-2">
            {(p.suggestions || []).map(s => (
              <button key={s} onClick={() => onInterroger(d, s)} className={`text-xs px-3 py-1.5 rounded-full border ${dark ? "border-gray-600 hover:border-laiton-400" : "border-gray-200 hover:border-laiton-400"}`}>{s}</button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Liste des sources ─────────────────────────────────────────────────
export default function PanelSources({ dark, onInterroger, onAbonnement }) {
  const { appeler, erreur } = useAPI();
  const [liste, setListe] = useState(null);
  const [vue, setVue] = useState("liste");      // liste | nouvelle | <id>
  const charger = useCallback(() => appeler("get", "/sources").then(r => r && setListe(r)), [appeler]);
  useEffect(() => { charger(); }, [charger]);
  // Rafraîchit tant qu'une analyse est en cours
  useEffect(() => {
    if (!liste?.data?.some(s => s.statut === "analyse")) return;
    const t = setTimeout(charger, 3000);
    return () => clearTimeout(t);
  }, [liste, charger]);

  const supprimer = async (s) => {
    if (!window.confirm(`Déconnecter « ${s.nom} » ? Ses identifiants et son analyse seront effacés (ta base n'est pas touchée).`)) return;
    await http.post(`/sources/${s.id}/supprimer`).catch(() => {});
    charger();
  };
  const reanalyser = async (s) => { await http.post(`/sources/${s.id}/analyser`).catch(() => {}); charger(); };
  const parDefaut = async (s) => {
    await http.post("/organisation/source-defaut", { id_source: liste.source_defaut === s.id ? null : s.id }).catch(() => {});
    charger();
  };

  if (vue === "nouvelle") {
    return <NouvelleSource dark={dark} types={liste?.types || []} onAnnuler={() => setVue("liste")}
      onCree={() => { setVue("liste"); charger(); }} />;
  }
  if (typeof vue === "number") {
    return <DetailSource dark={dark} id={vue} onRetour={() => setVue("liste")} onInterroger={onInterroger} />;
  }
  return (
    <div className="space-y-4">
      <div className={`${carte(dark)} flex flex-wrap items-center gap-4`}>
        <div className="flex-1 min-w-[240px]">
          <h2 className={titre(dark)}>Tes données, comprises et interrogeables en français</h2>
          <p className={texteDiscret(dark)}>Branche ta base (PostgreSQL, MySQL, SQL Server) ou tes fichiers Excel / CSV : VoiceBank analyse
            leur structure, en fait le diagnostic, puis répond à tes questions, à la voix ou au clavier.</p>
        </div>
        {liste?.peut_ajouter ? (
          <button onClick={() => setVue("nouvelle")} className={`${boutonPrincipal} flex items-center gap-2`}><Plus size={15} /> Connecter une source</button>
        ) : liste && (
          <button onClick={onAbonnement} className={`${boutonPrincipal} flex items-center gap-2`}><Lock size={15} /> S'abonner pour brancher ses données</button>
        )}
      </div>
      {erreur && <p className="text-sm text-red-500">{erreur}</p>}
      <div className="grid md:grid-cols-2 gap-3">
        {(liste?.data || []).map(s => {
          const Icone = ICONES[s.type] || Database;
          return (
            <div key={s.id} role="group" aria-label={`Source ${s.nom}`} className={`${carte(dark)} !p-4 flex flex-col gap-3 min-w-0`}>
              <div className="flex items-start gap-3">
                <Icone size={20} className="text-laiton-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold truncate flex items-center gap-2">{s.nom}
                    {liste.source_defaut === s.id && <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-laiton-400/20 text-laiton-500 flex-shrink-0">Par défaut</span>}
                  </p>
                  <p className={`${texteDiscret(dark)} truncate`}>{s.libelle_type} · {s.connexion}</p>
                </div>
                {s.statut === "pret" && <Jauge score={s.score_qualite} dark={dark} />}
              </div>
              {s.statut === "analyse" && <p className="text-xs text-laiton-500 flex items-center gap-2"><RefreshCw size={12} className="animate-spin" /> Analyse de la structure et de la qualité…</p>}
              {s.statut === "erreur" && <p className="text-xs text-red-500 flex items-center gap-2"><ShieldAlert size={12} /> {s.erreur}</p>}
              {s.statut === "pret" && s.resume && (
                <p className={texteDiscret(dark)}>{LIB_DOMAINES[s.domaine] || s.domaine} · {s.resume.tables} tables · {Number(s.resume.lignes).toLocaleString("fr-FR")} lignes · {s.resume.donnees_personnelles} données personnelles protégées</p>
              )}
              <div className="flex flex-wrap gap-2 mt-auto">
                <button onClick={() => setVue(s.id)} disabled={s.statut !== "pret" && !s.demo} className={`${boutonSecondaire(dark)} disabled:opacity-50`}>Diagnostic et carte</button>
                <button onClick={() => onInterroger(s)} disabled={s.statut !== "pret"} className={`${boutonSecondaire(dark)} disabled:opacity-50 flex items-center gap-1`}><Search size={12} /> Interroger</button>
                {!s.demo && liste.peut_definir_defaut && s.statut === "pret" && (
                  <button onClick={() => parDefaut(s)} title="Les membres de l'organisation arrivent directement sur cette base"
                    className={`${boutonSecondaire(dark)} flex items-center gap-1`}><Star size={12} className={liste.source_defaut === s.id ? "fill-laiton-400 text-laiton-400" : ""} />
                    {liste.source_defaut === s.id ? "Base par défaut" : "Définir par défaut"}</button>
                )}
                {!s.demo && liste.peut_ajouter && <button onClick={() => reanalyser(s)} className={`${boutonSecondaire(dark)} flex items-center gap-1`}><RefreshCw size={12} /> Réanalyser</button>}
                {!s.demo && liste.peut_ajouter && <button onClick={() => supprimer(s)} className={`${boutonSecondaire(dark)} text-red-500 flex items-center gap-1`}><Trash2 size={12} /> Déconnecter</button>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
