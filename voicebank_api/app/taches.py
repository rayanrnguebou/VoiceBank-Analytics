"""Tâches automatiques : surveillance des bases des organisations, e-mails d'alerte, résumé du matin, rapports PDF,
relecture hebdomadaire de la structure des bases.

Déclenchement :
* chaque heure par GitHub Actions (POST /taches/executer avec la clé TACHES_CLE) : réveille aussi l'API sur
  l'offre gratuite de Render, qui s'endort après 15 minutes sans visite ;
* en secours, par un fil d'exécution de l'API tant qu'elle est éveillée (TACHES_AUTO).
Les deux peuvent se chevaucher sans dégât : un verrou PostgreSQL empêche deux exécutions simultanées, et chaque
étape note sa dernière exécution (une base n'est analysée qu'une fois par heure, un résumé envoyé une fois par jour).
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, courriel, db, rapports, suivi
from .connecteur import service as sources

log = logging.getLogger("voicebank")
VERROU = 7_204_206                    # identifiant du verrou consultatif PostgreSQL
FUSEAU = ZoneInfo("Africa/Douala")
HEURE_MATIN = 7


# ── Mémoire des exécutions ────────────────────────────────────────────

def _derniere(nom: str) -> datetime | None:
    return db.ecrire("SELECT derniere_execution FROM voicebank.taches_planifiees WHERE nom = :n", {"n": nom}).scalar()


def _noter(nom: str, resultat: dict | None = None):
    import json
    db.ecrire("INSERT INTO voicebank.taches_planifiees (nom, derniere_execution, resultat) VALUES "
              "(:n, LOCALTIMESTAMP, CAST(:r AS JSONB)) ON CONFLICT (nom) DO UPDATE SET "
              "derniere_execution = LOCALTIMESTAMP, resultat = EXCLUDED.resultat",
              {"n": nom, "r": json.dumps(resultat or {}, default=str)})


# ── Qui surveiller, qui prévenir ─────────────────────────────────────

def sources_surveillees() -> list:
    """Bases prêtes dont l'organisation a un abonnement actif (ou d'un compte de la plateforme)."""
    return db.ecrire(
        "SELECT s.id_source, s.nom, s.proprietaire, s.id_org, o.nom AS organisation FROM voicebank.sources_donnees s "
        "LEFT JOIN voicebank.organisations o ON o.id_org = s.id_org "
        "JOIN voicebank.utilisateurs p ON p.nom = s.proprietaire AND p.actif "
        "WHERE s.statut = 'pret' AND (s.id_org IS NULL OR (o.actif AND o.abonnement_fin > LOCALTIMESTAMP)) "
        "ORDER BY s.id_source").lignes


def destinataires(id_source: int, preference: str) -> list[tuple[str, str, str | None]]:
    """(compte, adresse e-mail, nom) des membres qui veulent recevoir ce type d'envoi (préférence par défaut sinon)."""
    defaut = {"alertes_critiques": True, "resume_quotidien": True, "rapport_hebdo": False, "rapport_mensuel": True}
    if preference not in defaut:                 # nom de colonne : jamais une valeur venue de l'extérieur
        raise ValueError(f"Préférence inconnue : {preference}")
    r = db.ecrire(
        f"SELECT u.nom, COALESCE(u.email, CASE WHEN u.nom LIKE '%@%' THEN u.nom END) AS email, u.nom_complet, "
        f"COALESCE(p.{preference}, :d) AS veut FROM voicebank.sources_donnees s "
        f"JOIN voicebank.utilisateurs u ON {suivi.MEMBRES_AVEC_ACCES} "
        "LEFT JOIN voicebank.preferences_notifications p ON p.utilisateur = u.nom WHERE s.id_source = :s",
        {"s": id_source, "d": defaut[preference]})
    return [(l.nom, l.email, l.nom_complet) for l in r.lignes if l.veut and l.email]


def _salut(nom: str | None) -> str:
    return f"Bonjour {nom}," if nom else "Bonjour,"


def _montant(v, devise: str) -> str:
    lib = "FCFA" if devise in ("XAF", "XOF") else devise
    return f"{float(v or 0):,.0f}".replace(",", " ") + f" {lib}"


# ── Étapes ───────────────────────────────────────────────────────────

def analyser_source(src, maintenant: datetime, force: bool = False) -> dict:
    """Analyse la base, crée les nouvelles alertes et prévient tout de suite pour les plus graves."""
    nom_tache = f"analyse:{src.id_source}"
    derniere = _derniere(nom_tache)
    if not force and derniere and maintenant - derniere < timedelta(minutes=55):
        return {"ignoree": "analysée il y a moins d'une heure"}
    try:
        res, devise = sources.operations_base(src.id_source, src.proprietaire)
    except sources.SourceRefusee as e:
        _noter(nom_tache, {"erreur": str(e)})
        return {"erreur": str(e)}
    nouvelles = suivi.enregistrer(src.id_source, res["operations"])
    seuil = suivi.seuil_notification(src.id_source)
    a_envoyer = [a for a in nouvelles if a["niveau_risque"] in seuil["niveaux"] and a["score"] >= seuil["score_min"]]
    envoyes = 0
    if a_envoyer:
        details = []
        for a in a_envoyer[:10]:
            r = (a.get("raisons") or [{}])[0]
            details.append((f"{a['niveau_risque']} · {(a.get('date') or '')[:16]}",
                            f"{_montant(a['montant'], devise)} — {r.get('detail') or r.get('variable') or ''}"))
        for _, email, nom in destinataires(src.id_source, "alertes_critiques"):
            courriel.envoyer_en_arriere_plan(email, courriel.Message(
                sujet=f"{len(a_envoyer)} nouvelle(s) alerte(s) {'critique' if len(seuil['niveaux']) == 1 else 'importante'}(s) "
                      f"· {src.nom}",
                titre="Nouvelles opérations à vérifier",
                salutation=_salut(nom),
                paragraphes=[f"La surveillance automatique de « {src.nom} » vient de repérer {len(a_envoyer)} opération(s) "
                             "très atypique(s). Vérifiez-les et indiquez votre verdict (fraude confirmée ou fausse alerte) : "
                             "il améliore les prochaines alertes."],
                details=details, bouton=("Ouvrir les alertes", config.URL_INTERFACE),
                apercu=f"{len(a_envoyer)} opération(s) à vérifier sur {src.nom}",
                note=f"Règle d'envoi : {seuil['raison']}. Vous pouvez choisir vos e-mails dans « Mon organisation » → "
                     "Notifications."))
            envoyes += 1
        suivi.marquer_notifiees([a["id_suivi"] for a in a_envoyer])
    resultat = {"analysees": res["resume"]["analysees"], "nouvelles_alertes": len(nouvelles),
                "notifiees": len(a_envoyer), "emails": envoyes}
    _noter(nom_tache, resultat)
    return resultat


def resume_du_matin(src, maintenant_local: datetime) -> dict:
    """Une fois par jour, après 7 h (heure de Douala) : point sur les alertes de la veille et celles en attente."""
    nom_tache = f"resume:{src.id_source}:{maintenant_local:%Y-%m-%d}"
    if maintenant_local.hour < HEURE_MATIN or _derniere(nom_tache):
        return {}
    depuis = (maintenant_local - timedelta(days=1)).replace(tzinfo=None)
    st = suivi.statistiques(src.id_source, depuis)
    total = suivi.statistiques(src.id_source)
    if not st["total"] and not total["ouvertes"]:
        _noter(nom_tache, {"envoye": False, "raison": "rien à signaler"})
        return {"resume": "rien à signaler"}
    envoyes = 0
    for compte, email, nom in destinataires(src.id_source, "resume_quotidien"):
        a_moi = db.ecrire("SELECT COUNT(*) FROM voicebank.suivi_alertes WHERE id_source = :s AND assigne_a = :u AND statut "
                          "NOT IN ('fraude_confirmee', 'fausse_alerte', 'resolue')", {"s": src.id_source, "u": compte}).scalar()
        courriel.envoyer_en_arriere_plan(email, courriel.Message(
            sujet=f"Résumé du {maintenant_local:%d/%m} · {src.nom} : {st['total']} nouvelle(s) alerte(s), "
                  f"{total['ouvertes']} à traiter",
            titre="Votre point du matin",
            salutation=_salut(nom),
            paragraphes=[f"Voici l'activité de la surveillance de « {src.nom} » sur les dernières 24 heures."],
            details=[("Nouvelles alertes", f"{st['total']} (dont {st['critiques']} critique(s))"),
                     ("Alertes à traiter", str(total["ouvertes"])), ("Qui vous sont assignées", str(a_moi)),
                     ("Fraudes confirmées (24 h)", str(st["fraudes_confirmees"])),
                     ("Fausses alertes (24 h)", str(st["fausses_alertes"]))],
            bouton=("Traiter les alertes", config.URL_INTERFACE),
            apercu=f"{st['total']} nouvelle(s) alerte(s), {total['ouvertes']} à traiter"))
        envoyes += 1
    _noter(nom_tache, {"emails": envoyes})
    return {"resume_emails": envoyes}


def reanalyse_hebdomadaire(src, maintenant_local: datetime) -> dict:
    """Le dimanche (heure de Douala), la structure des bases est relue : nouvelles tables ou colonnes prises en compte
    par l'assistant et les modèles. Les administrateurs sont prévenus si une table ou une colonne a disparu."""
    if maintenant_local.weekday() != 6 or maintenant_local.hour < 2:
        return {}
    nom_tache = f"reanalyse:{src.id_source}:{maintenant_local:%G-W%V}"
    if _derniere(nom_tache):
        return {}
    res = sources.reanalyser(src.id_source, src.proprietaire)
    _noter(nom_tache, res)
    disparus = res.get("tables_supprimees", []) + res.get("colonnes_supprimees", [])
    if disparus:
        for _, email, nom in destinataires(src.id_source, "alertes_critiques"):
            courriel.envoyer_en_arriere_plan(email, courriel.Message(
                sujet=f"Structure modifiée · {src.nom}",
                titre="La structure de votre base a changé",
                salutation=_salut(nom),
                paragraphes=[f"La relecture hebdomadaire de « {src.nom} » montre que des éléments ont disparu. Les questions "
                             "et alertes qui les utilisaient peuvent ne plus fonctionner : vérifiez avec votre équipe "
                             "informatique (renommage, droits du compte de lecture)."],
                details=[("Disparu", x) for x in disparus[:15]] + [("Nouveau", x) for x in
                                                                     (res.get("tables_ajoutees", []) + res.get("colonnes_ajoutees", []))[:10]],
                bouton=("Ouvrir VoiceBank", config.URL_INTERFACE)))
    return {"reanalyse": res or "aucun changement"}


def rapports_periodiques(src, maintenant_local: datetime) -> dict:
    """Le lundi (rapport hebdomadaire) et le 1er du mois (rapport mensuel), après 7 h : PDF joint par e-mail."""
    res = {}
    if maintenant_local.hour < HEURE_MATIN:
        return res
    plan = []
    if maintenant_local.weekday() == 0:
        plan.append(("semaine", "rapport_hebdo", f"rapport_hebdo:{src.id_source}:{maintenant_local:%G-W%V}"))
    if maintenant_local.day == 1:
        plan.append(("mois", "rapport_mensuel", f"rapport_mensuel:{src.id_source}:{maintenant_local:%Y-%m}"))
    for periode, preference, nom_tache in plan:
        if _derniere(nom_tache):
            continue
        dest = destinataires(src.id_source, preference)
        pdfs = {}                                           # un rapport par langue des destinataires
        for _, email, nom in dest:
            langue = courriel.langue_destinataire(email)
            if langue not in pdfs:
                try:
                    pdfs[langue] = rapports.generer(src.id_source, src.proprietaire, periode,
                                                    maintenant_local.replace(tzinfo=None), langue=langue)
                except Exception as e:                  # un rapport raté ne doit pas bloquer les autres tâches
                    log.warning("Rapport %s impossible pour la source %s : %s", periode, src.id_source, e)
                    pdfs[langue] = None
            if not pdfs[langue]:
                continue
            pdf, nom_fichier = pdfs[langue]
            courriel.envoyer_en_arriere_plan(email, courriel.Message(
                sujet=f"Rapport de risque {rapports.PERIODES[periode][0]} · {src.nom}",
                titre=f"Rapport de risque {rapports.PERIODES[periode][0]}",
                salutation=_salut(nom),
                paragraphes=[f"Vous trouverez ci-joint le rapport {rapports.PERIODES[periode][0]} de « {src.nom} » : "
                             "synthèse des alertes, points d'attention, portefeuille de crédits et fiabilité des modèles."],
                bouton=("Ouvrir VoiceBank", config.URL_INTERFACE),
                pieces=[(nom_fichier, pdf, "application/pdf")]))
        _noter(nom_tache, {"destinataires": len(dest)})
        res[preference] = len(dest)
    return res


# ── Exécution ────────────────────────────────────────────────────────

def executer(force: bool = False, maintenant: datetime | None = None) -> dict:
    """Exécute toutes les tâches dues. Retourne un compte rendu (aussi gardé dans taches_planifiees)."""
    from sqlalchemy import text
    debut = time.time()
    maintenant = maintenant or datetime.now()
    local = maintenant.astimezone(FUSEAU) if maintenant.tzinfo else datetime.now(FUSEAU)
    with db.moteur_app.connect() as conn:
        if not conn.execute(text("SELECT pg_try_advisory_lock(:v)"), {"v": VERROU}).scalar():
            return {"deja_en_cours": True}
        try:
            rapport = {"sources": {}}
            for src in sources_surveillees():
                etapes = {}
                for etape in (lambda: analyser_source(src, maintenant.replace(tzinfo=None), force),
                              lambda: resume_du_matin(src, local), lambda: rapports_periodiques(src, local),
                              lambda: reanalyse_hebdomadaire(src, local)):
                    try:
                        etapes.update(etape() or {})
                    except Exception as e:
                        log.exception("Tâche automatique en échec (source %s)", src.id_source)
                        etapes.setdefault("erreurs", []).append(str(e)[:200])
                rapport["sources"][src.id_source] = etapes
            rapport["duree_s"] = round(time.time() - debut, 1)
            _noter("execution", rapport)
            return rapport
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:v)"), {"v": VERROU})
            conn.commit()


def demarrer_en_arriere_plan():
    """Secours quand l'API est éveillée : passe toutes les 15 minutes (chaque étape décide si elle est due)."""
    if not config.TACHES_AUTO:
        return

    def boucle():
        time.sleep(60)
        while True:
            try:
                executer()
            except Exception:
                log.exception("Tâches automatiques : échec de l'exécution")
            time.sleep(15 * 60)
    threading.Thread(target=boucle, daemon=True, name="taches-automatiques").start()
