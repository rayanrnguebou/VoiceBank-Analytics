"""
╔══════════════════════════════════════════════════════════════╗
║   VOICEBANK ANALYTICS — Modèles IA                          ║
║   Auteur : Nguebou Temgoua Rayan                            ║
║                                                              ║
║   Modèle 1 : Détection de fraude (Isolation Forest+XGBoost) ║
║   Modèle 2 : Scoring de crédit   (XGBoost + SHAP)           ║
╚══════════════════════════════════════════════════════════════╝

Installation :
    pip install pandas numpy scikit-learn xgboost shap sqlalchemy
                psycopg2-binary matplotlib seaborn joblib tqdm
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import shap
import joblib
import os
import warnings
from datetime import datetime
from tqdm import tqdm

from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import (classification_report, confusion_matrix,
                             roc_auc_score, roc_curve, precision_recall_curve)
from xgboost import XGBClassifier
from sqlalchemy import create_engine, text

warnings.filterwarnings("ignore")
np.random.seed(42)

# ════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════

DB_URL     = "postgresql://voicebank_user:voicebank2024@localhost:5432/voicebank_db"
CSV_DIR    = "../output_voicebank"
MODELS_DIR = "./modeles_sauvegardes"
PLOTS_DIR  = "./graphiques_ia"

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR,  exist_ok=True)


# ════════════════════════════════════════════════════════
# UTILITAIRES
# ════════════════════════════════════════════════════════

def charger_depuis_postgres(table):
    """Charge une table depuis PostgreSQL."""
    try:
        engine = create_engine(DB_URL)
        df = pd.read_sql(f"SELECT * FROM voicebank.{table}", engine)
        print(f"  ✓ {table} chargé depuis PostgreSQL → {len(df):,} lignes")
        return df
    except Exception as e:
        print(f"  ⚠️  PostgreSQL indisponible ({e}) → chargement depuis CSV")
        return pd.read_csv(f"{CSV_DIR}/{table}.csv", low_memory=False, encoding="utf-8-sig")

def sauvegarder_alertes(df_alertes):
    """Insère les alertes fraude dans PostgreSQL."""
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE voicebank.alertes_fraude"))
            conn.commit()
        df_alertes.to_sql("alertes_fraude", engine, schema="voicebank",
                          if_exists="append", index=False, method="multi")
        print(f"  ✓ {len(df_alertes):,} alertes insérées dans voicebank.alertes_fraude")
    except Exception as e:
        print(f"  ⚠️  Impossible d'insérer dans PostgreSQL : {e}")
        df_alertes.to_csv(f"{MODELS_DIR}/alertes_fraude.csv", index=False)
        print(f"  → Sauvegardé dans {MODELS_DIR}/alertes_fraude.csv")

def plot_save(fig, nom):
    path = f"{PLOTS_DIR}/{nom}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ Graphique sauvegardé → {path}")


# ════════════════════════════════════════════════════════
# ══ MODÈLE 1 : DÉTECTION DE FRAUDE ══════════════════════
# ════════════════════════════════════════════════════════

class DetecteurFraude:
    """
    Pipeline de détection de fraude bancaire en deux étapes :
      1. Isolation Forest  → détection non supervisée d'anomalies
      2. XGBoost Classifier → classification supervisée (si labels dispo)
    """

    def __init__(self):
        self.isolation_forest = None
        self.xgb_fraude       = None
        self.scaler           = StandardScaler()
        self.encoders         = {}
        self.features         = []

    # ── Préparation des features ──────────────────────────
    def preparer_features(self, df):
        print("\n  → Préparation des features transactions...")
        data = df.copy()

        # Variables numériques
        data["montant_log"]    = np.log1p(data["montant_fcfa"])
        data["heure_num"]      = pd.to_datetime(
            data["heure_transaction"], format="%H:%M", errors="coerce"
        ).dt.hour.fillna(12)
        data["est_nuit"]       = ((data["heure_num"] >= 22) | (data["heure_num"] <= 6)).astype(int)
        data["est_weekend"]    = pd.to_datetime(
            data["date_transaction"], errors="coerce"
        ).dt.dayofweek.isin([5, 6]).astype(int)

        # Encodage des variables catégorielles
        cols_cat = ["type_transaction", "canal", "banque", "ville", "est_internationale"]
        for col in cols_cat:
            if col in data.columns:
                le = LabelEncoder()
                data[col + "_enc"] = le.fit_transform(data[col].astype(str).fillna("Inconnu"))
                self.encoders[col] = le

        self.features = (
            ["montant_log", "heure_num", "est_nuit", "est_weekend"] +
            [c + "_enc" for c in cols_cat if c in data.columns]
        )

        print(f"  ✓ {len(self.features)} features préparées : {self.features}")
        return data

    # ── Isolation Forest (non supervisé) ─────────────────
    def entrainer_isolation_forest(self, data):
        print("\n  → Entraînement Isolation Forest...")
        X = data[self.features].fillna(0)
        X_scaled = self.scaler.fit_transform(X)

        self.isolation_forest = IsolationForest(
            n_estimators=200,
            contamination=0.04,    # ~4% de fraudes attendues
            max_samples="auto",
            random_state=42,
            n_jobs=-1,
        )
        self.isolation_forest.fit(X_scaled)
        scores = self.isolation_forest.decision_function(X_scaled)
        predictions = self.isolation_forest.predict(X_scaled)

        # -1 = anomalie, 1 = normal → convertir en 0/1
        data["anomalie_if"]    = (predictions == -1).astype(int)
        data["score_anomalie"] = -scores   # plus le score est haut, plus c'est suspect
        # Normaliser entre 0 et 1
        mn, mx = data["score_anomalie"].min(), data["score_anomalie"].max()
        data["score_anomalie"] = (data["score_anomalie"] - mn) / (mx - mn + 1e-9)

        nb_anomalies = data["anomalie_if"].sum()
        print(f"  ✓ Isolation Forest terminé")
        print(f"     Anomalies détectées : {nb_anomalies:,} ({nb_anomalies/len(data)*100:.2f}%)")
        return data

    # ── XGBoost supervisé ─────────────────────────────────
    def entrainer_xgboost(self, data):
        if "est_frauduleuse" not in data.columns:
            print("  ⚠️  Pas de labels → XGBoost ignoré (mode non supervisé uniquement)")
            return data

        print("\n  → Entraînement XGBoost (supervisé)...")
        y = (data["est_frauduleuse"].str.upper() == "OUI").astype(int)

        if y.sum() < 10:
            print("  ⚠️  Trop peu de fraudes labellisées → XGBoost ignoré")
            return data

        X = data[self.features].fillna(0)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=42
        )

        ratio = (y == 0).sum() / (y == 1).sum()
        self.xgb_fraude = XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            scale_pos_weight=ratio,
            use_label_encoder=False,
            eval_metric="aucpr",
            random_state=42,
            n_jobs=-1,
        )
        self.xgb_fraude.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        y_pred  = self.xgb_fraude.predict(X_test)
        y_proba = self.xgb_fraude.predict_proba(X_test)[:, 1]
        auc     = roc_auc_score(y_test, y_proba)

        print(f"  ✓ XGBoost Fraude — AUC-ROC : {auc:.4f}")
        print("\n" + classification_report(y_test, y_pred,
              target_names=["Légitime", "Fraude"]))

        # Score XGBoost sur tout le dataset
        data["score_xgb_fraude"] = self.xgb_fraude.predict_proba(X.fillna(0))[:, 1]
        # Score final = moyenne pondérée IF + XGBoost
        data["score_final_fraude"] = (
            0.4 * data["score_anomalie"] + 0.6 * data["score_xgb_fraude"]
        )

        # Graphiques
        self._plot_roc(y_test, y_proba, auc)
        self._plot_confusion(y_test, y_pred)
        return data

    def _plot_roc(self, y_test, y_proba, auc):
        fpr, tpr, _ = roc_curve(y_test, y_proba)
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.plot(fpr, tpr, color="#185FA5", lw=2, label=f"AUC = {auc:.4f}")
        ax.plot([0, 1], [0, 1], "k--", lw=1)
        ax.set_xlabel("Taux Faux Positifs")
        ax.set_ylabel("Taux Vrais Positifs")
        ax.set_title("Courbe ROC — Détection de Fraude")
        ax.legend()
        ax.grid(alpha=0.3)
        plot_save(fig, "roc_fraude")

    def _plot_confusion(self, y_test, y_pred):
        cm = confusion_matrix(y_test, y_pred)
        fig, ax = plt.subplots(figsize=(5, 4))
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                    xticklabels=["Légitime", "Fraude"],
                    yticklabels=["Légitime", "Fraude"], ax=ax)
        ax.set_title("Matrice de Confusion — Fraude")
        ax.set_ylabel("Réel")
        ax.set_xlabel("Prédit")
        plot_save(fig, "confusion_fraude")

    # ── Générer les alertes ───────────────────────────────
    def generer_alertes(self, data):
        print("\n  → Génération des alertes fraude...")
        score_col = "score_final_fraude" if "score_final_fraude" in data.columns else "score_anomalie"

        def niveau_alerte(score):
            if score >= 0.85: return "Critique"
            if score >= 0.70: return "Élevé"
            if score >= 0.50: return "Moyen"
            return "Faible"

        suspectes = data[data[score_col] >= 0.50].copy()
        suspectes["niveau_alerte"] = suspectes[score_col].apply(niveau_alerte)
        suspectes["score_anomalie"] = suspectes[score_col].round(4)
        suspectes["motif"] = suspectes.apply(lambda r: self._motif(r), axis=1)
        suspectes["traitee"] = False
        suspectes["date_alerte"] = datetime.now()

        alertes = suspectes[["id_transaction", "id_client", "score_anomalie",
                              "niveau_alerte", "motif", "traitee", "date_alerte"]].copy()
        alertes = alertes.rename(columns={})

        print(f"  ✓ {len(alertes):,} alertes générées")
        print(f"     Critique : {(alertes['niveau_alerte']=='Critique').sum():,}")
        print(f"     Élevé    : {(alertes['niveau_alerte']=='Élevé').sum():,}")
        print(f"     Moyen    : {(alertes['niveau_alerte']=='Moyen').sum():,}")
        return alertes

    def _motif(self, row):
        motifs = []
        if row.get("montant_fcfa", 0) > 5_000_000:
            motifs.append("Montant élevé")
        if row.get("est_nuit", 0) == 1:
            motifs.append("Transaction nocturne")
        if row.get("est_internationale_enc", 0) == 1:
            motifs.append("Transaction internationale")
        if row.get("est_weekend", 0) == 1:
            motifs.append("Weekend")
        return " · ".join(motifs) if motifs else "Comportement inhabituel"

    def sauvegarder(self):
        joblib.dump(self.isolation_forest, f"{MODELS_DIR}/isolation_forest.pkl")
        joblib.dump(self.scaler,           f"{MODELS_DIR}/scaler_fraude.pkl")
        joblib.dump(self.encoders,         f"{MODELS_DIR}/encoders_fraude.pkl")
        if self.xgb_fraude:
            self.xgb_fraude.save_model(f"{MODELS_DIR}/xgb_fraude.json")
        print(f"  ✓ Modèles fraude sauvegardés dans {MODELS_DIR}/")

    def executer(self, df_transactions):
        print("\n" + "═"*55)
        print("  MODÈLE 1 — DÉTECTION DE FRAUDE")
        print("═"*55)
        data   = self.preparer_features(df_transactions)
        data   = self.entrainer_isolation_forest(data)
        data   = self.entrainer_xgboost(data)
        alertes = self.generer_alertes(data)
        sauvegarder_alertes(alertes)
        self.sauvegarder()
        return data, alertes


# ════════════════════════════════════════════════════════
# ══ MODÈLE 2 : SCORING DE CRÉDIT ════════════════════════
# ════════════════════════════════════════════════════════

class ScoringCredit:
    """
    Modèle de scoring de crédit avec explainability SHAP.
    Prédit la probabilité de défaut d'un dossier de crédit.
    """

    def __init__(self):
        self.xgb_credit  = None
        self.encoders    = {}
        self.scaler      = StandardScaler()
        self.features    = []
        self.explainer   = None

    # ── Préparation des features ──────────────────────────
    def preparer_features(self, df):
        print("\n  → Préparation des features crédit...")
        data = df.copy()

        # Variables numériques enrichies
        data["montant_log"]         = np.log1p(data["montant_fcfa"].fillna(0))
        data["mensualite_log"]      = np.log1p(data["mensualite_fcfa"].fillna(0))
        data["revenu_log"]          = np.log1p(data["revenu_annuel_fcfa"].fillna(1_000_000))
        data["ratio_mensualite"]    = (
            data["mensualite_fcfa"].fillna(0) /
            (data["revenu_annuel_fcfa"].fillna(1_000_000) / 12 + 1)
        ).clip(0, 5)
        data["score_credit"]        = data["score_credit"].fillna(600)
        data["taux_interet_pct"]    = data["taux_interet_pct"].fillna(12.0)
        data["duree_mois"]          = data["duree_mois"].fillna(24)
        data["est_diaspora_num"]    = (data["est_diaspora"] == "Oui").astype(int)

        # Encodage catégorielles
        cols_cat = ["type_credit", "garantie", "banque"]
        for col in cols_cat:
            if col in data.columns:
                le = LabelEncoder()
                data[col + "_enc"] = le.fit_transform(data[col].astype(str).fillna("Inconnu"))
                self.encoders[col] = le

        self.features = [
            "montant_log", "mensualite_log", "revenu_log",
            "ratio_mensualite", "score_credit", "taux_interet_pct",
            "duree_mois", "est_diaspora_num",
        ] + [c + "_enc" for c in cols_cat if c in data.columns]

        print(f"  ✓ {len(self.features)} features préparées")
        return data

    # ── Entraînement XGBoost ──────────────────────────────
    def entrainer(self, data):
        print("\n  → Entraînement XGBoost Scoring Crédit...")

        # Cible : 1 = défaut ou retard, 0 = en cours ou remboursé
        data["cible"] = data["statut_credit"].isin(["Défaut", "En retard"]).astype(int)

        X = data[self.features].fillna(0)
        y = data["cible"]

        print(f"     Distribution : {y.value_counts().to_dict()}")

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=42
        )

        ratio = (y == 0).sum() / max((y == 1).sum(), 1)
        self.xgb_credit = XGBClassifier(
            n_estimators=400,
            max_depth=5,
            learning_rate=0.03,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=ratio,
            use_label_encoder=False,
            eval_metric="auc",
            random_state=42,
            n_jobs=-1,
        )
        self.xgb_credit.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        y_pred  = self.xgb_credit.predict(X_test)
        y_proba = self.xgb_credit.predict_proba(X_test)[:, 1]
        auc     = roc_auc_score(y_test, y_proba)

        print(f"  ✓ XGBoost Crédit — AUC-ROC : {auc:.4f}")
        print("\n" + classification_report(y_test, y_pred,
              target_names=["Sain", "Défaut/Retard"]))

        # Score sur tout le dataset
        data["proba_defaut"]  = self.xgb_credit.predict_proba(X.fillna(0))[:, 1]
        data["score_credit_ia"] = ((1 - data["proba_defaut"]) * 850).clip(300, 850).astype(int)
        data["risque_ia"]     = data["proba_defaut"].apply(
            lambda p: "Critique" if p > 0.7 else
                      "Élevé"    if p > 0.5 else
                      "Moyen"    if p > 0.3 else "Faible"
        )

        self._plot_roc(y_test, y_proba, auc)
        self._plot_importance()
        return data

    # ── SHAP — Explainability ─────────────────────────────
    def expliquer_shap(self, data):
        print("\n  → Calcul SHAP (explainability)...")
        X = data[self.features].fillna(0)

        # Échantillon pour SHAP (trop long sur tout le dataset)
        sample = X.sample(min(1000, len(X)), random_state=42)

        # self.explainer = shap.TreeExplainer(self.xgb_credit)
        try:
            self.explainer = shap.TreeExplainer(self.xgb_credit)
        except Exception:
            self.explainer = shap.Explainer(self.xgb_credit, sample)
            
        shap_values    = self.explainer.shap_values(sample)

        # Plot 1 : importance globale des features
        fig1, ax1 = plt.subplots(figsize=(8, 5))
        shap.summary_plot(shap_values, sample, plot_type="bar",
                          feature_names=self.features, show=False)
        plt.title("SHAP — Importance des variables (Scoring Crédit)")
        plt.tight_layout()
        plot_save(plt.gcf(), "shap_importance_credit")

        # Plot 2 : beeswarm (distribution des impacts)
        fig2, ax2 = plt.subplots(figsize=(8, 6))
        shap.summary_plot(shap_values, sample,
                          feature_names=self.features, show=False)
        plt.title("SHAP — Impact des variables sur le score")
        plt.tight_layout()
        plot_save(plt.gcf(), "shap_beeswarm_credit")

        print("  ✓ Graphiques SHAP générés")
        return shap_values, sample

    def expliquer_client(self, data, id_credit=None):
        """Explique le score d'un client spécifique."""
        if id_credit is None:
            # Prend le client avec le plus haut risque
            row = data.nlargest(1, "proba_defaut").iloc[0]
        else:
            row = data[data["id_credit"] == id_credit].iloc[0]

        X_client = pd.DataFrame([row[self.features].fillna(0)])
        shap_vals = self.explainer.shap_values(X_client)

        fig, ax = plt.subplots(figsize=(9, 4))
        shap.waterfall_plot(
            shap.Explanation(
                values=shap_vals[0],
                base_values=self.explainer.expected_value,
                data=X_client.iloc[0].values,
                feature_names=self.features,
            ),
            show=False,
        )
        plt.title(f"Explication du score — Crédit {row.get('id_credit','?')}")
        plt.tight_layout()
        plot_save(fig, f"shap_explication_client")

        print(f"\n  Client : {row.get('id_credit','?')}")
        print(f"  Score IA     : {row.get('score_credit_ia', '?')}/850")
        print(f"  Proba défaut : {row.get('proba_defaut', 0)*100:.1f}%")
        print(f"  Risque       : {row.get('risque_ia','?')}")

    def _plot_roc(self, y_test, y_proba, auc):
        fpr, tpr, _ = roc_curve(y_test, y_proba)
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.plot(fpr, tpr, color="#1D9E75", lw=2, label=f"AUC = {auc:.4f}")
        ax.plot([0, 1], [0, 1], "k--", lw=1)
        ax.set_xlabel("Taux Faux Positifs")
        ax.set_ylabel("Taux Vrais Positifs")
        ax.set_title("Courbe ROC — Scoring de Crédit")
        ax.legend()
        ax.grid(alpha=0.3)
        plot_save(fig, "roc_credit")

    def _plot_importance(self):
        importance = pd.Series(
            self.xgb_credit.feature_importances_,
            index=self.features
        ).sort_values(ascending=True)

        fig, ax = plt.subplots(figsize=(7, 5))
        importance.plot(kind="barh", color="#185FA5", ax=ax)
        ax.set_title("Importance des variables — XGBoost Crédit")
        ax.set_xlabel("Score d'importance")
        ax.grid(axis="x", alpha=0.3)
        plot_save(fig, "importance_credit")

    def sauvegarder(self):
        self.xgb_credit.save_model(f"{MODELS_DIR}/xgb_credit.json")
        joblib.dump(self.encoders,  f"{MODELS_DIR}/encoders_credit.pkl")
        joblib.dump(self.explainer, f"{MODELS_DIR}/shap_explainer.pkl")
        print(f"  ✓ Modèle crédit sauvegardé dans {MODELS_DIR}/")

    def executer(self, df_credits):
        print("\n" + "═"*55)
        print("  MODÈLE 2 — SCORING DE CRÉDIT")
        print("═"*55)
        data = self.preparer_features(df_credits)
        data = self.entrainer(data)
        self.expliquer_shap(data)
        self.expliquer_client(data)
        self.sauvegarder()
        # Sauvegarder les scores dans un CSV
        cols_export = ["id_credit", "id_client", "montant_fcfa", "statut_credit",
                       "proba_defaut", "score_credit_ia", "risque_ia"]
        cols_export = [c for c in cols_export if c in data.columns]
        data[cols_export].to_csv(f"{MODELS_DIR}/scores_credit.csv", index=False)
        print(f"  ✓ Scores exportés → {MODELS_DIR}/scores_credit.csv")
        return data


# ════════════════════════════════════════════════════════
# RAPPORT SYNTHÈSE
# ════════════════════════════════════════════════════════

def rapport_final(df_transactions, df_credits, alertes):
    print("\n" + "═"*55)
    print("  RAPPORT IA — VOICEBANK ANALYTICS")
    print("═"*55)

    print("\n📊 FRAUDE")
    print(f"  Transactions analysées   : {len(df_transactions):>10,}")
    print(f"  Alertes générées         : {len(alertes):>10,}")
    if "niveau_alerte" in alertes.columns:
        for niveau in ["Critique", "Élevé", "Moyen"]:
            n = (alertes["niveau_alerte"] == niveau).sum()
            print(f"  → {niveau:<10}           : {n:>10,}")

    print("\n📊 CRÉDIT")
    print(f"  Dossiers scorés          : {len(df_credits):>10,}")
    if "risque_ia" in df_credits.columns:
        for risque in ["Critique", "Élevé", "Moyen", "Faible"]:
            n = (df_credits["risque_ia"] == risque).sum()
            print(f"  → Risque {risque:<10}    : {n:>10,}")
        print(f"  Score moyen IA           : {df_credits['score_credit_ia'].mean():>10.0f}/850")

    print(f"\n📁 Fichiers générés :")
    print(f"  Modèles  → {MODELS_DIR}/")
    print(f"  Graphiques → {PLOTS_DIR}/")
    print("\n✅ Modèles IA prêts — on peut passer à FastAPI !\n")


# ════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "═"*55)
    print("   VOICEBANK ANALYTICS — Pipeline IA")
    print("   Auteur : Nguebou Temgoua Rayan")
    print("═"*55)

    # ── Chargement des données
    print("\n📂 Chargement des données...")
    df_transactions = charger_depuis_postgres("transactions")
    df_credits      = charger_depuis_postgres("credits")

    # ── Modèle 1 : Détection de fraude
    detecteur = DetecteurFraude()
    df_transactions_scored, alertes = detecteur.executer(df_transactions)

    # ── Modèle 2 : Scoring de crédit
    scorer = ScoringCredit()
    df_credits_scored = scorer.executer(df_credits)

    # ── Rapport final
    rapport_final(df_transactions_scored, df_credits_scored, alertes)
