# VOICEBANK ANALYTICS - API FastAPI avec RAG (auto-apprentissage)
# Auteur : Nguebou Temgoua Rayan
# Nouveautes : systeme RAG - memorise les corrections et s'ameliore seul

import os
import re
import time
import joblib
import tempfile
import shutil
import unicodedata
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional

# Ajoute ffmpeg local au PATH pour Whisper sous Windows
_FFMPEG_BIN = shutil.which("ffmpeg")
if _FFMPEG_BIN:
    print(f"INFO: ffmpeg disponible : {_FFMPEG_BIN}")
else:
    print("WARN: ffmpeg introuvable dans le PATH")

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from google import genai as google_genai
from dotenv import load_dotenv

load_dotenv()

# ════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════

DB_URL      = os.getenv("DATABASE_URL",
              "postgresql://voicebank_user:voicebank2024@localhost:5432/voicebank_db")
GEMINI_KEY  = os.getenv("GEMINI_API_KEY", "")
# MODELS_DIR  = "../voicebank_ia/modeles_sauvegardes"
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "voicebank_ia", "modeles_sauvegardes")
print(f"INFO: Chemin modeles = {MODELS_DIR}")
SEUIL_RAG   = 0.45    # score de similarite minimum pour utiliser une correction

# ════════════════════════════════════════
# INITIALISATION FASTAPI
# ════════════════════════════════════════

app = FastAPI(
    title="VoiceBank Analytics API",
    description="API bancaire vocale avec RAG auto-apprenant - Nguebou Temgoua Rayan",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ════════════════════════════════════════
# BASE DE DONNEES
# ════════════════════════════════════════

engine = create_engine(DB_URL, pool_pre_ping=True, pool_size=5)

def executer_sql(sql: str, params: dict = None):
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        colonnes = list(result.keys())
        lignes   = [dict(zip(colonnes, row)) for row in result.fetchall()]
    return colonnes, lignes

# ════════════════════════════════════════
# MODELES IA
# ════════════════════════════════════════

modeles = {}

def charger_modeles():
    global modeles
    try:
        modeles["isolation_forest"] = joblib.load(f"{MODELS_DIR}/isolation_forest.pkl")
        modeles["scaler_fraude"]    = joblib.load(f"{MODELS_DIR}/scaler_fraude.pkl")
        modeles["encoders_fraude"]  = joblib.load(f"{MODELS_DIR}/encoders_fraude.pkl")
        print("OK Modeles IA charges")
    except Exception as e:
        print(f"ATTENTION Modeles IA non charges : {e}")

charger_modeles()

# ════════════════════════════════════════
# WHISPER via GROQ API (remplace Whisper local)
# ════════════════════════════════════════

GROQ_KEY = os.getenv("GROQ_API_KEY", "")

def transcrire_avec_groq(chemin_audio: str) -> str:
    from groq import Groq
    client_groq = Groq(api_key=GROQ_KEY)
    with open(chemin_audio, "rb") as f:
        result = client_groq.audio.transcriptions.create(
            file=(os.path.basename(chemin_audio), f.read()),
            model="whisper-large-v3",
            language="fr",
        )
    return result.text.strip()

whisper_model = True  # Indique que la transcription est disponible
print("OK Whisper via Groq API configure" if GROQ_KEY else "WARN: GROQ_API_KEY non definie")

# charger_whisper()

# ════════════════════════════════════════
# GEMINI
# ════════════════════════════════════════

gemini_client = None

def init_gemini():
    global gemini_client
    if not GEMINI_KEY:
        print("ATTENTION GEMINI_KEY non definie")
        return
    try:
        gemini_client = google_genai.Client(api_key=GEMINI_KEY)
        print("OK Gemini initialise")
    except Exception as e:
        print(f"ERREUR GEMINI : {e}")

init_gemini()

# ════════════════════════════════════════
# PROMPT SYSTÈME
# ════════════════════════════════════════

SCHEMA_SQL = """
Tu es un expert SQL PostgreSQL pour la base de données bancaire VoiceBank Analytics.
Schema (schema = voicebank) :

TABLE voicebank.clients :
  id_client, nom, prenom, sexe, age, nationalite, pays_residence,
  est_diaspora (Oui/Non), devise_residence, telephone, profession,
  statut_civil, banque, ville_compte, type_compte, solde_fcfa,
  statut_compte (Actif/Inactif/Suspendu), score_risque (Faible/Moyen/Eleve)

TABLE voicebank.transactions :
  id_transaction, id_client, pays_residence, est_diaspora, banque,
  ville, type_transaction, categorie_depense, montant_fcfa,
  devise_origine, canal, statut (Reussie/Echouee/Suspecte),
  est_frauduleuse (Oui/Non), est_internationale (Oui/Non),
  date_transaction, heure_transaction

TABLE voicebank.credits :
  id_credit, id_client, banque, ville, type_credit, montant_fcfa,
  taux_interet_pct, duree_mois, mensualite_fcfa, revenu_annuel_fcfa,
  score_credit, statut_credit (En cours/Remboursé/En retard/Défaut),
  garantie, date_debut

TABLE voicebank.alertes_fraude :
  id_alerte, id_transaction, id_client, score_anomalie,
  niveau_alerte (Faible/Moyen/Eleve/Critique), motif, traitee, date_alerte

VUES : v_dashboard_global, v_clients_par_banque,
       v_transactions_mensuelles, v_portefeuille_credit

VALEURS EXACTES IMPORTANTES (respecte les accents) :
  statut_credit : 'En cours', 'Remboursé', 'En retard', 'Défaut'
  est_diaspora  : 'Oui', 'Non'
  est_frauduleuse : 'Oui', 'Non'
  est_internationale : 'Oui', 'Non'
  score_risque  : 'Faible', 'Moyen', 'Élevé'
  statut_compte : 'Actif', 'Inactif', 'Suspendu'
  niveau_alerte : 'Faible', 'Moyen', 'Élevé', 'Critique'
  nationalite   : toujours 'Camerounaise' (la diaspora se filtre par pays_residence)

REGLES :
- Reponds UNIQUEMENT avec la requete SQL, sans explication ni backticks
- Utilise TOUJOURS le schema voicebank. devant chaque table
- N'ajoute pas de LIMIT sauf si la question demande explicitement un nombre précis (ex: "top 10", "les 5 premiers")
- Pour les agrégations (GROUP BY, COUNT, SUM), pas de LIMIT
- N'utilise jamais DROP, DELETE, UPDATE, INSERT, CREATE, ALTER

EXEMPLES :
Question: "Montre les clients avec un credit en defaut"
SQL: SELECT c.id_client, c.nom, c.prenom, c.banque, cr.type_credit, cr.montant_fcfa, cr.statut_credit FROM voicebank.credits cr JOIN voicebank.clients c ON cr.id_client = c.id_client WHERE cr.statut_credit = 'Défaut';

Question: "Montre les credits rembourses"
SQL: SELECT c.id_client, c.nom, c.prenom, cr.type_credit, cr.montant_fcfa, cr.statut_credit FROM voicebank.credits cr JOIN voicebank.clients c ON cr.id_client = c.id_client WHERE cr.statut_credit = 'Remboursé';

Question: "Montre les credits en retard"
SQL: SELECT c.id_client, c.nom, c.prenom, cr.type_credit, cr.montant_fcfa, cr.statut_credit FROM voicebank.credits cr JOIN voicebank.clients c ON cr.id_client = c.id_client WHERE cr.statut_credit = 'En retard';

Question: "clients diaspora francaise"
SQL: SELECT id_client, nom, prenom, pays_residence, solde_fcfa, banque FROM voicebank.clients WHERE est_diaspora = 'Oui' AND pays_residence = 'France' LIMIT 100;

Question: "credits en defaut"
SQL: SELECT c.id_client, c.nom, c.prenom, c.banque, cr.type_credit, cr.montant_fcfa, cr.statut_credit FROM voicebank.credits cr JOIN voicebank.clients c ON cr.id_client = c.id_client WHERE cr.statut_credit = 'Défaut' LIMIT 100;

Question: "transactions frauduleuses"
SQL: SELECT id_transaction, id_client, banque, montant_fcfa, date_transaction FROM voicebank.transactions WHERE est_frauduleuse = 'Oui' ORDER BY montant_fcfa DESC LIMIT 100;

Question: "top 10 clients solde"
SQL: SELECT id_client, nom, prenom, banque, ville_compte, solde_fcfa FROM voicebank.clients ORDER BY solde_fcfa DESC LIMIT 10;

Question: "nombre clients par banque"
SQL: SELECT banque, COUNT(*) as nb_clients FROM voicebank.clients GROUP BY banque ORDER BY nb_clients DESC;
"""


# ════════════════════════════════════════
# SYSTEME RAG — AUTO-APPRENTISSAGE
# ════════════════════════════════════════

def chercher_correction_rag(question: str) -> tuple:
    """
    Cherche dans logs_corrections si une question similaire existe.
    Retourne (sql_correct, score) ou (None, 0) si rien trouve.
    """
    try:
        _, rows = executer_sql("""
            SELECT
                sql_correct,
                SIMILARITY(LOWER(question), LOWER(:q)) as score
            FROM voicebank.logs_corrections
            WHERE SIMILARITY(LOWER(question), LOWER(:q)) > :seuil
            ORDER BY score DESC
            LIMIT 1
        """, {"q": question, "seuil": SEUIL_RAG})

        if rows:
            sql   = rows[0]["sql_correct"]
            score = float(rows[0]["score"])
            return sql, score
    except Exception as e:
        print(f"  RAG non disponible : {e}")
    return None, 0.0


def incrementer_utilisation(question: str):
    """Incremente le compteur d'utilisation d'une correction."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE voicebank.logs_corrections
                SET utilisee = utilisee + 1, date_modif = NOW()
                WHERE SIMILARITY(LOWER(question), LOWER(:q)) > :seuil
            """), {"q": question, "seuil": SEUIL_RAG})
            conn.commit()
    except Exception:
        pass


def enregistrer_correction_db(question: str, sql_correct: str):
    """Enregistre une nouvelle correction dans la base."""
    with engine.connect() as conn:
        # Verifier si la question existe deja
        result = conn.execute(text("""
            SELECT id FROM voicebank.logs_corrections
            WHERE SIMILARITY(LOWER(question), LOWER(:q)) > 0.85
            LIMIT 1
        """), {"q": question})
        existe = result.fetchone()

        if existe:
            # Mettre a jour
            conn.execute(text("""
                UPDATE voicebank.logs_corrections
                SET sql_correct = :sql, date_modif = NOW()
                WHERE id = :id
            """), {"sql": sql_correct, "id": existe[0]})
        else:
            # Inserer nouvelle correction
            conn.execute(text("""
                INSERT INTO voicebank.logs_corrections (question, sql_correct)
                VALUES (:q, :sql)
            """), {"q": question, "sql": sql_correct})

        conn.commit()


def normaliser_question(question: str) -> str:
    """Nettoie et corrige légèrement une question transcrite."""
    texte = unicodedata.normalize("NFKC", question or "")
    texte = texte.replace("’", "'").replace(" ", " ")
    texte = re.sub(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ'’\.,;:!?%\s-]", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    # Corrections simples de mots fréquemment mal orthographiés
    remplacements = {
        "defaut": "Défaut",
        "eleve": "Élevé",
        "rembourses": "Remboursé",
        "en retard": "En retard",
        "frauduleuses": "frauduleuses",
        "diaspora francaise": "diaspora France",
        "top 10": "top 10",
        "clients par banque": "clients par banque",
        "transactions frauduleuses": "transactions frauduleuses",
    }
    for ancien, nouveau in remplacements.items():
        texte = re.sub(rf"\b{re.escape(ancien)}\b", nouveau, texte, flags=re.IGNORECASE)
    return texte.strip()


def sql_via_regles(question: str) -> Optional[str]:
    """Retourne une requete SQL simple pour les questions les plus courantes."""
    regles = [
        (
            r"clients.*transaction.*suspect",
            """
                SELECT t.id_client, c.nom, c.prenom, c.banque,
                       COUNT(*) AS nb_transactions_suspectes
                FROM voicebank.transactions t
                JOIN voicebank.clients c ON t.id_client = c.id_client
                WHERE t.statut = 'Suspecte' OR t.est_frauduleuse = 'Oui'
                GROUP BY t.id_client, c.nom, c.prenom, c.banque
                ORDER BY nb_transactions_suspectes DESC
                LIMIT 100
            """
        ),
        (
            r"cr[eé]dit.*d[eé]faut|credits? en defaut|credit en defaut",
            """
                SELECT c.id_client, c.nom, c.prenom, c.banque,
                       cr.type_credit, cr.montant_fcfa, cr.statut_credit
                FROM voicebank.credits cr
                JOIN voicebank.clients c ON cr.id_client = c.id_client
                WHERE cr.statut_credit = 'Défaut'
                LIMIT 100
            """
        ),
        (
            r"transactions.*frauduleuses|frauduleuses? transactions",
            """
                SELECT id_transaction, id_client, banque, montant_fcfa, date_transaction
                FROM voicebank.transactions
                WHERE est_frauduleuse = 'Oui'
                ORDER BY montant_fcfa DESC
                LIMIT 100
            """
        ),
        (
            r"clients?.*banques? par villes?|clients?.*banques? .*villes?|\bbanques? .*villes? .*clients?|\bclients?.*banques?\b",
            """
                SELECT banque, ville_compte AS ville, COUNT(*) AS nb_clients
                FROM voicebank.clients
                GROUP BY banque, ville_compte
                ORDER BY banque, ville_compte
                LIMIT 100
            """
        ),
        (
            r"banques?.*plus.*clients|plus.*clients.*banques?|banques? qui ont plus de clients|banques? avec le plus de clients|banques? ayant le plus de clients|nombre de clients par banque",
            """
                SELECT banque, COUNT(*) AS nb_clients
                FROM voicebank.clients
                GROUP BY banque
                ORDER BY nb_clients DESC
                LIMIT 100
            """
        ),
        (
            r"clients?.*villes?|nombre de clients.*ville|clients? par ville",
            """
                SELECT ville_compte AS ville, COUNT(*) AS nb_clients
                FROM voicebank.clients
                GROUP BY ville_compte
                ORDER BY nb_clients DESC
                LIMIT 100
            """
        ),
        (
            r"clients?.*banque|nombre de clients.*banque|clients? par banque",
            """
                SELECT banque, COUNT(*) AS nb_clients
                FROM voicebank.clients
                GROUP BY banque
                ORDER BY nb_clients DESC
                LIMIT 100
            """
        ),
    ]
    for motif, sql in regles:
        if re.search(motif, question, flags=re.IGNORECASE):
            return re.sub(r"\s+", " ", sql).strip()
    return None


def texte_vers_sql(question: str) -> tuple:
    """
    Convertit une question en SQL.
    1. Cherche d'abord dans le RAG (corrections existantes)
    2. Sinon utilise Gemini
    Retourne (sql, source) ou source = 'rag' ou 'gemini'
    """
    question = normaliser_question(question)
    # ── Etape 1 : chercher dans le RAG
    sql_rag, score_rag = chercher_correction_rag(question)
    if sql_rag:
        print(f"  RAG : correction trouvee (score={score_rag:.2f})")
        incrementer_utilisation(question)
        return sql_rag, "rag", score_rag

    # ── Etape 1.5 : verifier les regles locales
    sql_regle = sql_via_regles(question)
    if sql_regle:
        print("  Regle locale : requete SQL trouvee")
        return sql_regle, "rule", 0.0

    # ── Etape 2 : utiliser Gemini
    if not gemini_client:
        raise HTTPException(503, "Gemini non disponible. Verifie GEMINI_API_KEY dans .env ou reformule en termes simples, par exemple 'credit en defaut' ou 'transactions suspectes par client'.")

    print("  Gemini : generation SQL...")
    prompt = (
        f"{SCHEMA_SQL}\n\n"
        "Tu es un assistant SQL expert pour une base bancaire VoiceBank Analytics. "
        "Reformule la question en français clair, corrige les fautes et comprends l'intention métier. "
        "Si la question est ambiguë ou mal écrite, choisis l'intention la plus probable liée aux données bancaires. "
        "Ne réponds qu'avec une requête SELECT PostgreSQL valide sur le schema voicebank. "
        "N'ajoute aucun commentaire, aucune explication, ni aucune balise markdown. "
        "Si la question demande un total ou un classement, utilise GROUP BY, ORDER BY ou LIMIT selon les besoins. "
        "Respecte les valeurs exactes du schema, par exemple 'Défaut', 'Remboursé', 'En retard', 'Oui', 'Non', 'Élevé'."
        f"\n\nQuestion: {question}\nSQL:"
    )
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )
        sql = response.text.strip()
    except Exception as e:
        print(f"  Erreur Gemini : {e}")
        fallback = sql_via_regles(question)
        if fallback:
            print("  Regle locale utilisee en fallback apres erreur Gemini")
            return fallback, "rule", 0.0
        raise HTTPException(503, "Erreur reseau Gemini ou service indisponible. Reformule en mots simples comme 'credit en defaut' ou 'transactions suspectes par client'.")

    sql = re.sub(r"```sql|```", "", sql).strip()

    # Securite
    mots_interdits = ["DROP","DELETE","UPDATE","INSERT","CREATE","ALTER","TRUNCATE"]
    for mot in mots_interdits:
        if mot.upper() in sql.upper():
            raise HTTPException(400, f"Requete non autorisee : {mot}")

    if not sql.lower().startswith("select"):
        raise HTTPException(400, "Gemini n'a pas retourne de requete SELECT valide")

    return sql, "gemini", 0.0


# ════════════════════════════════════════
# SCHEMAS PYDANTIC
# ════════════════════════════════════════

class QuestionVocale(BaseModel):
    texte: str
    langue: Optional[str] = "fr"

class RequeteSQL(BaseModel):
    sql: str

class Correction(BaseModel):
    question   : str
    sql_correct: str

class TransactionAnalyse(BaseModel):
    montant_fcfa      : float
    type_transaction  : str
    canal             : str
    banque            : str
    ville             : str
    est_internationale: str = "Non"
    heure             : Optional[str] = "12:00"


# ════════════════════════════════════════
# ENDPOINTS
# ════════════════════════════════════════

@app.get("/")
def accueil():
    return {
        "message" : "VoiceBank Analytics API v2 avec RAG",
        "auteur"  : "Nguebou Temgoua Rayan",
        "version" : "2.0.0",
        "status"  : "OK",
    }

@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status"    : "ok" if db_ok else "degraded",
        "database"  : "connectee" if db_ok else "deconnectee",
        "gemini"    : "disponible" if gemini_client else "non configure",
        #"whisper"   : "charge" if whisper_model else "non charge",
        "whisper"   : "groq-api" if GROQ_KEY else "non configure",
        "modeles_ia": list(modeles.keys()),
        "timestamp" : datetime.now().isoformat(),
    }

@app.get("/dashboard")
def dashboard():
    try:
        _, rows = executer_sql("SELECT * FROM voicebank.v_dashboard_global")
        return {"status": "ok", "data": rows[0] if rows else {}}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/stats/global")
def stats_global():
    try:
        queries = {
            "clients_par_banque" : "SELECT * FROM voicebank.v_clients_par_banque",
            "transactions_mois"  : "SELECT * FROM voicebank.v_transactions_mensuelles LIMIT 12",
            "portefeuille_credit": "SELECT * FROM voicebank.v_portefeuille_credit",
        }
        result = {}
        for cle, sql in queries.items():
            _, rows = executer_sql(sql)
            result[cle] = rows
        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/clients")
def lister_clients(
    banque: Optional[str] = None, ville: Optional[str] = None,
    pays: Optional[str] = None, diaspora: Optional[str] = None,
    risque: Optional[str] = None, limit: int = 50
):
    conditions = ["1=1"]
    params = {}
    if banque:   conditions.append("banque = :banque");         params["banque"]   = banque
    if ville:    conditions.append("ville_compte = :ville");    params["ville"]    = ville
    if pays:     conditions.append("pays_residence = :pays");   params["pays"]     = pays
    if diaspora: conditions.append("est_diaspora = :diaspora"); params["diaspora"] = diaspora
    if risque:   conditions.append("score_risque = :risque");   params["risque"]   = risque

    sql = f"""
        SELECT id_client, nom, prenom, banque, ville_compte,
               pays_residence, est_diaspora, solde_fcfa,
               score_risque, statut_compte
        FROM voicebank.clients
        WHERE {' AND '.join(conditions)}
        ORDER BY solde_fcfa DESC
        LIMIT {min(limit, 200)}
    """
    try:
        _, rows = executer_sql(sql, params)
        return {"status": "ok", "total": len(rows), "data": rows}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/clients/{id_client}")
def detail_client(id_client: str):
    try:
        _, client = executer_sql(
            "SELECT * FROM voicebank.clients WHERE id_client = :id", {"id": id_client})
        if not client:
            raise HTTPException(404, f"Client {id_client} introuvable")
        _, transactions = executer_sql("""
            SELECT id_transaction, type_transaction, montant_fcfa,
                   date_transaction, statut, est_frauduleuse
            FROM voicebank.transactions WHERE id_client = :id
            ORDER BY date_transaction DESC LIMIT 10""", {"id": id_client})
        _, credits = executer_sql("""
            SELECT id_credit, type_credit, montant_fcfa,
                   statut_credit, taux_interet_pct, mensualite_fcfa
            FROM voicebank.credits WHERE id_client = :id""", {"id": id_client})
        return {"status": "ok", "client": client[0],
                "transactions": transactions, "credits": credits}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/transactions/recentes")
def transactions_recentes(limit: int = 50, fraude_only: bool = False):
    condition = "WHERE est_frauduleuse = 'Oui'" if fraude_only else ""
    sql = f"""
        SELECT id_transaction, id_client, banque, ville, type_transaction,
               montant_fcfa, statut, est_frauduleuse, est_internationale,
               date_transaction, heure_transaction
        FROM voicebank.transactions {condition}
        ORDER BY date_transaction DESC LIMIT {min(limit, 500)}
    """
    try:
        _, rows = executer_sql(sql)
        return {"status": "ok", "total": len(rows), "data": rows}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/alertes/fraude")
def alertes_fraude(niveau: Optional[str] = None,
                   traitee: Optional[bool] = None, limit: int = 50):
    conditions = ["1=1"]
    params = {}
    if niveau:
        conditions.append("niveau_alerte = :niveau"); params["niveau"] = niveau
    if traitee is not None:
        conditions.append("traitee = :traitee");      params["traitee"] = traitee
    sql = f"""
        SELECT a.id_alerte, a.id_transaction, a.id_client,
               a.score_anomalie, a.niveau_alerte, a.motif,
               a.traitee, a.date_alerte,
               t.montant_fcfa, t.banque, t.ville, t.type_transaction
        FROM voicebank.alertes_fraude a
        LEFT JOIN voicebank.transactions t ON a.id_transaction = t.id_transaction
        WHERE {' AND '.join(conditions)}
        ORDER BY a.score_anomalie DESC LIMIT {min(limit, 200)}
    """
    try:
        _, rows = executer_sql(sql, params)
        return {"status": "ok", "total": len(rows), "data": rows}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/credits/portefeuille")
def portefeuille_credit(statut: Optional[str] = None):
    condition = f"WHERE statut_credit = '{statut}'" if statut else ""
    sql = f"""
        SELECT id_credit, id_client, banque, type_credit, montant_fcfa,
               taux_interet_pct, mensualite_fcfa, statut_credit,
               score_credit, garantie, date_debut
        FROM voicebank.credits {condition}
        ORDER BY montant_fcfa DESC LIMIT 100
    """
    try:
        _, rows = executer_sql(sql)
        return {"status": "ok", "total": len(rows), "data": rows}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Question vocale (texte) ───────────────────────────

@app.post("/vocal/question")
def question_vocale(body: QuestionVocale):
    debut = time.time()
    try:
        sql_genere, source, score = texte_vers_sql(body.texte)
        colonnes, rows = executer_sql(sql_genere)
        duree_ms = int((time.time() - debut) * 1000)

        # Logger
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO voicebank.logs_vocaux
                    (texte_transcrit, requete_sql, succes, duree_ms)
                    VALUES (:texte, :sql, :succes, :duree)
                """), {"texte": body.texte, "sql": sql_genere,
                       "succes": True, "duree": duree_ms})
                conn.commit()
        except Exception:
            pass

        return {
            "status"      : "ok",
            "question"    : body.texte,
            "sql"         : sql_genere,
            "source"      : source,         # 'rag' ou 'gemini'
            "score_rag"   : score,
            "colonnes"    : colonnes,
            "total"       : len(rows),
            "data"        : rows,
            "duree_ms"    : duree_ms,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur : {str(e)}")

# ── Corriger une reponse (RAG learning) ──────────────

@app.post("/vocal/corriger")
def corriger_reponse(body: Correction):
    """
    Enregistre une correction SQL.
    Le systeme apprendra automatiquement pour les prochaines questions similaires.
    """
    try:
        enregistrer_correction_db(body.question, body.sql_correct)
        return {
            "status" : "ok",
            "message": "Correction enregistree. Le systeme apprendra pour les prochaines questions.",
            "question"   : body.question,
            "sql_correct": body.sql_correct,
        }
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Voir toutes les corrections RAG ──────────────────

@app.get("/rag/corrections")
def lister_corrections(limit: int = 50):
    """Affiche toutes les corrections enregistrees dans le RAG."""
    try:
        _, rows = executer_sql(f"""
            SELECT id, question, sql_correct, utilisee, date_ajout
            FROM voicebank.logs_corrections
            ORDER BY utilisee DESC, date_ajout DESC
            LIMIT {min(limit, 200)}
        """)
        return {"status": "ok", "total": len(rows), "data": rows}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Statistiques RAG ──────────────────────────────────

@app.get("/rag/stats")
def stats_rag():
    """Statistiques sur les performances du systeme RAG."""
    try:
        _, corrections = executer_sql(
            "SELECT COUNT(*) as total, SUM(utilisee) as total_utilisations FROM voicebank.logs_corrections")
        _, logs = executer_sql(
            "SELECT COUNT(*) as total FROM voicebank.logs_vocaux")
        return {
            "status"             : "ok",
            "nb_corrections"     : corrections[0]["total"],
            "total_utilisations" : corrections[0]["total_utilisations"] or 0,
            "nb_questions_posees": logs[0]["total"],
        }
    except Exception as e:
        raise HTTPException(500, str(e))

# ── SQL manuel ────────────────────────────────────────

@app.post("/sql/executer")
def executer_requete(body: RequeteSQL):
    mots_interdits = ["DROP","DELETE","UPDATE","INSERT","CREATE","ALTER","TRUNCATE"]
    for mot in mots_interdits:
        if mot.upper() in body.sql.upper():
            raise HTTPException(400, f"Requete non autorisee : {mot}")
    try:
        colonnes, rows = executer_sql(body.sql)
        return {"status": "ok", "colonnes": colonnes, "total": len(rows), "data": rows}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Transcription audio (Whisper) ─────────────────────

@app.post("/vocal/transcrire")
async def transcrire_audio(fichier: UploadFile = File(...)):
    if not whisper_model:
        raise HTTPException(503, "Whisper non disponible")
    
    chemin_tmp = None
    try:
        contenu = await fichier.read()
        if not contenu:
            raise Exception("Fichier audio vide")

        extension = fichier.filename.split(".")[-1] if fichier.filename else "webm"
        temp_dir = tempfile.gettempdir()
        chemin_tmp = os.path.join(temp_dir, f"voicebank_audio_{int(time.time() * 1000)}.{extension}")
        
        # Écrire le fichier
        with open(chemin_tmp, "wb") as f:
            f.write(contenu)
        
        # Vérifier que le fichier existe et a une taille
        taille = os.path.getsize(chemin_tmp)
        if taille == 0:
            raise Exception(f"Fichier audio vide : {chemin_tmp}")
        
        print(f"✓ Audio reçu ({taille} bytes) → {chemin_tmp}")
        
        # Transcrire avec verbose=False pour moins de bruit
       # result = whisper_model.transcribe(chemin_tmp, language="fr", fp16=False, verbose=False)
       # texte = result.get("text", "").strip()
        texte = transcrire_avec_groq(chemin_tmp)

        if not texte:
            raise Exception("Whisper n'a détecté aucun texte")
        
        print(f"✓ Transcription OK : {texte[:60]}")
        return {"status": "ok", "texte": texte}
    
    except FileNotFoundError as e:
        print(f"✗ Fichier non trouvé : {str(e)}")
        raise HTTPException(500, f"Whisper ne peut pas accéder au fichier : {str(e)}")
    except Exception as e:
        print(f"✗ Erreur transcription : {str(e)}")
        raise HTTPException(500, f"Erreur Whisper : {str(e)}")
    
    finally:
        if chemin_tmp and os.path.exists(chemin_tmp):
            try:
                os.unlink(chemin_tmp)
                print(f"✓ Fichier temporaire supprimé")
            except Exception as e:
                print(f"⚠ Impossible de supprimer {chemin_tmp}: {e}")

# ── Pipeline complet : audio -> SQL -> data ───────────

@app.post("/vocal/pipeline-complet")
async def pipeline_vocal_complet(fichier: UploadFile = File(...)):
    if not whisper_model:
        raise HTTPException(503, "Whisper non disponible")
    debut   = time.time()
    contenu = await fichier.read()
    extension = fichier.filename.split(".")[-1] if fichier.filename else "wav"
    with tempfile.NamedTemporaryFile(suffix=f".{extension}", delete=False) as f:
        f.write(contenu); chemin_tmp = f.name
    try:
        #result    = whisper_model.transcribe(chemin_tmp, language="fr", fp16=False)
        #texte     = result["text"].strip()
        texte = transcrire_avec_groq(chemin_tmp)

        sql, source, score = texte_vers_sql(texte)
        colonnes, rows     = executer_sql(sql)
        duree_ms  = int((time.time() - debut) * 1000)
        return {
            "status"      : "ok",
            "texte_audio" : texte,
            "sql"         : sql,
            "source"      : source,
            "total"       : len(rows),
            "data"        : rows,
            "duree_ms"    : duree_ms,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        os.unlink(chemin_tmp)

# ── Analyse transaction IA ────────────────────────────

@app.post("/ia/analyser-transaction")
def analyser_transaction(txn: TransactionAnalyse):
    try:
        if "isolation_forest" not in modeles:
            raise HTTPException(503, "Modele fraude non charge")
        heure       = int(txn.heure.split(":")[0]) if txn.heure else 12
        est_nuit    = 1 if heure >= 22 or heure <= 6 else 0
        est_weekend = 1 if datetime.now().weekday() >= 5 else 0
        encoders    = modeles["encoders_fraude"]
        scaler      = modeles["scaler_fraude"]

        def enc(col, val):
            if col in encoders:
                le = encoders[col]
                if val in le.classes_:
                    return int(le.transform([val])[0])
            return 0

        features = np.array([[
            np.log1p(txn.montant_fcfa), heure, est_nuit, est_weekend,
            enc("type_transaction", txn.type_transaction),
            enc("canal", txn.canal), enc("banque", txn.banque),
            enc("ville", txn.ville),
            enc("est_internationale", txn.est_internationale),
        ]])
        features_scaled = scaler.transform(features)
        score_if   = float(-modeles["isolation_forest"].decision_function(features_scaled)[0])
        score_norm = round(min(max(score_if, 0), 1), 4)
        niveau     = ("Critique" if score_norm >= 0.85 else
                      "Eleve"    if score_norm >= 0.70 else
                      "Moyen"    if score_norm >= 0.50 else "Faible")
        return {
            "status"        : "ok",
            "score_anomalie": score_norm,
            "niveau_risque" : niveau,
            "est_suspecte"  : score_norm >= 0.50,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Démarrage du serveur ──────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("🚀 Démarrage VoiceBank API sur http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
