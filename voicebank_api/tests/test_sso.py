"""Connexion avec un compte d'entreprise (OpenID Connect) : jeton d'identité signé par une clé locale."""
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import config, sso

CLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
EMAIL = "sso.client@exemple.cm"


class _Cle:
    key = CLE.public_key()


class _Jwks:
    def get_signing_key_from_jwt(self, jeton):
        return _Cle()


class _Rep:
    def __init__(self, data, code=200):
        self.status_code, self._d = code, data

    def json(self):
        return self._d


@pytest.fixture
def google(client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "id-google")
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "secret-google")
    monkeypatch.setattr(config, "TURNSTILE_SECRET", "")
    monkeypatch.setattr(sso, "_jwks", lambda url: _Jwks())
    client.post("/auth/essai", json={"nom_complet": "Client SSO", "email": EMAIL, "mot_de_passe": "Baobab-Douala-2026",
                                     "profil": "autre", "accepte_conditions": True})
    return monkeypatch


def _id_token(n, **modif):
    c = {"iss": "https://accounts.google.com", "aud": "id-google", "sub": "123", "email": EMAIL,
         "email_verified": True, "nonce": n, "iat": int(time.time()), "exp": int(time.time()) + 600}
    c.update(modif)
    return jwt.encode({k: v for k, v in c.items() if v is not None}, CLE, algorithm="RS256")


def _parcours(client, mp, **modif):
    d = client.get("/auth/sso/google/debut").json()
    q = parse_qs(urlparse(d["url"]).query)
    assert q["redirect_uri"] == [f"{config.URL_INTERFACE}/connexion-sso"] and q["code_challenge_method"] == ["S256"]
    vus = []
    mp.setattr(httpx, "post", lambda url, **kw: (vus.append(kw["data"]), _Rep({"id_token": _id_token(q["nonce"][0], **modif)}))[1])
    r = client.post("/auth/sso/google/fin", json={"code": "abc", "etat": q["state"][0], "verificateur": d["verificateur"]})
    return r, q, d, vus


def test_sso_masque_sans_configuration(client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "")
    monkeypatch.setattr(config, "MICROSOFT_CLIENT_ID", "")
    assert client.get("/auth/options").json()["sso"] == []
    assert client.get("/auth/sso/google/debut").status_code == 404
    assert client.get("/auth/sso/inconnu/debut").status_code == 404


def test_sso_connecte_un_compte_existant(client, google):
    assert client.get("/auth/options").json()["sso"] == ["google"]
    r, q, d, vus = _parcours(client, google)
    assert r.status_code == 200, r.text
    assert r.json()["utilisateur"] == EMAIL and r.json()["access_token"]
    assert vus[0]["code_verifier"] == d["verificateur"] and vus[0]["client_secret"] == "secret-google"
    # L'état ne sert qu'une fois (rejeu refusé)
    google.setattr(httpx, "post", lambda url, **kw: _Rep({"id_token": _id_token(q["nonce"][0])}))
    r = client.post("/auth/sso/google/fin", json={"code": "abc", "etat": q["state"][0], "verificateur": d["verificateur"]})
    assert r.status_code == 401 and "déjà été utilisée" in r.json()["detail"]


@pytest.mark.parametrize("modif, motif", [
    ({"email": "inconnu@exemple.cm"}, "Aucun compte"),
    ({"email_verified": False}, "non vérifiée"),
    ({"aud": "autre-application"}, "non vérifiable"),
    ({"iss": "https://pirate.exemple"}, "Émetteur"),
    ({"nonce": "autre"}, "nonce"),
    ({"exp": int(time.time()) - 3600}, "non vérifiable"),
])
def test_sso_refuse(client, google, modif, motif):
    r, *_ = _parcours(client, google, **modif)
    assert r.status_code == 401 and motif in r.json()["detail"], r.text


def test_sso_pkce_et_etat(client, google):
    d = client.get("/auth/sso/google/debut").json()
    etat = parse_qs(urlparse(d["url"]).query)["state"][0]
    # Vérificateur d'un autre onglet
    autre = client.get("/auth/sso/google/debut").json()["verificateur"]
    r = client.post("/auth/sso/google/fin", json={"code": "abc", "etat": etat, "verificateur": autre})
    assert r.status_code == 401 and "PKCE" in r.json()["detail"]
    # État falsifié ou destiné à un autre fournisseur
    faux = jwt.encode({"f": "google", "n": "x", "d": "y", "exp": int(time.time()) + 60, "usage": "sso"}, "x" * 40)
    r = client.post("/auth/sso/google/fin", json={"code": "abc", "etat": faux, "verificateur": d["verificateur"]})
    assert r.status_code == 401
    google.setattr(config, "MICROSOFT_CLIENT_ID", "id-ms")
    google.setattr(config, "MICROSOFT_CLIENT_SECRET", "secret-ms")
    r = client.post("/auth/sso/microsoft/fin", json={"code": "abc", "etat": etat, "verificateur": d["verificateur"]})
    assert r.status_code == 401


def test_sso_compte_desactive(client, google):
    from app import db
    db.ecrire("UPDATE voicebank.utilisateurs SET actif = FALSE WHERE nom = :n", {"n": EMAIL})
    try:
        r, *_ = _parcours(client, google)
        assert r.status_code == 401 and "Aucun compte" in r.json()["detail"]
    finally:
        db.ecrire("UPDATE voicebank.utilisateurs SET actif = TRUE WHERE nom = :n", {"n": EMAIL})


def test_sso_puis_code_a_6_chiffres(client, google):
    """Google / Microsoft ne dispensent pas du code de l'application si la double authentification est active."""
    from app import double_auth
    prep = double_auth.preparer(EMAIL)
    double_auth.activer(EMAIL, double_auth.code_totp(prep["secret"].replace(" ", ""), int(time.time() // 30)))
    try:
        r, *_ = _parcours(client, google)
        assert r.status_code == 200 and r.json()["double_auth"] and "access_token" not in r.json()
        code = double_auth.code_totp(prep["secret"].replace(" ", ""), int(time.time() // 30) + 1)
        r = client.post("/auth/2fa/connexion", json={"jeton_2fa": r.json()["jeton_2fa"], "code": code})
        assert r.status_code == 200 and r.json()["utilisateur"] == EMAIL
    finally:
        double_auth.desactiver(EMAIL)
