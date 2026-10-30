"""Connexion, sessions, mot de passe, essai gratuit."""
from fastapi import APIRouter

import secrets
from dataclasses import replace

import jwt
from pydantic import BaseModel, Field

from .. import antirobot, approbation, double_auth, protection, sessions, sso

from .commun import (  # noqa: F401
    ChangementMdp,
    CompteRefuse,
    ConfirmationCode,
    DemandeCode,
    Depends,
    Path,
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


def _bloque(e: Exception):
    return HTTPException(429, str(e))


def _fin_connexion(u: Utilisateur, version: int, ip: str, identifiant: str, methode: str) -> dict:
    """Identité prouvée (et double authentification passée si active) : ouvre la session."""
    protection.succes(u.nom, ip, identifiant)
    securite.noter_connexion(u.nom)
    securite.noter_langue(u.nom)
    if securite.mode_base():
        u = replace(u, doit_configurer_2fa=double_auth.requise(u.role, u.role_org) and not double_auth.active(u.nom),
                    session=sessions.ouvrir(u.nom, ip, methode, version))
    audit.journaliser(u.nom, "connexion", {"role": u.role, "methode": methode}, ip)
    return _reponse_jeton(u, version)


def _etape_suivante(u: Utilisateur, version: int, ip: str, identifiant: str, methode: str):
    """Après le mot de passe (ou Google / Microsoft) : maintenance, puis code à 6 chiffres si activé."""
    etat = maintenance.etat()
    if etat["active"] and u.role != "admin":
        return reponse_maintenance(etat)
    if securite.mode_base() and double_auth.active(u.nom):
        # « n » : aléa propre à cette tentative (deux connexions dans la même seconde n'ont pas le même jeton, donc pas
        # la même demande d'approbation sur le téléphone)
        jeton = jwt.encode({"sub": u.nom, "ver": version, "usage": "2fa", "m": methode, "id": identifiant[:254],
                            "n": secrets.token_urlsafe(8), "exp": int(time.time()) + 300}, config.JWT_SECRET,
                           algorithm="HS256")
        return {"double_auth": True, "jeton_2fa": jeton, "utilisateur": u.nom,
                "approbation": approbation.possible(u.nom)}      # téléphone enregistré : notification à approuver
    return _fin_connexion(u, version, ip, identifiant, methode)


@router.post("/auth/login")
@limiter.limit("5/minute")
def login(request: Request, body: Identifiants):
    ip = ip_client(request)
    if securite.mode_base():
        try:
            protection.verifier_adresse(body.nom, ip)
        except protection.ConnexionBloquee as e:
            raise _bloque(e)
    resultat = authentifier(body.nom, body.mot_de_passe)
    if not resultat:
        log.warning("Échec de connexion pour '%s' depuis %s", body.nom, ip)
        audit.journaliser(body.nom[:64], "connexion_refusee", None, ip)
        if securite.mode_base():
            protection.echec(body.nom, ip)
        raise HTTPException(401, "Identifiants incorrects.")
    u, version = resultat
    if securite.mode_base():
        try:
            protection.autoriser_mot_de_passe(u.nom, ip, body.nom)
        except protection.ConnexionBloquee as e:
            audit.journaliser(u.nom, "connexion_protegee", {"motif": "adresse inconnue, compte protégé"}, ip)
            raise _bloque(e)
    return _etape_suivante(u, version, ip, body.nom, "mot_de_passe")


class CodeConnexion(BaseModel):
    jeton_2fa: str = Field(min_length=1, max_length=2048)
    code: str = Field(min_length=6, max_length=12)


def _jeton_2fa(jeton_2fa: str, ip: str):
    """Tentative de connexion en attente de la double authentification : (utilisateur, version, jeton, clé)."""
    try:
        d = jwt.decode(jeton_2fa, config.JWT_SECRET, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Délai dépassé : reconnecte-toi.")
    if d.get("usage") != "2fa":
        raise HTTPException(401, "Délai dépassé : reconnecte-toi.")
    cle = f"2fa:{d['sub']}"
    try:
        protection.verifier_adresse(cle, ip)
    except protection.ConnexionBloquee as e:
        raise _bloque(e)
    try:
        u, version = sso.utilisateur(d["sub"])
    except Exception:
        raise HTTPException(401, "Délai dépassé : reconnecte-toi.")
    if version != d.get("ver"):
        raise HTTPException(401, "Délai dépassé : reconnecte-toi.")
    return u, version, d, cle


@router.post("/auth/2fa/connexion")
@limiter.limit("10/minute")
def connexion_code(request: Request, body: CodeConnexion):
    ip = ip_client(request)
    u, version, d, cle = _jeton_2fa(body.jeton_2fa, ip)
    try:
        moyen = double_auth.verifier(u.nom, body.code)
    except double_auth.DoubleAuthRefusee as e:
        protection.echec(cle, ip)
        audit.journaliser(u.nom, "double_auth_refusee", None, ip)
        raise HTTPException(401, str(e))
    protection.effacer_echecs(cle, ip)
    if moyen == "secours":
        audit.journaliser(u.nom, "code_secours_utilise", None, ip)
    return _fin_connexion(u, version, ip, d.get("id") or u.nom, f"{d.get('m', 'mot_de_passe')}+2fa")


# ── Approbation sur le téléphone ───────────────────────────────────────
class JetonConnexion(BaseModel):
    jeton_2fa: str = Field(min_length=1, max_length=2048)


class SuiviApprobation(JetonConnexion):
    id_demande: str = Field(min_length=8, max_length=32)


class AjoutTelephone(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    nom: str = Field(min_length=1, max_length=120)
    abonnement: dict


class SecretTelephone(BaseModel):
    secret: str = Field(min_length=20, max_length=100)


class ReponseTelephone(SecretTelephone):
    nombre: int | None = Field(None, ge=10, le=99)
    refuser: bool = False


def _approbation(action):
    try:
        return action()
    except approbation.ApprobationRefusee as e:
        raise HTTPException(404 if "introuvable" in str(e) else 400, str(e))


@router.post("/auth/2fa/approbation/demander")
@limiter.limit("10/minute")
def demander_approbation(request: Request, body: JetonConnexion):
    """L'ordinateur demande l'approbation : notification sur les téléphones, nombre à toucher affiché ici."""
    ip = ip_client(request)
    u, _, _, _ = _jeton_2fa(body.jeton_2fa, ip)
    navigateur = sessions.resume_navigateur(sessions._requete.get()[0])
    return _approbation(lambda: approbation.demander(u.nom, body.jeton_2fa, navigateur, ip))


@router.post("/auth/2fa/approbation/etat")
@limiter.limit("60/minute")
def suivre_approbation(request: Request, body: SuiviApprobation):
    """L'ordinateur attend (toutes les 2 s) : la session s'ouvre dès que le téléphone a approuvé."""
    ip = ip_client(request)
    u, version, d, cle = _jeton_2fa(body.jeton_2fa, ip)
    statut, nom = _approbation(lambda: approbation.etat(body.id_demande, body.jeton_2fa))
    if nom != u.nom:
        raise HTTPException(404, "Demande introuvable")
    if statut == "approuvee":
        protection.effacer_echecs(cle, ip)
        return _fin_connexion(u, version, ip, d.get("id") or u.nom, f"{d.get('m', 'mot_de_passe')}+telephone")
    if statut in ("mauvais_nombre", "pas_moi"):
        protection.echec(cle, ip)
    return {"statut": statut}


@router.get("/auth/approbation/cle")
def cle_notifications():
    """Clé publique des notifications (le navigateur du téléphone en a besoin pour s'abonner)."""
    if not securite.mode_base():
        raise HTTPException(409, "Indisponible sans base de comptes.")
    return {"cle_publique": approbation.cle_publique()}


@router.get("/auth/approbation/telephones")
def mes_telephones(u: Utilisateur = Depends(utilisateur_valide)):
    return {"status": "ok", "data": approbation.appareils(u.nom)}


@router.post("/auth/approbation/telephones")
@limiter.limit("5/hour")
def ajouter_telephone(request: Request, body: AjoutTelephone, u: Utilisateur = Depends(utilisateur_valide)):
    """Enregistre ce téléphone pour approuver les connexions (code à 6 chiffres redemandé)."""
    if not double_auth.active(u.nom):
        raise HTTPException(400, "Active d'abord la double authentification avec une application (code à 6 chiffres).")
    try:
        double_auth.verifier(u.nom, body.code)
    except double_auth.DoubleAuthRefusee as e:
        raise HTTPException(400, str(e))
    secret = _approbation(lambda: approbation.enregistrer(u.nom, body.nom, body.abonnement))
    audit.journaliser(u.nom, "telephone_approbation_ajoute", {"nom": body.nom[:60]}, ip_client(request))
    return {"status": "ok", "secret": secret}


@router.post("/auth/approbation/telephones/{id_appareil}/retirer")
def retirer_telephone(request: Request, id_appareil: int = Path(ge=1), u: Utilisateur = Depends(utilisateur_valide)):
    _approbation(lambda: approbation.retirer(u.nom, id_appareil))
    audit.journaliser(u.nom, "telephone_approbation_retire", None, ip_client(request))
    return {"status": "ok"}


@router.post("/approbation/{id_demande}")
@limiter.limit("30/minute")
def voir_demande(request: Request, body: SecretTelephone, id_demande: str = Path(min_length=8, max_length=32)):
    """Le téléphone (sans session : il prouve qu'il est enregistré par son secret) affiche la demande."""
    return _approbation(lambda: approbation.detail(id_demande, body.secret))


@router.post("/approbation/{id_demande}/repondre")
@limiter.limit("30/minute")
def repondre_demande(request: Request, body: ReponseTelephone, id_demande: str = Path(min_length=8, max_length=32)):
    if not body.refuser and body.nombre is None:
        raise HTTPException(422, "Choisis un nombre.")
    statut = _approbation(lambda: approbation.repondre(id_demande, body.secret, body.nombre, body.refuser,
                                                       ip_client(request)))
    return {"statut": statut}


class LienDeblocage(BaseModel):
    jeton: str = Field(min_length=1, max_length=2048)


@router.post("/auth/deblocage")
@limiter.limit("10/hour")
def deblocage(request: Request, body: LienDeblocage):
    """Lien reçu par e-mail par le titulaire d'un compte protégé : autorise l'appareil qui l'ouvre."""
    ip = ip_client(request)
    try:
        nom = protection.debloquer(body.jeton, ip)
    except protection.ConnexionBloquee as e:
        raise HTTPException(400, str(e))
    audit.journaliser(nom, "appareil_autorise", None, ip)
    return {"status": "ok", "message": "Cet appareil est autorisé : tu peux te connecter."}


# ── Double authentification : réglages du compte ──────────────────────

class CodeSeul(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class Desactivation(BaseModel):
    mot_de_passe: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=12)


def _2fa(fonction):
    try:
        return fonction()
    except double_auth.DoubleAuthRefusee as e:
        raise HTTPException(400, str(e))


@router.get("/auth/2fa")
def etat_double_auth(u: Utilisateur = Depends(utilisateur_authentifie)):
    return {**double_auth.etat(u.nom), "requise": double_auth.requise(u.role, u.role_org)}


@router.post("/auth/2fa/preparer")
@limiter.limit("10/hour")
def preparer_double_auth(request: Request, u: Utilisateur = Depends(utilisateur_authentifie)):
    return _2fa(lambda: double_auth.preparer(u.nom))


@router.post("/auth/2fa/activer")
@limiter.limit("10/minute")
def activer_double_auth(request: Request, body: CodeSeul, u: Utilisateur = Depends(utilisateur_authentifie)):
    codes = _2fa(lambda: double_auth.activer(u.nom, body.code))
    # Les autres sessions (ouvertes sans le code) sont fermées ; celle-ci reçoit un nouveau jeton.
    version = db.ecrire("UPDATE voicebank.utilisateurs SET version_jeton = version_jeton + 1 WHERE nom = :n "
                        "RETURNING version_jeton", {"n": u.nom}).scalar()
    audit.journaliser(u.nom, "double_auth_activee", None, ip_client(request))
    u = replace(u, doit_configurer_2fa=False)
    return {**_reponse_jeton(u, version), "codes_secours": codes}


@router.post("/auth/2fa/codes-secours")
@limiter.limit("5/hour")
def regenerer_codes(request: Request, body: CodeSeul, u: Utilisateur = Depends(utilisateur_valide)):
    _2fa(lambda: double_auth.verifier(u.nom, body.code))
    codes = _2fa(lambda: double_auth.nouveaux_codes_secours(u.nom))
    audit.journaliser(u.nom, "codes_secours_regeneres", None, ip_client(request))
    return {"codes_secours": codes}


@router.post("/auth/2fa/desactiver")
@limiter.limit("5/hour")
def desactiver_double_auth(request: Request, body: Desactivation, u: Utilisateur = Depends(utilisateur_valide)):
    if double_auth.requise(u.role, u.role_org):
        raise HTTPException(403, "La double authentification est obligatoire pour les administrateurs.")
    if not authentifier(u.nom, body.mot_de_passe):
        raise HTTPException(400, "Mot de passe incorrect.")
    _2fa(lambda: double_auth.verifier(u.nom, body.code))
    double_auth.desactiver(u.nom)
    version = db.ecrire("UPDATE voicebank.utilisateurs SET version_jeton = version_jeton + 1 WHERE nom = :n "
                        "RETURNING version_jeton", {"n": u.nom}).scalar()
    audit.journaliser(u.nom, "double_auth_desactivee", None, ip_client(request))
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
    return _reponse_jeton(replace(u, doit_changer=False), version)


@router.get("/auth/options")
def options_connexion():
    """Ce que l'écran de connexion peut proposer."""
    return {"oubli_par_email": recuperation.disponible(), "anti_robot": antirobot.actif(),
            "sso": sso.disponibles()}


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
    protection.lever(nom)               # le titulaire a prouvé qu'il reçoit les e-mails du compte
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
    securite.noter_langue(u.nom)          # l'interface l'appelle au chargement : suit le choix de langue
    email = (db.ecrire("SELECT email FROM voicebank.utilisateurs WHERE nom = :n", {"n": u.nom}).scalar()
             if securite.mode_base() else None)
    return {"utilisateur": u.nom, "role": u.role, "doit_changer_mot_de_passe": u.doit_changer,
            "doit_configurer_2fa": u.doit_configurer_2fa,
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
    version = securite.version_jeton(u.nom)
    return _reponse_jeton(replace(u, session=sessions.ouvrir(u.nom, ip_client(request), "essai", version)), version)


class RetourSSO(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    etat: str = Field(min_length=1, max_length=2048)
    verificateur: str = Field(min_length=43, max_length=128)


@router.get("/auth/sso/{fournisseur}/debut")
@limiter.limit("20/minute")
def sso_debut(request: Request, fournisseur: str):
    try:
        return sso.debut(fournisseur)
    except sso.SSORefuse as e:
        raise HTTPException(404, str(e))


@router.post("/auth/sso/{fournisseur}/fin")
@limiter.limit("10/minute")
def sso_fin(request: Request, fournisseur: str, body: RetourSSO):
    ip = ip_client(request)
    try:
        nom = sso.fin(fournisseur, body.code, body.etat, body.verificateur)
    except sso.SSORefuse as e:
        audit.journaliser("sso", "connexion_refusee", {"fournisseur": fournisseur[:20], "motif": str(e)[:200]}, ip)
        raise HTTPException(401, str(e))
    u, version = sso.utilisateur(nom)
    return _etape_suivante(u, version, ip, nom, f"sso_{fournisseur}")
