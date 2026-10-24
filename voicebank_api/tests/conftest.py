"""Prépare une base PostgreSQL de test complète (scripts d'init + rôles + données synthétiques).

Variable requise : TEST_PG_ADMIN_URL (superutilisateur), ex.
  postgresql://postgres@/postgres?host=/tmp&port=5433
"""
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import bcrypt
import psycopg2
import pytest

RACINE = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL", "postgresql://postgres@/postgres?host=/tmp&port=5433")
BASE = "voicebank_test"


def _url(user: str, pwd: str | None = None, base: str = BASE) -> str:
    p = urlsplit(ADMIN_URL)
    hote = p.netloc.split("@")[-1]
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    return urlunsplit((p.scheme, auth + hote, f"/{base}", p.query, ""))


def _preparer_base():
    c = psycopg2.connect(ADMIN_URL)
    c.autocommit = True
    c.cursor().execute(f"DROP DATABASE IF EXISTS {BASE} WITH (FORCE)")
    c.cursor().execute(f"CREATE DATABASE {BASE}")
    c.close()
    a = urlsplit(ADMIN_URL)
    url_admin = _url(a.username or "postgres", a.password)
    init = RACINE / "voicebank_db" / "init"
    for f in ["01_init_voicebank.sql", "02_corrections_rag.sql"]:
        subprocess.run(["psql", url_admin, "-q", "-v", "ON_ERROR_STOP=1", "-f", str(init / f)],
                       check=True, capture_output=True)
    subprocess.run(["psql", url_admin, "-q", "-v", "app_pwd=app_test_pwd_123", "-v",
                    "reader_pwd=reader_test_pwd_123", "-f",
                    str(RACINE / "voicebank_db" / "securite" / "roles.sql")], check=True, capture_output=True)

    from tests.donnees_test import inserer

    class _Conn:
        def __init__(self, cur): self.cur = cur
        def execute_many(self, sql, rows): self.cur.executemany(sql, rows)

    with psycopg2.connect(url_admin) as c:
        inserer(_Conn(c.cursor()))


def _hash(mdp: str) -> str:
    return bcrypt.hashpw(mdp.encode(), bcrypt.gensalt(rounds=4)).decode()


_preparer_base()
os.environ.update({
    "ENV": "test",
    "DATABASE_URL": _url("voicebank_app", "app_test_pwd_123"),
    "READONLY_DATABASE_URL": _url("voicebank_reader", "reader_test_pwd_123"),
    "JWT_SECRET": "x" * 40,
    "VOICEBANK_USERS": f"analyste1:analyste:{_hash('motdepasse-analyste')},"
                       f"rayan:admin:{_hash('motdepasse-admin')}",
    "GEMINI_API_KEY": "", "GROQ_API_KEY": "",
    "RATE_LIMIT_ACTIF": "false",
    "ALLOWED_ORIGINS": "http://localhost:3000",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def _jeton(client, nom, mdp):
    r = client.post("/auth/login", json={"nom": nom, "mot_de_passe": mdp})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def analyste(client):
    return _jeton(client, "analyste1", "motdepasse-analyste")


@pytest.fixture(scope="session")
def admin(client):
    return _jeton(client, "rayan", "motdepasse-admin")
