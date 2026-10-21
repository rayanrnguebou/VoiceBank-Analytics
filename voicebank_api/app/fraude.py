"""Scoring de fraude d'une transaction avec les modèles entraînés (voicebank_ia/modeles_ia.py).

Score final = 0,4 x Isolation Forest (normalisé) + 0,6 x probabilité XGBoost,
comme lors de l'entraînement.
"""
import logging
from datetime import date

import joblib
import numpy as np
import pandas as pd

from . import config

log = logging.getLogger("voicebank")

FEATURES = ["montant_log", "heure_num", "est_nuit", "est_weekend", "type_transaction_enc",
            "canal_enc", "banque_enc", "ville_enc", "est_internationale_enc"]
CATEGORIELLES = ["type_transaction", "canal", "banque", "ville", "est_internationale"]

# Bornes de -decision_function de l'Isolation Forest, pour reproduire la
# normalisation min-max faite à l'entraînement (min/max non sauvegardés).
IF_MIN, IF_MAX = -0.16, 0.10

modeles: dict = {}


def charger():
    d = config.MODELS_DIR
    try:
        modeles["iforest"] = joblib.load(d / "isolation_forest.pkl")
        modeles["scaler"] = joblib.load(d / "scaler_fraude.pkl")
        modeles["encoders"] = joblib.load(d / "encoders_fraude.pkl")
        from xgboost import XGBClassifier
        xgb = XGBClassifier()
        xgb.load_model(str(d / "xgb_fraude.json"))
        modeles["xgb"] = xgb
        log.info("Modèles IA chargés depuis %s", d)
    except Exception:
        log.exception("Modèles IA non chargés (dossier : %s)", d)


def referentiel() -> dict:
    enc = modeles.get("encoders", {})
    return {col: [str(c) for c in enc[col].classes_] for col in CATEGORIELLES if col in enc}


def niveau(score: float) -> str:
    return ("Critique" if score >= 0.85 else "Élevé" if score >= 0.70
            else "Moyen" if score >= 0.50 else "Faible")


def analyser(montant_fcfa: float, type_transaction: str, canal: str, banque: str,
             ville: str, est_internationale: str, jour: date | None = None) -> dict:
    if "iforest" not in modeles:
        raise RuntimeError("Modèles non chargés")
    enc = modeles["encoders"]
    valeurs = {"type_transaction": type_transaction, "canal": canal, "banque": banque,
               "ville": ville, "est_internationale": est_internationale}
    for col, val in valeurs.items():
        if val not in enc[col].classes_:
            raise ValueError(f"Valeur inconnue pour {col} : {val}")
    jour = jour or date.today()
    # NB : à l'entraînement, l'heure n'a pas pu être lue (format HH:MM:SS vs %H:%M) et
    # valait toujours 12. On fournit donc la même valeur pour rester cohérent avec
    # le modèle ; il faudra réentraîner pour exploiter l'heure.
    ligne = {
        "montant_log": np.log1p(montant_fcfa), "heure_num": 12, "est_nuit": 0,
        "est_weekend": int(jour.weekday() >= 5),
        **{f"{c}_enc": int(enc[c].transform([v])[0]) for c, v in valeurs.items()},
    }
    X = pd.DataFrame([ligne], columns=FEATURES)
    brut_if = float(-modeles["iforest"].decision_function(modeles["scaler"].transform(X))[0])
    score_if = min(max((brut_if - IF_MIN) / (IF_MAX - IF_MIN), 0.0), 1.0)
    proba_xgb = float(modeles["xgb"].predict_proba(X)[0, 1]) if "xgb" in modeles else score_if
    score = round(0.4 * score_if + 0.6 * proba_xgb, 4)
    return {
        "score_anomalie": score,
        "score_isolation_forest": round(score_if, 4),
        "probabilite_xgboost": round(proba_xgb, 4),
        "niveau_risque": niveau(score),
        "est_suspecte": score >= 0.50,
    }
