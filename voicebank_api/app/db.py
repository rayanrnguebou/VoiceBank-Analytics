"""Accès base de données.

* `lire()`  : requêtes en lecture, exécutées avec le compte lecture seule, dans
  une transaction READ ONLY et avec un timeout. Utilisée pour tout SQL
  dynamique (IA, RAG, admin) et pour les endpoints de consultation.
* `ecrire()`: requêtes internes paramétrées (journal, RAG) avec le compte applicatif.
"""
import time as _horloge
from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, text

from . import config

# pool_recycle : les bases « serverless » (Neon) ferment les connexions inactives et se mettent en veille
_POOL = dict(pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=280)
moteur_app = create_engine(config.DATABASE_URL, **_POOL)
moteur_lecture = (moteur_app if config.READONLY_DATABASE_URL == config.DATABASE_URL else
                  create_engine(config.READONLY_DATABASE_URL, **_POOL))


def _jsonable(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    return v


def lire(sql: str, params: dict | None = None, brut: bool = False) -> tuple[list[str], list[dict]]:
    """brut=True : SQL dynamique déjà validé, envoyé tel quel (sans interprétation
    des ':' comme paramètres, ex. '22:00'::time)."""
    with moteur_lecture.connect() as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {int(config.SQL_TIMEOUT_MS)}"))
            if brut:
                # Curseur DBAPI direct, sans paramètres : ni ':' ni '%' ne sont interprétés.
                cur = conn.connection.dbapi_connection.cursor()
                try:
                    cur.execute(sql)
                    colonnes = [d[0] for d in cur.description]
                    rows = cur.fetchall()
                finally:
                    cur.close()
            else:
                res = conn.execute(text(sql), params or {})
                colonnes, rows = list(res.keys()), res.fetchall()
            lignes = [{c: _jsonable(v) for c, v in zip(colonnes, row)} for row in rows]
    return colonnes, lignes


def ecrire(sql: str, params: dict | None = None) -> SimpleNamespace:
    """Retourne rowcount, lignes (si RETURNING) et scalar() — lus AVANT la fin de la transaction."""
    with moteur_app.begin() as conn:
        res = conn.execute(text(sql), params or {})
        lignes = res.fetchall() if res.returns_rows else []
        nb = res.rowcount
    return SimpleNamespace(rowcount=nb, lignes=lignes, scalar=lambda: lignes[0][0] if lignes else None)


_dernier_ok = {"t": 0.0}


def base_ok(cache_s: float = 0) -> bool:
    """La base répond-elle ? `cache_s` : un succès récent suffit (sondes de surveillance), pour ne pas
    réveiller toutes les 5 minutes une base qui se met en veille quand personne ne s'en sert (Neon)."""
    if cache_s and _horloge.time() - _dernier_ok["t"] < cache_s:
        return True
    try:
        lire("SELECT 1")
        _dernier_ok["t"] = _horloge.time()
        return True
    except Exception:
        return False
