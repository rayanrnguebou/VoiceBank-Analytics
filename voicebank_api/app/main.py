"""VoiceBank Analytics — API FastAPI.
Auteur : Nguebou Temgoua Rayan

Ce fichier assemble l'application : sécurité (en-têtes, CORS, maintenance, erreurs), chargement des
modèles, puis les routeurs de app/api/ (un par domaine)."""
import json
import logging

import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi.errors import RateLimitExceeded

from . import alertes_erreurs, config, i18n, credit, fraude, maintenance, securite, sessions, taches, transcription
from .api import (abonnement, admin, assistant, auth, demo, donnees, favoris, organisation, recouvrement, score,
                  sources, surveillance, systeme)
from .api.commun import VERSION_API, _lire, _SQL_CREDIT, reponse_maintenance  # noqa: F401  (utilisés par les tests)
from .limites import limiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("voicebank")
alertes_erreurs.demarrer(VERSION_API)           # Sentry (si SENTRY_DSN) : avant la création de l'application

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
    if not request.url.path.startswith(("/health", "/taches")):
        taches.noter_activite()            # les tâches automatiques attendent un moment calme
    if request.method != "OPTIONS" and not request.url.path.startswith(maintenance.OUVERTES):
        etat = await run_in_threadpool(maintenance.etat)
        if etat["active"] and _role_du_jeton(request) != "admin":
            return reponse_maintenance(etat)
    return await call_next(request)


@app.middleware("http")


async def langue_des_reponses(request: Request, call_next):
    """Langue de l'interface (Accept-Language) : messages, erreurs et textes des réponses JSON traduits."""
    code = i18n.depuis_entete(request.headers.get("accept-language"))
    jeton = i18n.definir(code)
    sessions.noter_requete(request.headers.get("user-agent"), request.headers.get("x-appareil"))
    try:
        rep = await call_next(request)
    finally:
        i18n._langue.reset(jeton)
    if code == "fr" or not rep.headers.get("content-type", "").startswith("application/json"):
        return rep
    corps = b"".join([morceau async for morceau in rep.body_iterator])
    try:
        donnees = i18n.traduire_objet(json.loads(corps), code)
        corps = json.dumps(donnees, ensure_ascii=False, separators=(",", ":")).encode()
    except ValueError:
        pass
    entetes = {k: v for k, v in rep.headers.items() if k.lower() not in ("content-length",)}
    return Response(corps, status_code=rep.status_code, headers=entetes, media_type="application/json")


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "Accept-Language", "X-Appareil"],
    expose_headers=["Content-Disposition"],      # nom des fichiers téléchargés (rapports PDF)
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


class LimiteCorps:
    """Taille maximale d'une requête, vérifiée AVANT de lire le corps : sans elle, un envoi de plusieurs Go (même
    sans être connecté : le formulaire est lu avant le contrôle du compte) remplirait le disque du serveur."""

    def __init__(self, app, maximum: int):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        longueur = dict(scope.get("headers") or []).get(b"content-length")
        if longueur is not None and (not longueur.isdigit() or int(longueur) > self.maximum):
            return await JSONResponse({"detail": "Requête trop volumineuse"}, status_code=413)(scope, receive, send)
        recu = 0

        async def lire():
            nonlocal recu
            message = await receive()
            if message["type"] == "http.request":
                recu += len(message.get("body", b""))
                if recu > self.maximum:          # corps envoyé « par morceaux », sans longueur annoncée
                    raise HTTPException(413, "Requête trop volumineuse")
            return message
        await self.app(scope, lire, send)


# 6 fichiers de données au plus (le surplus est ignoré), ou un enregistrement audio, plus l'enveloppe du formulaire
app.add_middleware(LimiteCorps, maximum=max(6 * config.CONNECTEUR_TAILLE_FICHIER_MO * 1024 * 1024,
                                            config.TAILLE_MAX_AUDIO) + 1024 * 1024)


fraude.charger()

credit.charger()

transcription.precharger_en_arriere_plan()
taches.demarrer_en_arriere_plan()


try:
    securite.amorcer()
except Exception:
    log.exception("Amorçage des comptes impossible (base indisponible ?) : nouvel essai au prochain démarrage")


for _r in (systeme, auth, abonnement, demo, assistant, admin, organisation, sources, surveillance, donnees, favoris,
           recouvrement, score):
    app.include_router(_r.router)
