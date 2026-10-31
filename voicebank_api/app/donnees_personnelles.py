"""Droits sur les données personnelles (loi camerounaise n° 2024/017 du 23 décembre 2024) : accès (export),
effacement d'un compte, durées de conservation.

* **Export** : tout ce que VoiceBank garde sur le compte, dans un fichier JSON lisible.
* **Effacement** : profil, questions posées, préférences, double authentification, appareils, accès et bases de
  données (si le compte est seul dans son organisation) sont supprimés ; le compte reçoit un pseudonyme
  (« efface-… ») et son adresse e-mail est libérée. Sont conservés, au nom d'obligations légales : les paiements
  (10 ans, comptabilité OHADA) avec les informations de facturation correspondantes, et le journal d'audit (5 ans,
  traçabilité dans le secteur financier).
* **Conservation** : chaque jour, `voicebank.appliquer_conservation()` supprime ce qui a dépassé sa durée, et les
  essais gratuits terminés depuis plus de 90 jours sans abonnement sont effacés.
"""
import logging
import secrets
from datetime import datetime

import bcrypt
from sqlalchemy import text

from . import audit, db

log = logging.getLogger("voicebank")
ESSAI_OUBLIE_JOURS = 90
CONSERVATION = {
    "questions": "12 mois", "journal_audit": "5 ans", "paiements": "10 ans", "appareils_connus": "180 jours",
    "sessions": "180 jours", "appels_api_du_logiciel_bancaire": "90 jours",
    "tentatives_de_connexion": "24 heures", "essai_sans_abonnement": f"{ESSAI_OUBLIE_JOURS} jours après la fin de l'essai",
}


class EffacementRefuse(Exception):
    """Message affichable."""


def _lignes(conn, sql: str, **p) -> list[dict]:
    res = conn.execute(text(sql), p)
    return [{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in r._mapping.items()} for r in res]


def exporter(nom: str) -> dict:
    """Tout ce qui concerne le compte (sans mot de passe, secret de double authentification ni identifiants de base)."""
    with db.moteur_app.connect() as c:
        compte = _lignes(c, "SELECT u.nom AS identifiant, u.email, u.nom_complet, u.profil, u.role, u.role_org, u.langue, "
                            "u.actif, u.date_creation, u.derniere_connexion, u.date_modif_mdp, u.essai_fin, "
                            "u.abonnement_fin, u.formule, o.nom AS organisation, o.type_org "
                            "FROM voicebank.utilisateurs u LEFT JOIN voicebank.organisations o ON o.id_org = u.id_org "
                            "WHERE u.nom = :n", n=nom)
        if not compte:
            raise EffacementRefuse("Compte introuvable")
        return {
            "export_du": datetime.now().isoformat(timespec="seconds"),
            "responsable_du_traitement": "VoiceBank Analytics — Rayan Nguebou Temgoua",
            "compte": compte[0],
            "double_authentification": (_lignes(c, "SELECT active, date_activation FROM voicebank.double_authentification "
                                                   "WHERE utilisateur = :n", n=nom) or [{"active": False}])[0],
            "appareils_connus": _lignes(c, "SELECT ip AS adresse_ip, derniere_connexion FROM voicebank.appareils_connus "
                                           "WHERE utilisateur = :n ORDER BY derniere_connexion DESC", n=nom),
            "telephones_d_approbation": _lignes(c, "SELECT nom, date_ajout, derniere_utilisation "
                                                   "FROM voicebank.appareils_approbation WHERE utilisateur = :n", n=nom),
            "sessions": _lignes(c, "SELECT navigateur AS appareil, adresse_ip, methode, debut, derniere_activite, revoquee "
                                   "FROM voicebank.sessions WHERE utilisateur = :n ORDER BY debut DESC", n=nom),
            "questions_favorites": _lignes(c, "SELECT question, envoi_hebdo, date_creation, dernier_envoi "
                                              "FROM voicebank.questions_favorites WHERE utilisateur = :n", n=nom),
            "preferences_e_mails": _lignes(c, "SELECT alertes_critiques, resume_quotidien, rapport_hebdo, rapport_mensuel "
                                              "FROM voicebank.preferences_notifications WHERE utilisateur = :n", n=nom),
            "facturation": _lignes(c, "SELECT type_client, informations, date_maj FROM voicebank.profils_facturation "
                                      "WHERE utilisateur = :n", n=nom),
            "paiements": _lignes(c, "SELECT reference, formule, montant, devise, statut, fournisseur, date_creation, "
                                    "date_paiement, abonnement_fin FROM voicebank.paiements WHERE utilisateur = :n "
                                    "ORDER BY date_creation DESC", n=nom),
            "bases_connectees": _lignes(c, "SELECT nom, type_source, resume_connexion, date_creation, date_analyse "
                                           "FROM voicebank.sources_donnees WHERE proprietaire = :n", n=nom),
            "questions_posees": _lignes(c, "SELECT date_requete, texte_original AS question, succes "
                                           "FROM voicebank.logs_vocaux WHERE utilisateur = :n ORDER BY date_requete DESC", n=nom),
            "commentaires_sur_alertes": _lignes(c, "SELECT date_commentaire, nature, texte FROM voicebank.commentaires_alerte "
                                                   "WHERE auteur = :n ORDER BY date_commentaire DESC", n=nom),
            "actions_de_recouvrement": _lignes(c, "SELECT date_action, nature, texte, montant FROM "
                                                  "voicebank.actions_recouvrement WHERE auteur = :n ORDER BY date_action DESC",
                                               n=nom),
            "journal_d_activite": _lignes(c, "SELECT date_evenement, action, detail, adresse_ip FROM voicebank.journal_audit "
                                             "WHERE utilisateur = :n ORDER BY date_evenement DESC LIMIT 5000", n=nom),
            "durees_de_conservation": CONSERVATION,
        }


def verifier_effacement(nom: str) -> dict:
    """Ligne du compte si l'effacement est possible ; sinon EffacementRefuse avec la raison."""
    r = db.ecrire("SELECT u.nom, u.role, u.role_org, u.id_org, u.email, u.efface_le, "
                  "(SELECT COUNT(*) FROM voicebank.utilisateurs m WHERE m.id_org = u.id_org AND m.nom <> u.nom "
                  " AND m.actif AND m.efface_le IS NULL) AS autres_membres, "
                  "(SELECT COUNT(*) FROM voicebank.utilisateurs m WHERE m.id_org = u.id_org AND m.nom <> u.nom "
                  " AND m.actif AND m.efface_le IS NULL AND m.role_org = 'admin') AS autres_admins "
                  "FROM voicebank.utilisateurs u WHERE u.nom = :n", {"n": nom})
    if not r.lignes or r.lignes[0].efface_le:
        raise EffacementRefuse("Compte introuvable")
    l = r.lignes[0]
    if l.role not in ("visiteur", "client"):
        raise EffacementRefuse("Compte interne à la plateforme : il se désactive dans Administration → Comptes.")
    if l.id_org and l.role_org == "admin" and l.autres_membres and not l.autres_admins:
        raise EffacementRefuse("Vous êtes le seul administrateur de votre organisation, qui a d'autres membres : "
                               "nommez d'abord un autre administrateur (Mon organisation → Membres) ou retirez les membres.")
    return l._asdict()


def effacer(nom: str, par: str, ip: str | None = None) -> str:
    """Efface le compte ; retourne son pseudonyme. `par` : le titulaire, l'administrateur ou « conservation »."""
    l = verifier_effacement(nom)
    pseudo = f"efface-{secrets.token_hex(5)}"
    seul = not l["autres_membres"]
    with db.moteur_app.begin() as c:
        x = lambda sql, **p: c.execute(text(sql), {"n": nom, **p})  # noqa: E731
        x("DELETE FROM voicebank.logs_vocaux WHERE utilisateur = :n")
        for table in ("codes_recuperation", "acces_sources", "preferences_notifications", "double_authentification",
                      "appareils_connus", "sessions", "questions_favorites", "appareils_approbation",
                      "demandes_approbation"):
            x(f"DELETE FROM voicebank.{table} WHERE utilisateur = :n")
        x("DELETE FROM voicebank.echecs_connexion WHERE identifiant IN (:n, :e)", e=(l["email"] or "").lower())
        if not c.execute(text("SELECT 1 FROM voicebank.paiements WHERE utilisateur = :n AND statut = 'paye' LIMIT 1"),
                         {"n": nom}).first():
            x("DELETE FROM voicebank.profils_facturation WHERE utilisateur = :n")
        x("UPDATE voicebank.cles_api SET revoquee = TRUE WHERE cree_par = :n")
        x("UPDATE voicebank.dossiers_recouvrement SET assigne_a = NULL WHERE assigne_a = :n "
          "AND statut NOT IN ('regle', 'irrecouvrable')")
        x("UPDATE voicebank.suivi_alertes SET assigne_a = NULL WHERE assigne_a = :n "
          "AND statut NOT IN ('fraude_confirmee', 'fausse_alerte', 'resolue')")
        if seul:                         # bases connectées : supprimées avec un compte seul dans son organisation
            ids = [r[0] for r in c.execute(text("SELECT id_source FROM voicebank.sources_donnees WHERE proprietaire = :n "
                                                "OR (id_org IS NOT NULL AND id_org = :o)"), {"n": nom, "o": l["id_org"]})]
            if ids:
                c.execute(text("DELETE FROM voicebank.dossiers_recouvrement WHERE id_source = ANY(:i)"), {"i": ids})
                c.execute(text("DELETE FROM voicebank.cles_api WHERE id_source = ANY(:i)"), {"i": ids})
                c.execute(text("DELETE FROM voicebank.sources_donnees WHERE id_source = ANY(:i)"), {"i": ids})
            if l["id_org"]:
                c.execute(text("UPDATE voicebank.organisations SET actif = FALSE WHERE id_org = :o"), {"o": l["id_org"]})
        else:                            # les bases de l'organisation restent : elles passent à un administrateur
            x("UPDATE voicebank.sources_donnees SET proprietaire = (SELECT m.nom FROM voicebank.utilisateurs m "
              "WHERE m.id_org = :o AND m.nom <> :n AND m.actif AND m.efface_le IS NULL "
              "ORDER BY (m.role_org = 'admin') DESC, m.date_creation LIMIT 1) WHERE proprietaire = :n", o=l["id_org"])
        hachage = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt(4)).decode()
        x("UPDATE voicebank.utilisateurs SET actif = FALSE, email = NULL, nom_complet = NULL, profil = NULL, "
          "langue = NULL, jeton_deblocage = NULL, hash_mdp = :h, version_jeton = version_jeton + 1, "
          "efface_le = LOCALTIMESTAMP WHERE nom = :n", h=hachage)
        c.execute(text("SELECT voicebank.pseudonymiser_compte(:n, :p)"), {"n": nom, "p": pseudo})
    if seul:
        from .connecteur import fichiers
        for i in ids:
            for f in fichiers.CACHE.glob(f"source_{int(i)}_*.sqlite"):
                f.unlink(missing_ok=True)
    audit.journaliser(par, "compte_efface", {"compte": nom, "pseudonyme": pseudo}, ip)
    return pseudo


def appliquer_conservation() -> dict:
    """Tâche quotidienne : durées de conservation, puis effacement des essais gratuits oubliés."""
    res = dict(db.ecrire("SELECT voicebank.appliquer_conservation()").scalar() or {})
    oublies = db.ecrire(
        "SELECT nom FROM voicebank.utilisateurs u WHERE role = 'visiteur' AND efface_le IS NULL "
        "AND essai_fin < LOCALTIMESTAMP - make_interval(days => :j) "
        "AND NOT EXISTS (SELECT 1 FROM voicebank.paiements p WHERE p.utilisateur = u.nom AND p.statut = 'paye')",
        {"j": ESSAI_OUBLIE_JOURS}).lignes
    res["essais_effaces"] = 0
    for l in oublies:
        try:
            effacer(l.nom, "conservation")
            res["essais_effaces"] += 1
        except Exception:
            log.exception("Effacement de l'essai %s impossible", l.nom)
    return res
