"""Schluessel im Chat einrichten, verstaendliche Fehler, App ohne Konsole (KI-App.exe)."""
import sys
from types import SimpleNamespace

import pytest

from assistant import schluessel
from assistant.config import load_config


def test_keys_are_found_and_masked():
    assert schluessel.find_key("sk-1234567890abcdef1234567890abcdef") == "sk-1234567890abcdef1234567890abcdef"
    assert schluessel.find_key("mein key: sk-ant-api03-AbCdEf1234567890_xyz-QQ bitte") == \
        "sk-ant-api03-AbCdEf1234567890_xyz-QQ"
    assert schluessel.find_key("Was ist ein sk-Ski?") is None
    assert schluessel.provider_for_key("sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxx") == "claude"
    assert schluessel.provider_for_key("sk-1234567890abcdef1234") == "deepseek"
    assert schluessel.mask("sk-1234567890abcdef1234") == "sk-123…1234"


class Err(Exception):
    def __init__(self, status, text="x"):
        super().__init__(text)
        self.status_code = status


def test_errors_are_explained():
    kind, msg = schluessel.classify(Err(401), "deepseek")
    assert kind == "invalid" and "abgelehnt" in msg
    kind, msg = schluessel.classify(Err(402, "Insufficient Balance"), "deepseek")
    assert kind == "balance" and "Guthaben" in msg and "deepseek" in msg.lower()
    kind, _ = schluessel.classify(Err(400, "Your credit balance is too low"), "claude")
    assert kind == "balance"
    assert schluessel.friendly_error(ValueError("kaputt"), "deepseek") is None


def test_setup_saves_key_and_switches_brain(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    cfg = load_config(tmp_path)
    assert cfg.active_provider == "claude"
    bad = schluessel.setup(cfg, key="sk-1234567890abcdef1234567890ab",
                           tester=lambda c, p, k: (False, "balance", "Guthaben leer"))
    assert not bad["ok"] and bad["kind"] == "balance" and not (tmp_path / ".env").exists()
    good = schluessel.setup(cfg, key="sk-1234567890abcdef1234567890ab", tester=lambda c, p, k: (True, "ok", ""))
    assert good["ok"] and good["changed_provider"] and cfg.active_provider == "deepseek"
    again = load_config(tmp_path)
    assert again.active_provider == "deepseek" and again.deepseek_api_key == "sk-1234567890abcdef1234567890ab"


def test_pasting_a_key_in_the_terminal_never_reaches_the_model(tmp_path, monkeypatch):
    from assistant.ui import cli as cli_mod

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(schluessel, "test_key", lambda c, p, k: (True, "ok", ""))
    cfg = load_config(tmp_path)
    c = cli_mod.CLI.__new__(cli_mod.CLI)
    c.config = cfg
    switched = []
    c.brain = SimpleNamespace(switch_provider=lambda: switched.append(1) or True)
    assert c._setup_key("sk-1234567890abcdef1234567890ab")
    assert switched and cfg.active_provider == "deepseek"


def test_app_without_console_starts(tmp_path, monkeypatch):
    """KI-App.exe: kein Konsolenfenster -> stdin/stdout/stderr sind None (das war der Absturz)."""
    import assistant.__main__ as main_mod
    from assistant.app import launcher

    started = {}

    def fake_run_app(config, started_by=None, **kw):
        from assistant.app.controller import AppController

        AppController(config, lambda e: None)  # hier stuerzte es ab (isatty auf None)
        print("geht")                          # print ohne Konsole darf nicht abstuerzen
        started["ok"] = True
        return 0

    monkeypatch.setattr(launcher, "run_app", fake_run_app)
    monkeypatch.setattr(main_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("assistant.config.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "stdin", None)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    try:
        code = main_mod.main(["--app"])
    finally:
        out = sys.stdout
    assert code == 0 and started.get("ok") and not out.isatty()


@pytest.fixture
def app_server(tmp_path, monkeypatch):
    from assistant.app.controller import AppController
    from assistant.app.server import AppServer

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = None
    server = AppServer(lambda b: AppController(cfg, b))
    server.start()
    server.events = server.hub.subscribe()
    yield server
    server.controller.shutdown()
    server.stop()


def test_app_key_paste_is_masked_and_sets_up_the_brain(app_server, monkeypatch):
    from tests.test_app import _events_until, _req

    monkeypatch.setattr(schluessel, "test_key", lambda c, p, k: (True, "ok", ""))
    ctl = app_server.controller
    assert _req(app_server, "/api/state")[1]["api_key_missing"] is True
    _req(app_server, "/api/send", {"text": "Hallo"})                   # ohne Schluessel: Hinweis statt Absturz
    notice = _events_until(app_server, "notice")[-1]
    assert "sk-" in notice["text"] and "platform.deepseek.com" in notice["text"]
    key = "sk-1234567890abcdef1234567890ab"
    _req(app_server, "/api/send", {"text": key})
    events = _events_until(app_server, "notice")
    users = [e["text"] for e in events if e["type"] == "user"]
    assert users and key not in users[-1] and "…" in users[-1]          # nur gekuerzt angezeigt
    assert all(key not in str(m) for m in ctl.history)
    _events_until(app_server, "state")
    state = _req(app_server, "/api/state")[1]
    assert state["api_key_missing"] is False and state["provider"] == "deepseek"
    assert ctl.brain.provider.name == "deepseek"
    info = _req(app_server, "/api/setup")[1]
    assert info["provider"] == "deepseek" and info["providers"][0]["has_key"] and key not in str(info)


def test_app_setup_endpoint_reports_problems(app_server, monkeypatch):
    from tests.test_app import _req

    monkeypatch.setattr(schluessel, "test_key", lambda c, p, k: (False, "invalid", "Der Schluessel wurde abgelehnt"))
    status, body = _req(app_server, "/api/setup", {"provider": "deepseek", "api_key": "sk-falsch1234567890abcdefgh"})
    assert body["ok"] is False and body["kind"] == "invalid" and "abgelehnt" in body["error"]
    assert _req(app_server, "/api/state")[1]["api_key_missing"] is True


def test_brain_with_a_key_is_used_automatically(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-1234567890abcdef1234567890ab\n", encoding="utf-8")
    cfg = load_config(tmp_path)                      # eingestellt ist Claude, Schluessel nur fuer DeepSeek
    assert cfg.active_provider == "deepseek" and cfg.provider_auto_switched == "claude" and cfg.api_key
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    (tmp_path / ".env").write_text("", encoding="utf-8")
    assert load_config(tmp_path).active_provider == "claude"                   # ohne Schluessel: wie eingestellt


def test_server_texts_get_umlauts():
    from assistant.anzeige import schoen

    kind, msg = schluessel.classify(Err(401), "deepseek")
    assert "Schlüssel" in schoen(msg) and "füge" in schoen(msg)
    _, msg = schluessel.classify(Err(402), "deepseek")
    assert "->" not in msg and "„Top up“" in msg
