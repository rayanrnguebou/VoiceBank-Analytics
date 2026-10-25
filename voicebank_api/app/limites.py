"""Limites de débit (partagées par toutes les routes)."""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from . import config


def ip_client(request: Request) -> str:
    """Adresse du client pour les limites de débit et l'audit. Derrière un proxy (Render), on prend
    la DERNIÈRE adresse de X-Forwarded-For, ajoutée par le proxy lui-même : les premières peuvent
    être inventées par le client pour contourner les limites."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        derniere = xff.split(",")[-1].strip()
        if derniere:
            return derniere[:64]
    return get_remote_address(request)


limiter = Limiter(key_func=ip_client, enabled=config.RATE_LIMIT_ACTIF)
