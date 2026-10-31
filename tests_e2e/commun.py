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


# Choix de cookies déjà fait (refus) : le bandeau ne recouvre pas les écrans testés. test_cookies.py le vérifie à part.
# Même chose pour la présentation des applications (indicateur réservé aux tests). test_cookies.py vérifie les deux.
CONSENTEMENT = ("window.__voicebankSansPresentation = true; try { localStorage.setItem('voicebank_consentement', "
                "JSON.stringify({version: 1, erreurs: false, date: new Date().toISOString()})) } catch (e) {}")


def lancer(p, args=None):
    """Chromium sans interface, avec les options éventuelles (micro simulé…). Chaque page et chaque contexte
    créés ensuite ont déjà répondu au bandeau des cookies ; `sans_consentement()` donne un contexte vierge."""
    b = p.chromium.launch(**NAVIGATEUR, **({"args": args} if args else {}))
    contexte_brut = b.new_context

    def new_context(**kw):
        c = contexte_brut(**kw)
        c.add_init_script(CONSENTEMENT)
        return c

    def new_page(**kw):
        return new_context(**kw).new_page()

    b.new_context, b.new_page, b.sans_consentement = new_context, new_page, contexte_brut
    return b


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
