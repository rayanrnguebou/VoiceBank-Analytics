// VOICEBANK ANALYTICS — Interface React v3
// Auteur : Nguebou Temgoua Rayan
// v3 : connexion sécurisée, corrections de bugs, analyse de transaction IA

import { useState, useEffect, useRef, useCallback } from "react";
import { LienCookies } from "./consentement";
import { PanelRecouvrement } from "./panneaux/Recouvrement";
import { PanelValeur } from "./panneaux/Valeur";
import { ClesApi } from "./panneaux/ClesApi";
import { http, lireSession, deconnexion, messageErreur, appliquerJeton } from "./api";
import EcranAccueil from "./panneaux/Accueil";
import { BandeauAcces, PanelAbonnement, PanelAbonnements } from "./panneaux/Abonnement";
import { LectureSeule } from "./lectureSeule";
import PanelSources from "./panneaux/Connecteur";
import PanelOrganisation, { PanelJournal } from "./panneaux/Organisation";
import { PanelFiches, PanelNotifications } from "./panneaux/Surveillance";
import { PanelOperationsSource, PanelAnalyseSource, PanelCreditSource } from "./panneaux/RisquesSource";
import Demarrage from "./panneaux/Demarrage";
import { useMaintenance, EcranMaintenance, BandeauAnnonce, BandeauReconnexion, IndicateurCalcul, PanelMaintenance } from "./maintenance";
import { FournisseurDevise, useDevise, SelecteurDevise } from "./devise";
import { useSessionActive } from "./session";
import { useAPI } from "./useAPI";
import PanelAlertes from "./panneaux/Alertes";
import { useTableauSource, kpisSource, SelecteurSource, PanelTableauSource } from "./panneaux/TableauSource";
import PanelCredit from "./panneaux/Credit";
import BarreLaterale from "./panneaux/BarreLaterale";
import { PanelApprentissage, PanelFiabilite, PanelAudit } from "./panneaux/Admin";
import { EcranMotDePasseProvisoire, FenetreMotDePasse, PanelComptes } from "./panneaux/Comptes";
import { EcranDoubleAuthObligatoire } from "./panneaux/DoubleAuth";
import { lireAVoixHaute, arreterLecture } from "./ui";
import { ecouterReponse, interpreterReponse } from "./conversation";
import { Mic, Sun, Moon, RefreshCw, Send, Activity, Users, CreditCard, ShieldAlert, Trash2, Square, AlertTriangle, X, Volume2, VolumeX, Menu, MessagesSquare, Timer } from "lucide-react";
import { LANGUE, LOCALE, tx } from "./i18n";
import { PanelGraphiques } from "./graphiques";
import { CLE_STORAGE, MAX_HISTORIQUE, chargerHistorique, sauverHistorique, CarteResultat, PanelHistorique } from "./panneaux/Historique";
import { BoutonMicro } from "./panneaux/Micro";
import { KpiCard, PanelAnalyse, BarreSourceRisque } from "./panneaux/Analyse";
import { PAGE_ETAT } from "./etatService";
import { useFavoris, BarreFavoris } from "./panneaux/Favoris";
import { EcranApprobation } from "./panneaux/Approbation";

export default function App() {
  const [session, setSession] = useState(() => lireSession());

  useEffect(() => {
    const surDeconnexion = () => setSession(null);
    window.addEventListener("voicebank:deconnexion", surDeconnexion);
    return () => window.removeEventListener("voicebank:deconnexion", surDeconnexion);
  }, []);

  const seDeconnecter = useCallback(() => {
    arreterLecture();
    if (session) sessionStorage.removeItem(`${CLE_STORAGE}_${session.utilisateur}`);
    deconnexion();
    setSession(null);
  }, [session]);

  // Notification touchée alors que VoiceBank est déjà ouvert : la demande s'affiche par-dessus, la page reste
  const [approbationSuperposee, setApprobationSuperposee] = useState(null);
  useEffect(() => {
    const sw = typeof navigator !== "undefined" ? navigator.serviceWorker : null;
    if (!sw) return undefined;
    const surMessage = e => { if (e.data?.type === "voicebank-approbation" && e.data.id) setApprobationSuperposee(e.data.id); };
    sw.addEventListener("message", surMessage);
    sw.startMessages?.();
    return () => sw.removeEventListener("message", surMessage);
  }, []);

  // Maintenance : page dédiée pour tous, sauf l'administrateur de la plateforme (qui peut se connecter)
  const maintenance = useMaintenance();
  const [accesAdmin, setAccesAdmin] = useState(false);
  const bloque = maintenance.active && session?.role !== "admin" && !(accesAdmin && !session);

  // Téléphone ouvert depuis la notification « connexion demandée » : écran d'approbation, sans session
  const idApprobation = new URLSearchParams(window.location.search).get("approbation");
  if (idApprobation) return <EcranApprobation idDemande={idApprobation} onFermer={() => window.location.replace("/")} />;

  return (
    <FournisseurDevise>
      {approbationSuperposee && <EcranApprobation key={approbationSuperposee} idDemande={approbationSuperposee} superpose
        onFermer={() => setApprobationSuperposee(null)} />}
      <BandeauReconnexion />
      <IndicateurCalcul />
      {bloque ? <EcranMaintenance etat={maintenance} onAccesAdmin={session ? undefined : () => setAccesAdmin(true)} />
        : !session ? <EcranAccueil onConnecte={setSession} annonce={maintenance.annonce} />
        : session.doitChangerMdp
          ? <EcranMotDePasseProvisoire session={session} onTermine={setSession} onDeconnexion={seDeconnecter} />
        : session.doitConfigurer2fa
          ? <EcranDoubleAuthObligatoire session={session} onTermine={setSession} onDeconnexion={seDeconnecter} />
          : <Tableau key={session.utilisateur} session={session} onDeconnexion={seDeconnecter} onSession={setSession}
              maintenance={maintenance} />}
    </FournisseurDevise>
  );
}

function Tableau({ session, onDeconnexion, onSession, maintenance }) {
  const devise = useDevise();
  const { resteMs, rester } = useSessionActive({ session, onSession, onDeconnexion });
  const [fenetreMdp, setFenetreMdp] = useState(false);
  const [dark, setDark]             = useState(true);
  const [question, setQuestion]     = useState("");
  const [dictee, setDictee]         = useState(false);
  const champQuestionRef            = useRef(null);
  const [historique, setHistorique] = useState(() => chargerHistorique(session.utilisateur));
  const [dashboard, setDashboard]   = useState(null);
  const [onglet, setOnglet]         = useState("assistant");
  const [menuOuvert, setMenuOuvert] = useState(false);
  const [compteurs, setCompteurs]   = useState({ alertes: 0, signalements: 0 });
  const [stats, setStats]           = useState(null);
  const [message, setMessage]       = useState(null);
  const [info, setInfo]             = useState(null);
  const [parle, setParle]           = useState(false);
  // Source interrogée : null = base VoiceBank ; sinon une base / des fichiers de l'organisation
  const [sourceActive, setSourceActive] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("voicebank_source") || "null"); } catch (e) { return null; }
  });
  const [sourcesPretes, setSourcesPretes] = useState([]);
  const [ecoute, setEcoute]         = useState(null);        // null | "attente" | "parole" | "transcription"
  const [conversation, setConversation] = useState(() => {
    try { return localStorage.getItem("voicebank_conversation") !== "non"; } catch (e) { return true; }
  });
  const ecouteRef  = useRef(null);       // contrôle de l'écoute en cours (annuler)
  const poserRef   = useRef(null);       // dernière version de poserQuestion (contexte à jour)
  const ongletRef  = useRef("assistant");
  const [voix, setVoix]             = useState(() => {
    try { return localStorage.getItem("voicebank_voix") !== "non"; } catch (e) { return true; }
  });
  // Deux canaux séparés : le chargement du tableau de bord ne doit jamais bloquer une question.
  const { appeler } = useAPI();
  const { appeler: appelerQuestion, chargement, erreur } = useAPI();
  const estAdmin = session.role === "admin";
  const externe = session.role === "visiteur" || session.role === "client";
  // Administration de la plateforme : l'administrateur, et les visiteurs en essai (démonstration en lecture seule).
  // Les membres d'une organisation cliente ne voient que leur organisation.
  const voitAdmin = estAdmin || session.role === "visiteur";
  const [acces, setAcces] = useState(null);
  const rafraichirAcces = useCallback(() => {
    http.get("/auth/moi").then(r => setAcces(r.data.acces)).catch(() => {});
  }, []);
  useEffect(() => { rafraichirAcces(); }, [rafraichirAcces, session.role]);
  useEffect(() => {
    const surExpiration = () => rafraichirAcces();
    window.addEventListener("voicebank:acces-expire", surExpiration);
    return () => window.removeEventListener("voicebank:acces-expire", surExpiration);
  }, [rafraichirAcces]);

  // Retour de la page de paiement : ?paiement=<référence> → vérification par le serveur
  useEffect(() => {
    const ref = new URLSearchParams(window.location.search).get("paiement");
    if (!ref) return;
    let essais = 0, fini = false;
    const verifier = async () => {
      try {
        const { data } = await http.get(`/abonnement/verifier/${encodeURIComponent(ref)}`);
        if (data.statut === "paye") {
          fini = true;
          if (data.jeton) onSession(appliquerJeton(data.jeton));
          setInfo(tx("Paiement confirmé : abonnement {formule} actif jusqu'au {x}. Merci !", { formule: data.formule, x: new Date(data.abonnement_fin).toLocaleDateString(LOCALE) }));
          rafraichirAcces();
        } else if (data.statut === "en_attente" && ++essais < 10) {
          setInfo(tx("Paiement en cours de confirmation…"));
          setTimeout(verifier, 3000);
          return;
        } else {
          fini = true;
          setMessage(data.statut === "en_attente" ? tx("Paiement pas encore confirmé. Il s'activera automatiquement dès réception.")
            : tx("Le paiement n'a pas abouti. Tu peux réessayer depuis la page Abonnement."));
          if (data.statut === "en_attente") setInfo(null);
        }
      } catch (e) {
        fini = true;
        setMessage(messageErreur(e));
      }
      if (fini) window.history.replaceState(null, "", window.location.pathname);
    };
    verifier();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const arreterEcoute = useCallback(() => {
    ecouteRef.current?.annuler?.();
    ecouteRef.current = null;
    setEcoute(null);
  }, []);

  const basculerVoix = () => {
    setVoix(v => {
      try { localStorage.setItem("voicebank_voix", v ? "non" : "oui"); } catch (e) { /* rien */ }
      if (v) { arreterLecture(); arreterEcoute(); }
      return !v;
    });
  };

  const basculerConversation = () => {
    setConversation(c => {
      try { localStorage.setItem("voicebank_conversation", c ? "non" : "oui"); } catch (e) { /* rien */ }
      if (c) arreterEcoute();
      return !c;
    });
  };

  // Mode conversation : la relance (« Veux-tu voir… ? ») vient d'être lue, on écoute la réponse.
  const ecouterLaReponse = async (relance, essai = 1) => {
    if (ongletRef.current !== "assistant") return;
    const controle = {};
    ecouteRef.current = controle;
    setEcoute("attente");
    let texte = "";
    try {
      texte = await ecouterReponse({
        controle,
        onParole: () => setEcoute("parole"),
        onTexteEnDirect: t => setQuestion(t),
        onTranscription: () => setEcoute("transcription"),
      });
    } catch (e) {
      setMessage(e.message);
    }
    if (ecouteRef.current !== controle) return;     // écoute annulée entre-temps
    ecouteRef.current = null;
    setEcoute(null);
    const reponse = interpreterReponse(texte);
    if (reponse.type === "vide") { setQuestion(""); return; }
    if (reponse.type === "non") { setQuestion(""); lireAVoixHaute(tx("D'accord. Je reste à ta disposition.")); return; }
    if (reponse.type === "oui") {
      setQuestion("");
      if (relance?.question) poserRef.current(relance.question);
      else if (essai === 1) lireAVoixHaute(tx("Je t'écoute."), { onFin: () => ecouterLaReponse(null, 2) });
      return;
    }
    poserRef.current(reponse.texte);
  };

  useEffect(() => {
    const surLecture = e => setParle(!!e.detail);
    window.addEventListener("voicebank:lecture", surLecture);
    return () => { window.removeEventListener("voicebank:lecture", surLecture); arreterLecture(); };
  }, []);

  useEffect(() => {
    appeler("get", "/dashboard").then(res => { if (res?.data) setDashboard(res.data); });
    appeler("get", "/stats/global").then(res => { if (res?.data) setStats(res.data); });
  }, [appeler]);

  const allerA = useCallback(id => {
    setOnglet(id); ongletRef.current = id; window.scrollTo(0, 0);
    if (id !== "assistant") arreterEcoute();
  }, [arreterEcoute]);
  useEffect(() => () => ecouteRef.current?.annuler?.(), []);

  // Compteurs de la barre latérale : alertes à traiter, signalements en attente (admin)
  // Base connectée choisie : uniquement ses alertes ouvertes, jamais celles de la démonstration.
  const idSourceAlertes = sourceActive?.id || 0;
  const rafraichirCompteurs = useCallback(() => {
    if (idSourceAlertes) {
      http.get(`/sources/${idSourceAlertes}/suivi`, { silencieux: true })
        .then(r => setCompteurs(c => ({ ...c, alertes: Number(r.data?.statistiques?.ouvertes) || 0 })))
        .catch(() => setCompteurs(c => ({ ...c, alertes: 0 })));
    } else if (!externe) {
      appeler("get", "/alertes/stats").then(r => r && setCompteurs(c => ({ ...c, alertes: Number(r.a_traiter) || 0 })));
    } else setCompteurs(c => ({ ...c, alertes: 0 }));
    if (voitAdmin) appeler("get", "/signalements?statut=Ouvert&limit=200")
      .then(r => r && setCompteurs(c => ({ ...c, signalements: r.total || 0 })));
  }, [appeler, voitAdmin, idSourceAlertes, externe]);
  useEffect(() => { rafraichirCompteurs(); }, [rafraichirCompteurs]);

  useEffect(() => { sauverHistorique(session.utilisateur, historique); }, [historique, session.utilisateur]);
  useEffect(() => { if (erreur) setMessage(erreur); }, [erreur]);

  const poserQuestion = async (texte, sourceForcee) => {
    const q = (texte ?? question).trim();
    if (!q || chargement) return;
    const src = sourceForcee !== undefined ? sourceForcee : sourceActive;
    if (ecouteRef.current) arreterEcoute();
    setQuestion("");
    setMessage(null);
    // Contexte = dernière question (moins de 15 min) : permet « et à Douala ? ».
    // C'est l'API qui décide si la nouvelle question est une suite ou une question complète.
    const derniere = historique[0];
    const contexte = derniere && derniere.sql && Date.now() - new Date(derniere.timestamp).getTime() < 15 * 60 * 1000
      ? { question: derniere.question, sql: derniere.sql } : null;
    // Base de l'organisation (connecteur) ou base VoiceBank principale
    const res = src
      ? await appelerQuestion("post", `/sources/${src.id}/question`, { texte: q, devise: devise.code }, { timeout: 90000 })
      : await appelerQuestion("post", "/vocal/question", { texte: q, langue: LANGUE, devise: devise.code,
          contexte: contexte && !historique[0]?.nom_source ? contexte : null });
    if (!res) return;  // le message d'erreur est affiché via `erreur`
    if (externe) setAcces(a => a ? { ...a, questions_jour: a.questions_jour + 1 } : a);
    setHistorique(prev => [{
      id: Date.now(), timestamp: new Date().toISOString(),
      question: q, sql: res.sql, source: res.source,
      colonnes: res.colonnes, total: res.total,
      data: res.data, duree_ms: res.duree_ms, avertissement: res.avertissement || null,
      resume: res.resume || null, commentaire: res.commentaire || null, relance: res.relance || null,
      suite: !!res.suite, question_precedente: res.question_precedente || null, nom_source: src ? src.nom : null,
      id_source: src ? src.id : 0,
      devise: res.devise || "XAF", colonnes_monetaires: res.colonnes_monetaires || [],
    }, ...prev].slice(0, MAX_HISTORIQUE));
    // Le résumé (affiché) est lu en premier, puis l'analyse plus poussée et la relance
    // (uniquement à l'oral). En mode conversation, on écoute ensuite la réponse, sans clic.
    if (voix && res.resume) {
      const relance = res.relance;
      lireAVoixHaute([res.resume, res.commentaire, relance?.texte], {
        onFin: conversation && relance ? () => ecouterLaReponse(relance) : undefined,
      });
    }
  };
  poserRef.current = poserQuestion;
  const favoris = useFavoris(true);

  const choisirSource = useCallback(async (s, question, garderPage = false) => {
    let choix = null;
    if (s && !s.demo) {
      choix = { id: s.id, nom: s.nom, suggestions: s.profil?.suggestions || [] };
      if (!choix.suggestions.length) {
        try { choix.suggestions = (await http.get(`/sources/${s.id}`)).data.data.profil?.suggestions || []; } catch (e) { /* rien */ }
      }
    }
    setSourceActive(choix);
    try { sessionStorage.setItem("voicebank_source", JSON.stringify(choix)); } catch (e) { /* rien */ }
    if (!garderPage) { setOnglet("assistant"); ongletRef.current = "assistant"; window.scrollTo(0, 0); }
    if (question) setTimeout(() => poserRef.current(question, choix), 0);
  }, []);

  useEffect(() => {
    http.get("/sources").then(r => setSourcesPretes(r.data.data.filter(x => !x.demo && x.statut === "pret"))).catch(() => {});
  }, [onglet]);

  // Base par défaut de l'organisation : appliquée à l'arrivée, tant que la personne n'a rien choisi elle-même
  useEffect(() => {
    let dejaChoisi = false;
    try { dejaChoisi = sessionStorage.getItem("voicebank_source") !== null; } catch (e) { /* rien */ }
    if (!dejaChoisi && acces?.source_defaut) choisirSource(acces.source_defaut, null, true);
  }, [acces?.source_defaut?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const supprimerItem = (id) => setHistorique(prev => prev.filter(item => item.id !== id));
  const toutEffacer = () => {
    if (window.confirm(tx("Supprimer tout l'historique ?"))) setHistorique([]);
  };

  const tableauSource = useTableauSource(sourceActive, devise.code);
  const kpis = sourceActive ? kpisSource(tableauSource.donnees, devise) : dashboard ? [
    { titre: tx("Clients"),        valeur: Number(dashboard.total_clients || 0).toLocaleString(LOCALE),       icone: Users,       couleur: "#1F654D" },
    { titre: tx("Transactions"),   valeur: Number(dashboard.total_transactions || 0).toLocaleString(LOCALE),   icone: Activity,    couleur: "#3E6FB0" },
    { titre: tx("Fraudes"),        valeur: Number(dashboard.total_fraudes || 0).toLocaleString(LOCALE),        icone: ShieldAlert, couleur: "#EF4444" },
    { titre: tx("Crédits en cours"), valeur: Number(dashboard.encours_credit_fcfa || 0) > 0
        ? devise.formater(dashboard.encours_credit_fcfa, { compact: true }) : "--",
      icone: CreditCard, couleur: "#A9852A" },
  ] : [];

  const suggestions = sourceActive?.suggestions?.length ? sourceActive.suggestions.slice(0, 6) : [
    tx("Top 10 clients par solde"),
    tx("Crédits en défaut"),
    tx("Transactions frauduleuses par banque"),
    tx("Alertes critiques"),
    tx("Clients diaspora France"),
    tx("Volume transactions par ville"),
  ];

  const PAGES = {
    assistant:     { titre: tx("Assistant vocal"),        sousTitre: tx("Pose une question sur tes données, à la voix ou au clavier") },
    donnees:       { titre: tx("Mes données"),            sousTitre: tx("Brancher, diagnostiquer et interroger les données de ton organisation") },
    tableau:       { titre: tx("Tableau de bord"),         sousTitre: sourceActive ? tx("Vue d'ensemble de « {nom} », calculée d'après sa structure", { nom: sourceActive.nom })
                                                                       : tx("Vue d'ensemble des clients, des transactions et des crédits") },
    alertes:       { titre: tx("Alertes de fraude"),       sousTitre: sourceActive ? tx("Opérations atypiques de « {nom} »", { nom: sourceActive.nom }) : tx("Alertes à vérifier et décisions prises") },
    analyse:       { titre: tx("Analyse de transaction"),  sousTitre: tx("Estimer le risque de fraude d'une opération") },
    credit:        { titre: tx("Score de crédit"),         sousTitre: sourceActive ? tx("Portefeuille de crédits de « {nom} »", { nom: sourceActive.nom }) : tx("Risque de défaut d'une demande ou d'un crédit en cours") },
    recouvrement:  { titre: tx("Recouvrement"),            sousTitre: tx("Crédits en retard de « {nom} » : qui relancer d'abord, promesses et paiements", { nom: sourceActive?.nom || tx("Démonstration VoiceBank") }) },
    api:           { titre: tx("Logiciel bancaire"),       sousTitre: tx("Brancher votre logiciel : score de fraude en temps réel avant chaque opération") },
    valeur:        { titre: tx("Valeur créée"),            sousTitre: tx("Argent récupéré, fraude évitée et temps gagné, chiffres à l'appui") },
    historique:    { titre: tx("Historique"),              sousTitre: tx("Questions de la session et rapport PDF") },
    modeles:       { titre: tx("Fiche des modèles"),       sousTitre: sourceActive ? tx("Modèles d'IA appris sur « {nom} » : données, fiabilité, dérive", { nom: sourceActive.nom }) : tx("Modèles d'IA de la démonstration : données, fiabilité, limites") },
    journal:       { titre: tx("Journal de l'organisation"), sousTitre: tx("Traitement des alertes et activité des membres") },
    notifications: { titre: tx("Notifications"),           sousTitre: tx("Alertes, résumé du matin et rapports PDF reçus par e-mail") },
    apprentissage: { titre: tx("Apprentissage"),           sousTitre: tx("Réponses signalées et corrections enregistrées") },
    fiabilite:     { titre: tx("Fiabilité"),               sousTitre: tx("Taux de bonnes réponses sur les questions de référence") },
    audit:         { titre: tx("Audit"),                   sousTitre: tx("Qui a fait quoi, et quand") },
    comptes:       { titre: tx("Comptes"),                 sousTitre: tx("Qui peut se connecter, avec quels droits") },
    abonnement:    { titre: tx("Abonnement"),              sousTitre: tx("Formules, paiement et factures") },
    maintenance:   { titre: tx("Maintenance"),             sousTitre: tx("Mettre le service en maintenance et prévenir les utilisateurs") },
    organisation:  { titre: acces?.type_organisation === "particulier" ? tx("Mon compte") : tx("Mon organisation"),
                     sousTitre: acces?.organisation ? tx("{organisation} : membres et abonnement partagé", { organisation: acces.organisation }) : tx("Membres et abonnement partagé") },
    abonnements:   { titre: tx("Abonnements"),             sousTitre: tx("Visiteurs, abonnés et paiements reçus") },
  };
  // Essai ou abonnement échu : seule la page Abonnement reste accessible.
  const page = acces?.expire ? "abonnement" : PAGES[onglet] ? onglet : "assistant";

  return (
    <div className={`min-h-screen flex ${dark ? "bg-gray-950 text-gray-100" : "bg-gray-50 text-gray-900"}`}>
      <BarreLaterale
        page={page} allerA={allerA} estAdmin={estAdmin} voitAdmin={voitAdmin} externe={externe} session={session} acces={acces}
        nbHistorique={historique.length} compteurs={compteurs}
        ouverte={menuOuvert} onFermer={() => setMenuOuvert(false)} onDeconnexion={onDeconnexion}
        onMotDePasse={() => setFenetreMdp(true)}
      />
      {resteMs !== null && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4">
          <div role="alertdialog" aria-modal="true" aria-labelledby="titre-inactivite"
            className={`w-full max-w-sm rounded-2xl border p-6 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200"}`}>
            <h2 id="titre-inactivite" className="text-lg font-bold flex items-center gap-2 mb-2"><Timer size={18} />{" "}{tx("Toujours là ?")}</h2>
            <p className={`text-sm mb-4 ${dark ? "text-gray-300" : "text-gray-600"}`}>
              {tx("Sans activité, tu seras déconnecté dans")}{" "}<strong>{tx("{x} s", { x: Math.ceil(resteMs / 1000) })}</strong>{tx(", pour protéger les données des clients.")}
            </p>
            <div className="flex gap-2">
              <button onClick={rester} autoFocus className="px-4 py-2 bg-foret-600 hover:bg-foret-700 text-white text-sm font-semibold rounded-xl">{tx("Rester connecté")}</button>
              <button onClick={onDeconnexion} className={`px-4 py-2 rounded-xl text-sm ${dark ? "hover:bg-gray-700" : "hover:bg-gray-100"}`}>{tx("Se déconnecter")}</button>
            </div>
          </div>
        </div>
      )}
      {fenetreMdp && (
        <FenetreMotDePasse dark={dark} session={session} onTermine={onSession} onFermer={() => setFenetreMdp(false)} />
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        {/* ── Barre du haut ─────────────────────────────── */}
        <header className={`sticky top-0 z-20 border-b px-4 sm:px-8 py-3 flex items-center gap-3 backdrop-blur-md ${
          dark ? "bg-gray-950/85 border-gray-800" : "bg-gray-50/85 border-gray-200"}`}>
          <button onClick={() => setMenuOuvert(true)} aria-label={tx("Ouvrir le menu")}
            className={`lg:hidden p-2 rounded-lg ${dark ? "hover:bg-gray-800" : "hover:bg-gray-200"}`}>
            <Menu size={18} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold leading-tight truncate">{PAGES[page].titre}</h1>
            <p className={`text-xs truncate ${dark ? "text-gray-400" : "text-gray-500"}`}>{PAGES[page].sousTitre}</p>
          </div>
          {parle && (
            <button onClick={arreterLecture} aria-label={tx("Arrêter la lecture")} title={tx("Arrêter la lecture")}
              className={`flex items-center gap-2 pl-2.5 pr-3 py-1.5 rounded-full text-xs font-medium ${
                dark ? "bg-laiton-400/15 text-laiton-300 hover:bg-laiton-400/25" : "bg-laiton-200/70 text-laiton-600 hover:bg-laiton-200"}`}>
              <span className="flex items-end gap-0.5 h-3" aria-hidden="true">
                {[0, 1, 2].map(i => <span key={i} className="w-0.5 bg-current rounded-full animate-pulse"
                  style={{ height: `${[60, 100, 70][i]}%`, animationDelay: `${i * 150}ms` }} />)}
              </span>
              <span className="hidden sm:inline">{tx("Lecture")}</span>
              <Square size={11} fill="currentColor" />
            </button>
          )}
          {ecoute && (
            <button onClick={arreterEcoute} aria-label={tx("Arrêter l'écoute")} title={tx("Arrêter l'écoute")}
              className="flex items-center gap-2 pl-2.5 pr-3 py-1.5 rounded-full text-xs font-medium bg-red-500/15 text-red-500 hover:bg-red-500/25">
              <span className="relative flex w-2 h-2" aria-hidden="true">
                <span className="absolute inset-0 rounded-full bg-red-500 animate-ping opacity-75" />
                <span className="relative w-2 h-2 rounded-full bg-red-500" />
              </span>
              <span>{ecoute === "transcription" ? tx("Je réfléchis…") : ecoute === "parole" ? tx("Je t'écoute…") : tx("À toi…")}</span>
              <Square size={11} fill="currentColor" />
            </button>
          )}
          <SelecteurDevise compact className={`text-xs px-2 py-1.5 rounded-lg border outline-none ${dark
            ? "bg-gray-900 border-gray-700 text-gray-200" : "bg-white border-gray-200 text-gray-700"}`} />
          {voix && (
            <button onClick={basculerConversation} aria-pressed={conversation}
              aria-label={conversation ? tx("Désactiver le mode conversation") : tx("Activer le mode conversation")}
              title={conversation ? tx("Mode conversation : je t'écoute après chaque réponse") : tx("Mode conversation désactivé")}
              className={`p-2 rounded-lg transition-colors ${conversation
                ? (dark ? "text-laiton-300 hover:bg-gray-800" : "text-laiton-600 hover:bg-gray-200")
                : (dark ? "text-gray-500 hover:bg-gray-800" : "text-gray-400 hover:bg-gray-200")}`}>
              <MessagesSquare size={17} />
            </button>
          )}
          <button onClick={basculerVoix} aria-label={voix ? tx("Désactiver la réponse vocale") : tx("Activer la réponse vocale")}
            title={voix ? tx("Réponse vocale activée") : tx("Réponse vocale désactivée")}
            className={`p-2 rounded-lg transition-colors ${dark ? "text-gray-300 hover:bg-gray-800" : "text-gray-600 hover:bg-gray-200"}`}>
            {voix ? <Volume2 size={17} /> : <VolumeX size={17} />}
          </button>
          <button onClick={() => setDark(!dark)} aria-label={tx("Changer de thème")} title={dark ? tx("Thème clair") : tx("Thème sombre")}
            className={`p-2 rounded-lg transition-colors ${dark ? "text-gray-300 hover:bg-gray-800" : "text-gray-600 hover:bg-gray-200"}`}>
            {dark ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </header>

        <LectureSeule.Provider value={externe}>
        <main className="w-full max-w-5xl mx-auto px-4 sm:px-8 py-6 flex-1">
          {maintenance?.active && estAdmin && (
            <div role="status" className="mb-4 px-4 py-3 rounded-xl border border-amber-500/50 bg-amber-500/10 text-amber-500 text-sm flex flex-wrap items-center gap-2">
              <strong>{tx("Maintenance en cours :")}</strong>{" "}{tx("les utilisateurs voient la page de maintenance, toi seul as accès.")}
              <button onClick={() => allerA("maintenance")} className="underline">{tx("Gérer")}</button>
            </div>
          )}
          <BandeauAnnonce annonce={maintenance?.annonce} sombre={dark} />
          {page !== "abonnement" && <BandeauAcces acces={acces} dark={dark} onChoisir={() => allerA("abonnement")} />}
          {info && (
            <div role="status" className="mb-4 flex items-start gap-2 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 text-sm">
              <span className="flex-1">{info}</span>
              <button onClick={() => setInfo(null)} aria-label={tx("Fermer")}><X size={14} /></button>
            </div>
          )}
          {message && (
            <div role="alert" className="mb-4 flex items-start gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-500 text-sm">
              <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" />
              <span className="flex-1">{message}</span>
              <button onClick={() => setMessage(null)} aria-label={tx("Fermer")}><X size={14} /></button>
            </div>
          )}

          {page === "assistant" && (
            <>
              {acces?.role_org === "admin" && acces?.type_organisation === "organisation" && (
                <Demarrage dark={dark} utilisateur={session.utilisateur} acces={acces} nbSources={sourcesPretes.length}
                  nbQuestions={historique.length} allerA={allerA} />
              )}
              {kpis.length > 0 && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
                  {kpis.map((k, i) => <KpiCard key={i} {...k} dark={dark} />)}
                </div>
              )}
              {/* ── Zone saisie ──────────────────────────────── */}
              <div className={`rounded-2xl border p-5 mb-6 ${dark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200 shadow-sm"}`}>
                {(sourcesPretes.length > 0 || sourceActive) && (
                  <div className="mb-4">
                    <SelecteurSource dark={dark} sourceActive={sourceActive} sourcesPretes={sourcesPretes} onChoisir={s => choisirSource(s)} />
                  </div>
                )}
                <div className="flex items-center gap-4 mb-4">
                  <BoutonMicro
                    onDebut={() => { arreterEcoute(); arreterLecture(); setMessage(null); setQuestion(""); setDictee(true); }}
                    onTexteEnDirect={texte => setQuestion(texte)}
                    onTranscription={texte => {
                      // Le texte final remplace l'aperçu ; on laisse l'utilisateur le relire puis valider.
                      setDictee(false);
                      setQuestion(texte);
                      setTimeout(() => champQuestionRef.current?.focus(), 0);
                    }}
                    onErreur={msg => { setDictee(false); setMessage(msg); }}
                    dark={dark}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex gap-2">
                      <input
                        ref={champQuestionRef}
                        aria-label={tx("Question")}
                        value={question}
                        onChange={e => { if (ecouteRef.current) arreterEcoute(); setQuestion(e.target.value); }}
                        onKeyDown={e => e.key === "Enter" && poserQuestion()}
                        placeholder={dictee || ecoute ? tx("Je t'écoute…") : tx("Pose ta question en français...")}
                        maxLength={500}
                        className={`flex-1 min-w-0 px-4 py-3 rounded-xl border text-sm outline-none transition-all ${
                          dark ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400 focus:border-foret-500"
                               : "bg-gray-50 border-gray-200 text-gray-900 focus:border-foret-500"
                        }`}
                      />
                      <button onClick={() => poserQuestion()} disabled={chargement || !question.trim()} aria-label={tx("Envoyer")}
                        className="px-4 py-3 bg-foret-600 hover:bg-foret-700 text-white rounded-xl transition-all disabled:opacity-50">
                        {chargement ? <RefreshCw size={15} className="animate-spin" /> : <Send size={15} />}
                      </button>
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {suggestions.map(s => (
                    <button key={s} onClick={() => poserQuestion(s)} disabled={chargement}
                      className={`text-xs px-3 py-1.5 rounded-full border transition-all hover:scale-105 disabled:opacity-50 ${
                        dark ? "border-gray-600 text-gray-300 hover:border-foret-500 hover:text-foret-400"
                             : "border-gray-200 text-gray-600 hover:border-foret-400 hover:text-foret-600"
                      }`}>
                      {s}
                    </button>
                  ))}
                </div>
                <BarreFavoris favoris={favoris} idSource={sourceActive?.id || 0} onPoser={q => poserQuestion(q)} desactive={chargement} dark={dark} />
              </div>

              {/* ── Résultats des questions ───────────────────── */}
              {historique.length > 0 ? (
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className={`text-sm font-bold ${dark ? "text-white" : "text-gray-900"}`}>
                      {tx("Résultats ({length})", { length: historique.length })}
                    </h2>
                    <button onClick={toutEffacer}
                      className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all ${
                        dark ? "text-gray-400 hover:bg-gray-700" : "text-gray-500 hover:bg-gray-100"
                      }`}>
                      <Trash2 size={12} />{" "}{tx("Tout effacer")}
                    </button>
                  </div>
                  {historique.slice(0, 5).map(item => (
                    <CarteResultat key={item.id} item={item} dark={dark} onSupprimer={supprimerItem} role={session.role}
                      favori={!!favoris.trouve(item.question, item.id_source)}
                      onFavori={() => favoris.basculer(item.question, item.id_source, item.devise)} />
                  ))}
                  {historique.length > 5 && (
                    <button onClick={() => allerA("historique")}
                      className={`text-xs mb-2 ${dark ? "text-foret-400" : "text-foret-600"}`}>
                      {tx("Voir les {x} autres dans l'historique", { x: historique.length - 5 })}
                    </button>
                  )}
                </div>
              ) : (
                <div className={`text-center py-16 ${dark ? "text-gray-500" : "text-gray-400"}`}>
                  <Mic size={40} className="mx-auto mb-3 opacity-30" />
                  <p className="text-sm">{tx("Pose une question vocale ou texte pour voir les résultats")}</p>
                  <p className="text-xs mt-1">{tx("Les résultats s'accumulent ici avec leurs graphiques")}</p>
                </div>
              )}

            </>
          )}
          {page === "tableau" && (
            <>
              {(sourcesPretes.length > 0 || sourceActive) && (
                <div className="mb-4">
                  <SelecteurSource dark={dark} sourceActive={sourceActive} sourcesPretes={sourcesPretes} onChoisir={s => choisirSource(s, null, true)} />
                </div>
              )}
              {kpis.length > 0 && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
                  {kpis.map((k, i) => <KpiCard key={i} {...k} dark={dark} />)}
                </div>
              )}
              {sourceActive
                ? <PanelTableauSource dark={dark} etat={tableauSource} devise={devise} />
                : stats
                  ? <PanelGraphiques dark={dark} stats={stats} />
                  : <p className={`text-sm ${dark ? "text-gray-500" : "text-gray-400"}`}>{tx("Statistiques indisponibles.")}</p>}
            </>
          )}
          {page === "donnees"    && <PanelSources dark={dark} onInterroger={choisirSource} onAbonnement={() => allerA("abonnement")} />}
          {["alertes", "analyse", "credit", "recouvrement", "valeur", "api"].includes(page) && (
            <BarreSourceRisque dark={dark} sourceActive={sourceActive} sourcesPretes={sourcesPretes} externe={externe}
              onChoisir={s => choisirSource(s, null, true)} onMesDonnees={() => allerA("donnees")} />
          )}
          {page === "alertes"    && (sourceActive ? <PanelOperationsSource key={sourceActive.id} source={sourceActive} dark={dark} onChange={rafraichirCompteurs} />
                                                  : <PanelAlertes dark={dark} onChange={rafraichirCompteurs} />)}
          {page === "analyse"    && (sourceActive ? <PanelAnalyseSource key={sourceActive.id} source={sourceActive} dark={dark} />
                                                  : <PanelAnalyse dark={dark} />)}
          {page === "api"        && <ClesApi key={sourceActive?.id || 0} source={sourceActive || { id: 0 }} dark={dark} onMesDonnees={() => allerA("donnees")} />}
          {page === "credit"     && (sourceActive ? <PanelCreditSource key={sourceActive.id} source={sourceActive} dark={dark} />
                                                  : <PanelCredit dark={dark} />)}
          {page === "recouvrement" && <PanelRecouvrement key={sourceActive?.id || 0} source={sourceActive} dark={dark} onValeur={() => allerA("valeur")} />}
          {page === "valeur"     && <PanelValeur key={sourceActive?.id || 0} source={sourceActive} dark={dark} />}
          {page === "modeles"    && <PanelFiches key={sourceActive ? sourceActive.id : 0} source={sourceActive} dark={dark} />}
          {page === "notifications" && <PanelNotifications dark={dark} />}
          {page === "historique" && (
            <PanelHistorique historique={historique} dark={dark} onSupprimerItem={supprimerItem} onToutEffacer={toutEffacer} />
          )}
          {voitAdmin && page === "apprentissage" && <PanelApprentissage dark={dark} onChange={rafraichirCompteurs} />}
          {voitAdmin && page === "fiabilite"     && <PanelFiabilite dark={dark} />}
          {voitAdmin && page === "audit"         && <PanelAudit dark={dark} />}
          {voitAdmin && page === "comptes"       && <PanelComptes dark={dark} session={session} />}
          {externe && page === "abonnement"      && <PanelAbonnement dark={dark} acces={acces} utilisateur={session.utilisateur} />}
          {externe && page === "organisation"    && <PanelOrganisation dark={dark} onAbonnement={() => allerA("abonnement")} />}
          {externe && page === "journal"         && <PanelJournal dark={dark} />}
          {estAdmin && page === "abonnements"    && <PanelAbonnements dark={dark} />}
          {estAdmin && page === "maintenance"    && <PanelMaintenance dark={dark} utilisateur={session.utilisateur} />}
        </main>
        </LectureSeule.Provider>

        <footer className={`px-4 sm:px-8 py-4 text-xs ${dark ? "text-gray-600" : "text-gray-400"}`}>
          {tx("© {x} VoiceBank Analytics — Rayan Nguebou Temgoua", { x: new Date().getFullYear() })}
          {" · "}<a href={`/confidentialite/${LANGUE === "en" ? "#en" : ""}`} target="_blank" rel="noopener noreferrer" className="hover:underline">{tx("Politique de confidentialité")}</a>
          {" · "}<LienCookies />
          {PAGE_ETAT && <>{" · "}<a href={PAGE_ETAT} target="_blank" rel="noopener noreferrer" className="hover:underline">{tx("État du service")}</a></>}
        </footer>
      </div>
    </div>
  );
}
