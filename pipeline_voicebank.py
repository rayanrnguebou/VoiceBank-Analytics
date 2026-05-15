"""
╔══════════════════════════════════════════════════════════════╗
║        VOICEBANK ANALYTICS — Pipeline Principal              ║
║        Auteur : Nguebou Temgoua Rayan                        ║
║        Description : Traitement Kaggle + Génération +        ║
║                      Fusion → Dataset Bancaire Camerounais   ║
╚══════════════════════════════════════════════════════════════╝

INSTRUCTIONS :
  1. Place ce script dans le même dossier que tes fichiers Kaggle
  2. Installe les dépendances : pip install pandas numpy faker tqdm
  3. Lance : python pipeline_voicebank.py
  4. Les fichiers finaux seront dans : ./output_voicebank/
"""

import pandas as pd
import numpy as np
import random
import os
import warnings
from datetime import datetime, timedelta
from tqdm import tqdm

warnings.filterwarnings("ignore")
random.seed(42)
np.random.seed(42)

# ════════════════════════════════════════════════════════
# CONFIGURATION — MODIFIE ICI LES CHEMINS SI NÉCESSAIRE
# ════════════════════════════════════════════════════════

CONFIG = {
    # Chemins vers tes fichiers Kaggle téléchargés
    "fraud_train"   : "fraudTrain.csv",         # Credit Card Fraud Detection
    "bank_marketing": "bank-full.csv",           # Bank Marketing (essaie aussi "bank.csv")
    "loan_default_1": "loan_default.csv",        # Loan Default 1 (renomme ton fichier)
    "loan_default_2": "credit_scoring.csv",      # Loan Default 2 (renomme ton fichier)

    # Objectifs volumétriques
    "nb_clients_cibles"     : 45_000,
    "nb_transactions_cibles": 1_000_000,
    "nb_credits_cibles"     : 20_000,

    # Dossier de sortie
    "output_dir": "output_voicebank",
}

os.makedirs(CONFIG["output_dir"], exist_ok=True)


# ════════════════════════════════════════════════════════
# DONNÉES DE RÉFÉRENCE CAMEROUNAISES
# ════════════════════════════════════════════════════════

BANQUES = [
    "Afriland First Bank", "UBA Cameroun", "SCB Cameroun",
    "Ecobank Cameroun", "BICEC", "CCA Bank", "BGFIBank Cameroun",
    "Société Générale Cameroun", "Atlantic Business International",
    "NSIA Banque Cameroun",
]

AGENCES = {
    "Douala"     : ["Akwa", "Bonanjo", "Deido", "Bonapriso", "Bassa", "Bonaberi", "Makepe"],
    "Yaoundé"    : ["Centre Ville", "Bastos", "Mvan", "Nlongkak", "Biyem-Assi", "Essos"],
    "Bafoussam"  : ["Centre", "Tamdja", "Djeleng", "Banengo"],
    "Garoua"     : ["Centre", "Marché", "Plateau", "Roumdé"],
    "Maroua"     : ["Centre", "Domayo", "Kakataré"],
    "Bertoua"    : ["Centre", "Mokolo", "Haoussa"],
    "Ebolowa"    : ["Centre", "Angalé"],
    "Limbe"      : ["Down Beach", "Mile 4", "Bota"],
    "Kribi"      : ["Centre", "Grand Batanga", "Mpangou"],
    "Ngaoundéré" : ["Centre", "Marché", "Dang"],
    "Buea"       : ["Molyko", "Clerks Quarter", "Mile 17"],
    "Bamenda"    : ["Commercial Avenue", "Up Station", "Nkwen"],
    "Edéa"       : ["Centre", "Dizangué"],
    "Kumba"      : ["Centre", "Fiango"],
}
VILLES = list(AGENCES.keys())

PAYS_RESIDENCE = {
    "Cameroun"      : {"poids": 55, "devise": "FCFA", "indicatif": "+237"},
    "France"        : {"poids": 12, "devise": "EUR",  "indicatif": "+33"},
    "États-Unis"    : {"poids":  5, "devise": "USD",  "indicatif": "+1"},
    "Canada"        : {"poids":  4, "devise": "CAD",  "indicatif": "+1"},
    "Belgique"      : {"poids":  3, "devise": "EUR",  "indicatif": "+32"},
    "Royaume-Uni"   : {"poids":  3, "devise": "GBP",  "indicatif": "+44"},
    "Suisse"        : {"poids":  2, "devise": "CHF",  "indicatif": "+41"},
    "Gabon"         : {"poids":  2, "devise": "FCFA", "indicatif": "+241"},
    "Côte d'Ivoire" : {"poids":  2, "devise": "FCFA", "indicatif": "+225"},
    "Nigeria"       : {"poids":  2, "devise": "NGN",  "indicatif": "+234"},
    "Allemagne"     : {"poids":  2, "devise": "EUR",  "indicatif": "+49"},
    "Espagne"       : {"poids":  1, "devise": "EUR",  "indicatif": "+34"},
    "Italie"        : {"poids":  1, "devise": "EUR",  "indicatif": "+39"},
    "Chine"         : {"poids":  1, "devise": "CNY",  "indicatif": "+86"},
    "Afrique du Sud": {"poids":  1, "devise": "ZAR",  "indicatif": "+27"},
    "Maroc"         : {"poids":  1, "devise": "MAD",  "indicatif": "+212"},
    "Dubaï (EAU)"   : {"poids":  1, "devise": "AED",  "indicatif": "+971"},
    "Sénégal"       : {"poids":  1, "devise": "FCFA", "indicatif": "+221"},
}

TAUX_FCFA = {
    "FCFA": 1, "EUR": 655.96, "USD": 610.50, "GBP": 780.00,
    "CHF": 680.00, "CAD": 450.00, "CNY": 85.00,
    "NGN": 0.40, "ZAR": 33.00, "MAD": 61.00, "AED": 166.00,
}

PROFESSIONS_MAP = {
    # Anglais → Français camerounais
    "admin."         : "Administrateur(trice)",
    "blue-collar"    : "Ouvrier(ère)",
    "entrepreneur"   : "Entrepreneur(e)",
    "housemaid"      : "Employé(e) de maison",
    "management"     : "Cadre dirigeant(e)",
    "retired"        : "Retraité(e)",
    "self-employed"  : "Travailleur(se) indépendant(e)",
    "services"       : "Agent de service",
    "student"        : "Étudiant(e)",
    "technician"     : "Technicien(ne)",
    "unemployed"     : "Sans emploi",
    "unknown"        : "Non précisé",
}

STATUT_CIVIL_MAP = {
    "married"  : "Marié(e)",
    "single"   : "Célibataire",
    "divorced" : "Divorcé(e)",
}

EDUCATION_MAP = {
    "primary"   : "Primaire",
    "secondary" : "Secondaire",
    "tertiary"  : "Supérieur",
    "unknown"   : "Non précisé",
}

CATEGORIES_DEPENSES_MAP = {
    "grocery_pos"        : "Supermarché",
    "gas_transport"      : "Carburant / Transport",
    "home"               : "Maison / Équipement",
    "shopping_net"       : "Achat en ligne",
    "shopping_pos"       : "Commerce local",
    "entertainment"      : "Loisirs / Divertissement",
    "food_dining"        : "Restauration",
    "personal_care"      : "Soins personnels",
    "health_fitness"     : "Santé / Sport",
    "travel"             : "Voyage",
    "kids_pets"          : "Enfants / Animaux",
    "misc_net"           : "Divers (en ligne)",
    "misc_pos"           : "Divers (commerce)",
}

PRENOMS_H = [
    "Jean", "Paul", "Pierre", "Michel", "André", "Emmanuel", "François",
    "Patrick", "Claude", "Henri", "Serge", "Bruno", "Alain", "Eric",
    "Christophe", "Joseph", "Daniel", "Samuel", "David", "Kevin",
    "Lionel", "Boris", "Cédric", "Thierry", "Rodrigue", "Hervé",
    "Guy", "Apollinaire", "Bertrand", "Gérard", "Justin", "Arnaud",
    "Hamadou", "Moussa", "Aliou", "Bello", "Ibrahim", "Adamou",
]

PRENOMS_F = [
    "Marie", "Jeanne", "Hélène", "Christine", "Sophie", "Anne",
    "Cécile", "Sandrine", "Valérie", "Nadège", "Carole", "Estelle",
    "Isabelle", "Florence", "Véronique", "Pauline", "Laure", "Nathalie",
    "Yvonne", "Chantal", "Béatrice", "Régine", "Pascale", "Solange",
    "Aïcha", "Fanta", "Mariama", "Aminata",
]

NOMS = [
    "Nkoulou", "Mbarga", "Tchamba", "Fomba", "Nguele", "Mendo",
    "Atangana", "Tsimi", "Mvondo", "Ngono", "Abena", "Fouda",
    "Essomba", "Ndjock", "Nkoa", "Owona", "Engamba", "Biloa",
    "Nganou", "Kamga", "Talla", "Nkuete", "Feudjio", "Wouaffo",
    "Djomo", "Nguebou", "Temgoua", "Fopa", "Kuete", "Pokam",
    "Simo", "Tchinda", "Hamadou", "Manga", "Eloundou", "Ondoua",
    "Mekongo", "Bikele", "Nkolo", "Djoumessi", "Njike",
]

TYPES_TRANSACTION = [
    "Virement entrant", "Virement sortant", "Retrait DAB",
    "Dépôt espèces", "Paiement marchand", "Mobile Money (envoi)",
    "Mobile Money (réception)", "Prélèvement automatique",
    "Paiement facture", "Transfert international",
    "Remise chèque", "Paiement en ligne",
]

CANAUX = ["Agence", "DAB", "Mobile Banking", "Internet Banking", "USSD"]

TYPES_CREDIT = [
    "Crédit immobilier", "Crédit automobile", "Crédit à la consommation",
    "Crédit scolaire", "Crédit professionnel", "Découvert autorisé",
    "Microfinancement", "Crédit agricole",
]


# ════════════════════════════════════════════════════════
# UTILITAIRES
# ════════════════════════════════════════════════════════

def choisir_pays():
    pays_liste = list(PAYS_RESIDENCE.keys())
    poids = [PAYS_RESIDENCE[p]["poids"] for p in pays_liste]
    return random.choices(pays_liste, weights=poids, k=1)[0]

def generer_telephone(pays):
    indicatif = PAYS_RESIDENCE[pays]["indicatif"]
    if pays == "Cameroun":
        prefix = random.choice(["650","651","652","670","671","672","680","690","691","699"])
        return f"{indicatif} {prefix} {random.randint(100,999)} {random.randint(100,999)}"
    return f"{indicatif} {random.randint(600000000, 799999999)}"

def date_aleatoire(debut="2015-01-01", fin="2024-12-31"):
    d1 = datetime.strptime(debut, "%Y-%m-%d")
    d2 = datetime.strptime(fin,   "%Y-%m-%d")
    return d1 + timedelta(days=random.randint(0, (d2 - d1).days))

def generer_id_client(i):
    return f"CLI-{str(i).zfill(6)}"

def generer_numero_compte():
    return f"CM{random.randint(10000000000000, 99999999999999)}"

def solde_realiste():
    cat = random.choices(["faible","moyen","élevé","très élevé"], weights=[40,35,20,5])[0]
    if cat == "faible":    return round(random.uniform(5_000, 200_000), 0)
    if cat == "moyen":     return round(random.uniform(200_000, 5_000_000), 0)
    if cat == "élevé":     return round(random.uniform(5_000_000, 50_000_000), 0)
    return round(random.uniform(50_000_000, 500_000_000), 0)

def charger_fichier(chemin, nom):
    """Charge un CSV avec gestion d'erreur propre."""
    if not os.path.exists(chemin):
        print(f"  ⚠️  Fichier introuvable : {chemin} — ignoré")
        return None
    try:
        df = pd.read_csv(chemin, low_memory=False)
        print(f"  ✓  {nom} chargé → {len(df):,} lignes × {len(df.columns)} colonnes")
        print(f"     Colonnes : {list(df.columns)}")
        return df
    except Exception as e:
        print(f"  ✗  Erreur chargement {nom} : {e}")
        return None


# ════════════════════════════════════════════════════════
# ÉTAPE 1 — TRAITEMENT BANK MARKETING DATASET
# ════════════════════════════════════════════════════════

def traiter_bank_marketing(chemin):
    """
    Colonnes originales attendues :
    age, job, marital, education, default, balance,
    housing, loan, contact, day, month, duration,
    campaign, pdays, previous, poutcome, y
    """
    print("\n─── Bank Marketing Dataset ───")
    df = charger_fichier(chemin, "Bank Marketing")
    if df is None:
        return pd.DataFrame()

    # Séparateur peut être ";" selon la version
    if len(df.columns) == 1:
        df = pd.read_csv(chemin, sep=";", low_memory=False)
        print(f"     Re-chargé avec sep=';' → {len(df.columns)} colonnes")

    # ── Colonnes à GARDER et renommer
    colonnes_utiles = {
        "age"       : "age",
        "job"       : "profession_orig",
        "marital"   : "statut_civil_orig",
        "education" : "niveau_education_orig",
        "default"   : "a_fait_defaut_avant",
        "balance"   : "solde_orig",
        "housing"   : "a_credit_immobilier",
        "loan"      : "a_credit_personnel",
    }
    # Garder seulement les colonnes qui existent vraiment
    colonnes_presentes = {k: v for k, v in colonnes_utiles.items() if k in df.columns}
    df = df[list(colonnes_presentes.keys())].rename(columns=colonnes_presentes)

    n = len(df)
    print(f"  → Adaptation camerounaise de {n:,} clients...")

    # ── Traductions
    df["profession"]       = df["profession_orig"].map(PROFESSIONS_MAP).fillna("Non précisé")
    df["statut_civil"]     = df["statut_civil_orig"].map(STATUT_CIVIL_MAP).fillna("Non précisé")
    df["niveau_education"] = df["niveau_education_orig"].map(EDUCATION_MAP).fillna("Non précisé")
    df["a_fait_defaut_avant"] = df["a_fait_defaut_avant"].map({"yes":"Oui","no":"Non"}).fillna("Non")
    df["a_credit_immobilier"] = df["a_credit_immobilier"].map({"yes":"Oui","no":"Non"}).fillna("Non")
    df["a_credit_personnel"]  = df["a_credit_personnel"].map({"yes":"Oui","no":"Non"}).fillna("Non")

    # ── Données camerounaises
    pays_list     = [choisir_pays() for _ in range(n)]
    villes        = [random.choice(VILLES) for _ in range(n)]
    sexes         = [random.choice(["Masculin","Féminin"]) for _ in range(n)]
    prenoms       = [random.choice(PRENOMS_H if s=="Masculin" else PRENOMS_F) for s in sexes]
    noms_fam      = [random.choice(NOMS) for _ in range(n)]

    df["id_client"]        = [generer_id_client(i) for i in range(1, n+1)]
    df["nom"]              = [n.upper() for n in noms_fam]
    df["prenom"]           = prenoms
    df["sexe"]             = sexes
    df["nationalite"]      = "Camerounaise"
    df["pays_residence"]   = pays_list
    df["est_diaspora"]     = ["Oui" if p != "Cameroun" else "Non" for p in pays_list]
    df["devise_residence"] = [PAYS_RESIDENCE[p]["devise"] for p in pays_list]
    df["telephone"]        = [generer_telephone(p) for p in pays_list]
    df["ville_compte"]     = villes
    df["agence"]           = [f"Agence {random.choice(AGENCES[v])} - {v}" for v in villes]
    df["banque"]           = [random.choice(BANQUES) for _ in range(n)]
    df["numero_compte"]    = [generer_numero_compte() for _ in range(n)]
    df["type_compte"]      = [random.choice(["Courant","Épargne","Professionnel","Mobile Money"]) for _ in range(n)]
    df["date_ouverture"]   = [date_aleatoire("2010-01-01","2023-12-31").strftime("%Y-%m-%d") for _ in range(n)]
    df["statut_compte"]    = random.choices(["Actif","Inactif","Suspendu"], weights=[85,10,5], k=n)
    df["score_risque"]     = random.choices(["Faible","Moyen","Élevé"], weights=[60,30,10], k=n)

    # Solde : convertir en FCFA (balance originale en EUR approximativement)
    df["solde_fcfa"] = (df["solde_orig"].abs() * 655.96).round(0).astype(int)
    # Remplacer les soldes aberrants
    df.loc[df["solde_fcfa"] < 1000, "solde_fcfa"] = [solde_realiste() for _ in range((df["solde_fcfa"] < 1000).sum())]

    # Supprimer colonnes originales brutes
    df.drop(columns=["profession_orig","statut_civil_orig","niveau_education_orig","solde_orig"],
            errors="ignore", inplace=True)

    print(f"  ✓  {len(df):,} clients Bank Marketing traités")
    return df


# ════════════════════════════════════════════════════════
# ÉTAPE 2 — TRAITEMENT CREDIT CARD FRAUD DETECTION
# ════════════════════════════════════════════════════════

def traiter_fraud(chemin):
    """
    Colonnes originales attendues :
    trans_date_trans_time, cc_num, merchant, category,
    amt, first, last, gender, street, city, state, zip,
    lat, long, city_pop, job, dob, trans_num, unix_time,
    merch_lat, merch_long, is_fraud
    """
    print("\n─── Credit Card Fraud Dataset ───")
    df = charger_fichier(chemin, "Fraud Detection")
    if df is None:
        return pd.DataFrame()

    # ── Colonnes à GARDER
    colonnes_utiles = {
        "trans_date_trans_time": "date_transaction_orig",
        "category"             : "categorie_orig",
        "amt"                  : "montant_usd",
        "gender"               : "sexe_orig",
        "job"                  : "profession_orig",
        "dob"                  : "date_naissance_orig",
        "is_fraud"             : "est_frauduleuse_orig",
    }
    colonnes_presentes = {k: v for k, v in colonnes_utiles.items() if k in df.columns}
    df = df[list(colonnes_presentes.keys())].rename(columns=colonnes_presentes)

    n = len(df)
    print(f"  → Adaptation de {n:,} transactions...")

    # ── Traductions et conversions
    df["categorie_depense"]  = df["categorie_orig"].map(CATEGORIES_DEPENSES_MAP).fillna("Divers")
    df["est_frauduleuse"]    = df["est_frauduleuse_orig"].map({1:"Oui", 0:"Non"}).fillna("Non")
    df["sexe"]               = df["sexe_orig"].map({"M":"Masculin","F":"Féminin"}).fillna("Non précisé")

    # Conversion USD → FCFA
    df["montant_fcfa"]       = (df["montant_usd"] * 610.50).round(0).astype(int)

    # Dates
    df["date_transaction"]   = pd.to_datetime(df["date_transaction_orig"], errors="coerce")
    df["date_transaction"]   = df["date_transaction"].dt.strftime("%Y-%m-%d")

    # Infos camerounaises
    pays_list  = [choisir_pays() for _ in range(n)]
    villes     = [random.choice(VILLES) for _ in range(n)]
    noms_fam   = [random.choice(NOMS) for _ in range(n)]
    prenoms    = [random.choice(PRENOMS_H if s=="Masculin" else PRENOMS_F) for s in df["sexe"]]

    df["id_client"]          = [generer_id_client(random.randint(1, 45000)) for _ in range(n)]
    df["nom_client"]         = [f"{p} {n.upper()}" for p, n in zip(prenoms, noms_fam)]
    df["pays_residence"]     = pays_list
    df["est_diaspora"]       = ["Oui" if p != "Cameroun" else "Non" for p in pays_list]
    df["ville"]              = villes
    df["banque"]             = [random.choice(BANQUES) for _ in range(n)]
    df["agence"]             = [f"Agence {random.choice(AGENCES[v])} - {v}" for v in villes]
    df["type_transaction"]   = [random.choice(TYPES_TRANSACTION) for _ in range(n)]
    df["canal"]              = random.choices(CANAUX, weights=[20,20,30,20,10], k=n)
    df["statut"]             = ["Suspecte" if f=="Oui" else
                                 random.choices(["Réussie","Échouée"], weights=[90,10])[0]
                                 for f in df["est_frauduleuse"]]
    df["est_internationale"] = ["Oui" if p != "Cameroun" and random.random() > 0.4 else "Non" for p in pays_list]
    df["heure_transaction"]  = [f"{random.randint(6,22):02d}:{random.randint(0,59):02d}" for _ in range(n)]

    # Supprimer colonnes brutes
    df.drop(columns=["date_transaction_orig","categorie_orig","montant_usd",
                      "sexe_orig","profession_orig","date_naissance_orig","est_frauduleuse_orig"],
            errors="ignore", inplace=True)

    print(f"  ✓  {len(df):,} transactions Fraud traitées")
    print(f"     Dont fraudes : {(df['est_frauduleuse']=='Oui').sum():,}")
    return df


# ════════════════════════════════════════════════════════
# ÉTAPE 3 — TRAITEMENT LOAN DEFAULT DATASETS
# ════════════════════════════════════════════════════════

def traiter_loan(chemin, nom="Loan"):
    """
    Colonnes typiques (varient selon le dataset) :
    loan_amount / LoanAmount, loan_status / Status,
    annual_income / Income, credit_score / CreditScore,
    interest_rate, term, purpose, etc.
    """
    print(f"\n─── {nom} ───")
    df = charger_fichier(chemin, nom)
    if df is None:
        return pd.DataFrame()

    # Normaliser les noms de colonnes en minuscules
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    print(f"     Colonnes normalisées : {list(df.columns)}")

    n = len(df)

    # ── Mapping flexible des colonnes (plusieurs noms possibles)
    def trouver_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    col_montant  = trouver_col(df, ["loan_amount","loanamount","amount","principal","montant"])
    col_statut   = trouver_col(df, ["loan_status","status","default","is_default","target"])
    col_taux     = trouver_col(df, ["interest_rate","rate","int_rate","taux"])
    col_duree    = trouver_col(df, ["term","duration","tenure","duree"])
    col_revenu   = trouver_col(df, ["annual_income","income","revenu","salary","annual_inc"])
    col_score    = trouver_col(df, ["credit_score","creditscore","fico","score"])
    col_objet    = trouver_col(df, ["purpose","loan_purpose","objet","motif"])

    result = pd.DataFrame()
    result["id_credit"]    = [f"CRD-{str(i).zfill(7)}" for i in range(1, n+1)]

    # Montant → FCFA
    if col_montant:
        result["montant_fcfa"] = (pd.to_numeric(df[col_montant], errors="coerce").fillna(500000) * 610.50).round(0).astype(int)
    else:
        result["montant_fcfa"] = [round(random.uniform(500_000, 50_000_000), 0) for _ in range(n)]

    # Statut → FR
    if col_statut:
        statut_map = {
            "fully paid"    : "Remboursé",   "current"       : "En cours",
            "default"       : "Défaut",       "charged off"   : "Défaut",
            "late"          : "En retard",    "in grace period": "En retard",
            0: "En cours", 1: "Défaut",
            "0": "En cours", "1": "Défaut",
        }
        result["statut_credit"] = df[col_statut].map(statut_map).fillna("En cours")
    else:
        result["statut_credit"] = random.choices(
            ["En cours","Remboursé","En retard","Défaut"],
            weights=[40, 30, 15, 15], k=n
        )

    # Taux
    if col_taux:
        result["taux_interet_pct"] = pd.to_numeric(df[col_taux], errors="coerce").fillna(12.0).round(2)
    else:
        result["taux_interet_pct"] = [round(random.uniform(8.5, 22.0), 2) for _ in range(n)]

    # Durée
    if col_duree:
        val = pd.to_numeric(df[col_duree], errors="coerce").fillna(24)
        result["duree_mois"] = val.astype(int)
    else:
        result["duree_mois"] = random.choices([6,12,24,36,48,60,84,120], k=n)

    # Revenu
    if col_revenu:
        result["revenu_annuel_fcfa"] = (pd.to_numeric(df[col_revenu], errors="coerce").fillna(3000000) * 610.50).round(0).astype(int)
    else:
        result["revenu_annuel_fcfa"] = [round(random.uniform(1_000_000, 30_000_000), 0) for _ in range(n)]

    # Score crédit
    if col_score:
        result["score_credit"] = pd.to_numeric(df[col_score], errors="coerce").fillna(600).astype(int)
    else:
        result["score_credit"] = [random.randint(300, 850) for _ in range(n)]

    # Objet
    if col_objet:
        objet_map = {
            "debt_consolidation": "Consolidation de dettes",
            "credit_card"       : "Remboursement carte crédit",
            "home_improvement"  : "Rénovation immobilière",
            "other"             : "Autre",
            "major_purchase"    : "Achat important",
            "small_business"    : "Petite entreprise",
            "car"               : "Achat véhicule",
            "medical"           : "Frais médicaux",
            "moving"            : "Déménagement",
            "vacation"          : "Voyage",
            "house"             : "Achat immobilier",
            "wedding"           : "Mariage",
        }
        result["objet_credit"] = df[col_objet].map(objet_map).fillna("Non précisé")
    else:
        result["objet_credit"] = [random.choice(TYPES_CREDIT) for _ in range(n)]

    # Données camerounaises
    pays_list = [choisir_pays() for _ in range(n)]
    villes    = [random.choice(VILLES) for _ in range(n)]

    result["id_client"]        = [generer_id_client(random.randint(1, 45000)) for _ in range(n)]
    result["banque"]           = [random.choice(BANQUES) for _ in range(n)]
    result["ville"]            = villes
    result["pays_residence"]   = pays_list
    result["est_diaspora"]     = ["Oui" if p != "Cameroun" else "Non" for p in pays_list]
    result["type_credit"]      = [random.choice(TYPES_CREDIT) for _ in range(n)]
    result["garantie"]         = random.choices(
        ["Hypothèque","Nantissement","Caution personnelle","Sans garantie"],
        weights=[30,20,30,20], k=n
    )
    result["date_debut"]       = [date_aleatoire("2018-01-01","2024-01-01").strftime("%Y-%m-%d") for _ in range(n)]
    result["mensualite_fcfa"]  = (
        result["montant_fcfa"] * (result["taux_interet_pct"]/100/12) /
        (1 - (1 + result["taux_interet_pct"]/100/12) ** (-result["duree_mois"]))
    ).round(0).astype(int)

    print(f"  ✓  {len(result):,} crédits {nom} traités")
    return result


# ════════════════════════════════════════════════════════
# ÉTAPE 4 — COMPLÉTER AVEC DES DONNÉES GÉNÉRÉES
# ════════════════════════════════════════════════════════

def generer_clients_supplementaires(existants, cible=45_000):
    manque = max(0, cible - len(existants))
    if manque == 0:
        print(f"\n  ✓  Objectif clients atteint ({len(existants):,})")
        return existants

    print(f"\n  → Génération de {manque:,} clients supplémentaires...")
    extras = []
    for i in tqdm(range(manque), desc="  Clients", ncols=70):
        sexe   = random.choice(["Masculin","Féminin"])
        prenom = random.choice(PRENOMS_H if sexe=="Masculin" else PRENOMS_F)
        nom    = random.choice(NOMS)
        pays   = choisir_pays()
        ville  = random.choice(VILLES)

        extras.append({
            "id_client"       : generer_id_client(len(existants) + i + 1),
            "nom"             : nom.upper(),
            "prenom"          : prenom,
            "sexe"            : sexe,
            "age"             : random.randint(18, 70),
            "nationalite"     : "Camerounaise",
            "pays_residence"  : pays,
            "est_diaspora"    : "Oui" if pays != "Cameroun" else "Non",
            "devise_residence": PAYS_RESIDENCE[pays]["devise"],
            "telephone"       : generer_telephone(pays),
            "profession"      : random.choice(list(PROFESSIONS_MAP.values())),
            "statut_civil"    : random.choice(["Marié(e)","Célibataire","Divorcé(e)"]),
            "niveau_education": random.choice(["Primaire","Secondaire","Supérieur"]),
            "banque"          : random.choice(BANQUES),
            "ville_compte"    : ville,
            "agence"          : f"Agence {random.choice(AGENCES[ville])} - {ville}",
            "numero_compte"   : generer_numero_compte(),
            "type_compte"     : random.choice(["Courant","Épargne","Professionnel","Mobile Money"]),
            "solde_fcfa"      : solde_realiste(),
            "date_ouverture"  : date_aleatoire("2010-01-01","2023-12-31").strftime("%Y-%m-%d"),
            "statut_compte"   : random.choices(["Actif","Inactif","Suspendu"], weights=[85,10,5])[0],
            "score_risque"    : random.choices(["Faible","Moyen","Élevé"], weights=[60,30,10])[0],
            "a_fait_defaut_avant"  : random.choice(["Non","Non","Non","Oui"]),
            "a_credit_immobilier"  : random.choice(["Non","Non","Oui"]),
            "a_credit_personnel"   : random.choice(["Non","Non","Oui"]),
        })

    df_extra = pd.DataFrame(extras)
    df_final = pd.concat([existants, df_extra], ignore_index=True)
    print(f"  ✓  Total clients : {len(df_final):,}")
    return df_final


def generer_transactions_supplementaires(df_clients, existantes, cible=1_000_000):
    manque = max(0, cible - len(existantes))
    if manque == 0:
        print(f"\n  ✓  Objectif transactions atteint ({len(existantes):,})")
        return existantes

    print(f"\n  → Génération de {manque:,} transactions supplémentaires...")
    ids_clients = df_clients["id_client"].tolist()
    extras = []

    for i in tqdm(range(manque), desc="  Transactions", ncols=70):
        id_cl      = random.choice(ids_clients)
        row_client = df_clients[df_clients["id_client"] == id_cl]
        pays       = row_client["pays_residence"].values[0] if len(row_client) > 0 else choisir_pays()
        ville      = row_client["ville_compte"].values[0] if "ville_compte" in row_client.columns and len(row_client) > 0 else random.choice(VILLES)
        montant    = round(random.uniform(500, 15_000_000), 0)
        devise     = PAYS_RESIDENCE.get(pays, {}).get("devise", "FCFA")
        est_int    = pays != "Cameroun" and random.random() > 0.5

        extras.append({
            "id_transaction"      : f"TXN-{str(len(existantes) + i + 1).zfill(8)}",
            "id_client"           : id_cl,
            "pays_residence"      : pays,
            "est_diaspora"        : "Oui" if pays != "Cameroun" else "Non",
            "ville"               : ville if isinstance(ville, str) else random.choice(VILLES),
            "banque"              : random.choice(BANQUES),
            "type_transaction"    : random.choice(TYPES_TRANSACTION),
            "categorie_depense"   : random.choice(list(CATEGORIES_DEPENSES_MAP.values())),
            "montant_fcfa"        : montant,
            "devise_origine"      : devise,
            "montant_devise_orig" : round(montant / TAUX_FCFA.get(devise, 1), 2),
            "canal"               : random.choices(CANAUX, weights=[20,20,30,20,10])[0],
            "statut"              : random.choices(["Réussie","Échouée","Suspecte"], weights=[88,7,5])[0],
            "est_frauduleuse"     : random.choices(["Non","Oui"], weights=[96,4])[0],
            "est_internationale"  : "Oui" if est_int else "Non",
            "date_transaction"    : date_aleatoire().strftime("%Y-%m-%d"),
            "heure_transaction"   : f"{random.randint(6,22):02d}:{random.randint(0,59):02d}",
        })

    df_extra = pd.DataFrame(extras)
    df_final = pd.concat([existantes, df_extra], ignore_index=True)
    print(f"  ✓  Total transactions : {len(df_final):,}")
    return df_final


def generer_credits_supplementaires(df_clients, existants, cible=20_000):
    manque = max(0, cible - len(existants))
    if manque == 0:
        return existants

    print(f"\n  → Génération de {manque:,} crédits supplémentaires...")
    ids_clients = df_clients["id_client"].tolist()
    extras = []

    for i in tqdm(range(manque), desc="  Crédits", ncols=70):
        id_cl   = random.choice(ids_clients)
        montant = round(random.uniform(100_000, 100_000_000), 0)
        taux    = round(random.uniform(8.5, 22.0), 2)
        duree   = random.choice([6,12,24,36,48,60,84,120])
        pays    = choisir_pays()

        extras.append({
            "id_credit"           : f"CRD-{str(len(existants) + i + 1).zfill(7)}",
            "id_client"           : id_cl,
            "banque"              : random.choice(BANQUES),
            "ville"               : random.choice(VILLES),
            "pays_residence"      : pays,
            "est_diaspora"        : "Oui" if pays != "Cameroun" else "Non",
            "type_credit"         : random.choice(TYPES_CREDIT),
            "objet_credit"        : random.choice(list(CATEGORIES_DEPENSES_MAP.values())),
            "montant_fcfa"        : montant,
            "taux_interet_pct"    : taux,
            "duree_mois"          : duree,
            "mensualite_fcfa"     : round((montant*(taux/100/12))/(1-(1+taux/100/12)**(-duree)), 0),
            "revenu_annuel_fcfa"  : round(random.uniform(1_000_000, 30_000_000), 0),
            "score_credit"        : random.randint(300, 850),
            "statut_credit"       : random.choices(
                ["En cours","Remboursé","En retard","Défaut"],
                weights=[40,30,15,15]
            )[0],
            "garantie"            : random.choices(
                ["Hypothèque","Nantissement","Caution personnelle","Sans garantie"],
                weights=[30,20,30,20]
            )[0],
            "date_debut"          : date_aleatoire("2018-01-01","2024-01-01").strftime("%Y-%m-%d"),
        })

    df_extra = pd.DataFrame(extras)
    df_final = pd.concat([existants, df_extra], ignore_index=True)
    print(f"  ✓  Total crédits : {len(df_final):,}")
    return df_final


# ════════════════════════════════════════════════════════
# ÉTAPE 5 — RAPPORT FINAL
# ════════════════════════════════════════════════════════

def rapport_final(df_clients, df_transactions, df_credits):
    print("\n" + "═"*60)
    print("   RAPPORT FINAL — DATASET VOICEBANK ANALYTICS")
    print("═"*60)

    print(f"\n{'─'*40}")
    print(f" CLIENTS : {len(df_clients):>10,}")
    print(f"{'─'*40}")
    print(f"  Résidents Cameroun    : {(df_clients['est_diaspora']=='Non').sum():>8,}")
    print(f"  Diaspora              : {(df_clients['est_diaspora']=='Oui').sum():>8,}")
    print(f"  Pays représentés      : {df_clients['pays_residence'].nunique():>8,}")
    print(f"\n  Top 5 pays de résidence :")
    for pays, count in df_clients["pays_residence"].value_counts().head(5).items():
        print(f"    {pays:<20} : {count:,}")

    print(f"\n{'─'*40}")
    print(f" TRANSACTIONS : {len(df_transactions):>10,}")
    print(f"{'─'*40}")
    if "est_frauduleuse" in df_transactions.columns:
        fraudes = (df_transactions["est_frauduleuse"]=="Oui").sum()
        print(f"  Frauduleuses          : {fraudes:>8,}  ({fraudes/len(df_transactions)*100:.2f}%)")
    if "est_internationale" in df_transactions.columns:
        intl = (df_transactions["est_internationale"]=="Oui").sum()
        print(f"  Internationales       : {intl:>8,}  ({intl/len(df_transactions)*100:.2f}%)")

    print(f"\n{'─'*40}")
    print(f" CRÉDITS : {len(df_credits):>10,}")
    print(f"{'─'*40}")
    if "statut_credit" in df_credits.columns:
        for statut, count in df_credits["statut_credit"].value_counts().items():
            print(f"  {statut:<22} : {count:,}")

    print(f"\n✅ Fichiers sauvegardés dans : ./{CONFIG['output_dir']}/")
    print(f"   clients.csv       → {len(df_clients):,} lignes")
    print(f"   transactions.csv  → {len(df_transactions):,} lignes")
    print(f"   credits.csv       → {len(df_credits):,} lignes\n")


# ════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "═"*60)
    print("   VOICEBANK ANALYTICS — Pipeline de Données")
    print("   Auteur : Nguebou Temgoua Rayan")
    print("═"*60)

    # ── 1. Traitement des fichiers Kaggle
    print("\n📂 ÉTAPE 1 : Chargement et traitement des fichiers Kaggle\n")
    df_clients_bm  = traiter_bank_marketing(CONFIG["bank_marketing"])
    df_fraud       = traiter_fraud(CONFIG["fraud_train"])
    df_loan1       = traiter_loan(CONFIG["loan_default_1"], "Loan Default 1")
    df_loan2       = traiter_loan(CONFIG["loan_default_2"], "Loan Default 2")

    # ── 2. Fusion clients
    print("\n📂 ÉTAPE 2 : Fusion des datasets clients\n")
    df_clients = df_clients_bm if len(df_clients_bm) > 0 else pd.DataFrame()
    print(f"  Base initiale : {len(df_clients):,} clients (Bank Marketing)")

    # ── 3. Compléter jusqu'à 45 000 clients
    print("\n📂 ÉTAPE 3 : Complétion jusqu'à 45 000 clients\n")
    df_clients = generer_clients_supplementaires(df_clients, CONFIG["nb_clients_cibles"])

    # ── 4. Transactions : Fraud + génération
    print("\n📂 ÉTAPE 4 : Construction du dataset transactions\n")
    df_transactions = df_fraud if len(df_fraud) > 0 else pd.DataFrame()
    print(f"  Base initiale : {len(df_transactions):,} transactions (Fraud Kaggle)")
    df_transactions = generer_transactions_supplementaires(
        df_clients, df_transactions, CONFIG["nb_transactions_cibles"]
    )

    # ── 5. Crédits : Loan1 + Loan2 + génération
    print("\n📂 ÉTAPE 5 : Construction du dataset crédits\n")
    frames_credit = [f for f in [df_loan1, df_loan2] if len(f) > 0]
    df_credits = pd.concat(frames_credit, ignore_index=True) if frames_credit else pd.DataFrame()
    print(f"  Base initiale : {len(df_credits):,} crédits (Loan Kaggle)")
    df_credits = generer_credits_supplementaires(
        df_clients, df_credits, CONFIG["nb_credits_cibles"]
    )

    # ── 6. Export
    print("\n📂 ÉTAPE 6 : Export CSV final\n")
    path_c = os.path.join(CONFIG["output_dir"], "clients.csv")
    path_t = os.path.join(CONFIG["output_dir"], "transactions.csv")
    path_cr= os.path.join(CONFIG["output_dir"], "credits.csv")

    print("  Sauvegarde clients...")
    df_clients.to_csv(path_c, index=False, encoding="utf-8-sig")
    print("  Sauvegarde transactions...")
    df_transactions.to_csv(path_t, index=False, encoding="utf-8-sig")
    print("  Sauvegarde crédits...")
    df_credits.to_csv(path_cr, index=False, encoding="utf-8-sig")

    # ── 7. Rapport
    rapport_final(df_clients, df_transactions, df_credits)
