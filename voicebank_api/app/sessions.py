"""Sessions ouvertes et appareils : « Mes appareils », déconnexion à distance, e-mail lors d'une connexion depuis un
appareil inconnu.

Chaque connexion ouvre une session (identifiant aléatoire porté par le jeton : « sid »). Le jeton renouvelé garde la
même session. Une session déconnectée à distance est refusée dès la requête suivante.
L'appareil est reconnu par un identifiant aléatoire gardé dans le navigateur (en-tête X-Appareil), à défaut par son
navigateur ; seule une empreinte (HMAC) est conservée.
"""
import contextvars
import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime

from . import config, courriel, db

log = logging.getLogger("voicebank")
_requete: contextvars.ContextVar[tuple[str, str]] = contextvars.ContextVar("requete_appareil", default=("", ""))
JOURS_HISTORIQUE = 30


def noter_requete(user_agent: str | None, appareil: str | None):
    """Appelé par l'intercepteur HTTP : navigateur et identifiant d'appareil de la requête en cours."""
    _requete.set(((user_agent or "")[:400], (appareil or "")[:100]))


def resume_navigateur(ua: str) -> str:
    """« Chrome · Windows », « Safari · iPhone »… (jamais la chaîne complète)."""
    navs = [("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung Internet"), ("Firefox/", "Firefox"),
            ("Chrome/", "Chrome"), ("Safari/", "Safari")]
    systemes = [("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"),
                ("Mac OS X", "Mac"), ("CrOS", "ChromeOS"), ("Linux", "Linux")]
    nav = next((n for m, n in navs if m in ua), None)
    os_ = next((n for m, n in systemes if m in ua), None)
    if not nav and not os_:
        return re.sub(r"[^\w .-]", "", ua.split("/")[0])[:40] or "Navigateur inconnu"
    return " · ".join(x for x in (nav, os_) if x)


def _empreinte(ua: str, appareil: str) -> str:
    source = f"id:{appareil}" if appareil else f"ua:{ua}"
    return hmac.new(config.JWT_SECRET.encode(), source.encode(), hashlib.sha256).hexdigest()[:40]


def ouvrir(nom: str, ip: str | None, methode: str, version: int) -> str:
    """Nouvelle session à la connexion ; e-mail si l'appareil est inconnu (et que le compte en a déjà utilisé un autre)."""
    ua, appareil = _requete.get()
    empreinte = _empreinte(ua, appareil)
    sid = secrets.token_urlsafe(16)
    deja = db.ecrire("SELECT COUNT(*) AS n, COALESCE(BOOL_OR(appareil = :a), FALSE) AS connu FROM voicebank.sessions "
                     "WHERE utilisateur = :u", {"u": nom, "a": empreinte}).lignes[0]
    db.ecrire("INSERT INTO voicebank.sessions (id_session, utilisateur, appareil, navigateur, adresse_ip, methode, "
              "version_jeton) VALUES (:s, :u, :a, :n, :ip, :m, :v)",
              {"s": sid, "u": nom, "a": empreinte, "n": resume_navigateur(ua), "ip": ip, "m": methode[:20], "v": version})
    if deja.n and not deja.connu:
        _prevenir(nom, resume_navigateur(ua), ip, methode)
    return sid


def toucher(sid: str, version: int):
    """Jeton renouvelé (ou réémis) : la session reste active."""
    db.ecrire("UPDATE voicebank.sessions SET derniere_activite = LOCALTIMESTAMP, version_jeton = :v "
              "WHERE id_session = :s", {"s": sid, "v": version})


def _prevenir(nom: str, navigateur: str, ip: str | None, methode: str):
    if not courriel.disponible():
        return
    l = db.ecrire("SELECT email, nom_complet FROM voicebank.utilisateurs WHERE nom = :n", {"n": nom}).lignes
    if not l or not l[0].email:
        return
    methodes = {"mot_de_passe": "Mot de passe", "google": "Google", "microsoft": "Microsoft", "essai": "Inscription",
                "invitation": "Activation du compte"}
    courriel.envoyer_en_arriere_plan(l[0].email, courriel.Message(
        sujet="Nouvelle connexion à votre compte VoiceBank",
        titre="Nouvelle connexion",
        salutation=f"Bonjour {l[0].nom_complet}," if l[0].nom_complet else "Bonjour,",
        paragraphes=["Votre compte VoiceBank vient d'être utilisé depuis un appareil qui ne s'était encore jamais "
                     "connecté. Si c'était vous, il n'y a rien à faire."],
        details=[("Date", datetime.now().strftime("%d/%m/%Y %H:%M")), ("Appareil", navigateur),
                 ("Adresse IP", ip or "inconnue"), ("Méthode", methodes.get(methode, methode))],
        bouton=("Vérifier mes appareils", config.URL_INTERFACE),
        apres=["Si ce n'était pas vous : changez votre mot de passe, puis ouvrez « Sécurité de mon compte » et "
               "choisissez « Déconnecter les autres appareils ». Activez aussi la double authentification."],
        apercu="Connexion depuis un nouvel appareil",
        note="E-mail de sécurité envoyé à chaque connexion depuis un appareil inconnu."))


def lister(nom: str, courante: str | None) -> list[dict]:
    r = db.ecrire(
        "SELECT s.id_session, s.navigateur, s.adresse_ip, s.methode, s.debut, s.derniere_activite, s.revoquee, "
        "(NOT s.revoquee AND s.version_jeton = u.version_jeton AND u.actif "
        " AND s.derniere_activite > LOCALTIMESTAMP - make_interval(mins => :d) "
        " AND s.debut > LOCALTIMESTAMP - make_interval(hours => :h)) AS active "
        "FROM voicebank.sessions s JOIN voicebank.utilisateurs u ON u.nom = s.utilisateur "
        "WHERE s.utilisateur = :n AND s.derniere_activite > LOCALTIMESTAMP - make_interval(days => :j) "
        "ORDER BY s.derniere_activite DESC LIMIT 50",
        {"n": nom, "d": config.JWT_DUREE_MIN, "h": int(config.SESSION_MAX_HEURES), "j": JOURS_HISTORIQUE})
    return [{"id": l.id_session, "appareil": l.navigateur, "adresse_ip": l.adresse_ip, "methode": l.methode,
             "debut": l.debut.isoformat(), "derniere_activite": l.derniere_activite.isoformat(),
             "active": bool(l.active) or l.id_session == courante, "courante": l.id_session == courante}
            for l in r.lignes]


def revoquer(nom: str, sid: str) -> bool:
    return bool(db.ecrire("UPDATE voicebank.sessions SET revoquee = TRUE WHERE utilisateur = :n AND id_session = :s",
                          {"n": nom, "s": sid}).rowcount)


def revoquer_autres(nom: str, courante: str | None) -> int:
    return db.ecrire("UPDATE voicebank.sessions SET revoquee = TRUE WHERE utilisateur = :n AND NOT revoquee "
                     "AND id_session IS DISTINCT FROM :s", {"n": nom, "s": courante}).rowcount
