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
# Une banque ou une ville que le modèle n'a pas apprise est acceptée : son effet est la moyenne des valeurs connues
OUVERTES = ("banque", "ville")

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
        "remarque": None if meta.get("heure_valide") else ("Modèle d'origine : l'heure n'est pas prise en compte. "
                                                         "Réentraîne-le avec app.outils.entrainer_fraude."),
        "fiabilite": _fiabilite(meta.get("auc_xgboost")),
    }


def _fiabilite(auc) -> str | None:
    """AUC traduite en mots, pour un public non technique."""
    if not auc:
        return None
    return ("excellente" if auc >= 0.9 else "bonne" if auc >= 0.8 else "correcte" if auc >= 0.7 else "modérée")


LIBELLES = {"montant_log": "Montant", "heure_num": "Heure", "est_nuit": "Opération de nuit", "est_weekend": "Jour",
            "type_transaction_enc": "Type d'opération", "canal_enc": "Canal", "banque_enc": "Banque",
            "ville_enc": "Ville", "est_internationale_enc": "Opération internationale"}


def _facteurs(X: pd.DataFrame, valeurs: dict, toujours: tuple = ()) -> list[dict]:
    """Contributions SHAP natives de XGBoost, regroupées et traduites (heure + nuit = « Heure »).
    `toujours` : variables montrées même hors des 5 premières (une banque ou une ville inconnue du modèle)."""
    if "xgb" not in modeles:
        return []
    import xgboost as xgb
    # Plusieurs lignes quand une banque ou une ville est inconnue : on moyenne sur les valeurs connues
    contrib = modeles["xgb"].get_booster().predict(xgb.DMatrix(X), pred_contribs=True)[:, :-1].mean(axis=0)
    groupes: dict[str, float] = {}
    for f, v in zip(FEATURES, contrib):
        nom = "Heure" if f in ("heure_num", "est_nuit") else LIBELLES[f]
        groupes[nom] = groupes.get(nom, 0.0) + float(v)
    res = []
    tries = sorted(groupes.items(), key=lambda kv: abs(kv[1]), reverse=True)
    for rang, (nom, v) in enumerate(tries):
        if nom not in toujours and (rang >= 5 or abs(v) < 0.02):
            continue
        res.append({"variable": nom, "valeur": valeurs.get(nom), "impact": round(v, 3),
                    "effet": "augmente le risque" if v > 0 else "réduit le risque"})
    return res


def recommandations(niveau_: str, facteurs: list[dict], contexte: dict) -> list[str]:
    """Conduite à tenir, selon le niveau de risque et ce qui l'explique."""
    base = {
        "Critique": ["Bloquer l'opération et contacter le client par un canal sûr (numéro déjà connu, jamais celui "
                     "fourni dans la transaction) avant toute validation.",
                     "Vérifier l'identité du donneur d'ordre et du bénéficiaire ; geler les opérations similaires du compte "
                     "le temps de la vérification.",
                     "Si la fraude est confirmée : signaler à la conformité (déclaration de soupçon à l'ANIF) et conserver "
                     "les traces."],
        "Élevé": ["Mettre l'opération en attente et demander une confirmation au client (appel ou SMS de validation).",
                  "Contrôler l'historique récent du compte : opérations similaires, changements de coordonnées, "
                  "nouveaux bénéficiaires."],
        "Moyen": ["Laisser passer mais placer le compte sous surveillance renforcée pendant quelques jours.",
                  "Vérifier que l'opération correspond aux habitudes du client (montants, horaires, bénéficiaires)."],
        "Faible": ["Aucune action particulière : l'opération ressemble aux opérations habituelles."],
    }[niveau_]
    hausse = {f["variable"] for f in facteurs if f["impact"] > 0}
    precis = []
    if "Heure" in hausse and contexte.get("nuit"):
        precis.append("Opération de nuit : vérifier si le client a l'habitude d'opérer à cette heure.")
    if "Opération internationale" in hausse and contexte.get("internationale"):
        precis.append("Opération internationale : contrôler le pays et le bénéficiaire (listes de sanctions, "
                      "pays à risque).")
    if "Montant" in hausse:
        precis.append("Montant inhabituel : appliquer une double validation (quatre yeux) au-delà de votre seuil interne.")
    if "Canal" in hausse:
        canal = str(contexte.get("canal") or "")
        bas = canal.lower()
        if any(m in bas for m in ("agence", "guichet", "branch")):
            conseil = "vérifier la pièce d'identité et la signature du client au guichet"
        elif any(m in bas for m in ("dab", "gab", "atm", "carte", "card", "tpe")):
            conseil = "vérifier que la carte n'a pas été copiée ou volée (lieu et terminal utilisés)"
        elif any(m in bas for m in ("mobile", "momo", "money")):
            conseil = "confirmer l'opération auprès du titulaire sur son numéro habituel (risque de SIM swap)"
        else:
            conseil = "vérifier l'appareil, l'adresse IP et la session utilisés"
        precis.append(f"Canal « {canal} » plus exposé : {conseil}.")
    return base + (precis if niveau_ != "Faible" else [])


def analyser(montant_fcfa: float, type_transaction: str, canal: str, banque: str,
             ville: str, est_internationale: str, jour: date | None = None,
             heure: time | None = None) -> dict:
    if "iforest" not in modeles:
        raise RuntimeError("Modèles non chargés")
    enc = modeles["encoders"]
    valeurs = {"type_transaction": type_transaction, "canal": canal, "banque": banque,
               "ville": ville, "est_internationale": est_internationale}
    inconnues = []
    for col, val in valeurs.items():
        if val not in enc[col].classes_:
            if col not in OUVERTES or not str(val or "").strip():
                raise ValueError(f"Valeur inconnue pour {col} : {val}")
            inconnues.append(col)
    jour = jour or date.today()
    meta = modeles.get("meta") or {}
    # Modèle d'origine : l'heure n'avait pas pu être lue à l'entraînement (toujours 12).
    # On ne l'utilise que si le modèle a été réentraîné avec le script corrigé.
    h = heure.hour if (heure and meta.get("heure_valide")) else 12
    ligne = {
        "montant_log": np.log1p(montant_fcfa), "heure_num": h, "est_nuit": int(h >= 22 or h <= 6),
        "est_weekend": int(jour.weekday() >= 5),
        **{f"{c}_enc": int(enc[c].transform([v])[0]) for c, v in valeurs.items() if c not in inconnues},
    }
    lignes = [ligne]
    for col in inconnues:          # une ligne par valeur connue de la colonne
        lignes = [{**l, f"{col}_enc": i} for l in lignes for i in range(len(enc[col].classes_))]
    X = pd.DataFrame(lignes, columns=FEATURES)
    brut_if = -modeles["iforest"].decision_function(modeles["scaler"].transform(X))
    if_min, if_max = meta.get("if_min", IF_MIN), meta.get("if_max", IF_MAX)
    score_if = float(np.clip((brut_if - if_min) / (if_max - if_min), 0.0, 1.0).mean())
    proba_xgb = float(modeles["xgb"].predict_proba(X)[:, 1].mean()) if "xgb" in modeles else score_if
    score = round(0.4 * score_if + 0.6 * proba_xgb, 4)
    niv = niveau(score)
    montant_txt = f"{montant_fcfa:,.0f} FCFA".replace(",", " ")
    valeurs_aff = {"Montant": montant_txt, "Heure": f"{h:02d} h" + (" (nuit)" if ligne["est_nuit"] else ""),
                   "Jour": "week-end" if ligne["est_weekend"] else "semaine", "Type d'opération": type_transaction,
                   "Canal": canal, "Banque": banque, "Ville": ville, "Opération internationale": est_internationale}
    noms = {"banque": "banque", "ville": "ville"}
    facteurs = _facteurs(X, valeurs_aff, tuple(noms[c].capitalize() for c in inconnues))
    avertissement = None
    if inconnues:
        quoi = " et ".join(f"la {noms[c]} « {valeurs[c]} »" for c in inconnues)
        avertissement = (f"Le modèle de démonstration n'a pas appris {quoi} : {'leur' if len(inconnues) > 1 else 'son'} effet est estimé par la moyenne "
                         "des valeurs qu'il connaît. Branche ta base pour un modèle appris sur tes propres données.")
        for f in facteurs:
            if f["variable"].lower() in inconnues:
                f["detail"] = f"{f['valeur']} (inconnue du modèle, effet moyen)"
    return {
        "avertissement": avertissement,
        "score_anomalie": score,
        "score_isolation_forest": round(score_if, 4),
        "probabilite_xgboost": round(proba_xgb, 4),
        "niveau_risque": niv,
        "est_suspecte": score >= 0.50,
        "facteurs": facteurs,
        "recommandations": recommandations(niv, facteurs, {"nuit": bool(ligne["est_nuit"]), "canal": canal,
                                                           "internationale": est_internationale == "Oui"}),
    }
