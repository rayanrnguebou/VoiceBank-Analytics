"""Administration de la plateforme : audit, comptes, e-mail de test."""
from fastapi import APIRouter
from .. import double_auth, protection

from .commun import (  # noqa: F401
    Depends,
    EmailTest,
    HTTPException,
    ModificationCompte,
    NouveauCompte,
    Path,
    Query,
    Request,
    Utilisateur,
    _anonyme,
    _compte,
    _lire,
    admin_ou_decouverte,
    admin_requis,
    audit,
    config,
    courriel,
    db,
    ip_client,
    limiter,
    securite,
)

router = APIRouter()


@router.get("/admin/audit")
def journal_audit(action: str | None = Query(None, max_length=40), utilisateur: str | None = Query(None, max_length=64),
                  limit: int = Query(100, ge=1, le=500), u: Utilisateur = Depends(admin_ou_decouverte)):
    conditions, params = ["TRUE"], {"limit": limit}
    if u.externe:          # un visiteur ne voit que sa propre activité
        utilisateur = u.nom
    if action == "securite":                  # tous les événements de sécurité (vigilance)
        conditions.append("action LIKE 'securite\\_%'")
    elif action:
        conditions.append("action = :a"); params["a"] = action
    if utilisateur:
        conditions.append("utilisateur = :u"); params["u"] = utilisateur
    _, evenements = _lire("SELECT id_evenement, date_evenement, utilisateur, action, detail, adresse_ip "
                          f"FROM voicebank.journal_audit WHERE {' AND '.join(conditions)} "
                          "ORDER BY date_evenement DESC LIMIT :limit", params)
    filtre, p_u = ("AND utilisateur = :u", {"u": u.nom}) if u.externe else ("", {})
    _, questions = _lire("SELECT date_requete, utilisateur, texte_original AS question, succes, duree_ms "
                         f"FROM voicebank.logs_vocaux WHERE TRUE {filtre} ORDER BY date_requete DESC LIMIT 100", p_u)
    _, synthese = _lire("SELECT utilisateur, COUNT(*) AS questions, "
                        "ROUND(100.0 * AVG(CASE WHEN succes THEN 1 ELSE 0 END), 1) AS taux_succes "
                        f"FROM voicebank.logs_vocaux WHERE date_requete > NOW() - INTERVAL '30 days' {filtre} "
                        "GROUP BY utilisateur ORDER BY questions DESC", p_u)
    return {"status": "ok", "evenements": evenements, "questions": questions, "synthese_30j": synthese}


@router.get("/admin/utilisateurs")
def lister_utilisateurs(u: Utilisateur = Depends(admin_ou_decouverte)):
    if u.externe:
        # Démonstration : la liste des comptes internes, anonymisée, sans les visiteurs ni les clients.
        comptes = [c for c in _compte(securite.lister_comptes) if c["role"] in securite.ROLES or c["nom"] == u.nom]
        champs = ("nom", "role", "actif", "doit_changer_mdp", "verrouille", "provisoire_expire", "derniere_connexion")
        return {"gestion_comptes": True, "lecture_seule": True,
                "data": [{**{k: c.get(k) for k in champs}, "nom": _anonyme(c["nom"], u),
                          "cree_par": _anonyme(c.get("cree_par"), u)} for c in comptes]}
    if not securite.mode_base():
        return {"gestion_comptes": False, "data": [{"nom": n, "role": r, "actif": True, "cree_par": "configuration"}
                                                  for n, (r, _) in securite.COMPTES.items()]}
    return {"gestion_comptes": True, "data": _compte(securite.lister_comptes)}


@router.post("/admin/utilisateurs")
@limiter.limit("20/minute")
def creer_utilisateur(request: Request, body: NouveauCompte, u: Utilisateur = Depends(admin_requis)):
    nom = body.nom.strip().lower()
    mdp = _compte(lambda: securite.creer_compte(nom, body.role, u.nom, body.email or None))
    audit.journaliser(u.nom, "compte_cree", {"compte": nom, "role": body.role}, ip_client(request))
    return {"status": "ok", "nom": nom, "role": body.role, "mot_de_passe_provisoire": mdp,
            "valable_heures": int(securite.DUREE_MDP_PROVISOIRE.total_seconds() // 3600)}


@router.post("/admin/utilisateurs/{nom}/reinitialiser")
@limiter.limit("20/minute")
def reinitialiser_utilisateur(request: Request, nom: str = Path(max_length=64),
                              u: Utilisateur = Depends(admin_requis)):
    mdp = _compte(lambda: securite.reinitialiser(nom))
    audit.journaliser(u.nom, "compte_reinitialise", {"compte": nom}, ip_client(request))
    return {"status": "ok", "nom": nom, "mot_de_passe_provisoire": mdp,
            "valable_heures": int(securite.DUREE_MDP_PROVISOIRE.total_seconds() // 3600)}


@router.post("/admin/utilisateurs/{nom}/double-auth/reinitialiser")
@limiter.limit("20/hour")
def reinitialiser_double_auth(request: Request, nom: str = Path(max_length=64), u: Utilisateur = Depends(admin_requis)):
    """Téléphone perdu sans code de secours : le titulaire devra réactiver la double authentification."""
    if nom == u.nom:
        raise HTTPException(400, "Utilise un code de secours, ou demande à un autre administrateur.")
    if not double_auth.active(nom):
        raise HTTPException(404, "Double authentification non activée pour ce compte.")
    double_auth.desactiver(nom)
    db.ecrire("UPDATE voicebank.utilisateurs SET version_jeton = version_jeton + 1 WHERE nom = :n", {"n": nom})
    audit.journaliser(u.nom, "double_auth_reinitialisee", {"compte": nom}, ip_client(request))
    return {"status": "ok"}


@router.post("/admin/utilisateurs/{nom}/debloquer")
@limiter.limit("20/hour")
def debloquer_utilisateur(request: Request, nom: str = Path(max_length=64), u: Utilisateur = Depends(admin_requis)):
    """Lève la protection d'un compte attaqué et efface les blocages d'adresses."""
    protection.lever(nom)
    audit.journaliser(u.nom, "compte_debloque", {"compte": nom}, ip_client(request))
    return {"status": "ok"}


@router.post("/admin/utilisateurs/{nom}/modifier")
def modifier_utilisateur(request: Request, body: ModificationCompte, nom: str = Path(max_length=64),
                         u: Utilisateur = Depends(admin_requis)):
    changements = _compte(lambda: securite.modifier(nom, u.nom, body.role, body.actif))
    if changements:
        audit.journaliser(u.nom, "compte_modifie", {"compte": nom, **changements}, ip_client(request))
    return {"status": "ok", "nom": nom, "changements": changements}


@router.post("/admin/email-test")
@limiter.limit("10/hour")
def email_de_test(request: Request, body: EmailTest, u: Utilisateur = Depends(admin_requis)):
    """Envoie un e-mail de test et renvoie la raison exacte d'un échec (diagnostic Brevo / SMTP)."""
    dest = (body.destinataire or db.ecrire("SELECT email FROM voicebank.utilisateurs WHERE nom = :n",
                                           {"n": u.nom}).scalar() or "").strip().lower()
    if not dest or not securite.EMAIL_VALIDE.fullmatch(dest):
        raise HTTPException(400, "Indique une adresse, ou ajoute ton e-mail de récupération (icône 🔑).")
    try:
        courriel.envoyer_message(dest, courriel.Message(
            sujet="Test d'envoi VoiceBank Analytics", titre="L'envoi d'e-mails fonctionne",
            paragraphes=["Ce message confirme que VoiceBank Analytics peut envoyer des e-mails : codes de vérification, "
                         "invitations des membres et reçus de paiement."],
            details=[("Expéditeur", config.EMAIL_EXPEDITEUR or "—"),
                     ("Service", "Brevo" if config.BREVO_API_KEY else "SMTP" if config.SMTP_HOTE else "aucun")],
            bouton=("Ouvrir VoiceBank", config.URL_INTERFACE)))
    except courriel.EnvoiImpossible as e:
        raise HTTPException(502, str(e))
    return {"status": "ok", "message": f"E-mail de test envoyé à {dest}. Vérifie aussi les courriers indésirables."}
