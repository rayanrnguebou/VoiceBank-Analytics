"""Risques sur la base d'une organisation, quel que soit son schéma.

* **Opérations atypiques** (fraude) : un Isolation Forest est entraîné sur les opérations récentes de la table
  de faits (montant, heure, jour, catégories), puis chaque opération reçoit un score et des raisons lisibles
  (« 12 fois le montant habituel pour ce type », « heure rare : 0,8 % des opérations »…). Si la base contient
  un indicateur de fraude, on mesure combien de fraudes connues le modèle aurait repérées.
* **Analyse d'une opération** saisie à la main, comparée aux habitudes de la base.
* **Portefeuille de crédits** : taux de défaut observé par segment et, s'il y a assez de défauts connus,
  un modèle (régression logistique) qui classe les crédits en cours par risque, avec les facteurs.

Tout est calculé sur un échantillon (20 000 lignes au plus), en lecture seule, et gardé 10 minutes.
Les colonnes de données personnelles ne sont jamais utilisées.
"""
import logging
import threading
import time

import numpy as np
import pandas as pd
from sqlglot import exp

from . import semantique as sem
from .tableau import FAITS, _c, _col, _Executeur, _table, _titre

log = logging.getLogger("voicebank")

ECHANTILLON = 20_000
MOTS_DEFAUT = {"defaut", "default", "defaulted", "retard", "late", "overdue", "arrears", "impaye", "impayes",
               "contentieux", "douteux", "npl", "charged", "chargedoff", "writeoff", "perte", "radie", "sinistre", "1",
               "true", "oui", "yes"}
MOTS_EN_COURS = {"cours", "encours", "actif", "active", "open", "ouvert", "current", "vivant", "normal", "sain"}
MOTS_CLOS = {"clos", "closed", "rembourse", "repaid", "solde", "settled", "termine", "paid", "paye"}
_cache: dict = {}
_verrou = threading.Lock()


class RisqueIndisponible(Exception):
    """Message affichable (la base ne s'y prête pas)."""


def _memo(cle, calcul, duree=600):
    with _verrou:
        t = _cache.get(cle)
        if t and time.time() - t[0] < duree:
            return t[1]
    res = calcul()
    with _verrou:
        _cache[cle] = (time.time(), res)
    return res


def _jetons_valeur(v) -> set[str]:
    return {sem.normaliser(x) for x in str(v).replace("_", " ").replace("-", " ").split()} | {sem.normaliser(str(v)).replace(" ", "")}


TYPES_OPERATION = {"type", "categorie", "category", "nature", "produit", "product", "operation", "mode", "motif"}


def _categories(t: dict, exclure: set[str], n: int = 4) -> list[dict]:
    """Colonnes de catégories utiles, la plus « métier » d'abord (type d'opération, produit…) : c'est elle
    qui sert de référence pour le montant habituel."""
    res = []
    for role in ("categorie", "geographie", "statut"):
        for c in t["colonnes"]:
            if (c["role"] == role and not c.get("pii") and c["nom"] not in exclure and 1 < (c.get("distincts") or 0) <= 60):
                res.append(c)
    res.sort(key=lambda c: 0 if set(sem.jetons(c["nom"])) & TYPES_OPERATION else 1)
    return res[:n]


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


# ── Opérations atypiques ─────────────────────────────────────────────

def table_operations(profil: dict) -> dict | None:
    tables = [t for t in profil.get("tables", []) if not t.get("erreur") and t.get("lignes") and _col(t, "montant")]
    if not tables:
        return None
    tables.sort(key=lambda t: (FAITS.index(t["entite"]) if t.get("entite") in FAITS else len(FAITS),
                               0 if _col(t, "date") else 1, -(t["lignes"] or 0)))
    t = tables[0]
    return t if (t.get("entite") in FAITS or _col(t, "date")) else None


class ModeleOperations:
    """Isolation Forest + statistiques de référence pour expliquer les scores."""

    def __init__(self, t: dict, df: pd.DataFrame, m: str, d: str | None, cats: list[str], fraude: str | None,
                 ident: str | None, devise: str, h: str | None = None):
        from sklearn.ensemble import IsolationForest
        self.table, self.m, self.d, self.cats, self.fraude, self.ident = t, m, d, cats, fraude, ident
        self.devise = "FCFA" if devise in ("XAF", "XOF") else devise
        self.h = h or d            # colonne d'où lire l'heure (horodatage, ou colonne « heure » séparée)
        self.df = df
        df = df[pd.to_numeric(df[m], errors="coerce").notna()].copy()
        df[m] = pd.to_numeric(df[m], errors="coerce").astype(float)
        self.df = df
        if len(df) < 50:
            raise RisqueIndisponible("Pas assez d'opérations (50 au moins) pour apprendre les habitudes de cette base.")
        self.mediane = float(df[m].median()) or 1.0
        self.med_cat = {c: df.groupby(c)[m].median().to_dict() for c in cats}
        self.freq = {c: df[c].astype(str).value_counts(normalize=True).to_dict() for c in cats}
        self.heures = None
        df["_heure"] = self._heure(df)
        if df["_heure"].notna().any() and df["_heure"].nunique() > 1:
            self.heures = df["_heure"].value_counts(normalize=True).to_dict()
        self.modele = IsolationForest(n_estimators=150, contamination="auto", random_state=42)
        X = self._features(df)
        self.modele.fit(X)
        brut = -self.modele.decision_function(X)
        self.reference = np.sort(brut)            # pour convertir un score en rang (percentile)
        # Repères explicites (lisibles) : écart au montant habituel, rareté des valeurs, rareté de l'heure.
        # Le score final est le plus élevé des rangs : un montant jamais vu reste « Critique » même si l'Isolation
        # Forest extrapole mal.
        self.ref_explicites = {k: np.sort(v) for k, v in self._explicites(df).items()}
        df["_brut"] = brut
        self.ref_combine = None
        self.ref_combine = np.sort(self.scores(df, brut))     # calibration : rang du maximum parmi les opérations
        df["_score"] = self.scores(df, brut)
        self.df = df

    def _heure(self, df: pd.DataFrame) -> pd.Series:
        if not self.h or self.h not in df:
            return pd.Series([None] * len(df), index=df.index, dtype="object")
        brut = df[self.h].astype(str)
        dt = pd.to_datetime(brut, errors="coerce", format="mixed")
        h = dt.dt.hour
        if h.isna().all() or (h.fillna(0) == 0).all():          # colonne TIME seule (« 14:05:00 »)
            h = pd.to_numeric(brut.str.extract(r"^(\d{1,2}):")[0], errors="coerce")
        return h

    def _explicites(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        m = pd.to_numeric(df[self.m], errors="coerce").fillna(0).clip(lower=0).astype(float)
        if self.cats:
            med = df[self.cats[0]].map(self.med_cat[self.cats[0]]).fillna(self.mediane).astype(float)
        else:
            med = pd.Series(self.mediane, index=df.index)
        res = {"ratio": np.log1p(m.to_numpy()) - np.log1p(np.clip(med.to_numpy(), 0, None))}
        for c in self.cats:
            res["rare_" + c] = -np.log(df[c].astype(str).map(self.freq[c]).fillna(0).to_numpy() + 1e-4)
        if self.heures is not None:
            res["heure"] = -np.log(df["_heure"].map(self.heures).fillna(0).to_numpy().astype(float) + 1e-4)
        return res

    def scores(self, df: pd.DataFrame, brut: np.ndarray) -> np.ndarray:
        rangs = [np.searchsorted(self.reference, brut, side="left") / len(self.reference)]
        for k, v in self._explicites(df).items():
            ref = self.ref_explicites[k]
            r = np.searchsorted(ref, v, side="left") / len(ref)
            r[v > ref[-1] + 1e-9] = 1.0           # au-delà de tout ce qui a été observé
            rangs.append(r)
        brut_max = np.max(np.vstack(rangs), axis=0)
        if self.ref_combine is None:
            return brut_max
        # Rang du score combiné parmi les opérations de la base : 0,98 = plus atypique que 98 % d'entre elles
        r = np.searchsorted(self.ref_combine, brut_max, side="left") / len(self.ref_combine)
        r[brut_max >= 1.0] = np.maximum(r[brut_max >= 1.0], 0.999)
        return r

    def _features(self, df: pd.DataFrame) -> np.ndarray:
        cols = [np.log1p(pd.to_numeric(df[self.m], errors="coerce").fillna(0).clip(lower=0).to_numpy())]
        for c in self.cats:
            f = df[c].astype(str).map(self.freq[c]).fillna(0).to_numpy()
            cols.append(-np.log(f + 1e-4))                                          # rareté de la catégorie
            med = df[c].map(self.med_cat[c]).fillna(self.mediane).astype(float).to_numpy()
            cols.append(np.log1p(df[self.m].astype(float).clip(lower=0).to_numpy()) - np.log1p(np.clip(med, 0, None)))
        if self.heures is not None:
            cols.append(-np.log(df["_heure"].map(self.heures).fillna(0).to_numpy().astype(float) + 1e-4))
        return np.column_stack(cols)

    def rang(self, brut: float) -> float:
        return float(np.searchsorted(self.reference, brut) / max(len(self.reference), 1))

    @staticmethod
    def niveau(r: float) -> str:
        return "Critique" if r >= 0.995 else "Élevé" if r >= 0.98 else "Moyen" if r >= 0.90 else "Faible"

    def raisons(self, ligne: dict) -> list[dict]:
        """Facteurs lisibles, dans l'ordre des repères qui font monter le score."""
        df = pd.DataFrame([{self.m: ligne[self.m], **{c: ligne.get(c) for c in self.cats},
                            "_heure": ligne.get("_heure")}])
        rangs = {}
        for k, v in self._explicites(df).items():
            ref = self.ref_explicites[k]
            rangs[k] = 1.0 if v[0] > ref[-1] + 1e-9 else float(np.searchsorted(ref, v[0]) / len(ref))
            if k == "ratio":                        # montant anormalement FAIBLE : rang de l'autre côté
                rangs["ratio_bas"] = 1.0 - float(np.searchsorted(ref, v[0]) / len(ref))
        res = []
        montant = float(ligne[self.m])
        c0 = self.cats[0] if self.cats else None
        ref_m = (self.med_cat[c0].get(ligne.get(c0), self.mediane) if c0 else self.mediane) or self.mediane
        pour = f" pour « {ligne.get(c0)} »" if c0 else ""
        if rangs.get("ratio", 0) >= 0.95 and ref_m:
            res.append({"variable": "Montant", "valeur": f"{_fmt(montant)} {self.devise}", "impact": rangs["ratio"],
                        "effet": "augmente le risque", "detail": f"{montant / ref_m:.0f} fois le montant habituel{pour}"
                        if montant >= 2 * ref_m else f"montant élevé{pour}"})
        elif rangs.get("ratio_bas", 0) >= 0.97 and montant > 0:
            res.append({"variable": "Montant", "valeur": f"{_fmt(montant)} {self.devise}", "impact": rangs["ratio_bas"],
                        "effet": "augmente le risque", "detail": f"montant inhabituellement faible{pour} "
                        f"(habituel : {_fmt(ref_m)} {self.devise})"})
        for c in self.cats:
            r = rangs.get("rare_" + c, 0)
            if r >= 0.95:
                f = self.freq[c].get(str(ligne.get(c)), 0)
                res.append({"variable": libelle(c), "valeur": str(ligne.get(c)), "impact": r, "effet": "augmente le risque",
                            "detail": "valeur rare : " + (f"{f * 100:.1f} % des opérations" if f else "jamais observée")})
        if rangs.get("heure", 0) >= 0.95 and ligne.get("_heure") is not None:
            f = self.heures.get(ligne["_heure"], 0)
            res.append({"variable": "Heure", "valeur": f"{int(ligne['_heure']):02d} h", "impact": rangs["heure"],
                        "effet": "augmente le risque", "detail": f"heure rare : {f * 100:.1f} % des opérations"})
        if not res:
            res.append({"variable": "Combinaison", "valeur": None, "impact": 0.5, "effet": "augmente le risque",
                        "detail": "chaque valeur est courante, mais leur combinaison est inhabituelle"})
        for r in res:
            r["impact"] = round(float(r["impact"]), 3)
        return sorted(res, key=lambda r: -r["impact"])[:4]


def libelle(colonne: str) -> str:
    """« revenu_annuel_fcfa » → « Revenu annuel » ; « taux_interet_pct » → « Taux interet (%) »."""
    j = [x for x in sem.jetons(colonne) if x not in {"fcfa", "xaf", "xof", "eur", "usd", "num", "nb", "id"}]
    pct = "pct" in j
    j = [x for x in j if x != "pct"]
    t = sem.en_francais("_".join(j)) if j else colonne
    return t[:1].upper() + t[1:] + (" (%)" if pct else "")


def _colonne_heure(t: dict, d: str | None) -> str | None:
    """Heure dans une colonne à part (type TIME ou nom « heure / hour / time »), sinon dans l'horodatage."""
    for c in t["colonnes"]:
        typ = (c.get("type_sql") or "").upper()
        if c["nom"] == d or c.get("pii"):
            continue
        if ("TIME" in typ and "STAMP" not in typ and "DATETIME" not in typ) or \
                set(sem.jetons(c["nom"])) & {"heure", "hour", "time", "horaire"}:
            return c["nom"]
    return d


def _modele_operations(eng, type_source: str, profil: dict, devise: str, cle) -> ModeleOperations:
    def calcul():
        t = table_operations(profil)
        if t is None:
            raise RisqueIndisponible("Aucune table d'opérations (avec montants) reconnue dans cette base.")
        req = _Executeur(eng, type_source, profil)
        m, d = _col(t, "montant")["nom"], (_col(t, "date") or {}).get("nom")
        f = _col(t, "drapeau_fraude")
        h = _colonne_heure(t, d)
        cats = [c["nom"] for c in _categories(t, {m, d, h, f["nom"] if f else None})]
        ident = (t.get("cle_primaire") or [None])[0]
        cols = [x for x in dict.fromkeys([ident, m, d, h, f["nom"] if f else None, *cats]) if x]
        q = exp.select(*[_c(x) for x in cols]).from_(_table(t, req.schema)).where(_c(m).is_(exp.null()).not_())
        if d:
            q = q.order_by(exp.Ordered(this=_c(d), desc=True))
        lignes = req(q, ECHANTILLON)
        if not lignes:
            raise RisqueIndisponible("Lecture des opérations impossible.")
        return ModeleOperations(t, pd.DataFrame(lignes), m, d, cats, f["nom"] if f else None, ident, devise, h)
    return _memo(("ops",) + cle, calcul)


def _vrai(v) -> bool:
    return bool(_jetons_valeur(v) & {"1", "true", "oui", "yes", "fraude", "fraud", "suspect", "suspecte", "y", "o", "vrai"})


def _ajuster(niveau: str, raisons: list[dict]) -> str:
    """Un montant simplement plus FAIBLE que d'habitude est atypique, mais rarement une fraude grave."""
    if raisons and all("faible" in (r.get("detail") or "") for r in raisons) and niveau in ("Critique", "Élevé"):
        return "Moyen"
    return niveau


def recommandation_courte(niveau: str) -> str:
    return {"Critique": "Bloquer et vérifier auprès du client par un canal sûr.",
            "Élevé": "Mettre en attente et demander une confirmation au client.",
            "Moyen": "Surveiller les prochaines opérations du compte.",
            "Faible": "Aucune action."}[niveau]


def operations_atypiques(eng, type_source: str, profil: dict, devise: str, cle, limite: int = 50) -> dict:
    mod = _modele_operations(eng, type_source, profil, devise, cle)
    df = mod.df
    rangs = df["_score"].to_numpy()
    df = df.assign(_rang=rangs)
    top = df.sort_values(["_score", "_brut"], ascending=False).head(limite)
    resultats = []
    for _, l in top.iterrows():
        ligne = l.to_dict()
        raisons = mod.raisons(ligne)
        niv = _ajuster(mod.niveau(float(l["_rang"])), raisons)
        resultats.append({
            "id": None if mod.ident is None else str(ligne.get(mod.ident)),
            "date": str(ligne.get(mod.d))[:19] if mod.d else None, "montant": float(ligne[mod.m]),
            "categories": {c: (None if pd.isna(ligne.get(c)) else str(ligne.get(c))) for c in mod.cats},
            "score": round(float(l["_rang"]), 4), "niveau_risque": niv,
            "raisons": raisons, "recommandation": recommandation_courte(niv),
            "fraude_connue": _vrai(ligne.get(mod.fraude)) if mod.fraude else None,
        })
    resume = {"table": mod.table["nom"], "titre": _titre(mod.table), "analysees": int(len(df)),
              "colonne_montant": mod.m, "colonne_date": mod.d, "categories": mod.cats,
              "heure_prise_en_compte": mod.heures is not None,
              "periode": [str(df[mod.d].min())[:10], str(df[mod.d].max())[:10]] if mod.d else None,
              "atypiques": int((rangs >= 0.98).sum())}
    if mod.fraude:
        connues = df[mod.fraude].map(_vrai)
        n = int(connues.sum())
        if n:
            # Part des fraudes connues parmi les 5 % d'opérations les plus atypiques (un tirage au hasard : 5 %)
            vues = int((connues & (df["_rang"] >= 0.95)).sum())
            resume["fraudes_connues"] = n
            resume["fraudes_reperees_pct"] = round(100 * vues / n, 1)
            resume["fraudes_hasard_pct"] = 5.0
    return {"resume": resume, "operations": resultats, "devise": devise}


def formulaire_operation(eng, type_source: str, profil: dict, devise: str, cle) -> dict:
    mod = _modele_operations(eng, type_source, profil, devise, cle)
    return {"table": mod.table["nom"], "titre": _titre(mod.table), "montant": mod.m, "devise": devise,
            "heure": mod.heures is not None, "montant_habituel": mod.mediane,
            "categories": [{"colonne": c, "libelle": libelle(c),
                            "valeurs": [str(v) for v, _ in sorted(mod.freq[c].items(), key=lambda kv: -kv[1])[:40]]}
                           for c in mod.cats]}


def analyser_operation(eng, type_source: str, profil: dict, devise: str, cle, montant: float,
                       heure: int | None, categories: dict) -> dict:
    from .. import fraude
    mod = _modele_operations(eng, type_source, profil, devise, cle)
    ligne = {mod.m: float(montant), **{c: categories.get(c) for c in mod.cats}, "_heure": heure}
    df = pd.DataFrame([{mod.m: float(montant), **{c: categories.get(c) for c in mod.cats},
                        "_heure": heure if heure is not None else 12}])
    brut = -mod.modele.decision_function(mod._features(df))
    r = float(mod.scores(df, brut)[0])
    niv = mod.niveau(r)
    facteurs = mod.raisons(ligne) if niv != "Faible" else []
    niv = _ajuster(niv, facteurs)
    return {"score_anomalie": round(r, 4), "niveau_risque": niv, "facteurs": facteurs,
            "recommandations": fraude.recommandations(niv, [{"variable": f["variable"], "impact": f["impact"]}
                                                             for f in facteurs], {"nuit": heure is not None and (heure >= 22 or heure <= 5)}),
            "reference": {"table": mod.table["nom"], "operations": int(len(mod.df))},
            "explication": f"Comparée aux {_fmt(len(mod.df))} opérations récentes de « {_titre(mod.table)} », "
                           f"cette opération est plus inhabituelle que {f'{r * 100:.1f}'.replace('.', ',')} % d'entre elles."}


# ── Portefeuille de crédits ──────────────────────────────────────────

def table_credits(profil: dict) -> tuple[dict, dict] | None:
    """(table, colonne de statut) d'une table de crédits dont le statut distingue des défauts."""
    candidats = []
    for t in profil.get("tables", []):
        if t.get("erreur") or not t.get("lignes"):
            continue
        for c in t["colonnes"]:
            if c["role"] in ("statut", "categorie") and c.get("valeurs") and not c.get("pii"):
                valeurs = [v["valeur"] for v in c["valeurs"]]
                # « Oui / 1 / true » ne vaut défaut que si la colonne elle-même parle de défaut ou de retard
                nom_defaut = bool(set(sem.jetons(c["nom"])) & {"defaut", "default", "impaye", "retard", "late", "npl"})
                mots = MOTS_DEFAUT if nom_defaut else MOTS_DEFAUT - {"1", "true", "oui", "yes"}
                if any(_jetons_valeur(v) & mots for v in valeurs):
                    prio = 0 if t.get("entite") == "crédits" else 1 if t.get("entite") in ("remboursements", "contrats") else 2
                    candidats.append((prio, -(t["lignes"] or 0), t, c))
    if not candidats:
        return None
    candidats.sort(key=lambda x: (x[0], x[1]))
    return candidats[0][2], candidats[0][3]


def _est_defaut(v) -> bool:
    j = _jetons_valeur(v)
    return bool(j & MOTS_DEFAUT) and not (j & {"non", "no", "false", "0"})


def _est_en_cours(v) -> bool:
    return bool(_jetons_valeur(v) & MOTS_EN_COURS)


def portefeuille(eng, type_source: str, profil: dict, devise: str, cle) -> dict:
    def calcul():
        tc = table_credits(profil)
        if tc is None:
            raise RisqueIndisponible("Aucune table de crédits avec un statut de défaut ou de retard n'a été reconnue "
                                     "dans cette base (ex. colonne « statut » avec « En défaut », « En retard »).")
        t, statut = tc
        req = _Executeur(eng, type_source, profil)
        m = _col(t, "montant")
        numeriques = [c for c in t["colonnes"] if c["role"] in ("montant", "taux", "quantite", "score", "mesure")
                      and c["nature"] == "nombre" and not c.get("pii") and c["nom"] != statut["nom"]][:6]
        cats = [c["nom"] for c in _categories(t, {statut["nom"]})][:4]
        ident = (t.get("cle_primaire") or [None])[0]
        cols = [x for x in dict.fromkeys([ident, statut["nom"], *[c["nom"] for c in numeriques], *cats]) if x]
        lignes = req(exp.select(*[_c(x) for x in cols]).from_(_table(t, req.schema)), ECHANTILLON)
        if not lignes:
            raise RisqueIndisponible("Lecture des crédits impossible.")
        df = pd.DataFrame(lignes)
        df["_defaut"] = df[statut["nom"]].map(_est_defaut)
        df["_en_cours"] = df[statut["nom"]].map(_est_en_cours)
        n, nd = len(df), int(df["_defaut"].sum())
        segments = []
        for c in cats:
            g = df.groupby(df[c].astype(str)).agg(nb=("_defaut", "size"), defauts=("_defaut", "sum"))
            g = g[g["nb"] >= max(5, n // 200)].assign(taux=lambda x: x["defauts"] / x["nb"]).sort_values("taux", ascending=False)
            segments.append({"colonne": c, "libelle": libelle(c),
                             "groupes": [{"valeur": k, "credits": int(r.nb), "defauts": int(r.defauts),
                                          "taux_defaut": round(float(r.taux), 4)} for k, r in g.head(8).iterrows()]})
        if m:
            vals = pd.to_numeric(df[m["nom"]], errors="coerce")
            if vals.notna().sum() > 20:
                tranches = pd.qcut(vals, 4, duplicates="drop")
                g = df.groupby(tranches, observed=True)["_defaut"].agg(["size", "sum"])
                segments.append({"colonne": m["nom"], "libelle": "Tranche de montant", "monetaire": True, "groupes": [
                    {"valeur": f"{_fmt(iv.left)} – {_fmt(iv.right)}", "credits": int(r["size"]), "defauts": int(r["sum"]),
                     "taux_defaut": round(float(r["sum"] / r["size"]), 4)} for iv, r in g.iterrows()]})
        res = {"table": t["nom"], "titre": _titre(t), "colonne_statut": statut["nom"], "credits": n, "defauts": nd,
               "taux_defaut": round(nd / n, 4) if n else 0, "en_cours": int(df["_en_cours"].sum()),
               "segments": segments, "a_risque": [], "modele": None}
        # Modèle : assez de défauts connus et de crédits en cours à classer
        if nd >= 15 and n - nd >= 15 and (numeriques or cats):
            res.update(_classer_en_cours(df, numeriques, cats, ident, devise, m["nom"] if m else None))
        return res
    return _memo(("credits",) + cle, calcul)


def _niveau_credit(p: float, base: float) -> str:
    """Niveau relatif au portefeuille : un crédit deux fois plus risqué que la moyenne mérite l'attention."""
    r = p / max(base, 1e-6)
    return "Critique" if p >= 0.7 else "Élevé" if r >= 1.8 or p >= 0.5 else "Moyen" if r >= 1.25 else "Faible"


def _conseils_credit(niveau: str, facteurs: list[dict]) -> list[str]:
    base = {"Critique": "Contacter l'emprunteur dès maintenant et préparer une restructuration ou des garanties complémentaires.",
            "Élevé": "Contacter l'emprunteur avant la prochaine échéance pour vérifier sa capacité de remboursement.",
            "Moyen": "Suivre de près les prochaines échéances : alerte au premier retard.",
            "Faible": "Suivi normal."}[niveau]
    res = [base]
    for f in facteurs:
        if f["impact"] > 0 and len(res) < 3:
            res.append(f"Point d'attention : {f['variable'].lower()} ({f['valeur']}), "
                       f"{f['detail']}." if f.get("detail") else f"Point d'attention : {f['variable'].lower()} ({f['valeur']}).")
    return res


def _classer_en_cours(df: pd.DataFrame, numeriques: list[dict], cats: list[str], ident: str | None, devise: str,
                      col_montant: str | None = None) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import cross_val_predict
    nums = [c["nom"] for c in numeriques]
    X = pd.DataFrame(index=df.index)
    for c in nums:
        v = pd.to_numeric(df[c], errors="coerce")
        X[c] = v.fillna(v.median())
    for c in cats:
        taux = df.groupby(df[c].astype(str))["_defaut"].mean()          # encodage par taux de défaut observé
        X[c] = df[c].astype(str).map(taux).fillna(df["_defaut"].mean())
    moy, et = X.mean(), X.std().replace(0, 1)
    Z = (X - moy) / et
    y = df["_defaut"].astype(int)
    # Probabilités calibrées sur le taux réel du portefeuille (pas de rééquilibrage des classes)
    lr = LogisticRegression(C=0.5, max_iter=500).fit(Z, y)
    proba = lr.predict_proba(Z)[:, 1]
    taux_base = float(y.mean())
    try:   # fiabilité mesurée hors échantillon (validation croisée), pas sur les données d'apprentissage
        oof = cross_val_predict(LogisticRegression(C=0.5, max_iter=500), Z, y, cv=min(5, int(y.sum()), int((1 - y).sum())),
                                method="predict_proba")[:, 1]
        auc = round(float(roc_auc_score(y, oof)), 3)
    except ValueError:
        auc = None
    fiabilite = None if auc is None else "bonne" if auc >= 0.75 else "correcte" if auc >= 0.65 else "faible"
    sains = X[~df["_defaut"]].mean()
    cible = df["_en_cours"] & ~df["_defaut"]
    if not cible.any():
        cible = ~df["_defaut"]
    ordre = np.argsort(-proba * cible.to_numpy())
    a_risque = []
    for i in ordre[:15]:
        if not cible.iloc[i]:
            continue
        contrib = lr.coef_[0] * Z.iloc[i].to_numpy()
        facteurs = []
        for j in np.argsort(-np.abs(contrib))[:4]:
            col = X.columns[j]
            brut = df[col].iloc[i]
            facteurs.append({
                "variable": libelle(col),
                "valeur": (f"{_fmt(float(brut))}" if col in nums and pd.notna(brut) else str(brut)),
                "impact": round(float(contrib[j]), 3), "effet": "augmente le risque" if contrib[j] > 0 else "réduit le risque",
                "detail": (f"crédits sains : {_fmt(float(sains[col]))} en moyenne" if col in nums else
                           f"taux de défaut de ce groupe : {float(X[col].iloc[i]) * 100:.0f} %")})
        p = float(proba[i])
        niveau = _niveau_credit(p, taux_base)
        mt = pd.to_numeric(df[col_montant].iloc[i], errors="coerce") if col_montant else None
        a_risque.append({"id": None if ident is None else str(df[ident].iloc[i]), "probabilite_defaut": round(p, 4),
                         "risque_relatif": round(p / max(taux_base, 1e-6), 2), "niveau_risque": niveau,
                         "montant": None if mt is None or pd.isna(mt) else float(mt),
                         "facteurs": facteurs, "recommandations": _conseils_credit(niveau, facteurs),
                         "valeurs": {libelle(c): (None if pd.isna(df[c].iloc[i]) else str(df[c].iloc[i])) for c in cats}})
    avertissement = None
    if fiabilite == "faible":
        avertissement = ("Les colonnes de cette base prédisent mal les défauts (fiabilité faible) : ce classement est indicatif. "
                         "Appuie-toi d'abord sur les taux par segment ci-dessus.")
    return {"a_risque": a_risque, "modele": {"type": "Régression logistique", "auc": auc, "fiabilite": fiabilite,
                                             "taux_base": round(taux_base, 4), "avertissement": avertissement,
                                             "variables": [libelle(c) for c in X.columns]}}
