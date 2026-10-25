"""Connecteur : bases réelles PostgreSQL et MySQL/MariaDB au schéma inconnu, fichiers Excel/CSV,
SQL Server (dialecte), sécurité (anti-SSRF, secrets, données personnelles, isolation, lecture seule)."""
import copy
import io
import os
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import pytest

from app import config
from app.connecteur import garde, questions as Q
from tests.sources.banque_externe import remplir

ADMIN_PG = os.environ.get("TEST_PG_ADMIN_URL", "postgresql://postgres@/postgres?host=/tmp&port=5433")
PG_PORT = urlsplit(ADMIN_PG).port or int(dict(x.split("=") for x in urlsplit(ADMIN_PG).query.split("&") if "=" in x).get("port", 5432))
LECTEUR = {"utilisateur": "lecteur_ext", "mot_de_passe": "Lecteur-2026!"}


def _url_pg(base):
    a = urlsplit(ADMIN_PG)
    return urlunsplit((a.scheme, a.netloc, f"/{base}", a.query, ""))


@pytest.fixture(scope="module")
def base_pg():
    c = psycopg2.connect(ADMIN_PG); c.autocommit = True
    cur = c.cursor()
    cur.execute("DROP DATABASE IF EXISTS banque_externe WITH (FORCE)")
    cur.execute("CREATE DATABASE banque_externe")
    cur.execute("DO $$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lecteur_ext') THEN "
                "CREATE ROLE lecteur_ext LOGIN PASSWORD 'Lecteur-2026!'; END IF; END$$")
    c.close()
    with psycopg2.connect(_url_pg("banque_externe")) as b:
        remplir(b.cursor())
        b.cursor().execute("ALTER TABLE accounts ADD CONSTRAINT fk_cust FOREIGN KEY (customer_id) REFERENCES customers(customer_id)")
        b.cursor().execute("GRANT USAGE ON SCHEMA public TO lecteur_ext; GRANT SELECT ON ALL TABLES IN SCHEMA public TO lecteur_ext")
    return {"type_source": "postgresql", "hote": "127.0.0.1", "port": PG_PORT, "base": "banque_externe", **LECTEUR}


@pytest.fixture(scope="module")
def base_mysql():
    try:
        import pymysql
        url = urlsplit(os.environ.get("TEST_MYSQL_ROOT_URL", "mysql://root@localhost/?unix_socket=/var/run/mysqld/mysqld.sock"))
        opts = dict(x.split("=") for x in url.query.split("&") if "=" in x)
        args = {"user": url.username or "root", "password": url.password or ""}
        if "unix_socket" in opts:
            args["unix_socket"] = opts["unix_socket"]
        else:
            args.update(host=url.hostname, port=url.port or 3306)
        c = pymysql.connect(**args, autocommit=True)
    except Exception as e:
        pytest.skip(f"MySQL/MariaDB indisponible : {e}")
    cur = c.cursor()
    cur.execute("DROP DATABASE IF EXISTS banque_externe")
    cur.execute("CREATE DATABASE banque_externe")
    for hote in ("localhost", "%"):
        cur.execute(f"DROP USER IF EXISTS 'lecteur'@'{hote}'")
        cur.execute(f"CREATE USER 'lecteur'@'{hote}' IDENTIFIED BY 'Lecteur-2026!'")
        cur.execute(f"GRANT SELECT ON banque_externe.* TO 'lecteur'@'{hote}'")
    cur.execute("USE banque_externe")
    remplir(cur)
    c.close()
    return {"type_source": "mysql", "hote": "127.0.0.1", "port": 3306, "base": "banque_externe",
            "utilisateur": "lecteur", "mot_de_passe": "Lecteur-2026!"}


@pytest.fixture(scope="module")
def client_abonne(client):
    """Un abonné (client) et un deuxième abonné, pour vérifier l'isolation."""
    comptes = []
    for email in ("orga.a@exemple.cm", "orga.b@exemple.cm"):
        r = client.post("/auth/essai", json={"nom_complet": "Orga", "email": email, "mot_de_passe": "Baobab-Kribi-2026",
                                             "accepte_conditions": True})
        assert r.status_code == 200, r.text
        a = urlsplit(ADMIN_PG)
        with psycopg2.connect(urlunsplit((a.scheme, a.netloc, "/voicebank_test", a.query, ""))) as c:
            c.cursor().execute("UPDATE voicebank.utilisateurs SET role = 'client', abonnement_fin = NOW() + INTERVAL '30 days' "
                               "WHERE nom = %s", (email,))
        r = client.post("/auth/login", json={"nom": email, "mot_de_passe": "Baobab-Kribi-2026"})
        comptes.append({"Authorization": f"Bearer {r.json()['access_token']}"})
    return comptes


def _q(client, h, id_source, texte):
    r = client.post(f"/sources/{id_source}/question", headers=h, json={"texte": texte})
    assert r.status_code == 200, (texte, r.text)
    return r.json()


@pytest.fixture(scope="module")
def source_pg(client, admin, base_pg):
    r = client.post("/sources?synchrone=true", headers=admin, json={"nom": "Banque partenaire", **base_pg})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ── Démonstration ─────────────────────────────────────────────────────

def test_source_de_demonstration_pour_les_visiteurs(client):
    r = client.post("/auth/essai", json={"nom_complet": "Visiteur", "email": "demo.connecteur@exemple.cm",
                                         "mot_de_passe": "Baobab-Kribi-2026", "accepte_conditions": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    liste = client.get("/sources", headers=h).json()
    assert liste["data"][0]["demo"] and liste["peut_ajouter"] is False
    p = client.get("/sources/0", headers=h).json()["data"]["profil"]
    assert {t["nom"] for t in p["tables"]} == {"clients", "transactions", "credits", "alertes_fraude"}
    assert p["domaine"] == "banque" and p["suggestions"]
    j = _q(client, h, 0, "Nombre de transactions par ville")
    assert j["total"] > 0 and j["resume"]
    noms = _q(client, h, 0, "Liste des clients")
    assert all(str(l["nom"]).endswith("***") for l in noms["data"])         # données personnelles masquées
    r = client.post("/sources/tester", headers=h, json={"type_source": "postgresql", "hote": "x.cm", "base": "b",
                                                      "utilisateur": "u"})
    assert r.status_code == 403 and "abonnés" in r.json()["detail"]


# ── Connexion et sécurité ─────────────────────────────────────────────

def test_tester_connexion_et_droits(client, admin, base_pg):
    j = client.post("/sources/tester", headers=admin, json=base_pg).json()
    assert j["ok"] and j["tables"] == 5 and j["droits_ecriture"] is False and j["avertissement"] is None
    a = urlsplit(ADMIN_PG)
    super_utilisateur = {**base_pg, "utilisateur": a.username or "postgres", "mot_de_passe": a.password or ""}
    j = client.post("/sources/tester", headers=admin, json=super_utilisateur).json()
    assert j["droits_ecriture"] is True and "MODIFIER" in j["avertissement"]
    r = client.post("/sources/tester", headers=admin, json={**base_pg, "base": "inexistante"})
    assert r.status_code == 400 and "introuvable" in r.json()["detail"]
    r = client.post("/sources/tester", headers=admin, json={**base_pg, "type_source": "sqlserver", "port": 1})
    assert r.status_code == 400 and ("refusée" in r.json()["detail"] or "répond pas" in r.json()["detail"])


@pytest.mark.parametrize("hote", ["127.0.0.1", "localhost", "169.254.169.254", "10.0.0.5", "192.168.1.10", "[::1]",
                                  "user@evil.cm", "hote inexistant.invalid"])
def test_anti_ssrf(client, admin, base_pg, monkeypatch, hote):
    monkeypatch.setattr(config, "CONNECTEUR_RESEAU_PRIVE", False)
    r = client.post("/sources/tester", headers=admin, json={**base_pg, "hote": hote})
    assert r.status_code == 400
    assert any(m in r.json()["detail"] for m in ("privée", "invalide", "introuvable")), r.text


def test_identifiants_chiffres_et_jamais_renvoyes(client, admin, source_pg):
    a = urlsplit(ADMIN_PG)
    with psycopg2.connect(urlunsplit((a.scheme, a.netloc, "/voicebank_test", a.query, ""))) as c, c.cursor() as cur:
        cur.execute("SELECT config_chiffree FROM voicebank.sources_donnees WHERE id_source = %s", (source_pg,))
        stocke = cur.fetchone()[0]
    assert "Lecteur-2026!" not in stocke and "lecteur_ext" not in stocke
    d = client.get(f"/sources/{source_pg}", headers=admin).text
    assert "Lecteur-2026!" not in d and "config_chiffree" not in d
    # Les tables des sources sont invisibles pour le compte lecture seule et pour l'IA
    assert client.post("/sql/executer", headers=admin, json={"sql": "SELECT * FROM voicebank.sources_donnees"}).status_code == 400


# ── Analyse intelligente ──────────────────────────────────────────────

def test_analyse_d_une_base_inconnue(client, admin, source_pg):
    d = client.get(f"/sources/{source_pg}", headers=admin).json()["data"]
    assert d["statut"] == "pret"
    p = d["profil"]
    assert p["domaine"] == "banque" and p["dialecte"] == "postgres"
    tables = {t["nom"]: t for t in p["tables"]}
    assert tables["customers"]["entite"] == "clients" and tables["loans"]["entite"] == "crédits"
    assert tables["branches"]["entite"] == "agences" and tables["payments"]["entite"] == "transactions"
    roles = {(t, c["nom"]): (c["role"], c["pii"]) for t in tables for c in tables[t]["colonnes"]}
    assert roles[("loans", "principal")][0] == "montant" and roles[("loans", "interest_rate")][0] == "taux"
    assert roles[("payments", "is_fraud")][0] == "drapeau_fraude" and roles[("payments", "user_password")][0] == "secret"
    assert roles[("customers", "email")][1] == "email" and roles[("customers", "phone")][1] == "telephone"
    assert roles[("accounts", "account_number")][1] == "compte_bancaire"
    # Relations : la déclarée et celles déduites des noms ; crédits orphelins détectés
    rel = {(r["de"], r["colonne"], r["vers"]): r for r in p["relations"]}
    assert rel[("accounts", "customer_id", "customers")]["deduite"] is False
    assert rel[("loans", "customer_id", "customers")]["orphelins"] == 4
    msgs = " ".join(x["message"] for x in p["diagnostics"])
    assert "4 ligne(s) pointent vers" in msgs and "futur" in msgs and "négatif" in msgs and "secrète" in msgs
    assert 0 < p["score_qualite"] < 100
    # Le mot de passe n'est même pas lu pendant l'analyse
    assert "valeurs" not in next(c for c in tables["payments"]["colonnes"] if c["nom"] == "user_password")
    assert any("par mois" in s for s in p["suggestions"])


# ── Questions en français ─────────────────────────────────────────────

def _scalaire(sql):
    with psycopg2.connect(_url_pg("banque_externe")) as c, c.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def test_questions_sur_postgresql(client, admin, source_pg):
    j = _q(client, admin, source_pg, "Combien de clients ?")
    assert j["data"] == [{"nombre": 300}] and j["source"] == "rule"
    j = _q(client, admin, source_pg, "Montant moyen des crédits en retard")
    attendu = _scalaire("SELECT AVG(principal) FROM loans WHERE status = 'late'")[0][0]
    assert abs(list(j["data"][0].values())[0] - float(attendu)) < 0.01
    j = _q(client, admin, source_pg, "Nombre de paiements frauduleux par canal")
    attendu = dict(_scalaire("SELECT channel, COUNT(*) FROM payments WHERE is_fraud = 1 GROUP BY channel"))
    assert {l["channel"]: l["nombre"] for l in j["data"]} == attendu
    j = _q(client, admin, source_pg, "Top 5 clients par nombre de crédits")
    assert j["colonnes"] == ["customer_id", "nombre"] and len(j["data"]) == 5
    j = _q(client, admin, source_pg, "Montant total des paiements par mois en 2025")
    assert j["colonnes"][:2] == ["annee", "mois"] and all(l["annee"] == 2025 for l in j["data"])
    assert j["resume"] and j["commentaire"] and j["relance"]["question"]
    r = client.post(f"/sources/{source_pg}/question", headers=admin, json={"texte": "Quel temps fait-il demain ?"})
    assert r.status_code == 422 and "Essaie par exemple" in r.json()["detail"]


def test_secrets_et_donnees_personnelles(client, admin, source_pg):
    j = _q(client, admin, source_pg, "Liste des paiements")
    assert "user_password" not in j["colonnes"] and j["total"] > 0
    j = _q(client, admin, source_pg, "Liste des clients")
    l = j["data"][0]
    assert l["email"].startswith(("c***@", "C***@")) and l["first_name"].endswith("***") and "***" in l["phone"]
    # Le propriétaire peut choisir de voir ses données en clair
    assert client.post(f"/sources/{source_pg}/masquage", headers=admin, json={"masquer": False}).status_code == 200
    assert _q(client, admin, source_pg, "Liste des clients")["data"][0]["email"].endswith("@mail.cm")
    assert "***" not in _q(client, admin, source_pg, "Liste des clients")["data"][0]["email"]
    client.post(f"/sources/{source_pg}/masquage", headers=admin, json={"masquer": True})


def test_gemini_carte_sans_donnees_personnelles_et_garde(client, admin, source_pg):
    reponses = iter(["DELETE FROM loans", "SELECT status, COUNT(*) AS nb FROM public.loans GROUP BY status"])

    def gemini(**kw):
        if "Réponds uniquement avec le SQL" in kw["contents"]:
            return type("R", (), {"text": next(reponses, "x")})()
        return type("R", (), {"text": '{"resume": "Résumé.", "commentaire": "Analyse.", "relance": "Et ensuite ?"}'})()
    with patch("app.nl2sql.client_gemini") as g:
        g.return_value.models.generate_content.side_effect = gemini
        j = _q(client, admin, source_pg, "Répartition des crédits par statut")
        assert j["source"] == "rule" and "moteur local" in j["avertissement"]      # DELETE refusé → moteur local
        j = _q(client, admin, source_pg, "Répartition des crédits par statut")
        assert j["source"] == "gemini" and j["colonnes"] == ["status", "nb"]
        prompts = " ".join(c.kwargs["contents"] for c in g.return_value.models.generate_content.call_args_list)
    assert "PostgreSQL" in prompts and "loans" in prompts and "interest_rate" in prompts
    assert "Prenom1" not in prompts and "@mail.cm" not in prompts and "user_password" not in prompts
    assert "'late'" in prompts                                       # valeurs non personnelles : oui


def test_isolation_entre_organisations(client, admin, source_pg, client_abonne):
    a, b = client_abonne
    assert [s["id"] for s in client.get("/sources", headers=a).json()["data"]] == [0]
    assert client.get(f"/sources/{source_pg}", headers=a).status_code == 404
    assert client.post(f"/sources/{source_pg}/question", headers=a, json={"texte": "Combien de clients ?"}).status_code == 404
    assert client.post(f"/sources/{source_pg}/supprimer", headers=a).status_code == 404
    assert client.post(f"/sources/{source_pg}/analyser", headers=a).status_code == 404


def test_mysql(client, client_abonne, base_mysql):
    a, b = client_abonne
    r = client.post("/sources?synchrone=true", headers=a, json={"nom": "Base MySQL", **base_mysql})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    d = client.get(f"/sources/{sid}", headers=a).json()["data"]
    assert d["statut"] == "pret" and d["profil"]["dialecte"] == "mysql" and d["profil"]["domaine"] == "banque"
    j = _q(client, a, sid, "Montant total des paiements par canal en 2025")
    assert "`" in j["sql"] and j["colonnes"][0] == "channel"
    j = _q(client, a, sid, "Top 10 clients par solde")
    assert j["colonnes"] == ["customer_id", "total_balance"] and len(j["data"]) == 10
    # L'autre organisation ne voit rien
    assert client.post(f"/sources/{sid}/question", headers=b, json={"texte": "Combien de clients ?"}).status_code == 404


# ── Fichiers Excel / CSV ──────────────────────────────────────────────

def _xlsx():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Ventes"
    ws.append(["Date vente", "Agence", "Produit", "Montant (FCFA)", "Client email"])
    villes = ["Douala", "Yaoundé", "Garoua"]
    from datetime import date
    for i in range(1, 121):
        ws.append([date(2025, 1 + i % 12, 1 + i % 27), villes[i % 3], ["Épargne", "Crédit", "Assurance"][i % 3],
                   10000 * i, f"client{i}@exemple.cm"])
    ws2 = wb.create_sheet("Agences")
    ws2.append(["Agence", "Responsable", "Effectif"])
    for v in villes:
        ws2.append([v, f"Chef {v}", 12])
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


def test_fichiers_excel_et_csv(client, client_abonne):
    a, _ = client_abonne
    csv_fr = ("Date;Ville;Statut;Montant\n" + "\n".join(
        f"{1 + i % 28:02d}/{1 + i % 12:02d}/2025;{['Douala', 'Bafoussam'][i % 2]};{['payé', 'en retard'][i % 3 == 0]};{i * 1000},50"
        for i in range(1, 61))).encode("latin-1")
    r = client.post("/sources/fichiers?synchrone=true", headers=a, data={"nom": "Mes fichiers"},
                    files=[("fichiers", ("ventes 2025.xlsx", _xlsx(), "application/octet-stream")),
                           ("fichiers", ("remboursements.csv", csv_fr, "text/csv"))])
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    p = client.get(f"/sources/{sid}", headers=a).json()["data"]["profil"]
    tables = {t["nom"]: t for t in p["tables"]}
    assert set(tables) == {"ventes", "agences", "remboursements"}
    cols = {c["nom"]: c for c in tables["remboursements"]["colonnes"]}
    assert cols["date"]["date_min"] == "2025-01-05" and cols["montant"]["role"] == "montant"   # 01/01/2025 → ISO, « 1000,50 » → nombre
    assert next(c for c in tables["ventes"]["colonnes"] if c["nom"] == "client_email")["pii"] == "email"
    j = _q(client, a, sid, "Montant total des ventes par agence")
    assert {l["agence"] for l in j["data"]} == {"Douala", "Yaoundé", "Garoua"}
    assert sum(list(l.values())[1] for l in j["data"]) == 10000 * sum(range(1, 121))
    j = _q(client, a, sid, "Montant total des ventes par mois")
    assert j["colonnes"][:2] == ["annee", "mois"] and len(j["data"]) == 12
    j = _q(client, a, sid, "Nombre de remboursements en retard par ville")
    assert {l["ville"] for l in j["data"]} <= {"Douala", "Bafoussam"} and sum(l["nombre"] for l in j["data"]) == 20
    # Fichiers refusés
    for nom, contenu in [("virus.exe", b"MZ..."), ("faux.xlsx", b"pas un zip"), ("vide.csv", b"")]:
        r = client.post("/sources/fichiers", headers=a, data={"nom": "Essai"}, files=[("fichiers", (nom, contenu, "text/plain"))])
        assert r.status_code == 400, (nom, r.text)
    assert client.post(f"/sources/{sid}/supprimer", headers=a).status_code == 200
    assert client.get(f"/sources/{sid}", headers=a).status_code == 404


# ── SQL Server : génération dans le bon dialecte ──────────────────────

def test_dialecte_sql_server(client, admin, source_pg):
    p = copy.deepcopy(client.get(f"/sources/{source_pg}", headers=admin).json()["data"]["profil"])
    p["dialecte"], p["schema"] = "tsql", "dbo"
    autorisees = {t["nom"] for t in p["tables"]}
    cas = {"Top 10 comptes par solde": ("TOP 10", "ORDER BY"),
           "Montant total des paiements par mois": ("YEAR(", "MONTH("),
           "Nombre de paiements frauduleux par canal": ("[is_fraud] = 1", "GROUP BY [channel]")}
    for question, attendus in cas.items():
        sql, _ = Q.sql_local(question, p, "tsql")
        sur = garde.valider(sql, "tsql", autorisees, 1000, {"dbo"})
        for a in attendus:
            assert a in sur, (question, sur)
        assert "LIMIT" not in sur and "[dbo].[" in sur


def test_suppression_d_une_source(client, admin, base_pg):
    sid = client.post("/sources?synchrone=true", headers=admin, json={"nom": "Temporaire", **base_pg}).json()["id"]
    assert client.post(f"/sources/{sid}/supprimer", headers=admin).status_code == 200
    assert client.post(f"/sources/{sid}/question", headers=admin, json={"texte": "Combien de clients ?"}).status_code == 404


def test_monnaie_des_bases_connectees(client, admin, source_pg):
    d = client.get(f"/sources/{source_pg}", headers=admin).json()["data"]
    assert d["devise_detectee"] == "XAF" and d["devise"] == "XAF"           # colonne « currency » = XAF
    base = _q(client, admin, source_pg, "Solde moyen des comptes")
    col = base["colonnes_monetaires"][0]
    eur = client.post(f"/sources/{source_pg}/question", headers=admin,
                      json={"texte": "Solde moyen des comptes", "devise": "EUR"}).json()
    assert abs(eur["data"][0][col] - base["data"][0][col] / 655.957) < 0.01 and "euros" in eur["resume"]
    # Base dont les montants sont en euros : affichage en FCFA converti
    assert client.post(f"/sources/{source_pg}/devise", headers=admin, json={"devise": "EUR"}).status_code == 200
    j = _q(client, admin, source_pg, "Solde moyen des comptes")
    assert j["devise_base"] == "EUR" and abs(j["data"][0][col] - base["data"][0][col] * 655.957) < 1
    client.post(f"/sources/{source_pg}/devise", headers=admin, json={"devise": None})
    assert _q(client, admin, source_pg, "Combien de clients ?")["colonnes_monetaires"] == []
