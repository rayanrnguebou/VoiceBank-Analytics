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


# ── Limite par compte connecté ─────────────────────────────────────
import threading  # noqa: E402
import time  # noqa: E402
from collections import defaultdict, deque  # noqa: E402

_verrou_comptes = threading.Lock()
_requetes_comptes: dict[str, deque] = defaultdict(deque)


def compte_depasse(compte: str) -> str | None:
    """Note une requête du compte ; retourne la limite dépassée (« minute » / « heure ») ou None."""
    maintenant = time.time()
    with _verrou_comptes:
        file = _requetes_comptes[compte]
        while file and file[0] < maintenant - 3600:
            file.popleft()
        derniere_minute = sum(1 for t in reversed(file) if t > maintenant - 60) if len(file) >= config.LIMITE_COMPTE_MINUTE else 0
        if derniere_minute >= config.LIMITE_COMPTE_MINUTE:
            return "minute"
        if len(file) >= config.LIMITE_COMPTE_HEURE:
            return "heure"
        file.append(maintenant)
        if len(_requetes_comptes) > 50_000:                 # mémoire bornée
            for k in [k for k, f in _requetes_comptes.items() if not f or f[-1] < maintenant - 3600]:
                del _requetes_comptes[k]
    return None


def oublier_comptes():
    """(tests)"""
    with _verrou_comptes:
        _requetes_comptes.clear()
