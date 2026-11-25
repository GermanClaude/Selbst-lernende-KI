"""Nova auf dem Handy (Termux): Server-Modus, Handy-Steuerung (Termux:API + ADB) - mit Attrappen."""
import subprocess
from types import SimpleNamespace

import pytest

from assistant import handy_steuerung as hs
from assistant.app import handy_server
from assistant.app.server import AppServer
from assistant.config import PermissionSettings, load_config
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry
from assistant.tools import handy_steuerung as hs_tool


def _r(stdout="", code=0, stderr=""):
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------- Termux erkennen
def test_termux_erkennen(monkeypatch):
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.setenv("PREFIX", "/usr")
    assert not hs.ist_termux()
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    assert hs.ist_termux()


# ---------------------------------------------------------------- Server-Modus
def test_fester_schluessel_bleibt(tmp_path):
    a = handy_server.fester_token(tmp_path)
    b = handy_server.fester_token(tmp_path)
    assert a == b and len(a) >= 24


def test_server_nimmt_festen_schluessel(tmp_path):
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    token = handy_server.fester_token(tmp_path)
    from assistant.app.controller import AppController
    server = AppServer(lambda b: AppController(cfg, b), token=token)
    try:
        assert server.token == token and server.url.endswith("?t=" + token)
    finally:
        server.httpd.server_close()
    kurz = AppServer(lambda b: None, token="zu-kurz")
    try:
        assert kurz.token != "zu-kurz"                     # zu kurze Schluessel werden nicht genommen
    finally:
        kurz.httpd.server_close()


def test_oberflaeche_oeffnet_zuerst_die_apk(monkeypatch):
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    monkeypatch.setattr(handy_server.shutil, "which", lambda n: "/bin/" + n)
    aufrufe = []
    womit = handy_server.oberflaeche_oeffnen("http://127.0.0.1:8765/?t=x",
                                             ausfuehren=lambda cmd, **kw: aufrufe.append(cmd) or _r("Starting: Intent"))
    assert womit == "apk" and aufrufe[0][:3] == ["am", "start", "-n"] and "de.nova.handy/.MainActivity" in aufrufe[0]
    # APK fehlt -> Browser ueber termux-open-url
    aufrufe.clear()
    womit = handy_server.oberflaeche_oeffnen(
        "http://127.0.0.1:8765/?t=x",
        ausfuehren=lambda cmd, **kw: aufrufe.append(cmd) or (_r("", 1, "Error: Activity class does not exist")
                                                             if cmd[0] == "am" else _r()))
    assert womit == "termux-browser" and aufrufe[-1][0] == "termux-open-url"


# ---------------------------------------------------------------- ADB
DUMP = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation="0">
<node text="" content-desc="" resource-id="" clickable="false" bounds="[0,0][1080,2400]">
  <node text="WhatsApp" content-desc="" resource-id="com.app:id/title" clickable="true" bounds="[100,200][300,260]"/>
  <node text="" content-desc="Suchen" resource-id="com.app:id/search" clickable="true" bounds="[900,100][1000,200]"/>
  <node text="" content-desc="" resource-id="" clickable="false" bounds="[0,0][10,10]"/>
</node></hierarchy>"""


def test_bildschirm_als_liste():
    liste = hs.elemente_aus_xml(DUMP)
    assert '"WhatsApp" [title] @ 200,230 klickbar' in liste
    assert "(Suchen) [search] @ 950,150 klickbar" in liste
    assert liste.count("\n") == 1                          # leere Knoten fallen weg


def _fake_adb(antworten):
    gesehen = []

    def run(cmd, **kw):
        gesehen.append(cmd)
        if cmd[:2] == ["adb", "devices"]:
            return _r("List of devices attached\n192.168.1.9:5555\tdevice\nlocalhost:40123\tdevice\n")
        return _r(antworten.get(cmd[3] if len(cmd) > 3 else "", "ok"))
    return run, gesehen


def test_adb_tippen_nimmt_das_eigene_handy(monkeypatch):
    monkeypatch.setattr(hs.shutil, "which", lambda n: "/bin/" + n)
    run, gesehen = _fake_adb({})
    hs.steuern("tippen", ausfuehren=run, x=200, y=230)
    assert gesehen[-1] == ["adb", "-s", "localhost:40123", "shell", "input", "tap", "200", "230"]


def test_adb_text_mit_leerzeichen(monkeypatch):
    monkeypatch.setattr(hs.shutil, "which", lambda n: "/bin/" + n)
    run, gesehen = _fake_adb({})
    hs.steuern("text", ausfuehren=run, text="Hallo Welt")
    assert gesehen[-1][-1] == "Hallo%sWelt"


def test_adb_fehlt_und_nicht_gekoppelt(monkeypatch):
    monkeypatch.setattr(hs.shutil, "which", lambda n: None)
    with pytest.raises(hs.HandyFehler, match="android-tools"):
        hs.adb_geraet()
    monkeypatch.setattr(hs.shutil, "which", lambda n: "/bin/" + n)
    with pytest.raises(hs.HandyFehler, match="Kabelloses Debugging"):
        hs.adb_geraet(ausfuehren=lambda cmd, **kw: _r("List of devices attached\n"))


def test_unbekannte_taste_und_paketname(monkeypatch):
    monkeypatch.setattr(hs.shutil, "which", lambda n: "/bin/" + n)
    run, _ = _fake_adb({})
    with pytest.raises(hs.HandyFehler):
        hs.steuern("taste", ausfuehren=run, text="selbstzerstoerung")
    with pytest.raises(hs.HandyFehler):
        hs.steuern("app_starten", ausfuehren=run, text="com.x; rm -rf /")


# ---------------------------------------------------------------- Werkzeug
def _ctx(tmp_path, confirm=lambda m, r: True, safe=False):
    pm = PermissionManager(PermissionSettings(safe_mode=safe, auto_confirm=False), tmp_path, confirm_fn=confirm)
    return ToolContext(permissions=pm, memory=None, extra={"app_root": tmp_path})


def test_werkzeug_nur_wo_es_ein_handy_gibt(monkeypatch):
    monkeypatch.setattr(hs, "verfuegbar", lambda: False)
    assert build_registry().get("handy_steuern") is None   # PC ohne ADB: Werkzeug bleibt weg
    monkeypatch.setattr(hs, "verfuegbar", lambda: True)
    assert build_registry().get("handy_steuern") is not None


def test_werkzeug_fragt_vor_dem_tippen_und_sperrt_installieren(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "verfuegbar", lambda: True)
    reg = build_registry()
    gefragt = []
    monkeypatch.setattr(hs, "steuern", lambda aktion, **p: "getippt")
    out, _ = reg.execute(_ctx(tmp_path, confirm=lambda m, r: gefragt.append(m) or False), "handy_steuern",
                         {"aktion": "tippen", "x": 1, "y": 2})
    assert gefragt and "getippt" not in out
    out, err = reg.execute(_ctx(tmp_path, safe=True), "handy_steuern", {"aktion": "installieren", "datei": "x.apk"})
    assert "Safe Mode" in str(out)


def test_werkzeug_termux_aktion_auf_dem_pc(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "verfuegbar", lambda: True)
    monkeypatch.setattr(hs, "ist_termux", lambda: False)
    out, _ = build_registry().execute(_ctx(tmp_path), "handy_steuern", {"aktion": "akku"})
    assert "Termux" in out


def test_werkzeug_ignoriert_fremde_angaben(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "verfuegbar", lambda: True)
    gesehen = {}
    monkeypatch.setattr(hs, "steuern", lambda aktion, **p: gesehen.update(p) or "ok")
    build_registry().execute(_ctx(tmp_path), "handy_steuern", {"aktion": "apps", "ausfuehren": "boese"})
    assert "ausfuehren" not in gesehen


# ---------------------------------------------------------------- System-Prompt
def test_prompt_kennt_das_handy_nur_auf_dem_handy(tmp_path, monkeypatch):
    from assistant.memory import Memory
    from assistant.personality import build_system_prompt

    cfg = load_config(tmp_path)
    mem = Memory(tmp_path / "m.sqlite3")
    monkeypatch.setattr(hs, "ist_termux", lambda: False)
    assert "ANDROID-HANDY" not in build_system_prompt(cfg, mem)
    monkeypatch.setattr(hs, "ist_termux", lambda: True)
    text = build_system_prompt(cfg, mem)
    assert "ANDROID-HANDY" in text and "kali.org" in text
