"""VoiceBank Analytics — API FastAPI (v3, sécurisée).
Auteur : Nguebou Temgoua Rayan
"""
import logging
import time
from datetime import date, datetime, time as heure_t
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Path, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi.errors import RateLimitExceeded

from . import audit, config, credit, db, evaluation, fraude, nl2sql, paiement, resume, transcription
from .garde_sql import SQLRefuse, valider_sql
from .masquage import masquer_ligne, masquer_lignes
from . import securite
from .connecteur import service as sources
from .paiement import PaiementRefuse
from .securite import (CompteRefuse, Utilisateur, admin_ou_decouverte, admin_requis, authentifier, creer_jeton,
                       interne_requis, utilisateur_authentifie, utilisateur_courant, utilisateur_valide)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("voicebank")

app = FastAPI(
    title="VoiceBank Analytics API",
    description="API bancaire vocale (texte/voix -> SQL) — Nguebou Temgoua Rayan",
    version="3.2.0",
    docs_url=None if config.EST_PROD else "/docs",
    redoc_url=None,
    openapi_url=None if config.EST_PROD else "/openapi.json",
)

from .limites import ip_client, limiter  # noqa: E402
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def _trop_de_requetes(request: Request, exc: RateLimitExceeded):
    return JSONResponse({"detail": "Trop de requêtes, réessaie dans un instant."}, status_code=429)


@app.middleware("http")
async def erreurs_internes(request: Request, call_next):
    # Ajouté AVANT CORS (donc à l'intérieur) : une erreur 500 garde les en-têtes CORS et le
    # navigateur affiche "Erreur interne" au lieu de "API injoignable".
    # Le détail reste dans les logs serveur, jamais renvoyé au client.
    try:
        return await call_next(request)
    except Exception:
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
credit.charger()
transcription.precharger_en_arriere_plan()
try:
    securite.amorcer()
except Exception:
    log.exception("Amorçage des comptes impossible (base indisponible ?) : nouvel essai au prochain démarrage")

# ════════════════════════════════════════
# SCHÉMAS
# ════════════════════════════════════════
class Identifiants(BaseModel):
    nom: str = Field(min_length=1, max_length=64)
    mot_de_passe: str = Field(min_length=1, max_length=128)


class ChangementMdp(BaseModel):
    actuel: str = Field(min_length=1, max_length=128)
    nouveau: str = Field(min_length=1, max_length=128)


class NouveauCompte(BaseModel):
    nom: str = Field(min_length=3, max_length=32)
    role: Literal["analyste", "admin"] = "analyste"


class ModificationCompte(BaseModel):
    role: Literal["analyste", "admin"] | None = None
    actif: bool | None = None


TELEPHONE = r"^\+?[0-9 ]{8,20}$"
EMAIL = r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,24}$"


class InscriptionEssai(BaseModel):
    nom_complet: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=64)
    mot_de_passe: str = Field(min_length=1, max_length=128)
    profil: Literal["etudiant", "professionnel", "entreprise", "recruteur", "autre"] = "professionnel"
    accepte_conditions: bool
    site_web: str | None = Field(None, max_length=200)     # piège à robots : doit rester vide


class InfosOrganisation(BaseModel):
    raison_sociale: str = Field(min_length=2, max_length=150)
    secteur: Literal["banque", "microfinance", "assurance", "fintech", "administration", "autre"]
    taille: Literal["1-10", "11-50", "51-250", "250+"]
    pays: str = Field(min_length=2, max_length=60)
    ville: str = Field(min_length=2, max_length=60)
    responsable: str = Field(min_length=2, max_length=120)
    fonction: str = Field(min_length=2, max_length=80)
    email: str = Field(pattern=EMAIL, max_length=254)
    telephone: str = Field(pattern=TELEPHONE)
    niu: str | None = Field(None, max_length=30)            # numéro d'identifiant unique (contribuable)
    rccm: str | None = Field(None, max_length=40)


class InfosParticulier(BaseModel):
    nom_complet: str = Field(min_length=2, max_length=120)
    profession: str = Field(min_length=2, max_length=80)
    pays: str = Field(min_length=2, max_length=60)
    ville: str = Field(min_length=2, max_length=60)
    email: str = Field(pattern=EMAIL, max_length=254)
    telephone: str = Field(pattern=TELEPHONE)


class Commande(BaseModel):
    formule: Literal["jour", "semaine", "mois", "annee"]
    type_client: Literal["organisation", "particulier"]
    organisation: InfosOrganisation | None = None
    particulier: InfosParticulier | None = None
    accepte_conditions: bool


class ConnexionBase(BaseModel):
    type_source: Literal["postgresql", "mysql", "sqlserver"]
    hote: str = Field(min_length=1, max_length=253)
    port: int | None = Field(None, ge=1, le=65535)
    base: str = Field(min_length=1, max_length=128)
    utilisateur: str = Field(min_length=1, max_length=128)
    mot_de_passe: str = Field("", max_length=256)
    ssl: Literal["prefere", "exige", "desactive"] = "prefere"
    schema_bd: str | None = Field(None, max_length=128, pattern=r"^[A-Za-z0-9_]+$", alias="schema")

    def config(self) -> dict:
        return {"hote": self.hote.strip(), "port": self.port, "base": self.base, "utilisateur": self.utilisateur,
                "mot_de_passe": self.mot_de_passe, "ssl": self.ssl, "schema": self.schema_bd}


class NouvelleSource(ConnexionBase):
    nom: str = Field(min_length=2, max_length=80)


class QuestionSource(BaseModel):
    texte: str = Field(min_length=2, max_length=500)


class Masquage(BaseModel):
    masquer: bool


class ContexteQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    sql: str = Field(min_length=1, max_length=5000)


class QuestionVocale(BaseModel):
    texte: str = Field(min_length=2, max_length=500)
    langue: str | None = "fr"
    contexte: ContexteQuestion | None = None      # question précédente, pour « et à Douala ? »
    resumer: bool = True                          # résumé rédigé (lu à voix haute par l'interface)


class RequeteSQL(BaseModel):
    sql: str = Field(min_length=1, max_length=5000)


class Correction(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    sql_correct: str = Field(min_length=1, max_length=5000)
    id_signalement: int | None = None


class Signalement(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    sql: str | None = Field(None, max_length=5000)
    source: str | None = Field(None, max_length=20)
    commentaire: str | None = Field(None, max_length=1000)


class DecisionSignalement(BaseModel):
    statut: Literal["Corrigé", "Rejeté"]


class TraitementAlerte(BaseModel):
    decision: Literal["Fraude confirmée", "Faux positif"]
    commentaire: str | None = Field(None, max_length=1000)


class DemandeCredit(BaseModel):
    montant_fcfa: float = Field(gt=0, lt=1e13)
    mensualite_fcfa: float = Field(ge=0, lt=1e12)
    revenu_annuel_fcfa: float = Field(gt=0, lt=1e13)
    score_credit: int = Field(600, ge=300, le=850)
    taux_interet_pct: float = Field(12.0, ge=0, le=100)
    duree_mois: int = Field(24, ge=1, le=480)
    est_diaspora: Literal["Oui", "Non"] = "Non"
    type_credit: str = Field(max_length=50)
    garantie: str = Field(max_length=50)
    banque: str = Field(max_length=60)


class TransactionAnalyse(BaseModel):
    montant_fcfa: float = Field(gt=0, lt=1e13)
    type_transaction: str = Field(max_length=60)
    canal: str = Field(max_length=40)
    banque: str = Field(max_length=60)
    ville: str = Field(max_length=50)
    est_internationale: Literal["Oui", "Non"] = "Non"
    date_transaction: date | None = None
    heure: heure_t | None = None


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


def _colonnes_de(sql: str) -> list[str]:
    try:
        return db.lire(valider_sql(sql, 0), brut=True)[0]
    except Exception:
        return []


def _question_vers_resultat(texte: str, u: Utilisateur, contexte: ContexteQuestion | None = None,
                            resumer: bool = True) -> dict:
    debut = time.time()
    question = nl2sql.normaliser_question(texte)
    ctx = contexte.model_dump() if contexte else None
    try:
        sql, source, score, avertissement, suite = nl2sql.texte_vers_sql_avec_contexte(
            question, ctx, lambda: _colonnes_de(ctx["sql"]))
    except nl2sql.IAIndisponible:
        _journaliser(texte, None, False, int((time.time() - debut) * 1000), u)
        raise HTTPException(503, "Je n'ai pas compris la question et l'IA est indisponible. "
                                 "Essaie par exemple « crédits en défaut » ou « clients par banque ».")
    try:
        sql, colonnes, lignes = _executer_sql_valide(sql)
    except HTTPException:
        _journaliser(texte, sql, False, int((time.time() - debut) * 1000), u)
        raise
    lignes = masquer_lignes(colonnes, lignes, u.role)
    r = resume.resumer(texte, colonnes, lignes) if resumer else {}
    duree = int((time.time() - debut) * 1000)
    _journaliser(texte, sql, True, duree, u)
    return {"status": "ok", "question": texte, "sql": sql, "source": source,
            "score_rag": score, "avertissement": avertissement, "colonnes": colonnes, "total": len(lignes),
            "data": lignes, "duree_ms": duree, "resume": r.get("resume"), "resume_source": r.get("source"),
            "commentaire": r.get("commentaire"), "relance": r.get("relance"),
            "suite": suite, "question_precedente": ctx["question"] if suite else None}


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
            "modeles_ia": sorted(k for k in fraude.modeles if k != "meta") + (["credit"] if credit.disponible() else []),
            "timestamp": datetime.now().isoformat()}


@app.post("/auth/login")
@limiter.limit("5/minute")
def login(request: Request, body: Identifiants):
    resultat = authentifier(body.nom, body.mot_de_passe)
    ip = ip_client(request)
    if not resultat:
        log.warning("Échec de connexion pour '%s' depuis %s", body.nom, ip)
        audit.journaliser(body.nom[:64], "connexion_refusee", None, ip)
        raise HTTPException(401, "Identifiants incorrects. Après 5 échecs, le compte est bloqué 15 minutes.")
    u, version = resultat
    audit.journaliser(u.nom, "connexion", {"role": u.role}, ip)
    return _reponse_jeton(u, version)


def _reponse_jeton(u: Utilisateur, version: int) -> dict:
    return {"access_token": creer_jeton(u, version), "token_type": "bearer",
            "utilisateur": u.nom, "role": u.role, "doit_changer_mot_de_passe": u.doit_changer,
            "expire_dans_min": config.JWT_DUREE_MIN}


@app.post("/auth/renouveler")
@limiter.limit("30/minute")
def renouveler_jeton(request: Request, u: Utilisateur = Depends(utilisateur_valide)):
    """Nouveau jeton pour une session active (l'interface l'appelle tant que l'utilisateur est actif).
    Un compte désactivé ou dont le mot de passe a changé est refusé par utilisateur_courant."""
    return _reponse_jeton(u, securite.version_jeton(u.nom))


@app.post("/auth/mot-de-passe")
@limiter.limit("5/minute")
def changer_mon_mot_de_passe(request: Request, body: ChangementMdp,
                             u: Utilisateur = Depends(utilisateur_authentifie)):
    try:
        version = securite.changer_mot_de_passe(u.nom, body.actuel, body.nouveau)
    except CompteRefuse as e:
        raise HTTPException(400, str(e))
    audit.journaliser(u.nom, "mot_de_passe_change", None, ip_client(request))
    # Nouveau jeton : cette session continue, les autres sont déconnectées.
    return _reponse_jeton(Utilisateur(u.nom, u.role, False), version)


# ════════════════════════════════════════
# CONSULTATION (authentifié)
# ════════════════════════════════════════

@app.get("/auth/moi")
def moi(u: Utilisateur = Depends(utilisateur_authentifie)):
    return {"utilisateur": u.nom, "role": u.role, "doit_changer_mot_de_passe": u.doit_changer,
            "gestion_comptes": securite.mode_base(), "acces": _acces(u)}


def _acces(u: Utilisateur) -> dict:
    """Statut d'accès affiché par l'interface (bandeau d'essai, abonnement)."""
    if not u.externe or not securite.mode_base():
        return {"type": "interne", "lecture_seule": False, "expire": False}
    l = db.ecrire("SELECT essai_fin, abonnement_fin, formule, nom_complet, "
                  "(SELECT COUNT(*) FROM voicebank.logs_vocaux WHERE utilisateur = :u "
                  " AND date_requete >= CURRENT_DATE) AS questions_jour, "
                  "GREATEST(EXTRACT(EPOCH FROM (CASE WHEN role = 'visiteur' THEN essai_fin ELSE abonnement_fin END) "
                  " - LOCALTIMESTAMP), 0) AS secondes_restantes "
                  "FROM voicebank.utilisateurs WHERE nom = :u", {"u": u.nom}).lignes[0]
    return {"type": "essai" if u.role == "visiteur" else "abonnement", "lecture_seule": True,
            "expire": u.acces_expire, "formule": l.formule, "nom_complet": l.nom_complet,
            "fin": (l.essai_fin if u.role == "visiteur" else l.abonnement_fin).isoformat()
                   if (l.essai_fin if u.role == "visiteur" else l.abonnement_fin) else None,
            "secondes_restantes": int(l.secondes_restantes or 0),
            "questions_jour": int(l.questions_jour), "quota_questions": _quota(u)}


def _quota(u: Utilisateur) -> int | None:
    if not u.externe:
        return None
    return config.QUOTA_QUESTIONS_ESSAI if u.role == "visiteur" else config.QUOTA_QUESTIONS_CLIENT


def _verifier_quota(u: Utilisateur):
    quota = _quota(u)
    if quota is None:
        return
    n = db.ecrire("SELECT COUNT(*) FROM voicebank.logs_vocaux WHERE utilisateur = :u "
                  "AND date_requete >= CURRENT_DATE", {"u": u.nom}).scalar()
    if n >= quota:
        raise HTTPException(429, f"Quota du jour atteint ({quota} questions"
                                 f"{' pendant l’essai' if u.role == 'visiteur' else ''}). Reviens demain"
                                 f"{' ou choisis une formule' if u.role == 'visiteur' else ''}.")


def _anonyme(nom: str | None, u: Utilisateur) -> str | None:
    """Pour un visiteur, les autres comptes sont anonymisés."""
    if not u.externe or not nom or nom == u.nom:
        return nom
    return nom[:1] + "***"


# ── Essai gratuit et abonnements ─────────────────────────────────────

@app.post("/auth/essai")
@limiter.limit("3/hour")
def inscription_essai(request: Request, body: InscriptionEssai):
    if not config.INSCRIPTION_ESSAI:
        raise HTTPException(403, "Les inscriptions sont fermées pour le moment.")
    if body.site_web:                       # robot : on fait comme si tout allait bien
        raise HTTPException(400, "Inscription impossible")
    if not body.accepte_conditions:
        raise HTTPException(400, "Accepte les conditions d'utilisation pour continuer.")
    try:
        u = securite.creer_essai(body.email, body.nom_complet, body.profil, body.mot_de_passe)
    except CompteRefuse as e:
        raise HTTPException(400, str(e))
    audit.journaliser(u.nom, "essai_cree", {"profil": body.profil}, ip_client(request))
    return _reponse_jeton(u, securite.version_jeton(u.nom))


@app.get("/abonnement/formules")
def formules_abonnement():
    return {"formules": paiement.formules(), "paiement": paiement.mode(), "essai_jours": config.ESSAI_JOURS,
            "quota_essai": config.QUOTA_QUESTIONS_ESSAI, "quota_client": config.QUOTA_QUESTIONS_CLIENT,
            "inscription_ouverte": config.INSCRIPTION_ESSAI}


@app.get("/abonnement/moi")
def mon_abonnement(u: Utilisateur = Depends(utilisateur_valide)):
    return {"acces": _acces(u), "paiements": paiement.mes_paiements(u.nom) if u.externe else []}


@app.post("/abonnement/commander")
@limiter.limit("10/hour")
def commander_abonnement(request: Request, body: Commande, u: Utilisateur = Depends(utilisateur_valide)):
    if not u.externe:
        raise HTTPException(400, "Les comptes de l'organisation n'ont pas besoin d'abonnement.")
    if not body.accepte_conditions:
        raise HTTPException(400, "Accepte les conditions de vente pour continuer.")
    infos = body.organisation if body.type_client == "organisation" else body.particulier
    if infos is None:
        raise HTTPException(400, "Complète les informations demandées.")
    try:
        cmd = paiement.commander(u.nom, body.formule, body.type_client, infos.model_dump())
    except PaiementRefuse as e:
        raise HTTPException(400, str(e))
    audit.journaliser(u.nom, "abonnement_commande", {"formule": body.formule, "reference": cmd["reference"],
                                                     "montant": cmd["montant"]}, ip_client(request))
    return cmd


@app.get("/abonnement/verifier/{reference}")
@limiter.limit("30/minute")
def verifier_abonnement(request: Request, reference: str = Path(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"),
                        u: Utilisateur = Depends(utilisateur_valide)):
    try:
        res = paiement.verifier(reference, u.nom)
    except PaiementRefuse as e:
        raise HTTPException(404, str(e))
    if res["statut"] == "paye":
        audit.journaliser(u.nom, "abonnement_paye", {"reference": res["reference"], "formule": res["formule"]},
                          ip_client(request))
        res["jeton"] = _reponse_jeton(Utilisateur(u.nom, "client"), securite.version_jeton(u.nom))
    return res


@app.post("/paiements/notchpay/webhook", include_in_schema=False)
@limiter.limit("120/minute")
async def webhook_notchpay(request: Request):
    corps = await request.body()
    if len(corps) > 100_000:
        raise HTTPException(413, "Trop volumineux")
    try:
        statut = await run_in_threadpool(paiement.traiter_webhook, corps, request.headers.get("x-notch-signature"))
    except PaiementRefuse:
        log.warning("Webhook NotchPay refusé (signature) depuis %s", ip_client(request))
        raise HTTPException(401, "Signature invalide")
    return {"status": "ok", "paiement": statut}


@app.get("/admin/abonnements")
def lister_abonnements(u: Utilisateur = Depends(admin_requis)):
    _, rows = _lire_app(
        "SELECT p.reference, p.utilisateur, p.formule, p.montant, p.devise, p.statut, p.fournisseur, "
        "p.date_creation, p.date_paiement, p.abonnement_fin, f.type_client, f.informations "
        "FROM voicebank.paiements p LEFT JOIN voicebank.profils_facturation f ON f.utilisateur = p.utilisateur "
        "ORDER BY p.date_creation DESC LIMIT 200")
    _, synthese = _lire_app(
        "SELECT COUNT(*) FILTER (WHERE role = 'visiteur') AS visiteurs, "
        "COUNT(*) FILTER (WHERE role = 'visiteur' AND essai_fin > LOCALTIMESTAMP) AS essais_en_cours, "
        "COUNT(*) FILTER (WHERE role = 'client' AND abonnement_fin > LOCALTIMESTAMP) AS abonnes_actifs, "
        "(SELECT COALESCE(SUM(montant), 0) FROM voicebank.paiements WHERE statut = 'paye') AS revenus "
        "FROM voicebank.utilisateurs")
    return {"status": "ok", "paiements": rows, "synthese": synthese[0] if synthese else {},
            "paiement": paiement.mode()}


def _lire_app(sql: str, params: dict | None = None):
    """Lecture avec le compte applicatif (tables invisibles pour le compte lecture seule)."""
    r = db.ecrire(sql, params)
    lignes = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in l._mapping.items()} for l in r.lignes]
    return (list(r.lignes[0]._mapping.keys()) if r.lignes else []), lignes


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
    rows = masquer_lignes(list(rows[0].keys()) if rows else [], rows, u.role)
    return {"status": "ok", "total": len(rows), "data": rows}


@app.get("/clients/{id_client}")
def detail_client(request: Request, id_client: str = Path(max_length=12),
                  u: Utilisateur = Depends(utilisateur_courant)):
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
    audit.journaliser(u.nom, "consultation_client", {"id_client": id_client}, ip_client(request))
    return {"status": "ok", "client": masquer_ligne(client[0], u.role), "transactions": transactions,
            "credits": credits}


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


@app.post("/alertes/{id_alerte}/traiter")
def traiter_alerte(request: Request, body: TraitementAlerte, id_alerte: int = Path(ge=1),
                   u: Utilisateur = Depends(interne_requis)):
    res = db.ecrire(
        "UPDATE voicebank.alertes_fraude SET traitee = TRUE, decision = :d, commentaire = :c, "
        "traitee_par = :u, date_traitement = NOW() WHERE id_alerte = :id AND traitee = FALSE",
        {"d": body.decision, "c": body.commentaire, "u": u.nom, "id": id_alerte})
    if res.rowcount == 0:
        _, existe = _lire("SELECT traitee FROM voicebank.alertes_fraude WHERE id_alerte = :id", {"id": id_alerte})
        raise HTTPException(409 if existe else 404, "Alerte déjà traitée" if existe else "Alerte introuvable")
    audit.journaliser(u.nom, "alerte_traitee", {"id_alerte": id_alerte, "decision": body.decision},
                      ip_client(request))
    return {"status": "ok", "id_alerte": id_alerte, "decision": body.decision, "traitee_par": u.nom}


@app.get("/alertes/stats")
def stats_alertes(u: Utilisateur = Depends(utilisateur_courant)):
    _, rows = _lire("SELECT COUNT(*) FILTER (WHERE NOT traitee) AS a_traiter, "
                    "COUNT(*) FILTER (WHERE decision = 'Fraude confirmée') AS confirmees, "
                    "COUNT(*) FILTER (WHERE decision = 'Faux positif') AS faux_positifs "
                    "FROM voicebank.alertes_fraude")
    return {"status": "ok", **rows[0]}


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
        "a.motif, a.traitee, a.decision, a.commentaire, a.traitee_par, a.date_traitement, a.date_alerte, "
        "t.montant_fcfa, t.banque, t.ville, t.type_transaction "
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
    _verifier_quota(u)
    return _question_vers_resultat(body.texte, u, body.contexte, body.resumer)


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
    await run_in_threadpool(_verifier_quota, u)
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
                              txn.ville, txn.est_internationale, txn.date_transaction, txn.heure)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"status": "ok", **res, "modele": fraude.infos_modele()}


@app.get("/ia/modeles")
def ia_modeles(u: Utilisateur = Depends(utilisateur_courant)):
    return {"status": "ok", "fraude": fraude.infos_modele(), "credit_disponible": credit.disponible()}


# ── IA score de crédit (expliqué) ─────────────────────

def _credit_requis():
    if not credit.disponible():
        raise HTTPException(503, "Modèle de crédit non chargé")


@app.get("/ia/credit/referentiel")
def credit_referentiel(u: Utilisateur = Depends(utilisateur_courant)):
    _credit_requis()
    return {"status": "ok", "data": credit.referentiel()}


@app.post("/ia/score-credit")
def score_demande_credit(body: DemandeCredit, u: Utilisateur = Depends(utilisateur_courant)):
    _credit_requis()
    try:
        return {"status": "ok", **credit.scorer(body.model_dump(), strict=True)}
    except ValueError as e:
        raise HTTPException(422, str(e))


_SQL_CREDIT = ("SELECT cr.id_credit, cr.id_client, cr.banque, cr.type_credit, cr.garantie, cr.montant_fcfa, "
               "cr.mensualite_fcfa, cr.revenu_annuel_fcfa, cr.score_credit, cr.taux_interet_pct, cr.duree_mois, "
               "cr.statut_credit, COALESCE(cr.est_diaspora, c.est_diaspora) AS est_diaspora "
               "FROM voicebank.credits cr LEFT JOIN voicebank.clients c ON c.id_client = cr.id_client ")


@app.get("/ia/score-credit/{id_credit}")
def score_credit_existant(request: Request, id_credit: str = Path(max_length=12),
                          u: Utilisateur = Depends(utilisateur_courant)):
    _credit_requis()
    _, rows = _lire(_SQL_CREDIT + "WHERE cr.id_credit = :id", {"id": id_credit})
    if not rows:
        raise HTTPException(404, "Crédit introuvable")
    audit.journaliser(u.nom, "score_credit", {"id_credit": id_credit}, ip_client(request))
    return {"status": "ok", "credit": rows[0], **credit.scorer(rows[0], strict=False)}


@app.get("/ia/credits-a-risque")
def credits_a_risque(limit: int = Query(15, ge=1, le=100), banque: str | None = Query(None, max_length=60),
                     u: Utilisateur = Depends(utilisateur_courant)):
    """Crédits EN COURS dont le modèle anticipe le plus fort risque de défaut."""
    _credit_requis()
    where, params = "WHERE cr.statut_credit = 'En cours'", {}
    if banque:
        where += " AND cr.banque = :banque"; params["banque"] = banque
    _, rows = _lire(_SQL_CREDIT + where + " ORDER BY cr.date_debut DESC NULLS LAST LIMIT 5000", params)
    scores = [{**r, **{k: v for k, v in credit.scorer(r, strict=False).items() if k != "facteurs"}} for r in rows]
    scores.sort(key=lambda r: r["probabilite_defaut"], reverse=True)
    return {"status": "ok", "analyses": len(rows), "data": scores[:limit]}


# ── Signalements (réponse jugée fausse) ───────────────

@app.post("/signalements")
def signaler(request: Request, body: Signalement, u: Utilisateur = Depends(interne_requis)):
    res = db.ecrire("INSERT INTO voicebank.signalements (question, requete_sql, source, commentaire, utilisateur) "
                    "VALUES (:q, :s, :src, :c, :u) RETURNING id_signalement",
                    {"q": body.question, "s": body.sql, "src": body.source, "c": body.commentaire, "u": u.nom})
    id_s = res.scalar()
    audit.journaliser(u.nom, "signalement", {"id_signalement": id_s, "question": body.question},
                      ip_client(request))
    return {"status": "ok", "id_signalement": id_s,
            "message": "Merci : un administrateur va vérifier et corriger cette réponse."}


# ════════════════════════════════════════
# ADMINISTRATION
# ════════════════════════════════════════

@app.post("/sql/executer")
@limiter.limit("30/minute")
def executer_requete(request: Request, body: RequeteSQL, u: Utilisateur = Depends(admin_ou_decouverte)):
    # Lecture seule (compte lecteur + garde SQL) : un visiteur peut tester, données personnelles masquées.
    sql, colonnes, lignes = _executer_sql_valide(body.sql)
    lignes = masquer_lignes(colonnes, lignes, u.role)
    log.info("SQL manuel exécuté par %s", u.nom)
    return {"status": "ok", "colonnes": colonnes, "total": len(lignes), "data": lignes}


@app.post("/vocal/corriger")
def corriger_reponse(request: Request, body: Correction, u: Utilisateur = Depends(admin_requis)):
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
    if body.id_signalement:
        db.ecrire("UPDATE voicebank.signalements SET statut = 'Corrigé', traite_par = :u, date_traitement = NOW() "
                  "WHERE id_signalement = :id", {"u": u.nom, "id": body.id_signalement})
    audit.journaliser(u.nom, "correction_rag", {"question": question, "id_signalement": body.id_signalement},
                      ip_client(request))
    return {"status": "ok", "message": "Correction enregistrée.", "question": question, "sql_correct": sql}


@app.post("/rag/corrections/{id_correction}/supprimer")
def supprimer_correction(request: Request, id_correction: int = Path(ge=1), u: Utilisateur = Depends(admin_requis)):
    res = db.ecrire("DELETE FROM voicebank.logs_corrections WHERE id = :id RETURNING question", {"id": id_correction})
    if not res.lignes:
        raise HTTPException(404, "Correction introuvable")
    audit.journaliser(u.nom, "correction_supprimee", {"id": id_correction, "question": res.scalar()},
                      ip_client(request))
    return {"status": "ok"}


@app.get("/signalements")
def lister_signalements(statut: Literal["Ouvert", "Corrigé", "Rejeté"] | None = "Ouvert",
                        limit: int = Query(50, ge=1, le=200), u: Utilisateur = Depends(admin_ou_decouverte)):
    where, params = ("WHERE statut = :st", {"st": statut}) if statut else ("", {})
    _, rows = _lire("SELECT id_signalement, question, requete_sql, source, commentaire, utilisateur, statut, "
                    f"traite_par, date_signalement FROM voicebank.signalements {where} "
                    "ORDER BY date_signalement DESC LIMIT :limit", params | {"limit": limit})
    for r in rows:
        r["utilisateur"], r["traite_par"] = _anonyme(r["utilisateur"], u), _anonyme(r["traite_par"], u)
    return {"status": "ok", "total": len(rows), "data": rows}


@app.post("/signalements/{id_signalement}/traiter")
def traiter_signalement(request: Request, body: DecisionSignalement, id_signalement: int = Path(ge=1),
                        u: Utilisateur = Depends(admin_requis)):
    res = db.ecrire("UPDATE voicebank.signalements SET statut = :st, traite_par = :u, date_traitement = NOW() "
                    "WHERE id_signalement = :id", {"st": body.statut, "u": u.nom, "id": id_signalement})
    if res.rowcount == 0:
        raise HTTPException(404, "Signalement introuvable")
    audit.journaliser(u.nom, "signalement_traite", {"id_signalement": id_signalement, "statut": body.statut},
                      ip_client(request))
    return {"status": "ok"}


# ── Audit et fiabilité ─────────────────────────────────

@app.get("/admin/audit")
def journal_audit(action: str | None = Query(None, max_length=40), utilisateur: str | None = Query(None, max_length=64),
                  limit: int = Query(100, ge=1, le=500), u: Utilisateur = Depends(admin_ou_decouverte)):
    conditions, params = ["TRUE"], {"limit": limit}
    if u.externe:          # un visiteur ne voit que sa propre activité
        utilisateur = u.nom
    if action:
        conditions.append("action = :a"); params["a"] = action
    if utilisateur:
        conditions.append("utilisateur = :u"); params["u"] = utilisateur
    _, evenements = _lire("SELECT id_evenement, date_evenement, utilisateur, action, detail, adresse_ip "
                          f"FROM voicebank.journal_audit WHERE {' AND '.join(conditions)} "
                          "ORDER BY date_evenement DESC LIMIT :limit", params)
    filtre, p_u = ("AND utilisateur = :u", {"u": u.nom}) if u.externe else ("", {})
    _, questions = _lire("SELECT date_requete, utilisateur, texte_original AS question, succes, duree_ms "
                         f"FROM voicebank.logs_vocaux WHERE TRUE {filtre} ORDER BY date_requete DESC LIMIT 100", p_u)
    _, synthese = _lire("SELECT utilisateur, COUNT(*) AS questions, "
                        "ROUND(100.0 * AVG(CASE WHEN succes THEN 1 ELSE 0 END), 1) AS taux_succes "
                        f"FROM voicebank.logs_vocaux WHERE date_requete > NOW() - INTERVAL '30 days' {filtre} "
                        "GROUP BY utilisateur ORDER BY questions DESC", p_u)
    return {"status": "ok", "evenements": evenements, "questions": questions, "synthese_30j": synthese}


# ── Comptes utilisateurs (administrateur) ───────────────────────────
def _compte(action):
    try:
        return action()
    except CompteRefuse as e:
        raise HTTPException(400, str(e))


@app.get("/admin/utilisateurs")
def lister_utilisateurs(u: Utilisateur = Depends(admin_ou_decouverte)):
    if u.externe:
        # Démonstration : la liste des comptes internes, anonymisée, sans les visiteurs ni les clients.
        comptes = [c for c in _compte(securite.lister_comptes) if c["role"] in securite.ROLES or c["nom"] == u.nom]
        champs = ("nom", "role", "actif", "doit_changer_mdp", "verrouille", "provisoire_expire", "derniere_connexion")
        return {"gestion_comptes": True, "lecture_seule": True,
                "data": [{**{k: c.get(k) for k in champs}, "nom": _anonyme(c["nom"], u),
                          "cree_par": _anonyme(c.get("cree_par"), u)} for c in comptes]}
    if not securite.mode_base():
        return {"gestion_comptes": False, "data": [{"nom": n, "role": r, "actif": True, "cree_par": "configuration"}
                                                  for n, (r, _) in securite.COMPTES.items()]}
    return {"gestion_comptes": True, "data": _compte(securite.lister_comptes)}


@app.post("/admin/utilisateurs")
@limiter.limit("20/minute")
def creer_utilisateur(request: Request, body: NouveauCompte, u: Utilisateur = Depends(admin_requis)):
    nom = body.nom.strip().lower()
    mdp = _compte(lambda: securite.creer_compte(nom, body.role, u.nom))
    audit.journaliser(u.nom, "compte_cree", {"compte": nom, "role": body.role}, ip_client(request))
    return {"status": "ok", "nom": nom, "role": body.role, "mot_de_passe_provisoire": mdp,
            "valable_heures": int(securite.DUREE_MDP_PROVISOIRE.total_seconds() // 3600)}


@app.post("/admin/utilisateurs/{nom}/reinitialiser")
@limiter.limit("20/minute")
def reinitialiser_utilisateur(request: Request, nom: str = Path(max_length=64),
                              u: Utilisateur = Depends(admin_requis)):
    mdp = _compte(lambda: securite.reinitialiser(nom))
    audit.journaliser(u.nom, "compte_reinitialise", {"compte": nom}, ip_client(request))
    return {"status": "ok", "nom": nom, "mot_de_passe_provisoire": mdp,
            "valable_heures": int(securite.DUREE_MDP_PROVISOIRE.total_seconds() // 3600)}


@app.post("/admin/utilisateurs/{nom}/modifier")
def modifier_utilisateur(request: Request, body: ModificationCompte, nom: str = Path(max_length=64),
                         u: Utilisateur = Depends(admin_requis)):
    changements = _compte(lambda: securite.modifier(nom, u.nom, body.role, body.actif))
    if changements:
        audit.journaliser(u.nom, "compte_modifie", {"compte": nom, **changements}, ip_client(request))
    return {"status": "ok", "nom": nom, "changements": changements}


# ════════════════════════════════════════
# CONNECTEUR : bases et fichiers des organisations
# ════════════════════════════════════════

def proprietaire_sources(u: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
    """Brancher ses propres données : abonnés et administrateur (pas pendant l'essai gratuit)."""
    if u.role not in ("client", "admin"):
        raise HTTPException(403, "Brancher tes propres données est réservé aux abonnés. Pendant l'essai, "
                                 "explore la source de démonstration." if u.role == "visiteur" else
                                 "Réservé aux administrateurs.")
    return u


def _src(action):
    try:
        return action()
    except sources.SourceRefusee as e:
        raise HTTPException(404 if str(e) == "Source introuvable" else 400, str(e))


@app.get("/sources")
def lister_sources(u: Utilisateur = Depends(utilisateur_courant)):
    return {"status": "ok", "data": _src(lambda: sources.lister(u.nom)),
            "peut_ajouter": u.role in ("client", "admin"), "types": [
                {"code": k, "libelle": v["libelle"], "port": v["port"]} for k, v in sources.TYPES.items() if k != "demo"]}


@app.get("/sources/{id_source}")
def detail_source(id_source: int = Path(ge=0), u: Utilisateur = Depends(utilisateur_courant)):
    if id_source == sources.DEMO_ID:
        return {"status": "ok", "data": _detail_demo()}
    return {"status": "ok", "data": _src(lambda: sources.detail(id_source, u.nom))}


def _detail_demo():
    try:
        return sources.detail(sources.DEMO_ID, "")
    except Exception:
        log.exception("Analyse de la démonstration impossible")
        raise HTTPException(503, "Analyse de démonstration indisponible pour le moment")


@app.post("/sources/tester")
@limiter.limit("10/minute")
def tester_source(request: Request, body: ConnexionBase, u: Utilisateur = Depends(proprietaire_sources)):
    return _src(lambda: sources.tester(body.type_source, body.config()))


@app.post("/sources")
@limiter.limit("10/hour")
def creer_source(request: Request, body: NouvelleSource, synchrone: bool = Query(False),
                 u: Utilisateur = Depends(proprietaire_sources)):
    id_source = _src(lambda: sources.creer(u.nom, u.role, body.nom.strip(), body.type_source, body.config()))
    audit.journaliser(u.nom, "source_ajoutee", {"id_source": id_source, "type": body.type_source},
                      ip_client(request))
    sources.analyser_en_arriere_plan(id_source, u.nom, synchrone)
    return {"status": "ok", "id": id_source}


@app.post("/sources/fichiers")
@limiter.limit("10/hour")
async def importer_fichiers(request: Request, nom: str = Form(..., min_length=2, max_length=80),
                            fichiers: list[UploadFile] = File(...), synchrone: bool = Query(False),
                            u: Utilisateur = Depends(proprietaire_sources)):
    limite = config.CONNECTEUR_TAILLE_FICHIER_MO * 1024 * 1024
    contenus = []
    for f in fichiers[:6]:
        contenu = await f.read(limite + 1)
        if len(contenu) > limite:
            raise HTTPException(413, f"{f.filename} : fichier trop volumineux ({config.CONNECTEUR_TAILLE_FICHIER_MO} Mo maximum)")
        contenus.append(((f.filename or "fichier.csv")[:200], contenu))
    id_source = await run_in_threadpool(lambda: _src(lambda: sources.creer_depuis_fichiers(u.nom, u.role, nom.strip(), contenus)))
    audit.journaliser(u.nom, "source_ajoutee", {"id_source": id_source, "type": "fichier", "fichiers": len(contenus)},
                      ip_client(request))
    await run_in_threadpool(sources.analyser_en_arriere_plan, id_source, u.nom, synchrone)
    return {"status": "ok", "id": id_source}


@app.post("/sources/{id_source}/analyser")
@limiter.limit("10/hour")
def reanalyser_source(request: Request, id_source: int = Path(ge=1), synchrone: bool = Query(False),
                      u: Utilisateur = Depends(proprietaire_sources)):
    _src(lambda: sources.detail(id_source, u.nom))
    sources.analyser_en_arriere_plan(id_source, u.nom, synchrone)
    return {"status": "ok"}


@app.post("/sources/{id_source}/masquage")
def masquage_source(body: Masquage, id_source: int = Path(ge=1), u: Utilisateur = Depends(proprietaire_sources)):
    _src(lambda: sources.modifier_masquage(id_source, u.nom, body.masquer))
    return {"status": "ok"}


@app.post("/sources/{id_source}/supprimer")
def supprimer_source(request: Request, id_source: int = Path(ge=1), u: Utilisateur = Depends(proprietaire_sources)):
    _src(lambda: sources.supprimer(id_source, u.nom))
    audit.journaliser(u.nom, "source_supprimee", {"id_source": id_source}, ip_client(request))
    return {"status": "ok"}


@app.post("/sources/{id_source}/question")
@limiter.limit("30/minute")
def question_source(request: Request, body: QuestionSource, id_source: int = Path(ge=0),
                    u: Utilisateur = Depends(utilisateur_courant)):
    _verifier_quota(u)
    debut = time.time()
    try:
        res = sources.repondre(id_source, u.nom, u.role, body.texte.strip())
    except sources.SourceRefusee as e:
        _journaliser(body.texte, None, False, int((time.time() - debut) * 1000), u)
        raise HTTPException(404 if str(e) == "Source introuvable" else 422, str(e))
    _journaliser(body.texte, res["sql"], True, res["duree_ms"], u)
    return res


@app.post("/admin/evaluation")
def lancer_evaluation(request: Request, u: Utilisateur = Depends(admin_requis)):
    if not evaluation.lancer_en_arriere_plan(u.nom):
        raise HTTPException(409, "Une évaluation est déjà en cours")
    audit.journaliser(u.nom, "evaluation_lancee", None, ip_client(request))
    return {"status": "ok", "message": "Évaluation lancée (1 à 2 minutes avec Gemini)."}


@app.get("/admin/evaluation")
def derniere_evaluation(u: Utilisateur = Depends(admin_ou_decouverte)):
    _, rows = _lire("SELECT id_evaluation, date_evaluation, utilisateur, nb_questions, nb_reussies, taux_reussite, "
                    "gemini_actif, details FROM voicebank.evaluations ORDER BY date_evaluation DESC LIMIT 1")
    _, historique = _lire("SELECT date_evaluation, taux_reussite, gemini_actif FROM voicebank.evaluations "
                          "ORDER BY date_evaluation DESC LIMIT 10")
    if rows:
        rows[0]["utilisateur"] = _anonyme(rows[0]["utilisateur"], u)
    return {"status": "ok", "en_cours": evaluation.etat["en_cours"], "derniere": rows[0] if rows else None,
            "historique": historique}


@app.get("/rag/corrections")
def lister_corrections(limit: int = Query(50, ge=1, le=200), u: Utilisateur = Depends(admin_ou_decouverte)):
    _, rows = _lire("SELECT id, question, sql_correct, utilisee, date_ajout FROM voicebank.logs_corrections "
                    "ORDER BY utilisee DESC, date_ajout DESC LIMIT :limit", {"limit": limit})
    return {"status": "ok", "total": len(rows), "data": rows}


@app.get("/rag/stats")
def stats_rag(u: Utilisateur = Depends(admin_ou_decouverte)):
    _, c = _lire("SELECT COUNT(*) AS total, COALESCE(SUM(utilisee), 0) AS utilisations "
                 "FROM voicebank.logs_corrections")
    _, l = _lire("SELECT COUNT(*) AS total FROM voicebank.logs_vocaux")
    return {"status": "ok", "nb_corrections": c[0]["total"],
            "total_utilisations": c[0]["utilisations"], "nb_questions_posees": l[0]["total"]}
