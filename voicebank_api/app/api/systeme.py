"""Accueil, santé du service et maintenance."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .commun import (  # noqa: F401
    Depends,
    ReglageMaintenance,
    Request,
    Utilisateur,
    VERSION_API,
    admin_requis,
    audit,
    config,
    credit,
    datetime,
    db,
    fraude,
    ip_client,
    maintenance,
    transcription,
)

router = APIRouter()


@router.get("/")
def accueil():
    return {"message": "VoiceBank Analytics API", "version": VERSION_API, "status": "OK"}


@router.api_route("/health/vivant", methods=["GET", "HEAD"])
def vivant():
    """Sonde de Render et de Docker (toutes les quelques secondes) : ne touche pas la base."""
    return {"status": "ok"}


@router.api_route("/health/pret", methods=["GET", "HEAD"])
def pret():
    """Pour la surveillance externe (UptimeRobot) : 200 si l'API ET la base répondent, 503 sinon.
    Une base vue en bon état depuis moins de 20 min n'est pas réinterrogée (elle peut dormir : Neon)."""
    if not db.base_ok(cache_s=20 * 60):
        return JSONResponse({"status": "degraded", "database": "deconnectee"}, status_code=503)
    return {"status": "ok"}


@router.api_route("/health", methods=["GET", "HEAD"])
def health():
    ok = db.base_ok(cache_s=10 * 60)
    return {"status": "ok" if ok else "degraded",
            "database": "connectee" if ok else "deconnectee",
            "gemini": "disponible" if config.GEMINI_API_KEY else "non configure",
            "whisper": transcription.etat(),
            "modeles_ia": sorted(k for k in fraude.modeles if k != "meta") + (["credit"] if credit.disponible() else []),
            "maintenance": maintenance.derniere_connue(),
            "timestamp": datetime.now().isoformat()}


@router.get("/maintenance")
def etat_maintenance():
    """Public : maintenance en cours et annonce de maintenance prévue (bandeau)."""
    return maintenance.public()


@router.get("/admin/maintenance")
def lire_maintenance(u: Utilisateur = Depends(admin_requis)):
    return maintenance.etat(force=True)


@router.post("/admin/maintenance")
def regler_maintenance(request: Request, body: ReglageMaintenance, u: Utilisateur = Depends(admin_requis)):
    annonce = None
    if body.annonce_message and body.annonce_message.strip():
        annonce = {"message": body.annonce_message.strip()[:300], "debut": body.annonce_debut, "fin": body.annonce_fin}
    e = maintenance.modifier(u.nom, body.active, body.message, body.fin_prevue, annonce)
    audit.journaliser(u.nom, "maintenance", {"active": body.active, "annonce": bool(annonce)}, ip_client(request))
    return e
