"""Vérifie que les clés Gemini et Groq du fichier .env fonctionnent.

Avec Docker (recommandé)  : docker compose exec api python -m app.outils.tester_ia
Sans Docker (voicebank_api/) : python -m app.outils.tester_ia
N'a pas besoin de la base de données.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    racine = Path(__file__).resolve().parents[3]
    load_dotenv()                      # voicebank_api/.env
    load_dotenv(racine / ".env")       # .env à la racine (celui de Docker)
except ImportError:
    pass


def _cle(nom):
    return os.getenv(nom, "").strip().strip("'\"")


def tester_gemini():
    cle, modele = _cle("GEMINI_API_KEY"), _cle("GEMINI_MODEL") or "gemini-3.5-flash-lite"
    if not cle:
        return "ABSENT  GEMINI_API_KEY n'est pas définie dans .env"
    try:
        from google import genai
    except ImportError:
        return "ERREUR  Bibliothèque google-genai absente : lance ce test avec Docker (voir docstring)"
    try:
        client = genai.Client(api_key=cle)
        rep = client.models.generate_content(
            model=modele,
            contents="Réponds uniquement par une requête SQL PostgreSQL : nombre de lignes de la table voicebank.clients")
        return f"OK      Gemini ({modele}) répond : {(rep.text or '').strip()[:80]}"
    except Exception as e:
        return f"ERREUR  Gemini ({modele}) : {str(e)[:200]}"


def tester_groq():
    cle, modele = _cle("GROQ_API_KEY"), _cle("GROQ_WHISPER_MODEL") or "whisper-large-v3"
    if not cle:
        return "ABSENT  GROQ_API_KEY n'est pas définie dans .env"
    try:
        from groq import Groq
    except ImportError:
        return "ERREUR  Bibliothèque groq absente : lance ce test avec Docker (voir docstring)"
    try:
        ids = {m.id for m in Groq(api_key=cle).models.list().data}
        if modele not in ids:
            proposes = ", ".join(sorted(i for i in ids if "whisper" in i)) or "aucun"
            return f"ERREUR  Clé Groq valide mais modèle '{modele}' indisponible. Modèles Whisper : {proposes}"
        return f"OK      Groq : clé valide, modèle {modele} disponible"
    except Exception as e:
        return f"ERREUR  Groq : {str(e)[:200]}"


if __name__ == "__main__":
    print(tester_gemini())
    print(tester_groq())
