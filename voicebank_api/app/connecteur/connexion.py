"""Connexion aux sources de données des organisations, en lecture seule.

Sécurité :
* identifiants chiffrés en base (Fernet / AES-128-CBC + HMAC), jamais renvoyés au navigateur ;
* anti-SSRF : l'adresse est résolue une fois, les adresses privées / locales sont refusées en ligne,
  et la connexion se fait sur l'adresse vérifiée (pas de « DNS rebinding ») ;
* sessions en lecture seule quand le moteur le permet, transaction toujours annulée, délais limités ;
* le SQL exécuté passe d'abord par la garde (garde.py) : une seule requête SELECT sur les tables connues.
"""
import base64
import hashlib
import ipaddress
import json
import logging
import socket
import sqlite3
import ssl as ssl_mod
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import certifi
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from .. import config
from . import oracle  # noqa: F401  (enregistre le dialecte SQL « oraclevb »)

log = logging.getLogger("voicebank")

TYPES = {
    "postgresql": {"libelle": "PostgreSQL", "port": 5432, "dialecte": "postgres", "schema": "public"},
    "mysql":      {"libelle": "MySQL / MariaDB", "port": 3306, "dialecte": "mysql", "schema": None},
    "sqlserver":  {"libelle": "SQL Server", "port": 1433, "dialecte": "tsql", "schema": "dbo"},
    "oracle":     {"libelle": "Oracle", "port": 1521, "dialecte": "oraclevb", "schema": None},   # schéma : celui du compte
    "fichier":    {"libelle": "Excel / CSV", "port": None, "dialecte": "sqlite", "schema": None},
    "demo":       {"libelle": "Démonstration VoiceBank", "port": None, "dialecte": "postgres", "schema": "voicebank"},
}


class ConnexionRefusee(Exception):
    """Message affichable à l'utilisateur."""


# ── Chiffrement des identifiants ───────────────────────────────────────

def _cle(secret: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("voicebank-sources:" + secret).encode()).digest()))


def _fernet() -> MultiFernet:
    """Chiffre avec CLE_SOURCES ; déchiffre aussi avec les anciennes clés (rotation sans coupure)."""
    return MultiFernet([_cle(config.CLE_SOURCES)] + [_cle(c) for c in config.CLE_SOURCES_ANCIENNES])


def rechiffrer(jeton: str) -> str:
    """Rechiffre avec la clé actuelle un jeton chiffré avec une ancienne clé (lève InvalidToken si illisible)."""
    return _fernet().rotate(jeton.encode()).decode()


def chiffrer(donnees: dict) -> str:
    return _fernet().encrypt(json.dumps(donnees).encode()).decode()


def dechiffrer(jeton: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(jeton.encode()))
    except (InvalidToken, ValueError):
        raise ConnexionRefusee("Identifiants illisibles (clé de chiffrement modifiée) : reconnecte la source.")


# ── Anti-SSRF ────────────────────────────────────────────────────────

def verifier_hote(hote: str) -> str:
    """Résout l'hôte et retourne une adresse IP autorisée."""
    hote = (hote or "").strip()
    if not hote or len(hote) > 253 or any(c in hote for c in "/\\@ ?#"):
        raise ConnexionRefusee("Adresse du serveur invalide")
    try:
        adresses = {i[4][0] for i in socket.getaddrinfo(hote, None, proto=socket.IPPROTO_TCP)}
    except socket.gaierror:
        raise ConnexionRefusee(f"Serveur introuvable : {hote}")
    for a in sorted(adresses):
        ip = ipaddress.ip_address(a.split("%")[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:      # ::ffff:127.0.0.1 → 127.0.0.1
            ip = ip.ipv4_mapped
        # « non globale » couvre aussi 100.64.0.0/10 (réseau partagé des hébergeurs), 0.0.0.0/8, 198.18.0.0/15…
        interdite = (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                     or ip.is_reserved or ip.is_unspecified)
        if interdite and not config.CONNECTEUR_RESEAU_PRIVE:
            raise ConnexionRefusee("Adresse privée ou locale refusée : la base doit être joignable sur Internet "
                                   "(ou utilise l'outil en local pour une base du réseau de l'entreprise).")
    return sorted(adresses)[0]


# ── Moteurs ──────────────────────────────────────────────────────────

def _jsonable(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(v))} octets>"
    if isinstance(v, float) and v != v:
        return None
    return v


def _fonctions_sqlite(conn):
    """Fonctions de date communes aux autres moteurs (YEAR, MONTH…) pour les fichiers importés."""
    def partie(i):
        return lambda v: int(str(v)[i[0]:i[1]]) if v and str(v)[i[0]:i[1]].isdigit() else None
    conn.create_function("YEAR", 1, partie((0, 4)), deterministic=True)
    conn.create_function("MONTH", 1, partie((5, 7)), deterministic=True)
    conn.create_function("DAY", 1, partie((8, 10)), deterministic=True)


def moteur(type_source: str, cfg: dict, chemin_fichier: Path | None = None):
    """Crée un moteur SQLAlchemy sans pool (aucune connexion gardée ouverte)."""
    t = config.CONNECTEUR_TIMEOUT_S
    if type_source == "demo":
        from .. import db
        return db.moteur_lecture
    if type_source == "fichier":
        if not chemin_fichier or not chemin_fichier.exists():
            raise ConnexionRefusee("Fichiers de la source introuvables")

        def creer():
            c = sqlite3.connect(f"file:{chemin_fichier}?mode=ro", uri=True, check_same_thread=False, timeout=t)
            _fonctions_sqlite(c)
            return c
        return create_engine("sqlite://", creator=creer, poolclass=NullPool)

    ip = verifier_hote(cfg.get("hote", ""))
    port = int(cfg.get("port") or TYPES[type_source]["port"])
    if not 1 <= port <= 65535:
        raise ConnexionRefusee("Port invalide")
    ssl = cfg.get("ssl", "prefere")
    commun = dict(username=cfg.get("utilisateur"), password=cfg.get("mot_de_passe"), port=port, database=cfg.get("base"))
    # « verifie » : chiffrement ET identité du serveur contrôlée (certificat signé par une autorité reconnue, au nom
    # de l'hôte saisi) ; « exige » chiffre sans vérifier l'identité ; « prefere » chiffre si le serveur le propose.
    if ssl == "verifie" and type_source == "sqlserver":
        raise ConnexionRefusee("La vérification du certificat n'est pas encore disponible pour SQL Server : "
                               "choisis « Exigé ».")
    if type_source == "postgresql":
        url = URL.create("postgresql+psycopg2", host=cfg["hote"], **commun)
        args = {"hostaddr": ip, "connect_timeout": 10,
                "sslmode": {"verifie": "verify-full", "exige": "require", "desactive": "disable"}.get(ssl, "prefer"),
                "options": f"-c default_transaction_read_only=on -c statement_timeout={t * 1000}",
                "application_name": "VoiceBank Analytics"}
        if ssl == "verifie":
            args["sslrootcert"] = certifi.where()      # autorités reconnues (le nom vérifié est celui saisi, pas l'IP)
    elif type_source == "mysql":
        # En mode vérifié, le certificat est contrôlé au nom de l'hôte : une redirection DNS vers une autre machine
        # échouerait faute de certificat valide pour ce nom.
        url = URL.create("mysql+pymysql", host=cfg["hote"] if ssl == "verifie" else ip, query={"charset": "utf8mb4"},
                         **commun)
        args = {"connect_timeout": 10, "read_timeout": t + 5, "write_timeout": t + 5}
        if ssl == "exige":
            args["ssl"] = {"check_hostname": False}
        elif ssl == "verifie":
            args["ssl"] = {"ca": certifi.where(), "check_hostname": True}
    elif type_source == "sqlserver":
        url = URL.create("mssql+pymssql", host=ip, **commun)
        args = {"login_timeout": 10, "timeout": t + 5, "appname": "VoiceBank Analytics"}
    elif type_source == "oracle":
        # « base » = nom du service (ex. ORCLPDB1, XEPDB1, FREEPDB1). Chiffrement TLS (TCPS) en « exigé » / « vérifié » :
        # le port est alors souvent 2484. « Préféré » se connecte en clair (le pilote ne négocie pas le chiffrement).
        commun.pop("database")
        verifie = ssl == "verifie"
        url = URL.create("oracle+oracledb", host=cfg["hote"] if verifie else ip, query={"service_name": cfg.get("base")},
                         **commun)
        args = {"tcp_connect_timeout": 10, "retry_count": 0}
        if ssl in ("exige", "verifie"):
            ctx = ssl_mod.create_default_context(cafile=certifi.where())
            if not verifie:
                ctx.check_hostname = False
                ctx.verify_mode = ssl_mod.CERT_NONE
            args.update(protocol="tcps", ssl_context=ctx, ssl_server_dn_match=verifie)
    else:
        raise ConnexionRefusee("Type de source inconnu")
    return create_engine(url, poolclass=NullPool, connect_args=args)


def _preparer_session(conn, type_source: str):
    """Lecture seule et délai maximal, selon ce que le moteur permet."""
    t = config.CONNECTEUR_TIMEOUT_S
    if type_source == "mysql":
        for instruction in ("SET SESSION TRANSACTION READ ONLY", f"SET SESSION MAX_EXECUTION_TIME = {t * 1000}",
                            f"SET SESSION max_statement_time = {t}"):
            try:
                conn.exec_driver_sql(instruction)
            except Exception:
                pass                                   # MySQL et MariaDB n'ont pas les mêmes variables
    elif type_source == "oracle":
        conn.connection.driver_connection.call_timeout = (t + 5) * 1000   # coupe toute requête trop longue
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    elif type_source == "sqlserver":
        conn.exec_driver_sql("SET LOCK_TIMEOUT 5000")
        conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")


@contextmanager
def connexion_lecture(eng, type_source: str):
    with eng.connect() as conn:
        if type_source == "demo":
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {config.CONNECTEUR_TIMEOUT_S * 1000}"))
        else:
            _preparer_session(conn, type_source)
        try:
            yield conn
        finally:
            conn.rollback()                            # rien n'est jamais validé


def executer(eng, type_source: str, sql: str, max_lignes: int = 1000) -> tuple[list[str], list[dict]]:
    with connexion_lecture(eng, type_source) as conn:
        res = conn.exec_driver_sql(sql)
        colonnes = list(res.keys())
        lignes = [{c: _jsonable(v) for c, v in zip(colonnes, row)} for row in res.fetchmany(max_lignes)]
    return colonnes, lignes


def message_erreur(e: Exception) -> str:
    """Erreur de connexion lisible, sans fuite d'informations internes."""
    if isinstance(e, ConnexionRefusee):
        return str(e)
    t = str(e).lower()
    if "ora-12514" in t or "ora-12505" in t or "dpy-6001" in t or "dpy-6003" in t:
        return "Service Oracle introuvable : vérifie le nom du service (ex. ORCLPDB1, XEPDB1)."
    if ("password" in t or "authentication" in t or "access denied" in t or "login failed" in t or "18456" in t
            or "ora-01017" in t or "ora-28000" in t):
        return "Identifiant ou mot de passe refusé par la base."
    if "timeout" in t or "timed out" in t:
        return "Le serveur ne répond pas (délai dépassé) : vérifie l'adresse, le port et le pare-feu."
    if "refused" in t or "dpy-6005" in t or "could not connect" in t or "can't connect" in t or "unable to connect" in t or "20009" in t:
        return "Connexion refusée : vérifie l'adresse, le port et que le serveur accepte les connexions externes."
    if "does not exist" in t or "unknown database" in t or "cannot open database" in t or "4060" in t:
        return "Base de données introuvable : vérifie son nom."
    if "ssl" in t:
        if "certificate" in t or "certificat" in t or "verify" in t:
            return ("Certificat du serveur non reconnu (autorité inconnue ou nom différent) : la connexion « vérifiée » "
                    "a été refusée par sécurité. Utilise le nom exact du serveur, ou l'option « Exigé ».")
        return "Problème de chiffrement SSL : essaie l'option SSL « préféré » ou « exigé »."
    return "Connexion impossible à la base. Vérifie les informations saisies."
