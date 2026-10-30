"""Approbation sur le téléphone : notification, choix du nombre, refus, expiration, repli sur le code à 6 chiffres."""
import pytest

from app import approbation
from tests.test_comptes import BON_MDP, _activer, _admin_sql, _h, _login
from tests.test_double_auth import _activer_2fa, _code_actuel
from tests.test_recuperation import capturer

ABONNEMENT = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc123", "keys": {"p256dh": "BPub" + "x" * 80, "auth": "aut" + "h" * 19}}


@pytest.fixture
def notifications(monkeypatch):
    envoyees = []
    monkeypatch.setattr(approbation, "ENVOI_EN_FOND", False)
    monkeypatch.setattr(approbation, "_envoyer", lambda abo, contenu: envoyees.append((abo, contenu)) or True)
    return envoyees


def _compte_avec_telephone(client, admin, nom):
    h = _activer(client, admin, nom)
    secret_totp, r = _activer_2fa(client, h)
    h = {"Authorization": f"Bearer {r['access_token']}"}
    codes = r["codes_secours"]
    t = client.post("/auth/approbation/telephones", headers=h,
                    json={"code": codes[0], "nom": "Samsung Galaxy · Android", "abonnement": ABONNEMENT})
    assert t.status_code == 200, t.text
    return h, t.json()["secret"], codes, secret_totp


def _demande(client, nom):
    r = _login(client, nom, BON_MDP).json()
    assert r["double_auth"] and r["approbation"] is True
    d = client.post("/auth/2fa/approbation/demander", json={"jeton_2fa": r["jeton_2fa"]})
    assert d.status_code == 200, d.text
    return r["jeton_2fa"], d.json()


def test_enregistrement_du_telephone(client, admin, notifications):
    h = _activer(client, admin, "paul.telephone")
    # Sans double authentification active : refusé
    r = client.post("/auth/approbation/telephones", headers=h, json={"code": "123456", "nom": "x", "abonnement": ABONNEMENT})
    assert r.status_code == 400 and "Active d'abord" in r.json()["detail"]
    _, r = _activer_2fa(client, h)
    h, codes = {"Authorization": f"Bearer {r['access_token']}"}, r["codes_secours"]
    assert client.post("/auth/approbation/telephones", headers=h,
                       json={"code": "000000", "nom": "x", "abonnement": ABONNEMENT}).status_code == 400      # mauvais code
    assert client.post("/auth/approbation/telephones", headers=h, json={
        "code": codes[0], "nom": "x", "abonnement": {"endpoint": "http://pas-https"}}).status_code == 400
    t = client.post("/auth/approbation/telephones", headers=h, json={"code": codes[1], "nom": "iPhone", "abonnement": ABONNEMENT})
    assert t.status_code == 200 and len(t.json()["secret"]) >= 40
    liste = client.get("/auth/approbation/telephones", headers=h).json()["data"]
    assert [x["nom"] for x in liste] == ["iPhone"] and "secret" not in str(liste) and "abonnement" not in liste[0]
    assert client.get("/auth/approbation/cle").json()["cle_publique"].startswith("B")      # point P-256 non compressé
    # Retrait
    assert client.post(f"/auth/approbation/telephones/{liste[0]['id']}/retirer", headers=h).status_code == 200
    assert client.get("/auth/approbation/telephones", headers=h).json()["data"] == []


def test_connexion_approuvee_avec_le_bon_nombre(client, admin, notifications):
    _, secret, _, _ = _compte_avec_telephone(client, admin, "awa.telephone")
    jeton, d = _demande(client, "awa.telephone")
    assert 10 <= d["nombre"] <= 99
    assert notifications[-1][1]["id"] == d["id"] and "connexion demandée" in notifications[-1][1]["titre"]
    # Redemander pour la même tentative ne renvoie pas une nouvelle demande
    assert client.post("/auth/2fa/approbation/demander", json={"jeton_2fa": jeton}).json()["id"] == d["id"]
    # En attente
    assert client.post("/auth/2fa/approbation/etat", json={"jeton_2fa": jeton, "id_demande": d["id"]}).json() == {"statut": "attente"}
    # Le téléphone voit la demande et trois nombres dont le bon
    vue = client.post(f"/approbation/{d['id']}", json={"secret": secret}).json()
    assert d["nombre"] in vue["choix"] and len(vue["choix"]) == 3 and vue["compte"] == "awa.telephone"
    assert client.post(f"/approbation/{d['id']}", json={"secret": "x" * 43}).status_code == 400          # secret inconnu
    r = client.post(f"/approbation/{d['id']}/repondre", json={"secret": secret, "nombre": d["nombre"]})
    assert r.json() == {"statut": "approuvee"}
    # L'ordinateur reçoit sa session, une seule fois
    s = client.post("/auth/2fa/approbation/etat", json={"jeton_2fa": jeton, "id_demande": d["id"]})
    assert s.status_code == 200 and s.json()["access_token"], s.text
    assert client.get("/auth/moi", headers=_h(s)).status_code == 200
    assert client.post("/auth/2fa/approbation/etat", json={"jeton_2fa": jeton, "id_demande": d["id"]}).json() == {"statut": "utilisee"}
    # Une réponse déjà donnée ne se change pas
    assert client.post(f"/approbation/{d['id']}/repondre", json={"secret": secret, "refuser": True}).status_code == 400


def test_mauvais_nombre_refuse_et_ce_n_etait_pas_moi_alerte(client, admin, notifications, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "BREVO_API_KEY", "cle-de-test")
    monkeypatch.setattr(config, "EMAIL_EXPEDITEUR", "no-reply@voicebank.test")
    boite = capturer(monkeypatch, [])
    _, secret, _, _ = _compte_avec_telephone(client, admin, "ines.telephone")
    _admin_sql("UPDATE voicebank.utilisateurs SET email = 'ines@exemple.cm' WHERE nom = 'ines.telephone'")
    jeton, d = _demande(client, "ines.telephone")
    faux = next(n for n in client.post(f"/approbation/{d['id']}", json={"secret": secret}).json()["choix"] if n != d["nombre"])
    assert client.post(f"/approbation/{d['id']}/repondre", json={"secret": secret, "nombre": faux}).json() == {"statut": "refusee"}
    assert client.post("/auth/2fa/approbation/etat", json={"jeton_2fa": jeton, "id_demande": d["id"]}).json() == {"statut": "mauvais_nombre"}
    # « Ce n'était pas moi » : refus + e-mail d'alerte
    jeton, d = _demande(client, "ines.telephone")
    assert client.post(f"/approbation/{d['id']}/repondre", json={"secret": secret, "refuser": True}).json() == {"statut": "refusee"}
    assert client.post("/auth/2fa/approbation/etat", json={"jeton_2fa": jeton, "id_demande": d["id"]}).json() == {"statut": "pas_moi"}
    alerte = [e for e in boite if e["a"] == "ines@exemple.cm"]
    assert alerte and "bloquée" in alerte[0]["sujet"]


def test_expiration_cloisonnement_et_repli_sur_le_code(client, admin, notifications):
    _, secret_a, codes, secret_totp = _compte_avec_telephone(client, admin, "jean.telephone")
    _, secret_b, _, _ = _compte_avec_telephone(client, admin, "lea.telephone")
    jeton, d = _demande(client, "jean.telephone")
    # Le téléphone d'un autre compte ne peut ni voir ni répondre
    assert client.post(f"/approbation/{d['id']}", json={"secret": secret_b}).status_code == 404
    assert client.post(f"/approbation/{d['id']}/repondre", json={"secret": secret_b, "nombre": d["nombre"]}).status_code == 400
    # Une autre tentative de connexion ne peut pas récupérer cette demande
    autre = _login(client, "jean.telephone", BON_MDP).json()["jeton_2fa"]
    assert client.post("/auth/2fa/approbation/etat", json={"jeton_2fa": autre, "id_demande": d["id"]}).status_code == 404
    # Expirée : plus de réponse possible
    _admin_sql(f"UPDATE voicebank.demandes_approbation SET expire = LOCALTIMESTAMP - INTERVAL '1 second' WHERE id_demande = '{d['id']}'")
    assert client.post("/auth/2fa/approbation/etat", json={"jeton_2fa": jeton, "id_demande": d["id"]}).json() == {"statut": "expiree"}
    assert client.post(f"/approbation/{d['id']}/repondre", json={"secret": secret_a, "nombre": d["nombre"]}).status_code == 400
    # Le code à 6 chiffres reste utilisable pour la même tentative
    r = client.post("/auth/2fa/connexion", json={"jeton_2fa": jeton, "code": _code_actuel(secret_totp, 1)})
    assert r.status_code == 200 and r.json()["access_token"]


def test_reinitialisation_retire_les_telephones(client, admin, notifications):
    h, _, _, _ = _compte_avec_telephone(client, admin, "zoe.telephone")
    assert client.post("/admin/utilisateurs/zoe.telephone/double-auth/reinitialiser", headers=admin).status_code == 200
    from tests.test_offre import _sql
    assert _sql("SELECT COUNT(*) FROM voicebank.appareils_approbation WHERE utilisateur = 'zoe.telephone'")[0][0] == 0
    r = _login(client, "zoe.telephone", BON_MDP).json()
    assert "approbation" not in r or r.get("approbation") is False


def test_sans_telephone_pas_de_notification(client, admin, notifications):
    h = _activer(client, admin, "sans.telephone")
    _activer_2fa(client, h)
    r = _login(client, "sans.telephone", BON_MDP).json()
    assert r["approbation"] is False
    d = client.post("/auth/2fa/approbation/demander", json={"jeton_2fa": r["jeton_2fa"]})
    assert d.status_code == 400 and "code à 6 chiffres" in d.json()["detail"]


def test_vraie_notification_chiffree(client, monkeypatch):
    """Le contenu part chiffré (aes128gcm) avec une signature VAPID valable, vers l'adresse du téléphone."""
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    import requests
    cle_tel = ec.generate_private_key(ec.SECP256R1())
    p256dh = base64.urlsafe_b64encode(cle_tel.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)).decode().rstrip("=")
    abo = {"endpoint": "https://updates.push.services.mozilla.com/wpush/v2/test", "keys": {
        "p256dh": p256dh, "auth": base64.urlsafe_b64encode(b"0123456789abcdef").decode().rstrip("=")}}
    vu = {}

    class Rep:
        status_code = 201
        text = ""

    def post(url, data=None, headers=None, timeout=None, **k):
        vu.update(url=url, data=data, headers=headers)
        return Rep()
    monkeypatch.setattr(requests, "post", post)
    assert approbation._envoyer(abo, {"type": "approbation", "id": "abc"}) is True
    assert vu["url"] == abo["endpoint"] and vu["headers"]["Content-Encoding"] == "aes128gcm"
    assert vu["headers"]["Authorization"].startswith("vapid t=") and b"approbation" not in vu["data"]


def test_maintenance_l_administrateur_finit_sa_connexion_avec_la_double_authentification(client, admin, notifications):
    """Pendant une maintenance, un administrateur protégé par la double authentification doit pouvoir se connecter
    (code ou téléphone) ; les autres comptes restent bloqués dès le mot de passe."""
    from tests.test_offre import _sql
    _, secret, codes, _ = _compte_avec_telephone(client, admin, "chef.maintenance")
    _sql("UPDATE voicebank.utilisateurs SET role = 'admin' WHERE nom = 'chef.maintenance'")
    client.post("/admin/maintenance", headers=admin, json={"active": True, "message": "Mise à jour"})
    try:
        import time
        time.sleep(0.05)
        from app import maintenance
        maintenance._cache["date"] = 0
        jeton, d = _demande(client, "chef.maintenance")
        client.post(f"/approbation/{d['id']}/repondre", json={"secret": secret, "nombre": d["nombre"]})
        s = client.post("/auth/2fa/approbation/etat", json={"jeton_2fa": jeton, "id_demande": d["id"]})
        assert s.status_code == 200 and s.json().get("access_token"), s.text
        r = _login(client, "chef.maintenance", BON_MDP).json()
        assert client.post("/auth/2fa/connexion", json={"jeton_2fa": r["jeton_2fa"], "code": codes[1]}).status_code == 200
        assert _login(client, "analyste1", "motdepasse-analyste").status_code == 503
    finally:
        client.post("/admin/maintenance", headers=admin, json={"active": False})
        maintenance._cache["date"] = 0
