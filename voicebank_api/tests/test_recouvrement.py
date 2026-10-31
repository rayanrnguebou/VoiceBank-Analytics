"""Recouvrement : dossiers tirés des crédits en retard (base de démonstration, schéma lu comme une base connectée),
coordonnées relues dans la table des clients, priorités, actions de l'équipe, droits, « Valeur créée »."""
from datetime import date, timedelta

import pytest

from app import db, recouvrement as R
from app.connecteur.recouvrement import etape


def _sql(req, **p):
    return db.ecrire(req, p)


@pytest.fixture(scope="module", autouse=True)
def propre():
    _sql("DELETE FROM voicebank.dossiers_recouvrement WHERE id_source IN (0, 9901)")
    yield
    _sql("DELETE FROM voicebank.dossiers_recouvrement WHERE id_source IN (0, 9901)")


@pytest.mark.parametrize("v,e", [("En retard", "retard"), ("Défaut", "defaut"), ("CONTENTIEUX", "defaut"),
                                 ("overdue", "retard"), ("En cours", None), ("Remboursé", None), ("impayé", "retard")])
def test_etape(v, e):
    assert etape(v) == e


def test_numero_et_message():
    assert R.numero_international("6 90 12 34 56") == "237690123456"
    assert R.numero_international("+33 6 12 34 56 78") == "33612345678"
    assert R.numero_international("abc") is None
    m = R.message({"paiement": "Orange Money marchand 123456", "signature": "Coopérative du Moungo"},
                  "Awa Ndi", "CRD-1", "25 000 FCFA")
    assert "Awa Ndi" in m and "CRD-1" in m and "25 000 FCFA" in m and "Orange Money marchand 123456" in m
    assert m.endswith("Coopérative du Moungo")
    assert "{" not in R.message({"modele": "Bonjour {client} {inconnu}"}, None, "X", "1").replace("{inconnu}", "")


def test_dossiers_de_la_demonstration(client, admin):
    r = client.get("/sources/0/recouvrement", headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["resume"]["ouverts"] > 100 and d["peut_traiter"] and d["contact"] and not d["masquees"]
    premier = d["dossiers"][0]
    assert premier["etape"] in ("retard", "defaut") and premier["reste"] > 0
    assert premier["client"] and premier["numero"] and premier["numero"].isdigit()
    assert premier["ref"] in premier["message"]
    # Priorité : montant × chance de récupération (repères tant que l'équipe n'a pas assez de dossiers clos)
    assert d["chances"]["retard"]["source"] == "repere"
    prio = [x["priorite"] for x in d["dossiers"]]
    assert prio == sorted(prio, reverse=True)


def test_analyste_demo_masque_et_lecture_seule(client, analyste):
    d = client.get("/sources/0/recouvrement", headers=analyste).json()
    assert d["masquees"] and not d["peut_traiter"] and not d["contact"]
    x = d["dossiers"][0]
    assert x["numero"] is None and (x["telephone"] is None or x["telephone"].startswith("***"))
    r = client.post(f"/sources/0/recouvrement/{x['id']}", headers=analyste, json={"nature": "appel"})
    assert r.status_code == 403


def test_cycle_complet_d_un_dossier(client, admin):
    d = client.get("/sources/0/recouvrement", headers=admin).json()
    x = d["dossiers"][0]
    url = f"/sources/0/recouvrement/{x['id']}"
    r = client.post(url, headers=admin, json={"nature": "whatsapp", "texte": "Relance du jour"})
    assert r.json()["data"]["statut"] == "contacte"
    hier = (date.today() - timedelta(days=1)).isoformat()
    assert client.post(url, headers=admin, json={"nature": "promesse", "montant": 1000, "date_promesse": hier}).status_code == 400
    demain = (date.today() + timedelta(days=1)).isoformat()
    r = client.post(url, headers=admin, json={"nature": "promesse", "montant": 1000, "date_promesse": demain})
    assert r.json()["data"]["statut"] == "promesse" and r.json()["data"]["promesse_date"] == demain
    du = x["montant_du"]
    r = client.post(url, headers=admin, json={"nature": "paiement", "montant": 1000})
    assert r.json()["data"]["statut"] == "paiement_partiel" and r.json()["data"]["promesse_date"] is None
    r = client.post(url, headers=admin, json={"nature": "paiement", "montant": du - 1000, "texte": "Solde Orange Money"})
    data = r.json()["data"]
    assert data["statut"] == "regle" and data["montant_recupere"] == pytest.approx(du)
    natures = [h["nature"] for h in data["historique"]]
    assert natures[:4] == ["paiement", "paiement", "promesse", "whatsapp"]
    # Valeur créée : l'argent récupéré apparaît
    v = client.get("/sources/0/valeur?jours=30", headers=admin).json()["data"]
    assert v["recupere"] >= du and v["dossiers_regles"] >= 1 and v["minutes_par_question"] == 15
    # Le dossier réglé n'est plus dans les ouverts, mais dans les clos
    ouverts = client.get("/sources/0/recouvrement", headers=admin).json()["dossiers"]
    assert x["id"] not in {o["id"] for o in ouverts}
    clos = client.get("/sources/0/recouvrement?statut=clos", headers=admin).json()["dossiers"]
    assert x["id"] in {o["id"] for o in clos}


def test_decisions_expliquees_et_assignation(client, admin):
    x = client.get("/sources/0/recouvrement", headers=admin).json()["dossiers"][1]
    url = f"/sources/0/recouvrement/{x['id']}"
    assert client.post(url, headers=admin, json={"nature": "statut", "statut": "irrecouvrable"}).status_code == 400
    r = client.post(url, headers=admin, json={"nature": "statut", "statut": "contentieux", "texte": "Huissier mandaté"})
    assert r.json()["data"]["statut"] == "contentieux"
    assert client.post(url, headers=admin, json={"nature": "assignation", "assigne_a": "inconnu"}).status_code == 400
    r = client.post(url, headers=admin, json={"nature": "assignation", "assigne_a": "rayan"})
    assert r.status_code == 200 and r.json()["data"]["assigne_a"] == "rayan"


def test_reglages_du_message(client, admin, analyste):
    corps = {"paiement": "MTN MoMo marchand 778899", "signature": "Banque de démonstration"}
    assert client.post("/sources/0/recouvrement-reglages", headers=analyste, json=corps).status_code == 403
    assert client.post("/sources/0/recouvrement-reglages", headers=admin, json=corps).status_code == 200
    x = client.get("/sources/0/recouvrement", headers=admin).json()["dossiers"][0]
    assert "MTN MoMo marchand 778899" in x["message"] and x["message"].endswith("Banque de démonstration")


def test_synchronisation_et_taux_de_l_equipe():
    R.synchroniser(9901, [{"ref": "A", "etape": "retard", "montant": 100.0}, {"ref": "B", "etape": "defaut", "montant": 50.0}], True)
    assert {d["ref"] for d in R.dossiers(9901, {})} == {"A", "B"}
    R.synchroniser(9901, [{"ref": "B", "etape": "defaut", "montant": 50.0}], True)   # A régularisé dans la base
    assert {d["ref"] for d in R.dossiers(9901, {})} == {"B"}
    assert [d["ref"] for d in R.dossiers(9901, {}, "clos")] == ["A"]
    # Liste incomplète (trop de crédits) : on ne clôt rien
    R.synchroniser(9901, [], False)
    assert {d["ref"] for d in R.dossiers(9901, {})} == {"B"}
    # Dès 10 dossiers clos dans une étape, le taux réel de l'équipe remplace le repère
    R.synchroniser(9901, [{"ref": f"R{i}", "etape": "retard", "montant": 100.0} for i in range(10)], False)
    for d in R.dossiers(9901, {}):
        if d["ref"].startswith("R"):
            R.agir(9901, d["id"], "test", "paiement", montant=100.0 if int(d["ref"][1:]) < 8 else None) \
                if int(d["ref"][1:]) < 8 else R.agir(9901, d["id"], "test", "statut", statut="irrecouvrable", texte="Client parti")
    ch = R.chances(9901)
    assert ch["retard"]["source"] == "equipe" and ch["retard"]["taux"] == pytest.approx(900 / 1100, abs=0.002)   # A (régularisé) + 8 payés sur 11
