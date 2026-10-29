"""Connexion avec un compte d'entreprise Google (Workspace) ou Microsoft (Entra ID / Microsoft 365) — OpenID Connect.

Sécurité :
* aucun compte n'est créé : l'adresse doit correspondre à un compte VoiceBank actif (une invitation reste nécessaire) ;
* état signé et daté (10 min) qui lie le fournisseur, un nonce à usage unique et le défi PKCE ; le vérificateur PKCE
  ne passe jamais par l'adresse de retour (il reste dans l'onglet) ;
* échange du code côté serveur avec la clé secrète ; jeton d'identité vérifié : signature (clés publiques du
  fournisseur), audience, émetteur, expiration, nonce, adresse e-mail vérifiée.
"""
import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt

from . import config, db
from .securite import Utilisateur

DUREE_ETAT_S = 600
_nonces_utilises: dict[str, float] = {}


class SSORefuse(Exception):
    """Connexion par compte d'entreprise refusée (message affichable)."""


def _fournisseurs() -> dict:
    t = config.MICROSOFT_TENANT or "organizations"
    return {
        "google": {
            "nom": "Google", "client_id": config.GOOGLE_CLIENT_ID, "secret": config.GOOGLE_CLIENT_SECRET,
            "autorisation": "https://accounts.google.com/o/oauth2/v2/auth",
            "jeton": "https://oauth2.googleapis.com/token",
            "cles": "https://www.googleapis.com/oauth2/v3/certs",
            "emetteurs": ("https://accounts.google.com", "accounts.google.com"),
        },
        "microsoft": {
            "nom": "Microsoft", "client_id": config.MICROSOFT_CLIENT_ID, "secret": config.MICROSOFT_CLIENT_SECRET,
            "autorisation": f"https://login.microsoftonline.com/{t}/oauth2/v2.0/authorize",
            "jeton": f"https://login.microsoftonline.com/{t}/oauth2/v2.0/token",
            "cles": f"https://login.microsoftonline.com/{t}/discovery/v2.0/keys",
            "emetteurs": None,                    # https://login.microsoftonline.com/<id du locataire>/v2.0
        },
    }


def disponibles() -> list[str]:
    from .securite import mode_base
    if not mode_base():
        return []
    return [k for k, f in _fournisseurs().items() if f["client_id"] and f["secret"]]


def adresse_retour() -> str:
    return f"{config.URL_INTERFACE}/connexion-sso"


def _fournisseur(nom: str) -> dict:
    f = _fournisseurs().get(nom)
    if not f or nom not in disponibles():
        raise SSORefuse("Ce mode de connexion n'est pas activé.")
    return f


def _b64(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode()


def debut(nom: str) -> dict:
    """Adresse vers laquelle envoyer l'utilisateur, et le vérificateur PKCE que l'interface garde dans l'onglet."""
    f = _fournisseur(nom)
    verificateur = _b64(secrets.token_bytes(48))
    defi = _b64(hashlib.sha256(verificateur.encode()).digest())
    nonce = secrets.token_urlsafe(24)
    etat = jwt.encode({"f": nom, "n": nonce, "d": defi, "exp": int(time.time()) + DUREE_ETAT_S, "usage": "sso"},
                      config.JWT_SECRET, algorithm="HS256")
    params = {"client_id": f["client_id"], "response_type": "code", "redirect_uri": adresse_retour(),
              "scope": "openid email profile", "state": etat, "nonce": nonce, "code_challenge": defi,
              "code_challenge_method": "S256", "prompt": "select_account"}
    return {"url": f"{f['autorisation']}?{urlencode(params)}", "verificateur": verificateur, "fournisseur": nom}


def _jwks(url: str):
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def _verifier_etat(nom: str, etat: str, verificateur: str) -> dict:
    try:
        e = jwt.decode(etat, config.JWT_SECRET, algorithms=["HS256"], options={"require": ["exp"]})
    except jwt.PyJWTError:
        raise SSORefuse("Connexion expirée ou invalide : recommence.")
    if e.get("usage") != "sso" or e.get("f") != nom:
        raise SSORefuse("Connexion invalide : recommence.")
    if _b64(hashlib.sha256((verificateur or "").encode()).digest()) != e.get("d"):
        raise SSORefuse("Connexion invalide (vérification PKCE) : recommence depuis le même onglet.")
    maintenant = time.time()
    for n, t in list(_nonces_utilises.items()):
        if t < maintenant:
            del _nonces_utilises[n]
    if e["n"] in _nonces_utilises:
        raise SSORefuse("Cette connexion a déjà été utilisée : recommence.")
    _nonces_utilises[e["n"]] = e["exp"]
    return e


def fin(nom: str, code: str, etat: str, verificateur: str) -> str:
    """Valide le retour du fournisseur et retourne le nom du compte VoiceBank correspondant."""
    f = _fournisseur(nom)
    e = _verifier_etat(nom, etat, verificateur)
    try:
        r = httpx.post(f["jeton"], timeout=15, data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": adresse_retour(),
            "client_id": f["client_id"], "client_secret": f["secret"], "code_verifier": verificateur})
    except httpx.HTTPError:
        raise SSORefuse(f"{f['nom']} est injoignable pour le moment : réessaie.")
    if r.status_code != 200 or "id_token" not in r.json():
        raise SSORefuse(f"{f['nom']} a refusé la connexion : recommence.")
    jeton = r.json()["id_token"]
    try:
        cle = _jwks(f["cles"]).get_signing_key_from_jwt(jeton)
        c = jwt.decode(jeton, cle.key, algorithms=["RS256"], audience=f["client_id"],
                       options={"require": ["exp", "iat", "iss", "aud", "sub"]}, leeway=60)
    except jwt.PyJWTError:
        raise SSORefuse("Identité non vérifiable : recommence.")
    iss = c.get("iss", "")
    if f["emetteurs"] is not None and iss not in f["emetteurs"]:
        raise SSORefuse("Émetteur inattendu : connexion refusée.")
    if nom == "microsoft" and not (iss.startswith("https://login.microsoftonline.com/") and iss.endswith("/v2.0")):
        raise SSORefuse("Émetteur inattendu : connexion refusée.")
    if c.get("nonce") != e["n"]:
        raise SSORefuse("Connexion invalide (nonce) : recommence.")
    if nom == "google":
        if not c.get("email_verified"):
            raise SSORefuse("Adresse Google non vérifiée : connexion refusée.")
        email = c.get("email")
    else:
        # Comptes professionnels Microsoft : l'adresse est l'e-mail, à défaut l'identifiant de connexion (UPN)
        email = c.get("email") or c.get("preferred_username")
    email = (email or "").strip().lower()
    if "@" not in email:
        raise SSORefuse("Aucune adresse e-mail transmise par le fournisseur.")
    l = db.ecrire("SELECT nom, actif, doit_changer_mdp FROM voicebank.utilisateurs WHERE LOWER(email) = :e OR nom = :e "
                  "ORDER BY (nom = :e) DESC LIMIT 1", {"e": email}).lignes
    if not l or not l[0].actif:
        raise SSORefuse(f"Aucun compte VoiceBank actif n'est associé à {email}. Demande une invitation à "
                        "l'administrateur de ton organisation.")
    if l[0].doit_changer_mdp:
        raise SSORefuse("Active d'abord ton compte avec le lien d'invitation reçu par e-mail.")
    db.ecrire("UPDATE voicebank.utilisateurs SET echecs_connexion = 0, verrouille_jusqua = NULL, "
              "derniere_connexion = LOCALTIMESTAMP WHERE nom = :n", {"n": l[0].nom})
    return l[0].nom


def utilisateur(nom: str) -> tuple[Utilisateur, int]:
    from .securite import _ligne
    l = _ligne(nom)
    return Utilisateur(l.nom, l.role, l.doit_changer_mdp, l.acces_expire, l.id_org, l.role_org), l.version_jeton
