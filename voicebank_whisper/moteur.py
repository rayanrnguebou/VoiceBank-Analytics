"""Moteur Whisper local basé sur faster-whisper (CTranslate2).

Pourquoi faster-whisper plutôt que openai-whisper :
  * pas de PyTorch (image Docker ~10x plus légère) ;
  * jusqu'à 4x plus rapide sur CPU, quantification int8 ;
  * décode lui-même WEBM/OGG/MP3/WAV (PyAV) : pas besoin d'installer ffmpeg.

Le modèle est téléchargé depuis Hugging Face au premier usage, puis reste en cache
(dossier WHISPER_LOCAL_DOSSIER ou ~/.cache/huggingface).
"""
import io
import logging
import threading

log = logging.getLogger("voicebank.whisper")


def disponible() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


class AudioTropLong(ValueError):
    pass


class MoteurWhisperLocal:
    def __init__(self, modele: str = "base", dossier: str | None = None, device: str = "cpu",
                 compute_type: str = "int8", langue: str = "fr", duree_max_s: float = 60.0):
        self.nom_modele = modele
        self.dossier = dossier or None
        self.device = device
        self.compute_type = compute_type
        self.langue = langue
        self.duree_max_s = duree_max_s
        self._modele = None
        self._verrou_chargement = threading.Lock()
        # Une transcription à la fois : le CPU est saturé par une seule.
        self._verrou_transcription = threading.Semaphore(1)

    @property
    def pret(self) -> bool:
        return self._modele is not None

    def charger(self):
        with self._verrou_chargement:
            if self._modele is None:
                from faster_whisper import WhisperModel
                log.info("Chargement du modèle Whisper local '%s' (%s/%s)…",
                         self.nom_modele, self.device, self.compute_type)
                self._modele = WhisperModel(self.nom_modele, device=self.device,
                                            compute_type=self.compute_type, download_root=self.dossier)
                log.info("Whisper local prêt")
        return self._modele

    def duree_audio(self, contenu: bytes) -> float:
        """Durée en secondes (lecture des métadonnées, sans décoder tout le fichier)."""
        import av
        try:
            with av.open(io.BytesIO(contenu)) as conteneur:
                if conteneur.duration:
                    return conteneur.duration / 1_000_000
                # WEBM du navigateur : durée souvent absente -> on compte les paquets audio
                flux = conteneur.streams.audio[0]
                fin = 0.0
                for paquet in conteneur.demux(flux):
                    if paquet.pts is not None and paquet.time_base is not None:
                        fin = max(fin, float((paquet.pts + (paquet.duration or 0)) * paquet.time_base))
                return fin
        except (av.error.FFmpegError, IndexError) as e:
            raise ValueError("Fichier audio illisible") from e

    def transcrire(self, contenu: bytes) -> str:
        duree = self.duree_audio(contenu)
        if duree > self.duree_max_s:
            raise AudioTropLong(f"Audio trop long ({duree:.0f} s, maximum {self.duree_max_s:.0f} s)")
        modele = self.charger()
        with self._verrou_transcription:
            segments, _ = modele.transcribe(io.BytesIO(contenu), language=self.langue, beam_size=5,
                                            vad_filter=True, condition_on_previous_text=False)
            return " ".join(s.text.strip() for s in segments).strip()
