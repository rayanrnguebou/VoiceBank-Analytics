"""Vigilance : journal des événements de sécurité et alerte par e-mail en cas de rafale.

Chaque événement (connexion refusée, clé d'API refusée, appel depuis une adresse IP non autorisée, limite d'un compte
dépassée) est noté dans le journal d'audit (« securite_… »), visible dans Administration → Journal. Quand un seuil
est franchi sur 10 minutes (même adresse IP, même clé ou même compte), un e-mail part :
* aux administrateurs de la plateforme (adresse de ALERTES_SECURITE_EMAIL, sinon e-mail des comptes « admin ») ;
* pour une clé d'API, aussi à la personne qui l'a créée (elle sait si l'appel est légitime).
Une même alerte n'est envoyée qu'une fois par heure : une attaque ne déclenche pas une avalanche d'e-mails.
"""
import logging
import threading
import time
from collections import defaultdict, deque

from . import audit, config, db

log = logging.getLogger("voicebank")

FENETRE_S = 600
RAPPEL_S = 3600
# Seuil (nombre d'événements sur 10 minutes, par clé de regroupement) avant d'alerter
SEUILS = {
    "connexion_refusee": 15,       # même adresse IP (devinage de mots de passe)
    "cle_api_refusee": 20,         # même adresse IP (clés inventées ou révoquées)
    "ip_non_autorisee": 1,         # bonne clé, mauvaise adresse : la clé a peut-être fuité
    "limite_compte": 1,            # un compte aspire des données à un rythme anormal
}
LIBELLES = {
    "connexion_refusee": "connexions refusées",
    "cle_api_refusee": "appels d'API refusés (clé absente, inventée ou révoquée)",
    "ip_non_autorisee": "appels avec une clé d'API valide depuis une adresse IP non autorisée",
    "limite_compte": "dépassement de la limite de requêtes d'un compte",
}

_verrou = threading.Lock()
_evenements: dict[tuple[str, str], deque] = defaultdict(deque)
_derniere_alerte: dict[tuple[str, str], float] = {}


def _compter(type_: str, cle: str, maintenant: float) -> int:
    with _verrou:
        file = _evenements[(type_, cle)]
        file.append(maintenant)
        while file and file[0] < maintenant - FENETRE_S:
            file.popleft()
        if len(_evenements) > 20_000:                      # mémoire bornée : on oublie les groupes inactifs
            for k in [k for k, f in _evenements.items() if not f or f[-1] < maintenant - FENETRE_S]:
                del _evenements[k]
        return len(file)


def _a_alerter(type_: str, cle: str, maintenant: float) -> bool:
    with _verrou:
        if maintenant - _derniere_alerte.get((type_, cle), 0) < RAPPEL_S:
            return False
        _derniere_alerte[(type_, cle)] = maintenant
        return True


def destinataires_plateforme() -> list[str]:
    if config.ALERTES_SECURITE_EMAIL:
        return config.ALERTES_SECURITE_EMAIL
    try:
        r = db.ecrire("SELECT COALESCE(email, CASE WHEN nom LIKE '%@%' THEN nom END) AS e FROM voicebank.utilisateurs "
                      "WHERE role = 'admin' AND actif").lignes
        return [l.e for l in r if l.e]
    except Exception:
        return []


def _email_compte(nom: str | None) -> str | None:
    if not nom:
        return None
    try:
        return db.ecrire("SELECT COALESCE(email, CASE WHEN nom LIKE '%@%' THEN nom END) FROM voicebank.utilisateurs "
                         "WHERE nom = :n AND actif", {"n": nom}).scalar()
    except Exception:
        return None


def _alerter(type_: str, cle: str, nombre: int, detail: dict, aussi: str | None):
    from . import courriel
    if not courriel.disponible():
        log.warning("Alerte de sécurité (e-mail indisponible) : %s %s ×%d", type_, cle, nombre)
        return
    lignes = [f"VoiceBank a détecté {nombre} {LIBELLES.get(type_, type_)} en moins de 10 minutes."]
    if type_ == "ip_non_autorisee":
        lignes.append("La clé est valide mais l'appel vient d'une adresse que vous n'avez pas autorisée : elle a "
                      "peut-être fuité. Si ce n'est pas un de vos serveurs, révoquez-la dans VoiceBank → Logiciel "
                      "bancaire et créez-en une nouvelle.")
    elif type_ == "connexion_refusee":
        lignes.append("Les comptes visés sont protégés (adresse bloquée après 5 essais, mode protégé en cas "
                      "d'attaque distribuée). Aucune action n'est nécessaire si personne de votre équipe n'a oublié "
                      "son mot de passe.")
    elif type_ == "limite_compte":
        lignes.append("Le compte a été ralenti automatiquement. Si cette activité n'est pas normale (compte volé, "
                      "script), déconnectez ses sessions et changez son mot de passe.")
    details = [(k, str(v)[:120]) for k, v in detail.items() if v not in (None, "")]
    m = courriel.Message(sujet=f"⚠ Alerte de sécurité VoiceBank : {LIBELLES.get(type_, type_)}",
                         titre="Activité suspecte détectée", paragraphes=lignes, details=details,
                         apercu=f"{nombre} {LIBELLES.get(type_, type_)}",
                         note="Une même alerte n'est envoyée qu'une fois par heure. Détail : Administration → Journal.")
    for d in dict.fromkeys([*destinataires_plateforme(), *([aussi] if aussi else [])]):
        courriel.envoyer_en_arriere_plan(d, m)


def signaler(type_: str, cle: str, detail: dict | None = None, utilisateur: str | None = None, ip: str | None = None,
             prevenir: str | None = None):
    """Note l'événement et alerte si le seuil est franchi. `prevenir` : compte à prévenir en plus (créateur d'une clé).
    Ne lève jamais d'exception : la sécurité ne doit pas casser la requête en cours."""
    try:
        detail = {**(detail or {}), "ip": ip}
        audit.journaliser(utilisateur, f"securite_{type_}", detail, ip)
        maintenant = time.time()
        nombre = _compter(type_, cle, maintenant)
        if nombre >= SEUILS.get(type_, 10) and _a_alerter(type_, cle, maintenant):
            log.warning("Alerte de sécurité : %s (%s) ×%d", type_, cle, nombre)
            _alerter(type_, cle, nombre, detail, _email_compte(prevenir))
    except Exception:
        log.exception("Vigilance : événement %s non traité", type_)


def oublier():
    """(tests)"""
    with _verrou:
        _evenements.clear()
        _derniere_alerte.clear()
