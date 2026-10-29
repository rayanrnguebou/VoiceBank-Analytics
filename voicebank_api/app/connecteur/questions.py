"""Questions en français sur une base d'organisation, quel que soit son schéma et son moteur.

1. Gemini (s'il est configuré) reçoit la CARTE de la base (tables, colonnes, rôles métier, valeurs
   fréquentes non personnelles, relations) et écrit la requête dans le dialecte du moteur.
2. Sinon, ou si Gemini échoue, un moteur local comprend les formulations courantes
   (« montant total des crédits par mois », « top 10 clients par solde », « nombre de paiements
   frauduleux par canal à Douala en 2025 »…) en s'appuyant sur cette même carte.
Dans les deux cas, la requête passe par la garde SQL avant d'être exécutée en lecture seule.
"""
import logging
import re

from sqlglot import exp

from .. import config, i18n
from . import semantique as sem

log = logging.getLogger("voicebank")

NOMS_DIALECTES = {"postgres": "PostgreSQL", "mysql": "MySQL / MariaDB", "tsql": "SQL Server (T-SQL)", "oraclevb": "Oracle",
                  "sqlite": "SQLite"}
VRAI = {"1", "true", "t", "oui", "yes", "y", "vrai", "o"}
MOTS_TEMPS = {"mois": "mois", "month": "mois", "mensuel": "mois", "annee": "annee", "an": "annee", "year": "annee",
              "annuel": "annee"}
MOTS_FRAUDE = {"fraude", "frauduleux", "frauduleuse", "frauduleuses", "frauduleuses", "fraud", "fraudulent",
               "suspect", "suspects", "suspecte", "suspectes"}
VIDES = {"le", "la", "les", "des", "de", "du", "d", "un", "une", "et", "a", "au", "aux", "en", "par", "pour",
         "sur", "dans", "avec", "quel", "quels", "quelle", "quelles", "est", "sont", "the", "of", "by", "in", "per",
         "me", "moi", "donne", "affiche", "montre", "liste", "voir", "combien", "nombre", "total", "top", "plus",
         "chaque", "selon", "y", "il", "ya", "qui", "que", "ont", "a"}


def _formes(mots) -> set[str]:
    return set().union(*(sem.formes(m) for m in mots)) if mots else set()


def _cols(t, *roles):
    return [c for c in t["colonnes"] if c["role"] in roles and c["role"] != "secret"]


def _vocabulaire_table(t) -> set[str]:
    v = _formes(sem.jetons(t["nom"]))
    if t.get("entite"):
        v |= sem.ENTITES.get(t["entite"], set()) | _formes(sem.jetons(t["entite"]))
    return v - {"id"}


def choisir_table(question: str, profil: dict):
    q = sem.normaliser(question)
    mots = sem.mots_etendus(q.split())
    meilleur, score_max = None, 0
    for t in profil["tables"]:
        if t.get("erreur") or not t["colonnes"]:
            continue
        score = 3 * len(_vocabulaire_table(t) & mots)
        for c in t["colonnes"]:
            if c["role"] == "secret":
                continue
            jc = _formes(sem.jetons(c["nom"])) - {"id", "date", "code", "type", "name", "nom"}
            if jc & mots:
                score += 1
            for v in c.get("valeurs") or []:
                if len(sem.normaliser(v["valeur"])) >= 3 and re.search(rf"\b{re.escape(sem.normaliser(v['valeur']))}\b", q):
                    score += 1
                    break
        if MOTS_FRAUDE & mots and _cols(t, "drapeau_fraude"):
            score += 2
        if score and _cols(t, "montant") and _cols(t, "date"):
            score += 0.5                                   # à égalité, la table de faits
        if score > score_max or (score == score_max and meilleur and score and (t["lignes"] or 0) > (meilleur["lignes"] or 0)):
            meilleur, score_max = t, score
    return meilleur if score_max > 0 else None


def _ident(nom):
    return exp.to_identifier(nom, quoted=True)


def _col(nom):
    return exp.column(_ident(nom))


def _litteral(c, valeur: str):
    if c["nature"] in ("nombre", "booleen"):
        try:
            return exp.Literal.number(int(float(valeur)))
        except ValueError:
            pass
    return exp.Literal.string(valeur)


def _colonne_citee(q: str, candidates: list[dict]) -> dict | None:
    mots = sem.mots_etendus(q.split())
    meilleure, score = None, 0
    for c in candidates:
        j = _formes(sem.jetons(c["nom"])) - {"id"}
        s = len(j & mots)
        if s > score:
            meilleure, score = c, s
    return meilleure


def sql_local(question: str, profil: dict, dialecte: str) -> tuple[str, dict] | None:
    """Retourne (SQL, explication) ou None si la question n'est pas comprise."""
    t = choisir_table(question, profil)
    if t is None:
        return None
    q = sem.normaliser(question)
    mots = q.split()
    par_entite = None       # « top 10 clients par solde » : regrouper la table de faits par client
    m_top0 = re.search(r"\btop\s*\d{1,3}\b|\b\d{1,3}\s+(?:plus|premiers|meilleurs)\b", q)
    if m_top0:
        avant = sem.mots_etendus(q.split(" par ")[0].split())
        tables = {x["nom"]: x for x in profil["tables"] if not x.get("erreur")}
        entite = next((x for x in tables.values() if _vocabulaire_table(x) & avant), None)
        if entite is not None:
            mesure_citee = lambda x: _colonne_citee(q, _cols(x, "montant", "quantite", "taux", "score", "mesure"))
            for r in profil.get("relations", []):
                if r["vers"] != entite["nom"] or r["de"] not in tables:
                    continue
                enfant = tables[r["de"]]
                if enfant["nom"] == t["nom"] or (entite["nom"] == t["nom"] and (mesure_citee(enfant) or "nombre" in mots)):
                    if "nombre" in mots and enfant["nom"] != t["nom"] and _vocabulaire_table(enfant) & sem.mots_etendus(mots) \
                            or enfant["nom"] == t["nom"] or mesure_citee(enfant):
                        t, par_entite = enfant, r["colonne"]
                        break
    table = exp.table_(_ident(t["nom"]), db=_ident(profil["schema"]) if profil.get("schema") and dialecte != "mysql" else None)
    mesures = _cols(t, "montant", "quantite", "taux", "score", "mesure")
    dates = _cols(t, "date")
    groupables = _cols(t, "categorie", "statut", "geographie", "drapeau_fraude", "identifiant")
    expl = {"table": t["nom"], "filtres": []}

    # Agrégat demandé
    if re.search(r"\b(moyen|moyenne|moyens|average|avg)\b", q):
        agg = "moyenne"
    elif re.search(r"\b(maximum|max|plus grand|plus eleve|plus elevee|plus gros)\b", q):
        agg = "max"
    elif re.search(r"\b(minimum|min|plus petit|plus faible|plus bas)\b", q):
        agg = "min"
    elif re.search(r"\b(total|somme|cumul|volume|montant total|montants)\b", q):
        agg = "somme"
    elif re.search(r"\b(nombre|combien|count|compte|repartition|distribution|nb)\b", q):
        agg = "nombre"
    else:
        agg = None
    m_top = re.search(r"\btop\s*(\d{1,3})\b", q) or re.search(r"\b(\d{1,3})\s+(?:plus|premiers|premieres|meilleurs|meilleures|principaux)\b", q)
    top = int(m_top.group(1)) if m_top else None

    # Mesure : celle qui est citée, sinon le premier montant
    mesure = _colonne_citee(q, mesures) or (mesures[0] if mesures and (agg in ("somme", "moyenne", "max", "min") or top) else None)
    if agg in ("somme", "moyenne", "max", "min") and mesure is None:
        agg = "nombre"

    # Regroupement : « par mois », « par ville », « par statut »…
    groupe, temps = None, None
    m_par = re.search(r"\b(?:par|by|selon|per|pour chaque)\s+(\w+(?:\s+\w+)?)", q)
    if m_par:
        cible = m_par.group(1).split()
        if cible[0] in MOTS_TEMPS and dates:
            temps = MOTS_TEMPS[cible[0]]
        else:
            groupe = _colonne_citee(" ".join(cible), groupables)
            if groupe is None:   # « par client » : la colonne qui pointe vers la table des clients
                for r in profil.get("relations", []):
                    if r["de"] == t["nom"]:
                        cible_t = next((x for x in profil["tables"] if x["nom"] == r["vers"]), None)
                        if cible_t and _vocabulaire_table(cible_t) & _formes(cible):
                            groupe = next((c for c in t["colonnes"] if c["nom"] == r["colonne"]), None)
                            break
    if par_entite and not temps:
        groupe = next((c for c in t["colonnes"] if c["nom"] == par_entite), groupe)
        if "nombre" in mots:
            agg = "nombre"
        elif mesure is not None:
            agg = agg if agg in ("moyenne", "max", "min") else "somme"
    date_col = _colonne_citee(q, dates) or (dates[0] if dates else None)

    # Filtres : fraude, valeurs citées (« à Douala », « en retard »), année
    conditions = []
    if set(mots) & MOTS_FRAUDE:
        f = next(iter(_cols(t, "drapeau_fraude")), None)
        if f:
            vrai = next((v["valeur"] for v in f.get("valeurs") or [] if sem.normaliser(v["valeur"]) in VRAI), "1")
            conditions.append(exp.EQ(this=_col(f["nom"]), expression=_litteral(f, vrai)))
            expl["filtres"].append(f"{f['nom']} = {vrai}")
    for c in _cols(t, "categorie", "statut", "geographie"):
        if groupe is not None and c["nom"] == groupe["nom"]:
            continue
        for v in c.get("valeurs") or []:
            nv = sem.normaliser(v["valeur"])
            synonyme = any(nv in syn for mot, syn in sem.VALEURS_SYNONYMES.items() if re.search(rf"\b{mot}", q))
            if (len(nv) >= 3 and nv not in VIDES and re.search(rf"\b{re.escape(nv)}\b", q)) or (nv and synonyme):
                conditions.append(exp.EQ(this=_col(c["nom"]), expression=_litteral(c, v["valeur"])))
                expl["filtres"].append(f"{c['nom']} = {v['valeur']}")
                break
    m_an = re.search(r"\b(19\d{2}|20\d{2})\b", q)
    if m_an and date_col and not top:
        conditions.append(exp.EQ(this=exp.Year(this=_col(date_col["nom"])), expression=exp.Literal.number(int(m_an.group(1)))))
        expl["filtres"].append(f"année {m_an.group(1)}")

    def valeur_agg(a):
        if a == "nombre" or mesure is None:
            return exp.Count(this=exp.Star()).as_("nombre")
        fonction = {"somme": exp.Sum, "moyenne": exp.Avg, "max": exp.Max, "min": exp.Min}[a]
        alias = {"somme": "total", "moyenne": "moyenne", "max": "maximum", "min": "minimum"}[a]
        return fonction(this=_col(mesure["nom"])).as_(f"{alias}_{mesure['nom']}")

    if temps:
        a = agg or ("somme" if mesure else "nombre")
        selection = [exp.Year(this=_col(date_col["nom"])).as_("annee")]
        if temps == "mois":
            selection.append(exp.Month(this=_col(date_col["nom"])).as_("mois"))
        requete = exp.select(*selection, valeur_agg(a)).from_(table)
        groupes = [exp.Year(this=_col(date_col["nom"]))] + ([exp.Month(this=_col(date_col["nom"]))] if temps == "mois" else [])
        requete = requete.group_by(*groupes).order_by(*[g.copy() for g in groupes])
        expl.update(type="evolution", periode=temps, date=date_col["nom"])
    elif groupe:
        a = agg or ("somme" if mesure and re.search(r"\b(montant|montants|amount|volume)\b", q) else "nombre")
        val = valeur_agg(a)
        requete = (exp.select(_col(groupe["nom"]), val).from_(table).group_by(_col(groupe["nom"]))
                   .order_by(exp.Ordered(this=exp.column(val.alias), desc=True)))
        if top:
            requete = requete.limit(top)
        expl.update(type="regroupement", par=groupe["nom"])
    elif top and mesure:
        visibles = [c["nom"] for c in t["colonnes"] if c["role"] not in ("secret",) and not c["pii"]][:6]
        if mesure["nom"] not in visibles:
            visibles.append(mesure["nom"])
        requete = (exp.select(*[_col(n) for n in visibles]).from_(table)
                   .order_by(exp.Ordered(this=_col(mesure["nom"]), desc=True)).limit(top))
        expl.update(type="classement", par=mesure["nom"])
    elif agg:
        requete = exp.select(valeur_agg(agg)).from_(table)
        expl.update(type="indicateur")
    else:
        visibles = [c["nom"] for c in t["colonnes"] if c["role"] != "secret"]
        requete = exp.select(*[_col(n) for n in visibles]).from_(table).limit(100)
        expl.update(type="liste")
    if conditions:
        cond = conditions[0]
        for c in conditions[1:]:
            cond = exp.And(this=cond, expression=c)
        requete = requete.where(cond)
    return requete.sql(dialect=dialecte), expl


# ── Gemini ────────────────────────────────────────────────────────────

def carte_pour_ia(profil: dict, question: str, max_tables: int = 25) -> str:
    """Description compacte de la base, SANS aucune valeur personnelle."""
    q = _formes(sem.normaliser(question).split())
    tables = [t for t in profil["tables"] if not t.get("erreur")]
    if len(tables) > max_tables:
        tables.sort(key=lambda t: -(3 * len(_vocabulaire_table(t) & q)
                                    + sum(1 for c in t["colonnes"] if _formes(sem.jetons(c["nom"])) & q)))
        tables = tables[:max_tables]
    lignes = []
    for t in tables:
        cols = []
        for c in t["colonnes"]:
            if c["role"] == "secret":
                continue
            d = f"{c['nom']} {c['type_sql'].split('(')[0].lower()} [{c['role']}"
            if c["pii"]:
                d += ", personnel"
            elif c.get("valeurs"):
                d += ": " + ", ".join(repr(v["valeur"]) for v in c["valeurs"][:6])
            cols.append(d + "]")
        pk = f", clé {t['cle_primaire'][0]}" if t["cle_primaire"] else ""
        lignes.append(f"- {t['nom']} ({t.get('entite') or 'table'}, ~{t['lignes']} lignes{pk}) : " + "; ".join(cols))
    rel = [f"- {r['de']}.{r['colonne']} → {r['vers']}.{r['colonne_cible']}" for r in profil.get("relations", [])]
    return "Tables :\n" + "\n".join(lignes) + ("\nRelations :\n" + "\n".join(rel) if rel else "")


def sql_gemini(question: str, profil: dict, dialecte: str) -> str | None:
    from ..nl2sql import client_gemini
    client = client_gemini()
    if client is None:
        return None
    schema = profil.get("schema")
    prefixe = f"Les tables sont dans le schéma « {schema} » : préfixe-les ({schema}.table).\n" if schema and dialecte in ("postgres", "tsql", "oraclevb") else ""
    prompt = (
        f"Tu traduis des questions (en français ou en anglais) en UNE requête SQL {NOMS_DIALECTES.get(dialecte, dialecte)}.\n"
        "Règles : une seule requête SELECT, uniquement les tables et colonnes listées, alias de colonnes "
        f"lisibles en {'anglais' if i18n.langue() == 'en' else 'français'}, pas de commentaire, pas de point-virgule, au plus 1000 lignes. Pour les "
        "évolutions dans le temps, regroupe par année et mois. N'utilise jamais une colonne marquée "
        "« personnel » dans un filtre ou un regroupement sauf si la question le demande explicitement.\n"
        + prefixe + carte_pour_ia(profil, question) +
        f"\n\nQuestion : <<<{question}>>>\nRéponds uniquement avec le SQL.")
    try:
        rep = client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
        texte = (rep.text or "").strip()
    except Exception as e:
        log.warning("Gemini indisponible pour une source : %s", e)
        return None
    texte = re.sub(r"^```(?:sql)?\s*|\s*```$", "", texte, flags=re.I).strip()
    return texte or None
