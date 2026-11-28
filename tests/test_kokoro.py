"""Kokoro-Stimme (lokale TTS-Alternative zu ElevenLabs). Ohne echtes Modell: reine Logik + Fallback."""
import types

import pytest

from assistant import voice as V


def _settings(**kw):
    d = dict(stimme="kokoro", stimme_name="", stimme_tempo=1.0)
    d.update(kw)
    return types.SimpleNamespace(**d)


def test_kokoro_in_stimmenliste():
    ids = [s["id"] for s in V.STIMMEN]
    assert "kokoro" in ids
    info = V.stimme_info("kokoro")
    assert info["kostenlos"] is True and info["provider"] == "kokoro"


def test_kokoro_pcm_wandelt_float_in_pcm(monkeypatch):
    import numpy as np
    fake = types.SimpleNamespace(create=lambda t, voice, speed, lang="de": (np.array([0.0, 1.0, -1.0, 0.5], "float32"), 24000))
    monkeypatch.setitem(V._kokoro_cache, "tts", fake)
    pcm = V.kokoro_pcm("hallo", voice="af_heart", tempo=1.0, sprache="de")
    import struct
    assert struct.unpack("<4h", pcm) == (0, 32767, -32767, 16383)
    V._kokoro_cache.clear()


def test_kokoro_pcm_resampelt_fremde_rate(monkeypatch):
    import numpy as np
    # 48 kHz -> 24 kHz: jede zweite Probe
    fake = types.SimpleNamespace(create=lambda t, voice, speed, lang="de": (np.array([0, .25, .5, .75], "float32"), 48000))
    monkeypatch.setitem(V._kokoro_cache, "tts", fake)
    pcm = V.kokoro_pcm("x")
    import struct
    vals = struct.unpack("<2h", pcm)   # 4 Proben @48k -> 2 @24k
    assert len(vals) == 2
    V._kokoro_cache.clear()


def test_build_speaker_nimmt_kokoro_wenn_verfuegbar(monkeypatch):
    monkeypatch.setattr(V, "kokoro_verfuegbar", lambda: True)
    spk = V.build_speaker(_settings(), keys={}, http=lambda *a: b"")  # http-Sentinel: kein sounddevice noetig
    assert isinstance(spk, V.KokoroSpeaker)
    assert spk.available is True
    spk.stop()


def test_build_speaker_faellt_auf_frei_zurueck_ohne_modell(monkeypatch):
    monkeypatch.setattr(V, "kokoro_verfuegbar", lambda: False)
    spk = V.build_speaker(_settings(), keys={}, http=lambda *a: b"")
    assert not isinstance(spk, V.KokoroSpeaker)   # -> Speaker (freie Stimme)


def test_install_kokoro_laedt_modelldateien(tmp_path, monkeypatch):
    monkeypatch.setattr(V, "_KOKORO_DIR", tmp_path)
    monkeypatch.setattr(V, "_KOKORO_MODELL", tmp_path / "kokoro-v1.0.onnx")
    monkeypatch.setattr(V, "_KOKORO_STIMMEN_DAT", tmp_path / "voices-v1.0.bin")
    monkeypatch.setattr(V, "_importable", lambda n: False if n == "kokoro_onnx" else True)
    ran = {}
    def fake_run(cmd):
        ran["cmd"] = cmd
        return types.SimpleNamespace(returncode=0, stderr="")
    ok, msg = V.install_kokoro(run=fake_run, fetch=lambda url: b"x" * 2_000_000)
    assert ok is True
    assert "pip" in ran["cmd"] and "install" in ran["cmd"]
    assert (tmp_path / "kokoro-v1.0.onnx").exists() and (tmp_path / "voices-v1.0.bin").exists()


# -- Piper (zweite lokale Open-Source-Stimme) ---------------------------------
def test_piper_in_stimmenliste():
    assert "piper" in [s["id"] for s in V.STIMMEN]
    assert V.stimme_info("piper")["provider"] == "piper"


def test_build_speaker_nimmt_piper_wenn_verfuegbar(monkeypatch):
    monkeypatch.setattr(V, "piper_verfuegbar", lambda voice="": True)
    spk = V.build_speaker(_settings(stimme="piper"), keys={}, http=lambda *a: b"")
    assert isinstance(spk, V.PiperSpeaker) and spk.available is True
    spk.stop()


def test_build_speaker_piper_faellt_auf_frei_zurueck(monkeypatch):
    monkeypatch.setattr(V, "piper_verfuegbar", lambda voice="": False)
    spk = V.build_speaker(_settings(stimme="piper"), keys={}, http=lambda *a: b"")
    assert not isinstance(spk, V.PiperSpeaker)


def test_install_piper_laedt_stimme(tmp_path, monkeypatch):
    monkeypatch.setattr(V, "_PIPER_DIR", tmp_path)
    monkeypatch.setattr(V, "_importable", lambda n: False if n == "piper" else True)
    import types as _t
    ok, msg = V.install_piper(run=lambda cmd: _t.SimpleNamespace(returncode=0, stderr=""),
                              fetch=lambda url: b"x" * 2_000_000)
    assert ok is True
    assert (tmp_path / "de_DE-thorsten-medium.onnx").exists()
    assert (tmp_path / "de_DE-thorsten-medium.onnx.json").exists()
