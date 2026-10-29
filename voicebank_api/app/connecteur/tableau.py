"""Tableau de bord d'une base connectée : indicateurs et graphiques choisis d'après l'analyse de la base.

Rien n'est codé en dur : on part des entités reconnues (clients, transactions, crédits, ventes…), des rôles
des colonnes (montant, date, statut, lieu, drapeau de fraude) et on construit quelques requêtes d'agrégation
simples (COUNT, SUM, regroupement par mois ou par catégorie), traduites dans le dialecte de la base.
Aucune donnée personnelle n'est regroupée ni affichée. Les résultats sont gardés 10 minutes en mémoire.
"""
import logging

from sqlglot import exp

from ..memoire import Memoire
from . import garde
from . import semantique as sem
from .connexion import executer

log = logging.getLogger("voicebank")

# Ordre d'importance des entités pour les indicateurs
ORDRE = ["clients", "comptes", "transactions", "ventes", "crédits", "contrats", "sinistres", "remboursements",
         "alertes", "épargne", "groupes", "produits", "agences", "employés"]
# Tables « de faits » : leur évolution dans le temps a du sens
FAITS = ["transactions", "ventes", "remboursements", "crédits", "sinistres", "alertes", "contrats", "épargne"]
VRAI = {"1", "true", "t", "oui", "yes", "y", "o", "vrai", "fraude", "fraud", "suspect", "suspecte"}
_memoire = Memoire(frais=600, garde=24 * 3600)


def _titre(t: dict) -> str:
    nom = t.get("entite") or sem.en_francais(t["nom"])
    return nom[:1].upper() + nom[1:]


def _rang(t: dict) -> tuple:
    e = t.get("entite")
    return (ORDRE.index(e) if e in ORDRE else len(ORDRE), -(t.get("lignes") or 0))


def _col(t: dict, *roles, valeurs: bool = False):
    for role in roles:
        for c in t["colonnes"]:
            if c["role"] == role and not c.get("pii") and (not valeurs or c.get("valeurs")):
                if role in ("categorie", "statut", "geographie") and not (1 < (c.get("distincts") or 0) <= 50):
                    continue
                if role == "date" and set(sem.jetons(c["nom"])) & {"naissance", "birth", "dob", "nee", "ne"}:
                    continue
                return c
    return None


def _table(t: dict, schema: str | None) -> exp.Table:
    return exp.table_(exp.to_identifier(t["nom"], quoted=True),
                      db=exp.to_identifier(schema, quoted=True) if schema else None)


def _c(nom: str) -> exp.Column:
    return exp.column(exp.to_identifier(nom, quoted=True))


class _Executeur:
    def __init__(self, eng, type_source, profil):
        self.eng, self.type_source, self.profil = eng, type_source, profil
        self.dialecte = profil["dialecte"]
        self.schema = profil.get("schema") if type_source not in ("mysql", "fichier") else None
        self.autorisees = {t["nom"].lower() for t in profil["tables"] if not t.get("erreur")}
        self.schemas = {(profil.get("schema") or "").lower()} - {""}

    def __call__(self, requete: exp.Expression, max_lignes: int = 50) -> list[dict] | None:
        try:
            sql = garde.valider(requete.sql(dialect=self.dialecte), self.dialecte, self.autorisees, max_lignes, self.schemas)
            return executer(self.eng, self.type_source, sql, max_lignes)[1]
        except Exception as e:
            log.info("Tableau de bord : requête ignorée (%s)", e)
            return None


def _nombre(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def calculer(eng, type_source: str, profil: dict) -> dict:
    """Indicateurs et graphiques, montants dans la monnaie de la base."""
    req = _Executeur(eng, type_source, profil)
    tables = sorted([t for t in profil.get("tables", []) if not t.get("erreur") and t.get("lignes")], key=_rang)
    indicateurs, graphiques, entites_vues = [], [], set()

    def compter(t):
        cle = t.get("entite") or t["nom"]
        if cle in entites_vues:
            return
        entites_vues.add(cle)
        indicateurs.append({"titre": _titre(t), "valeur": t["lignes"], "type": "nombre", "entite": t.get("entite"),
                            "table": t["nom"]})

    # 1. Les deux entités principales (ex. clients, transactions)
    for t in tables:
        if len(indicateurs) >= 2:
            break
        compter(t)

    # 2. Fraudes, s'il existe un drapeau de fraude
    for t in tables:
        f = _col(t, "drapeau_fraude")
        if not f:
            continue
        lignes = req(exp.select(_c(f["nom"]).as_("v"), exp.Count(this=exp.Star()).as_("nb"))
                     .from_(_table(t, req.schema)).group_by(_c(f["nom"])))
        if lignes is not None:
            nb = sum(int(_nombre(l["nb"]) or 0) for l in lignes if str(l["v"]).strip().lower() in VRAI)
            indicateurs.append({"titre": "Fraudes", "valeur": nb, "type": "nombre", "entite": "alertes", "table": t["nom"]})
            break

    # 3. Montant total de la table la plus parlante (crédits d'abord : l'encours)
    candidats = sorted([t for t in tables if _col(t, "montant")],
                       key=lambda t: (0 if t.get("entite") == "crédits" else 1 if t.get("entite") in FAITS else 2, _rang(t)))
    for t in candidats[:2]:
        m = _col(t, "montant")
        lignes = req(exp.select(exp.Sum(this=_c(m["nom"])).as_("total")).from_(_table(t, req.schema)), 1)
        total = _nombre(lignes[0]["total"]) if lignes else None
        if total is not None:
            indicateurs.append({"titre": f"Montant des {(t.get('entite') or sem.en_francais(t['nom']))}", "valeur": total, "type": "montant",
                                "entite": t.get("entite"), "table": t["nom"], "colonne": m["nom"]})
            break

    # 4. Compléter jusqu'à 4 avec d'autres entités
    for t in tables:
        if len(indicateurs) >= 4:
            break
        compter(t)
    indicateurs = indicateurs[:4]

    # Graphique : évolution mensuelle d'une table de faits datée
    datees = sorted([t for t in tables if _col(t, "date")],
                    key=lambda t: (FAITS.index(t["entite"]) if t.get("entite") in FAITS else len(FAITS), -(t["lignes"] or 0)))
    for t in datees[:2]:
        d, m = _col(t, "date"), _col(t, "montant")
        annee, mois = exp.Year(this=_c(d["nom"])), exp.Month(this=_c(d["nom"]))
        selection = [annee.copy().as_("annee"), mois.copy().as_("mois"), exp.Count(this=exp.Star()).as_("nb")]
        if m:
            selection.append(exp.Sum(this=_c(m["nom"])).as_("total"))
        lignes = req(exp.select(*selection).from_(_table(t, req.schema))
                     .where(exp.and_(_c(d["nom"]).is_(exp.null()).not_(),
                                     exp.LTE(this=_c(d["nom"]), expression=exp.CurrentDate())))  # pas de dates futures
                     .group_by(annee.copy(), mois.copy())
                     .order_by(exp.Ordered(this=annee.copy(), desc=True), exp.Ordered(this=mois.copy(), desc=True)), 12)
        points = []
        for l in reversed(lignes or []):
            a, mo = _nombre(l.get("annee")), _nombre(l.get("mois"))
            if a and mo:
                points.append({"label": f"{int(a):04d}-{int(mo):02d}", "nb": int(_nombre(l["nb"]) or 0),
                               "total": _nombre(l.get("total"))})
        if len(points) >= 2:
            graphiques.append({"id": "evolution", "titre": f"{_titre(t)} par mois", "type": "line", "donnees": points,
                               "series": [{"cle": "nb", "nom": "Nombre"}], "temps": True})
            if m and any(p["total"] for p in points):
                graphiques.append({"id": "montant_mois", "titre": f"Montant des {(t.get('entite') or sem.en_francais(t['nom']))} par mois",
                                   "type": "bar", "donnees": points, "series": [{"cle": "total", "nom": "Montant", "montant": True}],
                                   "temps": True})
            break

    # Graphiques : répartition par lieu, statut ou catégorie (2 au plus, tables différentes si possible)
    deja = set()
    for t in tables:
        if len([g for g in graphiques if g["id"].startswith("repartition")]) >= 2:
            break
        c = _col(t, "geographie", "statut", "categorie", "drapeau_fraude", valeurs=True)
        if not c or c["role"] == "drapeau_fraude" or (t["nom"], c["nom"]) in deja:
            continue
        nb = exp.Count(this=exp.Star())
        lignes = req(exp.select(_c(c["nom"]).as_("label"), nb.copy().as_("nb")).from_(_table(t, req.schema))
                     .where(_c(c["nom"]).is_(exp.null()).not_()).group_by(_c(c["nom"]))
                     .order_by(exp.Ordered(this=nb.copy(), desc=True)), 8)
        if lignes and len(lignes) >= 2:
            deja.add((t["nom"], c["nom"]))
            graphiques.append({"id": f"repartition_{len(deja)}",
                               "titre": f"{_titre(t)} par {sem.en_francais(c['nom'])}", "type": "bar",
                               "donnees": [{"label": str(l["label"])[:30], "nb": int(_nombre(l["nb"]) or 0)} for l in lignes],
                               "series": [{"cle": "nb", "nom": "Nombre"}], "temps": False})

    return {"indicateurs": indicateurs, "graphiques": graphiques[:4]}


def tableau(cle: tuple, calcul) -> dict:
    """Résultat gardé par (source, date d'analyse…) : frais 10 minutes, puis rendu tout de suite et recalculé en
    arrière-plan. Une nouvelle analyse de la source remplace les anciens résultats."""
    return _memoire.obtenir(cle, calcul, remplace=lambda k: k[0] == cle[0] and k[2:3] != cle[2:3])
