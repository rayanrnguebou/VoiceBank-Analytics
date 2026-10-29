"""Abonnements, paiements NotchPay, monnaies."""
from fastapi import APIRouter

from .commun import (  # noqa: F401
    Commande,
    Depends,
    HTTPException,
    PaiementRefuse,
    Path,
    Request,
    Utilisateur,
    _acces,
    _lire_app,
    _reponse_jeton,
    admin_requis,
    audit,
    config,
    devises,
    ip_client,
    limiter,
    log,
    paiement,
    run_in_threadpool,
    securite,
    utilisateur_valide,
)

router = APIRouter()


@router.get("/devises")
def liste_devises():
    """Monnaies d'affichage et taux (1 FCFA = x unités). Public : utilisé aussi par la page d'accueil."""
    return devises.liste()


@router.get("/abonnement/formules")
def formules_abonnement():
    return {"formules": paiement.formules(), "paiement": paiement.mode(), "essai_jours": config.ESSAI_JOURS,
            "quota_essai": config.QUOTA_QUESTIONS_ESSAI, "quota_client": config.QUOTA_QUESTIONS_CLIENT,
            "inscription_ouverte": config.INSCRIPTION_ESSAI}


@router.get("/abonnement/moi")
def mon_abonnement(u: Utilisateur = Depends(utilisateur_valide)):
    voit_paiements = u.externe and (u.id_org is None or u.admin_org)
    return {"acces": _acces(u), "paiements": paiement.mes_paiements(u.nom) if voit_paiements else []}


@router.post("/abonnement/commander")
@limiter.limit("10/hour")
def commander_abonnement(request: Request, body: Commande, u: Utilisateur = Depends(utilisateur_valide)):
    if not u.externe:
        raise HTTPException(400, "Les comptes de l'organisation n'ont pas besoin d'abonnement.")
    if u.id_org is not None and not u.admin_org:
        raise HTTPException(403, "L'abonnement est géré par l'administrateur de ton organisation.")
    if not body.accepte_conditions:
        raise HTTPException(400, "Accepte les conditions de vente pour continuer.")
    infos = body.organisation if body.type_client == "organisation" else body.particulier
    if infos is None:
        raise HTTPException(400, "Complète les informations demandées.")
    try:
        cmd = paiement.commander(u.nom, body.formule, body.type_client, infos.model_dump())
    except PaiementRefuse as e:
        raise HTTPException(400, str(e))
    audit.journaliser(u.nom, "abonnement_commande", {"formule": body.formule, "reference": cmd["reference"],
                                                     "montant": cmd["montant"]}, ip_client(request))
    return cmd


@router.get("/abonnement/verifier/{reference}")
@limiter.limit("30/minute")
def verifier_abonnement(request: Request, reference: str = Path(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"),
                        u: Utilisateur = Depends(utilisateur_valide)):
    try:
        res = paiement.verifier(reference, u.nom)
    except PaiementRefuse as e:
        raise HTTPException(404, str(e))
    if res["statut"] == "paye":
        audit.journaliser(u.nom, "abonnement_paye", {"reference": res["reference"], "formule": res["formule"]},
                          ip_client(request))
        res["jeton"] = _reponse_jeton(Utilisateur(u.nom, "client", session=u.session), securite.version_jeton(u.nom))
    return res


@router.post("/paiements/notchpay/webhook", include_in_schema=False)
@limiter.limit("120/minute")
async def webhook_notchpay(request: Request):
    corps = await request.body()
    if len(corps) > 100_000:
        raise HTTPException(413, "Trop volumineux")
    try:
        statut = await run_in_threadpool(paiement.traiter_webhook, corps, request.headers.get("x-notch-signature"))
    except PaiementRefuse:
        log.warning("Webhook NotchPay refusé (signature) depuis %s", ip_client(request))
        raise HTTPException(401, "Signature invalide")
    return {"status": "ok", "paiement": statut}


@router.get("/admin/abonnements")
def lister_abonnements(u: Utilisateur = Depends(admin_requis)):
    _, rows = _lire_app(
        "SELECT p.reference, p.utilisateur, p.formule, p.montant, p.devise, p.statut, p.fournisseur, "
        "p.date_creation, p.date_paiement, p.abonnement_fin, f.type_client, f.informations "
        "FROM voicebank.paiements p LEFT JOIN voicebank.profils_facturation f ON f.utilisateur = p.utilisateur "
        "ORDER BY p.date_creation DESC LIMIT 200")
    _, synthese = _lire_app(
        "SELECT COUNT(*) FILTER (WHERE role = 'visiteur') AS visiteurs, "
        "COUNT(*) FILTER (WHERE role = 'visiteur' AND essai_fin > LOCALTIMESTAMP) AS essais_en_cours, "
        "COUNT(*) FILTER (WHERE role = 'client' AND abonnement_fin > LOCALTIMESTAMP) AS abonnes_actifs, "
        "(SELECT COALESCE(SUM(montant), 0) FROM voicebank.paiements WHERE statut = 'paye') AS revenus "
        "FROM voicebank.utilisateurs")
    return {"status": "ok", "paiements": rows, "synthese": synthese[0] if synthese else {},
            "paiement": paiement.mode()}
