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


# ── Test sur l'historique ────────────────────────────────────────────

def test_test_sur_l_historique_de_la_demonstration(client, analyste):
    r = client.get("/sources/0/test-historique", headers=analyste)
    assert r.status_code == 200, r.text
    c, f = r.json()["data"]["credits"], r.json()["data"]["fraude"]
    # Crédits : apprentissage sur les plus anciens, test sur les plus récents (dates en ordre)
    assert c["apprentissage"] > c["test"] > 20 and c["colonne_date"] == "date_debut"
    assert c["periode_apprentissage"][1] <= c["periode_test"][0]
    # Verdict honnête, tiré de la mesure (les données des tests sont tirées au hasard : souvent « faible »)
    assert c["verdict"] == ("bon" if c["auc"] >= 0.75 else "moyen" if c["auc"] >= 0.62 else "faible")
    assert 0 <= c["defauts_reperes"] <= c["defauts_test"] and 0 <= c["taux_defaut_cible_pct"] <= 100
    # Fraude : le détecteur ne voit pas les étiquettes ; part des fraudes et du montant parmi les 5 % les plus atypiques
    assert f["fraudes_connues"] >= 5 and 0 <= f["fraudes_reperees_pct"] <= 100 and 0 <= f["montant_repere_pct"] <= 100


# ── API de score en temps réel ───────────────────────────────────────

def test_cles_api_et_score_en_temps_reel(client, admin, analyste):
    assert client.post("/sources/0/cles-api", headers=analyste, json={"nom": "Core banking"}).status_code == 403
    r = client.post("/sources/0/cles-api", headers=admin, json={"nom": "Core banking"})
    assert r.status_code == 200, r.text
    cle = r.json()["data"]["cle"]
    assert cle.startswith("vb_") and len(cle) > 40
    liste = client.get("/sources/0/cles-api", headers=admin).json()["data"]
    assert liste[0]["prefixe"] == cle[:12] and "cle" not in liste[0]
    # Sans clé, ou avec une fausse : refusé
    corps = {"reference": "OP-1", "montant": 25000, "heure": 14}
    assert client.post("/api/v1/operations/score", json=corps).status_code == 401
    assert client.post("/api/v1/operations/score", json=corps, headers={"Authorization": "Bearer vb_faux"}).status_code == 401
    # Opération ordinaire, puis opération énorme en pleine nuit
    ok = client.post("/api/v1/operations/score", json=corps, headers={"Authorization": f"Bearer {cle}"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["decision"] in ("accepter", "verifier", "bloquer") and 0 <= ok.json()["score"] <= 1
    gros = client.post("/api/v1/operations/score", headers={"X-Cle-API": cle},
                       json={"reference": "OP-2", "montant": 950_000_000, "heure": 3}).json()
    assert gros["decision"] in ("verifier", "bloquer") and gros["raisons"] and gros["score"] > ok.json()["score"]
    assert client.get("/sources/0/cles-api", headers=admin).json()["data"][0]["nb_appels"] == 2
    assert ok.headers["content-type"] == "application/json; charset=utf-8"
    # Suivi en direct : logiciel en ligne, chiffres du jour, 24 heures, derniers appels (visible par les membres)
    logiciels = client.get("/sources/0/logiciels", headers=analyste).json()["data"]
    assert logiciels[0]["en_ligne"] and logiciels[0]["premiere_utilisation"] and "cree_par" not in logiciels[0]
    act = client.get(f"/sources/0/cles-api/{liste[0]['id']}/activite", headers=analyste).json()["data"]
    assert act["aujourdhui"]["appels"] == 2 and act["aujourdhui"]["acceptees"] + act["aujourdhui"]["a_verifier"] + act["aujourdhui"]["bloquees"] == 2
    assert len(act["par_heure"]) == 24 and sum(h["accepter"] + h["verifier"] + h["bloquer"] for h in act["par_heure"]) == 2
    assert [a["reference"] for a in act["appels"]] == ["OP-2", "OP-1"] and act["appels"][0]["duree_ms"] >= 0
    nouveaux = client.get(f"/sources/0/cles-api/{liste[0]['id']}/activite?apres={act['appels'][0]['id']}", headers=analyste).json()
    assert nouveaux["data"]["appels"] == []
    # Révocation : la clé ne marche plus
    assert client.post(f"/sources/0/cles-api/{liste[0]['id']}/revoquer", headers=admin).status_code == 200
    assert client.post("/api/v1/operations/score", json=corps, headers={"Authorization": f"Bearer {cle}"}).status_code == 401


def test_cles_api_observation_test_et_adresses_ip(client, admin):
    gros = {"reference": "OP-N", "montant": 950_000_000, "heure": 3}
    # Mode observation : rien n'est bloqué, la décision de VoiceBank est donnée à part (pour comparer)
    obs = client.post("/sources/0/cles-api", headers=admin, json={"nom": "Observation", "mode": "observation"}).json()["data"]
    assert obs["mode"] == "observation" and not obs["test"]
    r = client.post("/api/v1/operations/score", json=gros, headers={"X-Cle-API": obs["cle"]}).json()
    assert r["mode"] == "observation" and r["decision"] == "accepter" and r["decision_voicebank"] in ("verifier", "bloquer")
    act = client.get(f"/sources/0/cles-api/{obs['id']}/activite", headers=admin).json()["data"]
    assert act["appels"][0]["decision"] == r["decision_voicebank"] and act["appels"][0]["mode"] == "observation"
    # Activation : même opération, désormais bloquée ou à vérifier
    m = client.post(f"/sources/0/cles-api/{obs['id']}/modifier", headers=admin, json={"mode": "actif"})
    assert m.status_code == 200 and m.json()["data"]["mode"] == "actif"
    r = client.post("/api/v1/operations/score", json=gros, headers={"X-Cle-API": obs["cle"]}).json()
    assert r["mode"] == "actif" and r["decision"] == r["decision_voicebank"] != "accepter"
    # Clé de test : reconnaissable, aucune alerte
    t = client.post("/sources/0/cles-api", headers=admin, json={"nom": "Recette", "test": True}).json()["data"]
    assert t["cle"].startswith("vb_test_") and t["prefixe"] == t["cle"][:16]
    r = client.post("/api/v1/operations/score", json=gros, headers={"X-Cle-API": t["cle"]}).json()
    assert r["mode"] == "test" and r["decision"] != "accepter" and not r["alerte_creee"]
    # Adresses IP : réseau autorisé seulement (403 ailleurs), adresses invalides refusées à la saisie
    assert client.post("/sources/0/cles-api", headers=admin, json={"nom": "Mauvaise", "ips_autorisees": "41.202.300.1"}).status_code == 400
    ip = client.post("/sources/0/cles-api", headers=admin,
                     json={"nom": "Agence", "ips_autorisees": "41.202.0.0/16; 102.244.1.7"}).json()["data"]
    assert ip["ips_autorisees"] == "41.202.0.0/16, 102.244.1.7/32"
    dedans = client.post("/api/v1/operations/score", json=gros, headers={"X-Cle-API": ip["cle"], "X-Forwarded-For": "41.202.10.5"})
    assert dedans.status_code == 200
    dehors = client.post("/api/v1/operations/score", json=gros, headers={"X-Cle-API": ip["cle"], "X-Forwarded-For": "8.8.8.8"})
    assert dehors.status_code == 403 and "8.8.8.8" in dehors.json()["detail"]
    m = client.post(f"/sources/0/cles-api/{ip['id']}/modifier", headers=admin, json={"changer_ips": True, "ips_autorisees": ""})
    assert m.json()["data"]["ips_autorisees"] is None
    assert client.post("/api/v1/operations/score", json=gros, headers={"X-Cle-API": ip["cle"], "X-Forwarded-For": "8.8.8.8"}).status_code == 200
    for c in (obs, t, ip):
        client.post(f"/sources/0/cles-api/{c['id']}/revoquer", headers=admin)


# ── Documents réglementaires ─────────────────────────────────────────

def test_etat_du_portefeuille(client, analyste):
    r = client.get("/sources/0/etat-portefeuille", headers=analyste)
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF" and len(r.content) > 3000
    assert r.headers["content-disposition"].startswith('attachment; filename="etat_portefeuille_')


def test_projet_de_declaration_de_soupcon():
    from app import reglementaire, suivi
    db.ecrire("INSERT INTO voicebank.sources_donnees (id_source, nom, proprietaire, type_source, config_chiffree, statut) "
              "VALUES (9902, 'Base test', 'rayan', 'postgresql', '', 'pret') ON CONFLICT DO NOTHING")
    try:
        a = suivi.enregistrer(9902, [{"id": "OP-77", "date": "2026-10-30T03:12:00", "montant": 2_500_000,
                                      "niveau_risque": "Critique", "score": 0.998,
                                      "raisons": [{"variable": "Montant", "detail": "40 fois le montant habituel"}],
                                      "categories": {"Canal": "Mobile money"}}])[0]
        with pytest.raises(reglementaire.DocumentRefuse):
            reglementaire.declaration_soupcon(9902, a["id_suivi"], "rayan")       # pas encore confirmée
        suivi.modifier(9902, a["id_suivi"], "rayan", statut="fraude_confirmee", commentaire="Client injoignable, compte vidé en 10 min")
        contenu, nom = reglementaire.declaration_soupcon(9902, a["id_suivi"], "rayan")
        assert contenu[:4] == b"%PDF" and nom.startswith("projet_declaration_soupcon_VB-9902-")
    finally:
        db.ecrire("DELETE FROM voicebank.sources_donnees WHERE id_source = 9902")
