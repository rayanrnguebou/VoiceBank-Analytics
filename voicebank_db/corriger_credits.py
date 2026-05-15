# VOICEBANK - Correction credits.csv
# Auteur : Nguebou Temgoua Rayan
# Probleme : 2512 doublons sur id_credit dans le CSV
# Solution : regenerer des id_credit uniques pour tout le fichier

import pandas as pd
import os

CSV_DIR = "../output_voicebank"
chemin  = os.path.join(CSV_DIR, "credits.csv")

print("\n  Chargement credits.csv...")
df = pd.read_csv(chemin, encoding="utf-8-sig", low_memory=False)
print(f"  Lignes initiales     : {len(df):,}")

# Verifier les doublons
if "id_credit" in df.columns:
    doublons = df.duplicated(subset=["id_credit"]).sum()
    print(f"  Doublons detectes    : {doublons:,}")
else:
    print("  Colonne id_credit absente - elle sera creee")

# Regenerer des id_credit 100% uniques pour toutes les lignes
df["id_credit"] = [f"CRD-{str(i+1).zfill(7)}" for i in range(len(df))]

# Verifier qu'il n'y a plus de doublons
doublons_apres = df.duplicated(subset=["id_credit"]).sum()
print(f"  Doublons apres fix   : {doublons_apres}")
print(f"  Lignes finales       : {len(df):,}")

# Sauvegarder
df.to_csv(chemin, index=False, encoding="utf-8-sig")
print(f"\n  OK credits.csv corrige et sauvegarde !")
print(f"  -> Relance maintenant : python charger_csv_postgres_v3.py\n")
