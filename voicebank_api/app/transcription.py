"""Voix -> texte : Groq si GROQ_API_KEY est définie, sinon Whisper local (voicebank_whisper).

Si Groq est configuré mais échoue (réseau, quota), le Whisper local prend le relais
quand il est disponible.
"""
import logging
import sys
import threading

from . import config, i18n

log = logging.getLogger("voicebank")

# voicebank_whisper est à la racine du projet (ou dans /app dans l'image Docker)
for _chemin in (config.BASE_DIR, config.BASE_DIR.parent):
    if (_chemin / "voicebank_whisper").is_dir() and str(_chemin) not in sys.path:
        sys.path.append(str(_chemin))


class TranscriptionErreur(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _creer_moteur_local():
    if config.WHISPER_LOCAL == "false":
        return None
    try:
        from voicebank_whisper import MoteurWhisperLocal, disponible
    except ImportError:
        log.info("Dossier voicebank_whisper introuvable : Whisper local désactivé")
        return None
    if not disponible():
        log.info("faster-whisper non installé : Whisper local désactivé")
        return None
    return MoteurWhisperLocal(config.WHISPER_LOCAL_MODELE, dossier=config.WHISPER_LOCAL_DOSSIER,
                              duree_max_s=config.WHISPER_LOCAL_DUREE_MAX_S)


moteur_local = _creer_moteur_local()


def precharger_en_arriere_plan():
    """Télécharge/charge le modèle local au démarrage pour que la 1re question ne soit pas lente."""
    if moteur_local and not config.GROQ_API_KEY and config.WHISPER_LOCAL_PRECHARGER:
        def _charger():
            try:
                moteur_local.charger()
            except Exception:
                log.exception("Préchargement du Whisper local impossible (il sera réessayé à la demande)")
        threading.Thread(target=_charger, daemon=True, name="whisper-local").start()


def etat() -> str:
    if config.GROQ_API_KEY:
        return "groq-api" + (f" (secours : local {moteur_local.nom_modele})" if moteur_local else "")
    if moteur_local:
        return f"local ({moteur_local.nom_modele})" + ("" if moteur_local.pret else " - chargement")
    return "non configure"


def _groq(contenu: bytes, extension: str) -> str:
    from groq import Groq
    rep = Groq(api_key=config.GROQ_API_KEY, timeout=30).audio.transcriptions.create(
        file=(f"audio.{extension}", contenu), model=config.GROQ_WHISPER_MODEL, language=i18n.langue())
    return (rep.text or "").strip()


def _local(contenu: bytes) -> str:
    from voicebank_whisper import AudioTropLong
    try:
        return moteur_local.transcrire(contenu)
    except AudioTropLong as e:
        raise TranscriptionErreur(413, str(e))
    except ValueError:
        raise TranscriptionErreur(415, "Fichier audio illisible")
    except Exception:
        log.exception("Erreur du Whisper local")
        raise TranscriptionErreur(502, "La transcription locale a échoué")


def transcrire(contenu: bytes, extension: str) -> tuple[str, str]:
    """Retourne (texte, moteur utilisé). Fonction bloquante : appeler hors de la boucle async."""
    if config.GROQ_API_KEY:
        try:
            return _groq(contenu, extension), "groq"
        except Exception as e:
            log.warning("Erreur Groq : %s", e)
            if not moteur_local:
                raise TranscriptionErreur(502, "Le service de transcription a échoué")
            log.info("Bascule sur le Whisper local")
    if moteur_local:
        return _local(contenu), "local"
    raise TranscriptionErreur(503, "Transcription non configurée : renseigne GROQ_API_KEY "
                                   "ou installe faster-whisper pour le Whisper local")
