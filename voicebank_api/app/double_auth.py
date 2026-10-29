"""Double authentification : code à 6 chiffres d'une application (TOTP, RFC 6238), compatible Google Authenticator,
Microsoft Authenticator, Authy, 1Password…

* Obligatoire pour les administrateurs (plateforme et organisations) quand DOUBLE_AUTH_ADMINS=obligatoire ;
  facultative pour les autres comptes.
* Secret chiffré en base (même clé que les identifiants des sources) ; un code déjà utilisé est refusé (rejeu).
* 10 codes de secours à usage unique (seule leur empreinte est gardée) si le téléphone est perdu.
"""
import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
from urllib.parse import quote

import segno

from . import config, db

PERIODE = 30
CHIFFRES = 6
TOLERANCE = 1                 # un pas avant / après (horloge du téléphone décalée de ±30 s)
NB_CODES_SECOURS = 10
EMETTEUR = "VoiceBank Analytics"


class DoubleAuthRefusee(Exception):
    """Message affichable."""


def _chiffrer(secret: str) -> str:
    from .connecteur.connexion import chiffrer
    return chiffrer({"totp": secret})


def _dechiffrer(jeton: str) -> str:
    from .connecteur.connexion import dechiffrer
    return dechiffrer(jeton)["totp"]


def code_totp(secret: str, pas: int) -> str:
    cle = base64.b32decode(secret + "=" * (-len(secret) % 8))
    h = hmac.new(cle, struct.pack(">Q", pas), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** CHIFFRES).zfill(CHIFFRES)


def _pas_valide(secret: str, code: str, dernier_pas: int, maintenant: float | None = None) -> int | None:
    pas = int((maintenant or time.time()) // PERIODE)
    for p in range(pas - TOLERANCE, pas + TOLERANCE + 1):
        if p > dernier_pas and hmac.compare_digest(code_totp(secret, p), code):
            return p
    return None


def _empreinte(code: str) -> str:
    return hashlib.sha256(f"{config.JWT_SECRET[:16]}:{code.replace('-', '').upper()}".encode()).hexdigest()


def requise(role: str, role_org: str | None) -> bool:
    """Les administrateurs doivent l'activer (sauf si la configuration la rend facultative)."""
    return config.DOUBLE_AUTH_ADMINS == "obligatoire" and (role == "admin" or (role == "client" and role_org == "admin"))


def active(nom: str) -> bool:
    return bool(db.ecrire("SELECT active FROM voicebank.double_authentification WHERE utilisateur = :n",
                          {"n": nom}).scalar())


def etat(nom: str) -> dict:
    l = db.ecrire("SELECT active, date_activation, jsonb_array_length(codes_secours) AS restants "
                  "FROM voicebank.double_authentification WHERE utilisateur = :n", {"n": nom}).lignes
    if not l or not l[0].active:
        return {"active": False}
    return {"active": True, "date_activation": l[0].date_activation.isoformat() if l[0].date_activation else None,
            "codes_secours_restants": l[0].restants}


def preparer(nom: str) -> dict:
    """Nouveau secret (pas encore actif) : QR code à scanner avec l'application."""
    if active(nom):
        raise DoubleAuthRefusee("La double authentification est déjà active.")
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    db.ecrire("INSERT INTO voicebank.double_authentification (utilisateur, secret_chiffre) VALUES (:n, :s) "
              "ON CONFLICT (utilisateur) DO UPDATE SET secret_chiffre = :s, active = FALSE, dernier_pas = 0, "
              "codes_secours = '[]'", {"n": nom, "s": _chiffrer(secret)})
    uri = (f"otpauth://totp/{quote(EMETTEUR)}:{quote(nom)}?secret={secret}&issuer={quote(EMETTEUR)}"
           f"&algorithm=SHA1&digits={CHIFFRES}&period={PERIODE}")
    tampon = io.BytesIO()
    segno.make(uri, error="m").save(tampon, kind="svg", scale=5, border=2, dark="#0b1f17", light="#ffffff")
    return {"secret": " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)), "uri": uri,
            "qr_svg": tampon.getvalue().decode()}


def _codes_secours() -> list[str]:
    alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ["".join(secrets.choice(alpha) for _ in range(4)) + "-" + "".join(secrets.choice(alpha) for _ in range(4))
            for _ in range(NB_CODES_SECOURS)]


def activer(nom: str, code: str) -> list[str]:
    """Vérifie le premier code de l'application et active ; retourne les codes de secours (affichés une fois)."""
    l = db.ecrire("SELECT secret_chiffre, active, dernier_pas FROM voicebank.double_authentification WHERE utilisateur = :n",
                  {"n": nom}).lignes
    if not l:
        raise DoubleAuthRefusee("Commence par scanner le QR code.")
    if l[0].active:
        raise DoubleAuthRefusee("La double authentification est déjà active.")
    pas = _pas_valide(_dechiffrer(l[0].secret_chiffre), (code or "").strip().replace(" ", ""), l[0].dernier_pas)
    if pas is None:
        raise DoubleAuthRefusee("Code incorrect : vérifie que l'heure de ton téléphone est à jour, puis saisis le code affiché.")
    codes = _codes_secours()
    import json
    db.ecrire("UPDATE voicebank.double_authentification SET active = TRUE, dernier_pas = :p, date_activation = LOCALTIMESTAMP, "
              "codes_secours = CAST(:c AS JSONB) WHERE utilisateur = :n",
              {"n": nom, "p": pas, "c": json.dumps([_empreinte(c) for c in codes])})
    return codes


def verifier(nom: str, code: str) -> str:
    """Code de l'application ou code de secours. Retourne « application » ou « secours » ; lève sinon."""
    code = (code or "").strip().replace(" ", "")
    l = db.ecrire("SELECT secret_chiffre, dernier_pas, codes_secours FROM voicebank.double_authentification "
                  "WHERE utilisateur = :n AND active", {"n": nom}).lignes
    if not l:
        raise DoubleAuthRefusee("Double authentification non activée.")
    if code.isdigit() and len(code) == CHIFFRES:
        pas = _pas_valide(_dechiffrer(l[0].secret_chiffre), code, l[0].dernier_pas)
        # Mise à jour conditionnelle : deux requêtes simultanées avec le même code ne passent pas toutes les deux
        if pas is not None and db.ecrire("UPDATE voicebank.double_authentification SET dernier_pas = :p "
                                         "WHERE utilisateur = :n AND dernier_pas < :p", {"n": nom, "p": pas}).rowcount:
            return "application"
        raise DoubleAuthRefusee("Code incorrect ou déjà utilisé.")
    e = _empreinte(code)
    if e in (l[0].codes_secours or []) and db.ecrire(
            "UPDATE voicebank.double_authentification SET codes_secours = codes_secours - :e "
            "WHERE utilisateur = :n AND jsonb_exists(codes_secours, :e)", {"n": nom, "e": e}).rowcount:
        return "secours"
    raise DoubleAuthRefusee("Code incorrect ou déjà utilisé.")


def nouveaux_codes_secours(nom: str) -> list[str]:
    import json
    codes = _codes_secours()
    r = db.ecrire("UPDATE voicebank.double_authentification SET codes_secours = CAST(:c AS JSONB) "
                  "WHERE utilisateur = :n AND active", {"n": nom, "c": json.dumps([_empreinte(c) for c in codes])})
    if not r.rowcount:
        raise DoubleAuthRefusee("Double authentification non activée.")
    return codes


def desactiver(nom: str):
    db.ecrire("DELETE FROM voicebank.double_authentification WHERE utilisateur = :n", {"n": nom})
