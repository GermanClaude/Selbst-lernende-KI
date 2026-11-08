"""Spielmodus in der App (/api/spiel, Band/Bericht-Ereignisse, Bilder) und im Terminal (/spiel)."""
import json
import queue
import time
import urllib.error
import urllib.request

import pytest

from assistant.app.controller import AppController
from assistant.app.server import AppServer
from assistant.config import load_config
from assistant.spiel.windows import WachHalter
from tests._fakes import AnthroClient
from tests.test_spiel import SPIEL, Bilder, FakeTasten, Uhr, Vorne, _aktion, _text, _werkzeug


def _fakes(st, vorne=None):
    uhr = Uhr()
    tasten = FakeTasten()
    st.plattform = "win32"
    st.tasten_fabrik = lambda: tasten
    st.vordergrund = vorne or Vorne()
    st.aufnahme = Bilder()
    st.wach_fabrik = lambda: WachHalter(aufruf=lambda f: 1)
    st.speichern = lambda k, v: None
    st.fenster_liste = lambda: [dict(SPIEL)]
    st.notaus_fabrik = None
    st.uhr = uhr
    st.schlafe = uhr.schlafe
    return tasten


SKRIPT = [
    _aktion(1, [{"typ": "taste", "taste": "c"}, {"typ": "klick", "x": 0.4, "y": 0.6}]),
    _text("Bau-Menue offen."),
    _werkzeug(2, "spiel_notiz", {"art": "fortschritt", "text": "Kornspeicher platziert"}),
    _werkzeug(3, "spiel_ende", {"grund": "fertig", "text": "Markt und Kirche stehen."}),
    _text("Fertig."),
]


@pytest.fixture
def app(tmp_path):
    servers = []

    def make(scripted):
        cfg = load_config(tmp_path)
        cfg.update.modus = "aus"
        cfg.anthropic_api_key = "sk-ant-test-schluessel"
        cfg.provider.aktiv = "claude"
        server = AppServer(lambda broadcast: AppController(cfg, broadcast))
        server.start()
        ctl = server.controller
        ctl.brain.provider.client = AnthroClient(scripted)
        ctl.sehen.fenster_schutz = lambda an: ""
        server.events = server.hub.subscribe()
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.controller.shutdown()
        server.stop()


def _req(server, path, body=None, token=True, host=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-KI-Token"] = server.token
    if host:
        headers["Host"] = host
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}{path}", data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            roh = resp.read()
            try:
                return resp.status, json.loads(roh or b"{}")
            except ValueError:
                return resp.status, roh
    except urllib.error.HTTPError as exc:
        return exc.code, None


def _events_until(server, kind, timeout=15):
    seen, end = [], time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            event = json.loads(server.events.get(timeout=0.2))
        except queue.Empty:
            continue
        seen.append(event)
        if event["type"] == kind:
            return seen
    raise AssertionError(f"kein '{kind}' - gesehen: {[e['type'] for e in seen]}")


def test_api_spiel_schutz_status_und_zustimmung(app):
    server = app([_text("ok")])
    _fakes(server.controller.spiel)
    assert _req(server, "/api/spiel", {"aktion": "status"}, token=False)[0] == 403
    assert _req(server, "/api/spiel", {"aktion": "status"}, host="evil.example:80")[0] == 403
    code, body = _req(server, "/api/spiel", {"aktion": "status"})
    assert code == 200 and body["ok"] and body["spiel"]["aktiv"] is False
    assert body["laufend"] == ["Manor Lords"] and "Strg+Alt+Umschalt+P" in body["warnung"]
    assert body["spiel"]["zustimmung_noetig"] is True
    state = _req(server, "/api/state")[1]
    assert state["spiel"]["zustand"] == "aus" and any(c["cmd"] == "/spiel" for c in state["commands"])
    body = _req(server, "/api/spiel", {"aktion": "start", "ziel": "Stadt"})[1]
    assert not body["ok"] and body["zustimmung"] is True
    assert not server.controller.spiel.aktiv
    assert _req(server, "/api/spiel", {"aktion": "quatsch"})[1]["ok"] is False


def test_api_spiel_ganze_sitzung_mit_bericht_und_bildern(app):
    server = app(SKRIPT)
    ctl = server.controller
    tasten = _fakes(ctl.spiel)
    body = _req(server, "/api/spiel", {"aktion": "start", "ziel": "Bau eine wundersch\u00f6ne Stadt", "modus": "nacht",
                                       "stunden": 1, "euro": 2, "einverstanden": True})[1]
    assert body["ok"], body
    assert "wechsle jetzt ins Spiel" in body["text"]
    events = _events_until(server, "spiel_bericht", timeout=20)
    bericht = events[-1]
    assert "Markt und Kirche stehen" in bericht["text"] and "Kornspeicher platziert" in bericht["text"]
    assert bericht["grund"] == "fertig" and bericht["bilder"]
    assert any(e["type"] == "spiel" for e in events)  # Band bekommt Zwischenstaende
    assert tasten.gedrueckt(0x43) == 1
    # Bild des Berichts abrufbar - nur mit Schluessel, nur passende Namen
    url = bericht["bilder"][0]["url"]
    assert url.startswith("/api/bild/s/")
    code, daten = _req(server, url + f"?t={server.token}", token=False)
    assert code == 200 and isinstance(daten, bytes) and daten[:3] in (b"\xff\xd8\xff", b"\x89PN")
    assert _req(server, url, token=False)[0] == 403
    assert _req(server, "/api/bild/s/..%2Fsettings.png")[0] == 404
    assert _req(server, "/api/bild/s/kein_datum.png")[0] == 404
    # im Verlauf als Karte mit Bildern, Kosten zaehlen zur Sitzung
    hist = _req(server, "/api/history")[1]["messages"]
    assert any(m.get("level") == "spiel" and m.get("bilder") for m in hist)
    assert ctl.brain.usage.total_tokens > 0
    # die naechste Nachricht an Nova traegt den Bericht einmal mit
    assert "Bericht deiner letzten Spielsitzung" in ctl._with_afk_hints("Wie lief es?", None)
    assert ctl._with_afk_hints("Und jetzt?", None) is None


def test_api_spiel_stopp_und_kein_afk_waehrenddessen(app):
    server = app([_aktion(1, [{"typ": "warten", "zahl": 3}]), _text("weiter")])
    ctl = server.controller
    vorne = Vorne(dict(SPIEL, exe="ki-app.exe", titel="Nova", pid=1, hwnd=9))  # erst ist Nova vorne
    _fakes(ctl.spiel, vorne)
    ctl.spiel.zustimmen()
    assert _req(server, "/api/spiel", {"aktion": "start", "ziel": "Stadt"})[1]["ok"]
    assert ctl.spiel.status()["zustand"] == "sucht"
    afk = _req(server, "/api/afk", {"action": "start", "auftrag": "x"})[1]
    assert not afk["ok"] and "Spielmodus" in afk["error"]
    body = _req(server, "/api/spiel", {"aktion": "stopp"})[1]
    assert body["ok"]
    assert ctl.spiel.warten(10) and not ctl.spiel.aktiv


def test_api_spiel_nicht_waehrend_afk(app):
    server = app([_text("ok")])
    ctl = server.controller
    _fakes(ctl.spiel)
    ctl._afk_pending = {"auftrag": "", "minutes": None, "budget": None}
    body = _req(server, "/api/spiel", {"aktion": "start", "ziel": "Stadt", "einverstanden": True})[1]
    assert not body["ok"] and "AFK" in body["error"]


def test_nova_schlaegt_vor_die_app_oeffnet_den_dialog(app):
    from tests._fakes import anthro_msg, tool_use_block

    server = app([
        (anthro_msg([tool_use_block("spiel_starten", "s1", {"ziel": "Bau eine Stadt", "modus": "normal"})],
                    stop_reason="tool_use"), []),
        _text("Ich schlage dir den Spielmodus vor."),
    ])
    ctl = server.controller
    _fakes(ctl.spiel)
    assert _req(server, "/api/send", {"text": "Spiel bitte Manor Lords fuer mich"})[1]["ok"]
    events = _events_until(server, "spiel_vorschlag")
    assert events[-1]["ziel"] == "Bau eine Stadt"
    _events_until(server, "done")
    assert not ctl.spiel.aktiv  # nie von selbst
    assert _req(server, "/api/spiel", {"aktion": "ablehnen"})[1]["ok"] and ctl.spiel.vorschlag is None


def test_befehl_spiel_im_fenster(app):
    server = app([_text("ok")])
    ctl = server.controller
    _fakes(ctl.spiel)
    assert _req(server, "/api/send", {"text": "/spiel start Bau eine Stadt"})[1]["ok"]
    events = _events_until(server, "open")
    assert events[-1]["what"] == "spiel" and events[-1]["ziel"] == "Bau eine Stadt"  # Zustimmung im Dialog
    assert not ctl.spiel.aktiv


# -- Terminal ---------------------------------------------------------------------------
@pytest.fixture
def cli(tmp_path):
    from assistant.ui.cli import CLI

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    cfg.provider.aktiv = "claude"
    c = CLI(cfg)
    c.sehen.fenster_schutz = lambda an: ""
    yield c
    c.spiel.stoppen()
    c.memory.close()


def test_terminal_hilfe_und_ohne_zustimmung(cli, capsys, monkeypatch):
    from assistant.ui import cli as cli_modul

    _fakes(cli.spiel)
    cli._handle_command("/spiel")
    out = capsys.readouterr().out
    assert "Spielmodus ist aus" in out and "/spiel nacht" in out and "/spiel" in cli_modul.__doc__
    monkeypatch.setattr(cli, "_ask_yes", lambda *a, **k: False)
    cli._handle_command("/spiel start Stadt")
    out = capsys.readouterr().out
    assert "bitte einmal lesen" in out and "kein Spielmodus" in out and not cli.spiel.aktiv


def test_terminal_ganze_sitzung(cli, capsys, monkeypatch):
    cli.brain.provider.client = AnthroClient(SKRIPT)
    tasten = _fakes(cli.spiel)
    monkeypatch.setattr(cli, "_ask_yes", lambda *a, **k: True)
    cli._handle_command("/spiel nacht Bau eine Stadt")
    out = capsys.readouterr().out
    assert "[Spielmodus]" in out and "Spielbericht" in out and "Markt und Kirche stehen" in out
    assert tasten.gedrueckt(0x43) == 1 and cli.brain.usage.total_tokens > 0
    assert cli.spiel.letzte_sitzung.modus == "nacht"
    assert "Bericht deiner letzten Spielsitzung" in cli._spiel_rueckkehr() and cli._spiel_rueckkehr() == ""


def test_terminal_nicht_unter_linux(cli, capsys):
    cli._handle_command("/spiel start Stadt")
    assert "nur unter Windows" in capsys.readouterr().out
