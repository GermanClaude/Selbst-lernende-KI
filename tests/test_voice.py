from array import array
from types import SimpleNamespace

from assistant import voice
from assistant.config import VoiceSettings


def _pcm(seconds, loud=True):
    value = 8000 if loud else 0
    return array("h", [value, -value] * int(8000 * seconds)).tobytes()


def test_split_audio_cuts_at_quiet_point():
    pcm = _pcm(27) + _pcm(1, loud=False) + _pcm(20)
    chunks = voice.split_audio(pcm)
    assert b"".join(chunks) == pcm
    assert len(chunks) == 2
    first_seconds = len(chunks[0]) / 32000
    assert 27 <= first_seconds <= 28  # in der Sprechpause geschnitten


def test_split_audio_long_recording_all_chunks_short():
    pcm = _pcm(95)
    chunks = voice.split_audio(pcm)
    assert b"".join(chunks) == pcm
    assert all(len(c) <= 30 * 32000 for c in chunks)


def test_problem_explains_missing_packages(monkeypatch):
    monkeypatch.setattr(voice, "_importable", lambda name: False)
    msg = voice.VoiceCapture(VoiceSettings()).problem()
    assert "sounddevice" in msg and "/sprache einrichten" in msg


def test_backend_choice(monkeypatch):
    monkeypatch.setattr(voice, "_importable", lambda name: name in ("sounddevice", "speech_recognition"))
    assert voice.VoiceCapture(VoiceSettings()).backend() == "google"
    assert voice.VoiceCapture(VoiceSettings()).problem() is None
    assert voice.VoiceCapture(VoiceSettings(erkennung="whisper")).backend() is None


def test_short_press_without_speech_returns_nothing():
    cap = voice.VoiceCapture(VoiceSettings())
    cap._frames = [b"\0\0" * 1000]  # 1/16 s
    assert cap.stop() == ""


def test_install_voice_packages_uses_pip():
    calls = []
    ok, msg = voice.install_voice_packages(
        run=lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(returncode=0, stdout="", stderr="")
    )
    assert ok and calls[0][1:4] == ["-m", "pip", "install"] and "sounddevice" in calls[0]
