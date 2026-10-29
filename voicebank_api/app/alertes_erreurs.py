"""Alertes automatiques en cas d'erreur (Sentry, offre gratuite) : chaque erreur inattendue de l'API arrive par
e-mail chez l'équipe, avec la trace. Activé seulement si SENTRY_DSN est renseigné.

Confidentialité : ni corps de requête, ni en-têtes d'authentification, ni adresse IP, ni données de la base ne sont
envoyés (send_default_pii=False, corps jamais joints, en-têtes sensibles et paramètres effacés).
"""
import logging

from . import config

log = logging.getLogger("voicebank")
EN_TETES_SENSIBLES = {"authorization", "cookie", "x-cle-taches", "x-forwarded-for", "x-real-ip"}


def _nettoyer(evenement: dict, _indice=None) -> dict:
    req = evenement.get("request") or {}
    req.pop("data", None)
    req.pop("cookies", None)
    req.pop("query_string", None)
    if isinstance(req.get("headers"), dict):
        req["headers"] = {k: v for k, v in req["headers"].items() if k.lower() not in EN_TETES_SENSIBLES}
    evenement.pop("user", None)
    # Variables locales des traces : pourraient contenir des mots de passe ou des lignes de la base
    for exc in (evenement.get("exception") or {}).get("values", []):
        for cadre in (exc.get("stacktrace") or {}).get("frames", []):
            cadre.pop("vars", None)
    return evenement


def demarrer(version: str = "?"):
    if not config.SENTRY_DSN:
        return False
    import sentry_sdk
    sentry_sdk.init(dsn=config.SENTRY_DSN, environment=config.ENV, release=f"voicebank-api@{version}",
                    send_default_pii=False, include_local_variables=False, max_request_body_size="never",
                    traces_sample_rate=0.0, before_send=_nettoyer)
    log.info("Alertes d'erreurs Sentry actives")
    return True
