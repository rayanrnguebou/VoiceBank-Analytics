"""Authentification (JWT), comptes utilisateurs et contrôle d'accès par rôle.

Où vivent les comptes :
* En base (table voicebank.utilisateurs) : c'est la source de vérité. L'administrateur crée
  les comptes depuis l'interface ; chaque compte reçoit un mot de passe provisoire (valable
  72 h) à changer à la première connexion.
* VOICEBANK_USERS (configuration) sert seulement à AMORCER la base : au démarrage, les comptes
  qui n'existent pas encore y sont ajoutés. Ensuite, la base fait foi (un mot de passe changé
  ou un compte désactivé dans l'interface n'est pas écrasé par la configuration).
* Si la table n'existe pas encore (ancienne base pas encore migrée), l'API fonctionne comme
  avant, uniquement avec VOICEBANK_USERS.

Protections : verrouillage 15 min après 5 échecs, politique de mot de passe, révocation
immédiate des sessions (version du jeton) en cas de changement de mot de passe, de rôle ou de
désactivation, aucun compte supprimé (traçabilité), dernier administrateur protégé.
"""
import logging
import re
import secrets
import string
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config, db

log = logging.getLogger("voicebank")

ROLES = {"analyste", "admin"}
_HASH_BCRYPT = re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}")
NOM_VALIDE = re.compile(r"[a-z0-9][a-z0-9._-]{2,31}")
ALGO = "HS256"
MAX_ECHECS = 5
DUREE_VERROU = timedelta(minutes=15)
DUREE_MDP_PROVISOIRE = timedelta(hours=72)
MDP_MIN = 12
_MDP_COURANTS = {"motdepasse123", "password1234", "azerty123456", "voicebank2026", "123456789012",
                 "motdepasse2026", "bonjour12345", "qwerty123456", "admin1234567"}


@dataclass(frozen=True)
class Utilisateur:
    nom: str
    role: str
    doit_changer: bool = False


class CompteRefuse(Exception):
    """Erreur métier sur la gestion des comptes (message affichable)."""


# ════════════════════════════════════════
# Configuration (amorçage)
# ════════════════════════════════════════

def _charger_comptes() -> dict[str, tuple[str, bytes]]:
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
        raise RuntimeError("VOICEBANK_USERS est vide : il faut au moins le compte administrateur "
                           "de départ (les autres se créent ensuite depuis l'interface)")
    return comptes


COMPTES = _charger_comptes()
# Hash factice : évite de révéler par le temps de réponse si un compte existe.
_HASH_FACTICE = bcrypt.hashpw(b"factice", bcrypt.gensalt())
_mode_base = {"actif": False, "verifie": 0.0}


def mode_base() -> bool:
    """True si la table des comptes existe. Tant qu'elle n'existe pas, revérifié chaque minute."""
    if _mode_base["actif"]:
        return True
    if time.monotonic() - _mode_base["verifie"] < 60 and _mode_base["verifie"]:
        return False
    _mode_base["verifie"] = time.monotonic()
    try:
        _mode_base["actif"] = bool(db.ecrire("SELECT to_regclass('voicebank.utilisateurs') IS NOT NULL").scalar())
    except Exception:
        log.warning("Table des comptes inaccessible pour l'instant")
    return _mode_base["actif"]


def amorcer():
    """Ajoute en base les comptes de VOICEBANK_USERS qui n'y sont pas encore."""
    if not mode_base():
        log.warning("Table voicebank.utilisateurs absente : comptes lus dans VOICEBANK_USERS uniquement. "
                    "Mets la base à jour (voicebank_db/securite/migrer.sh) pour gérer les comptes "
                    "depuis l'interface.")
        return
    for nom, (role, hash_) in COMPTES.items():
        r = db.ecrire("INSERT INTO voicebank.utilisateurs (nom, role, hash_mdp, doit_changer_mdp, cree_par) "
                      "VALUES (:n, :r, :h, FALSE, 'configuration') ON CONFLICT (nom) DO NOTHING",
                      {"n": nom, "r": role, "h": hash_.decode()})
        if r.rowcount:
            log.info("Compte '%s' (%s) ajouté depuis la configuration", nom, role)


# ════════════════════════════════════════
# Mots de passe
# ════════════════════════════════════════

def hacher(mdp: str) -> str:
    return bcrypt.hashpw(mdp.encode()[:72], bcrypt.gensalt(12)).decode()


def verifier_politique(mdp: str, nom: str):
    """Lève CompteRefuse si le mot de passe est trop faible."""
    if len(mdp) < MDP_MIN:
        raise CompteRefuse(f"Le mot de passe doit faire au moins {MDP_MIN} caractères")
    if len(mdp.encode()) > 72:
        raise CompteRefuse("Le mot de passe est trop long (72 octets maximum)")
    familles = sum(bool(re.search(m, mdp)) for m in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if familles < 3:
        raise CompteRefuse("Mélange au moins trois types de caractères : minuscules, majuscules, "
                           "chiffres, symboles")
    bas = mdp.lower()
    if nom.lower() in bas or bas in _MDP_COURANTS or len(set(bas)) < 5:
        raise CompteRefuse("Mot de passe trop facile à deviner (il contient l'identifiant ou est trop courant)")


def mdp_provisoire() -> str:
    """16 caractères aléatoires, sans caractères ambigus (0/O, 1/l/I)."""
    alpha = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    while True:
        mdp = "".join(secrets.choice(alpha) for _ in range(14)) + secrets.choice("-_.!") + secrets.choice("23456789")
        mdp = "".join(secrets.SystemRandom().sample(mdp, len(mdp)))
        if re.search(r"[a-z]", mdp) and re.search(r"[A-Z]", mdp):
            return mdp


# ════════════════════════════════════════
# Connexion
# ════════════════════════════════════════

def _ligne(nom: str):
    # Les dates sont comparées dans la base (LOCALTIMESTAMP) : pas de souci de fuseau horaire.
    r = db.ecrire("SELECT nom, role, hash_mdp, actif, doit_changer_mdp, echecs_connexion, version_jeton, "
                  "COALESCE(verrouille_jusqua > LOCALTIMESTAMP, FALSE) AS verrouille, "
                  "COALESCE(doit_changer_mdp AND mdp_provisoire_expire < LOCALTIMESTAMP, FALSE) AS expire "
                  "FROM voicebank.utilisateurs WHERE nom = :n", {"n": nom})
    return r.lignes[0] if r.lignes else None


def authentifier(nom: str, mot_de_passe: str) -> tuple[Utilisateur, int] | None:
    """Retourne (utilisateur, version du jeton) ou None. Même message d'erreur pour tous les
    cas (compte inconnu, désactivé, verrouillé, mot de passe faux) : rien n'est révélé."""
    mdp = mot_de_passe.encode()[:72]
    if not mode_base():
        role, hash_ = COMPTES.get(nom, (None, _HASH_FACTICE))
        ok = bcrypt.checkpw(mdp, hash_)
        return (Utilisateur(nom, role), 0) if ok and role else None

    l = _ligne(nom)
    if l is None:
        bcrypt.checkpw(mdp, _HASH_FACTICE)
        return None
    if not l.actif or l.verrouille:
        bcrypt.checkpw(mdp, _HASH_FACTICE)
        return None
    if not bcrypt.checkpw(mdp, l.hash_mdp.encode()):
        echecs = l.echecs_connexion + 1
        if echecs >= MAX_ECHECS:
            db.ecrire("UPDATE voicebank.utilisateurs SET echecs_connexion = 0, "
                      "verrouille_jusqua = LOCALTIMESTAMP + :v WHERE nom = :n", {"n": nom, "v": DUREE_VERROU})
            log.warning("Compte '%s' verrouillé %s après %d échecs", nom, DUREE_VERROU, MAX_ECHECS)
        else:
            db.ecrire("UPDATE voicebank.utilisateurs SET echecs_connexion = :e WHERE nom = :n",
                      {"n": nom, "e": echecs})
        return None
    if l.expire:
        return None     # mot de passe provisoire expiré : l'administrateur doit le réinitialiser
    db.ecrire("UPDATE voicebank.utilisateurs SET echecs_connexion = 0, verrouille_jusqua = NULL, "
              "derniere_connexion = LOCALTIMESTAMP WHERE nom = :n", {"n": nom})
    return Utilisateur(l.nom, l.role, l.doit_changer_mdp), l.version_jeton


def creer_jeton(u: Utilisateur, version: int = 0) -> str:
    maintenant = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": u.nom, "role": u.role, "ver": version, "iat": maintenant,
        "exp": maintenant + timedelta(minutes=config.JWT_DUREE_MIN),
    }, config.JWT_SECRET, algorithm=ALGO)


_bearer = HTTPBearer(auto_error=False)


def _depuis_jeton(cred: HTTPAuthorizationCredentials | None) -> Utilisateur:
    erreur = HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise",
                           headers={"WWW-Authenticate": "Bearer"})
    if cred is None:
        raise erreur
    try:
        data = jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=[ALGO],
                          options={"require": ["exp", "sub", "role"]})
    except jwt.PyJWTError:
        raise erreur
    if not mode_base():
        # Le compte doit toujours exister avec le même rôle (révocation par configuration).
        if COMPTES.get(data["sub"], (None,))[0] != data["role"]:
            raise erreur
        return Utilisateur(data["sub"], data["role"])
    r = db.ecrire("SELECT role, actif, doit_changer_mdp, version_jeton FROM voicebank.utilisateurs "
                  "WHERE nom = :n", {"n": data["sub"]})
    l = r.lignes[0] if r.lignes else None
    # Compte supprimé, désactivé, rôle changé ou mot de passe changé : la session est révoquée.
    if l is None or not l.actif or l.role != data["role"] or l.version_jeton != data.get("ver"):
        raise erreur
    return Utilisateur(data["sub"], l.role, l.doit_changer_mdp)


def utilisateur_authentifie(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Utilisateur:
    """Accepte aussi un compte dont le mot de passe provisoire doit être changé."""
    return _depuis_jeton(cred)


def utilisateur_courant(u: Utilisateur = Depends(utilisateur_authentifie)) -> Utilisateur:
    if u.doit_changer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Change ton mot de passe provisoire pour continuer")
    return u


def admin_requis(u: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
    if u.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux administrateurs")
    return u


# ════════════════════════════════════════
# Gestion des comptes
# ════════════════════════════════════════

def _exiger_base():
    if not mode_base():
        raise CompteRefuse("Les comptes sont encore gérés par la configuration (VOICEBANK_USERS). "
                           "Mets la base à jour avec voicebank_db/securite/migrer.sh pour les gérer ici.")


def changer_mot_de_passe(nom: str, actuel: str, nouveau: str) -> int:
    """Retourne la nouvelle version du jeton (les autres sessions sont déconnectées)."""
    _exiger_base()
    l = _ligne(nom)
    if l is None or not bcrypt.checkpw(actuel.encode()[:72], l.hash_mdp.encode()):
        raise CompteRefuse("Mot de passe actuel incorrect")
    if actuel == nouveau:
        raise CompteRefuse("Le nouveau mot de passe doit être différent de l'actuel")
    verifier_politique(nouveau, nom)
    r = db.ecrire("UPDATE voicebank.utilisateurs SET hash_mdp = :h, doit_changer_mdp = FALSE, "
                  "mdp_provisoire_expire = NULL, date_modif_mdp = LOCALTIMESTAMP, "
                  "version_jeton = version_jeton + 1 WHERE nom = :n RETURNING version_jeton",
                  {"n": nom, "h": hacher(nouveau)})
    return r.scalar()


def lister_comptes() -> list[dict]:
    _exiger_base()
    r = db.ecrire("SELECT nom, role, actif, doit_changer_mdp, mdp_provisoire_expire, cree_par, date_creation, "
                  "date_modif_mdp, derniere_connexion, "
                  "COALESCE(verrouille_jusqua > LOCALTIMESTAMP, FALSE) AS verrouille, "
                  "COALESCE(doit_changer_mdp AND mdp_provisoire_expire < LOCALTIMESTAMP, FALSE) AS provisoire_expire "
                  "FROM voicebank.utilisateurs ORDER BY actif DESC, nom")
    return [{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in l._mapping.items()}
            for l in r.lignes]


def creer_compte(nom: str, role: str, par: str) -> str:
    """Crée le compte et retourne le mot de passe provisoire (affiché une seule fois)."""
    _exiger_base()
    if not NOM_VALIDE.fullmatch(nom):
        raise CompteRefuse("Identifiant invalide : 3 à 32 caractères, minuscules, chiffres, . _ - "
                           "(ex. : jean.mballa)")
    if role not in ROLES:
        raise CompteRefuse("Rôle inconnu")
    mdp = mdp_provisoire()
    r = db.ecrire("INSERT INTO voicebank.utilisateurs (nom, role, hash_mdp, doit_changer_mdp, "
                  "mdp_provisoire_expire, cree_par) VALUES (:n, :r, :h, TRUE, LOCALTIMESTAMP + :e, :p) "
                  "ON CONFLICT (nom) DO NOTHING",
                  {"n": nom, "r": role, "h": hacher(mdp), "e": DUREE_MDP_PROVISOIRE, "p": par})
    if not r.rowcount:
        raise CompteRefuse("Cet identifiant existe déjà (un compte désactivé garde son identifiant)")
    return mdp


def reinitialiser(nom: str) -> str:
    """Nouveau mot de passe provisoire, déverrouille et déconnecte les sessions en cours."""
    _exiger_base()
    mdp = mdp_provisoire()
    r = db.ecrire("UPDATE voicebank.utilisateurs SET hash_mdp = :h, doit_changer_mdp = TRUE, "
                  "mdp_provisoire_expire = LOCALTIMESTAMP + :e, echecs_connexion = 0, verrouille_jusqua = NULL, "
                  "date_modif_mdp = LOCALTIMESTAMP, version_jeton = version_jeton + 1 WHERE nom = :n",
                  {"n": nom, "h": hacher(mdp), "e": DUREE_MDP_PROVISOIRE})
    if not r.rowcount:
        raise CompteRefuse("Compte introuvable")
    return mdp


def modifier(nom: str, par: str, role: str | None = None, actif: bool | None = None) -> dict:
    """Change le rôle et/ou active/désactive. Retourne les changements effectués."""
    _exiger_base()
    l = _ligne(nom)
    if l is None:
        raise CompteRefuse("Compte introuvable")
    if role is not None and role not in ROLES:
        raise CompteRefuse("Rôle inconnu")
    if nom == par and (actif is False or (role and role != "admin")):
        raise CompteRefuse("Tu ne peux pas désactiver ton propre compte ni retirer tes droits d'administrateur")
    perd_admin = l.role == "admin" and l.actif and (actif is False or (role and role != "admin"))
    if perd_admin:
        r = db.ecrire("SELECT COUNT(*) FROM voicebank.utilisateurs WHERE role = 'admin' AND actif AND nom <> :n",
                      {"n": nom})
        if not r.scalar():
            raise CompteRefuse("Il doit toujours rester au moins un administrateur actif")
    changements = {}
    if role is not None and role != l.role:
        changements["role"] = role
    if actif is not None and actif != l.actif:
        changements["actif"] = actif
    if changements:
        db.ecrire("UPDATE voicebank.utilisateurs SET role = COALESCE(:r, role), actif = COALESCE(:a, actif), "
                  "echecs_connexion = 0, verrouille_jusqua = NULL, version_jeton = version_jeton + 1 "
                  "WHERE nom = :n", {"n": nom, "r": changements.get("role"), "a": changements.get("actif")})
    return changements
