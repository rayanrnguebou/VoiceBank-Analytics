"""Questions favorites de l'assistant (relance en un clic, envoi chaque lundi par e-mail)."""
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field

from .. import favoris, securite
from .commun import CodeDevise
from ..limites import limiter
from ..securite import Utilisateur, utilisateur_courant

router = APIRouter()


class NouveauFavori(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    id_source: int = Field(0, ge=0)
    devise: CodeDevise = "XAF"


class EnvoiFavori(BaseModel):
    envoi_hebdo: bool


def _base_requise():
    if not securite.mode_base():
        raise HTTPException(409, "Favoris indisponibles sans base de comptes.")


def _favori(action):
    try:
        return action()
    except favoris.FavoriRefuse as e:
        raise HTTPException(404 if "introuvable" in str(e) else 400, str(e))


@router.get("/favoris")
def mes_favoris(u: Utilisateur = Depends(utilisateur_courant)):
    _base_requise()
    return {"status": "ok", "data": favoris.lister(u.nom)}


@router.post("/favoris")
@limiter.limit("30/hour")
def ajouter_favori(request: Request, body: NouveauFavori, u: Utilisateur = Depends(utilisateur_courant)):
    _base_requise()
    return {"status": "ok", "data": _favori(lambda: favoris.ajouter(u.nom, body.question, body.id_source, body.devise))}


@router.post("/favoris/{id_favori}")
def modifier_favori(body: EnvoiFavori, id_favori: int = Path(ge=1), u: Utilisateur = Depends(utilisateur_courant)):
    _base_requise()
    _favori(lambda: favoris.modifier(u.nom, id_favori, body.envoi_hebdo))
    return {"status": "ok"}


@router.post("/favoris/{id_favori}/supprimer")
def supprimer_favori(id_favori: int = Path(ge=1), u: Utilisateur = Depends(utilisateur_courant)):
    _base_requise()
    _favori(lambda: favoris.supprimer(u.nom, id_favori))
    return {"status": "ok"}
