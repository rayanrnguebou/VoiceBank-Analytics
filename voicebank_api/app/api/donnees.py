"""Mon compte : export de mes données, effacement du compte (loi n° 2024/017), appareils et sessions ouvertes."""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import audit, db, donnees_personnelles as dp, securite, sessions
from ..limites import ip_client, limiter
from ..securite import Utilisateur, admin_requis, utilisateur_valide
from .commun import _reponse_jeton

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


@router.get("/moi/sessions")
def mes_sessions(u: Utilisateur = Depends(utilisateur_valide)):
    """Appareils connectés ces 30 derniers jours (session en cours, sessions actives, terminées)."""
    _base_requise()
    return {"status": "ok", "data": sessions.lister(u.nom, u.session)}


@router.post("/moi/sessions/{id_session}/deconnecter")
@limiter.limit("30/hour")
def deconnecter_session(request: Request, id_session: str = Path(min_length=8, max_length=32),
                        u: Utilisateur = Depends(utilisateur_valide)):
    _base_requise()
    if id_session == u.session:
        raise HTTPException(400, "Pour cet appareil, utilise « Se déconnecter ».")
    if not sessions.revoquer(u.nom, id_session):
        raise HTTPException(404, "Session introuvable")
    audit.journaliser(u.nom, "session_deconnectee", {"session": id_session[:8]}, ip_client(request))
    return {"status": "ok"}


@router.post("/moi/sessions/deconnecter-autres")
@limiter.limit("10/hour")
def deconnecter_autres(request: Request, u: Utilisateur = Depends(utilisateur_valide)):
    """Toutes les autres sessions sont fermées, y compris celles ouvertes avant la mise à jour (version du jeton)."""
    _base_requise()
    n = sessions.revoquer_autres(u.nom, u.session)
    version = db.ecrire("UPDATE voicebank.utilisateurs SET version_jeton = version_jeton + 1 WHERE nom = :n "
                        "RETURNING version_jeton", {"n": u.nom}).scalar()
    audit.journaliser(u.nom, "autres_sessions_deconnectees", {"nombre": n}, ip_client(request))
    return {**_reponse_jeton(u, version), "deconnectees": n}
