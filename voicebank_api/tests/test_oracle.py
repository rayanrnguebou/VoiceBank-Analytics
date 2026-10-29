"""Connecteur Oracle : dialecte, garde SQL, paramètres de connexion ; base réelle si TEST_ORACLE_URL est fourni
(ex. oracle://system:motdepasse@127.0.0.1:1521/FREEPDB1 — service lancé par l'intégration continue)."""
import os
import ssl
from urllib.parse import urlsplit

import pytest
from sqlglot import exp

from app.connecteur import connexion, garde, oracle
from app.connecteur import questions as Q
from tests.sources.banque_externe import DDL, lignes

ORACLE_URL = os.environ.get("TEST_ORACLE_URL")


def test_dialecte_identifiants():
    req = exp.select(exp.column(exp.to_identifier("amount", quoted=True))).from_(
        exp.table_(exp.to_identifier("payments", quoted=True), db=exp.to_identifier("banque", quoted=True))).limit(5)
    assert req.sql(dialect=oracle.DIALECTE) == 'SELECT "AMOUNT" FROM "BANQUE"."PAYMENTS" FETCH FIRST 5 ROWS ONLY'
    # Casse mixte (créée entre guillemets) : conservée
    assert exp.to_identifier("MonMontant", quoted=True).sql(dialect=oracle.DIALECTE) == '"MonMontant"'
    assert Q.NOMS_DIALECTES[oracle.DIALECTE] == "Oracle"
    annee = exp.select(exp.Year(this=exp.column("paid_at")), exp.Month(this=exp.column("paid_at"))).from_("payments")
    assert annee.sql(dialect=oracle.DIALECTE) == "SELECT EXTRACT(YEAR FROM paid_at), EXTRACT(MONTH FROM paid_at) FROM payments"


@pytest.mark.parametrize("sql", [
    "SELECT UTL_HTTP.REQUEST('http://pirate.exemple') FROM payments",
    "SELECT DBMS_PIPE.RECEIVE_MESSAGE('a', 30) FROM payments",
    "SELECT DBMS_XMLGEN.GETXML('select * from all_users') FROM payments",
    "SELECT SYS_CONTEXT('USERENV', 'IP_ADDRESS') FROM payments",
    "SELECT USER FROM payments",
    "SELECT ma_fonction_maison(amount) FROM payments",
    "SELECT * FROM all_users",
    "SELECT 1 FROM dual",
    "SELECT * FROM payments@lien_distant",
])
def test_garde_oracle_refuse(sql):
    with pytest.raises(garde.SQLRefuse):
        garde.valider(sql, oracle.DIALECTE, {"payments"})


def test_garde_oracle_accepte_et_plafonne():
    s = garde.valider("SELECT channel, NVL(SUM(amount), 0) AS total, TO_CHAR(paid_at, 'YYYY-MM') AS mois FROM payments "
                      "GROUP BY channel, TO_CHAR(paid_at, 'YYYY-MM') ORDER BY total DESC FETCH FIRST 3 ROWS ONLY",
                      oracle.DIALECTE, {"payments"})
    assert s.endswith("FETCH FIRST 3 ROWS ONLY")
    assert garde.valider("SELECT amount FROM payments", oracle.DIALECTE, {"payments"}, 50).endswith("FETCH FIRST 50 ROWS ONLY")
    assert garde.valider("SELECT amount FROM payments FETCH FIRST 5000 ROWS ONLY", oracle.DIALECTE, {"payments"},
                         100).endswith("FETCH FIRST 100 ROWS ONLY")


def test_parametres_de_connexion(monkeypatch):
    monkeypatch.setattr(connexion, "verifier_hote", lambda h: "203.0.113.10")
    cfg = {"hote": "core.banque.cm", "base": "ORCLPDB1", "utilisateur": "lecteur", "mot_de_passe": "x"}
    eng = connexion.moteur("oracle", {**cfg, "ssl": "prefere"})
    assert eng.url.host == "203.0.113.10" and eng.url.port == 1521 and eng.url.query["service_name"] == "ORCLPDB1"
    vus = {}
    monkeypatch.setattr(connexion, "create_engine", lambda url, **kw: vus.update(url=url, **kw["connect_args"]))
    connexion.moteur("oracle", {**cfg, "ssl": "exige", "port": 2484})
    assert vus["protocol"] == "tcps" and vus["ssl_context"].verify_mode == ssl.CERT_NONE and not vus["ssl_server_dn_match"]
    assert vus["url"].host == "203.0.113.10"
    connexion.moteur("oracle", {**cfg, "ssl": "verifie", "port": 2484})
    assert vus["ssl_context"].verify_mode == ssl.CERT_REQUIRED and vus["ssl_context"].check_hostname
    assert vus["ssl_server_dn_match"] and vus["url"].host == "core.banque.cm"


def test_messages_erreur_oracle():
    m = connexion.message_erreur
    assert "Service Oracle introuvable" in m(Exception("ORA-12514: TNS:listener does not currently know of service"))
    assert "mot de passe refusé" in m(Exception("ORA-01017: invalid username/password; logon denied"))
    assert "Connexion refusée" in m(Exception("DPY-6005: cannot connect to database"))


# ── Base Oracle réelle ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def base_oracle():
    if not ORACLE_URL:
        pytest.skip("TEST_ORACLE_URL absent : base Oracle réelle non testée")
    import oracledb
    u = urlsplit(ORACLE_URL)
    dsn = f"{u.hostname}:{u.port or 1521}/{u.path.lstrip('/')}"
    c = oracledb.connect(user=u.username, password=u.password, dsn=dsn)
    cur = c.cursor()
    for instr in ("DROP USER banque CASCADE", "DROP USER lecteur_vb CASCADE"):
        try:
            cur.execute(instr)
        except oracledb.DatabaseError:
            pass
    cur.execute('CREATE USER banque IDENTIFIED BY "Banque-2026" QUOTA UNLIMITED ON users')
    cur.execute('CREATE USER lecteur_vb IDENTIFIED BY "Lecteur-2026"')
    cur.execute("GRANT CREATE SESSION TO lecteur_vb")
    for instr in [s for s in DDL.split(";") if s.strip()]:
        cur.execute(instr.replace("CREATE TABLE ", "CREATE TABLE banque."))
    for table, rows in lignes().items():
        marques = ", ".join(f":{i + 1}" for i in range(len(rows[0])))
        cur.executemany(f"INSERT INTO banque.{table} VALUES ({marques})", rows)
        cur.execute(f"GRANT SELECT ON banque.{table} TO lecteur_vb")
    cur.execute("ALTER TABLE banque.accounts ADD CONSTRAINT fk_cust FOREIGN KEY (customer_id) "
                "REFERENCES banque.customers (customer_id)")
    c.commit()
    cur.execute("BEGIN DBMS_STATS.GATHER_SCHEMA_STATS('BANQUE'); END;")
    c.close()
    return {"type_source": "oracle", "hote": u.hostname, "port": u.port or 1521, "base": u.path.lstrip("/"),
            "utilisateur": "lecteur_vb", "mot_de_passe": "Lecteur-2026", "schema": "BANQUE", "ssl": "desactive"}


def _q(client, h, sid, texte):
    r = client.post(f"/sources/{sid}/question", headers=h, json={"texte": texte})
    assert r.status_code == 200, (texte, r.text)
    return r.json()


def test_oracle_reel(client, admin, base_oracle):
    r = client.post("/sources/tester", headers=admin, json=base_oracle)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] and r.json()["droits_ecriture"] is False and r.json()["tables"] == 5, r.json()
    r = client.post("/sources?synchrone=true", headers=admin, json={"nom": "Système central Oracle", **base_oracle})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    d = client.get(f"/sources/{sid}", headers=admin).json()["data"]
    assert d["statut"] == "pret", d
    p = d["profil"]
    assert p["dialecte"] == oracle.DIALECTE and p["domaine"] == "banque"
    assert {t["nom"] for t in p["tables"]} == {"branches", "customers", "accounts", "loans", "payments"}
    assert any(r["de"] == "accounts" and r["vers"] == "customers" for r in p["relations"])
    pay = next(t for t in p["tables"] if t["nom"] == "payments")
    assert pay["lignes"] == 1500 and next(c for c in pay["colonnes"] if c["nom"] == "user_password")["role"] == "secret"
    j = _q(client, admin, sid, "Montant total des paiements par canal en 2025")
    assert '"PAYMENTS"' in j["sql"] and j["colonnes"][0] == "channel" and j["data"], j
    j = _q(client, admin, sid, "Top 10 clients par solde")
    assert len(j["data"]) == 10
    t = client.get(f"/sources/{sid}/tableau", headers=admin).json()["data"]
    assert len(t["indicateurs"]) == 4
    # Lecture seule côté serveur : même une écriture qui passerait la garde serait refusée par Oracle
    eng = connexion.moteur("oracle", {**base_oracle})
    import sqlalchemy
    with pytest.raises(sqlalchemy.exc.DatabaseError):
        with connexion.connexion_lecture(eng, "oracle") as conn:
            conn.exec_driver_sql("UPDATE banque.payments SET amount = 0")
    client.post(f"/sources/{sid}/supprimer", headers=admin)
