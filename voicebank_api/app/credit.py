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


OUVERTES = ("banque",)   # une banque inconnue du modèle est acceptée : effet moyen des banques connues


def _encoder(col: str, valeur, strict: bool) -> tuple[int, bool]:
    enc = modele["encoders"][col]
    if valeur in enc.classes_:
        return int(enc.transform([valeur])[0]), True
    if strict and (col not in OUVERTES or not str(valeur or "").strip()):
        raise ValueError(f"Valeur inconnue pour {col} : {valeur}")
    return 0, False


def _deplier(X: pd.DataFrame, inconnues: list[str]) -> pd.DataFrame:
    """Une ligne par valeur connue de chaque colonne inconnue (pour en moyenner l'effet)."""
    for col in inconnues:
        n = len(modele["encoders"][col].classes_)
        X = pd.concat([X.assign(**{f"{col}_enc": i}) for i in range(n)], ignore_index=True)
    return X


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
    Xd = _deplier(X, inconnues)
    proba = float(modele["xgb"].predict_proba(Xd)[:, 1].mean())
    contrib = modele["xgb"].get_booster().predict(xgb.DMatrix(Xd), pred_contribs=True)[:, :-1].mean(axis=0)
    valeurs = _valeurs_affichees(c, X.iloc[0])
    facteurs = sorted(
        ({"variable": LIBELLES[f], "code": f, "valeur": valeurs.get(f), "impact": round(float(v), 3),
          "effet": "augmente le risque" if v > 0 else "réduit le risque"} for f, v in zip(FEATURES, contrib)),
        key=lambda d: abs(d["impact"]), reverse=True)[:5]
    niv = niveau(proba)
    resultat = {
        "probabilite_defaut": round(proba, 4),
        "score_ia": int(min(max((1 - proba) * 850, 300), 850)),
        "niveau_risque": niv,
        "facteurs": facteurs,
        "ratio_mensualite_pct": round(float(X.iloc[0]["ratio_mensualite"]) * 100, 1),
        "recommandations": recommandations(niv, facteurs, c, float(X.iloc[0]["ratio_mensualite"])),
    }
    if inconnues:
        resultat["avertissement"] = ("Le modèle de démonstration n'a pas appris " + " et ".join(
            f"la valeur « {c.get(x)} » ({x.replace('_', ' ')})" for x in inconnues)
            + " : son effet est estimé par la moyenne des valeurs qu'il connaît.")
    return resultat


def _fcfa(v) -> str:
    return f"{float(v or 0):,.0f} FCFA".replace(",", " ")


def _valeurs_affichees(c: dict, x) -> dict:
    return {"montant_log": _fcfa(c.get("montant_fcfa")), "mensualite_log": _fcfa(c.get("mensualite_fcfa")),
            "revenu_log": _fcfa(c.get("revenu_annuel_fcfa")),
            "ratio_mensualite": f"{float(x['ratio_mensualite']) * 100:.0f} % du revenu mensuel",
            "score_credit": f"{int(x['score_credit'])} / 850", "taux_interet_pct": f"{float(x['taux_interet_pct']):g} %",
            "duree_mois": f"{int(x['duree_mois'])} mois", "est_diaspora_num": "Oui" if x["est_diaspora_num"] else "Non",
            "type_credit_enc": c.get("type_credit"), "garantie_enc": c.get("garantie"), "banque_enc": c.get("banque")}


def recommandations(niveau_: str, facteurs: list[dict], c: dict, ratio: float) -> list[str]:
    """Décision conseillée et leviers concrets, d'après ce qui fait monter le risque."""
    decision = {
        "Faible": "Accord envisageable aux conditions demandées.",
        "Moyen": "Accord possible sous conditions : sécuriser le dossier avant décaissement.",
        "Élevé": "Accord déconseillé en l'état : revoir le montant, la durée ou les garanties.",
        "Critique": "Refus recommandé, ou dossier à restructurer entièrement avant un nouvel examen.",
    }[niveau_]
    leviers = []
    hausse = [f["code"] for f in facteurs if f["impact"] > 0]
    if ratio > 0.33 or "ratio_mensualite" in hausse or "mensualite_log" in hausse:
        leviers.append(f"La mensualité pèse {ratio * 100:.0f} % du revenu mensuel (repère prudent : 33 %) : allonger la durée "
                       "ou réduire le montant pour alléger l'échéance.")
    if "score_credit" in hausse:
        leviers.append("Historique de crédit fragile : demander un co-emprunteur ou une garantie solide, et vérifier les "
                       "incidents de paiement récents.")
    if c.get("garantie") in ("Sans garantie", None) or "garantie_enc" in hausse:
        leviers.append("Garantie insuffisante : exiger une caution, un nantissement ou une hypothèque selon le montant.")
    if "taux_interet_pct" in hausse:
        leviers.append("Le taux alourdit la charge : un taux révisé ou une bonification réduirait le risque.")
    if "duree_mois" in hausse:
        leviers.append("Durée longue : plus d'aléas sur la période ; un échéancier plus court est préférable si la capacité "
                       "de remboursement le permet.")
    if "montant_log" in hausse:
        leviers.append("Montant élevé au regard du profil : envisager un décaissement en plusieurs tranches.")
    if "type_credit_enc" in hausse:
        leviers.append(f"Les crédits « {c.get('type_credit')} » font plus de défauts dans le portefeuille : prévoir un suivi "
                       "rapproché des premières échéances.")
    if niveau_ == "Faible":
        return [decision] + leviers[:1]
    return [decision] + leviers[:4] + ["Mettre en place un suivi des premières échéances (alerte au premier retard)."]


def scorer_lot(credits: list[dict]) -> list[dict]:
    """Probabilité de défaut de nombreux crédits en UNE prédiction (sans explication SHAP, calculée à la
    demande pour un crédit précis) : quelques millisecondes pour des milliers de crédits."""
    if not credits:
        return []
    enc = modele["encoders"]
    codes = {col: {v: i for i, v in enumerate(enc[col].classes_)} for col in CATEGORIELLES}
    df = pd.DataFrame(credits)
    for col in ("montant_fcfa", "mensualite_fcfa", "revenu_annuel_fcfa", "score_credit", "taux_interet_pct", "duree_mois"):
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    revenu = df["revenu_annuel_fcfa"].fillna(1_000_000).replace(0, 1_000_000)
    mensualite = df["mensualite_fcfa"].fillna(0)
    X = pd.DataFrame({
        "montant_log": np.log1p(df["montant_fcfa"].fillna(0).clip(lower=0)),
        "mensualite_log": np.log1p(mensualite.clip(lower=0)),
        "revenu_log": np.log1p(revenu.clip(lower=0)),
        "ratio_mensualite": (mensualite / (revenu / 12 + 1)).clip(0, 5),
        "score_credit": df["score_credit"].fillna(600),
        "taux_interet_pct": df["taux_interet_pct"].fillna(12.0).astype(float),
        "duree_mois": df["duree_mois"].fillna(24),
        "est_diaspora_num": (df.get("est_diaspora") == "Oui").astype(int),
        **{f"{col}_enc": df.get(col).map(codes[col]).fillna(0).astype(int) for col in CATEGORIELLES},
    }, columns=FEATURES)
    probas = modele["xgb"].predict_proba(X)[:, 1]
    return [{"probabilite_defaut": round(float(p), 4), "score_ia": int(min(max((1 - p) * 850, 300), 850)),
             "niveau_risque": niveau(float(p))} for p in probas]

