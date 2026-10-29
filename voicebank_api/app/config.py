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
# Durée maximale d'une session, renouvellements compris : au-delà, il faut se reconnecter
# (un jeton volé ne peut pas être prolongé indéfiniment).
SESSION_MAX_HEURES = float(_env("SESSION_MAX_HEURES", "12"))

# Comptes : NOM:ROLE:HASH_BCRYPT séparés par des virgules.
# Générer un hash : python -m app.outils.creer_hash
# Exemple : VOICEBANK_USERS=rayan:admin:$2b$12$...,analyste1:analyste:$2b$12$...
VOICEBANK_USERS = _env("VOICEBANK_USERS")

ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in _env(
    "ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

TAILLE_MAX_AUDIO = int(_env("TAILLE_MAX_AUDIO_MO", "10")) * 1024 * 1024
RATE_LIMIT_ACTIF = _env("RATE_LIMIT_ACTIF", "true").lower() == "true"
# Anti-robot Cloudflare Turnstile (gratuit) : clé secrète côté API ; la clé de site va dans l'interface
# (REACT_APP_TURNSTILE_SITE_KEY). Vide : vérification désactivée.
TURNSTILE_SECRET = _env("TURNSTILE_SECRET")

# ── Offre publique : essai gratuit et abonnements ─────────────
INSCRIPTION_ESSAI = _env("INSCRIPTION_ESSAI", "true").lower() == "true"
ESSAI_JOURS = int(_env("ESSAI_JOURS", "3"))
MAX_ESSAIS_PAR_JOUR = int(_env("MAX_ESSAIS_PAR_JOUR", "200"))     # protège les coûts IA
QUOTA_QUESTIONS_ESSAI = int(_env("QUOTA_QUESTIONS_ESSAI", "30"))  # par jour
QUOTA_QUESTIONS_CLIENT = int(_env("QUOTA_QUESTIONS_CLIENT", "500"))
# Formules : (libellé, durée en jours, prix en FCFA). Prix modifiables sans toucher au code.
FORMULES = {
    "jour":    ("Journée", 1, int(_env("PRIX_JOUR", "500"))),
    "semaine": ("Semaine", 7, int(_env("PRIX_SEMAINE", "2000"))),
    "mois":    ("Mois", 30, int(_env("PRIX_MOIS", "6000"))),
    "annee":   ("Année", 365, int(_env("PRIX_ANNEE", "60000"))),
}
DEVISE = "XAF"
# Comptes inclus dans l'abonnement d'une ORGANISATION (administrateur compris) ; un particulier : 1 compte.
COMPTES_PAR_FORMULE = {
    "jour": int(_env("COMPTES_JOUR", "3")),
    "semaine": int(_env("COMPTES_SEMAINE", "3")),
    "mois": int(_env("COMPTES_MOIS", "10")),
    "annee": int(_env("COMPTES_ANNEE", "25")),
}

# ── Paiement (NotchPay : MTN MoMo, Orange Money, cartes) ─────
NOTCHPAY_URL = _env("NOTCHPAY_URL", "https://api.notchpay.co").rstrip("/")
NOTCHPAY_PUBLIC_KEY = _env("NOTCHPAY_PUBLIC_KEY")
NOTCHPAY_HASH_KEY = _env("NOTCHPAY_HASH_KEY")          # clé de signature des webhooks
# Adresse de l'interface (retour après paiement). Par défaut : la première de ALLOWED_ORIGINS.
URL_INTERFACE = (_env("URL_INTERFACE") or ALLOWED_ORIGINS[0]).rstrip("/")
# Simulation (sans compte marchand) : jamais sur Render, jamais avec une vraie clé.
PAIEMENT_SIMULATION = (_env("PAIEMENT_SIMULATION", "false").lower() == "true"
                       and not os.environ.get("RENDER") and not NOTCHPAY_PUBLIC_KEY)

# ── E-mails (codes de récupération du mot de passe) ──────────
# Brevo (API HTTPS, 300 e-mails/jour gratuits ; fonctionne sur Render, qui bloque le SMTP en offre gratuite)
# ou, à défaut, un serveur SMTP (ex. Gmail avec un « mot de passe d'application »).
BREVO_API_KEY = _env("BREVO_API_KEY")
SMTP_HOTE = _env("SMTP_HOTE")
SMTP_PORT = int(_env("SMTP_PORT", "587"))
SMTP_UTILISATEUR = _env("SMTP_UTILISATEUR")
SMTP_MOT_DE_PASSE = _env("SMTP_MOT_DE_PASSE")
EMAIL_EXPEDITEUR = _env("EMAIL_EXPEDITEUR") or SMTP_UTILISATEUR
EMAIL_NOM_EXPEDITEUR = _env("EMAIL_NOM_EXPEDITEUR", "VoiceBank Analytics")
CODE_RECUPERATION_MIN = int(_env("CODE_RECUPERATION_MIN", "15"))
INVITATION_HEURES = int(_env("INVITATION_HEURES", "72"))
# Signature des e-mails
EMAIL_SIGNATURE_NOM = _env("EMAIL_SIGNATURE_NOM", "Rayan Nguebou Temgoua")
EMAIL_SIGNATURE_FONCTION = _env("EMAIL_SIGNATURE_FONCTION", "Fondateur, VoiceBank Analytics")
EMAIL_CONTACT = _env("EMAIL_CONTACT") or EMAIL_EXPEDITEUR

# ── Tâches automatiques (surveillance horaire, résumé du matin, rapports PDF) ──
# TACHES_CLE : secret partagé avec GitHub Actions, qui appelle POST /taches/executer chaque heure.
TACHES_CLE = _env("TACHES_CLE")
# Secours : l'API exécute aussi les tâches toutes les 15 min tant qu'elle est éveillée (désactivé pendant les tests).
TACHES_AUTO = _env("TACHES_AUTO", "false" if ENV == "test" else "true").lower() == "true"

# ── Connecteur : bases et fichiers des organisations ─────────
# Clé de chiffrement des identifiants de connexion (n'importe quelle chaîne longue et secrète).
# À défaut, dérivée de JWT_SECRET (changer JWT_SECRET rendrait alors les identifiants illisibles).
CLE_SOURCES = _env("CLE_SOURCES") or JWT_SECRET
# Rotation : mets la nouvelle clé dans CLE_SOURCES et l'ancienne ici (séparées par des virgules s'il y en a
# plusieurs), puis lance « python -m app.outils.rechiffrer_sources » ; ensuite cette variable peut être vidée.
CLE_SOURCES_ANCIENNES = [c.strip() for c in _env("CLE_SOURCES_ANCIENNES").split(",") if c.strip()]
# false (en ligne) : refuse les adresses privées (127.0.0.1, 10.x, 192.168.x…) pour éviter qu'un
# utilisateur fasse sonder le réseau interne du serveur. true en local (base sur le réseau de l'entreprise).
CONNECTEUR_RESEAU_PRIVE = _env("CONNECTEUR_RESEAU_PRIVE", "false").lower() == "true"
CONNECTEUR_TIMEOUT_S = int(_env("CONNECTEUR_TIMEOUT_S", "20"))
CONNECTEUR_MAX_SOURCES = int(_env("CONNECTEUR_MAX_SOURCES", "5"))
CONNECTEUR_MAX_TABLES = int(_env("CONNECTEUR_MAX_TABLES", "150"))
CONNECTEUR_TAILLE_FICHIER_MO = int(_env("CONNECTEUR_TAILLE_FICHIER_MO", "10"))
