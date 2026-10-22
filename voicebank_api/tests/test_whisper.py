"""Transcription : choix Groq / Whisper local (voicebank_whisper) et traitement de l'audio."""
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app import config, transcription
from voicebank_whisper import AudioTropLong, MoteurWhisperLocal

ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg requis pour générer l'audio de test")


def _audio(secondes: float, fmt: str = "webm") -> bytes:
    """Génère un vrai fichier audio (bip 440 Hz). webm/opus = format envoyé par Chrome."""
    codec = {"webm": ["-c:a", "libopus"], "ogg": ["-c:a", "libopus"], "wav": [], "mp3": []}[fmt]
    return subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={secondes}",
         *codec, "-f", fmt, "pipe:1"], check=True, capture_output=True).stdout


class FauxModele:
    """Remplace faster_whisper.WhisperModel (le vrai modèle se télécharge depuis Hugging Face)."""
    appels = []

    def __init__(self, nom, **kw):
        self.nom, self.kw = nom, kw

    def transcribe(self, audio, **kw):
        FauxModele.appels.append((audio, kw))
        return iter([SimpleNamespace(text=" crédits "), SimpleNamespace(text="en défaut ")]), None


# ── Moteur local ─────────────────────────────────────

@ffmpeg
@pytest.mark.parametrize("fmt", ["webm", "ogg", "wav", "mp3"])
def test_duree_audio_formats_navigateur(fmt):
    assert MoteurWhisperLocal().duree_audio(_audio(3, fmt)) == pytest.approx(3, abs=0.2)


@ffmpeg
def test_decodage_reel_par_faster_whisper():
    """Vérifie que faster-whisper (PyAV) décode bien le WEBM/Opus du navigateur, sans ffmpeg système."""
    import io

    from faster_whisper import decode_audio
    echantillons = decode_audio(io.BytesIO(_audio(2, "webm")), sampling_rate=16000)
    assert abs(len(echantillons) - 32000) < 1600


@ffmpeg
def test_moteur_local_transcrit_et_charge_une_fois():
    FauxModele.appels.clear()
    m = MoteurWhisperLocal("base")
    with patch("faster_whisper.WhisperModel", FauxModele) as _:
        assert m.transcrire(_audio(2)) == "crédits en défaut"
        assert m.transcrire(_audio(2)) == "crédits en défaut"
    assert m._modele.nom == "base" and m._modele.kw["compute_type"] == "int8"
    assert FauxModele.appels[0][1]["language"] == "fr" and FauxModele.appels[0][1]["vad_filter"]
    assert len(FauxModele.appels) == 2


@ffmpeg
def test_moteur_local_refuse_audio_trop_long():
    with pytest.raises(AudioTropLong):
        MoteurWhisperLocal(duree_max_s=5).transcrire(_audio(8))


def test_moteur_local_refuse_fichier_illisible():
    with pytest.raises(ValueError):
        MoteurWhisperLocal().duree_audio(b"ceci n'est pas de l'audio")


# ── Choix du moteur ──────────────────────────────────

@pytest.fixture
def moteur_simule(monkeypatch):
    m = MagicMock(nom_modele="base", pret=True)
    m.transcrire.return_value = "texte local"
    monkeypatch.setattr(transcription, "moteur_local", m)
    return m


def test_sans_cle_groq_utilise_le_local(monkeypatch, moteur_simule):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    assert transcription.transcrire(b"x", "webm") == ("texte local", "local")
    assert transcription.etat() == "local (base)"


def test_avec_cle_groq_utilise_groq(monkeypatch, moteur_simule):
    monkeypatch.setattr(config, "GROQ_API_KEY", "cle")
    with patch.object(transcription, "_groq", return_value="texte groq"):
        assert transcription.transcrire(b"x", "webm") == ("texte groq", "groq")
    moteur_simule.transcrire.assert_not_called()


def test_groq_en_panne_bascule_sur_local(monkeypatch, moteur_simule):
    monkeypatch.setattr(config, "GROQ_API_KEY", "cle")
    with patch.object(transcription, "_groq", side_effect=ConnectionError("réseau")):
        assert transcription.transcrire(b"x", "webm") == ("texte local", "local")


def test_aucun_moteur(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(transcription, "moteur_local", None)
    with pytest.raises(transcription.TranscriptionErreur) as e:
        transcription.transcrire(b"x", "webm")
    assert e.value.code == 503
    assert transcription.etat() == "non configure"


# ── Via l'API ────────────────────────────────────────

@ffmpeg
def test_api_micro_sans_groq_avec_whisper_local(client, analyste, monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(transcription, "moteur_local", MoteurWhisperLocal("base"))
    with patch("faster_whisper.WhisperModel", FauxModele):
        r = client.post("/vocal/pipeline-complet", headers=analyste,
                        files={"fichier": ("audio.webm", _audio(3), "audio/webm")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["moteur_transcription"] == "local" and j["texte_audio"] == "crédits en défaut" and j["total"] > 0
    assert "local (base)" in client.get("/health").json()["whisper"]


@ffmpeg
def test_api_audio_trop_long_en_local(client, analyste, monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(transcription, "moteur_local", MoteurWhisperLocal("base", duree_max_s=5))
    r = client.post("/vocal/transcrire", headers=analyste,
                    files={"fichier": ("audio.webm", _audio(8), "audio/webm")})
    assert r.status_code == 413


def test_api_audio_illisible_en_local(client, analyste, monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(transcription, "moteur_local", MoteurWhisperLocal("base"))
    r = client.post("/vocal/transcrire", headers=analyste,
                    files={"fichier": ("audio.webm", b"pas de l'audio", "audio/webm")})
    assert r.status_code == 415
