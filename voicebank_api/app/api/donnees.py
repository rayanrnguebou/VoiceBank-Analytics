"""Mes données : export de tout ce qui concerne le compte, effacement du compte (loi n° 2024/017)."""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import audit, donnees_personnelles as dp, securite
from ..limites import ip_client, limiter
from ..securite import Utilisateur, admin_requis, utilisateur_valide

router = APIRouter()


class DemandeEffacement(BaseModel):
    mot_de_passe: str = Field(min_length=1, max_length=200)
    confirmation: str = Field(max_length=20)


def _base_requise():
    if not securite.mode_base():
        raise HTTPException(409, "Comptes gérés par la configuration du serveur : rien à exporter ni à effacer.")


@router.get("/moi/donnees")
@limiter.limit("10/hour")
def exporter_mes_donnees(request: Request, u: Utilisateur = Depends(utilisateur_valide)):
    """Fichier JSON avec tout ce que VoiceBank garde sur le compte (droit d'accès)."""
    _base_requise()
    try:
        contenu = dp.exporter(u.nom)
    except dp.EffacementRefuse as e:
        raise HTTPException(404, str(e))
    audit.journaliser(u.nom, "export_donnees", None, ip_client(request))
    nom = f"voicebank_mes_donnees_{date.today().isoformat()}.json"
    return Response(json.dumps(contenu, ensure_ascii=False, indent=2, default=str), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"', "Cache-Control": "no-store"})


@router.get("/moi/effacement")
def effacement_possible(u: Utilisateur = Depends(utilisateur_valide)):
    """Le compte peut-il être effacé par son titulaire ? (sinon : la raison, à afficher)"""
    _base_requise()
    try:
        dp.verifier_effacement(u.nom)
        return {"possible": True, "conservation": dp.CONSERVATION}
    except dp.EffacementRefuse as e:
        return {"possible": False, "raison": str(e), "conservation": dp.CONSERVATION}


@router.post("/moi/supprimer")
@limiter.limit("5/hour")
def effacer_mon_compte(request: Request, body: DemandeEffacement, u: Utilisateur = Depends(utilisateur_valide)):
    """Effacement du compte par son titulaire : mot de passe et mot « SUPPRIMER » exigés."""
    _base_requise()
    if body.confirmation.strip().upper() not in ("SUPPRIMER", "DELETE"):
        raise HTTPException(400, "Tapez SUPPRIMER pour confirmer.")
    if not securite.authentifier(u.nom, body.mot_de_passe):
        raise HTTPException(400, "Mot de passe incorrect.")
    try:
        dp.effacer(u.nom, u.nom, ip_client(request))
    except dp.EffacementRefuse as e:
        raise HTTPException(409, str(e))
    return {"status": "ok", "message": "Votre compte et vos données personnelles ont été effacés."}


@router.post("/admin/utilisateurs/{nom}/effacer")
@limiter.limit("20/hour")
def effacer_un_compte(request: Request, nom: str = Path(min_length=1, max_length=64),
                      u: Utilisateur = Depends(admin_requis)):
    """Demande d'effacement reçue par e-mail : l'administrateur de la plateforme l'exécute."""
    try:
        pseudo = dp.effacer(nom, u.nom, ip_client(request))
    except dp.EffacementRefuse as e:
        raise HTTPException(404 if str(e) == "Compte introuvable" else 409, str(e))
    return {"status": "ok", "pseudonyme": pseudo}
