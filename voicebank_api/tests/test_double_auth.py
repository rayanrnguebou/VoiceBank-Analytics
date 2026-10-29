"""Double authentification (code à 6 chiffres) et protection des comptes contre les attaques par mot de passe."""
import re
import time

import pytest

from app import config, double_auth
from tests.test_comptes import BON_MDP, _activer, _admin_sql, _h, _login
from tests.test_recuperation import capturer


def _code_actuel(secret, decalage=0):
    return double_auth.code_totp(secret.replace(" ", ""), int(time.time() // 30) + decalage)


def _activer_2fa(client, h):
    prep = client.post("/auth/2fa/preparer", headers=h).json()
    assert prep["qr_svg"].startswith("<?xml") or "<svg" in prep["qr_svg"]
    assert prep["uri"].startswith("otpauth://totp/VoiceBank%20Analytics:")
    r = client.post("/auth/2fa/activer", headers=h, json={"code": _code_actuel(prep["secret"])})
    assert r.status_code == 200, r.text
    return prep["secret"], r.json()


def test_totp_conforme_rfc6238():
    # Vecteur de test de la RFC 6238 (SHA-1, 8 chiffres ramenés à 6) : T = 59 s → 94287082 → 287082
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert double_auth.code_totp(secret, 59 // 30) == "287082"
    assert double_auth.code_totp(secret, 1111111109 // 30) == "081804"


def test_activation_connexion_et_codes_de_secours(client, admin):
    h = _activer(client, admin, "awa.2fa")
    assert client.get("/auth/2fa", headers=h).json() == {"active": False, "requise": False}
    prep = client.post("/auth/2fa/preparer", headers=h).json()
    assert client.post("/auth/2fa/activer", headers=h, json={"code": "000000"}).status_code == 400
    r = client.post("/auth/2fa/activer", headers=h, json={"code": _code_actuel(prep["secret"])})
    assert r.status_code == 200
    secret, codes = prep["secret"], r.json()["codes_secours"]
    assert len(codes) == 10 and all(re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", c) for c in codes)
    # L'ancienne session est fermée, la nouvelle fonctionne
    assert client.get("/auth/moi", headers=h).status_code == 401
    assert client.get("/auth/moi", headers=_h(r)).status_code == 200
    assert client.get("/auth/2fa", headers=_h(r)).json()["codes_secours_restants"] == 10

    # Connexion : le mot de passe seul ne donne pas de session
    r = _login(client, "awa.2fa", BON_MDP)
    assert r.status_code == 200 and r.json()["double_auth"] and "access_token" not in r.json()
    etape = r.json()["jeton_2fa"]
    # Le jeton intermédiaire ne vaut pas session
    assert client.get("/auth/moi", headers={"Authorization": f"Bearer {etape}"}).status_code == 401
    assert client.post("/auth/2fa/connexion", json={"jeton_2fa": etape, "code": "123456"}).status_code == 401
    # Le code utilisé à l'activation ne repasse pas (rejeu) ; le suivant oui
    code = _code_actuel(secret, 1)
    r = client.post("/auth/2fa/connexion", json={"jeton_2fa": etape, "code": code})
    assert r.status_code == 200 and r.json()["access_token"], r.text
    assert client.post("/auth/2fa/connexion", json={"jeton_2fa": etape, "code": code}).status_code == 401
    # Code de secours : une seule fois
    etape = _login(client, "awa.2fa", BON_MDP).json()["jeton_2fa"]
    assert client.post("/auth/2fa/connexion", json={"jeton_2fa": etape, "code": codes[0].lower()}).status_code == 200
    etape = _login(client, "awa.2fa", BON_MDP).json()["jeton_2fa"]
    assert client.post("/auth/2fa/connexion", json={"jeton_2fa": etape, "code": codes[0]}).status_code == 401
    # Jeton intermédiaire falsifié ou expiré
    import jwt
    faux = jwt.encode({"sub": "awa.2fa", "usage": "2fa", "ver": 0, "exp": int(time.time()) - 10}, config.JWT_SECRET)
    assert client.post("/auth/2fa/connexion", json={"jeton_2fa": faux, "code": codes[1]}).status_code == 401


def test_code_devine_bloque_l_adresse(client, admin):
    h = _activer(client, admin, "ines.2fa")
    _activer_2fa(client, h)
    pirate = {"X-Forwarded-For": "198.51.100.200"}
    etape = client.post("/auth/login", headers=pirate, json={"nom": "ines.2fa", "mot_de_passe": BON_MDP}).json()["jeton_2fa"]
    for _ in range(5):
        client.post("/auth/2fa/connexion", headers=pirate, json={"jeton_2fa": etape, "code": "111111"})
    r = client.post("/auth/2fa/connexion", headers=pirate, json={"jeton_2fa": etape, "code": "222222"})
    assert r.status_code == 429


def test_obligatoire_pour_les_administrateurs(client, admin, monkeypatch):
    _admin_sql("DELETE FROM voicebank.double_authentification WHERE utilisateur = 'chef.2fa'")
    rc = client.post("/admin/utilisateurs", headers=admin, json={"nom": "chef.2fa", "role": "admin"})
    assert rc.status_code == 200, rc.text
    _admin_sql("UPDATE voicebank.utilisateurs SET hash_mdp = %s, doit_changer_mdp = FALSE WHERE nom = 'chef.2fa'",
               (__import__("bcrypt").hashpw(BON_MDP.encode(), __import__("bcrypt").gensalt(4)).decode(),))
    monkeypatch.setattr(config, "DOUBLE_AUTH_ADMINS", "obligatoire")
    r = _login(client, "chef.2fa", BON_MDP)
    assert r.status_code == 200 and r.json()["doit_configurer_2fa"] is True
    h = _h(r)
    # Tant qu'elle n'est pas activée : rien d'autre n'est possible
    assert client.get("/admin/utilisateurs", headers=h).status_code == 403
    assert client.get("/auth/moi", headers=h).json()["doit_configurer_2fa"] is True
    assert client.get("/auth/2fa", headers=h).json()["requise"] is True
    secret, rep = _activer_2fa(client, h)
    assert rep["doit_configurer_2fa"] is False
    assert client.get("/admin/utilisateurs", headers={"Authorization": f"Bearer {rep['access_token']}"}).status_code == 200
    # Impossible à désactiver pour un administrateur
    r = client.post("/auth/2fa/desactiver", headers={"Authorization": f"Bearer {rep['access_token']}"},
                    json={"mot_de_passe": BON_MDP, "code": _code_actuel(secret, 1)})
    assert r.status_code == 403
    # Téléphone perdu : un autre administrateur réinitialise ; pas soi-même
    monkeypatch.setattr(config, "DOUBLE_AUTH_ADMINS", "facultative")        # « rayan » n'a pas de code ici
    assert client.post("/admin/utilisateurs/chef.2fa/double-auth/reinitialiser", headers=admin).status_code == 200
    monkeypatch.setattr(config, "DOUBLE_AUTH_ADMINS", "obligatoire")
    r = _login(client, "chef.2fa", BON_MDP)
    assert "jeton_2fa" not in r.json() and r.json()["doit_configurer_2fa"] is True
    monkeypatch.setattr(config, "DOUBLE_AUTH_ADMINS", "facultative")
    assert client.post("/admin/utilisateurs/rayan/double-auth/reinitialiser", headers=admin).status_code == 400
    liste = {c["nom"]: c for c in client.get("/admin/utilisateurs", headers=admin).json()["data"]}
    assert liste["chef.2fa"]["double_auth"] is False


def test_desactivation_volontaire(client, admin):
    h = _activer(client, admin, "paul.2fa")
    secret, rep = _activer_2fa(client, h)
    h = {"Authorization": f"Bearer {rep['access_token']}"}
    r = client.post("/auth/2fa/desactiver", headers=h, json={"mot_de_passe": "faux", "code": _code_actuel(secret, 1)})
    assert r.status_code == 400
    r = client.post("/auth/2fa/desactiver", headers=h, json={"mot_de_passe": BON_MDP, "code": _code_actuel(secret, 1)})
    assert r.status_code == 200
    assert "access_token" in _login(client, "paul.2fa", BON_MDP).json()


# ── Mode protégé ──────────────────────────────────────────────────────

@pytest.fixture
def boite(monkeypatch):
    envoyes = []
    monkeypatch.setattr(config, "BREVO_API_KEY", "cle-de-test")
    monkeypatch.setattr(config, "EMAIL_EXPEDITEUR", "no-reply@voicebank.test")
    return capturer(monkeypatch, envoyes)


def test_attaque_distribuee_et_lien_de_deblocage(client, admin, boite):
    h = _activer(client, admin, "zoe.cible")
    client.post("/auth/email", headers=h, json={"mot_de_passe": BON_MDP, "email": "zoe@exemple.cm"})
    maison = {"X-Forwarded-For": "203.0.113.10"}
    assert client.post("/auth/login", headers=maison, json={"nom": "zoe.cible", "mot_de_passe": BON_MDP}).status_code == 200
    for n in range(20):                                    # 20 adresses différentes, 1 essai chacune
        client.post("/auth/login", headers={"X-Forwarded-For": f"198.51.100.{n + 1}"},
                    json={"nom": "zoe.cible", "mot_de_passe": f"essai{n}"})
    alerte = [e for e in boite if e["a"] == "zoe@exemple.cm"]
    assert len(alerte) == 1 and "protégé" in alerte[0]["message"].titre
    # Le titulaire, depuis son adresse habituelle : aucun blocage
    assert client.post("/auth/login", headers=maison, json={"nom": "zoe.cible", "mot_de_passe": BON_MDP}).status_code == 200
    # Depuis un nouvel appareil, même avec le bon mot de passe : refus, nouveau lien envoyé au titulaire
    cafe = {"X-Forwarded-For": "192.0.2.99"}
    r = client.post("/auth/login", headers=cafe, json={"nom": "zoe.cible", "mot_de_passe": BON_MDP})
    assert r.status_code == 429 and "protégé" in r.json()["detail"]
    lien = boite[-1]["bouton"][1]
    assert boite[-1]["a"] == "zoe@exemple.cm" and "?deblocage=" in lien
    jeton = lien.split("deblocage=")[1]
    # Le lien ouvert sur le nouvel appareil l'autorise ; il ne sert qu'une fois
    assert client.post("/auth/deblocage", headers=cafe, json={"jeton": jeton}).status_code == 200
    assert client.post("/auth/deblocage", headers=cafe, json={"jeton": jeton}).status_code == 400
    assert client.post("/auth/login", headers=cafe, json={"nom": "zoe.cible", "mot_de_passe": BON_MDP}).status_code == 200
    # Un lien inventé ne marche pas
    assert client.post("/auth/deblocage", json={"jeton": "abc"}).status_code == 400
    liste = {c["nom"]: c for c in client.get("/admin/utilisateurs", headers=admin).json()["data"]}
    assert liste["zoe.cible"]["verrouille"] is True
    client.post("/admin/utilisateurs/zoe.cible/debloquer", headers=admin)
    liste = {c["nom"]: c for c in client.get("/admin/utilisateurs", headers=admin).json()["data"]}
    assert liste["zoe.cible"]["verrouille"] is False


def test_surveillance_externe_et_sentry(client, monkeypatch):
    assert client.head("/health").status_code == 200
    assert client.get("/health/pret").json() == {"status": "ok"}
    from app import db
    monkeypatch.setattr(db, "base_ok", lambda: False)
    assert client.head("/health/pret").status_code == 503
    # Rien de confidentiel ne part chez Sentry
    from app.alertes_erreurs import _nettoyer
    ev = _nettoyer({"request": {"data": {"mot_de_passe": "x"}, "cookies": "c", "query_string": "jeton=1",
                                "headers": {"Authorization": "Bearer x", "User-Agent": "ua", "X-Cle-Taches": "k"}},
                    "user": {"ip_address": "1.2.3.4"},
                    "exception": {"values": [{"stacktrace": {"frames": [{"vars": {"mdp": "secret"}}]}}]}})
    assert ev["request"] == {"headers": {"User-Agent": "ua"}} and "user" not in ev
    assert "vars" not in ev["exception"]["values"][0]["stacktrace"]["frames"][0]
    monkeypatch.setattr(config, "SENTRY_DSN", "")
    from app import alertes_erreurs
    assert alertes_erreurs.demarrer() is False
