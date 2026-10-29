"""Garde SQL pour les bases des organisations, quel que soit le moteur (PostgreSQL, MySQL, SQL Server, Oracle, SQLite).

N'accepte qu'UNE requête de lecture (SELECT / UNION / WITH … SELECT) portant uniquement sur les tables
découvertes lors de l'analyse, sans fonction dangereuse (fichiers, réseau, temporisation, administration),
puis plafonne le nombre de lignes dans le dialecte du moteur (LIMIT ou TOP).
"""
import sqlglot
from sqlglot import exp

from . import oracle

INTERDITS = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Merge,
             exp.Into, exp.Lock, exp.Grant, exp.TruncateTable, exp.Set, exp.Use, exp.Transaction, exp.Commit,
             exp.Rollback, exp.Copy, exp.LoadData, exp.Pragma)
PREFIXES_INTERDITS = ("pg_", "lo_", "dblink", "xp_", "sp_", "fn_", "sys_", "load_", "openrowset", "opendatasource",
                      "openquery", "openxml", "bulk", "readfile", "writefile", "sleep", "benchmark", "waitfor",
                      "set_config", "current_setting", "query_to_xml", "load_file", "inet_", "version")
FONCTIONS_INTERDITES = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer", "get_lock",
                        "release_lock", "user", "system_user", "current_user", "session_user", "database",
                        "uuid_short", "master_pos_wait", "extractvalue", "updatexml", "row_count", "found_rows"}


# Informations sur le serveur, la session ou les droits : inutiles pour l'analyse, utiles à un attaquant
PREFIXES_SYSTEME = ("db_", "host_", "suser", "user_", "schema", "object_", "server", "connection", "is_srv",
                    "has_", "current_", "txid", "session_", "app_name", "original_", "context_info")
AUTORISEES = {"current_date", "current_timestamp", "current_time", "currentdate", "currenttimestamp",
              "currenttime", "current_datetime", "currentdatetime"}


class SQLRefuse(ValueError):
    pass


def _noms_fonction(f: exp.Expression) -> set[str]:
    noms = {type(f).__name__.lower(), (f.sql_name() or "").lower()}
    if isinstance(f, exp.Anonymous):
        noms.add(str(f.this).lower())
    try:
        noms.add(f.sql().split("(")[0].strip().lower())
    except Exception:
        pass
    return {n for n in noms if n}


def valider(sql: str, dialecte: str, tables_autorisees: set[str], max_lignes: int = 1000,
            schemas_autorises: set[str] | None = None) -> str:
    """Retourne le SQL sûr, dans le dialecte du moteur. `tables_autorisees` : noms en minuscules ;
    `schemas_autorises` : schémas permis devant un nom de table (en minuscules)."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise SQLRefuse("Requête vide")
    if ";" in sql:
        raise SQLRefuse("Une seule requête à la fois")
    try:
        requetes = sqlglot.parse(sql, read=dialecte)
    except sqlglot.errors.ParseError:
        raise SQLRefuse("Requête illisible")
    if len(requetes) != 1 or requetes[0] is None:
        raise SQLRefuse("Une seule requête à la fois")
    arbre = requetes[0]
    if not isinstance(arbre, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise SQLRefuse("Seules les requêtes de lecture (SELECT) sont autorisées")
    for noeud in arbre.walk():
        if isinstance(noeud, (exp.SessionParameter, exp.Parameter, exp.Placeholder)):
            raise SQLRefuse("Variables système interdites")
        if isinstance(noeud, INTERDITS):
            raise SQLRefuse(f"Instruction interdite : {type(noeud).__name__}")
        if isinstance(noeud, exp.Func):
            noms = _noms_fonction(noeud)
            if noms & AUTORISEES:
                continue
            for nom in noms:
                if (nom in FONCTIONS_INTERDITES or nom.startswith(PREFIXES_INTERDITS)
                        or nom.startswith(PREFIXES_SYSTEME)):
                    raise SQLRefuse(f"Fonction interdite : {nom}")
    if dialecte == oracle.DIALECTE and (motif := oracle.controler(arbre)):
        raise SQLRefuse(motif)
    ctes = {c.alias_or_name.lower() for c in arbre.find_all(exp.CTE)}
    for table in arbre.find_all(exp.Table):
        nom = table.name.lower()
        if not nom:
            raise SQLRefuse("Source de données non autorisée")
        if nom in ctes and not table.args.get("db"):
            continue
        if nom not in tables_autorisees:
            raise SQLRefuse(f"Table inconnue : {table.name}")
        if table.args.get("catalog") is not None:
            raise SQLRefuse("Accès à une autre base interdit")
        schema = table.args.get("db")
        if schema is not None and schema.name.lower() not in (schemas_autorises or set()):
            raise SQLRefuse(f"Schéma non autorisé : {schema.name}")
    # Plafond de lignes : directement sur le SELECT (TOP en SQL Server), sinon en sous-requête
    if isinstance(arbre, exp.Select):
        limite = arbre.args.get("limit")
        try:
            # LIMIT n, TOP n ou FETCH FIRST n ROWS ONLY (Oracle)
            borne = (limite.args.get("count") if isinstance(limite, exp.Fetch) else limite.expression) if limite is not None else None
            existant = int(borne.name) if borne is not None else None
        except (AttributeError, ValueError):
            existant = None
        if existant is None or existant > max_lignes:
            arbre = arbre.limit(max_lignes)
        return arbre.sql(dialect=dialecte)
    return exp.select("*").from_(arbre.subquery("resultat")).limit(max_lignes).sql(dialect=dialecte)
