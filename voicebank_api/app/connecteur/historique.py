"""Test sur l'historique : ce que VoiceBank aurait repéré dans les données passées de l'organisation.

* **Crédits** : le modèle apprend sur les crédits les plus anciens (70 %) dont l'issue est connue (défaut ou
  remboursé), puis classe les plus récents (30 %) comme s'il les découvrait. On mesure la part des défauts réels
  qui se trouvaient parmi les 20 % de crédits jugés les plus risqués (un tirage au hasard en trouverait 20 %),
  et les montants correspondants. Encodages appris sur la partie ancienne seulement : aucune fuite d'information.
* **Fraude** : le détecteur d'opérations atypiques n'utilise jamais les étiquettes de fraude ; on regarde combien
  des fraudes connues de la base il place parmi les 5 % d'opérations les plus atypiques, et pour quel montant.
"""
import numpy as np
import pandas as pd
from sqlglot import exp

from . import semantique as sem
from .risques import (ECHANTILLON, MOTS_CLOS, RisqueIndisponible, _categories, _est_defaut, _jetons_valeur, _memo,
                      _modele_operations, _vrai, libelle, table_credits)
from .tableau import _c, _col, _Executeur, _table

PART_APPRENTISSAGE = 0.7
PART_CIBLEE = 0.2


def _colonne_date_octroi(t: dict):
    dates = [c for c in t["colonnes"] if c["role"] == "date" and not c.get("pii")
             and not set(sem.jetons(c["nom"])) & {"naissance", "birth", "dob"}]
    for mots in ({"debut", "start", "octroi", "decaissement", "disbursed", "ouverture", "opened"}, {"created", "creation"}):
        c = next((c for c in dates if set(sem.jetons(c["nom"])) & mots), None)
        if c:
            return c
    return dates[0] if dates else None


def credits(eng, type_source: str, profil: dict, cle) -> dict:
    def calcul():
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
        tc = table_credits(profil)
        if tc is None:
            raise RisqueIndisponible("Aucune table de crédits avec un statut de défaut reconnue.")
        t, statut = tc
        m = _col(t, "montant")
        numeriques = [c["nom"] for c in t["colonnes"] if c["role"] in ("montant", "taux", "quantite", "score", "mesure")
                      and c["nature"] == "nombre" and not c.get("pii") and c["nom"] != statut["nom"]][:6]
        cats = [c["nom"] for c in _categories(t, {statut["nom"]})][:4]
        d = _colonne_date_octroi(t)
        req = _Executeur(eng, type_source, profil)
        cols = [x for x in dict.fromkeys([statut["nom"], *numeriques, *cats, d["nom"] if d else None]) if x]
        lignes = req(exp.select(*[_c(x) for x in cols]).from_(_table(t, req.schema)), ECHANTILLON)
        if not lignes:
            raise RisqueIndisponible("Lecture des crédits impossible.")
        df = pd.DataFrame(lignes)
        df["_defaut"] = df[statut["nom"]].map(_est_defaut)
        df["_clos"] = df[statut["nom"]].map(lambda v: bool(_jetons_valeur(v) & MOTS_CLOS))
        connus = df[df["_defaut"] | df["_clos"]].copy()          # issue connue : défaut ou remboursé
        if len(connus) < 60 or connus["_defaut"].sum() < 15 or (~connus["_defaut"]).sum() < 15:
            raise RisqueIndisponible("Pas assez de crédits à l'issue connue (au moins 60, dont 15 défauts et 15 remboursés) "
                                     "pour un test sur l'historique.")
        if d:
            connus["_date"] = pd.to_datetime(connus[d["nom"]], errors="coerce")
            connus = connus.sort_values("_date", kind="stable")
        coupe = int(len(connus) * PART_APPRENTISSAGE)
        ancien, recent = connus.iloc[:coupe], connus.iloc[coupe:]
        if recent["_defaut"].sum() < 5 or ancien["_defaut"].sum() < 10:
            raise RisqueIndisponible("Trop peu de défauts dans la période récente pour un test fiable.")

        def matrice(part):
            X = pd.DataFrame(index=part.index)
            for c in numeriques:
                X[c] = pd.to_numeric(part[c], errors="coerce")
            for c in cats:
                X[c] = part[c].astype(str).map(taux[c]).fillna(base)
            return X
        base = float(ancien["_defaut"].mean())
        taux = {c: ancien.groupby(ancien[c].astype(str))["_defaut"].mean() for c in cats}
        Xa, Xr = matrice(ancien), matrice(recent)
        med = Xa.median()
        Xa, Xr = Xa.fillna(med), Xr.fillna(med)
        moy, et = Xa.mean(), Xa.std().replace(0, 1)
        lr = LogisticRegression(C=0.5, max_iter=500).fit((Xa - moy) / et, ancien["_defaut"].astype(int))
        p = lr.predict_proba((Xr - moy) / et)[:, 1]
        y = recent["_defaut"].to_numpy()
        n_cible = max(1, int(round(len(recent) * PART_CIBLEE)))
        cibles = np.argsort(-p)[:n_cible]
        captures = int(y[cibles].sum())
        res = {"table": t["nom"], "colonne_date": d["nom"] if d else None,
               "apprentissage": int(len(ancien)), "test": int(len(recent)), "defauts_test": int(y.sum()),
               "auc": round(float(roc_auc_score(y, p)), 3), "part_ciblee": PART_CIBLEE,
               "defauts_reperes": captures, "defauts_reperes_pct": round(100 * captures / int(y.sum()), 1),
               "hasard_pct": round(100 * PART_CIBLEE, 1), "variables": [libelle(c) for c in Xa.columns],
               # Parmi les crédits ciblés, part réellement en défaut, contre la moyenne de la période
               "taux_defaut_cible_pct": round(100 * captures / n_cible, 1), "taux_defaut_moyen_pct": round(100 * float(y.mean()), 1)}
        auc = res["auc"]
        res["verdict"] = "bon" if auc >= 0.75 else "moyen" if auc >= 0.62 else "faible"
        if d:
            dates = connus["_date"].dropna()
            if len(dates):
                res["periode_apprentissage"] = [str(ancien["_date"].min())[:10], str(ancien["_date"].max())[:10]]
                res["periode_test"] = [str(recent["_date"].min())[:10], str(recent["_date"].max())[:10]]
        if m:
            mt = pd.to_numeric(recent[m["nom"]], errors="coerce").fillna(0).to_numpy()
            total = float(mt[y.astype(bool)].sum())
            if total > 0:
                res["montant_defauts_test"] = total
                res["montant_repere"] = float(mt[cibles][y[cibles].astype(bool)].sum())
        return res
    return _memo(("historique_credits",) + tuple(cle), calcul)


def fraude(eng, type_source: str, profil: dict, devise: str, cle) -> dict:
    mod = _modele_operations(eng, type_source, profil, devise, cle)
    if not mod.fraude:
        raise RisqueIndisponible("La base n'indique pas quelles opérations étaient des fraudes : impossible de mesurer "
                                 "ce qu'aurait repéré le détecteur.")
    df = mod.df
    connues = df[mod.fraude].map(_vrai)
    n = int(connues.sum())
    if n < 5:
        raise RisqueIndisponible("Moins de 5 fraudes connues dans la base : mesure impossible.")
    haut = df["_score"] >= 0.95
    vues = connues & haut
    mt = pd.to_numeric(df[mod.m], errors="coerce").fillna(0)
    res = {"table": mod.table["nom"], "operations": int(len(df)), "fraudes_connues": n, "fraudes_reperees": int(vues.sum()),
            "fraudes_reperees_pct": round(100 * int(vues.sum()) / n, 1), "part_ciblee": 0.05, "hasard_pct": 5.0,
            "montant_fraudes": float(mt[connues].sum()), "montant_repere": float(mt[vues].sum()),
            "periode": [str(df[mod.d].min())[:10], str(df[mod.d].max())[:10]] if mod.d else None}
    total = float(mt[connues].sum())
    res["montant_repere_pct"] = round(100 * res["montant_repere"] / total, 1) if total else None
    meilleur = max(res["fraudes_reperees_pct"], res["montant_repere_pct"] or 0)
    res["verdict"] = "bon" if meilleur >= 25 else "moyen" if meilleur >= 10 else "faible"
    return res
