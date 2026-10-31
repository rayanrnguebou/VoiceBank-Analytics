"""Messages de connexion précis (Neon, pooler, rôle inconnu, réseau) et adresse IPv4 choisie en priorité."""
from unittest.mock import patch

import pytest

from app.connecteur import connexion as C


def test_adresse_directe_neon():
    assert C.hote_direct("ep-abc-123-pooler.eu-central-1.aws.neon.tech") == "ep-abc-123.eu-central-1.aws.neon.tech"
    assert C.hote_direct(" ep-abc-123.eu-central-1.aws.neon.tech ") == "ep-abc-123.eu-central-1.aws.neon.tech"
    assert C.hote_direct("db-pooler.exemple.cm") == "db-pooler.exemple.cm"          # seulement chez Neon


@pytest.mark.parametrize("brut,attendu", [
    ("ERROR:  Endpoint ID is not specified. Either please upgrade", "nom complet du serveur"),
    ("ERROR: unsupported startup parameter: options", "sans « -pooler »"),
    ('FATAL:  role "Lecteur" does not exist', "utilisateur n'existe pas"),
    ("connection to server failed: Network is unreachable", "pas joignable"),
    ('FATAL:  password authentication failed for user "x"', "mot de passe refusé"),
])
def test_messages_precis(brut, attendu):
    assert attendu in C.message_erreur(Exception(brut))


def test_message_inconnu_avec_detail_sans_secret():
    m = C.message_erreur(Exception("(psycopg2.OperationalError) quelque chose d'inattendu postgresql://u:secret@h/d\n"
                                   "(Background on this error at: https://sqlalche.me)"))
    assert m.startswith("Connexion impossible à la base.") and "quelque chose d'inattendu" in m
    assert "secret" not in m and "sqlalche" not in m


def test_ipv4_choisie_en_premier():
    faux = [(None, None, None, None, ("2600:1f18::1", 5432, 0, 0)), (None, None, None, None, ("3.120.10.20", 5432))]
    with patch("socket.getaddrinfo", return_value=faux):
        assert C.verifier_hote("ep-abc.eu-central-1.aws.neon.tech") == "3.120.10.20"


def test_mysql_poignee_de_main_non_utf8():
    """Serveur MySQL qui annonce un module d'authentification illisible : la connexion continue (auth standard)."""
    import struct

    import pymysql
    from pymysql.protocol import MysqlPacket
    data = (b"\x0a" + b"5.6.10-log\x00" + struct.pack("<I", 7) + b"abcdefgh" + b"\x00" + struct.pack("<H", 0xF7FF)
            + struct.pack("<BHHB", 33, 2, 0x0008, 21) + b"\x00" * 10 + b"ijklmnopqrst" + b"\x00" + b"m\x8b\x1f\x00")
    c = pymysql.connections.Connection(defer_connect=True)
    with patch.object(c, "_read_packet", return_value=MysqlPacket(data, "utf-8")):
        c._get_server_information()
    assert c.server_version == "5.6.10-log" and c._auth_plugin_name == ""


def test_mysql_valeur_texte_mal_encodee():
    from pymysql.connections import MySQLResult
    from pymysql.protocol import MysqlPacket
    r = MySQLResult.__new__(MySQLResult)
    r.converters = [("utf8", None), ("utf8", int)]
    r.unbuffered_active = False
    paquet = MysqlPacket(b"\x03a\x8bz\x0242", "utf8")
    assert r._read_row_from_packet(paquet) == ("a�z", 42)


def test_inspection_mysql_tolerante():
    """Réponse binaire Latin-1 d'une commande d'inspection (vieux serveur) : lue avec un caractère de remplacement."""
    from sqlalchemy.dialects.mysql.base import _DecodingRow

    class Ligne(tuple):
        nom = b"famille_\x8b"
    r = _DecodingRow(Ligne((b"s\x8bx", "ok")), "utf8mb4")
    assert r[0] == "s�x" and r[1] == "ok" and r.nom == "famille_�"


def test_message_encodage_indique_le_lieu():
    def fautif():
        b"s\x8b".decode("utf-8")
    try:
        fautif()
    except UnicodeDecodeError as e:
        m = C.message_erreur(e)
    assert "encodage inattendu" in m and "fautif" in m and "test_connexion_messages.py" in m


def test_mysql_reessaie_en_latin1():
    """Test de connexion MySQL : erreur d'encodage en UTF-8, réussite en Latin-1 → réglage gardé."""
    from app.connecteur import service as S
    essais = []

    def faux(type_source, cfg):
        essais.append(cfg.get("jeu_caracteres"))
        if not cfg.get("jeu_caracteres"):
            raise S.SourceRefusee("Le serveur renvoie du texte dans un encodage inattendu.")
        return {"ok": True}
    cfg = {"hote": "h"}
    with patch.object(S, "_tester", side_effect=faux):
        assert S.tester("mysql", cfg) == {"ok": True}
    assert essais == [None, "latin1"] and cfg["jeu_caracteres"] == "latin1"


def test_colonne_binaire_dans_l_analyse():
    """Une colonne BLOB (octets gzip 0x1f 0x8b, comme sur la base Rfam) ne fait plus échouer le profil de la table."""
    import pandas as pd
    from app.connecteur import analyse

    class Resultat:
        def fetchall(self):
            return [(i, b"\x1f\x8b\x08\x00" + bytes([i])) for i in range(30)]

        def keys(self):
            return ["id", "alignement"]

    class Conn:
        def exec_driver_sql(self, sql):
            return Resultat()
    df = analyse._echantillon(Conn(), "familles", None, "mysql", ["id", "alignement"])
    assert df["alignement"].iloc[0] == "<5 octets>"
    col = analyse._profil_colonne("alignement", "LONGBLOB", df["alignement"], len(df))
    assert col["nature"] == "texte"
    with pytest.raises(UnicodeDecodeError):                     # ce qui se passait avant
        pd.Series([b"\x1f\x8b\x08"]).astype(str)


def test_messages_azure_sql():
    m = C.message_erreur(Exception("(40615, b\"Cannot open server 'vb' requested by the login. Client with IP address "
                                   "'20.40.228.15' is not allowed to access the server.\")"))
    assert "pare-feu Azure" in m and "20.40.228.15" in m
    assert "adresse complète" in C.message_erreur(Exception("(40532, b'DB-Lib error message 20018')"))


def test_azure_sql_par_son_nom():
    from sqlalchemy.engine import Engine
    faux = [(None, None, None, None, ("20.40.228.15", 1433))]
    with patch("socket.getaddrinfo", return_value=faux):
        eng = C.moteur("sqlserver", {"hote": "vb-test.database.windows.net", "port": 1433, "base": "b",
                                     "utilisateur": "u", "mot_de_passe": "p", "ssl": "exige"})
        autre = C.moteur("sqlserver", {"hote": "sql.exemple.cm", "port": 1433, "base": "b", "utilisateur": "u",
                                       "mot_de_passe": "p", "ssl": "exige"})
    assert isinstance(eng, Engine) and eng.url.host == "vb-test.database.windows.net"
    assert autre.url.host == "20.40.228.15"


def test_tableau_de_bord_grande_table_sur_echantillon(tmp_path):
    """Grande table : répartitions et montants calculés sur un échantillon limité, signalé dans le résultat."""
    import sqlite3

    from app.connecteur import analyse, tableau
    chemin = tmp_path / "banque.sqlite"
    c = sqlite3.connect(chemin)
    c.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, montant REAL, ville TEXT, date_operation TEXT)")
    c.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?)",
                  [(i, 1000.0, ["Douala", "Yaoundé", "Bafoussam"][i % 3], f"2026-{1 + i % 9:02d}-15") for i in range(300)])
    c.commit(); c.close()
    eng = C.moteur("fichier", {}, chemin)
    profil = analyse.analyser(eng, "fichier", "sqlite", None)
    profil["tables"][0]["lignes"] = 300                    # nombre de lignes connu (ici fixé pour le test)
    with patch.object(tableau, "GRANDE_TABLE", 100), patch.object(tableau, "ECHANTILLON_TABLEAU", 120):
        res = tableau.calculer(eng, "fichier", profil)
    montant = next(i for i in res["indicateurs"] if i["type"] == "montant")
    assert montant["echantillon"] == 120 and montant["valeur"] == 120 * 1000.0
    rep = next(g for g in res["graphiques"] if g["id"].startswith("repartition"))
    assert rep["echantillon"] == 120 and sum(p["nb"] for p in rep["donnees"]) == 120
    petit = tableau.calculer(eng, "fichier", profil)                       # seuil normal : toute la table
    assert next(i for i in petit["indicateurs"] if i["type"] == "montant")["valeur"] == 300 * 1000.0


def test_tableau_de_bord_complet_en_arriere_plan(tmp_path):
    """Grande table : aperçu sur échantillon tout de suite, puis calcul sur toutes les lignes en arrière-plan, rangé
    en base et affiché ensuite immédiatement."""
    import sqlite3
    import time as _t
    from types import SimpleNamespace

    from app.connecteur import analyse, service, tableau
    chemin = tmp_path / "banque.sqlite"
    c = sqlite3.connect(chemin)
    c.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, montant REAL, ville TEXT, date_operation TEXT)")
    c.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?)",
                  [(i, 1000.0, ["Douala", "Yaoundé"][i % 2], f"2026-{1 + i % 9:02d}-15") for i in range(300)])
    c.commit(); c.close()
    eng = C.moteur("fichier", {}, chemin)
    profil = analyse.analyser(eng, "fichier", "sqlite", None)
    profil["tables"][0]["lignes"] = 300
    ligne = SimpleNamespace(type_source="fichier", profil=profil)
    ranges = []
    with patch.object(tableau, "GRANDE_TABLE", 100), patch.object(tableau, "ECHANTILLON_TABLEAU", 120), \
            patch.object(service, "_ligne", return_value=ligne), patch.object(service, "_moteur_source", return_value=eng), \
            patch.object(service, "_ranger_tableau", side_effect=lambda i, c, r: ranges.append(r)):
        rapide = tableau.calculer(eng, "fichier", profil)
        assert rapide["complet"] is False
        service._lancer_calcul_complet(987654, "x", "cle", rapide)
        service._lancer_calcul_complet(987654, "x", "cle", rapide)          # déjà en cours : pas de second calcul
        for _ in range(100):
            if 987654 not in service._complets_en_cours:
                break
            _t.sleep(0.05)
    assert len(ranges) == 1 and ranges[0]["complet"] is True and ranges[0]["complet_le"]
    montant = next(i for i in ranges[0]["indicateurs"] if i["type"] == "montant")
    assert montant["valeur"] == 300 * 1000.0 and not montant.get("echantillon")
