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


def test_corps_trop_volumineux_refuse_avant_lecture(client):
    """Un envoi énorme est refusé d'après sa longueur annoncée, avant d'être lu (même sans être connecté)."""
    r = client.post("/sources/fichiers", headers={"Content-Length": str(10 * 1024 ** 3), "Content-Type": "multipart/form-data; boundary=x"},
                    content=b"--x--")
    assert r.status_code == 413
    gros = b"0" * (70 * 1024 * 1024)

    def morceaux():                                  # sans longueur annoncée (envoi « par morceaux »)
        for i in range(0, len(gros), 1024 * 1024):
            yield gros[i:i + 1024 * 1024]
    r = client.post("/sources/fichiers", headers={"Content-Type": "multipart/form-data; boundary=x"}, content=morceaux())
    assert r.status_code in (400, 413)


def test_methodes_http_autorisees_par_cors():
    """Toutes les routes utilisent GET ou POST : une autre méthode serait bloquée par le navigateur (CORS)."""
    from app.main import app
    methodes = {m for r in app.routes for m in (getattr(r, "methods", None) or set())}
    assert methodes <= {"GET", "POST", "HEAD"}, methodes


def test_limite_par_compte(client, analyste, monkeypatch):
    """Au-delà de la limite par minute, le COMPTE est ralenti (429), même depuis plusieurs adresses ; signalé."""
    from app import config, limites, vigilance
    monkeypatch.setattr(config, "RATE_LIMIT_ACTIF", True)
    monkeypatch.setattr(config, "LIMITE_COMPTE_MINUTE", 5)
    signales = []
    monkeypatch.setattr(vigilance, "signaler", lambda *a, **k: signales.append(a))
    limites.oublier_comptes()
    codes = [client.get("/auth/moi", headers=analyste).status_code for _ in range(2)]        # /auth/ : non compté
    codes += [client.get("/clients", headers={**analyste, "X-Forwarded-For": f"41.202.0.{i}"}).status_code for i in range(7)]
    assert codes[:7] == [200] * 7 and codes[7:] == [429, 429]
    assert signales and signales[0][0] == "limite_compte" and signales[0][1] == "analyste1"
    r = client.get("/clients", headers=analyste)
    assert r.status_code == 429 and "ce compte" in r.json()["detail"]
    limites.oublier_comptes()


def test_vigilance_alerte_une_fois_par_rafale(monkeypatch):
    from app import config, courriel, vigilance
    envois = []
    monkeypatch.setattr(courriel, "disponible", lambda: True)
    monkeypatch.setattr(courriel, "envoyer_en_arriere_plan", lambda dest, m: envois.append((dest, m)))
    monkeypatch.setattr(config, "ALERTES_SECURITE_EMAIL", ["securite@voicebank.test"])
    vigilance.oublier()
    for _ in range(vigilance.SEUILS["connexion_refusee"] + 5):
        vigilance.signaler("connexion_refusee", "203.0.113.9", {"identifiant": "rayan"}, None, "203.0.113.9")
    assert len(envois) == 1 and envois[0][0] == "securite@voicebank.test"
    assert "connexions refusées" in envois[0][1].sujet
    # Clé utilisée hors des adresses autorisées : alerte dès le premier appel
    vigilance.signaler("ip_non_autorisee", "7|8.8.8.8", {"cle": "vb_abc"}, None, "8.8.8.8")
    assert len(envois) == 2 and "fuité" in " ".join(envois[1][1].paragraphes)
    vigilance.oublier()


def test_double_auth_obligatoire_pour_abonne_individuel(monkeypatch):
    from app import config, double_auth
    monkeypatch.setattr(config, "DOUBLE_AUTH_ABONNES", "obligatoire")
    monkeypatch.setattr(config, "DOUBLE_AUTH_ADMINS", "obligatoire")
    assert double_auth.requise("client", None)                 # abonné individuel : son propre administrateur
    assert double_auth.requise("client", "admin") and double_auth.requise("admin", None)
    assert not double_auth.requise("client", "analyste") and not double_auth.requise("visiteur", None)
    monkeypatch.setattr(config, "DOUBLE_AUTH_ABONNES", "facultative")
    assert not double_auth.requise("client", None)
