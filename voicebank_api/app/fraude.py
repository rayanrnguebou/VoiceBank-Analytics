"""Scoring de fraude d'une transaction avec les modèles entraînés (voicebank_ia/modeles_ia.py).

Score final = 0,4 x Isolation Forest (normalisé) + 0,6 x probabilité XGBoost,
comme lors de l'entraînement.
"""
import json
import logging
from datetime import date, time

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
        meta = d / "meta_fraude.json"
        modeles["meta"] = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
        log.info("Modèles IA chargés depuis %s", d)
    except Exception:
        log.exception("Modèles IA non chargés (dossier : %s)", d)


def referentiel() -> dict:
    enc = modeles.get("encoders", {})
    return {col: [str(c) for c in enc[col].classes_] for col in CATEGORIELLES if col in enc}


def niveau(score: float) -> str:
    return ("Critique" if score >= 0.85 else "Élevé" if score >= 0.70
            else "Moyen" if score >= 0.50 else "Faible")


def infos_modele() -> dict:
    meta = modeles.get("meta") or {}
    return {
        "date_entrainement": meta.get("date_entrainement"),
        "nb_transactions": meta.get("nb_transactions"),
        "auc_xgboost": meta.get("auc_xgboost"),
        "heure_prise_en_compte": bool(meta.get("heure_valide")),
        "remarque": None if meta else ("Modèle d'origine : l'heure n'a pas été apprise. "
                                       "Réentraîne-le avec app.outils.entrainer_fraude."),
    }


def analyser(montant_fcfa: float, type_transaction: str, canal: str, banque: str,
             ville: str, est_internationale: str, jour: date | None = None,
             heure: time | None = None) -> dict:
    if "iforest" not in modeles:
        raise RuntimeError("Modèles non chargés")
    enc = modeles["encoders"]
    valeurs = {"type_transaction": type_transaction, "canal": canal, "banque": banque,
               "ville": ville, "est_internationale": est_internationale}
    for col, val in valeurs.items():
        if val not in enc[col].classes_:
            raise ValueError(f"Valeur inconnue pour {col} : {val}")
    jour = jour or date.today()
    meta = modeles.get("meta") or {}
    # Modèle d'origine : l'heure n'avait pas pu être lue à l'entraînement (toujours 12).
    # On ne l'utilise que si le modèle a été réentraîné avec le script corrigé.
    h = heure.hour if (heure and meta.get("heure_valide")) else 12
    ligne = {
        "montant_log": np.log1p(montant_fcfa), "heure_num": h, "est_nuit": int(h >= 22 or h <= 6),
        "est_weekend": int(jour.weekday() >= 5),
        **{f"{c}_enc": int(enc[c].transform([v])[0]) for c, v in valeurs.items()},
    }
    X = pd.DataFrame([ligne], columns=FEATURES)
    brut_if = float(-modeles["iforest"].decision_function(modeles["scaler"].transform(X))[0])
    if_min, if_max = meta.get("if_min", IF_MIN), meta.get("if_max", IF_MAX)
    score_if = min(max((brut_if - if_min) / (if_max - if_min), 0.0), 1.0)
    proba_xgb = float(modeles["xgb"].predict_proba(X)[0, 1]) if "xgb" in modeles else score_if
    score = round(0.4 * score_if + 0.6 * proba_xgb, 4)
    return {
        "score_anomalie": score,
        "score_isolation_forest": round(score_if, 4),
        "probabilite_xgboost": round(proba_xgb, 4),
        "niveau_risque": niveau(score),
        "est_suspecte": score >= 0.50,
    }
