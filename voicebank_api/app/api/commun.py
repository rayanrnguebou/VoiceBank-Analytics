"""Éléments partagés par les routeurs : schémas des requêtes et fonctions communes."""
import logging
import time
from datetime import date, datetime, time as heure_t
from typing import Literal
from fastapi import Depends, FastAPI, File, Form, HTTPException, Path, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
import jwt
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi.errors import RateLimitExceeded
from .. import audit, config, credit, db, devises, evaluation, fraude, nl2sql, paiement, resume, transcription
from ..garde_sql import SQLRefuse, valider_sql
from ..masquage import masquer_ligne, masquer_lignes
from .. import courriel, maintenance, organisations, recuperation, securite
from ..connecteur import service as sources
from ..paiement import PaiementRefuse
from ..securite import (CompteRefuse, Utilisateur, admin_organisation, admin_ou_decouverte, admin_requis, authentifier,
                       creer_jeton, interne_requis, utilisateur_authentifie, utilisateur_courant, utilisateur_valide)
from ..limites import ip_client, limiter  # noqa: F401

log = logging.getLogger("voicebank")
VERSION_API = "3.3.0"


def reponse_maintenance(etat: dict) -> JSONResponse:
    return JSONResponse({"detail": etat["message"], "maintenance": True, "fin_prevue": etat["fin_prevue"]},
                        status_code=503, headers={"Retry-After": "120"})


CodeDevise = Literal["XAF", "XOF", "EUR", "USD", "GBP", "CAD", "CHF", "CNY", "NGN"]


class Identifiants(BaseModel):
    nom: str = Field(min_length=1, max_length=64)
    mot_de_passe: str = Field(min_length=1, max_length=128)


class ChangementMdp(BaseModel):
    actuel: str = Field(min_length=1, max_length=128)
    nouveau: str = Field(min_length=1, max_length=128)


class Invitation(BaseModel):
    email: str = Field(min_length=5, max_length=64)
    nom_complet: str = Field(min_length=2, max_length=120)
    role_org: Literal["analyste", "admin", "lecteur", "auditeur"] = "analyste"


class ModificationMembre(BaseModel):
    role_org: Literal["analyste", "admin", "lecteur", "auditeur"] | None = None
    actif: bool | None = None


class NomOrganisation(BaseModel):
    nom: str = Field(min_length=2, max_length=150)


class ActivationInvitation(BaseModel):
    identifiant: str = Field(min_length=3, max_length=64)
    jeton: str = Field(min_length=20, max_length=100)
    nouveau: str = Field(min_length=1, max_length=128)


DATE_HEURE = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$"


class ReglageMaintenance(BaseModel):
    active: bool = False
    message: str | None = Field(None, max_length=500)
    fin_prevue: str | None = Field(None, pattern=DATE_HEURE)        # heure de retour annoncée
    annonce_message: str | None = Field(None, max_length=300)       # bandeau « maintenance prévue »
    annonce_debut: str | None = Field(None, pattern=DATE_HEURE)
    annonce_fin: str | None = Field(None, pattern=DATE_HEURE)


class EmailTest(BaseModel):
    destinataire: str | None = Field(None, max_length=64)


class DemandeCode(BaseModel):
    identifiant: str = Field(min_length=3, max_length=64)
    captcha: str | None = Field(None, max_length=2048)     # jeton Cloudflare Turnstile


class ConfirmationCode(BaseModel):
    identifiant: str = Field(min_length=3, max_length=64)
    code: str = Field(min_length=6, max_length=12)
    nouveau: str = Field(min_length=1, max_length=128)


class EmailRecuperation(BaseModel):
    mot_de_passe: str = Field(min_length=1, max_length=128)
    email: str | None = Field(None, max_length=64)


class NouveauCompte(BaseModel):
    nom: str = Field(min_length=3, max_length=32)
    role: Literal["analyste", "admin"] = "analyste"
    email: str | None = Field(None, max_length=64)      # pour « mot de passe oublié »


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
    captcha: str | None = Field(None, max_length=2048)     # jeton Cloudflare Turnstile


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
    type_source: Literal["postgresql", "mysql", "sqlserver", "oracle"]
    hote: str = Field(min_length=1, max_length=253)
    port: int | None = Field(None, ge=1, le=65535)
    base: str = Field(min_length=1, max_length=128)
    utilisateur: str = Field(min_length=1, max_length=128)
    mot_de_passe: str = Field("", max_length=256)
    ssl: Literal["prefere", "exige", "verifie", "desactive"] = "prefere"
    schema_bd: str | None = Field(None, max_length=128, pattern=r"^[A-Za-z0-9_]+$", alias="schema")

    def config(self) -> dict:
        return {"hote": self.hote.strip(), "port": self.port, "base": self.base, "utilisateur": self.utilisateur,
                "mot_de_passe": self.mot_de_passe, "ssl": self.ssl, "schema": self.schema_bd}


class NouvelleSource(ConnexionBase):
    nom: str = Field(min_length=2, max_length=80)


class QuestionSource(BaseModel):
    texte: str = Field(min_length=2, max_length=500)
    devise: CodeDevise = "XAF"


class DeviseSource(BaseModel):
    devise: CodeDevise | None = None               # None : détection automatique


class Masquage(BaseModel):
    masquer: bool


class ContexteQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    sql: str = Field(min_length=1, max_length=5000)


class QuestionVocale(BaseModel):
    devise: CodeDevise = "XAF"                     # monnaie d'affichage des montants
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
    banque: str = Field(max_length=120)


class TransactionAnalyse(BaseModel):
    montant_fcfa: float = Field(gt=0, lt=1e13)
    type_transaction: str = Field(max_length=60)
    canal: str = Field(max_length=40)
    banque: str = Field(max_length=120)
    ville: str = Field(max_length=80)
    est_internationale: Literal["Oui", "Non"] = "Non"
    date_transaction: date | None = None
    heure: heure_t | None = None


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
                            resumer: bool = True, devise: str = "XAF") -> dict:
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
    lignes, monetaires = devises.convertir_lignes(colonnes, lignes, devise)     # données stockées en FCFA
    r = resume.resumer(texte, colonnes, lignes, devise) if resumer else {}
    duree = int((time.time() - debut) * 1000)
    _journaliser(texte, sql, True, duree, u)
    return {"status": "ok", "question": texte, "sql": sql, "source": source,
            "score_rag": score, "avertissement": avertissement, "colonnes": colonnes, "total": len(lignes),
            "data": lignes, "duree_ms": duree, "resume": r.get("resume"), "resume_source": r.get("source"),
            "commentaire": r.get("commentaire"), "relance": r.get("relance"),
            "suite": suite, "question_precedente": ctx["question"] if suite else None,
            "devise": devise, "colonnes_monetaires": monetaires}


def _reponse_jeton(u: Utilisateur, version: int, debut: int | None = None) -> dict:
    return {"access_token": creer_jeton(u, version, debut), "token_type": "bearer",
            "utilisateur": u.nom, "role": u.role, "doit_changer_mot_de_passe": u.doit_changer,
            "expire_dans_min": config.JWT_DUREE_MIN, "doit_configurer_2fa": u.doit_configurer_2fa}


MESSAGE_CODE = ("Si un compte avec une adresse e-mail correspond, un code à 6 chiffres vient d'y être envoyé. "
                "Pense à regarder dans les courriers indésirables.")


def _acces(u: Utilisateur) -> dict:
    """Statut d'accès affiché par l'interface (bandeau d'essai, abonnement)."""
    if not u.externe or not securite.mode_base():
        return {"type": "interne", "lecture_seule": False, "expire": False}
    # Abonné : l'abonnement est celui de son organisation (partagé par tous ses membres)
    l = db.ecrire("SELECT u.essai_fin, COALESCE(o.abonnement_fin, u.abonnement_fin) AS abonnement_fin, "
                  "COALESCE(o.formule, u.formule) AS formule, u.nom_complet, o.nom AS organisation, o.type_org, "
                  "(SELECT COUNT(*) FROM voicebank.logs_vocaux WHERE utilisateur = :u "
                  " AND date_requete >= CURRENT_DATE) AS questions_jour, "
                  "GREATEST(EXTRACT(EPOCH FROM (CASE WHEN u.role = 'visiteur' THEN u.essai_fin "
                  " ELSE COALESCE(o.abonnement_fin, u.abonnement_fin) END) - LOCALTIMESTAMP), 0) AS secondes_restantes "
                  "FROM voicebank.utilisateurs u LEFT JOIN voicebank.organisations o ON o.id_org = u.id_org "
                  "WHERE u.nom = :u", {"u": u.nom}).lignes[0]
    fin = l.essai_fin if u.role == "visiteur" else l.abonnement_fin
    return {"type": "essai" if u.role == "visiteur" else "abonnement", "lecture_seule": True,
            "expire": u.acces_expire, "formule": l.formule, "nom_complet": l.nom_complet,
            "fin": fin.isoformat() if fin else None,
            "secondes_restantes": int(l.secondes_restantes or 0),
            "questions_jour": int(l.questions_jour), "quota_questions": _quota(u),
            "organisation": l.organisation, "type_organisation": l.type_org, "role_org": u.role_org,
            "source_defaut": _source_defaut(u),
            "gere_abonnement": u.role == "visiteur" or u.id_org is None or u.admin_org}


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


def _lire_app(sql: str, params: dict | None = None):
    """Lecture avec le compte applicatif (tables invisibles pour le compte lecture seule)."""
    r = db.ecrire(sql, params)
    lignes = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in l._mapping.items()} for l in r.lignes]
    return (list(r.lignes[0]._mapping.keys()) if r.lignes else []), lignes


def _credit_requis():
    if not credit.disponible():
        raise HTTPException(503, "Modèle de crédit non chargé")


_SQL_CREDIT = ("SELECT cr.id_credit, cr.id_client, cr.banque, cr.type_credit, cr.garantie, cr.montant_fcfa, "
               "cr.mensualite_fcfa, cr.revenu_annuel_fcfa, cr.score_credit, cr.taux_interet_pct, cr.duree_mois, "
               "cr.statut_credit, COALESCE(cr.est_diaspora, c.est_diaspora) AS est_diaspora "
               "FROM voicebank.credits cr LEFT JOIN voicebank.clients c ON c.id_client = cr.id_client ")


_cache_risques: dict = {}


def _compte(action):
    try:
        return action()
    except CompteRefuse as e:
        raise HTTPException(400, str(e))


def _membre_org(u: Utilisateur = Depends(utilisateur_valide)) -> Utilisateur:
    if u.id_org is None:
        raise HTTPException(404, "Ce compte n'appartient à aucune organisation cliente")
    return u


def _peut_brancher(u: Utilisateur) -> bool:
    return u.role == "admin" or (u.role == "client" and (u.id_org is None or u.role_org == "admin"))


def proprietaire_sources(u: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
    """Brancher et gérer les données de l'organisation : son administrateur (et l'administrateur de la
    plateforme). Les analystes les interrogent ; pas pendant l'essai gratuit."""
    if not _peut_brancher(u):
        raise HTTPException(403, "Brancher tes propres données est réservé aux abonnés. Pendant l'essai, "
                                 "explore la source de démonstration." if u.role == "visiteur" else
                                 "Seul l'administrateur de ton organisation peut brancher ou modifier les données."
                                 if u.role == "client" else "Réservé aux administrateurs.")
    return u


def _src(action):
    try:
        return action()
    except sources.SourceRefusee as e:
        raise HTTPException(404 if str(e) == "Source introuvable" else 400, str(e))


def _source_defaut(u: Utilisateur) -> dict | None:
    if u.id_org is None:
        return None
    r = db.ecrire("SELECT s.id_source, s.nom FROM voicebank.organisations o JOIN voicebank.sources_donnees s "
                  "ON s.id_source = o.source_defaut AND s.id_org = o.id_org AND s.statut = 'pret' WHERE o.id_org = :o "
                  "AND (NOT EXISTS (SELECT 1 FROM voicebank.acces_sources a WHERE a.utilisateur = :u) "
                  " OR EXISTS (SELECT 1 FROM voicebank.acces_sources a WHERE a.utilisateur = :u AND a.id_source = s.id_source))",
                  {"o": u.id_org, "u": u.nom}).lignes
    return {"id": r[0].id_source, "nom": r[0].nom} if r else None


class SourceDefaut(BaseModel):
    id_source: int | None = Field(None, ge=1)


def _detail_demo():
    try:
        return sources.detail(sources.DEMO_ID, "")
    except Exception:
        log.exception("Analyse de la démonstration impossible")
        raise HTTPException(503, "Analyse de démonstration indisponible pour le moment")


class OperationSource(BaseModel):
    montant: float = Field(gt=0, lt=1e13)
    heure: int | None = Field(None, ge=0, le=23)
    categories: dict[str, str] = Field(default_factory=dict)
    devise: CodeDevise = "XAF"


def _risque_source(action):
    try:
        return {"status": "ok", "data": action()}
    except sources.SourceRefusee as e:
        raise HTTPException(404 if str(e) == "Source introuvable" else 422, str(e))
