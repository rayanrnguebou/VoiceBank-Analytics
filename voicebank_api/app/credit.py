"""Score de crédit expliqué (modèle XGBoost entraîné dans voicebank_ia/modeles_ia.py).

Le modèle estime la probabilité qu'un crédit tombe en défaut ou en retard. L'explication
vient des contributions SHAP calculées nativement par XGBoost (pred_contribs), sans
dépendre de la bibliothèque shap.
"""
import logging

import numpy as np
import pandas as pd

from . import config

log = logging.getLogger("voicebank")

FEATURES = ["montant_log", "mensualite_log", "revenu_log", "ratio_mensualite", "score_credit",
            "taux_interet_pct", "duree_mois", "est_diaspora_num", "type_credit_enc", "garantie_enc",
            "banque_enc"]
CATEGORIELLES = ["type_credit", "garantie", "banque"]

LIBELLES = {
    "montant_log": "Montant du crédit", "mensualite_log": "Mensualité", "revenu_log": "Revenu annuel",
    "ratio_mensualite": "Poids de la mensualité dans le revenu", "score_credit": "Score de crédit historique",
    "taux_interet_pct": "Taux d'intérêt", "duree_mois": "Durée", "est_diaspora_num": "Client de la diaspora",
    "type_credit_enc": "Type de crédit", "garantie_enc": "Garantie", "banque_enc": "Banque",
}

modele: dict = {}


def charger():
    try:
        import joblib
        from xgboost import XGBClassifier
        m = XGBClassifier()
        m.load_model(str(config.MODELS_DIR / "xgb_credit.json"))
        modele["xgb"] = m
        modele["encoders"] = joblib.load(config.MODELS_DIR / "encoders_credit.pkl")
        log.info("Modèle de score de crédit chargé")
    except Exception:
        log.exception("Modèle de crédit non chargé")


def disponible() -> bool:
    return "xgb" in modele


def referentiel() -> dict:
    enc = modele.get("encoders", {})
    return {c: [str(v) for v in enc[c].classes_] for c in CATEGORIELLES if c in enc}


def niveau(proba: float) -> str:
    return ("Critique" if proba > 0.7 else "Élevé" if proba > 0.5 else "Moyen" if proba > 0.3 else "Faible")


def _encoder(col: str, valeur, strict: bool) -> tuple[int, bool]:
    enc = modele["encoders"][col]
    if valeur in enc.classes_:
        return int(enc.transform([valeur])[0]), True
    if strict:
        raise ValueError(f"Valeur inconnue pour {col} : {valeur}")
    return 0, False


def _features(c: dict, strict: bool) -> tuple[pd.DataFrame, list[str]]:
    revenu = c.get("revenu_annuel_fcfa") or 1_000_000
    mensualite = c.get("mensualite_fcfa") or 0
    ligne = {
        "montant_log": np.log1p(c.get("montant_fcfa") or 0),
        "mensualite_log": np.log1p(mensualite),
        "revenu_log": np.log1p(revenu),
        "ratio_mensualite": min(max(mensualite / (revenu / 12 + 1), 0), 5),
        "score_credit": c.get("score_credit") or 600,
        "taux_interet_pct": float(c.get("taux_interet_pct") or 12.0),
        "duree_mois": c.get("duree_mois") or 24,
        "est_diaspora_num": 1 if c.get("est_diaspora") == "Oui" else 0,
    }
    inconnues = []
    for col in CATEGORIELLES:
        code, connu = _encoder(col, c.get(col), strict)
        ligne[f"{col}_enc"] = code
        if not connu:
            inconnues.append(col)
    return pd.DataFrame([ligne], columns=FEATURES), inconnues


def scorer(c: dict, strict: bool = True) -> dict:
    """c : montant_fcfa, mensualite_fcfa, revenu_annuel_fcfa, score_credit, taux_interet_pct,
    duree_mois, est_diaspora, type_credit, garantie, banque."""
    import xgboost as xgb
    X, inconnues = _features(c, strict)
    proba = float(modele["xgb"].predict_proba(X)[0, 1])
    contrib = modele["xgb"].get_booster().predict(xgb.DMatrix(X), pred_contribs=True)[0][:-1]
    facteurs = sorted(
        ({"variable": LIBELLES[f], "impact": round(float(v), 3),
          "effet": "augmente le risque" if v > 0 else "réduit le risque"} for f, v in zip(FEATURES, contrib)),
        key=lambda d: abs(d["impact"]), reverse=True)[:5]
    resultat = {
        "probabilite_defaut": round(proba, 4),
        "score_ia": int(min(max((1 - proba) * 850, 300), 850)),
        "niveau_risque": niveau(proba),
        "facteurs": facteurs,
    }
    if inconnues:
        resultat["avertissement"] = ("Catégorie inconnue du modèle pour : " + ", ".join(inconnues)
                                     + " ; valeur par défaut utilisée.")
    return resultat
