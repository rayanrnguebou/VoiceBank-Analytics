"""Réentraîne le modèle de fraude (Isolation Forest + XGBoost) à partir de la base.

Corrige le défaut du script d'origine : l'heure (format HH:MM:SS) n'était jamais lue.
Écrit les modèles + meta_fraude.json (date, AUC, bornes de normalisation) dans MODELS_DIR.

Avec Docker (depuis la racine du projet) :
  docker compose run --rm -v ./voicebank_ia/modeles_sauvegardes:/app/voicebank_ia/modeles_sauvegardes \\
      api python -m app.outils.entrainer_fraude
puis : docker compose up -d --build api
"""
import argparse
import json
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

from .. import config, db

CATEGORIELLES = ["type_transaction", "canal", "banque", "ville", "est_internationale"]
FEATURES = ["montant_log", "heure_num", "est_nuit", "est_weekend"] + [f"{c}_enc" for c in CATEGORIELLES]


def charger(max_lignes: int) -> pd.DataFrame:
    _, total = db.lire("SELECT COUNT(*) AS n FROM voicebank.transactions")
    n = total[0]["n"]
    echantillon = "" if n <= max_lignes else f"TABLESAMPLE SYSTEM ({min(100, max_lignes / n * 110):.4f})"
    colonnes, lignes = db.lire(
        f"SELECT montant_fcfa, heure_transaction, date_transaction, est_frauduleuse, "
        f"{', '.join(CATEGORIELLES)} FROM voicebank.transactions {echantillon} LIMIT {int(max_lignes)}")
    print(f"  {len(lignes):,} transactions chargées sur {n:,}")
    return pd.DataFrame(lignes, columns=colonnes)


def preparer(df: pd.DataFrame):
    data = df.copy()
    data["montant_log"] = np.log1p(data["montant_fcfa"].astype(float))
    data["heure_num"] = pd.to_datetime(data["heure_transaction"].astype(str), format="mixed",
                                       errors="coerce").dt.hour.fillna(12).astype(int)
    data["est_nuit"] = ((data["heure_num"] >= 22) | (data["heure_num"] <= 6)).astype(int)
    data["est_weekend"] = pd.to_datetime(data["date_transaction"], errors="coerce").dt.dayofweek.isin([5, 6]).astype(int)
    encodeurs = {}
    for col in CATEGORIELLES:
        le = LabelEncoder()
        data[f"{col}_enc"] = le.fit_transform(data[col].astype(str).fillna("Inconnu"))
        encodeurs[col] = le
    return data, encodeurs


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--max-lignes", type=int, default=500_000)
    a = p.parse_args()

    print("→ Chargement des transactions…")
    data, encodeurs = preparer(charger(a.max_lignes))
    nb_heures = data["heure_num"].nunique()
    print(f"  Heures distinctes lues : {nb_heures} (l'ancien script n'en lisait qu'une)")
    X = data[FEATURES].astype(float)
    y = (data["est_frauduleuse"].astype(str).str.upper() == "OUI").astype(int)

    print("→ Isolation Forest…")
    scaler = StandardScaler().fit(X)
    iforest = IsolationForest(n_estimators=200, contamination=0.04, random_state=42, n_jobs=-1)
    iforest.fit(scaler.transform(X))
    brut = -iforest.decision_function(scaler.transform(X))
    if_min, if_max = float(np.quantile(brut, 0.001)), float(np.quantile(brut, 0.999))

    print("→ XGBoost…")
    auc = None
    xgb = None
    if y.sum() >= 10:
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
        # Modèle volontairement prudent (arbres peu profonds, régularisé) et contraintes métier : un montant
        # plus élevé, une opération de nuit ou internationale ne peuvent qu'AUGMENTER le risque. Les
        # explications restent ainsi cohérentes, même sur des données bruitées.
        monotones = {"montant_log": 1, "est_nuit": 1, "est_internationale_enc": 1}
        oui_en_dernier = list(encodeurs["est_internationale"].classes_)[-1:] == ["Oui"]
        contraintes = tuple(monotones.get(f, 0) if (f != "est_internationale_enc" or oui_en_dernier) else 0
                            for f in FEATURES)
        xgb = XGBClassifier(n_estimators=250, max_depth=3, learning_rate=0.05, min_child_weight=10,
                            subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0,
                            monotone_constraints=contraintes,
                            scale_pos_weight=(y == 0).sum() / max((y == 1).sum(), 1),
                            eval_metric="aucpr", random_state=42, n_jobs=-1)
        xgb.fit(X_tr, y_tr)
        auc = round(float(roc_auc_score(y_te, xgb.predict_proba(X_te)[:, 1])), 4)
        print(f"  AUC-ROC (jeu de test) : {auc}")
    else:
        print("  Trop peu de fraudes étiquetées : XGBoost non réentraîné")

    d = config.MODELS_DIR
    joblib.dump(iforest, d / "isolation_forest.pkl")
    joblib.dump(scaler, d / "scaler_fraude.pkl")
    joblib.dump(encodeurs, d / "encoders_fraude.pkl")
    if xgb is not None:
        xgb.save_model(str(d / "xgb_fraude.json"))
    meta = {"date_entrainement": datetime.now().isoformat(timespec="seconds"), "nb_transactions": len(data),
            "nb_fraudes": int(y.sum()), "auc_xgboost": auc, "heure_valide": nb_heures > 1,
            "if_min": if_min, "if_max": if_max, "features": FEATURES}
    (d / "meta_fraude.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Modèles enregistrés dans {d}. Relance l'API pour les utiliser.")


if __name__ == "__main__":
    main()
