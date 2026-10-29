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
                                  "100.64.0.1", "0.0.0.0", "::ffff:127.0.0.1", "198.18.0.1",
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
    # Tableau de bord dans le dialecte MySQL
    t = client.get(f"/sources/{sid}/tableau", headers=a).json()["data"]
    assert len(t["indicateurs"]) == 4 and any(g["id"] == "evolution" for g in t["graphiques"])
    assert client.get(f"/sources/{sid}/tableau", headers=b).status_code == 404


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
    # Tableau de bord d'un import de fichiers
    t = client.get(f"/sources/{sid}/tableau", headers=a).json()["data"]
    total = next(i for i in t["indicateurs"] if i["type"] == "montant")
    assert total["table"] in ("ventes", "remboursements")
    mois = next(g for g in t["graphiques"] if g["id"] == "evolution")
    assert len(mois["donnees"]) >= 2
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


# ── Tableau de bord adapté à la base ──────────────────────────────────

def test_tableau_de_bord_adapte_a_la_base(client, admin, source_pg):
    r = client.get(f"/sources/{source_pg}/tableau", headers=admin)
    assert r.status_code == 200, r.text
    t = r.json()["data"]
    ind = {i["titre"]: i for i in t["indicateurs"]}
    assert len(t["indicateurs"]) == 4
    assert ind["Clients"]["valeur"] == 300 and ind["Clients"]["table"] == "customers"
    assert ind["Fraudes"]["valeur"] == _scalaire("SELECT COUNT(*) FROM payments WHERE is_fraud = 1")[0][0]
    montant = next(i for i in t["indicateurs"] if i["type"] == "montant")
    assert montant["table"] == "loans"
    assert round(montant["valeur"]) == round(float(_scalaire("SELECT SUM(principal) FROM loans")[0][0]))
    g = {x["id"]: x for x in t["graphiques"]}
    assert g["evolution"]["donnees"][0]["label"][:4].isdigit() and 2 <= len(g["evolution"]["donnees"]) <= 12
    assert sum(p["nb"] for p in g["evolution"]["donnees"]) <= _scalaire("SELECT COUNT(*) FROM payments")[0][0]
    rep = [x for x in t["graphiques"] if x["id"].startswith("repartition")]
    assert rep and all(len(x["donnees"]) >= 2 for x in rep)
    # Aucune donnée personnelle regroupée (ni e-mail, ni téléphone, ni nom)
    assert not any(k in x["titre"].lower() for x in t["graphiques"] for k in ("email", "phone", "name", "password"))
    # Montants convertis dans la monnaie choisie
    e = client.get(f"/sources/{source_pg}/tableau?devise=EUR", headers=admin).json()["data"]
    m_eur = next(i for i in e["indicateurs"] if i["type"] == "montant")["valeur"]
    assert abs(m_eur * 655.957 - montant["valeur"]) < 655.957 * 0.01
    # Démonstration et isolation
    assert client.get("/sources/0/tableau", headers=admin).json()["data"]["indicateurs"]
    assert client.get("/sources/999999/tableau", headers=admin).status_code == 404


# ── Risques appris sur la base connectée ─────────────────────────────

def test_operations_atypiques_sur_la_base(client, admin, source_pg):
    r = client.get(f"/sources/{source_pg}/risques/operations", headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["resume"]["table"] == "payments" and d["resume"]["analysees"] > 100
    assert d["resume"]["colonne_montant"] == "amount" and "channel" in d["resume"]["categories"]
    ops = d["operations"]
    assert ops and ops[0]["score"] >= ops[-1]["score"] and ops[0]["niveau_risque"] in ("Critique", "Élevé", "Moyen", "Faible")
    assert all(o["raisons"] and o["recommandation"] for o in ops)
    assert "fraudes_connues" in d["resume"] and 0 <= d["resume"]["fraudes_reperees_pct"] <= 100
    # Aucune donnée personnelle utilisée
    assert not set(d["resume"]["categories"]) & {"email", "phone", "first_name", "last_name", "user_password"}
    # Monnaie choisie
    e = client.get(f"/sources/{source_pg}/risques/operations?devise=EUR", headers=admin).json()["data"]
    assert abs(e["operations"][0]["montant"] * 655.957 - ops[0]["montant"]) < 655.957


def test_analyser_une_operation_sur_la_base(client, admin, source_pg):
    f = client.get(f"/sources/{source_pg}/risques/formulaire", headers=admin).json()["data"]
    assert f["montant"] == "amount" and f["categories"] and f["categories"][0]["valeurs"]
    cats = {c["colonne"]: c["valeurs"][0] for c in f["categories"]}
    normal = client.post(f"/sources/{source_pg}/risques/operation", headers=admin,
                         json={"montant": f["montant_habituel"], "categories": cats}).json()["data"]
    enorme = client.post(f"/sources/{source_pg}/risques/operation", headers=admin,
                         json={"montant": f["montant_habituel"] * 500, "categories": {**cats, f["categories"][0]["colonne"]: "Inconnue"}}).json()["data"]
    assert enorme["score_anomalie"] > normal["score_anomalie"]
    assert enorme["niveau_risque"] in ("Critique", "Élevé") and enorme["recommandations"] and enorme["facteurs"]
    assert any("fois le montant habituel" in (x.get("detail") or "") for x in enorme["facteurs"])


def test_portefeuille_de_credits_sur_la_base(client, admin, source_pg):
    r = client.get(f"/sources/{source_pg}/risques/credits", headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["table"] == "loans" and d["colonne_statut"] == "status" and d["credits"] > 0
    assert 0 < d["taux_defaut"] < 1 and d["segments"]
    g = d["segments"][0]["groupes"]
    assert g and all(0 <= x["taux_defaut"] <= 1 for x in g)
    if d["modele"]:
        assert d["a_risque"] and d["a_risque"][0]["facteurs"]


def test_risques_sur_la_demonstration(client, analyste):
    ops = client.get("/sources/0/risques/operations", headers=analyste).json()["data"]
    assert ops["resume"]["table"] == "transactions" and ops["resume"]["heure_prise_en_compte"]
    cr = client.get("/sources/0/risques/credits", headers=analyste).json()["data"]
    assert cr["table"] == "credits" and cr["modele"] and cr["a_risque"]


def test_bombe_de_decompression_refusee():
    """Un .xlsx de quelques Ko qui se décompresserait en centaines de Mo est refusé avant toute lecture."""
    import io
    import zipfile

    from app.connecteur import fichiers
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", b"0" * (300 * 1024 * 1024))
    piege = tampon.getvalue()
    assert len(piege) < 1024 * 1024
    with pytest.raises(fichiers.FichierRefuse, match="anormal"):
        fichiers.verifier("piege.xlsx", piege)
    with pytest.raises(fichiers.FichierRefuse, match="abîmé"):
        fichiers.verifier("faux.xlsx", b"PK\x03\x04" + b"\x00" * 50)


# ════════════════ Suivi des alertes, fiches des modèles, rapports, tâches automatiques ════════════════

def _premiere_alerte(client, h, source):
    ops = client.get(f"/sources/{source}/risques/operations", headers=h).json()["data"]["operations"]
    suivies = [o for o in ops if o.get("suivi")]
    assert suivies, "les opérations atypiques (Moyen et plus) deviennent des alertes suivies"
    assert all(o["niveau_risque"] in ("Critique", "Élevé") for o in suivies)
    assert all(o["suivi"] is None for o in ops if o["niveau_risque"] in ("Moyen", "Faible"))
    return suivies[0], ops


def test_suivi_des_alertes(client, admin, analyste, source_pg):
    a, _ = _premiere_alerte(client, admin, source_pg)
    i = a["suivi"]["id"]
    assert a["suivi"]["statut"] == "nouvelle"
    d = client.get(f"/sources/{source_pg}/alertes/{i}", headers=admin).json()
    assert d["data"]["statut"] == "nouvelle" and d["peut_traiter"] and [p["nom"] for p in d["assignables"]] == ["rayan"]
    # Assignation : passe « en cours », tracée dans l'historique
    r = client.post(f"/sources/{source_pg}/alertes/{i}", headers=admin, json={"assigne_a": "rayan"})
    assert r.status_code == 200 and r.json()["data"]["statut"] == "en_cours" and r.json()["data"]["assigne_a"] == "rayan"
    assert client.post(f"/sources/{source_pg}/alertes/{i}", headers=admin, json={"assigne_a": "analyste1"}).status_code == 400
    # Un verdict s'explique
    r = client.post(f"/sources/{source_pg}/alertes/{i}", headers=admin, json={"statut": "fausse_alerte"})
    assert r.status_code == 400 and "verdict" in r.json()["detail"]
    r = client.post(f"/sources/{source_pg}/alertes/{i}", headers=admin,
                    json={"statut": "fausse_alerte", "commentaire": "Virement de salaire habituel, vérifié avec le client."})
    h = r.json()["data"]["historique"]
    assert [x["nature"] for x in h] == ["assignation", "statut", "commentaire"]
    assert h[1]["texte"] == "En cours → Fausse alerte" and r.json()["data"]["date_cloture"]
    # La fausse alerte ne redevient pas « nouvelle » à l'analyse suivante
    _, ops = _premiere_alerte(client, admin, source_pg)
    meme = [o for o in ops if o.get("suivi") and o["suivi"]["id"] == i]
    assert meme and meme[0]["suivi"]["statut"] == "fausse_alerte"
    s = client.get(f"/sources/{source_pg}/suivi", headers=admin).json()
    assert s["statistiques"]["fausses_alertes"] >= 1 and s["statistiques"]["verdicts"] >= 1
    assert s["notification"]["niveaux"] == ["Critique"]                 # moins de 10 verdicts : règle par défaut
    # Isolation : un autre compte ne voit ni ne traite les alertes de cette base ; pas de suivi sur la démo
    assert client.get(f"/sources/{source_pg}/alertes/{i}", headers=analyste).status_code == 404
    assert client.post(f"/sources/{source_pg}/alertes/{i}", headers=analyste, json={"commentaire": "x"}).status_code == 404
    assert client.get("/sources/0/suivi", headers=admin).status_code == 404
    assert client.get(f"/sources/{source_pg}/alertes/999999", headers=admin).status_code == 404


def test_fiches_des_modeles(client, admin, source_pg):
    f = client.get(f"/sources/{source_pg}/modeles", headers=admin).json()["data"]
    op = f["operations"]
    assert op["donnees"]["table"] and op["donnees"]["operations"] > 100 and "Montant" in op["donnees"]["variables"]
    assert op["derive"]["etat"] in ("stable", "a_surveiller", "forte") and op["derive"]["indice"] >= 0
    assert op["fiabilite"]["fraudes_connues"] > 0 and op["verdicts"]["notification"]["niveaux"]
    assert [s["niveau"] for s in op["seuils"]] == ["Critique", "Élevé", "Moyen"] and op["limites"]
    assert "credits" in f
    demo = client.get("/sources/0/modeles", headers=admin).json()["data"]
    assert demo["operations"]["fiabilite"]["auc"] and 0 < demo["credits"]["fiabilite"]["auc"] < 1
    assert demo["credits"]["fiabilite"]["niveau"] in ("bonne", "correcte", "faible")


def test_derive_mesuree_par_le_psi():
    import numpy as np

    from app.connecteur.risques import etat_derive, psi
    rng = np.random.default_rng(1)
    a = rng.normal(10, 1, 5000)
    bornes = np.quantile(a, np.linspace(0, 1, 11))
    bornes[0], bornes[-1] = -np.inf, np.inf
    assert etat_derive(psi(a, rng.normal(10, 1, 2000), bornes)) == "stable"
    assert etat_derive(psi(a, rng.normal(11.5, 1, 2000), bornes)) == "forte"


def test_rapport_pdf(client, admin, analyste, source_pg):
    import io

    from pypdf import PdfReader
    r = client.get(f"/sources/{source_pg}/rapport?periode=mois", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert "voicebank_rapport_mensuel_" in r.headers["content-disposition"]
    texte = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    for attendu in ("Rapport de risque mensuel", "Synthèse de la période", "Points d'attention",
                    "Alertes ouvertes les plus critiques", "Modèles d'IA utilisés", "Méthodologie"):
        assert attendu in texte, attendu
    assert "@" not in texte                               # aucune adresse e-mail de client dans le rapport
    assert client.get(f"/sources/{source_pg}/rapport", headers=analyste).status_code == 404


def test_taches_automatiques(client, admin, source_pg, monkeypatch):
    from app import courriel, db
    envois = []
    monkeypatch.setattr(courriel, "envoyer_en_arriere_plan", lambda dest, m: envois.append((dest, m)))
    ancien = db.ecrire("SELECT email FROM voicebank.utilisateurs WHERE nom = 'rayan'").scalar()
    db.ecrire("UPDATE voicebank.utilisateurs SET email = 'rayan@voicebank.test' WHERE nom = 'rayan'")
    try:
        _taches_automatiques(client, admin, source_pg, monkeypatch, envois)
    finally:
        db.ecrire("UPDATE voicebank.utilisateurs SET email = :e WHERE nom = 'rayan'", {"e": ancien})


def _taches_automatiques(client, admin, source_pg, monkeypatch, envois):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app import config, taches
    a = urlsplit(ADMIN_PG)                                # l'application ne peut pas effacer des alertes : compte admin
    with psycopg2.connect(urlunsplit((a.scheme, a.netloc, "/voicebank_test", a.query, ""))) as c, c.cursor() as cur:
        cur.execute("DELETE FROM voicebank.suivi_alertes WHERE id_source = %s", (source_pg,))
        cur.execute("DELETE FROM voicebank.taches_planifiees")
    assert client.post("/notifications", headers=admin, json={"alertes_critiques": True, "resume_quotidien": True,
                                                              "rapport_hebdo": True, "rapport_mensuel": True}).status_code == 200
    lundi_1er = datetime(2026, 6, 1, 8, 30, tzinfo=ZoneInfo("Africa/Douala"))
    rapport = taches.executer(force=True, maintenant=lundi_1er)
    etapes = rapport["sources"][source_pg]
    assert etapes["nouvelles_alertes"] > 0 and etapes["notifiees"] >= 1, etapes
    envois_rayan = [(d, m) for d, m in envois if d == "rayan@voicebank.test"]   # les autres bases préviennent leurs membres
    sujets = [m.sujet for _, m in envois_rayan]
    assert any("nouvelle(s) alerte(s)" in s and "Banque partenaire" in s for s in sujets), sujets
    assert any(s.startswith("Résumé du 01/06") for s in sujets), sujets
    pdfs = [m for _, m in envois_rayan if m.pieces]
    assert {p.pieces[0][0].split("_")[2] for p in pdfs} == {"hebdomadaire", "mensuel"}
    assert all(p.pieces[0][1][:4] == b"%PDF" for p in pdfs)
    assert all("Banque partenaire" in m.sujet for _, m in envois_rayan if not m.sujet.startswith("Rapport"))
    # Deuxième passage : rien n'est envoyé deux fois
    n = len(envois)
    taches.executer(maintenant=lundi_1er)
    assert len(envois) == n
    # Préférences respectées
    client.post("/notifications", headers=admin, json={"alertes_critiques": False, "resume_quotidien": False,
                                                       "rapport_hebdo": False, "rapport_mensuel": False})
    assert client.get("/notifications", headers=admin).json()["data"]["resume_quotidien"] is False
    assert taches.destinataires(source_pg, "resume_quotidien") == []
    # Déclenchement par GitHub Actions : invisible sans la bonne clé
    monkeypatch.setattr(config, "TACHES_CLE", "")
    assert client.post("/taches/executer").status_code == 404
    monkeypatch.setattr(config, "TACHES_CLE", "cle-des-taches-de-test-2026")
    assert client.post("/taches/executer", headers={"X-Cle-Taches": "mauvaise"}).status_code == 404
    r = client.post("/taches/executer", headers={"X-Cle-Taches": "cle-des-taches-de-test-2026"})
    assert r.status_code == 200 and "sources" in r.json()
