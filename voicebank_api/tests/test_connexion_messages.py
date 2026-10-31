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
    paquet = MysqlPacket(b"\x03a\x8bz\x0242", "utf8")
    assert r._read_row_from_packet(paquet) == ("a�z", 42)


def test_inspection_mysql_tolerante():
    """Réponse binaire Latin-1 d'une commande d'inspection (vieux serveur) : lue avec un caractère de remplacement."""
    from sqlalchemy.dialects.mysql.base import _DecodingRow

    class Ligne(tuple):
        nom = b"famille_\x8b"
    r = _DecodingRow(Ligne((b"s\x8bx", "ok")), "utf8mb4")
    assert r[0] == "s�x" and r[1] == "ok" and r.nom == "famille_�"
