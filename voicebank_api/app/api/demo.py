"""Banque de démonstration : tableau de bord, clients, alertes, crédits, modèles d'IA."""
from fastapi import APIRouter

from .commun import (  # noqa: F401
    DemandeCredit,
    Depends,
    HTTPException,
    Literal,
    Path,
    Query,
    Request,
    Signalement,
    TraitementAlerte,
    TransactionAnalyse,
    Utilisateur,
    _SQL_CREDIT,
    _cache_risques,
    _credit_requis,
    _lire,
    audit,
    credit,
    db,
    fraude,
    interne_requis,
    ip_client,
    masquer_ligne,
    masquer_lignes,
    time,
    utilisateur_courant,
)

router = APIRouter()


@router.get("/dashboard")
def dashboard(u: Utilisateur = Depends(utilisateur_courant)):
    _, rows = _lire("SELECT * FROM voicebank.v_dashboard_global")
    return {"status": "ok", "data": rows[0] if rows else {}}


@router.get("/stats/global")
def stats_global(u: Utilisateur = Depends(utilisateur_courant)):
    requetes = {
        "clients_par_banque": "SELECT * FROM voicebank.v_clients_par_banque",
        "transactions_mois": (
            "SELECT * FROM (SELECT mois, SUM(nb_transactions) AS nb_transactions, SUM(nb_fraudes) AS nb_fraudes, "
            "SUM(volume_fcfa) AS volume_fcfa FROM voicebank.v_transactions_mensuelles GROUP BY mois "
            "ORDER BY mois DESC LIMIT 12) m ORDER BY mois"),
        "portefeuille_credit": "SELECT * FROM voicebank.v_portefeuille_credit",
    }
    return {"status": "ok", "data": {k: _lire(sql)[1] for k, sql in requetes.items()}}


@router.get("/clients")
def lister_clients(
    banque: str | None = Query(None, max_length=60), ville: str | None = Query(None, max_length=50),
    pays: str | None = Query(None, max_length=60), diaspora: Literal["Oui", "Non"] | None = None,
    risque: Literal["Faible", "Moyen", "Élevé"] | None = None,
    limit: int = Query(50, ge=1, le=200), u: Utilisateur = Depends(utilisateur_courant),
):
    filtres = {"banque": banque, "ville_compte": ville, "pays_residence": pays,
               "est_diaspora": diaspora, "score_risque": risque}
    conditions = [f"{col} = :{col}" for col, v in filtres.items() if v is not None]
    params = {col: v for col, v in filtres.items() if v is not None} | {"limit": limit}
    where = " AND ".join(conditions) or "TRUE"
    _, rows = _lire(
        "SELECT id_client, nom, prenom, banque, ville_compte, pays_residence, est_diaspora, "
        f"solde_fcfa, score_risque, statut_compte FROM voicebank.clients WHERE {where} "
        "ORDER BY solde_fcfa DESC LIMIT :limit", params)
    rows = masquer_lignes(list(rows[0].keys()) if rows else [], rows, u.role)
    return {"status": "ok", "total": len(rows), "data": rows}


@router.get("/clients/{id_client}")
def detail_client(request: Request, id_client: str = Path(max_length=12),
                  u: Utilisateur = Depends(utilisateur_courant)):
    _, client = _lire("SELECT * FROM voicebank.clients WHERE id_client = :id", {"id": id_client})
    if not client:
        raise HTTPException(404, "Client introuvable")
    _, transactions = _lire(
        "SELECT id_transaction, type_transaction, montant_fcfa, date_transaction, statut, est_frauduleuse "
        "FROM voicebank.transactions WHERE id_client = :id ORDER BY date_transaction DESC LIMIT 10",
        {"id": id_client})
    _, credits = _lire(
        "SELECT id_credit, type_credit, montant_fcfa, statut_credit, taux_interet_pct, mensualite_fcfa "
        "FROM voicebank.credits WHERE id_client = :id", {"id": id_client})
    audit.journaliser(u.nom, "consultation_client", {"id_client": id_client}, ip_client(request))
    return {"status": "ok", "client": masquer_ligne(client[0], u.role), "transactions": transactions,
            "credits": credits}


@router.get("/transactions/recentes")
def transactions_recentes(limit: int = Query(50, ge=1, le=500), fraude_only: bool = False,
                          u: Utilisateur = Depends(utilisateur_courant)):
    where = "WHERE est_frauduleuse = 'Oui'" if fraude_only else ""
    _, rows = _lire(
        "SELECT id_transaction, id_client, banque, ville, type_transaction, montant_fcfa, statut, "
        "est_frauduleuse, est_internationale, date_transaction, heure_transaction "
        f"FROM voicebank.transactions {where} ORDER BY date_transaction DESC LIMIT :limit",
        {"limit": limit})
    return {"status": "ok", "total": len(rows), "data": rows}


@router.post("/alertes/{id_alerte}/traiter")
def traiter_alerte(request: Request, body: TraitementAlerte, id_alerte: int = Path(ge=1),
                   u: Utilisateur = Depends(interne_requis)):
    res = db.ecrire(
        "UPDATE voicebank.alertes_fraude SET traitee = TRUE, decision = :d, commentaire = :c, "
        "traitee_par = :u, date_traitement = NOW() WHERE id_alerte = :id AND traitee = FALSE",
        {"d": body.decision, "c": body.commentaire, "u": u.nom, "id": id_alerte})
    if res.rowcount == 0:
        _, existe = _lire("SELECT traitee FROM voicebank.alertes_fraude WHERE id_alerte = :id", {"id": id_alerte})
        raise HTTPException(409 if existe else 404, "Alerte déjà traitée" if existe else "Alerte introuvable")
    audit.journaliser(u.nom, "alerte_traitee", {"id_alerte": id_alerte, "decision": body.decision},
                      ip_client(request))
    return {"status": "ok", "id_alerte": id_alerte, "decision": body.decision, "traitee_par": u.nom}


@router.get("/alertes/stats")
def stats_alertes(u: Utilisateur = Depends(utilisateur_courant)):
    _, rows = _lire("SELECT COUNT(*) FILTER (WHERE NOT traitee) AS a_traiter, "
                    "COUNT(*) FILTER (WHERE decision = 'Fraude confirmée') AS confirmees, "
                    "COUNT(*) FILTER (WHERE decision = 'Faux positif') AS faux_positifs "
                    "FROM voicebank.alertes_fraude")
    return {"status": "ok", **rows[0]}


@router.get("/alertes/fraude")
def alertes_fraude(niveau: Literal["Faible", "Moyen", "Élevé", "Critique"] | None = None,
                   traitee: bool | None = None, limit: int = Query(50, ge=1, le=200),
                   u: Utilisateur = Depends(utilisateur_courant)):
    conditions, params = ["TRUE"], {"limit": limit}
    if niveau:
        conditions.append("a.niveau_alerte = :niveau"); params["niveau"] = niveau
    if traitee is not None:
        conditions.append("a.traitee = :traitee"); params["traitee"] = traitee
    _, rows = _lire(
        "SELECT a.id_alerte, a.id_transaction, a.id_client, a.score_anomalie, a.niveau_alerte, "
        "a.motif, a.traitee, a.decision, a.commentaire, a.traitee_par, a.date_traitement, a.date_alerte, "
        "t.montant_fcfa, t.banque, t.ville, t.type_transaction "
        "FROM voicebank.alertes_fraude a LEFT JOIN voicebank.transactions t "
        f"ON a.id_transaction = t.id_transaction WHERE {' AND '.join(conditions)} "
        "ORDER BY a.score_anomalie DESC LIMIT :limit", params)
    return {"status": "ok", "total": len(rows), "data": rows}


@router.get("/credits/portefeuille")
def portefeuille_credit(statut: Literal["En cours", "Remboursé", "En retard", "Défaut"] | None = None,
                        u: Utilisateur = Depends(utilisateur_courant)):
    where = "WHERE statut_credit = :statut" if statut else ""
    _, rows = _lire(
        "SELECT id_credit, id_client, banque, type_credit, montant_fcfa, taux_interet_pct, "
        f"mensualite_fcfa, statut_credit, score_credit, garantie, date_debut FROM voicebank.credits {where} "
        "ORDER BY montant_fcfa DESC LIMIT 100", {"statut": statut} if statut else {})
    return {"status": "ok", "total": len(rows), "data": rows}


@router.get("/ia/referentiel")
def ia_referentiel(u: Utilisateur = Depends(utilisateur_courant)):
    return {"status": "ok", "data": fraude.referentiel()}


@router.post("/ia/analyser-transaction")
def analyser_transaction(txn: TransactionAnalyse, u: Utilisateur = Depends(utilisateur_courant)):
    if "iforest" not in fraude.modeles:
        raise HTTPException(503, "Modèle de fraude non chargé")
    try:
        res = fraude.analyser(txn.montant_fcfa, txn.type_transaction, txn.canal, txn.banque,
                              txn.ville, txn.est_internationale, txn.date_transaction, txn.heure)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"status": "ok", **res, "modele": fraude.infos_modele()}


@router.get("/ia/modeles")
def ia_modeles(u: Utilisateur = Depends(utilisateur_courant)):
    return {"status": "ok", "fraude": fraude.infos_modele(), "credit_disponible": credit.disponible()}


@router.get("/ia/credit/referentiel")
def credit_referentiel(u: Utilisateur = Depends(utilisateur_courant)):
    _credit_requis()
    return {"status": "ok", "data": credit.referentiel()}


@router.post("/ia/score-credit")
def score_demande_credit(body: DemandeCredit, u: Utilisateur = Depends(utilisateur_courant)):
    _credit_requis()
    try:
        return {"status": "ok", **credit.scorer(body.model_dump(), strict=True)}
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/ia/score-credit/{id_credit}")
def score_credit_existant(request: Request, id_credit: str = Path(max_length=12),
                          u: Utilisateur = Depends(utilisateur_courant)):
    _credit_requis()
    _, rows = _lire(_SQL_CREDIT + "WHERE cr.id_credit = :id", {"id": id_credit})
    if not rows:
        raise HTTPException(404, "Crédit introuvable")
    audit.journaliser(u.nom, "score_credit", {"id_credit": id_credit}, ip_client(request))
    return {"status": "ok", "credit": rows[0], **credit.scorer(rows[0], strict=False)}


@router.get("/ia/credits-a-risque")
def credits_a_risque(limit: int = Query(15, ge=1, le=100), banque: str | None = Query(None, max_length=60),
                     u: Utilisateur = Depends(utilisateur_courant)):
    """Crédits EN COURS dont le modèle anticipe le plus fort risque de défaut."""
    _credit_requis()
    where, params = "WHERE cr.statut_credit = 'En cours'", {}
    if banque:
        where += " AND cr.banque = :banque"; params["banque"] = banque
    cle = (banque or "", limit)
    trouve = _cache_risques.get(cle)
    if trouve and time.time() - trouve[0] < 600:          # les crédits en cours bougent peu : 10 minutes
        return trouve[1]
    _, rows = _lire(_SQL_CREDIT + where + " ORDER BY cr.date_debut DESC NULLS LAST LIMIT 5000", params)
    # Une seule prédiction pour tous les crédits ; l'explication détaillée est calculée au clic
    scores = [{**r, **s} for r, s in zip(rows, credit.scorer_lot(rows))]
    scores.sort(key=lambda r: r["probabilite_defaut"], reverse=True)
    res = {"status": "ok", "analyses": len(rows), "data": scores[:limit]}
    _cache_risques[cle] = (time.time(), res)
    return res


@router.post("/signalements")
def signaler(request: Request, body: Signalement, u: Utilisateur = Depends(interne_requis)):
    res = db.ecrire("INSERT INTO voicebank.signalements (question, requete_sql, source, commentaire, utilisateur) "
                    "VALUES (:q, :s, :src, :c, :u) RETURNING id_signalement",
                    {"q": body.question, "s": body.sql, "src": body.source, "c": body.commentaire, "u": u.nom})
    id_s = res.scalar()
    audit.journaliser(u.nom, "signalement", {"id_signalement": id_s, "question": body.question},
                      ip_client(request))
    return {"status": "ok", "id_signalement": id_s,
            "message": "Merci : un administrateur va vérifier et corriger cette réponse."}
