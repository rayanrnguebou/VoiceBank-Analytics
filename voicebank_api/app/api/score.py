"""API de score de fraude en temps réel (appelée par le logiciel bancaire) et gestion des clés d'API."""
import time
from typing import Literal
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .. import audit, cles_api, devises, suivi
from ..connecteur import service as sources
from ..limites import ip_client, limiter
from ..securite import Utilisateur, utilisateur_courant

router = APIRouter()


class NouvelleCle(BaseModel):
    nom: str = Field(min_length=2, max_length=80)
    test: bool = False
    mode: Literal["actif", "observation"] = "actif"
    ips_autorisees: str | None = Field(None, max_length=1000)


class ModifCle(BaseModel):
    mode: Literal["actif", "observation"] | None = None
    ips_autorisees: str | None = Field(None, max_length=1000)
    changer_ips: bool = False


class OperationAScorer(BaseModel):
    reference: str | None = Field(None, max_length=120, description="Identifiant de l'opération dans votre logiciel")
    montant: float = Field(gt=0, lt=1e13)
    devise: str | None = Field(None, max_length=3, description="Monnaie du montant (par défaut : celle de la base)")
    heure: int | None = Field(None, ge=0, le=23)
    date: datetime | None = None
    categories: dict[str, str] = Field(default_factory=dict, description="Type, canal, ville… : mêmes colonnes que la base")


def _gestionnaire(id_source: int, u: Utilisateur) -> None:
    if not (u.role == "admin" or u.admin_org or (u.role == "client" and u.id_org is None)):
        raise HTTPException(403, "Seul l'administrateur de l'organisation gère les clés d'API.")
    if id_source == sources.DEMO_ID and u.role != "admin":
        raise HTTPException(403, "Les clés d'API se créent sur la base de ton organisation, pas sur la démonstration.")
    try:
        sources.detail(id_source, u.nom)
    except sources.SourceRefusee as e:
        raise HTTPException(404, str(e))


@router.get("/sources/{id_source}/cles-api")
def lister_cles(id_source: int = Path(ge=0), u: Utilisateur = Depends(utilisateur_courant)):
    _gestionnaire(id_source, u)
    return {"status": "ok", "data": cles_api.lister(id_source)}


@router.post("/sources/{id_source}/cles-api")
@limiter.limit("10/hour")
def creer_cle(request: Request, body: NouvelleCle, id_source: int = Path(ge=0), u: Utilisateur = Depends(utilisateur_courant)):
    _gestionnaire(id_source, u)
    try:
        c = cles_api.creer(id_source, body.nom, u.nom, test=body.test, mode=body.mode, ips=body.ips_autorisees)
    except cles_api.CleRefusee as e:
        raise HTTPException(400, str(e))
    audit.journaliser(u.nom, "cle_api_creee", {"id_source": id_source, "nom": c["nom"], "prefixe": c["prefixe"],
                                               "test": c["test"], "mode": c["mode"], "ips": c["ips_autorisees"]}, ip_client(request))
    return {"status": "ok", "data": c}


@router.patch("/sources/{id_source}/cles-api/{id_cle}")
def modifier_cle(request: Request, body: ModifCle, id_source: int = Path(ge=0), id_cle: int = Path(ge=1),
                 u: Utilisateur = Depends(utilisateur_courant)):
    """Passer une clé de l'observation au blocage réel (ou l'inverse), changer les adresses IP autorisées."""
    _gestionnaire(id_source, u)
    try:
        c = cles_api.modifier(id_source, id_cle, body.mode, body.ips_autorisees, body.changer_ips)
    except cles_api.CleRefusee as e:
        raise HTTPException(400 if "introuvable" not in str(e) else 404, str(e))
    audit.journaliser(u.nom, "cle_api_modifiee", {"id_source": id_source, "id_cle": id_cle, "mode": c["mode"],
                                                  "ips": c["ips_autorisees"]}, ip_client(request))
    return {"status": "ok", "data": {k: v for k, v in c.items() if k != "cree_par"}}


@router.post("/sources/{id_source}/cles-api/{id_cle}/revoquer")
def revoquer_cle(request: Request, id_source: int = Path(ge=0), id_cle: int = Path(ge=1), u: Utilisateur = Depends(utilisateur_courant)):
    _gestionnaire(id_source, u)
    try:
        cles_api.revoquer(id_source, id_cle)
    except cles_api.CleRefusee as e:
        raise HTTPException(404, str(e))
    audit.journaliser(u.nom, "cle_api_revoquee", {"id_source": id_source, "id_cle": id_cle}, ip_client(request))
    return {"status": "ok"}


def _cle(authorization: str | None, x_cle_api: str | None) -> str:
    if x_cle_api:
        return x_cle_api.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


@router.post("/api/v1/operations/score", tags=["API publique"])
@limiter.limit("600/minute")
async def scorer_operation(request: Request, body: OperationAScorer, authorization: str | None = Header(None),
                           x_cle_api: str | None = Header(None)):
    """Score de fraude d'une opération AVANT sa validation. Réponse : décision (accepter, vérifier, bloquer), score
    (rang parmi les opérations habituelles de la base, de 0 à 1), niveau et raisons lisibles. Une opération jugée
    Élevée ou Critique crée une alerte dans VoiceBank pour l'équipe.

    Clé en mode « observation » : la décision renvoyée est toujours « accepter » (rien n'est bloqué) et celle de
    VoiceBank est dans `decision_voicebank`, pour comparer avant d'activer. Clé de test (« vb_test_… ») : même
    réponse qu'en réel, mais aucune alerte n'est créée."""
    debut = time.perf_counter()
    try:
        k = await run_in_threadpool(cles_api.verifier, _cle(authorization, x_cle_api), ip_client(request))
    except cles_api.IpRefusee as e:
        raise HTTPException(403, str(e))
    except cles_api.CleRefusee as e:
        raise HTTPException(401, str(e), headers={"WWW-Authenticate": "Bearer"})
    id_source, compte, id_cle = k["source"], k["nom"], k["id_cle"]
    base = sources.monnaie(id_source, compte)
    devise = (body.devise or base).upper()
    if devise not in devises.DEVISES:
        raise HTTPException(422, f"Monnaie inconnue : {devise}")
    heure = body.heure if body.heure is not None else (body.date.hour if body.date else None)
    try:
        # Colonnes non transmises : valeur la plus courante de la base (sinon « jamais observée » gonflerait le score)
        f = await run_in_threadpool(sources.formulaire_operation, id_source, compte, base)
        categories, supposees = dict(body.categories), {}
        for c in f["categories"]:
            if not categories.get(c["colonne"]) and c["valeurs"]:
                categories[c["colonne"]] = supposees[c["colonne"]] = c["valeurs"][0]
        r = await run_in_threadpool(sources.analyser_operation, id_source, compte, body.montant, heure, categories, devise)
    except sources.SourceRefusee as e:
        raise HTTPException(422, str(e))
    niveau = r["niveau_risque"]
    decision = cles_api.DECISIONS.get(niveau, "accepter")
    alerte = None
    if decision != "accepter" and id_source != sources.DEMO_ID and not k["test"]:
        op = {"id": f"api:{body.reference}" if body.reference else None, "date": (body.date or datetime.now()).isoformat(),
              "montant": devises.convertir(body.montant, devise, base), "niveau_risque": niveau, "score": r["score_anomalie"],
              "raisons": r["facteurs"], "categories": categories}
        nouvelles = await run_in_threadpool(suivi.enregistrer, id_source, [op])
        alerte = nouvelles[0]["id_suivi"] if nouvelles else None
    observation = k["mode"] == "observation"
    reponse = {"reference": body.reference, "decision": "accepter" if observation else decision,
               "decision_voicebank": decision, "mode": "test" if k["test"] else k["mode"], "niveau": niveau, "score": r["score_anomalie"],
               "raisons": [{"variable": x["variable"], "detail": x.get("detail") or x.get("valeur")} for x in r["facteurs"]],
               "recommandation": (r.get("recommandations") or [None])[0], "explication": r.get("explication"),
               "alerte_creee": alerte is not None, "id_alerte": alerte, "valeurs_supposees": supposees,
               "colonnes_attendues": [c["colonne"] for c in f["categories"]]}
    duree = int((time.perf_counter() - debut) * 1000)
    await run_in_threadpool(cles_api.noter_appel, id_cle, id_source, reponse, body.montant, devise, duree, reponse["mode"])
    # Jeu de caractères explicite : sinon certains clients (PowerShell 5) lisent l'UTF-8 comme du Latin-1 (« Ã© »)
    return JSONResponse(reponse, media_type="application/json; charset=utf-8")


# ── Suivi en direct des logiciels branchés ───────────────────────────

def _membre(id_source: int, u: Utilisateur) -> None:
    try:
        sources.detail(id_source, u.nom)
    except sources.SourceRefusee as e:
        raise HTTPException(404, str(e))


@router.get("/sources/{id_source}/logiciels")
def logiciels_branches(id_source: int = Path(ge=0), u: Utilisateur = Depends(utilisateur_courant)):
    """Logiciels branchés sur la base (clés d'API) et leur état : en ligne si un appel a eu lieu dans les 10 minutes."""
    _membre(id_source, u)
    return {"status": "ok", "data": [{k: v for k, v in c.items() if k != "cree_par"} for c in cles_api.lister(id_source)
                                     if c["premiere_utilisation"] or not c["revoquee"]]}


@router.get("/sources/{id_source}/cles-api/{id_cle}/activite")
@limiter.limit("60/minute")
def activite_logiciel(request: Request, id_source: int = Path(ge=0), id_cle: int = Path(ge=1), apres: int = Query(0, ge=0),
                      u: Utilisateur = Depends(utilisateur_courant)):
    """Tableau de bord en direct : chiffres du jour, 24 dernières heures, derniers appels (ceux après `apres`)."""
    _membre(id_source, u)
    try:
        return {"status": "ok", "data": cles_api.activite(id_source, id_cle, apres)}
    except cles_api.CleRefusee as e:
        raise HTTPException(404, str(e))
