"""Configuration centralisée, lue uniquement depuis les variables d'environnement.

Aucun secret n'est écrit dans le code : tout vient de `.env` (local) ou des
variables du service (Docker / Render).
"""
import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("voicebank")

BASE_DIR = Path(__file__).resolve().parent.parent  # dossier voicebank_api/


def _env(nom: str, defaut: str = "") -> str:
    return os.getenv(nom, defaut).strip().strip("'\"")


ENV = _env("ENV", "development").lower()          # development | production | test
EST_PROD = ENV == "production"

# ── Base de données ───────────────────────────────────────────
# DATABASE_URL          : compte propriétaire (écritures applicatives : logs, RAG)
# READONLY_DATABASE_URL : compte en LECTURE SEULE pour exécuter le SQL généré
DATABASE_URL = _env("DATABASE_URL")
READONLY_DATABASE_URL = _env("READONLY_DATABASE_URL") or DATABASE_URL
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL n'est pas définie (voir .env.example)")
def _pilote_psycopg2(url: str) -> str:
    # Render/Heroku donnent "postgres://" ; on force le pilote psycopg2 installé.
    for prefixe in ("postgres://", "postgresql://"):
        if url.startswith(prefixe):
            return "postgresql+psycopg2://" + url[len(prefixe):]
    return url


DATABASE_URL = _pilote_psycopg2(DATABASE_URL)
READONLY_DATABASE_URL = _pilote_psycopg2(READONLY_DATABASE_URL)

SQL_TIMEOUT_MS = int(_env("SQL_TIMEOUT_MS", "5000"))
SQL_MAX_LIGNES = int(_env("SQL_MAX_LIGNES", "1000"))

# ── IA ────────────────────────────────────────────────────────
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.5-flash-lite")
GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_WHISPER_MODEL = _env("GROQ_WHISPER_MODEL", "whisper-large-v3")
# Whisper local (voicebank_whisper), utilisé si GROQ_API_KEY est vide ou si Groq échoue
WHISPER_LOCAL = _env("WHISPER_LOCAL", "auto").lower()          # auto | false
WHISPER_LOCAL_MODELE = _env("WHISPER_LOCAL_MODELE", "base")    # tiny, base, small, medium…
WHISPER_LOCAL_DOSSIER = _env("WHISPER_LOCAL_DOSSIER") or None
WHISPER_LOCAL_DUREE_MAX_S = float(_env("WHISPER_LOCAL_DUREE_MAX_S", "60"))
WHISPER_LOCAL_PRECHARGER = _env("WHISPER_LOCAL_PRECHARGER", "true").lower() == "true"
SEUIL_RAG = float(_env("SEUIL_RAG", "0.45"))


def _trouver_dossier_modeles() -> Path:
    candidats = [
        _env("MODELS_DIR"),
        BASE_DIR / "voicebank_ia" / "modeles_sauvegardes",          # image Docker
        BASE_DIR.parent / "voicebank_ia" / "modeles_sauvegardes",   # local / Render
        BASE_DIR / "modeles_sauvegardes",
    ]
    for c in candidats:
        if c and Path(c).is_dir():
            return Path(c)
    return Path(candidats[2])


MODELS_DIR = _trouver_dossier_modeles()

# ── Sécurité ──────────────────────────────────────────────────
JWT_SECRET = _env("JWT_SECRET")
if not JWT_SECRET:
    if EST_PROD:
        raise RuntimeError("JWT_SECRET est obligatoire en production")
    JWT_SECRET = secrets.token_urlsafe(48)
    log.warning("JWT_SECRET absent : secret temporaire généré (sessions perdues au redémarrage)")
if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET doit faire au moins 32 caractères")

JWT_DUREE_MIN = int(_env("JWT_DUREE_MIN", "60"))

# Comptes : NOM:ROLE:HASH_BCRYPT séparés par des virgules.
# Générer un hash : python -m app.outils.creer_hash
# Exemple : VOICEBANK_USERS=rayan:admin:$2b$12$...,analyste1:analyste:$2b$12$...
VOICEBANK_USERS = _env("VOICEBANK_USERS")

ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in _env(
    "ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

TAILLE_MAX_AUDIO = int(_env("TAILLE_MAX_AUDIO_MO", "10")) * 1024 * 1024
RATE_LIMIT_ACTIF = _env("RATE_LIMIT_ACTIF", "true").lower() == "true"
