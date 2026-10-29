"""Connexion, sessions, mot de passe, essai gratuit."""
from fastapi import APIRouter

from .. import antirobot

from .commun import (  # noqa: F401
    ChangementMdp,
    CompteRefuse,
    ConfirmationCode,
    DemandeCode,
    Depends,
    EmailRecuperation,
    HTTPException,
    Identifiants,
    InscriptionEssai,
    MESSAGE_CODE,
    Request,
    Utilisateur,
    _acces,
    _reponse_jeton,
    audit,
    authentifier,
    config,
    courriel,
    db,
    ip_client,
    limiter,
    log,
    maintenance,
    organisations,
    recuperation,
    reponse_maintenance,
    securite,
    time,
    utilisateur_authentifie,
    utilisateur_valide,
)

router = APIRouter()


@router.post("/auth/login")
@limiter.limit("5/minute")
def login(request: Request, body: Identifiants):
    resultat = authentifier(body.nom, body.mot_de_passe)
    ip = ip_client(request)
    if not resultat:
        log.warning("Échec de connexion pour '%s' depuis %s", body.nom, ip)
        audit.journaliser(body.nom[:64], "connexion_refusee", None, ip)
        raise HTTPException(401, "Identifiants incorrects. Après 5 échecs, le compte est bloqué 15 minutes.")
    u, version = resultat
    etat = maintenance.etat()
    if etat["active"] and u.role != "admin":
        return reponse_maintenance(etat)
    audit.journaliser(u.nom, "connexion", {"role": u.role}, ip)
    return _reponse_jeton(u, version)


@router.post("/auth/renouveler")
@limiter.limit("30/minute")
def renouveler_jeton(request: Request, u: Utilisateur = Depends(utilisateur_valide)):
    """Nouveau jeton pour une session active (l'interface l'appelle tant que l'utilisateur est actif).
    Un compte désactivé ou dont le mot de passe a changé est refusé par utilisateur_courant.
    Passé SESSION_MAX_HEURES depuis la connexion, il faut se reconnecter (même pour un utilisateur actif)."""
    debut = securite.debut_session((request.headers.get("authorization") or "")[7:])
    if debut is None or time.time() - debut > config.SESSION_MAX_HEURES * 3600:
        raise HTTPException(401, "Session expirée : reconnecte-toi.", headers={"WWW-Authenticate": "Bearer"})
    return _reponse_jeton(u, securite.version_jeton(u.nom), debut)


@router.post("/auth/mot-de-passe")
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


@router.get("/auth/options")
def options_connexion():
    """Ce que l'écran de connexion peut proposer."""
    return {"oubli_par_email": recuperation.disponible(), "anti_robot": antirobot.actif()}


def _anti_robot(jeton: str | None, ip: str | None):
    try:
        antirobot.verifier(jeton, ip)
    except antirobot.RobotSuspecte as e:
        raise HTTPException(400, str(e))


@router.post("/auth/oubli")
@limiter.limit("5/hour")
def mot_de_passe_oublie(request: Request, body: DemandeCode):
    if not recuperation.disponible():
        raise HTTPException(503, "La récupération par e-mail n'est pas activée : contacte ton administrateur.")
    ip = ip_client(request)
    _anti_robot(body.captcha, ip)
    nom = recuperation.demander(body.identifiant, ip)
    if nom:
        audit.journaliser(nom, "code_recuperation_envoye", None, ip)
    return {"status": "ok", "message": MESSAGE_CODE}


@router.post("/auth/oubli/confirmer")
@limiter.limit("10/hour")
def confirmer_code(request: Request, body: ConfirmationCode):
    try:
        nom = recuperation.confirmer(body.identifiant, body.code, body.nouveau)
    except CompteRefuse as e:
        raise HTTPException(400, str(e))
    audit.journaliser(nom, "mot_de_passe_recupere", None, ip_client(request))
    return {"status": "ok", "message": "Mot de passe changé. Tu peux te connecter."}


@router.post("/auth/email")
@limiter.limit("5/minute")
def email_recuperation(request: Request, body: EmailRecuperation, u: Utilisateur = Depends(utilisateur_authentifie)):
    """Adresse e-mail de récupération d'un compte interne (mot de passe actuel exigé)."""
    try:
        email = recuperation.definir_email(u.nom, body.mot_de_passe, body.email or None)
    except CompteRefuse as e:
        raise HTTPException(400, str(e))
    audit.journaliser(u.nom, "email_recuperation", {"defini": bool(email)}, ip_client(request))
    return {"status": "ok", "email": email}


@router.get("/auth/moi")
def moi(u: Utilisateur = Depends(utilisateur_authentifie)):
    email = (db.ecrire("SELECT email FROM voicebank.utilisateurs WHERE nom = :n", {"n": u.nom}).scalar()
             if securite.mode_base() else None)
    return {"utilisateur": u.nom, "role": u.role, "doit_changer_mot_de_passe": u.doit_changer,
            "gestion_comptes": securite.mode_base(), "acces": _acces(u), "email": email,
            "oubli_par_email": recuperation.disponible()}


@router.post("/auth/essai")
@limiter.limit("3/hour")
def inscription_essai(request: Request, body: InscriptionEssai):
    if not config.INSCRIPTION_ESSAI:
        raise HTTPException(403, "Les inscriptions sont fermées pour le moment.")
    if body.site_web:                       # robot : on fait comme si tout allait bien
        raise HTTPException(400, "Inscription impossible")
    if not body.accepte_conditions:
        raise HTTPException(400, "Accepte les conditions d'utilisation pour continuer.")
    _anti_robot(body.captcha, ip_client(request))
    try:
        u = securite.creer_essai(body.email, body.nom_complet, body.profil, body.mot_de_passe)
    except CompteRefuse as e:
        raise HTTPException(400, str(e))
    audit.journaliser(u.nom, "essai_cree", {"profil": body.profil}, ip_client(request))
    if courriel.disponible():
        courriel.envoyer_en_arriere_plan(u.nom, organisations.message_bienvenue_essai(body.nom_complet.strip(),
                                                                                      config.ESSAI_JOURS))
    return _reponse_jeton(u, securite.version_jeton(u.nom))
