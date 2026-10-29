"""VoiceBank Analytics — API FastAPI.
Auteur : Nguebou Temgoua Rayan

Ce fichier assemble l'application : sécurité (en-têtes, CORS, maintenance, erreurs), chargement des
modèles, puis les routeurs de app/api/ (un par domaine)."""
import logging

import jwt
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from . import config, credit, fraude, maintenance, securite, transcription
from .api import abonnement, admin, assistant, auth, demo, organisation, sources, systeme
from .api.commun import VERSION_API, _lire, _SQL_CREDIT, reponse_maintenance  # noqa: F401  (utilisés par les tests)
from .limites import limiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("voicebank")

app = FastAPI(
    title="VoiceBank Analytics API",
    description="API bancaire vocale (texte/voix -> SQL) — Nguebou Temgoua Rayan",
    version=VERSION_API,
    docs_url=None if config.EST_PROD else "/docs",
    redoc_url=None,
    openapi_url=None if config.EST_PROD else "/openapi.json",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)


def _trop_de_requetes(request: Request, exc: RateLimitExceeded):
    return JSONResponse({"detail": "Trop de requêtes, réessaie dans un instant."}, status_code=429)


@app.middleware("http")


async def erreurs_internes(request: Request, call_next):
    # Ajouté AVANT CORS (donc à l'intérieur) : une erreur 500 garde les en-têtes CORS et le
    # navigateur affiche "Erreur interne" au lieu de "API injoignable".
    # Le détail reste dans les logs serveur, jamais renvoyé au client.
    try:
        return await call_next(request)
    except Exception:
        log.exception("Erreur non gérée sur %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Erreur interne du serveur"}, status_code=500)


def _role_du_jeton(request: Request) -> str | None:
    """Rôle signé dans le jeton (simple filtre : chaque route revérifie le compte en base)."""
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    try:
        return jwt.decode(auth[7:], config.JWT_SECRET, algorithms=[securite.ALGO]).get("role")
    except jwt.PyJWTError:
        return None


@app.middleware("http")


async def mode_maintenance(request: Request, call_next):
    # Avant CORS (donc à l'intérieur) : la réponse 503 garde les en-têtes CORS et l'interface l'affiche.
    if request.method != "OPTIONS" and not request.url.path.startswith(maintenance.OUVERTES):
        etat = await run_in_threadpool(maintenance.etat)
        if etat["active"] and _role_du_jeton(request) != "admin":
            return reponse_maintenance(etat)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")


async def entetes_securite(request: Request, call_next):
    rep = await call_next(request)
    rep.headers["X-Content-Type-Options"] = "nosniff"
    rep.headers["X-Frame-Options"] = "DENY"
    rep.headers["Referrer-Policy"] = "no-referrer"
    rep.headers["Cache-Control"] = "no-store"
    if config.EST_PROD:
        rep.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return rep


fraude.charger()

credit.charger()

transcription.precharger_en_arriere_plan()


try:
    securite.amorcer()
except Exception:
    log.exception("Amorçage des comptes impossible (base indisponible ?) : nouvel essai au prochain démarrage")


for _r in (systeme, auth, abonnement, demo, assistant, admin, organisation, sources):
    app.include_router(_r.router)
