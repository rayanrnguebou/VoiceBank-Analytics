"""Compléments de sécurité : anti-robot (Turnstile)."""
import httpx

from app import antirobot, config


class _Rep:
    def __init__(self, ok, code=200):
        self.status_code, self._ok = code, ok

    def json(self):
        return {"success": self._ok}


def _essai(client, email, captcha=None):
    return client.post("/auth/essai", json={"nom_complet": "Awa Robot", "email": email, "mot_de_passe": "Baobab-Douala-2026",
                                            "profil": "autre", "accepte_conditions": True, "captcha": captcha})


def test_anti_robot_inactif_sans_cle(client, monkeypatch):
    monkeypatch.setattr(config, "TURNSTILE_SECRET", "")
    assert client.get("/auth/options").json()["anti_robot"] is False
    assert _essai(client, "sans.captcha@exemple.cm").status_code == 200


def test_anti_robot_actif(client, monkeypatch):
    monkeypatch.setattr(config, "TURNSTILE_SECRET", "secret-de-test")
    assert client.get("/auth/options").json()["anti_robot"] is True
    vus = []
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (vus.append(kw["data"]), _Rep(kw["data"]["response"] == "bon"))[1])
    r = _essai(client, "robot1@exemple.cm")
    assert r.status_code == 400 and "anti-robot" in r.json()["detail"]
    assert _essai(client, "robot2@exemple.cm", "mauvais").status_code == 400
    assert _essai(client, "humain@exemple.cm", "bon").status_code == 200
    assert vus[-1]["secret"] == "secret-de-test"
    # Mot de passe oublié protégé aussi (pas d'inondation d'e-mails)
    r = client.post("/auth/oubli", json={"identifiant": "humain@exemple.cm"})
    assert r.status_code in (400, 503)


def test_anti_robot_cloudflare_injoignable_refuse(client, monkeypatch):
    monkeypatch.setattr(config, "TURNSTILE_SECRET", "secret-de-test")

    def panne(url, **kw):
        raise httpx.ConnectError("injoignable")
    monkeypatch.setattr(httpx, "post", panne)
    r = _essai(client, "panne@exemple.cm", "bon")
    assert r.status_code == 400 and "indisponible" in r.json()["detail"]
    assert antirobot.actif()


def test_connexion_verifiee_controle_le_certificat(monkeypatch):
    """Mode « vérifié » : identité du serveur contrôlée (verify-full / check_hostname), jamais pour SQL Server."""
    import certifi
    import pytest

    from app.connecteur import connexion
    monkeypatch.setattr(connexion, "verifier_hote", lambda h: "93.184.216.34")
    captures = {}
    monkeypatch.setattr(connexion, "create_engine", lambda url, **kw: captures.update(url=url, **kw) or "moteur")
    cfg = {"hote": "base.exemple.cm", "utilisateur": "lecteur", "mot_de_passe": "x", "base": "b", "ssl": "verifie"}
    connexion.moteur("postgresql", cfg)
    assert captures["connect_args"]["sslmode"] == "verify-full"
    assert captures["connect_args"]["sslrootcert"] == certifi.where()
    assert captures["url"].host == "base.exemple.cm" and captures["connect_args"]["hostaddr"] == "93.184.216.34"
    connexion.moteur("mysql", cfg)
    assert captures["connect_args"]["ssl"] == {"ca": certifi.where(), "check_hostname": True}
    assert captures["url"].host == "base.exemple.cm"
    connexion.moteur("mysql", {**cfg, "ssl": "exige"})
    assert captures["connect_args"]["ssl"] == {"check_hostname": False} and captures["url"].host == "93.184.216.34"
    with pytest.raises(connexion.ConnexionRefusee, match="SQL Server"):
        connexion.moteur("sqlserver", cfg)
    assert "Certificat du serveur non reconnu" in connexion.message_erreur(Exception("SSL: certificate verify failed"))


def test_rotation_de_la_cle_des_sources(monkeypatch):
    """Nouvelle clé + ancienne : tout reste lisible ; après rechiffrement, l'ancienne clé n'est plus nécessaire."""
    import pytest
    from cryptography.fernet import InvalidToken

    from app.connecteur import connexion
    monkeypatch.setattr(config, "CLE_SOURCES", "ancienne-cle-tres-longue-et-secrete-0001")
    monkeypatch.setattr(config, "CLE_SOURCES_ANCIENNES", [])
    jeton = connexion.chiffrer({"mot_de_passe": "Secret-2026"})
    monkeypatch.setattr(config, "CLE_SOURCES", "nouvelle-cle-tres-longue-et-secrete-0002")
    with pytest.raises(connexion.ConnexionRefusee):
        connexion.dechiffrer(jeton)                        # sans l'ancienne clé : illisible
    monkeypatch.setattr(config, "CLE_SOURCES_ANCIENNES", ["ancienne-cle-tres-longue-et-secrete-0001"])
    assert connexion.dechiffrer(jeton)["mot_de_passe"] == "Secret-2026"
    neuf = connexion.rechiffrer(jeton)
    monkeypatch.setattr(config, "CLE_SOURCES_ANCIENNES", [])
    assert connexion.dechiffrer(neuf)["mot_de_passe"] == "Secret-2026"   # la nouvelle clé seule suffit
    with pytest.raises(InvalidToken):
        connexion.rechiffrer("jeton-invalide")
