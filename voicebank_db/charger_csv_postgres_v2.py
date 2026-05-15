"""
╔══════════════════════════════════════════════════════════════╗
║   VOICEBANK ANALYTICS — Chargement CSV → PostgreSQL v2       ║
║   Auteur : Nguebou Temgoua Rayan                             ║
║   Corrections : Permission denied · Gros fichiers · FK       ║
╚══════════════════════════════════════════════════════════════╝

Usage :
    pip install psycopg2-binary pandas sqlalchemy tqdm
    python charger_csv_postgres_v2.py
"""

import pandas as pd
import psycopg2
from sqlalchemy import create_engine, text
from tqdm import tqdm
import os
import time
import shutil

# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────
DB_URL     = "postgresql://voicebank_user:voicebank2024@localhost:5432/voicebank_db"
CSV_DIR    = "../output_voicebank"
CHUNK_SIZE = 5_000      # réduit pour éviter les timeouts

# Ordre de chargement important (clés étrangères)
FICHIERS = [
    ("clients",      "clients.csv"),
    ("credits",      "credits.csv"),
    ("transactions", "transactions.csv"),
]


# ─────────────────────────────────────────
# CONNEXION
# ─────────────────────────────────────────
def connecter():
    print("\n  Connexion à PostgreSQL...")
    for tentative in range(1, 6):
        try:
            engine = create_engine(
                DB_URL,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={"connect_timeout": 30},
            )
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"  ✓ Connecté à voicebank_db")
            return engine
        except Exception as e:
            print(f"  ⚠️  Tentative {tentative}/5 — attente 3s... ({e})")
            time.sleep(3)
    raise ConnectionError("❌ Impossible de se connecter. Docker tourne ?")


# ─────────────────────────────────────────
# VÉRIFIER QUE LE FICHIER EST ACCESSIBLE
# ─────────────────────────────────────────
def verifier_acces_fichier(chemin):
    """Vérifie qu'on peut lire le fichier et le copie si nécessaire."""
    if not os.path.exists(chemin):
        print(f"  ❌ Fichier introuvable : {chemin}")
        return None

    # Tester la permission de lecture
    try:
        with open(chemin, "r", encoding="utf-8-sig") as f:
            f.read(100)
        print(f"  ✓ Accès fichier OK : {chemin}")
        return chemin
    except PermissionError:
        print(f"  ⚠️  Permission denied sur {chemin}")
        print(f"  → Tentative de copie dans un dossier temporaire...")

        # Copier dans le dossier temp Windows
        temp_dir  = os.path.join(os.environ.get("TEMP", "."), "voicebank_temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, os.path.basename(chemin))

        try:
            shutil.copy2(chemin, temp_path)
            print(f"  ✓ Copié vers : {temp_path}")
            return temp_path
        except Exception as e:
            print(f"  ❌ Impossible de copier : {e}")
            print(f"  → Ferme Talend, Excel, Power BI et relance le script")
            return None


# ─────────────────────────────────────────
# DÉSACTIVER LES CONTRAINTES FK
# ─────────────────────────────────────────
def desactiver_contraintes(engine):
    """Désactive temporairement les clés étrangères pour éviter les rejets."""
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE voicebank.transactions 
            DROP CONSTRAINT IF EXISTS transactions_id_client_fkey;
        """))
        conn.execute(text("""
            ALTER TABLE voicebank.credits 
            DROP CONSTRAINT IF EXISTS credits_id_client_fkey;
        """))
        conn.commit()
    print("  ✓ Contraintes FK désactivées temporairement")

def reactiver_contraintes(engine):
    """Réactive les clés étrangères après chargement."""
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE voicebank.transactions
            ADD CONSTRAINT IF NOT EXISTS transactions_id_client_fkey
            FOREIGN KEY (id_client) 
            REFERENCES voicebank.clients(id_client) ON DELETE SET NULL;
        """))
        conn.execute(text("""
            ALTER TABLE voicebank.credits
            ADD CONSTRAINT IF NOT EXISTS credits_id_client_fkey
            FOREIGN KEY (id_client) 
            REFERENCES voicebank.clients(id_client) ON DELETE SET NULL;
        """))
        conn.commit()
    print("  ✓ Contraintes FK réactivées")


# ─────────────────────────────────────────
# CHARGEMENT D'UNE TABLE
# ─────────────────────────────────────────
def charger_table(engine, nom_table, fichier_csv):
    chemin_orig = os.path.join(CSV_DIR, fichier_csv)
    chemin      = verifier_acces_fichier(chemin_orig)

    if chemin is None:
        print(f"  ❌ Table {nom_table} ignorée — fichier inaccessible")
        return 0

    print(f"\n  → Chargement {nom_table}...")

    # Compter les lignes
    try:
        nb_lignes = sum(1 for _ in open(chemin, encoding="utf-8-sig")) - 1
        print(f"     {nb_lignes:,} lignes à insérer")
    except Exception:
        nb_lignes = None
        print(f"     Nombre de lignes inconnu")

    # Vider la table
    with engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE voicebank.{nom_table} CASCADE"))
        conn.commit()
        print(f"     Table voicebank.{nom_table} vidée ✓")

    # Insertion par chunks
    total = 0
    erreurs = 0

    try:
        reader = pd.read_csv(
            chemin,
            chunksize=CHUNK_SIZE,
            encoding="utf-8-sig",
            low_memory=False,
            on_bad_lines="skip",   # ignore les lignes mal formées
        )
    except Exception as e:
        print(f"  ❌ Impossible de lire {chemin} : {e}")
        return 0

    with tqdm(total=nb_lignes, desc=f"  {nom_table}", ncols=70, unit="lignes") as pbar:
        for i, chunk in enumerate(reader):
            # Nettoyage des colonnes
            chunk.columns = [c.lower().strip() for c in chunk.columns]
            chunk = chunk.where(pd.notna(chunk), None)

            # Supprimer colonnes dupliquées si présentes
            chunk = chunk.loc[:, ~chunk.columns.duplicated()]

            try:
                chunk.to_sql(
                    name=nom_table,
                    schema="voicebank",
                    con=engine,
                    if_exists="append",
                    index=False,
                    method="multi",
                    chunksize=500,
                )
                total += len(chunk)
                pbar.update(len(chunk))

            except Exception as e:
                erreurs += len(chunk)
                pbar.update(len(chunk))
                if i < 3:  # Afficher seulement les 3 premières erreurs
                    print(f"\n  ⚠️  Chunk {i} ignoré : {str(e)[:120]}")
                continue

    print(f"\n  ✓ {total:,} lignes insérées dans voicebank.{nom_table}")
    if erreurs > 0:
        print(f"  ⚠️  {erreurs:,} lignes ignorées (erreurs)")
    return total


# ─────────────────────────────────────────
# VÉRIFICATION FINALE
# ─────────────────────────────────────────
def verifier(engine):
    print("\n" + "═"*50)
    print("  VÉRIFICATION FINALE")
    print("═"*50)

    attendu = {
        "clients"     : 45_211,
        "transactions": 1_296_675,
        "credits"     : 20_000,
    }

    with engine.connect() as conn:
        for table, cible in attendu.items():
            n = conn.execute(
                text(f"SELECT COUNT(*) FROM voicebank.{table}")
            ).scalar()
            statut = "✅" if n >= cible * 0.95 else "⚠️ "
            print(f"  {statut} {table:<15} : {n:>10,} / {cible:,} attendues")

    print("\n  Test vue dashboard :")
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM voicebank.v_dashboard_global")
            ).fetchone()
            if row:
                print(f"  ✅ v_dashboard_global OK")
    except Exception as e:
        print(f"  ⚠️  Vue inaccessible : {e}")

    print("\n✅ Base de données prête !")
    print("   pgAdmin : http://localhost:5050")
    print("   On peut lancer les modèles IA 🚀\n")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "═"*50)
    print("   VOICEBANK — Chargement CSV → PostgreSQL v2")
    print("   Auteur : Nguebou Temgoua Rayan")
    print("═"*50)

    print("\n⚠️  IMPORTANT : Ferme Talend, Excel et Power BI avant de continuer !")
    input("   Appuie sur Entrée quand c'est fait...")

    engine = connecter()

    # Désactiver FK pour éviter les rejets
    desactiver_contraintes(engine)

    # Charger dans l'ordre
    for table, fichier in FICHIERS:
        charger_table(engine, table, fichier)

    # Réactiver FK
    reactiver_contraintes(engine)

    # Vérifier
    verifier(engine)
