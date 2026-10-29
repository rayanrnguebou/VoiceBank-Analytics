"""Validation du SQL avant exécution (SQL généré par l'IA, issu du RAG ou saisi par un admin).

Première ligne de défense. La seconde est en base : le SQL est exécuté avec un
compte en lecture seule, dans une transaction READ ONLY, avec un timeout.
Règles :
  * une seule instruction, de type SELECT (WITH / UNION autorisés) ;
  * uniquement des tables/vues du schéma `voicebank` (sauf les tables internes) ;
  * aucune fonction système dangereuse (lecture de fichiers, sommeil, dblink…) ;
  * nombre de lignes plafonné.
"""
import re

import sqlglot
from sqlglot import exp

SCHEMA = "voicebank"

TABLES_AUTORISEES = {
    "clients", "transactions", "credits", "alertes_fraude",
    "v_dashboard_global", "v_clients_par_banque",
    "v_transactions_mensuelles", "v_portefeuille_credit",
}

# Préfixes / noms de fonctions interdits (accès fichiers, réseau, admin, DoS)
_FONCTIONS_INTERDITES = re.compile(
    r"^(pg_|lo_|dblink|set_config|current_setting|query_to_xml|table_to_xml|"
    r"database_to_xml|cursor_to_xml|xpath|copy|txid_|version$|inet_|has_.*privilege|"
    r"generate_series$|repeat$|"
    # Informations sur le serveur ou la session (version, compte, base) : utiles seulement à un attaquant.
    # Les versions récentes de sqlglot traduisent version() en CURRENT_VERSION, current_user en CURRENT_USER…
    r"current_(version|user|database|schema|schemas|role|catalog|query)|currentversion|currentuser|"
    r"currentdatabase|currentschema|session_user|sessionuser|system_user|user$)",
    re.IGNORECASE,
)


class SQLRefuse(ValueError):
    """Le SQL ne respecte pas les règles de sécurité."""


def _nettoyer(sql: str) -> str:
    sql = re.sub(r"```(?:sql)?", "", sql or "", flags=re.IGNORECASE).strip()
    return sql.rstrip(";").strip()


def valider_sql(sql: str, max_lignes: int) -> str:
    """Retourne une version sûre du SQL (avec LIMIT) ou lève SQLRefuse."""
    sql = _nettoyer(sql)
    if not sql:
        raise SQLRefuse("Requête vide")
    if len(sql) > 5000:
        raise SQLRefuse("Requête trop longue")

    try:
        instructions = [i for i in sqlglot.parse(sql, read="postgres") if i is not None]
    except sqlglot.errors.ParseError:
        raise SQLRefuse("Requête SQL invalide")
    if len(instructions) != 1:
        raise SQLRefuse("Une seule instruction est autorisée")
    arbre = instructions[0]

    if not isinstance(arbre, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise SQLRefuse("Seules les requêtes SELECT sont autorisées")

    # Aucun nœud d'écriture / DDL / commande, même imbriqué
    interdits = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
                 exp.Command, exp.Into, exp.Merge, exp.TruncateTable, exp.Lock)
    for noeud in arbre.walk():
        if isinstance(noeud, interdits):
            raise SQLRefuse("Opération non autorisée")
        if isinstance(noeud, exp.Func):
            # Tous les noms possibles de la fonction (nom SQL, classe sqlglot, nom écrit) : aucun contournement
            noms = {noeud.sql_name() or "", type(noeud).__name__}
            if isinstance(noeud, exp.Anonymous):
                noms.add(noeud.name or "")
            for nom in filter(None, noms):
                if _FONCTIONS_INTERDITES.match(nom):
                    raise SQLRefuse(f"Fonction non autorisée : {nom.lower()}")

    # Tables : schéma voicebank + liste blanche (les CTE sont acceptées)
    ctes = {c.alias_or_name.lower() for c in arbre.find_all(exp.CTE)}
    for table in arbre.find_all(exp.Table):
        nom = table.name.lower()
        schema = (table.db or "").lower()
        if not schema and nom in ctes:
            continue
        if schema != SCHEMA or nom not in TABLES_AUTORISEES:
            raise SQLRefuse(f"Table non autorisée : {table.sql()}")

    # Plafond de lignes : on encapsule plutôt que de modifier la requête
    return f"SELECT * FROM ({arbre.sql(dialect='postgres')}) AS resultat LIMIT {int(max_lignes)}"
