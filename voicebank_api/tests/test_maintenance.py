"""Mode maintenance : bloque les utilisateurs (503 + message), laisse passer l'administrateur et les routes
publiques ; annonce de maintenance prévue ; secours par variable d'environnement."""
import pytest

from app import config, maintenance


@pytest.fixture(autouse=True)
def remise_a_zero(client, admin):
    yield
    client.post("/admin/maintenance", headers=admin, json={"active": False})
    maintenance._cache["etat"] = None


def test_maintenance_bloque_les_utilisateurs_mais_pas_l_administrateur(client, admin, analyste):
    r = client.post("/admin/maintenance", headers=admin, json={
        "active": True, "message": "Mise à jour du modèle de fraude.", "fin_prevue": "2030-01-01T14:30"})
    assert r.status_code == 200 and r.json()["active"] and r.json()["modifie_par"] == "rayan"
    # Utilisateur : 503 avec le message et l'heure de retour
    q = client.post("/vocal/question", headers=analyste, json={"texte": "top 3 clients par solde"})
    assert q.status_code == 503 and q.json()["maintenance"] and q.json()["detail"] == "Mise à jour du modèle de fraude."
    assert q.json()["fin_prevue"] == "2030-01-01T14:30" and q.headers["retry-after"] == "120"
    # Connexion refusée aux utilisateurs, acceptée pour l'administrateur
    login = client.post("/auth/login", json={"nom": "analyste1", "mot_de_passe": "motdepasse-analyste"})
    assert login.status_code == 503 and login.json()["maintenance"]
    assert client.post("/auth/login", json={"nom": "rayan", "mot_de_passe": "motdepasse-admin"}).status_code == 200
    assert client.post("/vocal/question", headers=admin, json={"texte": "top 3 clients par solde"}).status_code == 200
    # Routes publiques toujours ouvertes
    assert client.get("/health").json()["maintenance"] is True
    pub = client.get("/maintenance").json()
    assert pub["active"] and pub["message"] == "Mise à jour du modèle de fraude."
    assert client.get("/auth/moi", headers=analyste).status_code == 200
    # Fin de la maintenance
    client.post("/admin/maintenance", headers=admin, json={"active": False})
    assert client.post("/vocal/question", headers=analyste, json={"texte": "top 3 clients par solde"}).status_code == 200


def test_jeton_falsifie_ne_contourne_pas(client, admin):
    import jwt
    client.post("/admin/maintenance", headers=admin, json={"active": True})
    faux = jwt.encode({"sub": "rayan", "role": "admin", "ver": 0}, "pas-le-bon-secret", algorithm="HS256")
    r = client.get("/dashboard", headers={"Authorization": f"Bearer {faux}"})
    assert r.status_code == 503


def test_annonce_de_maintenance_prevue(client, admin, analyste):
    r = client.post("/admin/maintenance", headers=admin, json={
        "active": False, "annonce_message": "Maintenance prévue mercredi de 22 h à 23 h.",
        "annonce_debut": "2030-01-01T22:00", "annonce_fin": "2030-01-01T23:00"})
    assert r.status_code == 200
    a = client.get("/maintenance").json()["annonce"]
    assert a["message"].startswith("Maintenance prévue") and a["fin"] == "2030-01-01T23:00"
    assert client.get("/dashboard", headers=analyste).status_code == 200      # simple annonce : rien n'est bloqué
    # Annonce passée : plus affichée
    client.post("/admin/maintenance", headers=admin, json={"annonce_message": "Ancienne", "annonce_fin": "2020-01-01T00:00"})
    assert client.get("/maintenance").json()["annonce"] is None


def test_reserve_a_l_administrateur(client, analyste):
    assert client.post("/admin/maintenance", headers=analyste, json={"active": True}).status_code == 403
    assert client.post("/admin/maintenance", json={"active": True}).status_code == 401


def test_secours_par_variable_d_environnement(client, analyste, monkeypatch):
    monkeypatch.setattr(maintenance, "_env_active", lambda: True)
    r = client.get("/dashboard", headers=analyste)
    assert r.status_code == 503 and r.json()["detail"] == maintenance.MESSAGE_DEFAUT


def test_les_paiements_continuent(client, admin):
    client.post("/admin/maintenance", headers=admin, json={"active": True})
    # Le webhook NotchPay reste joignable (il est refusé ici pour signature invalide, pas pour maintenance)
    assert client.post("/paiements/notchpay/webhook", content=b"{}").status_code == 401
    assert config  # garde l'import
