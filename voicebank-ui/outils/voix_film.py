"""Ajoute au film de présentation des voix humaines enregistrées.

Usage : python voicebank-ui/outils/voix_film.py <dossier> <langue>
  <dossier> contient un enregistrement par scène, nommé d'après la scène (n'importe quel format audio : m4a, mp3, ogg,
  opus, wav…) : accueil, voix, fraude, approbation, monde, fin.
  <langue> : fr ou en.

Chaque fichier est nettoyé (silences au début et à la fin retirés, volume harmonisé à -16 LUFS, mono 44,1 kHz),
encodé en MP3 dans voicebank-ui/public/film/voix/<langue>/<scène>.mp3 et déclaré dans voix.json. Une scène sans
fichier garde la synthèse vocale du navigateur. Nécessite ffmpeg.
"""
import json
import subprocess
import sys
from pathlib import Path

SCENES = ["accueil", "voix", "fraude", "approbation", "monde", "fin"]
RACINE = Path(__file__).resolve().parent.parent / "public" / "film" / "voix"
FILTRE = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,"
          "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.25,areverse,"
          "highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11")


def main(dossier: str, langue: str) -> None:
    if langue not in ("fr", "en"):
        sys.exit("Langue : fr ou en")
    sortie = RACINE / langue
    sortie.mkdir(parents=True, exist_ok=True)
    fichiers = {f.stem.lower(): f for f in Path(dossier).iterdir() if f.is_file()}
    faits = []
    for scene in SCENES:
        source = fichiers.get(scene)
        if not source:
            print(f"  {scene} : pas d'enregistrement (synthèse vocale)")
            continue
        cible = sortie / f"{scene}.mp3"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(source), "-af", FILTRE, "-ac", "1", "-ar", "44100",
                        "-codec:a", "libmp3lame", "-b:a", "96k", str(cible)], check=True)
        faits.append(scene)
        print(f"  {scene} : {cible.stat().st_size // 1024} Ko")
    manifeste = RACINE / "voix.json"
    voix = json.loads(manifeste.read_text()) if manifeste.exists() else {}
    voix[langue] = faits
    manifeste.write_text(json.dumps({"fr": voix.get("fr", []), "en": voix.get("en", [])}, indent=1) + "\n")
    print(f"{len(faits)} voix enregistrée(s) en « {langue} »")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
