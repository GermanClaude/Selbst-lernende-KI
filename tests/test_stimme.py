"""Stimme waehlen: kostenlose Computerstimme oder realistische Cloud-Stimme (OpenAI/ElevenLabs)."""
import json

from assistant import voice as voicemod
from assistant.config import PermissionSettings, VoiceSettings, load_config
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry

from tests.test_erlauben import _cli


class _Fake:
    """Nimmt die HTTP-Aufrufe der Cloud-Stimme auf, ohne ins Netz zu gehen."""
    def __init__(self):
        self.calls = []

    def __call__(self, url, data, headers):
        self.calls.append((url, json.loads(data.decode("utf-8")), headers))
        return b""  # bei gesetztem http wird nichts abgespielt


def _spk(provider, settings, key="k-123"):
    fake = _Fake()
    spk = voicemod.CloudSpeaker(provider, key, settings, "de", http=fake)
    assert spk.available
    spk.say("Hallo Welt")
    assert spk.wait(5)
    spk.stop()
    return fake


def test_build_speaker_frei_ohne_schluessel():
    # "frei" -> immer die kostenlose Speaker-Klasse (pyttsx3), nie Cloud.
    spk = voicemod.build_speaker(VoiceSettings(stimme="frei"), {"openai": "x"}, http=_Fake())
    assert isinstance(spk, voicemod.Speaker)
    # "openai" gewaehlt, aber kein Schluessel -> Rueckfall auf die kostenlose Stimme.
    spk2 = voicemod.build_speaker(VoiceSettings(stimme="openai"), {"openai": None}, http=_Fake())
    assert isinstance(spk2, voicemod.Speaker)


def test_build_speaker_openai_mit_schluessel_ist_cloud():
    spk = voicemod.build_speaker(VoiceSettings(stimme="openai"), {"openai": "sk-proj-abc"}, http=_Fake())
    assert isinstance(spk, voicemod.CloudSpeaker) and spk.provider == "openai"


def test_cloud_openai_request_shape():
    fake = _spk("openai", VoiceSettings(stimme="openai", stimme_name="cedar", stimme_anweisung="freundlich"))
    url, body, headers = fake.calls[0]
    assert url == voicemod.OPENAI_TTS_URL
    assert body["model"] == voicemod.OPENAI_TTS_MODELL and body["voice"] == "cedar"
    assert body["response_format"] == "pcm" and body["instructions"] == "freundlich"
    assert headers["Authorization"].startswith("Bearer ")


def test_cloud_elevenlabs_request_shape():
    fake = _spk("elevenlabs", VoiceSettings(stimme="elevenlabs", stimme_name="voice-42"))
    url, body, headers = fake.calls[0]
    assert url.startswith(voicemod.ELEVEN_TTS_URL + "voice-42")
    assert "output_format=pcm_24000" in url
    assert body["model_id"] == voicemod.ELEVEN_MODELL and body["text"] == "Hallo Welt"
    assert headers["xi-api-key"] == "k-123"


def test_set_stimme_speichert_und_meldet_fehlenden_schluessel(tmp_path, monkeypatch):
    c = _cli(tmp_path, [], monkeypatch)
    r = c.set_stimme("openai")
    assert r["stimme"] == "openai" and r["fehlt_schluessel"] is True  # kein OpenAI-Schluessel im Test
    assert load_config(tmp_path).voice.stimme == "openai"
    r2 = c.set_stimme("elevenlabs", "meine-stimme")
    assert r2["stimme"] == "elevenlabs"
    cfg = load_config(tmp_path)
    assert cfg.voice.stimme == "elevenlabs" and cfg.voice.stimme_name == "meine-stimme"
    # unbekannte Stimme -> Fehler
    import pytest
    with pytest.raises(ValueError):
        c.set_stimme("quatsch")


def test_elevenlabs_schluessel_speichern(tmp_path, monkeypatch):
    c = _cli(tmp_path, [], monkeypatch)
    c.set_elevenlabs_key("xi-geheim")
    assert load_config(tmp_path).elevenlabs_api_key == "xi-geheim"
    assert c.set_stimme("elevenlabs")["fehlt_schluessel"] is False


def test_werkzeug_stimme_waehlen(tmp_path):
    root = tmp_path
    (root / "config").mkdir()
    reg = build_registry()
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=True), root,
                           confirm_fn=lambda m, r: True)
    gewaehlt = {}

    def setter(stimme, name=""):
        gewaehlt["stimme"], gewaehlt["name"] = stimme, name
        return {"ok": True, "stimme": stimme, "name": name, "fehlt_schluessel": stimme == "elevenlabs",
                "info": voicemod.stimme_info(stimme)}

    ctx = ToolContext(permissions=pm, extra={"set_stimme": setter})
    out, err = reg.execute(ctx, "stimme_waehlen", {"stimme": "openai", "name": "nova"})
    assert not err and gewaehlt == {"stimme": "openai", "name": "nova"} and "nova" not in out.lower()
    out2, _ = reg.execute(ctx, "stimme_waehlen", {"stimme": "elevenlabs"})
    assert "Schluessel" in out2 or "schluessel" in out2.lower()


def test_stimme_info():
    assert voicemod.stimme_info("openai")["kostenlos"] is False
    assert voicemod.stimme_info("frei")["kostenlos"] is True
    assert voicemod.stimme_info("gibtsnicht")["id"] == "frei"  # unbekannt -> Standard
