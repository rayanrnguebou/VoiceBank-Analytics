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
