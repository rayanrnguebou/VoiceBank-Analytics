"""Tests des fonctions v3.1 : résumé parlé, questions de suite, évaluation, corrections depuis
l'interface, score de crédit expliqué, traitement des alertes, masquage et audit."""
from unittest.mock import patch

import pytest

from app import evaluation, nl2sql, resume


def _q(client, h, texte, **kw):
    r = client.post("/vocal/question", json={"texte": texte, **kw}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ════════════════ 1. Réponse rédigée ════════════════

def test_resume_local_sans_gemini(client, analyste):
    j = _q(client, analyste, "Transactions frauduleuses par banque")
    assert j["resume_source"] == "local"
    assert j["resume"].startswith(f"{j['total']} résultats") and "En tête" in j["resume"]


def test_resume_gemini_sans_donnees_personnelles(client, admin):
    with patch.object(resume, "resume_gemini", wraps=resume.resume_gemini) as espion, \
         patch("app.nl2sql.client_gemini") as faux_client:
        faux_client.return_value.models.generate_content.return_value.text = "79 crédits en défaut."
        j = _q(client, admin, "Crédits en défaut")
    assert j["resume"] == "79 crédits en défaut." and j["resume_source"] == "gemini"
    prompt = faux_client.return_value.models.generate_content.call_args.kwargs["contents"]
    assert '"nom"' not in prompt and '"prenom"' not in prompt and "Nom1" not in prompt
    espion.assert_called_once()


def test_commentaire_local_va_plus_loin(client, analyste):
    j = _q(client, analyste, "Transactions frauduleuses par banque")
    c = j["commentaire"]
    assert c and c != j["resume"] and len(c) > 80
    assert "alertes critiques" in c          # conseil lié au thème de la question


def test_commentaire_gemini_en_json(client, admin):
    with patch("app.nl2sql.client_gemini") as faux_client:
        faux_client.return_value.models.generate_content.return_value.text = (
            '{"resume": "79 crédits en défaut.", "commentaire": "La moitié vient de Douala. Relance ces clients."}')
        j = _q(client, admin, "Crédits en défaut")
    assert j["resume"] == "79 crédits en défaut."
    assert j["commentaire"] == "La moitié vient de Douala. Relance ces clients."
    kw = faux_client.return_value.models.generate_content.call_args.kwargs
    assert kw["config"] == {"response_mime_type": "application/json"} and '"commentaire"' in kw["contents"]


def test_commentaire_local_cas_limites():
    assert "élargir" in resume.commentaire_local("q", ["a"], [])
    serie = [{"mois": f"2025-{m:02d}", "volume_fcfa": 100 + 10 * m} for m in range(1, 7)]
    assert "hausse" in resume.commentaire_local("Volume par mois", ["mois", "volume_fcfa"], serie)
    conc = [{"banque": "Afriland", "nb": 90}, {"banque": "SGC", "nb": 5}, {"banque": "UBA", "nb": 5}]
    assert "concentration" in resume.commentaire_local("Clients par banque", ["banque", "nb"], conc)


def test_resume_desactivable(client, analyste):
    j = _q(client, analyste, "Crédits en défaut", resumer=False)
    assert j["resume"] is None and j["commentaire"] is None


def test_resume_aucun_resultat():
    assert resume.resume_local("q", ["a"], []) == "Aucun résultat ne correspond à cette question."


# ════════════════ 2. Questions de suite ════════════════

CTX_FRAUDES = {"question": "Transactions frauduleuses",
               "sql": "SELECT id_transaction, id_client, banque, ville, montant_fcfa, date_transaction "
                      "FROM voicebank.transactions WHERE est_frauduleuse = 'Oui' ORDER BY montant_fcfa DESC LIMIT 100"}


@pytest.mark.parametrize("question,attendu", [
    ("et à Douala ?", True), ("seulement BICEC", True), ("en 2025", True), ("Douala", True),
    ("Crédits en défaut", False), ("Top 10 clients par solde", False),
])
def test_detection_question_de_suite(question, attendu):
    assert nl2sql.est_question_de_suite(question) is attendu


def test_suite_locale_sans_gemini(client, analyste):
    j = _q(client, analyste, "et à Douala ?", contexte=CTX_FRAUDES)
    assert j["suite"] and j["question_precedente"] == "Transactions frauduleuses"
    assert j["total"] > 0 and all(l["ville"] == "Douala" for l in j["data"])


def test_suite_banque_et_annee(client, analyste):
    j = _q(client, analyste, "seulement BICEC en 2025", contexte=CTX_FRAUDES)
    assert all(l["banque"] == "BICEC" and l["date_transaction"].startswith("2025") for l in j["data"])


def test_suite_avec_gemini_recoit_le_contexte(client, analyste):
    sql = "SELECT id_transaction FROM voicebank.transactions WHERE est_frauduleuse = 'Oui' AND ville = 'Douala'"
    with patch.object(nl2sql, "sql_via_gemini", return_value=sql) as g:
        j = _q(client, analyste, "et à Douala ?", contexte=CTX_FRAUDES)
    assert g.call_args.args[1]["question"] == "Transactions frauduleuses" and j["source"] == "gemini" and j["suite"]


def test_nouvelle_question_ignore_le_contexte(client, analyste):
    j = _q(client, analyste, "Crédits en défaut", contexte=CTX_FRAUDES)
    assert not j["suite"] and "credits" in j["sql"]


def test_contexte_malveillant_bloque(client, analyste):
    ctx = {"question": "x", "sql": "SELECT pg_read_file('/etc/passwd') AS ville"}
    r = client.post("/vocal/question", json={"texte": "et à Douala ?", "contexte": ctx}, headers=analyste)
    assert r.status_code in (400, 503)


# ════════════════ 3. Évaluation ════════════════

def test_jeu_evaluation_references_valides():
    questions = evaluation.charger_questions()
    assert len(questions) >= 50
    for q in questions:
        evaluation._executer(q["sql_reference"])          # lève une erreur si invalide


def test_comparaison_tolerante():
    assert evaluation.comparer(["n"], [{"n": 10.0}], ["banque", "total"], [{"banque": "X", "total": 10}])
    assert evaluation.comparer(["m"], [{"m": 3.14159}], ["moy"], [{"moy": 3.14}])
    assert not evaluation.comparer(["n"], [{"n": 10}], ["n"], [{"n": 12}])
    assert not evaluation.comparer(["n"], [{"n": 1}, {"n": 2}], ["n"], [{"n": 1}])
    # liste volontairement limitée (LIMIT 1) : juste si c'est un sous-ensemble de la référence
    assert evaluation.comparer(["n"], [{"n": 1}, {"n": 2}], ["n"], [{"n": 2}], limite=1)
    assert not evaluation.comparer(["n"], [{"n": 1}, {"n": 2}], ["n"], [{"n": 3}], limite=1)


def test_evaluation_sans_gemini():
    r = evaluation.evaluer()
    assert r["nb_questions"] >= 50
    regles = r["par_source"].get("rule", {})
    assert regles.get("taux") == 100.0, [d for d in r["details"] if d.get("source") == "rule" and d["statut"] != "juste"]
    assert r["par_source"]["aucune"]["questions"] > 0          # celles qui demandent Gemini
    assert not [d for d in r["details"] if d["statut"] in ("faux", "erreur_sql", "reference_invalide")]


def test_evaluation_api(client, admin, analyste):
    import time
    assert client.post("/admin/evaluation", headers=analyste).status_code == 403
    assert client.post("/admin/evaluation", headers=admin).status_code == 200
    for _ in range(100):
        j = client.get("/admin/evaluation", headers=admin).json()
        if not j["en_cours"] and j["derniere"]:
            break
        time.sleep(0.2)
    assert j["derniere"]["nb_questions"] >= 50 and j["derniere"]["taux_reussite"] is not None


# ════════════════ 4. Corrections depuis l'interface ════════════════

def test_cycle_signalement_correction(client, admin, analyste):
    r = client.post("/signalements", headers=analyste, json={
        "question": "crédits immobiliers en défaut", "sql": "SELECT 1", "source": "rule", "commentaire": "pas filtré"})
    id_s = r.json()["id_signalement"]
    assert client.get("/signalements", headers=analyste).status_code == 403
    ouverts = client.get("/signalements", headers=admin).json()["data"]
    assert any(s["id_signalement"] == id_s for s in ouverts)
    sql = ("SELECT id_credit, montant_fcfa FROM voicebank.credits "
           "WHERE statut_credit = 'Défaut' AND type_credit = 'Crédit immobilier'")
    r = client.post("/vocal/corriger", headers=admin, json={
        "question": "crédits immobiliers en défaut", "sql_correct": sql, "id_signalement": id_s})
    assert r.status_code == 200
    assert not any(s["id_signalement"] == id_s for s in client.get("/signalements", headers=admin).json()["data"])
    j = _q(client, analyste, "crédits immobiliers en défaut")
    assert j["source"] == "rag" and "Crédit immobilier" in j["sql"]


def test_supprimer_correction(client, admin):
    client.post("/vocal/corriger", headers=admin, json={
        "question": "question jetable de test", "sql_correct": "SELECT COUNT(*) FROM voicebank.clients"})
    c = next(c for c in client.get("/rag/corrections?limit=200", headers=admin).json()["data"]
             if c["question"] == "question jetable de test")
    assert client.post(f"/rag/corrections/{c['id']}/supprimer", headers=admin).status_code == 200
    assert client.post(f"/rag/corrections/{c['id']}/supprimer", headers=admin).status_code == 404


def test_rejeter_signalement(client, admin, analyste):
    id_s = client.post("/signalements", headers=analyste, json={"question": "q"}).json()["id_signalement"]
    assert client.post(f"/signalements/{id_s}/traiter", headers=admin, json={"statut": "Rejeté"}).status_code == 200
    assert client.post(f"/signalements/{id_s}/traiter", headers=analyste, json={"statut": "Rejeté"}).status_code == 403


# ════════════════ 5. Score de crédit expliqué ════════════════

def test_score_demande_credit(client, analyste):
    ref = client.get("/ia/credit/referentiel", headers=analyste).json()["data"]
    demande = {"montant_fcfa": 20_000_000, "mensualite_fcfa": 900_000, "revenu_annuel_fcfa": 6_000_000,
               "score_credit": 450, "taux_interet_pct": 16, "duree_mois": 36, "est_diaspora": "Non",
               "type_credit": ref["type_credit"][0], "garantie": "Sans garantie", "banque": ref["banque"][0]}
    risque = client.post("/ia/score-credit", json=demande, headers=analyste).json()
    sain = client.post("/ia/score-credit", headers=analyste, json={
        **demande, "mensualite_fcfa": 150_000, "revenu_annuel_fcfa": 40_000_000, "score_credit": 800}).json()
    assert 0 <= risque["probabilite_defaut"] <= 1 and 300 <= risque["score_ia"] <= 850
    assert len(risque["facteurs"]) == 5 and {"variable", "impact", "effet"} <= set(risque["facteurs"][0])
    assert sain["probabilite_defaut"] < risque["probabilite_defaut"]
    demande["type_credit"] = "Inventé"
    assert client.post("/ia/score-credit", json=demande, headers=analyste).status_code == 422


def test_score_credit_existant_et_liste(client, analyste):
    j = client.get("/ia/score-credit/CRD-0000001", headers=analyste).json()
    assert j["credit"]["id_credit"] == "CRD-0000001" and "facteurs" in j
    assert client.get("/ia/score-credit/CRD-9999999", headers=analyste).status_code == 404
    liste = client.get("/ia/credits-a-risque?limit=5", headers=analyste).json()
    probas = [c["probabilite_defaut"] for c in liste["data"]]
    assert len(probas) == 5 and probas == sorted(probas, reverse=True)
    assert all(c["statut_credit"] == "En cours" for c in liste["data"])


def test_infos_modele_fraude(client, analyste):
    j = client.get("/ia/modeles", headers=analyste).json()
    assert j["credit_disponible"] and j["fraude"]["heure_prise_en_compte"] is False


def test_reentrainement_fraude(tmp_path, monkeypatch):
    import json
    import shutil

    from app import config, fraude
    from app.outils import entrainer_fraude
    for f in config.MODELS_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["entrainer_fraude"])
    entrainer_fraude.main()
    meta = json.loads((tmp_path / "meta_fraude.json").read_text(encoding="utf-8"))
    assert meta["heure_valide"] and meta["nb_transactions"] == 2000 and meta["auc_xgboost"] is not None
    sauvegarde = dict(fraude.modeles)
    try:
        fraude.charger()
        from datetime import time
        ref = fraude.referentiel()
        args = (250000, ref["type_transaction"][0], ref["canal"][0], ref["banque"][0], ref["ville"][0], "Non")
        assert 0 <= fraude.analyser(*args, heure=time(3, 0))["score_anomalie"] <= 1
        assert fraude.infos_modele()["heure_prise_en_compte"]
    finally:
        fraude.modeles.clear(); fraude.modeles.update(sauvegarde)


# ════════════════ 6. Traitement des alertes ════════════════

def test_traitement_alerte(client, analyste, admin):
    alerte = client.get("/alertes/fraude?traitee=false&limit=1", headers=analyste).json()["data"][0]
    avant = client.get("/alertes/stats", headers=analyste).json()["a_traiter"]
    r = client.post(f"/alertes/{alerte['id_alerte']}/traiter", headers=analyste,
                    json={"decision": "Faux positif", "commentaire": "Client joint, achat légitime"})
    assert r.status_code == 200
    assert client.get("/alertes/stats", headers=analyste).json()["a_traiter"] == avant - 1
    a = next(x for x in client.get("/alertes/fraude?traitee=true&limit=200", headers=analyste).json()["data"]
             if x["id_alerte"] == alerte["id_alerte"])
    assert a["decision"] == "Faux positif" and a["traitee_par"] == "analyste1" and a["date_traitement"]
    assert client.post(f"/alertes/{alerte['id_alerte']}/traiter", headers=admin,
                       json={"decision": "Fraude confirmée"}).status_code == 409
    assert client.post("/alertes/999999/traiter", headers=admin, json={"decision": "Faux positif"}).status_code == 404
    assert client.post(f"/alertes/{alerte['id_alerte']}/traiter", headers=admin,
                       json={"decision": "Peut-être"}).status_code == 422


# ════════════════ 7. Masquage et audit ════════════════

def test_noms_masques_pour_analyste(client, analyste, admin):
    sql_noms = "SELECT id_client, nom, prenom, solde_fcfa FROM voicebank.clients ORDER BY solde_fcfa DESC LIMIT 3"
    with patch.object(nl2sql, "sql_via_gemini", return_value=sql_noms):
        a = _q(client, analyste, "qui sont nos clients les plus riches")
        b = _q(client, admin, "qui sont nos clients les plus riches")
    assert all(l["nom"].endswith("***") and l["prenom"].endswith("***") for l in a["data"])
    assert not b["data"][0]["nom"].endswith("***")
    assert a["data"][0]["solde_fcfa"] == b["data"][0]["solde_fcfa"]
    c = client.get("/clients/CLI-000001", headers=analyste).json()["client"]
    assert c["nom"].endswith("***") and c["email"].startswith(c["email"][0] + "***@")
    assert client.get("/clients?limit=1", headers=analyste).json()["data"][0]["nom"].endswith("***")


def test_journal_audit(client, admin, analyste):
    client.post("/auth/login", json={"nom": "analyste1", "mot_de_passe": "mauvais"})
    client.get("/clients/CLI-000002", headers=analyste)
    assert client.get("/admin/audit", headers=analyste).status_code == 403
    j = client.get("/admin/audit?limit=500", headers=admin).json()
    actions = {e["action"] for e in j["evenements"]}
    assert {"connexion", "connexion_refusee", "consultation_client"} <= actions
    assert j["questions"] and j["synthese_30j"]
    assert any(e["action"] == "consultation_client" and e["detail"]["id_client"] == "CLI-000002"
               and e["utilisateur"] == "analyste1" for e in j["evenements"])


def test_audit_en_ajout_seul():
    from app import db
    with pytest.raises(Exception):
        db.ecrire("DELETE FROM voicebank.journal_audit")
    with pytest.raises(Exception):
        db.ecrire("UPDATE voicebank.journal_audit SET action = 'x'")
