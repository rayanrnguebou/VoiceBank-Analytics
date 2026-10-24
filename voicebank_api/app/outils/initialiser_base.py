"""Crée le schéma VoiceBank (scripts voicebank_db/init/01 et 02) sans psql.

Utilisé au démarrage sur Render (INITIALISER_BASE=true). Idempotent : ne supprime rien.
Les comptes à privilèges minimaux (securite/roles.sql) nécessitent psql : voir README.
"""
import os
from pathlib import Path

import psycopg2


def trouver_scripts() -> list[Path]:
    for racine in (Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[3]):
        d = racine / "voicebank_db" / "init"
        if d.is_dir():
            return [d / "01_init_voicebank.sql", d / "02_corrections_rag.sql"]
    raise SystemExit("Scripts voicebank_db/init introuvables")


def main():
    url = (os.environ.get("ADMIN_DATABASE_URL") or os.environ["DATABASE_URL"]).replace(
        "postgresql+psycopg2://", "postgresql://").replace("postgres://", "postgresql://", 1)
    with psycopg2.connect(url) as conn:
        for script in trouver_scripts():
            conn.cursor().execute(script.read_text(encoding="utf-8"))
            print(f"OK {script.name}")


if __name__ == "__main__":
    main()
