"""Questions favorites : ajout, envoi chaque lundi par e-mail avec les droits actuels du compte, cloisonnement."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app import favoris
from tests.test_offre import _h, _inscrire, _sql
from tests.test_organisations import boite  # noqa: F401  (fixture)

LUNDI = datetime(2026, 11, 2, 8, 0, tzinfo=ZoneInfo("Africa/Douala"))
MARDI = datetime(2026, 11, 3, 8, 0, tzinfo=ZoneInfo("Africa/Douala"))


def test_ajouter_lister_modifier_supprimer(client):
    h = _h(_inscrire(client, "favoris.base@exemple.cm"))
    r = client.post("/favoris", headers=h, json={"question": "  Top 10 clients   par solde ", "devise": "EUR"})
    assert r.status_code == 200, r.text
    f = r.json()["data"]
    assert f["question"] == "Top 10 clients par solde" and f["base"] == "Démonstration VoiceBank" and not f["envoi_hebdo"]
    assert client.post("/favoris", headers=h, json={"question": "top 10 clients par solde"}).status_code == 400   # doublon
    assert client.post("/favoris", headers=h, json={"question": "x", "id_source": 0}).status_code == 422
    assert client.post("/favoris", headers=h, json={"question": "ventes", "id_source": 99999}).status_code == 404
    assert client.post(f"/favoris/{f['id']}", headers=h, json={"envoi_hebdo": True}).status_code == 200
    assert client.get("/favoris", headers=h).json()["data"][0]["envoi_hebdo"] is True
    # Les favoris d'un autre compte sont inaccessibles
    autre = _h(_inscrire(client, "favoris.autre@exemple.cm"))
    assert client.get("/favoris", headers=autre).json()["data"] == []
    assert client.post(f"/favoris/{f['id']}", headers=autre, json={"envoi_hebdo": False}).status_code == 404
    assert client.post(f"/favoris/{f['id']}/supprimer", headers=autre).status_code == 404
    assert client.post(f"/favoris/{f['id']}/supprimer", headers=h).status_code == 200
    assert client.get("/favoris", headers=h).json()["data"] == []


def test_limite_de_favoris(client, monkeypatch):
    monkeypatch.setattr(favoris, "MAX_FAVORIS", 2)
    h = _h(_inscrire(client, "favoris.limite@exemple.cm"))
    for q in ("clients par ville", "crédits en défaut"):
        assert client.post("/favoris", headers=h, json={"question": q}).status_code == 200
    r = client.post("/favoris", headers=h, json={"question": "alertes critiques"})
    assert r.status_code == 400 and "au maximum" in r.json()["detail"]


def test_envoi_du_lundi(client, boite):  # noqa: F811
    email = "favoris.lundi@exemple.cm"
    h = _h(_inscrire(client, email))
    f = client.post("/favoris", headers=h, json={"question": "Top 10 clients par solde"}).json()["data"]
    client.post(f"/favoris/{f['id']}", headers=h, json={"envoi_hebdo": True})
    sans = client.post("/favoris", headers=h, json={"question": "clients par ville"}).json()["data"]   # pas d'envoi demandé
    assert favoris.envoyer_du_lundi(MARDI).get("ignoree")
    res = favoris.envoyer_du_lundi(LUNDI)
    mails = [e for e in boite if e["a"] == email and "question de la semaine" in e["sujet"]]
    assert res["envoyes"] >= 1 and len(mails) == 1
    m = mails[0]["message"]
    assert "Top 10 clients par solde" in m.sujet and len(m.details) == 10
    nom, contenu, mime = m.pieces[0]
    assert nom.endswith(".csv") and mime == "text/csv" and contenu.startswith("﻿".encode())
    assert contenu.decode("utf-8-sig").count("\n") == 11          # en-tête + 10 clients
    # Données personnelles masquées : le visiteur ne voit pas les noms des clients
    assert all("@" not in v for _, v in m.details)
    # Une seule fois par semaine
    favoris.envoyer_du_lundi(LUNDI)
    assert len([e for e in boite if e["a"] == email and "question de la semaine" in e["sujet"]]) == 1
    assert not any(sans["question"] in e["sujet"] for e in boite)


def test_pas_d_envoi_quand_l_essai_est_termine(client, boite):  # noqa: F811
    email = "favoris.expire@exemple.cm"
    h = _h(_inscrire(client, email))
    f = client.post("/favoris", headers=h, json={"question": "crédits en défaut"}).json()["data"]
    client.post(f"/favoris/{f['id']}", headers=h, json={"envoi_hebdo": True})
    _sql("UPDATE voicebank.utilisateurs SET essai_fin = LOCALTIMESTAMP - INTERVAL '1 day' WHERE nom = %s", (email,))
    favoris.envoyer_du_lundi(LUNDI)
    assert not [e for e in boite if e["a"] == email and "question de la semaine" in e["sujet"]]
