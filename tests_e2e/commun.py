"""Réglages communs des tests de bout en bout (navigateur réel contre l'API et l'interface lancées en local).

Tout se règle par variables d'environnement (valeurs par défaut = celles de `lancer.py`) :
  E2E_URL        adresse de l'interface            (http://localhost:3000)
  E2E_API        adresse de l'API                  (http://localhost:8000)
  E2E_BASE       base VoiceBank de test, pour psql (postgresql://postgres@localhost:5432/vbe2e)
  E2E_MAILS      dossier où le faux serveur d'e-mails dépose les messages (.eml)
  E2E_CHROMIUM   navigateur à utiliser (facultatif : sinon celui de Playwright)
  E2E_SOURCE_*   base « externe » que les tests branchent dans le connecteur (hôte, port)
"""
import os
import subprocess
import wave
from pathlib import Path

ICI = Path(__file__).resolve().parent
URL = os.environ.get("E2E_URL", "http://localhost:3000")
API = os.environ.get("E2E_API", "http://localhost:8000")
BASE = os.environ.get("E2E_BASE", "postgresql://postgres@localhost:5432/vbe2e")
MAILS = Path(os.environ.get("E2E_MAILS", ICI / "sortie" / "mails"))
DONNEES = ICI / "donnees"
SOURCE_HOTE = os.environ.get("E2E_SOURCE_HOTE", "127.0.0.1")
SOURCE_PORT = os.environ.get("E2E_SOURCE_PORT", "5432")
RACINE_API = ICI.parent / "voicebank_api"

NAVIGATEUR = {"executable_path": os.environ["E2E_CHROMIUM"]} if os.environ.get("E2E_CHROMIUM") else {}


def lancer(p, args=None):
    """Chromium sans interface, avec les options éventuelles (micro simulé…)."""
    return p.chromium.launch(**NAVIGATEUR, **({"args": args} if args else {}))


def sql(req: str):
    subprocess.run(["psql", BASE, "-X", "-qc", req], check=True)


def silence_wav() -> str:
    """Fichier audio silencieux (20 s) pour le micro simulé de Chromium."""
    chemin = ICI / "sortie" / "silence.wav"
    if not chemin.exists():
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(chemin), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
            w.writeframes(b"\0\0" * 48000 * 20)
    return str(chemin)
