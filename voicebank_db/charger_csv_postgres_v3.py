# VOICEBANK ANALYTICS - Chargement CSV -> PostgreSQL v3
# Auteur : Nguebou Temgoua Rayan
# Corrections : doublons id_credit, contraintes FK DO $$, colonnes filtrées

import pandas as pd
from sqlalchemy import create_engine, text
from tqdm import tqdm
import os, time

# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────
DB_URL     = "postgresql://voicebank_user:voicebank2024@localhost:5432/voicebank_db"
CSV_DIR    = "../output_voicebank"
CHUNK_SIZE = 5_000      # reduit pour eviter les timeouts

# Ordre de chargement important (cles etrangeres)
FICHIERS = [
    ("clients",      "clients.csv"),
    ("credits",      "credits.csv"),
    ("transactions", "transactions.csv"),
]

# Colonnes autorisees par table
COLONNES_VALIDES = {
    "clients": [
        "id_client", "numero_compte", "nom", "prenom", "sexe", "age",
        "date_naissance", "nationalite", "pays_residence", "est_diaspora",
        "devise_residence", "telephone", "email", "profession", "statut_civil",
        "niveau_education", "banque", "ville_compte", "agence", "type_compte",
        "date_ouverture", "statut_compte", "solde_fcfa", "score_risque",
        "a_fait_defaut_avant", "a_credit_immobilier", "a_credit_personnel",
    ],
    "transactions": [
        "id_transaction", "id_client", "nom_client", "pays_residence",
        "est_diaspora", "banque", "agence", "ville", "type_transaction",
        "categorie_depense", "montant_fcfa", "devise_origine",
        "montant_devise_orig", "canal", "statut", "est_frauduleuse",
        "est_internationale", "date_transaction", "heure_transaction",
        "solde_avant_fcfa", "solde_apres_fcfa",
    ],
    "credits": [
        "id_credit", "id_client", "nom_client", "pays_residence", "est_diaspora",
        "banque", "ville", "type_credit", "objet_credit", "montant_fcfa",
        "taux_interet_pct", "duree_mois", "mensualite_fcfa", "revenu_annuel_fcfa",
        "score_credit", "score_risque_client", "garantie", "statut_credit",
        "date_debut", "date_fin_prevue",
    ],
}


# ─────────────────────────────────────────
# CONNEXION
# ─────────────────────────────────────────
def connecter():
    print("\n  Connexion a PostgreSQL...")
    for tentative in range(1, 6):
        try:
            engine = create_engine(DB_URL, echo=False)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("  OK Connecte a voicebank_db")
            return engine
        except Exception as e:
            print(f"  Tentative {tentative}/5 - attente 3s... ({e})")
            time.sleep(3)
    raise ConnectionError("Impossible de se connecter. Docker tourne-t-il ?")


# ─────────────────────────────────────────
# DESACTIVER CONTRAINTES FK
# ─────────────────────────────────────────
def desactiver_contraintes(engine):
    with engine.connect() as conn:
        conn.execute(text("SET session_replication_role = replica;"))
        conn.commit()
    print("  OK Contraintes FK desactivees")


# ─────────────────────────────────────────
# REACTIVER CONTRAINTES FK - syntaxe DO $$ (PostgreSQL compatible)
# ─────────────────────────────────────────
def reactiver_contraintes(engine):
    with engine.connect() as conn:

        conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'transactions_id_client_fkey'
                  AND table_schema = 'voicebank'
            ) THEN
                ALTER TABLE voicebank.transactions
                ADD CONSTRAINT transactions_id_client_fkey
                FOREIGN KEY (id_client)
                REFERENCES voicebank.clients(id_client)
                ON DELETE SET NULL;
            END IF;
        END $$;
        """))

        conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'credits_id_client_fkey'
                  AND table_schema = 'voicebank'
            ) THEN
                ALTER TABLE voicebank.credits
                ADD CONSTRAINT credits_id_client_fkey
                FOREIGN KEY (id_client)
                REFERENCES voicebank.clients(id_client)
                ON DELETE SET NULL;
            END IF;
        END $$;
        """))

        conn.execute(text("SET session_replication_role = DEFAULT;"))
        conn.commit()

    print("  OK Contraintes FK reactivees")


# ─────────────────────────────────────────
# CHARGEMENT D'UNE TABLE
# ─────────────────────────────────────────
def charger_table(engine, nom_table, fichier_csv):
    chemin = os.path.join(CSV_DIR, fichier_csv)

    if not os.path.exists(chemin):
        print(f"  ATTENTION Fichier introuvable : {chemin}")
        return 0

    print(f"\n  -> Chargement {nom_table}...")
    nb_lignes = sum(1 for _ in open(chemin, encoding="utf-8-sig")) - 1
    print(f"     {nb_lignes:,} lignes a inserer")

    with engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE voicebank.{nom_table} CASCADE"))
        conn.commit()
        print(f"     Table voicebank.{nom_table} videe OK")

    colonnes_valides = COLONNES_VALIDES.get(nom_table, [])
    total_insere  = 0
    total_ignores = 0
    ids_vus       = set()

    reader = pd.read_csv(
        chemin,
        chunksize=CHUNK_SIZE,
        encoding="utf-8-sig",
        low_memory=False,
    )

    with tqdm(total=nb_lignes, desc=f"  {nom_table}", ncols=70, unit="lignes") as pbar:
        for chunk in reader:

            # Normaliser les noms de colonnes
            chunk.columns = [c.lower().strip() for c in chunk.columns]

            # ── Corrections specifiques par table ──

            if nom_table == "transactions":
                # Generer id_transaction si absent ou null
                if "id_transaction" not in chunk.columns:
                    chunk.insert(0, "id_transaction",
                        [f"TXN-{str(total_insere + i + 1).zfill(8)}"
                         for i in range(len(chunk))])
                else:
                    mask_null = chunk["id_transaction"].isna()
                    if mask_null.sum() > 0:
                        chunk.loc[mask_null, "id_transaction"] = [
                            f"TXN-{str(total_insere + i + 1).zfill(8)}"
                            for i in range(mask_null.sum())
                        ]

            if nom_table == "credits":
                # Supprimer doublons id_credit
                if "id_credit" in chunk.columns:
                    avant = len(chunk)
                    chunk = chunk[~chunk["id_credit"].isin(ids_vus)]
                    chunk = chunk.drop_duplicates(subset=["id_credit"])
                    ids_vus.update(chunk["id_credit"].tolist())
                    ignores = avant - len(chunk)
                    if ignores > 0:
                        total_ignores += ignores

            # Garder uniquement les colonnes valides
            if colonnes_valides:
                cols_presentes = [c for c in colonnes_valides if c in chunk.columns]
                chunk = chunk[cols_presentes]

            # Remplacer NaN par None
            chunk = chunk.where(pd.notna(chunk), None)

            if len(chunk) == 0:
                pbar.update(CHUNK_SIZE)
                continue

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
                total_ignores += len(chunk)
                pbar.update(len(chunk))
                print(f"\n  ERREUR chunk ignore : {str(e)[:120]}")

    print(f"  OK {total_insere:,} lignes inserees dans voicebank.{nom_table}")
    if total_ignores > 0:
        print(f"  ATTENTION {total_ignores:,} lignes ignorees (doublons ou erreurs)")
    return total_insere


# ─────────────────────────────────────────
# VERIFICATION FINALE
# ─────────────────────────────────────────
def verifier(engine):
    print("\n" + "="*50)
    print("  VERIFICATION FINALE")
    print("="*50)
    requetes = {
        "clients"           : "SELECT COUNT(*) FROM voicebank.clients",
        "transactions"      : "SELECT COUNT(*) FROM voicebank.transactions",
        "credits"           : "SELECT COUNT(*) FROM voicebank.credits",
        "fraudes"           : "SELECT COUNT(*) FROM voicebank.transactions WHERE est_frauduleuse = 'Oui'",
        "diaspora"          : "SELECT COUNT(*) FROM voicebank.clients WHERE est_diaspora = 'Oui'",
        "credits en defaut" : "SELECT COUNT(*) FROM voicebank.credits WHERE statut_credit = 'Defaut'",
    }
    resultats = {}
    with engine.connect() as conn:
        for label, sql in requetes.items():
            val = conn.execute(text(sql)).scalar()
            resultats[label] = val
            status = "OK" if val and val > 0 else "VIDE"
            print(f"  {status}  {label:<22} : {val:>10,}")

    print()
    ok_clients = resultats.get("clients", 0) >= 45_000
    ok_txn     = resultats.get("transactions", 0) >= 1_000_000
    ok_credits = resultats.get("credits", 0) >= 19_000

    print(f"  {'OK' if ok_clients else 'ECHEC'} Objectif clients      : >= 45 000")
    print(f"  {'OK' if ok_txn     else 'ECHEC'} Objectif transactions : >= 1 000 000")
    print(f"  {'OK' if ok_credits else 'ECHEC'} Objectif credits      : >= 19 000")

    if ok_clients and ok_txn and ok_credits:
        print("\n  BASE DE DONNEES COMPLETE - pret pour les modeles IA !\n")
    else:
        print("\n  ATTENTION : certains objectifs non atteints\n")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*50)
    print("   VOICEBANK - Chargement CSV -> PostgreSQL v3")
    print("   Auteur : Nguebou Temgoua Rayan")
    print("="*50)

    input("\nATTENTION : Ferme Talend, Excel et Power BI !\n"
          "Appuie sur Entree quand c'est fait...")

    engine = connecter()
    desactiver_contraintes(engine)

    for table, fichier in FICHIERS:
        charger_table(engine, table, fichier)

    reactiver_contraintes(engine)
    verifier(engine)
