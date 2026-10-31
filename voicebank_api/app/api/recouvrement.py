"""Recouvrement des crédits en retard et « Valeur créée » (argent récupéré, fraude évitée, temps gagné)."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .. import audit, devises, recouvrement as R, reglementaire, suivi, valeur
from ..connecteur import service as sources
from ..limites import ip_client, limiter
from ..masquage import masquer_valeur
from ..securite import Utilisateur, utilisateur_courant
from .surveillance import peut_traiter

router = APIRouter()


class ActionDossier(BaseModel):
    nature: Literal["appel", "sms", "whatsapp", "promesse", "paiement", "commentaire", "statut", "assignation"]
    texte: str | None = Field(None, max_length=2000)
    montant: float | None = Field(None, gt=0, lt=1e15)
    date_promesse: date | None = None
    statut: Literal[tuple(R.STATUTS)] | None = None  # type: ignore[valid-type]
    assigne_a: str | None = Field(None, max_length=64)
    desassigner: bool = False


class Reglages(BaseModel):
    paiement: str = Field("", max_length=300)
    signature: str = Field("", max_length=120)
    modele: str | None = Field(None, max_length=800)


def _acces(id_source: int, u: Utilisateur) -> dict:
    try:
        return sources.detail(id_source, u.nom)
    except sources.SourceRefusee as e:
        raise HTTPException(404, str(e))


def _peut_modifier(id_source: int, u: Utilisateur) -> bool:
    """Démonstration : l'administrateur de la plateforme seulement (les visiteurs la consultent)."""
    return peut_traiter(u) and (id_source != sources.DEMO_ID or u.role == "admin")


def _assignables(id_source: int, u: Utilisateur) -> list[dict]:
    if id_source == sources.DEMO_ID:
        return [{"nom": u.nom, "nom_complet": u.nom}]
    return suivi.personnes_assignables(id_source)


def _texte_montant(v: float, devise: str) -> str:
    libelle = devises.DEVISES.get(devise, {}).get("libelle", devise)
    return f"{v:,.0f}".replace(",", " ") + f" {libelle}"


def _lire_credits(id_source: int, u: Utilisateur):
    try:
        return sources.credits_a_recouvrer(id_source, u.nom, u.role)
    except sources.SourceRefusee as e:
        raise HTTPException(404 if str(e) == "Source introuvable" else 422, str(e))


@router.get("/sources/{id_source}/recouvrement")
@limiter.limit("30/minute")
async def liste_recouvrement(request: Request, id_source: int = Path(ge=0),
                             statut: Literal[tuple(["ouverts", "clos", "tous", *R.STATUTS])] = Query("ouverts"),  # type: ignore[valid-type]
                             devise: str = Query("XAF", max_length=3), u: Utilisateur = Depends(utilisateur_courant)):
    _acces(id_source, u)
    lus, base, masquer = await run_in_threadpool(_lire_credits, id_source, u)
    await run_in_threadpool(R.synchroniser, id_source, lus["dossiers"], lus["complet"])
    par_ref = {c["ref"]: c for c in lus["dossiers"]}
    liste = await run_in_threadpool(R.dossiers, id_source, par_ref, statut)
    reglage = R.reglages(id_source)
    devise = devise.upper() if devise.upper() in devises.DEVISES else "XAF"
    conv = lambda v: devises.convertir(v, base, devise) if v is not None else None  # noqa: E731
    for d in liste:
        tel = None if masquer else d["telephone"]
        numero = R.numero_international(tel)
        d["message"] = R.message(reglage, None if masquer else d["client"], d["ref"], _texte_montant(d["reste"], base))
        d["numero"] = numero
        if masquer:
            d["client"] = masquer_valeur("nom", d["client"])
            d["telephone"] = masquer_valeur("telephone", d["telephone"])
        for k in ("montant_du", "montant_recupere", "reste", "promesse_montant", "priorite"):
            d[k] = conv(d[k])
    stats = R.statistiques(id_source)
    for k in ("reste_du", "montant_promis", "recupere"):
        stats[k] = conv(stats[k])
    return {"status": "ok", "dossiers": liste, "resume": stats, "chances": R.chances(id_source),
            "reglages": reglage, "assignables": _assignables(id_source, u), "peut_traiter": _peut_modifier(id_source, u),
            "contact": lus["contact"] and not masquer, "masquees": masquer, "table": lus["table"],
            "colonne_montant": lus["colonne_montant"], "colonne_echeance": lus["colonne_echeance"],
            "complet": lus["complet"], "devise": devise, "devise_base": base, "statuts": R.STATUTS}


@router.get("/sources/{id_source}/recouvrement/{id_dossier}")
def historique_dossier(id_source: int = Path(ge=0), id_dossier: int = Path(ge=1), u: Utilisateur = Depends(utilisateur_courant)):
    _acces(id_source, u)
    try:
        return {"status": "ok", "historique": R.historique(id_source, id_dossier)}
    except R.DossierRefuse as e:
        raise HTTPException(404, str(e))


@router.post("/sources/{id_source}/recouvrement/{id_dossier}")
@limiter.limit("120/minute")
def agir_dossier(request: Request, body: ActionDossier, id_source: int = Path(ge=0), id_dossier: int = Path(ge=1),
                 u: Utilisateur = Depends(utilisateur_courant)):
    _acces(id_source, u)
    if not _peut_modifier(id_source, u):
        raise HTTPException(403, "Ton rôle permet de consulter les dossiers, pas de les traiter.")
    if body.nature == "assignation" and not body.desassigner and body.assigne_a not in {
            p["nom"] for p in _assignables(id_source, u)}:
        raise HTTPException(400, "Cette personne n'a pas accès à cette base.")
    try:
        d = R.agir(id_source, id_dossier, u.nom, body.nature, body.texte, body.montant, body.date_promesse,
                   body.statut, body.assigne_a, body.desassigner)
    except R.DossierRefuse as e:
        raise HTTPException(404 if "introuvable" in str(e) else 400, str(e))
    audit.journaliser(u.nom, "recouvrement", {"id_source": id_source, "id_dossier": id_dossier, "action": body.nature,
                                              "montant": body.montant, "statut": d["statut"]}, ip_client(request))
    return {"status": "ok", "data": d}


@router.post("/sources/{id_source}/recouvrement-reglages")
def enregistrer_reglages(body: Reglages, id_source: int = Path(ge=0), u: Utilisateur = Depends(utilisateur_courant)):
    _acces(id_source, u)
    if not (u.role == "admin" or u.admin_org or (u.role == "client" and u.id_org is None)):
        raise HTTPException(403, "Seul l'administrateur de l'organisation règle les messages de relance.")
    if id_source == sources.DEMO_ID and u.role != "admin":
        raise HTTPException(403, "La démonstration se consulte, elle ne se règle pas.")
    return {"status": "ok", "data": R.enregistrer_reglages(id_source, u.nom, body.paiement, body.signature, body.modele)}


@router.get("/sources/{id_source}/valeur")
def valeur_creee(id_source: int = Path(ge=0), jours: int = Query(30, ge=7, le=366),
                 devise: str = Query("XAF", max_length=3), u: Utilisateur = Depends(utilisateur_courant)):
    _acces(id_source, u)
    base = sources.monnaie(id_source, u.nom)
    devise = devise.upper() if devise.upper() in devises.DEVISES else "XAF"
    v = valeur.calculer(id_source, u.nom, jours)
    conv = lambda x: devises.convertir(x, base, devise)  # noqa: E731
    for k in ("recupere", "reste_a_recouvrer", "fraude_evitee", "total"):
        v[k] = conv(v[k])
    for s in v["par_semaine"]:
        s["montant"] = conv(s["montant"])
    return {"status": "ok", "data": {**v, "devise": devise}}



@router.get("/sources/{id_source}/test-historique")
@limiter.limit("10/minute")
async def test_historique(request: Request, id_source: int = Path(ge=0), devise: str = Query("XAF", max_length=3),
                          u: Utilisateur = Depends(utilisateur_courant)):
    """Ce que VoiceBank aurait repéré sur les données passées : défauts de crédit prévus, fraudes connues retrouvées."""
    _acces(id_source, u)
    try:
        res, base = await run_in_threadpool(sources.test_historique, id_source, u.nom)
    except sources.SourceRefusee as e:
        raise HTTPException(404 if str(e) == "Source introuvable" else 422, str(e))
    devise = devise.upper() if devise.upper() in devises.DEVISES else "XAF"
    for bloc, cles in (("credits", ("montant_defauts_test", "montant_repere")), ("fraude", ("montant_fraudes", "montant_repere"))):
        for k in cles:
            if k in res[bloc]:
                res[bloc][k] = devises.convertir(res[bloc][k], base, devise)
    return {"status": "ok", "data": {**res, "devise": devise}}


# ── Documents réglementaires ─────────────────────────────────────────

def _pdf(contenu: bytes, nom: str) -> Response:
    return Response(contenu, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nom}"'})


@router.get("/sources/{id_source}/alertes/{id_suivi}/declaration")
@limiter.limit("20/minute")
def projet_declaration(request: Request, id_source: int = Path(ge=1), id_suivi: int = Path(ge=1),
                       u: Utilisateur = Depends(utilisateur_courant)):
    """Projet de déclaration de soupçon (PDF) à partir d'une fraude confirmée."""
    _acces(id_source, u)
    if not peut_traiter(u):
        raise HTTPException(403, "Ton rôle ne permet pas de préparer une déclaration.")
    try:
        contenu, nom = reglementaire.declaration_soupcon(id_source, id_suivi, u.nom)
    except reglementaire.DocumentRefuse as e:
        raise HTTPException(404 if "introuvable" in str(e) else 422, str(e))
    audit.journaliser(u.nom, "declaration_soupcon_preparee", {"id_source": id_source, "id_suivi": id_suivi}, ip_client(request))
    return _pdf(contenu, nom)


@router.get("/sources/{id_source}/etat-portefeuille")
@limiter.limit("10/minute")
async def etat_portefeuille(request: Request, id_source: int = Path(ge=0), u: Utilisateur = Depends(utilisateur_courant)):
    """État de la qualité du portefeuille de crédits (PDF) : aide à la préparation des états prudentiels."""
    _acces(id_source, u)
    try:
        contenu, nom = await run_in_threadpool(reglementaire.etat_portefeuille, id_source, u.nom, u.role)
    except sources.SourceRefusee as e:
        raise HTTPException(422, str(e))
    audit.journaliser(u.nom, "etat_portefeuille", {"id_source": id_source}, ip_client(request))
    return _pdf(contenu, nom)
