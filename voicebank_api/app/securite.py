"""Authentification (JWT) et contrôle d'accès par rôle."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

ROLES = {"analyste", "admin"}
_HASH_BCRYPT = re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}")
ALGO = "HS256"


@dataclass(frozen=True)
class Utilisateur:
    nom: str
    role: str


def _charger_comptes() -> dict:
    comptes = {}
    for entree in filter(None, (e.strip() for e in config.VOICEBANK_USERS.split(","))):
        try:
            nom, role, hash_ = entree.split(":", 2)
        except ValueError:
            raise RuntimeError("VOICEBANK_USERS mal formé (attendu nom:role:hash)")
        if role not in ROLES:
            raise RuntimeError(f"Rôle inconnu '{role}' (attendu : {', '.join(sorted(ROLES))})")
        if not _HASH_BCRYPT.fullmatch(hash_):
            raise RuntimeError(
                f"VOICEBANK_USERS : le hash du compte '{nom}' n'est pas un hash bcrypt valide "
                f"(60 caractères commençant par $2b$). Génère-le avec : python -m app.outils.creer_hash "
                f"et mets la valeur entre apostrophes simples dans .env")
        comptes[nom] = (role, hash_.encode())
    if not comptes:
        raise RuntimeError("VOICEBANK_USERS est vide : aucun compte ne pourrait se connecter")
    return comptes


COMPTES = _charger_comptes()
# Hash factice : évite de révéler par le temps de réponse si un compte existe.
_HASH_FACTICE = bcrypt.hashpw(b"factice", bcrypt.gensalt())


def authentifier(nom: str, mot_de_passe: str) -> Utilisateur | None:
    role, hash_ = COMPTES.get(nom, (None, _HASH_FACTICE))
    ok = bcrypt.checkpw(mot_de_passe.encode()[:72], hash_)
    return Utilisateur(nom, role) if ok and role else None


def creer_jeton(u: Utilisateur) -> str:
    maintenant = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": u.nom, "role": u.role, "iat": maintenant,
        "exp": maintenant + timedelta(minutes=config.JWT_DUREE_MIN),
    }, config.JWT_SECRET, algorithm=ALGO)


_bearer = HTTPBearer(auto_error=False)


def utilisateur_courant(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Utilisateur:
    erreur = HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise",
                           headers={"WWW-Authenticate": "Bearer"})
    if cred is None:
        raise erreur
    try:
        data = jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=[ALGO],
                          options={"require": ["exp", "sub", "role"]})
    except jwt.PyJWTError:
        raise erreur
    # Le compte doit toujours exister avec le même rôle (révocation par config).
    if COMPTES.get(data["sub"], (None,))[0] != data["role"]:
        raise erreur
    return Utilisateur(data["sub"], data["role"])


def admin_requis(u: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
    if u.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux administrateurs")
    return u
