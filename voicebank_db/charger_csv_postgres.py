"""
╔══════════════════════════════════════════════════════════╗
║   VOICEBANK ANALYTICS — Chargement CSV → PostgreSQL      ║
║   Auteur : Nguebou Temgoua Rayan                         ║
║   À exécuter APRÈS : docker compose up -d                ║
╚══════════════════════════════════════════════════════════╝

Usage :
    pip install psycopg2-binary pandas sqlalchemy tqdm
    python charger_csv_postgres.py
"""

import pandas as pd
from sqlalchemy import create_engine, text
from tqdm import tqdm
import os
import time

# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────
DB_URL     = "postgresql://voicebank_user:voicebank2024@localhost:5432/voicebank_db"
CSV_DIR    = "../output_voicebank"          # dossier contenant tes 3 CSV
CHUNK_SIZE = 10_000                        # lignes insérées par lot

FICHIERS = {
    "clients"     : "clients.csv",
    "transactions": "transactions.csv",
    "credits"     : "credits.csv",
}


def connecter():
    """Crée et teste la connexion à PostgreSQL."""
    print("\n  Connexion à PostgreSQL...")
    for tentative in range(1, 6):
        try:
            engine = create_engine(DB_URL, echo=False)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"  ✓ Connecté à voicebank_db")
            return engine
        except Exception as e:
            print(f"  ⚠️  Tentative {tentative}/5 échouée — attente 3s... ({e})")
            time.sleep(3)
    raise ConnectionError("❌ Impossible de se connecter à PostgreSQL. Vérifie que Docker tourne.")


def charger_table(engine, nom_table, fichier_csv):
    """Charge un CSV dans la table PostgreSQL correspondante par chunks."""
    chemin = os.path.join(CSV_DIR, fichier_csv)

    if not os.path.exists(chemin):
        print(f"  ⚠️  Fichier introuvable : {chemin} — ignoré")
        return 0

    print(f"\n  → Chargement {nom_table} depuis {fichier_csv}...")

    # Compter les lignes pour la barre de progression
    nb_lignes = sum(1 for _ in open(chemin, encoding="utf-8")) - 1
    print(f"     {nb_lignes:,} lignes à insérer")

    # Vider la table avant insertion (evite les doublons)
    with engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE voicebank.{nom_table} CASCADE"))
        conn.commit()
        print(f"     Table voicebank.{nom_table} vidée")

    # Insertion par chunks
    total_insere = 0
    reader = pd.read_csv(
        chemin,
        chunksize=CHUNK_SIZE,
        encoding="utf-8-sig",
        low_memory=False
    )

    with tqdm(total=nb_lignes, desc=f"  {nom_table}", ncols=70, unit="lignes") as pbar:
        for chunk in reader:
            # Nettoyer les noms de colonnes
            chunk.columns = [c.lower().strip() for c in chunk.columns]

            # Gérer les valeurs manquantes
            chunk = chunk.where(pd.notna(chunk), None)

            try:
                chunk.to_sql(
                    name=nom_table,
                    schema="voicebank",
                    con=engine,
                    if_exists="append",
                    index=False,
                    method="multi",
                )
                total_insere += len(chunk)
                pbar.update(len(chunk))
            except Exception as e:
                print(f"\n  ⚠️  Erreur sur un chunk : {e}")
                continue

    print(f"  ✓  {total_insere:,} lignes insérées dans voicebank.{nom_table}")
    return total_insere


def verifier_chargement(engine):
    """Vérifie les comptages après chargement."""
    print("\n" + "═"*55)
    print("  VÉRIFICATION DU CHARGEMENT")
    print("═"*55)

    requetes = {
        "clients"     : "SELECT COUNT(*) FROM voicebank.clients",
        "transactions": "SELECT COUNT(*) FROM voicebank.transactions",
        "credits"     : "SELECT COUNT(*) FROM voicebank.credits",
        "fraudes"     : "SELECT COUNT(*) FROM voicebank.transactions WHERE est_frauduleuse = 'Oui'",
        "diaspora"    : "SELECT COUNT(*) FROM voicebank.clients WHERE est_diaspora = 'Oui'",
    }

    with engine.connect() as conn:
        for label, sql in requetes.items():
            result = conn.execute(text(sql)).scalar()
            print(f"  {label:<20} : {result:>10,}")

    print("\n  Test des vues :")
    vues = ["v_clients_par_banque", "v_transactions_mensuelles",
            "v_portefeuille_credit", "v_dashboard_global"]

    with engine.connect() as conn:
        for vue in vues:
            try:
                result = conn.execute(text(f"SELECT COUNT(*) FROM voicebank.{vue}")).scalar()
                print(f"  {vue:<35} : ✓ ({result} lignes)")
            except Exception as e:
                print(f"  {vue:<35} : ✗ {e}")

    print("\n✅ Base de données VoiceBank prête !")
    print("   pgAdmin disponible sur : http://localhost:5050")
    print("   Login : rayan@voicebank.cm / voicebank2024\n")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "═"*55)
    print("   VOICEBANK — Chargement CSV → PostgreSQL")
    print("   Auteur : Nguebou Temgoua Rayan")
    print("═"*55)

    engine = connecter()

    for table, fichier in FICHIERS.items():
        charger_table(engine, table, fichier)

    verifier_chargement(engine)
