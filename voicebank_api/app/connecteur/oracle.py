"""Oracle (11g R2 et plus, pilote python-oracledb en mode « thin » : aucun client Oracle à installer).

Oracle range en MAJUSCULES les noms créés sans guillemets ; SQLAlchemy les présente en minuscules. Le dialecte
« oraclevb » écrit donc les identifiants tout en minuscules entre guillemets en MAJUSCULES ("CLIENTS"), ce qui
désigne exactement l'objet, même si son nom est un mot réservé. Les noms à casse mixte restent tels quels.
"""
from sqlglot import exp
from sqlglot.dialects.oracle import Oracle

DIALECTE = "oraclevb"

# Fonctions libres (non reconnues par l'analyseur SQL) permises sur Oracle : calcul, texte, dates, fenêtres.
# Toute autre fonction est refusée — une fonction maison pourrait écrire (transaction autonome) ou sortir du réseau.
FONCTIONS_PERMISES = {
    "nvl", "nvl2", "nullif", "lpad", "rpad", "ltrim", "rtrim", "trim", "last_day", "next_day", "to_timestamp",
    "width_bucket", "percentile_cont", "percentile_disc", "ratio_to_report", "ntile", "lag", "lead", "row_number",
    "rank", "dense_rank", "greatest", "least", "ceil", "power", "sqrt", "exp", "ln", "log", "sign", "trunc", "round",
    "replace", "translate", "concat", "chr", "ascii", "numtodsinterval", "numtoyminterval", "regexp_substr",
    "regexp_replace", "regexp_count", "regexp_instr", "corr", "variance", "covar_pop", "covar_samp", "stddev_pop",
    "stddev_samp", "var_pop", "var_samp", "cume_dist", "percent_rank", "first_value", "last_value", "nth_value",
    "to_char", "to_date", "to_number", "months_between", "add_months", "decode", "listagg", "bitand", "mod",
    "initcap", "lower", "upper", "length", "substr", "instr", "median", "count", "sum", "avg", "min", "max",
}
# Pseudo-colonnes qui renseignent sur la session ou le serveur
PSEUDO_COLONNES = {"user", "uid", "sessiontimezone", "dbtimezone", "ora_rowscn", "ora_database_name",
                   "ora_login_user", "ora_client_ip_address"}


class Oraclevb(Oracle):
    class Generator(Oracle.Generator):
        def identifier_sql(self, expression: exp.Identifier) -> str:
            nom = expression.this
            if expression.quoted and isinstance(nom, str) and nom == nom.lower() and nom != nom.upper():
                expression = expression.copy()
                expression.set("this", nom.upper())
            return super().identifier_sql(expression)


def controler(arbre: exp.Expression) -> str | None:
    """Motif de refus propre à Oracle, ou None."""
    for n in arbre.walk():
        if isinstance(n, exp.Dot) and n.find(exp.Func):
            return "Appel de paquetage interdit"
        if isinstance(n, exp.Anonymous) and str(n.this).lower() not in FONCTIONS_PERMISES:
            return f"Fonction non autorisée : {str(n.this).lower()}"
        if isinstance(n, exp.Column) and not n.table and not n.this.quoted and n.name.lower() in PSEUDO_COLONNES:
            return f"Information système interdite : {n.name.lower()}"
    return None
