# VOICEBANK ANALYTICS - Module Reconnaissance Vocale (Whisper Local)
# Auteur : Nguebou Temgoua Rayan
# Description : Capture micro -> Whisper -> texte -> Gemini -> SQL -> resultat
#
# Installation :
# pip install openai-whisper sounddevice soundfile numpy scipy pyaudio
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
#
# Si pyaudio pose probleme sur Windows :
# pip install pipwin
# pipwin install pyaudio

import os
import time
import tempfile
import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper
import httpx
import json

os.environ["PATH"] += os.pathsep + r"C:\Users\Rayan\Documents\Mes projets\VoiceBank Analytics\voicebank_whisper\ffmpeg-2026-05-11-git-17bc88e67f-essentials_build\bin"  # chemin vers ffmpeg.exe (ajuste selon ton installation)

# ════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════

API_URL        = "http://localhost:8000"
WHISPER_MODEL  = "base"       # tiny/base/small/medium — base est le meilleur compromis
SAMPLE_RATE    = 16000        # Hz requis par Whisper
DUREE_ENREG    = 5            # secondes d'enregistrement par defaut
LANGUE_WHISPER = "fr"         # forcer le francais


# ════════════════════════════════════════
# CHARGEMENT DU MODELE WHISPER
# ════════════════════════════════════════

print("\n  Chargement du modele Whisper...")
print(f"  Modele : {WHISPER_MODEL} (premier lancement = telechargement automatique)")
model_whisper = whisper.load_model(WHISPER_MODEL)
print(f"  OK Modele Whisper '{WHISPER_MODEL}' charge !")


# ════════════════════════════════════════
# FONCTIONS PRINCIPALES
# ════════════════════════════════════════

def enregistrer_audio(duree: int = DUREE_ENREG) -> np.ndarray:
    """Enregistre l'audio depuis le microphone."""
    print(f"\n  Enregistrement en cours ({duree}s)... Parle maintenant !")
    audio = sd.rec(
        int(duree * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    print("  Enregistrement termine.")
    return audio.flatten()


def transcrire_audio(audio: np.ndarray) -> str:
    """Transcrit l'audio en texte avec Whisper."""
    print("  Transcription Whisper en cours...")

    # Sauvegarder dans un fichier temporaire WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        chemin_tmp = f.name
        sf.write(chemin_tmp, audio, SAMPLE_RATE)

    try:
        result = model_whisper.transcribe(
            chemin_tmp,
            language=LANGUE_WHISPER,
            fp16=False,              # desactiver fp16 pour CPU
            temperature=0.0,         # deterministe
        )
        texte = result["text"].strip()
        print(f"  Transcrit : \"{texte}\"")
        return texte
    finally:
        os.unlink(chemin_tmp)


def transcrire_fichier(chemin_fichier: str) -> str:
    """Transcrit un fichier audio existant."""
    result = model_whisper.transcribe(
        chemin_fichier,
        language=LANGUE_WHISPER,
        fp16=False,
        temperature=0.0,
    )
    return result["text"].strip()


def envoyer_question(texte: str) -> dict:
    """Envoie la question transcrite a l'API FastAPI."""
    print(f"\n  Envoi a l'API : \"{texte}\"")
    try:
        response = httpx.post(
            f"{API_URL}/vocal/question",
            json={"texte": texte, "langue": "fr"},
            timeout=30.0,
        )
        return response.json()
    except Exception as e:
        return {"status": "erreur", "detail": str(e)}


def afficher_resultat(resultat: dict):
    """Affiche le resultat de facon lisible."""
    print("\n" + "="*55)
    if resultat.get("status") != "ok":
        print(f"  ERREUR : {resultat.get('detail', 'Inconnue')}")
        return

    print(f"  Question  : {resultat['question']}")
    print(f"  SQL genere : {resultat['sql'][:100]}...")
    print(f"  Resultats  : {resultat['total']} lignes")
    print(f"  Duree      : {resultat['duree_ms']} ms")

    if resultat["data"]:
        print("\n  Apercu des resultats :")
        for i, row in enumerate(resultat["data"][:5]):
            print(f"    [{i+1}] {row}")
    print("="*55)


# ════════════════════════════════════════
# ENDPOINT FASTAPI — a ajouter dans main.py
# ════════════════════════════════════════

ENDPOINT_CODE = '''
# ── Transcription audio -> texte (Whisper) ────────────
# Ajoute cet endpoint dans ton main.py

from fastapi import UploadFile, File
import tempfile, os
import whisper as whisper_lib

whisper_model = None

def charger_whisper():
    global whisper_model
    try:
        whisper_model = whisper_lib.load_model("base")
        print("OK Whisper charge")
    except Exception as e:
        print(f"ATTENTION Whisper non charge : {e}")

charger_whisper()

@app.post("/vocal/transcrire")
async def transcrire_audio(fichier: UploadFile = File(...)):
    """Recoit un fichier audio et retourne la transcription Whisper."""
    if not whisper_model:
        raise HTTPException(503, "Whisper non disponible")

    contenu = await fichier.read()

    with tempfile.NamedTemporaryFile(
        suffix=f".{fichier.filename.split('.')[-1]}",
        delete=False
    ) as f:
        f.write(contenu)
        chemin_tmp = f.name

    try:
        result = whisper_model.transcribe(
            chemin_tmp,
            language="fr",
            fp16=False,
            temperature=0.0,
        )
        texte = result["text"].strip()
        return {
            "status"  : "ok",
            "texte"   : texte,
            "langue"  : result.get("language", "fr"),
            "segments": len(result.get("segments", [])),
        }
    finally:
        os.unlink(chemin_tmp)


@app.post("/vocal/transcrire-et-analyser")
async def transcrire_et_analyser(fichier: UploadFile = File(...)):
    """Pipeline complet : audio -> Whisper -> Gemini -> SQL -> resultat."""
    # 1. Transcription
    transcription = await transcrire_audio(fichier)
    if transcription["status"] != "ok":
        raise HTTPException(500, "Echec transcription")

    texte = transcription["texte"]

    # 2. Text-to-SQL via Gemini
    from fastapi import Request
    sql_genere = texte_vers_sql(texte)

    # 3. Execution SQL
    colonnes, rows = executer_sql(sql_genere)

    return {
        "status"       : "ok",
        "texte_audio"  : texte,
        "sql"          : sql_genere,
        "colonnes"     : colonnes,
        "total"        : len(rows),
        "data"         : rows,
    }
'''


# ════════════════════════════════════════
# MODE INTERACTIF — TEST EN LIGNE DE COMMANDE
# ════════════════════════════════════════

def mode_micro():
    """Mode microphone interactif."""
    print("\n" + "="*55)
    print("   VOICEBANK ANALYTICS - Mode Vocal")
    print("   Appuie sur Entree pour parler, 'q' pour quitter")
    print("="*55)

    while True:
        cmd = input("\n  [Entree] Parler | [q] Quitter : ").strip().lower()
        if cmd == "q":
            print("  Au revoir !")
            break

        # Enregistrement
        audio = enregistrer_audio(duree=DUREE_ENREG)

        # Transcription
        texte = transcrire_audio(audio)

        if not texte:
            print("  Aucun texte detecte. Reessaie.")
            continue

        # Envoi a l'API
        resultat = envoyer_question(texte)

        # Affichage
        afficher_resultat(resultat)


def mode_fichier(chemin: str):
    """Transcrit un fichier audio existant et envoie a l'API."""
    print(f"\n  Transcription de : {chemin}")
    texte = transcrire_fichier(chemin)
    print(f"  Texte : \"{texte}\"")
    resultat = envoyer_question(texte)
    afficher_resultat(resultat)


def mode_texte():
    """Mode texte — simule la voix par saisie clavier (pour tester sans micro)."""
    print("\n" + "="*55)
    print("   VOICEBANK ANALYTICS - Mode Texte (simulation)")
    print("="*55)

    while True:
        texte = input("\n  Question (ou 'q' pour quitter) : ").strip()
        if texte.lower() == "q":
            break
        if not texte:
            continue
        resultat = envoyer_question(texte)
        afficher_resultat(resultat)


# ════════════════════════════════════════
# MAIN
# ════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*55)
    print("   VOICEBANK ANALYTICS - Reconnaissance Vocale")
    print("   Auteur : Nguebou Temgoua Rayan")
    print("="*55)

    print("\n  Quel mode veux-tu utiliser ?")
    print("  [1] Mode microphone (Whisper + micro)")
    print("  [2] Mode texte     (simulation sans micro)")
    print("  [3] Mode fichier   (transcrire un fichier audio)")

    choix = input("\n  Ton choix (1/2/3) : ").strip()

    if choix == "1":
        mode_micro()
    elif choix == "2":
        mode_texte()
    elif choix == "3":
        chemin = input("  Chemin du fichier audio : ").strip()
        mode_fichier(chemin)
    else:
        print("  Choix invalide. Lancement mode texte par defaut.")
        mode_texte()
