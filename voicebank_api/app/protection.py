"""Protection des connexions contre le devinage de mots de passe, sans permettre de bloquer le compte d'autrui.

Avant : 5 échecs bloquaient le COMPTE 15 minutes, donc n'importe qui pouvait empêcher un administrateur de se
connecter en tapant 5 mots de passe faux. Désormais :

1. Les échecs sont comptés par (identifiant, adresse IP). Au 5e échec, seule CETTE adresse est bloquée pour cet
   identifiant, avec un délai croissant (1, 5, 15, puis 60 minutes). Le titulaire, depuis son adresse, n'est pas gêné.
2. Si un compte subit beaucoup d'échecs depuis plusieurs adresses (attaque distribuée), il passe en « mode protégé »
   24 h : le mot de passe ne suffit plus depuis une adresse inconnue ; les adresses d'où le titulaire s'est déjà
   connecté (60 derniers jours) continuent de fonctionner.
3. Déblocage : un lien à usage unique est envoyé à l'adresse e-mail DU COMPTE. Le pirate ne peut ni le recevoir ni
   le déclencher pour lui-même ; le lien autorise seulement l'appareil qui l'ouvre. Se connecter avec Google /
   Microsoft ou réinitialiser son mot de passe par e-mail débloque aussi.
"""
import logging
import secrets
import time
from datetime import timedelta

import jwt

from . import config, db

log = logging.getLogger("voicebank")

ECHECS_PAR_ADRESSE = 5
PALIERS_MIN = (1, 5, 15, 60)
SEUIL_MODE_PROTEGE = 20               # échecs sur l'heure, toutes adresses confondues
DUREE_MODE_PROTEGE = timedelta(hours=24)
ADRESSE_CONNUE_JOURS = 60
DUREE_LIEN_H = 24


class ConnexionBloquee(Exception):
    """Message affichable (n'indique pas si l'identifiant existe)."""


def _ident(identifiant: str) -> str:
    return (identifiant or "").strip().lower()[:254]


def _minutes(secondes: float) -> str:
    m = max(1, round(secondes / 60))
    return f"{m} minute{'s' if m > 1 else ''}"


def verifier_adresse(identifiant: str, ip: str):
    """Avant de vérifier le mot de passe : refuse si cette adresse est bloquée pour cet identifiant."""
    r = db.ecrire("SELECT EXTRACT(EPOCH FROM (bloque_jusqua - LOCALTIMESTAMP)) FROM voicebank.echecs_connexion "
                  "WHERE identifiant = :i AND ip = :a AND bloque_jusqua > LOCALTIMESTAMP",
                  {"i": _ident(identifiant), "a": ip}).scalar()
    if r:
        raise ConnexionBloquee(f"Trop d'essais depuis cette connexion : réessaie dans {_minutes(float(r))}. "
                               "Mot de passe oublié ? Utilise « Mot de passe oublié ».")


def echec(identifiant: str, ip: str):
    """Note un échec ; bloque l'adresse au 5e ; passe le compte en mode protégé si l'attaque est distribuée."""
    i = _ident(identifiant)
    l = db.ecrire(
        "INSERT INTO voicebank.echecs_connexion (identifiant, ip, echecs, dernier_echec) VALUES (:i, :a, 1, LOCALTIMESTAMP) "
        "ON CONFLICT (identifiant, ip) DO UPDATE SET dernier_echec = LOCALTIMESTAMP, echecs = CASE "
        "WHEN echecs_connexion.dernier_echec < LOCALTIMESTAMP - INTERVAL '1 day' THEN 1 ELSE echecs_connexion.echecs + 1 END, "
        "palier = CASE WHEN echecs_connexion.dernier_echec < LOCALTIMESTAMP - INTERVAL '1 day' THEN 0 "
        "ELSE echecs_connexion.palier END RETURNING echecs, palier", {"i": i, "a": ip}).lignes[0]
    if l.echecs >= ECHECS_PAR_ADRESSE:
        minutes = PALIERS_MIN[min(l.palier, len(PALIERS_MIN) - 1)]
        db.ecrire("UPDATE voicebank.echecs_connexion SET echecs = 0, palier = palier + 1, "
                  "bloque_jusqua = LOCALTIMESTAMP + make_interval(mins => :m) WHERE identifiant = :i AND ip = :a",
                  {"i": i, "a": ip, "m": minutes})
        log.warning("Connexion : adresse %s bloquée %d min pour '%s'", ip, minutes, i)
    total = db.ecrire("SELECT COALESCE(SUM(echecs + palier * :n), 0) FROM voicebank.echecs_connexion "
                      "WHERE identifiant = :i AND dernier_echec > LOCALTIMESTAMP - INTERVAL '1 hour'",
                      {"i": i, "n": ECHECS_PAR_ADRESSE}).scalar()
    if total >= SEUIL_MODE_PROTEGE:
        _proteger(i)


def _compte(identifiant: str):
    l = db.ecrire("SELECT nom, email, nom_complet, COALESCE(verrouille_jusqua > LOCALTIMESTAMP, FALSE) AS protege "
                  "FROM voicebank.utilisateurs WHERE nom = :i OR LOWER(email) = :i ORDER BY (nom = :i) DESC LIMIT 1",
                  {"i": identifiant}).lignes
    return l[0] if l else None


def _proteger(identifiant: str):
    c = _compte(identifiant)
    if c is None or c.protege:
        return
    jti = secrets.token_urlsafe(24)
    db.ecrire("UPDATE voicebank.utilisateurs SET verrouille_jusqua = LOCALTIMESTAMP + :d, jeton_deblocage = :j "
              "WHERE nom = :n", {"n": c.nom, "d": DUREE_MODE_PROTEGE, "j": jti})
    log.warning("Compte '%s' en mode protégé (échecs répétés depuis plusieurs adresses)", c.nom)
    from . import audit
    audit.journaliser(c.nom, "compte_protege", {"motif": "échecs répétés depuis plusieurs adresses"}, None)
    if c.email:
        _envoyer_lien(c, jti, motif="attaque")


def _envoyer_lien(c, jti: str, motif: str):
    from . import courriel
    lien = jwt.encode({"sub": c.nom, "jti": jti, "usage": "deblocage", "exp": int(time.time()) + DUREE_LIEN_H * 3600},
                      config.JWT_SECRET, algorithm="HS256")
    url = f"{config.URL_INTERFACE}/?deblocage={lien}"
    if motif == "attaque":
        paragraphes = ["De nombreux mots de passe erronés ont été essayés sur votre compte VoiceBank, depuis plusieurs "
                       "adresses. Par précaution, votre compte est protégé pendant 24 heures : il reste accessible depuis "
                       "les appareils que vous utilisez habituellement.",
                       "Si vous n'arrivez pas à vous connecter depuis un nouvel appareil, ouvrez le lien ci-dessous "
                       "sur cet appareil. Personne d'autre ne peut l'utiliser à votre place."]
    else:
        paragraphes = ["Votre bon mot de passe vient d'être saisi depuis un appareil inconnu alors que votre compte est "
                       "protégé. Si c'était vous, ouvrez le lien ci-dessous sur cet appareil.",
                       "Si ce n'était pas vous, votre mot de passe est connu d'un tiers : changez-le immédiatement "
                       "(« Mot de passe oublié » sur l'écran de connexion)."]
    courriel.envoyer_en_arriere_plan(c.email, courriel.Message(
        sujet="Sécurité de votre compte VoiceBank", titre="Votre compte est protégé",
        salutation=f"Bonjour {c.nom_complet}," if c.nom_complet else "Bonjour,",
        paragraphes=paragraphes, bouton=("Autoriser cet appareil", url),
        note="Le lien est valable 24 heures et ne fonctionne qu'une fois. Vous n'avez rien demandé ? Ignorez ce lien."))


def autoriser_mot_de_passe(nom: str, ip: str, identifiant: str) -> None:
    """Après un mot de passe CORRECT : en mode protégé, seule une adresse connue est acceptée."""
    c = _compte(nom)
    if c is None or not c.protege:
        return
    connue = db.ecrire("SELECT 1 FROM voicebank.appareils_connus WHERE utilisateur = :n AND ip = :a AND "
                       f"derniere_connexion > LOCALTIMESTAMP - INTERVAL '{ADRESSE_CONNUE_JOURS} days'",
                       {"n": c.nom, "a": ip}).lignes
    if connue:
        return
    if c.email:
        jti = db.ecrire("SELECT jeton_deblocage FROM voicebank.utilisateurs WHERE nom = :n", {"n": c.nom}).scalar()
        if not jti:
            jti = secrets.token_urlsafe(24)
            db.ecrire("UPDATE voicebank.utilisateurs SET jeton_deblocage = :j WHERE nom = :n", {"n": c.nom, "j": jti})
        _envoyer_lien(c, jti, motif="appareil_inconnu")
    raise ConnexionBloquee("Ton compte est temporairement protégé après de nombreuses tentatives suspectes. Ouvre, sur "
                           "cet appareil, le lien envoyé à ton adresse e-mail, ou connecte-toi depuis ton appareil "
                           "habituel. Sans e-mail, demande à ton administrateur.")


def effacer_echecs(identifiant: str, ip: str):
    db.ecrire("DELETE FROM voicebank.echecs_connexion WHERE ip = :a AND identifiant = :i", {"a": ip, "i": _ident(identifiant)})


def succes(nom: str, ip: str, identifiant: str | None = None):
    """Connexion réussie : efface les échecs de cette adresse et la mémorise comme connue."""
    db.ecrire("DELETE FROM voicebank.echecs_connexion WHERE ip = :a AND identifiant IN (:i, :n)",
              {"a": ip, "i": _ident(identifiant or nom), "n": _ident(nom)})
    db.ecrire("INSERT INTO voicebank.appareils_connus (utilisateur, ip) VALUES (:n, :a) ON CONFLICT (utilisateur, ip) "
              "DO UPDATE SET derniere_connexion = LOCALTIMESTAMP", {"n": nom, "a": ip})


def debloquer(jeton: str, ip: str) -> str:
    """Lien reçu par e-mail : autorise l'appareil qui l'ouvre. Usage unique."""
    try:
        d = jwt.decode(jeton, config.JWT_SECRET, algorithms=["HS256"], options={"require": ["exp", "sub", "jti"]})
    except jwt.PyJWTError:
        raise ConnexionBloquee("Lien invalide ou expiré.")
    if d.get("usage") != "deblocage":
        raise ConnexionBloquee("Lien invalide ou expiré.")
    r = db.ecrire("UPDATE voicebank.utilisateurs SET jeton_deblocage = NULL WHERE nom = :n AND jeton_deblocage = :j",
                  {"n": d["sub"], "j": d["jti"]})
    if not r.rowcount:
        raise ConnexionBloquee("Ce lien a déjà été utilisé ou n'est plus valable.")
    db.ecrire("DELETE FROM voicebank.echecs_connexion WHERE ip = :a", {"a": ip})
    db.ecrire("INSERT INTO voicebank.appareils_connus (utilisateur, ip) VALUES (:n, :a) ON CONFLICT (utilisateur, ip) "
              "DO UPDATE SET derniere_connexion = LOCALTIMESTAMP", {"n": d["sub"], "a": ip})
    return d["sub"]


def lever(nom: str):
    """Fin de la protection (administrateur, mot de passe réinitialisé par e-mail, connexion Google / Microsoft)."""
    email = db.ecrire("UPDATE voicebank.utilisateurs SET verrouille_jusqua = NULL, jeton_deblocage = NULL, "
                      "echecs_connexion = 0 WHERE nom = :n RETURNING LOWER(email)", {"n": nom}).scalar()
    db.ecrire("DELETE FROM voicebank.echecs_connexion WHERE identifiant IN (:n, :e)", {"n": _ident(nom), "e": email or ""})
