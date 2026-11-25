"""Spracheingabe: welche Erkennung im Modus "auto" genommen wird (Regression 0.27.1 -> 0.32.1)."""
import pytest
from types import SimpleNamespace

from assistant import voice


def _cap(erkennung="auto"):
    return voice.VoiceCapture(SimpleNamespace(erkennung=erkennung, whisper_modell="small", sprache="de"))


def _pakete(monkeypatch, *da):
    monkeypatch.setattr(voice, "_importable", lambda name: name in da)


def test_auto_nimmt_google_auch_wenn_whisper_da_ist(monkeypatch):
    # seit 0.27.1 steckt faster-whisper (fuer den Mitschnitt) in der .exe - die Spracheingabe darf
    # deshalb NICHT still auf Whisper (460-MB-Download beim ersten F2) umspringen
    _pakete(monkeypatch, "sounddevice", "speech_recognition", "faster_whisper")
    assert _cap().backend() == "google"


def test_auto_faellt_auf_whisper_zurueck(monkeypatch):
    _pakete(monkeypatch, "sounddevice", "faster_whisper")
    assert _cap().backend() == "whisper"


def test_ausdruecklich_whisper(monkeypatch):
    _pakete(monkeypatch, "sounddevice", "speech_recognition", "faster_whisper")
    assert _cap("whisper").backend() == "whisper"


def test_nichts_da_meldet_problem(monkeypatch):
    _pakete(monkeypatch)
    cap = _cap()
    assert cap.backend() is None and "sounddevice" in cap.problem()


def test_whisper_bekommt_die_aufnahme_direkt_ohne_pyav():
    # Regression: "open() got an unexpected keyword argument 'metadata_errors'" - faster-whisper las eine
    # WAV-Datei ueber PyAV, und neuere PyAV-Versionen kennen das Argument nicht mehr. Jetzt: Array statt Datei.
    np = pytest.importorskip("numpy")
    gesehen = {}

    class FakeWhisper:
        def transcribe(self, audio, **kw):
            gesehen["audio"] = audio
            return [SimpleNamespace(text=" Hallo Nova ")], None

    cap = _cap("whisper")
    cap._whisper = FakeWhisper()
    pcm = np.array([0, 16384, -32768, 32767], dtype=np.int16).tobytes()
    assert cap._transcribe_whisper(pcm) == "Hallo Nova"
    a = gesehen["audio"]
    assert isinstance(a, np.ndarray) and a.dtype == np.float32
    assert a.tolist() == [0.0, 0.5, -1.0, 32767 / 32768]
