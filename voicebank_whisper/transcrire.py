"""Outil en ligne de commande du Whisper local.

  python -m voicebank_whisper.transcrire --precharger        # télécharge le modèle (une fois)
  python -m voicebank_whisper.transcrire mon_audio.wav       # transcrit un fichier
  python -m voicebank_whisper.transcrire mon_audio.wav --modele small
"""
import argparse
import os
import sys
import time

from .moteur import MoteurWhisperLocal, disponible


def main():
    p = argparse.ArgumentParser(description="Transcription locale VoiceBank (faster-whisper)")
    p.add_argument("fichier", nargs="?", help="fichier audio (wav, mp3, webm, ogg, m4a…)")
    p.add_argument("--modele", default=os.getenv("WHISPER_LOCAL_MODELE", "base"),
                   help="tiny, base, small, medium, large-v3 (défaut : base)")
    p.add_argument("--precharger", action="store_true", help="télécharge seulement le modèle")
    a = p.parse_args()

    if not disponible():
        sys.exit("faster-whisper n'est pas installé : pip install -r voicebank_api/requirements.txt")
    moteur = MoteurWhisperLocal(a.modele, dossier=os.getenv("WHISPER_LOCAL_DOSSIER") or None,
                                duree_max_s=3600)
    debut = time.time()
    moteur.charger()
    print(f"Modèle '{a.modele}' prêt en {time.time() - debut:.1f} s")
    if a.precharger or not a.fichier:
        return
    with open(a.fichier, "rb") as f:
        contenu = f.read()
    debut = time.time()
    texte = moteur.transcrire(contenu)
    print(f"Transcription ({time.time() - debut:.1f} s) : {texte or '(aucune parole détectée)'}")


if __name__ == "__main__":
    main()
