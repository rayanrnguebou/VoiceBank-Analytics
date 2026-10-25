"""Analyse d'une base inconnue : structure, sens métier, qualité des données, questions utiles.

Tout est calculé sur un ÉCHANTILLON (500 lignes par table au plus) et quelques requêtes de comptage,
avec des délais limités : l'analyse reste rapide et légère, même sur une grosse base de production.
"""
import logging
import re
from datetime import date, datetime, timedelta

import pandas as pd
import sqlglot
from sqlalchemy import inspect
from sqlglot import exp

from .. import config
from . import semantique as sem
from .connexion import connexion_lecture

log = logging.getLogger("voicebank")

ECHANTILLON = 500
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
RE_TEL = re.compile(r"^\+?[0-9][0-9 .\-]{7,16}$")
RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}|^\d{2}/\d{2}/\d{4}")


def _table_sql(nom: str, schema: str | None, dialecte: str) -> exp.Table:
    return exp.table_(exp.to_identifier(nom, quoted=True),
                      db=exp.to_identifier(schema, quoted=True) if schema else None)


def _echantillon(conn, nom, schema, dialecte, colonnes):
    # Les colonnes secrètes (mots de passe, jetons…) ne sont jamais lues
    lisibles = [c for c in colonnes if sem.role_par_nom(c)[0] != "secret"] or colonnes[:1]
    sql = (exp.select(*[exp.column(exp.to_identifier(c, quoted=True)) for c in lisibles])
           .from_(_table_sql(nom, schema, dialecte)).limit(ECHANTILLON).sql(dialect=dialecte))
    res = conn.exec_driver_sql(sql)
    return pd.DataFrame(res.fetchall(), columns=list(res.keys()))


def _compter(conn, nom, schema, dialecte, type_source) -> int | None:
    """Estimation rapide depuis le catalogue, comptage exact si la table est petite."""
    estimation = None
    try:
        if type_source in ("postgresql", "demo"):
            estimation = conn.exec_driver_sql(
                "SELECT c.reltuples::bigint FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relname = %(t)s AND n.nspname = %(s)s", {"t": nom, "s": schema or "public"}).scalar()
        elif type_source == "mysql":
            estimation = conn.exec_driver_sql(
                "SELECT TABLE_ROWS FROM information_schema.TABLES WHERE TABLE_NAME = %(t)s "
                "AND TABLE_SCHEMA = DATABASE()", {"t": nom}).scalar()
        elif type_source == "sqlserver":
            estimation = conn.exec_driver_sql(
                "SELECT SUM(p.rows) FROM sys.partitions p JOIN sys.tables t ON t.object_id = p.object_id "
                "WHERE t.name = %(t)s AND p.index_id IN (0, 1)", {"t": nom}).scalar()
    except Exception:
        conn.rollback()
    if estimation is not None and int(estimation) > 2_000_000:
        return int(estimation)
    try:
        sql = exp.select(exp.Count(this=exp.Star())).from_(_table_sql(nom, schema, dialecte)).sql(dialect=dialecte)
        return int(conn.exec_driver_sql(sql).scalar())
    except Exception:
        conn.rollback()
        return int(estimation) if estimation is not None and int(estimation) >= 0 else None


def _profil_colonne(nom: str, type_sql: str, s: pd.Series, n_lignes: int) -> dict:
    role, pii = sem.role_par_nom(nom)
    if role == "secret":          # jamais lue : aucune statistique
        return {"nom": nom, "type_sql": type_sql, "nulls_pct": None, "distincts": 0, "nature": "texte",
                "role": "secret", "pii": None}
    nn = s.dropna()
    p = {"nom": nom, "type_sql": type_sql, "nulls_pct": round(100 * (1 - len(nn) / n_lignes), 1) if n_lignes else 0.0,
         "distincts": int(nn.astype(str).nunique()) if len(nn) else 0}
    t = type_sql.lower()
    nature = "texte"
    if len(nn) and pd.api.types.is_bool_dtype(nn):
        nature = "booleen"
    elif any(k in t for k in ("date", "time")) or (len(nn) and pd.api.types.is_datetime64_any_dtype(nn)):
        nature = "date"
    elif any(k in t for k in ("int", "numeric", "decimal", "float", "double", "real", "money", "number")):
        nature = "nombre"
    elif len(nn):
        txt = nn.astype(str)
        if txt.str.match(RE_DATE).mean() > 0.9:
            nature = "date"
        else:
            num = pd.to_numeric(txt.str.replace(",", ".", regex=False).str.replace(" ", "", regex=False), errors="coerce")
            zeros_tete = txt.str.match(r"^0\d").mean() > 0.2           # codes « 00123 » : pas des nombres
            if num.notna().mean() > 0.95 and not zeros_tete:
                nature = "nombre"
            elif pii is None:
                if txt.str.match(RE_EMAIL).mean() > 0.6:
                    pii = "email"
                elif txt.str.match(RE_TEL).mean() > 0.6 and nature == "texte":
                    pii = "telephone"
    p["nature"] = nature
    if nature == "nombre" and len(nn):
        v = pd.to_numeric(nn.astype(str).str.replace(",", ".", regex=False).str.replace(" ", "", regex=False), errors="coerce").dropna()
        if len(v):
            p.update(min=float(v.min()), max=float(v.max()), moyenne=round(float(v.mean()), 2),
                     negatifs=int((v < 0).sum()))
            if v.nunique() <= 2 and set(v.unique()) <= {0, 1} and role is None:
                nature = p["nature"] = "booleen"
    if nature == "date" and len(nn):
        d = pd.to_datetime(nn.astype(str), errors="coerce", format="mixed", utc=False)
        d = d.dropna()
        if len(d):
            p.update(date_min=str(d.min())[:10], date_max=str(d.max())[:10])
    # Rôle final : le nom d'abord, puis le contenu
    if role is None:
        if nature == "date":
            role = "date"
        elif nature == "nombre":
            role = "identifiant" if (p["distincts"] == len(nn) and len(nn) > 20 and float(p.get("min", 0)) >= 0
                                     and str(nom).lower().endswith(("id", "no", "num"))) else "mesure"
        elif nature == "booleen":
            role = "categorie"
        elif pii:
            role = "texte"
        else:
            role = "categorie" if 0 < p["distincts"] <= 50 and p["distincts"] <= 0.5 * max(len(nn), 1) else "texte"
    if pii and role in ("mesure", "categorie", None):
        role = "texte"
    if role in ("montant", "taux", "score", "quantite") and nature not in ("nombre",):
        role = "categorie" if p["distincts"] <= 50 else "texte"
    p["role"], p["pii"] = role, pii
    # Valeurs fréquentes : utiles pour comprendre « à Douala », « en retard »… jamais pour les données perso
    if role in ("categorie", "statut", "geographie", "drapeau_fraude") and not pii and role != "secret" and len(nn):
        vc = nn.astype(str).str.slice(0, 40).value_counts().head(8)
        p["valeurs"] = [{"valeur": k, "nb": int(v)} for k, v in vc.items()]
    return p


def _relations(tables: dict, insp, schema) -> list[dict]:
    rels = []
    for nom, t in tables.items():
        try:
            for fk in insp.get_foreign_keys(nom, schema=schema):
                if fk.get("referred_table") in tables and fk.get("constrained_columns"):
                    rels.append({"de": nom, "colonne": fk["constrained_columns"][0], "vers": fk["referred_table"],
                                 "colonne_cible": (fk.get("referred_columns") or [None])[0], "deduite": False})
        except Exception:
            pass
    # Relations déduites des noms : customer_id → customers.id / id_client → clients
    connues = {(r["de"], r["colonne"]) for r in rels}
    for nom, t in tables.items():
        for c in t["colonnes"]:
            if (nom, c["nom"]) in connues or c["nom"] in t["cle_primaire"] or c["role"] != "identifiant":
                continue
            j = set(sem.jetons(c["nom"])) - {"id", "code", "no", "num", "numero", "ref", "fk", "key"}
            for cible, tc in tables.items():
                if cible == nom or not tc["cle_primaire"]:
                    continue
                noms_cible = {sem.singulier(x) for x in sem.jetons(cible)} | set(sem.jetons(cible))
                if j and (j & noms_cible or (tc.get("entite") and tc["entite"] == sem.entite_table(" ".join(j)))):
                    rels.append({"de": nom, "colonne": c["nom"], "vers": cible, "colonne_cible": tc["cle_primaire"][0],
                                 "deduite": True})
                    break
    return rels


def _orphelins(conn, rel, schema, dialecte) -> int | None:
    """Lignes dont la référence pointe vers une ligne inexistante (sur un échantillon de 10 000 lignes)."""
    if not rel.get("colonne_cible"):
        return None
    enfant = _table_sql(rel["de"], schema, dialecte)
    parent = _table_sql(rel["vers"], schema, dialecte)
    c, pk = exp.to_identifier(rel["colonne"], quoted=True), exp.to_identifier(rel["colonne_cible"], quoted=True)
    sous = exp.select("1").from_(parent.as_("p")).where(exp.EQ(this=exp.column(pk, table="p"), expression=exp.column(c, table="e")))
    echant = exp.select(exp.column(c)).from_(enfant).where(exp.column(c).is_(exp.null()).not_()).limit(10000).subquery("e")
    req = exp.select(exp.Count(this=exp.Star())).from_(echant).where(exp.Exists(this=sous).not_())
    try:
        return int(conn.exec_driver_sql(req.sql(dialect=dialecte)).scalar())
    except Exception:
        conn.rollback()
        return None


def _diagnostics(tables: dict, rels: list, orphelins: dict) -> tuple[list[dict], int]:
    diag, penalite = [], 0
    aujourdhui = date.today()

    def ajouter(gravite, table, colonne, message):
        nonlocal penalite
        diag.append({"gravite": gravite, "table": table, "colonne": colonne, "message": message})
        penalite += {"critique": 8, "attention": 3, "info": 0}[gravite]

    for nom, t in tables.items():
        if t["lignes"] == 0:
            ajouter("attention", nom, None, "Table vide.")
            continue
        if not t["cle_primaire"]:
            ajouter("attention", nom, None, "Pas de clé primaire : des doublons sont possibles.")
        for c in t["colonnes"]:
            if c["role"] == "secret":
                ajouter("info", nom, c["nom"], "Donnée secrète détectée : elle ne sera jamais lue ni affichée.")
                continue
            if (c["nulls_pct"] or 0) >= 99.9:
                ajouter("attention", nom, c["nom"], "Colonne toujours vide.")
            elif (c["nulls_pct"] or 0) >= 30 and c["role"] in ("montant", "date", "statut", "identifiant", "geographie"):
                ajouter("attention", nom, c["nom"], f"{c['nulls_pct']} % de valeurs manquantes.")
            if c["distincts"] == 1 and (t["lignes"] or 0) > 10 and (c["nulls_pct"] or 0) < 50:
                ajouter("info", nom, c["nom"], "Toujours la même valeur : colonne peut-être inutile.")
            if c["role"] == "montant" and c.get("negatifs"):
                ajouter("attention", nom, c["nom"], f"{c['negatifs']} montant(s) négatif(s) dans l'échantillon.")
            if c.get("date_max"):
                try:
                    dmax = datetime.fromisoformat(c["date_max"]).date()
                    dmin = datetime.fromisoformat(c["date_min"]).date()
                except ValueError:
                    continue
                if dmax > aujourdhui + timedelta(days=1) and not set(sem.jetons(c["nom"])) & {"echeance", "due", "fin", "end", "expiration", "maturite"}:
                    ajouter("attention", nom, c["nom"], f"Dates dans le futur (jusqu'au {c['date_max']}).")
                if dmin.year < 1900:
                    ajouter("attention", nom, c["nom"], f"Dates improbables (dès {c['date_min']}).")
            if c["pii"]:
                ajouter("info", nom, c["nom"], f"Donnée personnelle ({c['pii'].replace('_', ' ')}) : masquée et jamais envoyée à l'IA.")
        if t["doublons"]:
            ajouter("critique", nom, t["cle_primaire"][0] if t["cle_primaire"] else None,
                    f"{t['doublons']} identifiant(s) en double dans l'échantillon.")
        dates = [c for c in t["colonnes"] if c.get("date_max") and c["role"] == "date"]
        if dates and t.get("entite") in ("transactions", "remboursements", "alertes", "ventes"):
            plus_recente = max(c["date_max"] for c in dates)
            try:
                age = (aujourdhui - datetime.fromisoformat(plus_recente).date()).days
                if age > 90:
                    ajouter("info", nom, None, f"Données anciennes : dernière date le {plus_recente} ({age} jours).")
            except ValueError:
                pass
    for (de, col, vers), n in orphelins.items():
        if n:
            ajouter("critique", de, col, f"{n} ligne(s) pointent vers un(e) {vers} inexistant(e).")
    score = max(0, 100 - penalite)
    ordre = {"critique": 0, "attention": 1, "info": 2}
    return sorted(diag, key=lambda d: ordre[d["gravite"]]), score


def _libelle(t: dict) -> str:
    return t.get("entite") or sem.humaniser(t["nom"])


def suggestions(tables: dict) -> list[str]:
    """Questions adaptées à la base, que le moteur local sait traiter sans IA."""
    q = []
    faits = sorted(tables.values(), key=lambda t: (-(t["entite"] in ("transactions", "crédits", "ventes", "remboursements",
                                                                     "alertes", "sinistres")), -(t["lignes"] or 0)))
    for t in faits:
        if not t["lignes"]:
            continue
        cols = t["colonnes"]
        lib = _libelle(t)
        m = next((c for c in cols if c["role"] == "montant" and not c["pii"]), None)
        d = next((c for c in cols if c["role"] == "date" and not c["pii"]), None)
        g = next((c for c in cols if c["role"] == "geographie" and c.get("valeurs")), None)
        s = next((c for c in cols if c["role"] == "statut" and c.get("valeurs")), None)
        k = next((c for c in cols if c["role"] == "categorie" and c.get("valeurs") and c["distincts"] > 1), None)
        f = next((c for c in cols if c["role"] == "drapeau_fraude"), None)
        if m and d:
            q.append(f"Montant total des {lib} par mois")
        if m and g:
            q.append(f"Montant total des {lib} par {sem.humaniser(g['nom'])}")
        if s:
            q.append(f"Répartition des {lib} par {sem.humaniser(s['nom'])}")
        if f and (k or g):
            q.append(f"Nombre de {lib} frauduleuses par {sem.humaniser((k or g)['nom'])}")
        elif k:
            q.append(f"Nombre de {lib} par {sem.humaniser(k['nom'])}")
        if m and t.get("entite") in ("clients", "comptes", "crédits", "agences", "produits"):
            q.append(f"Top 10 {lib} par {sem.humaniser(m['nom'])}")
        if len(q) >= 8:
            break
    if not q:
        q = [f"Combien de {_libelle(t)} ?" for t in list(tables.values())[:4]]
    vus, res = set(), []
    for x in q:
        if x not in vus:
            vus.add(x); res.append(x)
    return res[:8]


def analyser(eng, type_source: str, dialecte: str, schema: str | None, tables_permises: set[str] | None = None) -> dict:
    insp = inspect(eng)
    if schema is None and type_source in ("postgresql",):
        schema = "public"
    noms = sorted(set(insp.get_table_names(schema=schema)) | set(insp.get_view_names(schema=schema)))
    if tables_permises is not None:
        noms = [n for n in noms if n in tables_permises]
    tronque = len(noms) > config.CONNECTEUR_MAX_TABLES
    noms = noms[:config.CONNECTEUR_MAX_TABLES]
    tables = {}
    with connexion_lecture(eng, type_source) as conn:
        for nom in noms:
            try:
                cols_sql = insp.get_columns(nom, schema=schema)
                try:
                    pk = insp.get_pk_constraint(nom, schema=schema).get("constrained_columns") or []
                except Exception:
                    pk = []
                df = _echantillon(conn, nom, schema, dialecte, [c["name"] for c in cols_sql])
                lignes = _compter(conn, nom, schema, dialecte, type_source)
            except Exception as e:
                conn.rollback()
                log.warning("Analyse impossible de la table %s : %s", nom, e)
                tables[nom] = {"nom": nom, "erreur": "Lecture impossible (droits insuffisants ?)", "colonnes": [],
                               "cle_primaire": [], "lignes": None, "entite": sem.entite_table(nom), "doublons": 0}
                continue
            n = len(df)
            colonnes = [_profil_colonne(c["name"], str(c["type"]), df[c["name"]] if c["name"] in df else pd.Series([], dtype=object), n)
                        for c in cols_sql]
            if not pk:      # clé candidate : un identifiant unique dans l'échantillon
                cand = next((c for c in colonnes if c["role"] == "identifiant" and c["distincts"] == n and n > 0
                             and c["nulls_pct"] == 0), None)
                pk_eff = [cand["nom"]] if cand else []
            else:
                pk_eff = pk
            doublons = int(n - df[pk_eff[0]].nunique()) if pk_eff and pk_eff[0] in df and n else 0
            tables[nom] = {"nom": nom, "entite": sem.entite_table(nom), "lignes": lignes, "colonnes": colonnes,
                           "cle_primaire": pk_eff, "cle_declaree": bool(pk), "doublons": doublons}
        rels = _relations({k: v for k, v in tables.items() if not v.get("erreur")}, insp, schema)
        orphelins = {}
        for r in rels[:15]:
            orphelins[(r["de"], r["colonne"], r["vers"])] = _orphelins(conn, r, schema, dialecte)
            r["orphelins"] = orphelins[(r["de"], r["colonne"], r["vers"])]
    diag, score = _diagnostics({k: v for k, v in tables.items() if not v.get("erreur")}, rels, orphelins)
    entites = {t["entite"] for t in tables.values() if t.get("entite")}
    return {
        "dialecte": dialecte, "schema": schema, "domaine": sem.domaine(entites), "tables": list(tables.values()),
        "relations": rels, "diagnostics": diag, "score_qualite": score, "tronque": tronque,
        "suggestions": suggestions({k: v for k, v in tables.items() if not v.get("erreur")}),
        "resume": {"tables": len(tables), "lignes": sum(t["lignes"] or 0 for t in tables.values()),
                   "colonnes": sum(len(t["colonnes"]) for t in tables.values()),
                   "donnees_personnelles": sum(1 for t in tables.values() for c in t["colonnes"] if c["pii"]),
                   "relations": len(rels), "entites": sorted(entites)},
        "date_analyse": datetime.now().isoformat(timespec="seconds"),
    }
