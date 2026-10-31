"""« Quelles tables ? » : réponse tirée du profil de la base, jamais d'information_schema ; refus expliqués."""
from unittest.mock import patch

import pytest

from app import catalogue, nl2sql
from app.garde_sql import SQLRefuse, message_refus


@pytest.mark.parametrize("q", ["Quelles tables contient la base ?", "liste des tables", "montre-moi les colonnes",
                               "Quelle est la structure de la base de données", "quelles données as-tu ?",
                               "Que contient la base", "what tables do you have"])
def test_questions_de_structure_reconnues(q):
    assert catalogue.est_question_structure(q)


@pytest.mark.parametrize("q", ["clients par banque", "montant total des transactions", "crédits en défaut à Douala"])
def test_questions_ordinaires_non_concernees(q):
    assert not catalogue.est_question_structure(q)


def test_tables_de_la_base_sans_appel_a_l_ia(client, analyste):
    with patch.object(nl2sql, "sql_via_gemini", side_effect=AssertionError("pas d'IA")):
        r = client.post("/vocal/question", headers=analyste, json={"texte": "Quelles sont les tables de la base ?"})
    assert r.status_code == 200, r.text
    d = r.json()
    tables = {l["table"] for l in d["data"]}
    assert {"clients", "transactions", "credits", "alertes_fraude"} <= tables
    assert d["sql"] is None and "consultables" in d["resume"]
    assert not any("information_schema" in l["table"] for l in d["data"])


def test_meme_reponse_pour_une_source(client, analyste):
    r = client.post("/sources/0/question", headers=analyste, json={"texte": "liste des tables"})
    assert r.status_code == 200, r.text
    assert {l["table"] for l in r.json()["data"]} >= {"clients", "transactions"}


def test_refus_des_tables_systeme_explique():
    m = message_refus(SQLRefuse("Table non autorisée : information_schema.tables"))
    assert "tables internes" in m and "information_schema" not in m
    assert "quelles tables" in message_refus(SQLRefuse("Table inconnue : comptes"))
    assert message_refus(SQLRefuse("Opération non autorisée")) == "Requête refusée : Opération non autorisée"


def test_traduction_anglaise():
    from app import i18n
    assert i18n.traduire("« Base VoiceBank » contient 4 tables consultables : a, b.", "en").startswith("“")
