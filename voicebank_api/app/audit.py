"""Journal d'audit : qui a fait quoi, quand (table en ajout seul)."""
import json
import logging

from . import db

log = logging.getLogger("voicebank")


def journaliser(utilisateur: str | None, action: str, detail: dict | None = None, ip: str | None = None):
    try:
        db.ecrire("INSERT INTO voicebank.journal_audit (utilisateur, action, detail, adresse_ip) "
                  "VALUES (:u, :a, CAST(:d AS JSONB), :ip)",
                  {"u": utilisateur, "a": action, "d": json.dumps(detail or {}, ensure_ascii=False, default=str),
                   "ip": ip})
    except Exception:
        log.exception("Audit impossible (%s)", action)
