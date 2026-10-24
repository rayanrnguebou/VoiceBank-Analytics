"""Transcription vocale locale (hors ligne) pour VoiceBank Analytics."""
from .moteur import AudioTropLong, MoteurWhisperLocal, disponible

__all__ = ["MoteurWhisperLocal", "AudioTropLong", "disponible"]
