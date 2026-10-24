# voicebank_whisper — transcription vocale locale

Moteur de secours utilisé par l'API **quand `GROQ_API_KEY` est vide** (ou si Groq échoue).
Il tourne sur ton ordinateur / serveur, sans Internet une fois le modèle téléchargé, et gratuitement.

| | Groq (par défaut si clé) | Whisper local (ce dossier) |
|---|---|---|
| Coût | ~0,11 $ / heure d'audio | gratuit |
| Internet | obligatoire | seulement pour le 1er téléchargement du modèle |
| Vitesse (8 s d'audio) | < 1 s | ~1-3 s sur CPU avec `base` |
| Qualité | large-v3 (excellente) | selon le modèle choisi |

## Réglages (.env)

```
WHISPER_LOCAL=auto            # auto = actif si faster-whisper est installé ; false = désactivé
WHISPER_LOCAL_MODELE=base     # tiny (75 Mo), base (145 Mo), small (480 Mo), medium (1,5 Go)
WHISPER_LOCAL_DOSSIER=        # où stocker le modèle (vide = cache Hugging Face par défaut)
```

`small` comprend nettement mieux le français que `base`, pour ~2x plus de temps de calcul.

## Tester

```bash
pip install -r voicebank_api/requirements.txt
python -m voicebank_whisper.transcrire --precharger          # télécharge le modèle
python -m voicebank_whisper.transcrire mon_enregistrement.wav
```

Puis lance l'API **sans** `GROQ_API_KEY` : `/health` affiche `"whisper": "local (base)"`
et le bouton micro de l'interface utilise ce moteur.
