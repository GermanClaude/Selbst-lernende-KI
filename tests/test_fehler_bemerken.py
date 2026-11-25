"""Fehler in der App: Nova merkt sie sich, bekommt einen Hinweis, reagiert gedrosselt selbst."""
import pytest

from assistant.app.controller import AppController
from assistant.config import load_config
from assistant.tools import ToolContext, build_registry
from assistant.tools import app_fehler


@pytest.fixture
def ctl(tmp_path):
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = cfg.anthropic_api_key or "sk-ant-test-schluessel"
    c = AppController(cfg, lambda e: None)
    yield c
    c.shutdown()


def test_hinweis_kommt_genau_einmal(ctl):
    ctl._fehler_merken("Spracheingabe", "Mikrofon nicht gefunden")
    erst = ctl._mit_fehler_hinweis("Hallo", None)
    assert "Mikrofon nicht gefunden" in erst and erst.endswith("Hallo")
    assert ctl._mit_fehler_hinweis("Hallo", None) is None          # schon gesehen -> kein Hinweis mehr


def test_fenster_fehler_ohne_auto_antwort(ctl, monkeypatch):
    monkeypatch.setattr(ctl, "run_background", lambda fn: pytest.fail("Fensterfehler: keine Auto-Antwort"))
    assert ctl.fehler_melden({"text": "TypeError: x is undefined (app.js:12)"})["ok"]
    assert ctl._mit_fehler_hinweis("x", None)


def test_auto_reaktion_gedrosselt(ctl, monkeypatch):
    laeufe = []
    monkeypatch.setattr(ctl, "run_background", lambda fn: laeufe.append(fn))
    ctl._fehler_merken("Spracheingabe", "Mikrofon weg", reagieren=True)
    ctl._fehler_merken("Spracheingabe", "Mikrofon weg", reagieren=True)       # gleiche Meldung: nicht nochmal
    ctl._fehler_merken("Spracheingabe", "anderer Fehler", reagieren=True)     # innerhalb 2 Min.: nicht nochmal
    assert len(laeufe) == 1


def test_ohne_schluessel_keine_auto_reaktion(tmp_path, monkeypatch):
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    c = AppController(cfg, lambda e: None)
    try:
        if c.config.api_key:
            pytest.skip("Testumgebung hat einen Schluessel")
        monkeypatch.setattr(c, "run_background", lambda fn: pytest.fail("ohne Gehirn keine Auto-Antwort"))
        c._fehler_merken("App", "kaputt", reagieren=True)
    finally:
        c.shutdown()


def test_werkzeug_zeigt_fehler_und_protokoll(tmp_path, monkeypatch):
    log = tmp_path / "ki.log"
    log.write_text("2026-11-25 10:00:00 [INFO] ki: Start\n"
                   "2026-11-25 10:00:01 [WARNING] ki: Spracheingabe: Erkennung ging nicht (whisper): Timeout\n"
                   "Traceback (most recent call last):\n  File \"x.py\", line 1\nValueError: kaputt\n"
                   "2026-11-25 10:00:02 [INFO] ki: alles gut\n", encoding="utf-8")
    auszug = app_fehler.log_auszug(40, pfad=log)
    assert "Erkennung ging nicht" in auszug and "ValueError: kaputt" in auszug and "alles gut" not in auszug
    monkeypatch.setattr(app_fehler, "log_auszug", lambda n: auszug)
    ctx = ToolContext(permissions=None, memory=None,
                      extra={"fehler_liste": lambda: [{"zeit": 0, "quelle": "App", "text": "Schluessel sk-ant-abcdefghijklmnopqrstuvwx kaputt"}]})
    out = app_fehler.AppFehlerTool().run(ctx)
    assert "Letzte Fehler" in out and "Protokoll" in out
    assert "abcdefghijklmnopqrstuvwx" not in out                         # Geheimnisse geschwaerzt


def test_werkzeug_ist_registriert():
    assert build_registry().get("app_fehler") is not None
