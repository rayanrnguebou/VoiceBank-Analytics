"""VoiceBank Analytics — API FastAPI (v3, sécurisée).
Auteur : Nguebou Temgoua Rayan
"""
import logging
import time
from datetime import date, datetime
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Path, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from . import config, db, fraude, nl2sql, transcription
from .garde_sql import SQLRefuse, valider_sql
from .securite import Utilisateur, admin_requis, authentifier, creer_jeton, utilisateur_courant

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("voicebank")

app = FastAPI(
    title="VoiceBank Analytics API",
    description="API bancaire vocale (texte/voix -> SQL) — Nguebou Temgoua Rayan",
    version="3.0.0",
    docs_url=None if config.EST_PROD else "/docs",
    redoc_url=None,
    openapi_url=None if config.EST_PROD else "/openapi.json",
)

limiter = Limiter(key_func=get_remote_address, enabled=config.RATE_LIMIT_ACTIF)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def _trop_de_requetes(request: Request, exc: RateLimitExceeded):
    return JSONResponse({"detail": "Trop de requêtes, réessaie dans un instant."}, status_code=429)


@app.exception_handler(Exception)
def _erreur_interne(request: Request, exc: Exception):
    # Le détail reste dans les logs serveur, jamais renvoyé au client.
    log.exception("Erreur non gérée sur %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Erreur interne du serveur"}, status_code=500)


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def entetes_securite(request: Request, call_next):
    rep = await call_next(request)
    rep.headers["X-Content-Type-Options"] = "nosniff"
    rep.headers["X-Frame-Options"] = "DENY"
    rep.headers["Referrer-Policy"] = "no-referrer"
    rep.headers["Cache-Control"] = "no-store"
    if config.EST_PROD:
        rep.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return rep


fraude.charger()
transcription.precharger_en_arriere_plan()

# ════════════════════════════════════════
# SCHÉMAS
# ════════════════════════════════════════
class Identifiants(BaseModel):
    nom: str = Field(min_length=1, max_length=64)
    mot_de_passe: str = Field(min_length=1, max_length=128)


class QuestionVocale(BaseModel):
    texte: str = Field(min_length=2, max_length=500)
    langue: str | None = "fr"


class RequeteSQL(BaseModel):
    sql: str = Field(min_length=1, max_length=5000)


class Correction(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    sql_correct: str = Field(min_length=1, max_length=5000)


class TransactionAnalyse(BaseModel):
    montant_fcfa: float = Field(gt=0, lt=1e13)
    type_transaction: str = Field(max_length=60)
    canal: str = Field(max_length=40)
    banque: str = Field(max_length=60)
    ville: str = Field(max_length=50)
    est_internationale: Literal["Oui", "Non"] = "Non"
    date_transaction: date | None = None


# ════════════════════════════════════════
# OUTILS
# ════════════════════════════════════════

def _executer_sql_valide(sql: str) -> tuple[str, list, list]:
    try:
        sql_sur = valider_sql(sql, config.SQL_MAX_LIGNES)
    except SQLRefuse as e:
        raise HTTPException(400, f"Requête refusée : {e}")
    try:
        colonnes, lignes = db.lire(sql_sur, brut=True)
    except Exception as e:
        log.warning("Échec d'exécution SQL : %s", e)
        raise HTTPException(422, "La requête n'a pas pu être exécutée. Reformule ta question.")
    return sql, colonnes, lignes


def _journaliser(texte: str, sql: str | None, succes: bool, duree_ms: int, u: Utilisateur):
    try:
        db.ecrire("INSERT INTO voicebank.logs_vocaux (texte_original, texte_transcrit, requete_sql, "
                  "succes, duree_ms, utilisateur) VALUES (:t, :t, :s, :ok, :d, :u)",
                  {"t": texte, "s": sql, "ok": succes, "d": duree_ms, "u": u.nom})
    except Exception:
        log.exception("Journalisation impossible")


def _lire(sql: str, params: dict | None = None):
    try:
        return db.lire(sql, params)
    except Exception:
        log.exception("Erreur de lecture")
        raise HTTPException(503, "Base de données indisponible")


async def _transcrire(contenu: bytes, extension: str) -> tuple[str, str]:
    """Groq, ou Whisper local si la clé est vide / Groq en panne. Exécuté hors de la boucle async."""
    try:
        texte, moteur = await run_in_threadpool(transcription.transcrire, contenu, extension)
    except transcription.TranscriptionErreur as e:
        raise HTTPException(e.code, e.message)
    if not texte:
        raise HTTPException(422, "Aucune parole détectée")
    return texte, moteur


EXTENSIONS_AUDIO = {"webm", "ogg", "wav", "mp3", "m4a", "mp4", "mpeg", "flac"}


async def _lire_audio(fichier: UploadFile) -> tuple[bytes, str]:
    extension = (fichier.filename or "").rsplit(".", 1)[-1].lower()
    if extension not in EXTENSIONS_AUDIO:
        raise HTTPException(415, "Format audio non pris en charge")
    contenu = await fichier.read(config.TAILLE_MAX_AUDIO + 1)
    if len(contenu) > config.TAILLE_MAX_AUDIO:
        raise HTTPException(413, "Fichier audio trop volumineux")
    if not contenu:
        raise HTTPException(400, "Fichier audio vide")
    return contenu, extension


def _question_vers_resultat(texte: str, u: Utilisateur) -> dict:
    debut = time.time()
    question = nl2sql.normaliser_question(texte)
    try:
        sql, source, score = nl2sql.texte_vers_sql(question)
    except nl2sql.IAIndisponible:
        _journaliser(texte, None, False, int((time.time() - debut) * 1000), u)
        raise HTTPException(503, "Je n'ai pas compris la question et l'IA est indisponible. "
                                 "Essaie par exemple « crédits en défaut » ou « clients par banque ».")
    try:
        sql, colonnes, lignes = _executer_sql_valide(sql)
    except HTTPException:
        _journaliser(texte, sql, False, int((time.time() - debut) * 1000), u)
        raise
    duree = int((time.time() - debut) * 1000)
    _journaliser(texte, sql, True, duree, u)
    return {"status": "ok", "question": texte, "sql": sql, "source": source,
            "score_rag": score, "colonnes": colonnes, "total": len(lignes),
            "data": lignes, "duree_ms": duree}


# ════════════════════════════════════════
# PUBLIC
# ════════════════════════════════════════

@app.get("/")
def accueil():
    return {"message": "VoiceBank Analytics API", "version": app.version, "status": "OK"}


@app.get("/health")
def health():
    ok = db.base_ok()
    return {"status": "ok" if ok else "degraded",
            "database": "connectee" if ok else "deconnectee",
            "gemini": "disponible" if config.GEMINI_API_KEY else "non configure",
            "whisper": transcription.etat(),
            "modeles_ia": sorted(fraude.modeles.keys()),
            "timestamp": datetime.now().isoformat()}


@app.post("/auth/login")
@limiter.limit("5/minute")
def login(request: Request, body: Identifiants):
    u = authentifier(body.nom, body.mot_de_passe)
    if not u:
        log.warning("Échec de connexion pour '%s' depuis %s", body.nom, get_remote_address(request))
        raise HTTPException(401, "Identifiants incorrects")
    return {"access_token": creer_jeton(u), "token_type": "bearer",
            "utilisateur": u.nom, "role": u.role, "expire_dans_min": config.JWT_DUREE_MIN}


# ════════════════════════════════════════
# CONSULTATION (authentifié)
# ════════════════════════════════════════

@app.get("/auth/moi")
def moi(u: Utilisateur = Depends(utilisateur_courant)):
    return {"utilisateur": u.nom, "role": u.role}


@app.get("/dashboard")
def dashboard(u: Utilisateur = Depends(utilisateur_courant)):
    _, rows = _lire("SELECT * FROM voicebank.v_dashboard_global")
    return {"status": "ok", "data": rows[0] if rows else {}}


@app.get("/stats/global")
def stats_global(u: Utilisateur = Depends(utilisateur_courant)):
    requetes = {
        "clients_par_banque": "SELECT * FROM voicebank.v_clients_par_banque",
        "transactions_mois": (
            "SELECT * FROM (SELECT mois, SUM(nb_transactions) AS nb_transactions, SUM(nb_fraudes) AS nb_fraudes, "
            "SUM(volume_fcfa) AS volume_fcfa FROM voicebank.v_transactions_mensuelles GROUP BY mois "
            "ORDER BY mois DESC LIMIT 12) m ORDER BY mois"),
        "portefeuille_credit": "SELECT * FROM voicebank.v_portefeuille_credit",
    }
    return {"status": "ok", "data": {k: _lire(sql)[1] for k, sql in requetes.items()}}


@app.get("/clients")
def lister_clients(
    banque: str | None = Query(None, max_length=60), ville: str | None = Query(None, max_length=50),
    pays: str | None = Query(None, max_length=60), diaspora: Literal["Oui", "Non"] | None = None,
    risque: Literal["Faible", "Moyen", "Élevé"] | None = None,
    limit: int = Query(50, ge=1, le=200), u: Utilisateur = Depends(utilisateur_courant),
):
    filtres = {"banque": banque, "ville_compte": ville, "pays_residence": pays,
               "est_diaspora": diaspora, "score_risque": risque}
    conditions = [f"{col} = :{col}" for col, v in filtres.items() if v is not None]
    params = {col: v for col, v in filtres.items() if v is not None} | {"limit": limit}
    where = " AND ".join(conditions) or "TRUE"
    _, rows = _lire(
        "SELECT id_client, nom, prenom, banque, ville_compte, pays_residence, est_diaspora, "
        f"solde_fcfa, score_risque, statut_compte FROM voicebank.clients WHERE {where} "
        "ORDER BY solde_fcfa DESC LIMIT :limit", params)
    return {"status": "ok", "total": len(rows), "data": rows}


@app.get("/clients/{id_client}")
def detail_client(id_client: str = Path(max_length=12), u: Utilisateur = Depends(utilisateur_courant)):
    _, client = _lire("SELECT * FROM voicebank.clients WHERE id_client = :id", {"id": id_client})
    if not client:
        raise HTTPException(404, "Client introuvable")
    _, transactions = _lire(
        "SELECT id_transaction, type_transaction, montant_fcfa, date_transaction, statut, est_frauduleuse "
        "FROM voicebank.transactions WHERE id_client = :id ORDER BY date_transaction DESC LIMIT 10",
        {"id": id_client})
    _, credits = _lire(
        "SELECT id_credit, type_credit, montant_fcfa, statut_credit, taux_interet_pct, mensualite_fcfa "
        "FROM voicebank.credits WHERE id_client = :id", {"id": id_client})
    return {"status": "ok", "client": client[0], "transactions": transactions, "credits": credits}


@app.get("/transactions/recentes")
def transactions_recentes(limit: int = Query(50, ge=1, le=500), fraude_only: bool = False,
                          u: Utilisateur = Depends(utilisateur_courant)):
    where = "WHERE est_frauduleuse = 'Oui'" if fraude_only else ""
    _, rows = _lire(
        "SELECT id_transaction, id_client, banque, ville, type_transaction, montant_fcfa, statut, "
        "est_frauduleuse, est_internationale, date_transaction, heure_transaction "
        f"FROM voicebank.transactions {where} ORDER BY date_transaction DESC LIMIT :limit",
        {"limit": limit})
    return {"status": "ok", "total": len(rows), "data": rows}


@app.get("/alertes/fraude")
def alertes_fraude(niveau: Literal["Faible", "Moyen", "Élevé", "Critique"] | None = None,
                   traitee: bool | None = None, limit: int = Query(50, ge=1, le=200),
                   u: Utilisateur = Depends(utilisateur_courant)):
    conditions, params = ["TRUE"], {"limit": limit}
    if niveau:
        conditions.append("a.niveau_alerte = :niveau"); params["niveau"] = niveau
    if traitee is not None:
        conditions.append("a.traitee = :traitee"); params["traitee"] = traitee
    _, rows = _lire(
        "SELECT a.id_alerte, a.id_transaction, a.id_client, a.score_anomalie, a.niveau_alerte, "
        "a.motif, a.traitee, a.date_alerte, t.montant_fcfa, t.banque, t.ville, t.type_transaction "
        "FROM voicebank.alertes_fraude a LEFT JOIN voicebank.transactions t "
        f"ON a.id_transaction = t.id_transaction WHERE {' AND '.join(conditions)} "
        "ORDER BY a.score_anomalie DESC LIMIT :limit", params)
    return {"status": "ok", "total": len(rows), "data": rows}


@app.get("/credits/portefeuille")
def portefeuille_credit(statut: Literal["En cours", "Remboursé", "En retard", "Défaut"] | None = None,
                        u: Utilisateur = Depends(utilisateur_courant)):
    where = "WHERE statut_credit = :statut" if statut else ""
    _, rows = _lire(
        "SELECT id_credit, id_client, banque, type_credit, montant_fcfa, taux_interet_pct, "
        f"mensualite_fcfa, statut_credit, score_credit, garantie, date_debut FROM voicebank.credits {where} "
        "ORDER BY montant_fcfa DESC LIMIT 100", {"statut": statut} if statut else {})
    return {"status": "ok", "total": len(rows), "data": rows}


# ── Questions en langage naturel ──────────────────────

@app.post("/vocal/question")
@limiter.limit("30/minute")
def question_vocale(request: Request, body: QuestionVocale, u: Utilisateur = Depends(utilisateur_courant)):
    return _question_vers_resultat(body.texte, u)


@app.post("/vocal/transcrire")
@limiter.limit("10/minute")
async def transcrire_audio(request: Request, fichier: UploadFile = File(...),
                           u: Utilisateur = Depends(utilisateur_courant)):
    contenu, extension = await _lire_audio(fichier)
    texte, moteur = await _transcrire(contenu, extension)
    return {"status": "ok", "texte": texte, "moteur": moteur}


@app.post("/vocal/pipeline-complet")
@limiter.limit("10/minute")
async def pipeline_vocal_complet(request: Request, fichier: UploadFile = File(...),
                                 u: Utilisateur = Depends(utilisateur_courant)):
    contenu, extension = await _lire_audio(fichier)
    texte, moteur = await _transcrire(contenu, extension)
    resultat = await run_in_threadpool(_question_vers_resultat, texte, u)
    return {"texte_audio": texte, "moteur_transcription": moteur, **resultat}


# ── IA fraude ─────────────────────────────────────────

@app.get("/ia/referentiel")
def ia_referentiel(u: Utilisateur = Depends(utilisateur_courant)):
    return {"status": "ok", "data": fraude.referentiel()}


@app.post("/ia/analyser-transaction")
def analyser_transaction(txn: TransactionAnalyse, u: Utilisateur = Depends(utilisateur_courant)):
    if "iforest" not in fraude.modeles:
        raise HTTPException(503, "Modèle de fraude non chargé")
    try:
        res = fraude.analyser(txn.montant_fcfa, txn.type_transaction, txn.canal, txn.banque,
                              txn.ville, txn.est_internationale, txn.date_transaction)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"status": "ok", **res}


# ════════════════════════════════════════
# ADMINISTRATION
# ════════════════════════════════════════

@app.post("/sql/executer")
@limiter.limit("30/minute")
def executer_requete(request: Request, body: RequeteSQL, u: Utilisateur = Depends(admin_requis)):
    sql, colonnes, lignes = _executer_sql_valide(body.sql)
    log.info("SQL manuel exécuté par %s", u.nom)
    return {"status": "ok", "colonnes": colonnes, "total": len(lignes), "data": lignes}


@app.post("/vocal/corriger")
def corriger_reponse(body: Correction, u: Utilisateur = Depends(admin_requis)):
    # Une correction n'est enregistrée que si elle passe la validation ET s'exécute.
    sql, _, _ = _executer_sql_valide(body.sql_correct)
    question = nl2sql.normaliser_question(body.question)
    _, existe = _lire("SELECT id FROM voicebank.logs_corrections "
                      "WHERE SIMILARITY(LOWER(question), LOWER(:q)) > 0.85 LIMIT 1", {"q": question})
    if existe:
        db.ecrire("UPDATE voicebank.logs_corrections SET sql_correct = :s, date_modif = NOW() WHERE id = :id",
                  {"s": sql, "id": existe[0]["id"]})
    else:
        db.ecrire("INSERT INTO voicebank.logs_corrections (question, sql_correct) VALUES (:q, :s)",
                  {"q": question, "s": sql})
    log.info("Correction RAG enregistrée par %s", u.nom)
    return {"status": "ok", "message": "Correction enregistrée.", "question": question, "sql_correct": sql}


@app.get("/rag/corrections")
def lister_corrections(limit: int = Query(50, ge=1, le=200), u: Utilisateur = Depends(admin_requis)):
    _, rows = _lire("SELECT id, question, sql_correct, utilisee, date_ajout FROM voicebank.logs_corrections "
                    "ORDER BY utilisee DESC, date_ajout DESC LIMIT :limit", {"limit": limit})
    return {"status": "ok", "total": len(rows), "data": rows}


@app.get("/rag/stats")
def stats_rag(u: Utilisateur = Depends(admin_requis)):
    _, c = _lire("SELECT COUNT(*) AS total, COALESCE(SUM(utilisee), 0) AS utilisations "
                 "FROM voicebank.logs_corrections")
    _, l = _lire("SELECT COUNT(*) AS total FROM voicebank.logs_vocaux")
    return {"status": "ok", "nb_corrections": c[0]["total"],
            "total_utilisations": c[0]["utilisations"], "nb_questions_posees": l[0]["total"]}
