"""Organisations clientes : membres, invitations, base par défaut."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import double_auth
from ..securite import CompteRefuse, utilisateur_courant
from .commun import (  # noqa: F401
    ActivationInvitation,
    Depends,
    HTTPException,
    Invitation,
    ModificationMembre,
    NomOrganisation,
    Path,
    Request,
    SourceDefaut,
    Utilisateur,
    _compte,
    _membre_org,
    _reponse_jeton,
    _source_defaut,
    admin_organisation,
    admin_requis,
    audit,
    db,
    ip_client,
    limiter,
    organisations,
)

router = APIRouter()


@router.get("/organisation")
def mon_organisation(u: Utilisateur = Depends(_membre_org)):
    return {"status": "ok", "data": _compte(lambda: organisations.infos(u))}


@router.post("/organisation/membres")
@limiter.limit("30/hour")
def inviter_membre(request: Request, body: Invitation, u: Utilisateur = Depends(admin_organisation)):
    res = _compte(lambda: organisations.inviter(u, body.email, body.nom_complet, body.role_org))
    audit.journaliser(u.nom, "membre_invite", {"compte": res["nom"], "role_org": body.role_org, "org": u.id_org,
                                               "email_envoye": res["invitation_envoyee"]}, ip_client(request))
    return {"status": "ok", **res}


@router.post("/organisation/membres/{nom}/inviter")
@limiter.limit("30/hour")
def renvoyer_invitation(request: Request, nom: str = Path(max_length=64), u: Utilisateur = Depends(admin_organisation)):
    res = _compte(lambda: organisations.renvoyer_invitation(u, nom))
    audit.journaliser(u.nom, "invitation_renvoyee", {"compte": nom, "org": u.id_org}, ip_client(request))
    return {"status": "ok", **res}


@router.post("/organisation/membres/{nom}/modifier")
def modifier_membre(request: Request, body: ModificationMembre, nom: str = Path(max_length=64),
                    u: Utilisateur = Depends(admin_organisation)):
    changements = _compte(lambda: organisations.modifier_membre(u, nom, body.role_org, body.actif))
    if changements:
        audit.journaliser(u.nom, "membre_modifie", {"compte": nom, "org": u.id_org, **changements}, ip_client(request))
    return {"status": "ok", "changements": changements}


@router.post("/organisation/membres/{nom}/double-auth/reinitialiser")
@limiter.limit("20/hour")
def reinitialiser_double_auth_membre(request: Request, nom: str = Path(max_length=64),
                                     u: Utilisateur = Depends(admin_organisation)):
    """Membre qui a perdu son téléphone et ses codes de secours : il réactivera la double authentification."""
    if nom == u.nom:
        raise HTTPException(400, "Utilise un code de secours, ou demande à un autre administrateur de l'organisation.")
    membre = db.ecrire("SELECT 1 FROM voicebank.utilisateurs WHERE nom = :n AND id_org = :o",
                       {"n": nom, "o": u.id_org}).lignes
    if not membre or not double_auth.active(nom):
        raise HTTPException(404, "Membre introuvable ou double authentification non activée.")
    double_auth.desactiver(nom)
    db.ecrire("UPDATE voicebank.utilisateurs SET version_jeton = version_jeton + 1 WHERE nom = :n", {"n": nom})
    audit.journaliser(u.nom, "double_auth_reinitialisee", {"compte": nom, "org": u.id_org}, ip_client(request))
    return {"status": "ok"}


class BasesMembre(BaseModel):
    bases: list[int] | None = Field(None, max_length=200)      # None : toutes les bases de l'organisation


@router.post("/organisation/membres/{nom}/bases")
def bases_membre(request: Request, body: BasesMembre, nom: str = Path(max_length=64),
                 u: Utilisateur = Depends(admin_organisation)):
    """Limite l'accès d'un membre à certaines bases (ou le rend à toutes)."""
    ids = _compte(lambda: organisations.definir_bases(u, nom, body.bases))
    audit.journaliser(u.nom, "acces_bases", {"compte": nom, "org": u.id_org, "bases": ids}, ip_client(request))
    return {"status": "ok", "bases": ids}


@router.get("/organisation/journal")
def journal_organisation(u: Utilisateur = Depends(utilisateur_courant)):
    """Activité de l'organisation : administrateur et auditeur uniquement."""
    try:
        return {"status": "ok", **organisations.journal(u)}
    except CompteRefuse as e:
        raise HTTPException(403, str(e))


@router.post("/organisation/nom")
def renommer_organisation(body: NomOrganisation, u: Utilisateur = Depends(admin_organisation)):
    _compte(lambda: organisations.renommer(u, body.nom))
    return {"status": "ok"}


@router.post("/auth/invitation")
@limiter.limit("10/hour")
def activer_invitation(request: Request, body: ActivationInvitation):
    """Lien reçu par e-mail : la personne choisit son mot de passe et elle est connectée."""
    u, version = _compte(lambda: organisations.activer_invitation(body.identifiant, body.jeton, body.nouveau))
    audit.journaliser(u.nom, "invitation_acceptee", {"org": u.id_org}, ip_client(request))
    return _reponse_jeton(u, version)


@router.get("/admin/organisations")
def lister_organisations(u: Utilisateur = Depends(admin_requis)):
    return {"status": "ok", "data": organisations.lister()}


@router.post("/organisation/source-defaut")
def choisir_source_defaut(request: Request, body: SourceDefaut, u: Utilisateur = Depends(admin_organisation)):
    """Base sur laquelle arrivent tous les membres de l'organisation (None : la démonstration)."""
    if body.id_source is not None:
        ok = db.ecrire("SELECT 1 FROM voicebank.sources_donnees WHERE id_source = :i AND id_org = :o",
                       {"i": body.id_source, "o": u.id_org}).lignes
        if not ok:
            raise HTTPException(404, "Source introuvable dans ton organisation")
    db.ecrire("UPDATE voicebank.organisations SET source_defaut = :i WHERE id_org = :o", {"i": body.id_source, "o": u.id_org})
    audit.journaliser(u.nom, "source_defaut", {"id_source": body.id_source, "org": u.id_org}, ip_client(request))
    return {"status": "ok", "source_defaut": _source_defaut(u)}
