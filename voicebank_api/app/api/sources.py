"""Connecteur : bases et fichiers des organisations, risques appris sur leurs données."""
from fastapi import APIRouter

from .commun import (  # noqa: F401
    CodeDevise,
    ConnexionBase,
    Depends,
    DeviseSource,
    File,
    Form,
    HTTPException,
    Masquage,
    NouvelleSource,
    OperationSource,
    Path,
    Query,
    QuestionSource,
    Request,
    UploadFile,
    Utilisateur,
    _detail_demo,
    _journaliser,
    _peut_brancher,
    _risque_source,
    _source_defaut,
    _src,
    _verifier_quota,
    audit,
    config,
    ip_client,
    limiter,
    proprietaire_sources,
    run_in_threadpool,
    sources,
    time,
    utilisateur_courant,
)

router = APIRouter()


@router.get("/sources")
def lister_sources(u: Utilisateur = Depends(utilisateur_courant)):
    defaut = _source_defaut(u)
    return {"status": "ok", "data": _src(lambda: sources.lister(u.nom)),
            "source_defaut": defaut["id"] if defaut else None, "peut_definir_defaut": u.admin_org,
            "peut_ajouter": _peut_brancher(u), "types": [
                {"code": k, "libelle": v["libelle"], "port": v["port"]} for k, v in sources.TYPES.items() if k != "demo"]}


@router.get("/sources/{id_source}")
def detail_source(id_source: int = Path(ge=0), u: Utilisateur = Depends(utilisateur_courant)):
    if id_source == sources.DEMO_ID:
        return {"status": "ok", "data": _detail_demo()}
    return {"status": "ok", "data": _src(lambda: sources.detail(id_source, u.nom))}


@router.post("/sources/tester")
@limiter.limit("10/minute")
def tester_source(request: Request, body: ConnexionBase, u: Utilisateur = Depends(proprietaire_sources)):
    return _src(lambda: sources.tester(body.type_source, body.config()))


@router.post("/sources")
@limiter.limit("10/hour")
def creer_source(request: Request, body: NouvelleSource, synchrone: bool = Query(False),
                 u: Utilisateur = Depends(proprietaire_sources)):
    id_source = _src(lambda: sources.creer(u.nom, u.role, body.nom.strip(), body.type_source, body.config()))
    audit.journaliser(u.nom, "source_ajoutee", {"id_source": id_source, "type": body.type_source},
                      ip_client(request))
    sources.analyser_en_arriere_plan(id_source, u.nom, synchrone)
    return {"status": "ok", "id": id_source}


@router.post("/sources/fichiers")
@limiter.limit("10/hour")
async def importer_fichiers(request: Request, nom: str = Form(..., min_length=2, max_length=80),
                            fichiers: list[UploadFile] = File(...), synchrone: bool = Query(False),
                            u: Utilisateur = Depends(proprietaire_sources)):
    limite = config.CONNECTEUR_TAILLE_FICHIER_MO * 1024 * 1024
    contenus = []
    for f in fichiers[:6]:
        contenu = await f.read(limite + 1)
        if len(contenu) > limite:
            raise HTTPException(413, f"{f.filename} : fichier trop volumineux ({config.CONNECTEUR_TAILLE_FICHIER_MO} Mo maximum)")
        contenus.append(((f.filename or "fichier.csv")[:200], contenu))
    id_source = await run_in_threadpool(lambda: _src(lambda: sources.creer_depuis_fichiers(u.nom, u.role, nom.strip(), contenus)))
    audit.journaliser(u.nom, "source_ajoutee", {"id_source": id_source, "type": "fichier", "fichiers": len(contenus)},
                      ip_client(request))
    await run_in_threadpool(sources.analyser_en_arriere_plan, id_source, u.nom, synchrone)
    return {"status": "ok", "id": id_source}


@router.post("/sources/{id_source}/analyser")
@limiter.limit("10/hour")
def reanalyser_source(request: Request, id_source: int = Path(ge=1), synchrone: bool = Query(False),
                      u: Utilisateur = Depends(proprietaire_sources)):
    _src(lambda: sources.detail(id_source, u.nom))
    sources.analyser_en_arriere_plan(id_source, u.nom, synchrone)
    return {"status": "ok"}


@router.post("/sources/{id_source}/masquage")
def masquage_source(body: Masquage, id_source: int = Path(ge=1), u: Utilisateur = Depends(proprietaire_sources)):
    _src(lambda: sources.modifier_masquage(id_source, u.nom, body.masquer))
    return {"status": "ok"}


@router.post("/sources/{id_source}/devise")
def devise_source(body: DeviseSource, id_source: int = Path(ge=1), u: Utilisateur = Depends(proprietaire_sources)):
    """Monnaie dans laquelle sont stockés les montants de la base (None : détection automatique)."""
    _src(lambda: sources.modifier_devise(id_source, u.nom, body.devise))
    return {"status": "ok"}


@router.post("/sources/{id_source}/supprimer")
def supprimer_source(request: Request, id_source: int = Path(ge=1), u: Utilisateur = Depends(proprietaire_sources)):
    _src(lambda: sources.supprimer(id_source, u.nom))
    audit.journaliser(u.nom, "source_supprimee", {"id_source": id_source}, ip_client(request))
    return {"status": "ok"}


@router.get("/sources/{id_source}/tableau")
@limiter.limit("30/minute")
def tableau_source(request: Request, id_source: int = Path(ge=0), devise: CodeDevise = Query("XAF"),
                   u: Utilisateur = Depends(utilisateur_courant)):
    """Indicateurs et graphiques calculés d'après la structure de la base (mis en cache 10 minutes)."""
    try:
        return {"status": "ok", "data": sources.tableau_de_bord(id_source, u.nom, devise)}
    except sources.SourceRefusee as e:
        raise HTTPException(404 if str(e) == "Source introuvable" else 422, str(e))


@router.get("/sources/{id_source}/risques/operations")
@limiter.limit("20/minute")
def operations_atypiques(request: Request, id_source: int = Path(ge=0), devise: CodeDevise = Query("XAF"),
                         u: Utilisateur = Depends(utilisateur_courant)):
    """Opérations les plus atypiques de la base (Isolation Forest entraîné sur ses propres données)."""
    return _risque_source(lambda: sources.operations_atypiques(id_source, u.nom, devise))


@router.get("/sources/{id_source}/risques/formulaire")
def formulaire_operation(id_source: int = Path(ge=0), devise: CodeDevise = Query("XAF"),
                         u: Utilisateur = Depends(utilisateur_courant)):
    return _risque_source(lambda: sources.formulaire_operation(id_source, u.nom, devise))


@router.post("/sources/{id_source}/risques/operation")
@limiter.limit("30/minute")
def analyser_operation_source(request: Request, body: OperationSource, id_source: int = Path(ge=0),
                              u: Utilisateur = Depends(utilisateur_courant)):
    cats = {k[:64]: v[:100] for k, v in list(body.categories.items())[:10]}
    return _risque_source(lambda: sources.analyser_operation(id_source, u.nom, body.montant, body.heure, cats, body.devise))


@router.get("/sources/{id_source}/risques/credits")
@limiter.limit("20/minute")
def portefeuille_credits(request: Request, id_source: int = Path(ge=0), devise: CodeDevise = Query("XAF"),
                         u: Utilisateur = Depends(utilisateur_courant)):
    """Taux de défaut par segment et crédits en cours les plus risqués, appris sur la base elle-même."""
    return _risque_source(lambda: sources.portefeuille_credits(id_source, u.nom, devise))


@router.post("/sources/{id_source}/question")
@limiter.limit("30/minute")
def question_source(request: Request, body: QuestionSource, id_source: int = Path(ge=0),
                    u: Utilisateur = Depends(utilisateur_courant)):
    _verifier_quota(u)
    debut = time.time()
    try:
        res = sources.repondre(id_source, u.nom, u.role, body.texte.strip(), body.devise)
    except sources.SourceRefusee as e:
        _journaliser(body.texte, None, False, int((time.time() - debut) * 1000), u)
        raise HTTPException(404 if str(e) == "Source introuvable" else 422, str(e))
    _journaliser(body.texte, res["sql"], True, res["duree_ms"], u)
    return res
