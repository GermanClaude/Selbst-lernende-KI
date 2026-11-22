"""Updates laufen schnell - die KI-Erklaerung der Neuerungen darf ein Update nie lange aufhalten."""
import time
from types import SimpleNamespace

from assistant.ui import cli as cli_mod
from assistant.updater import UpdateInfo

from tests.test_erlauben import _cli


def test_mit_zeitlimit_schnell_gibt_ergebnis():
    assert cli_mod._mit_zeitlimit(lambda: "fertig", 2.0) == "fertig"


def test_mit_zeitlimit_langsam_gibt_none():
    def lahm():
        time.sleep(1.0)
        return "zu spaet"

    assert cli_mod._mit_zeitlimit(lahm, 0.1) is None


def _cli_mit_provider(tmp_path, monkeypatch, ask_once):
    c = _cli(tmp_path, [], monkeypatch)
    c.config.anthropic_api_key = "sk-ant-test"
    c.config.provider.aktiv = "claude"
    c.brain = SimpleNamespace(provider=SimpleNamespace(ask_once=ask_once))
    return c


def _info():
    return UpdateInfo(current="0.1.0", new="0.2.0", notes="**Tolle Sachen**\n- Punkt X\n- Punkt Y",
                      download_url="", kind="exe")


def test_erklaerung_wird_genutzt_wenn_modell_schnell(tmp_path, monkeypatch):
    c = _cli_mit_provider(tmp_path, monkeypatch, lambda prompt, max_tokens=400: "- so erklaert dir Nova das")
    text = c._explain_update(_info())
    assert "so erklaert dir Nova das" in text


def test_faellt_auf_versionshinweise_zurueck_bei_langsamem_modell(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "UPDATE_ERKLAER_TIMEOUT", 0.2)

    def lahm(prompt, max_tokens=400):
        time.sleep(1.5)
        return "diese Erklaerung kommt zu spaet"

    c = _cli_mit_provider(tmp_path, monkeypatch, lahm)
    start = time.monotonic()
    text = c._explain_update(_info())
    dauer = time.monotonic() - start
    assert dauer < 1.0  # hat NICHT auf das langsame Modell gewartet
    assert "zu spaet" not in text and "Punkt X" in text  # die rohen Versionshinweise


def test_ohne_schluessel_direkt_die_notizen(tmp_path, monkeypatch):
    c = _cli(tmp_path, [], monkeypatch)
    c.config.anthropic_api_key = None
    c.config.deepseek_api_key = None
    c.config.gemini_api_key = None
    c.config.openai_api_key = None
    c.config.provider.aktiv = "claude"
    c.brain = SimpleNamespace(provider=SimpleNamespace(ask_once=lambda *a, **k: "sollte nicht aufgerufen werden"))
    text = c._explain_update(_info())
    assert "Punkt X" in text and "sollte nicht" not in text
