"""Vérification anti-robot (Cloudflare Turnstile, gratuit) sur l'inscription à l'essai et le mot de passe oublié.

Inactive tant que TURNSTILE_SECRET n'est pas défini (développement, tests). Une fois activée, le jeton produit
par le widget de l'interface est vérifié auprès de Cloudflare : sans jeton valide, la demande est refusée.
Si Cloudflare est injoignable, on refuse aussi (fail-closed) : un robot ne doit pas profiter d'une panne.
"""
import logging

import httpx

from . import config

log = logging.getLogger("voicebank")
URL_VERIFICATION = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class RobotSuspecte(Exception):
    """Vérification anti-robot échouée (message affichable)."""


def actif() -> bool:
    return bool(config.TURNSTILE_SECRET)


def verifier(jeton: str | None, ip: str | None = None):
    if not actif():
        return
    if not jeton:
        raise RobotSuspecte("Vérification anti-robot manquante : recharge la page et réessaie.")
    try:
        r = httpx.post(URL_VERIFICATION, timeout=8, data={
            "secret": config.TURNSTILE_SECRET, "response": jeton[:2048], **({"remoteip": ip} if ip else {})})
        ok = r.status_code == 200 and r.json().get("success") is True
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Turnstile injoignable : %s", e)
        raise RobotSuspecte("Vérification anti-robot indisponible pour le moment, réessaie dans un instant.")
    if not ok:
        log.info("Vérification anti-robot refusée depuis %s", ip)
        raise RobotSuspecte("Vérification anti-robot échouée : recharge la page et réessaie.")
