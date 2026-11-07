"""Jarvis-Modus, App-Aussehen, Tutorial, Stuetzraeder."""
import threading
from array import array
from types import SimpleNamespace

import pytest

from assistant import aussehen, voice
from assistant.config import load_config
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry


def _block(level):
    return array("h", [level, -level] * 800).tobytes()  # 1600 Werte = 100 ms


class FakeSD:
    """Liefert vorgegebene 100-ms-Bloecke an den Callback wie ein Mikrofon."""

    def __init__(self, blocks):
        self.blocks = blocks

    def RawInputStream(self, callback, **kw):  # noqa: N802
        fake = self

        class Stream:
            def __enter__(self):
                def feed():
                    for b in fake.blocks:
                        callback(b, 1600, None, None)
                threading.Thread(target=feed, daemon=True).start()
                return self

            def __exit__(self, *a):
                return False

        return Stream()


def test_listens_until_a_pause():
    quiet, loud = _block(50), _block(4000)
    blocks = [quiet] * 6 + [loud] * 15 + [quiet] * 12 + [loud] * 5
    levels = []
    pcm = voice.listen_utterance(on_level=levels.append, silence=1.0, sd_module=FakeSD(blocks))
    seconds = len(pcm) / 32000
    assert 2.0 <= seconds <= 3.0  # Vorlauf + 1,5 s Sprache + ~1 s Pause, das Spaetere nicht
    assert max(levels) > 0.5 and min(levels) < 0.1


def test_listen_returns_empty_when_nobody_speaks_and_none_on_stop():
    assert voice.listen_utterance(start_timeout=0.3, sd_module=FakeSD([_block(30)] * 40)) == b""
    stop = threading.Event()
    stop.set()
    assert voice.listen_utterance(stop_event=stop, sd_module=FakeSD([])) is None


def test_speech_text_is_speakable():
    out = voice.speech_text("## Titel\n**fett** und `x`\n\n| A | B |\n|---|---|\n| 1 | 2 |\n```py\nprint()\n```")
    assert "#" not in out and "*" not in out and "|" not in out and "print" not in out
    assert "A, B" in out and "Code siehe Bildschirm" in out


def _ctx(tmp_path, notify=None):
    pm = PermissionManager(load_config(tmp_path).permissions.__class__(safe_mode=False, auto_confirm=True),
                           tmp_path, confirm_fn=lambda m, r: True, app_root=tmp_path)
    ctx = ToolContext(permissions=pm, memory=None)
    ctx.extra["app_root"] = tmp_path
    if notify:
        ctx.extra["on_appearance"] = notify
    return ctx


def test_nova_can_restyle_the_app(tmp_path):
    seen = []
    reg = build_registry()
    ctx = _ctx(tmp_path, notify=lambda: seen.append(1))
    out, err = reg.execute(ctx, "app_anpassen", {"aktion": "setzen", "akzentfarbe": "#16a34a", "schriftgroesse": 115})
    assert not err and "zeigt es schon an" in out and seen
    assert aussehen.load(tmp_path) == {"akzentfarbe": "#16a34a", "schriftgroesse": 115}
    out, _ = reg.execute(ctx, "app_anpassen", {"aktion": "setzen", "akzentfarbe": "gruen"})
    assert "Nicht geaendert" in out
    reg.execute(ctx, "app_anpassen", {"aktion": "css_ersetzen",
                                      "css": "@import url(https://boese.de/x.css); body{background:url(https://x.de/a.png)}"})
    css = aussehen.css(tmp_path)
    assert "@import" not in css and "https://" not in css and "background:none" in css
    reg.execute(ctx, "app_anpassen", {"aktion": "zuruecksetzen"})
    assert aussehen.load(tmp_path) == {} and aussehen.css(tmp_path) == ""


def test_tutorial_steps_and_done(tmp_path):
    from assistant import tutorial

    cfg = load_config(tmp_path)
    steps = tutorial.steps(cfg)
    assert steps[0]["titel"] == "Hallo, ich bin Nova!" and any(s["zeigen"] for s in steps)
    assert not tutorial.is_done(tmp_path)
    tutorial.mark_done(tmp_path)
    assert tutorial.is_done(tmp_path)


def test_training_wheels_on_and_off(tmp_path, monkeypatch):
    from tests.test_erlauben import _cli

    c = _cli(tmp_path, [], monkeypatch)
    c.set_training_wheels(False)
    cfg = load_config(tmp_path)
    assert not cfg.permissions.safe_mode and cfg.permissions.auto_confirm and cfg.permissions.allow_full_filesystem
    assert c.training_wheels_state() == "aus"
    c.set_training_wheels(True)
    cfg = load_config(tmp_path)
    assert cfg.permissions.safe_mode and not cfg.permissions.auto_confirm and not cfg.permissions.allow_full_filesystem
    assert c.training_wheels_state() == "an"


def test_exit_phrases():
    from assistant.ui.cli import _is_exit_phrase

    assert _is_exit_phrase("Chat-Modus bitte") and _is_exit_phrase("Beenden.")
    assert not _is_exit_phrase("Wie wird das Wetter morgen?")


def test_nova_can_choose_her_sphere(tmp_path):
    reg = build_registry()
    ctx = _ctx(tmp_path)
    out, _ = reg.execute(ctx, "app_anpassen", {"aktion": "setzen", "avatar": "sphaere", "sphaere_farbe": "#a855f7",
                                               "bewegung": "lebhaft"})
    assert aussehen.load(tmp_path) == {"avatar": "sphaere", "sphaere_farbe": "#a855f7", "bewegung": "lebhaft"}
    out, _ = reg.execute(ctx, "app_anpassen", {"aktion": "setzen", "bewegung": "wild"})
    assert "Nicht geaendert" in out


def test_mic_level_reaches_the_window():
    from assistant.voice import VoiceCapture

    seen = []
    cap = VoiceCapture(SimpleNamespace(erkennung="auto"))
    cap.on_level = seen.append
    cap._on_audio(array("h", [3000, -3000] * 400).tobytes(), 800, None, None)
    assert seen and 0.9 <= seen[0] <= 1.0 and cap.seconds() > 0
