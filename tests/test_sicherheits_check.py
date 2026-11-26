"""Sicherheits-Check (die typischen 10 Luecken): Schluessel bleiben geheim, die KI gibt sich keine Rechte,
Raten des Zugangs-Schluessels wird gebremst, Telegram-Besitzer nur mit Code."""
import http.client
from pathlib import Path

import pytest

from assistant import geheimnisse as G
from assistant import handy
from assistant.app import handy_server as hs
from assistant.app.server import AppServer
from assistant.config import PermissionSettings
from assistant.permissions import PermissionError_, PermissionManager
from assistant.tools import ToolContext
from assistant.tools.base import Tool, ToolRegistry

UMGEBUNG = {"PATH": "/usr/bin", "HOME": "/home/nova", "ANTHROPIC_API_KEY": "sk-ant-echt-1234567890abcdef",
            "TELEGRAM_BOT_TOKEN": "123456:ABCDEFabcdef123456", "NOVA_ABGLEICH_PASSWORT": "Fahrrad-Mond-47",
            "TG_API_HASH": "0123456789abcdef0123", "HA_TOKEN": "eyJhbGciOi.xyz.123456", "NOVA_TOKEN": "x" * 30,
            "NOVA_ABGLEICH_REPO": "ich/repo"}


def test_befehle_bekommen_keine_schluessel():
    env = G.umgebung_ohne_geheimnisse(UMGEBUNG)
    assert env == {"PATH": "/usr/bin", "HOME": "/home/nova"}


def test_schluessel_werden_geschwaerzt():
    text = "Ausgabe: ANTHROPIC_API_KEY=sk-ant-echt-1234567890abcdef und 123456:ABCDEFabcdef123456"
    sauber = G.werte_schwaerzen(text, UMGEBUNG)
    assert "sk-ant-echt" not in sauber and "ABCDEFabcdef" not in sauber and G.ERSATZ in sauber


def test_werkzeug_ergebnis_wird_geschwaerzt(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-geheim-987654321")

    class Plaudertasche(Tool):
        name = "plaudern"
        description = "gibt die Umgebung aus"
        input_schema = {"type": "object", "properties": {}}

        def run(self, ctx):
            import os
            return "env: " + os.environ["DEEPSEEK_API_KEY"]

    reg = ToolRegistry()
    reg.register(Plaudertasche())
    out, fehler = reg.execute(ToolContext(permissions=None, memory=None), "plaudern", {})
    assert "sk-deepseek-geheim" not in out and not fehler


def test_shell_umgebung_ohne_schluessel(monkeypatch):
    from assistant.tools import shell

    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-geheim-1234567890")
    env = shell._child_env()
    assert "OPENAI_API_KEY" not in env and "PATH" in {k.upper() for k in env}


@pytest.mark.parametrize("pfad", [".env", "config/settings.toml", "config/permissions.toml",
                                  "config/plugins.json", "data/server_token", "data/telegram_konto.session",
                                  "data/vonage_private.key", "data/memory.sqlite3"])
def test_ki_kommt_nicht_an_eigene_schluessel_und_rechte(tmp_path, pfad):
    pm = PermissionManager(PermissionSettings(safe_mode=False, allow_full_filesystem=True, vollzugriff=True),
                           tmp_path / "workspace", confirm_fn=lambda m, r: True, app_root=tmp_path)
    with pytest.raises(PermissionError_, match="geschuetzte Datei"):
        pm.resolve_path(str(tmp_path / pfad))
    with pytest.raises(PermissionError_):
        pm.resolve_path("../" + pfad)                       # auch ueber Umwege nicht


def test_normale_dateien_gehen_weiter(tmp_path):
    pm = PermissionManager(PermissionSettings(safe_mode=False, allow_full_filesystem=True),
                           tmp_path / "workspace", confirm_fn=lambda m, r: True, app_root=tmp_path)
    assert pm.resolve_path(str(tmp_path / "config" / "persona.md")).name == "persona.md"
    assert pm.resolve_path("notiz.txt").name == "notiz.txt"


def test_telegram_besitzer_nur_mit_code():
    code = handy.kopplungs_code()
    assert len(code) == 6 and code.isdigit()
    assert handy.ist_kopplung(f"Mein Code: {code[:3]} {code[3:]}", code)
    assert not handy.ist_kopplung("/start", code) and not handy.ist_kopplung("hallo", "")


def _status(server, pfad, xff=None):
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    kopf = {"Host": "nova.example"}
    if xff:
        kopf["X-Forwarded-For"] = xff
    c.request("GET", pfad, headers=kopf)
    return c.getresponse().status


TOKEN = "richtiger-schluessel-abcdefghijklmnop"


def test_raten_wird_gebremst():
    s = AppServer(lambda b: type("C", (), {"state": lambda self: {}})(), port=0, token=TOKEN, hosts="*")
    s.start()
    try:
        for i in range(s.SPERRE_VERSUCHE):
            assert _status(s, f"/api/state?t=falsch{i:030d}", xff="9.9.9.9") == 403
        assert _status(s, "/api/state?t=" + TOKEN, xff="1.1.1.1, 9.9.9.9") == 403   # gesperrt, auch mit richtigem
        assert _status(s, "/api/state?t=" + TOKEN, xff="8.8.8.8") == 200            # andere Adresse: geht
    finally:
        s.stop()


def test_am_pc_keine_aussperrung():
    s = AppServer(lambda b: type("C", (), {"state": lambda self: {}})(), port=0, token=TOKEN)
    s.start()
    try:
        c = lambda t: http.client.HTTPConnection("127.0.0.1", s.port, timeout=5)  # noqa: E731
        for _ in range(s.SPERRE_VERSUCHE + 2):
            k = c(0)
            k.request("GET", "/api/state?t=alt-alt-alt-alt-alt-alt-alt", headers={"Host": f"127.0.0.1:{s.port}"})
            assert k.getresponse().status == 403
        k = c(0)
        k.request("GET", "/api/state?t=" + TOKEN, headers={"Host": f"127.0.0.1:{s.port}"})
        assert k.getresponse().status == 200
    finally:
        s.stop()


def test_schwacher_cloud_schluessel_wird_ersetzt(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_TOKEN", "a" * 30)
    e = hs.cloud_einstellungen(tmp_path)
    assert not e["token_eigen"] and e["token"] != "a" * 30
