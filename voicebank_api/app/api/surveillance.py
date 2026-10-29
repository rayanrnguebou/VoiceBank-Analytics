"""Surveillance des bases des organisations : suivi des alertes, fiches des modèles, rapports PDF,
préférences de notification et déclenchement des tâches automatiques."""
import hmac
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import audit, config, courriel, credit, db, fraude, rapports, securite, suivi, taches
from ..connecteur import service as sources
from ..limites import ip_client, limiter
from ..securite import Utilisateur, utilisateur_courant

router = APIRouter()


class ActionAlerte(BaseModel):
    statut: Literal["nouvelle", "en_cours", "fraude_confirmee", "fausse_alerte", "resolue"] | None = None
    assigne_a: str | None = Field(None, max_length=64)
    desassigner: bool = False
    commentaire: str | None = Field(None, max_length=2000)


class Preferences(BaseModel):
    alertes_critiques: bool = True
    resume_quotidien: bool = True
    rapport_hebdo: bool = False
    rapport_mensuel: bool = True


def _source_suivie(id_source: int, u: Utilisateur) -> dict:
    """Contrôle d'accès (même portée que la source) ; le suivi n'existe pas sur la démonstration."""
    if id_source == sources.DEMO_ID:
        raise HTTPException(404, "Le suivi des alertes concerne les bases de ton organisation, pas la démonstration.")
    try:
        return sources.detail(id_source, u.nom)
    except sources.SourceRefusee as e:
        raise HTTPException(404, str(e))


def peut_traiter(u: Utilisateur) -> bool:
    """Changer le statut d'une alerte, l'assigner ou la commenter (les rôles en lecture seule ne le peuvent pas)."""
    return getattr(u, "peut_agir", True)


@router.get("/sources/{id_source}/alertes/{id_suivi}")
def detail_alerte(id_source: int = Path(ge=0), id_suivi: int = Path(ge=1), u: Utilisateur = Depends(utilisateur_courant)):
    _source_suivie(id_source, u)
    try:
        return {"status": "ok", "data": suivi.detail(id_source, id_suivi),
                "assignables": suivi.personnes_assignables(id_source), "peut_traiter": peut_traiter(u)}
    except suivi.SuiviRefuse as e:
        raise HTTPException(404, str(e))


@router.post("/sources/{id_source}/alertes/{id_suivi}")
@limiter.limit("120/minute")
def traiter_alerte_source(request: Request, body: ActionAlerte, id_source: int = Path(ge=0), id_suivi: int = Path(ge=1),
                          u: Utilisateur = Depends(utilisateur_courant)):
    _source_suivie(id_source, u)
    if not peut_traiter(u):
        raise HTTPException(403, "Ton rôle permet de consulter les alertes, pas de les traiter.")
    try:
        d = suivi.modifier(id_source, id_suivi, u.nom, body.statut, body.assigne_a, body.desassigner, body.commentaire)
    except suivi.SuiviRefuse as e:
        raise HTTPException(404 if "introuvable" in str(e) else 400, str(e))
    audit.journaliser(u.nom, "alerte_suivie", {"id_source": id_source, "id_suivi": id_suivi, "statut": body.statut,
                                               "assigne_a": body.assigne_a, "commentaire": bool(body.commentaire)},
                      ip_client(request))
    return {"status": "ok", "data": d}


@router.get("/sources/{id_source}/suivi")
def synthese_suivi(id_source: int = Path(ge=0), u: Utilisateur = Depends(utilisateur_courant)):
    """Chiffres du suivi, règle des notifications et personnes à qui assigner une alerte."""
    _source_suivie(id_source, u)
    return {"status": "ok", "statistiques": suivi.statistiques(id_source), "notification": suivi.seuil_notification(id_source),
            "assignables": suivi.personnes_assignables(id_source), "peut_traiter": peut_traiter(u),
            "statuts": suivi.STATUTS}


@router.get("/sources/{id_source}/modeles")
@limiter.limit("20/minute")
def fiches_source(request: Request, id_source: int = Path(ge=0), u: Utilisateur = Depends(utilisateur_courant)):
    """Fiche de chaque modèle appris sur la base : données, méthode, seuils, fiabilité, dérive, limites."""
    if id_source == sources.DEMO_ID:
        return {"status": "ok", "data": fiches_demo()}
    try:
        f = sources.fiches_modeles(id_source, u.nom)
    except sources.SourceRefusee as e:
        raise HTTPException(404 if str(e) == "Source introuvable" else 422, str(e))
    if f.get("operations", {}).get("nom"):
        f["operations"]["verdicts"] = {**suivi.precision(id_source), "notification": suivi.seuil_notification(id_source)}
    return {"status": "ok", "data": f}


_cache_demo: dict = {}


def fiches_demo() -> dict:
    """Fiches des modèles pré-entraînés de la banque de démonstration."""
    import time
    if _cache_demo.get("t", 0) > time.time() - 600:
        return _cache_demo["fiches"]
    infos = fraude.infos_modele()
    meta = fraude.modeles.get("meta") or {}
    fiches = {"operations": {
        "nom": "Détection de fraude (démonstration)",
        "objectif": "Estimer la probabilité qu'une transaction soit frauduleuse et expliquer pourquoi.",
        "methode": "XGBoost (gradient boosting) à contraintes monotones, combiné à une Isolation Forest (40 % / 60 %) ; "
                   "un montant plus élevé, la nuit ou l'international ne peuvent jamais réduire le risque.",
        "donnees": {"table": "Transactions de démonstration (fictives)", "operations": infos.get("nb_transactions"),
                    "fraudes": meta.get("nb_fraudes"),
                    "variables": [fraude.LIBELLES.get(f, f) for f in meta.get("features", [])],
                    "donnees_personnelles": "aucune"},
        "appris_le": infos.get("date_entrainement"), "reapprentissage": "manuel (app.outils.entrainer_fraude)",
        "seuils": [{"niveau": "Critique", "regle": "score ≥ 80 %"}, {"niveau": "Élevé", "regle": "≥ 60 %"},
                   {"niveau": "Moyen", "regle": "≥ 40 %"}],
        "fiabilite": {"auc": infos.get("auc_xgboost"), "niveau": infos.get("fiabilite"),
                      "explication": f"AUC {str(infos.get('auc_xgboost')).replace('.', ',')} sur des transactions non vues "
                                     f"pendant l'apprentissage (0,5 = hasard, 1 = parfait) : fiabilité {infos.get('fiabilite')}."
                      if infos.get("auc_xgboost") else None},
        "derive": None,
        "limites": ["Données fictives : les fraudes de démonstration sont peu prévisibles, d'où une fiabilité moyenne.",
                    "Une banque ou une ville que le modèle n'a pas apprise reçoit l'effet moyen des valeurs connues."]}}
    fiches["credits"] = _fiche_credit_demo()
    _cache_demo.update(t=time.time(), fiches=fiches)
    return fiches


def _fiche_credit_demo() -> dict:
    if not credit.disponible():
        return {"indisponible": "Modèle de crédit non chargé."}
    from sklearn.metrics import roc_auc_score
    from .commun import _SQL_CREDIT
    try:
        _, rows = db.lire(_SQL_CREDIT + " WHERE cr.statut_credit IN ('Remboursé', 'Défaut', 'En retard') LIMIT 5000")
        y = [1 if r.get("statut_credit") in ("Défaut", "En retard") else 0 for r in rows]
        p = [s["probabilite_defaut"] for s in credit.scorer_lot(rows)]
        auc = round(float(roc_auc_score(y, p)), 3) if 0 < sum(y) < len(y) else None
    except Exception:
        rows, auc = [], None
    niveau = None if auc is None else "bonne" if auc >= 0.75 else "correcte" if auc >= 0.65 else "faible"
    return {
        "nom": "Score de crédit (démonstration)",
        "objectif": "Estimer la probabilité de défaut d'une demande ou d'un crédit en cours, facteur par facteur.",
        "methode": "XGBoost ; explication de chaque score par les contributions des variables (valeurs de Shapley).",
        "donnees": {"table": "Crédits de démonstration (fictifs)", "credits": len(rows),
                    "variables": list(credit.LIBELLES.values()), "donnees_personnelles": "aucune"},
        "appris_le": None, "reapprentissage": "manuel",
        "seuils": [{"niveau": "Critique", "regle": "probabilité > 70 %"}, {"niveau": "Élevé", "regle": "> 50 %"},
                   {"niveau": "Moyen", "regle": "> 30 %"}],
        "fiabilite": {"auc": auc, "niveau": niveau,
                      "explication": f"AUC {str(auc).replace('.', ',')} mesurée sur {len(rows)} crédits terminés de la "
                                     f"démonstration : fiabilité {niveau}." if auc else None},
        "derive": None,
        "limites": ["Mesure faite sur les crédits de démonstration, en partie vus pendant l'apprentissage : "
                    "elle surestime la fiabilité réelle."]}


@router.get("/sources/{id_source}/rapport")
@limiter.limit("10/minute")
def rapport_pdf(request: Request, id_source: int = Path(ge=0), periode: Literal["semaine", "mois"] = Query("semaine"),
                u: Utilisateur = Depends(utilisateur_courant)):
    _source_suivie(id_source, u)
    try:
        contenu, nom = rapports.generer(id_source, u.nom, periode)
    except sources.SourceRefusee as e:
        raise HTTPException(422, str(e))
    audit.journaliser(u.nom, "rapport_pdf", {"id_source": id_source, "periode": periode}, ip_client(request))
    return Response(contenu, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


# ── Préférences de notification (chaque utilisateur) ──────────────────

@router.get("/notifications")
def lire_preferences(u: Utilisateur = Depends(utilisateur_courant)):
    r = db.ecrire("SELECT alertes_critiques, resume_quotidien, rapport_hebdo, rapport_mensuel "
                  "FROM voicebank.preferences_notifications WHERE utilisateur = :u", {"u": u.nom}).lignes
    prefs = dict(r[0]._mapping) if r else Preferences().model_dump()
    email = db.ecrire("SELECT COALESCE(email, CASE WHEN nom LIKE '%@%' THEN nom END) FROM voicebank.utilisateurs "
                      "WHERE nom = :u", {"u": u.nom}).scalar() if securite.mode_base() else None
    return {"status": "ok", "data": prefs, "email": email,
            "envoi_possible": bool(email) and courriel.disponible()}


@router.post("/notifications")
def enregistrer_preferences(body: Preferences, u: Utilisateur = Depends(utilisateur_courant)):
    db.ecrire("INSERT INTO voicebank.preferences_notifications (utilisateur, alertes_critiques, resume_quotidien, "
              "rapport_hebdo, rapport_mensuel) VALUES (:u, :a, :r, :h, :m) ON CONFLICT (utilisateur) DO UPDATE SET "
              "alertes_critiques = :a, resume_quotidien = :r, rapport_hebdo = :h, rapport_mensuel = :m",
              {"u": u.nom, "a": body.alertes_critiques, "r": body.resume_quotidien, "h": body.rapport_hebdo,
               "m": body.rapport_mensuel})
    return {"status": "ok", "data": body.model_dump()}


# ── Déclenchement des tâches (GitHub Actions, chaque heure) ───────────

@router.post("/taches/executer", include_in_schema=False)
@limiter.limit("12/hour")
async def executer_taches(request: Request, x_cle_taches: str | None = Header(None)):
    if not config.TACHES_CLE or not x_cle_taches or not hmac.compare_digest(x_cle_taches, config.TACHES_CLE):
        raise HTTPException(404, "Not Found")             # rien n'indique que la route existe
    return await run_in_threadpool(taches.executer)
