"""Questions en langage naturel (texte et voix), SQL, apprentissage (RAG), signalements."""
from fastapi import APIRouter

from .commun import (  # noqa: F401
    CodeDevise,
    Correction,
    DecisionSignalement,
    Depends,
    File,
    HTTPException,
    Literal,
    Path,
    Query,
    QuestionVocale,
    Request,
    RequeteSQL,
    UploadFile,
    Utilisateur,
    _anonyme,
    _executer_sql_valide,
    _lire,
    _lire_audio,
    _question_vers_resultat,
    _transcrire,
    _verifier_quota,
    admin_ou_decouverte,
    admin_requis,
    audit,
    db,
    evaluation,
    ip_client,
    limiter,
    log,
    masquer_lignes,
    nl2sql,
    run_in_threadpool,
    utilisateur_courant,
)

router = APIRouter()


@router.post("/vocal/question")
@limiter.limit("30/minute")
def question_vocale(request: Request, body: QuestionVocale, u: Utilisateur = Depends(utilisateur_courant)):
    _verifier_quota(u)
    return _question_vers_resultat(body.texte, u, body.contexte, body.resumer, body.devise)


@router.post("/vocal/transcrire")
@limiter.limit("10/minute")
async def transcrire_audio(request: Request, fichier: UploadFile = File(...),
                           u: Utilisateur = Depends(utilisateur_courant)):
    contenu, extension = await _lire_audio(fichier)
    texte, moteur = await _transcrire(contenu, extension)
    return {"status": "ok", "texte": texte, "moteur": moteur}


@router.post("/vocal/pipeline-complet")
@limiter.limit("10/minute")
async def pipeline_vocal_complet(request: Request, fichier: UploadFile = File(...), devise: CodeDevise = Query("XAF"),
                                 u: Utilisateur = Depends(utilisateur_courant)):
    await run_in_threadpool(_verifier_quota, u)
    contenu, extension = await _lire_audio(fichier)
    texte, moteur = await _transcrire(contenu, extension)
    resultat = await run_in_threadpool(_question_vers_resultat, texte, u, None, True, devise)
    return {"texte_audio": texte, "moteur_transcription": moteur, **resultat}


@router.post("/sql/executer")
@limiter.limit("30/minute")
def executer_requete(request: Request, body: RequeteSQL, u: Utilisateur = Depends(admin_ou_decouverte)):
    # Lecture seule (compte lecteur + garde SQL) : un visiteur peut tester, données personnelles masquées.
    sql, colonnes, lignes = _executer_sql_valide(body.sql)
    lignes = masquer_lignes(colonnes, lignes, u.role)
    log.info("SQL manuel exécuté par %s", u.nom)
    return {"status": "ok", "colonnes": colonnes, "total": len(lignes), "data": lignes}


@router.post("/vocal/corriger")
def corriger_reponse(request: Request, body: Correction, u: Utilisateur = Depends(admin_requis)):
    # Une correction n'est enregistrée que si elle passe la validation ET s'exécute.
    sql, _, _ = _executer_sql_valide(body.sql_correct)
    question = nl2sql.normaliser_question(body.question)
    _, existe = _lire("SELECT id FROM voicebank.logs_corrections "
                      "WHERE SIMILARITY(LOWER(question), LOWER(:q)) > 0.85 LIMIT 1", {"q": question})
    if existe:
        db.ecrire("UPDATE voicebank.logs_corrections SET sql_correct = :s, date_modif = NOW() WHERE id = :id",
                  {"s": sql, "id": existe[0]["id"]})
    else:
        db.ecrire("INSERT INTO voicebank.logs_corrections (question, sql_correct) VALUES (:q, :s)",
                  {"q": question, "s": sql})
    if body.id_signalement:
        db.ecrire("UPDATE voicebank.signalements SET statut = 'Corrigé', traite_par = :u, date_traitement = NOW() "
                  "WHERE id_signalement = :id", {"u": u.nom, "id": body.id_signalement})
    audit.journaliser(u.nom, "correction_rag", {"question": question, "id_signalement": body.id_signalement},
                      ip_client(request))
    return {"status": "ok", "message": "Correction enregistrée.", "question": question, "sql_correct": sql}


@router.post("/rag/corrections/{id_correction}/supprimer")
def supprimer_correction(request: Request, id_correction: int = Path(ge=1), u: Utilisateur = Depends(admin_requis)):
    res = db.ecrire("DELETE FROM voicebank.logs_corrections WHERE id = :id RETURNING question", {"id": id_correction})
    if not res.lignes:
        raise HTTPException(404, "Correction introuvable")
    audit.journaliser(u.nom, "correction_supprimee", {"id": id_correction, "question": res.scalar()},
                      ip_client(request))
    return {"status": "ok"}


@router.get("/signalements")
def lister_signalements(statut: Literal["Ouvert", "Corrigé", "Rejeté"] | None = "Ouvert",
                        limit: int = Query(50, ge=1, le=200), u: Utilisateur = Depends(admin_ou_decouverte)):
    where, params = ("WHERE statut = :st", {"st": statut}) if statut else ("", {})
    _, rows = _lire("SELECT id_signalement, question, requete_sql, source, commentaire, utilisateur, statut, "
                    f"traite_par, date_signalement FROM voicebank.signalements {where} "
                    "ORDER BY date_signalement DESC LIMIT :limit", params | {"limit": limit})
    for r in rows:
        r["utilisateur"], r["traite_par"] = _anonyme(r["utilisateur"], u), _anonyme(r["traite_par"], u)
    return {"status": "ok", "total": len(rows), "data": rows}


@router.post("/signalements/{id_signalement}/traiter")
def traiter_signalement(request: Request, body: DecisionSignalement, id_signalement: int = Path(ge=1),
                        u: Utilisateur = Depends(admin_requis)):
    res = db.ecrire("UPDATE voicebank.signalements SET statut = :st, traite_par = :u, date_traitement = NOW() "
                    "WHERE id_signalement = :id", {"st": body.statut, "u": u.nom, "id": id_signalement})
    if res.rowcount == 0:
        raise HTTPException(404, "Signalement introuvable")
    audit.journaliser(u.nom, "signalement_traite", {"id_signalement": id_signalement, "statut": body.statut},
                      ip_client(request))
    return {"status": "ok"}


@router.post("/admin/evaluation")
def lancer_evaluation(request: Request, u: Utilisateur = Depends(admin_requis)):
    if not evaluation.lancer_en_arriere_plan(u.nom):
        raise HTTPException(409, "Une évaluation est déjà en cours")
    audit.journaliser(u.nom, "evaluation_lancee", None, ip_client(request))
    return {"status": "ok", "message": "Évaluation lancée (1 à 2 minutes avec Gemini)."}


@router.get("/admin/evaluation")
def derniere_evaluation(u: Utilisateur = Depends(admin_ou_decouverte)):
    _, rows = _lire("SELECT id_evaluation, date_evaluation, utilisateur, nb_questions, nb_reussies, taux_reussite, "
                    "gemini_actif, details FROM voicebank.evaluations ORDER BY date_evaluation DESC LIMIT 1")
    _, historique = _lire("SELECT date_evaluation, taux_reussite, gemini_actif FROM voicebank.evaluations "
                          "ORDER BY date_evaluation DESC LIMIT 10")
    if rows:
        rows[0]["utilisateur"] = _anonyme(rows[0]["utilisateur"], u)
    return {"status": "ok", "en_cours": evaluation.etat["en_cours"], "derniere": rows[0] if rows else None,
            "historique": historique}


@router.get("/rag/corrections")
def lister_corrections(limit: int = Query(50, ge=1, le=200), u: Utilisateur = Depends(admin_ou_decouverte)):
    _, rows = _lire("SELECT id, question, sql_correct, utilisee, date_ajout FROM voicebank.logs_corrections "
                    "ORDER BY utilisee DESC, date_ajout DESC LIMIT :limit", {"limit": limit})
    return {"status": "ok", "total": len(rows), "data": rows}


@router.get("/rag/stats")
def stats_rag(u: Utilisateur = Depends(admin_ou_decouverte)):
    _, c = _lire("SELECT COUNT(*) AS total, COALESCE(SUM(utilisee), 0) AS utilisations "
                 "FROM voicebank.logs_corrections")
    _, l = _lire("SELECT COUNT(*) AS total FROM voicebank.logs_vocaux")
    return {"status": "ok", "nb_corrections": c[0]["total"],
            "total_utilisations": c[0]["utilisations"], "nb_questions_posees": l[0]["total"]}
