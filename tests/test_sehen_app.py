"""Live-Sehen in der App: /api/sehen, /api/kamera/bild, Wortmeldungen ueber die Warteschlange, Werkzeug."""
import io
import json
import queue
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from assistant.app.controller import AppController
from assistant.app.server import AppServer
from assistant.config import load_config
from assistant.sehen.dienst import Weckpaket
from assistant.tools import ToolContext, build_registry
from assistant.tools.base import ToolOutput
from tests._fakes import AnthroClient, anthro_msg, text_block


def _streamed(text):
    return (anthro_msg([text_block(text)]), [SimpleNamespace(type="text", text=t) for t in (text[:4], text[4:])])


class _Langsam:
    """Antwort, die langsam kommt (bis sie angehalten wird)."""

    def __iter__(self):
        for _ in range(100):
            time.sleep(0.05)
            yield SimpleNamespace(type="text", text="bla ")


class FakeAuge:
    def __init__(self, einst):
        self.einst, self.befehle, self.gestoppt = einst, [], False

    def start(self):
        pass

    def senden(self, befehl):
        self.befehle.append(befehl)

    def lies(self, timeout=0.1):
        time.sleep(min(timeout, 0.05))
        return None

    def lebt(self):
        return not self.gestoppt

    def stop(self, warten=2.0):
        self.gestoppt = True


@pytest.fixture
def app(tmp_path):
    servers = []

    def make(scripted):
        cfg = load_config(tmp_path)
        cfg.update.modus = "aus"
        cfg.anthropic_api_key = cfg.anthropic_api_key or "sk-ant-test-schluessel"
        cfg.provider.aktiv = "claude"
        server = AppServer(lambda broadcast: AppController(cfg, broadcast))
        server.start()
        ctl = server.controller
        ctl.brain.provider.client = AnthroClient(scripted)
        ctl.sehen.auge_fabrik = FakeAuge
        ctl.sehen.bildschirm_moeglich = True
        ctl.sehen.fenster_schutz = lambda an: ""
        server.events = server.hub.subscribe()
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.controller.shutdown()
        server.stop()


def _req(server, path, body=None, token=True, host=None, raw=None, ctype="application/json"):
    headers = {"Content-Type": ctype}
    if token:
        headers["X-KI-Token"] = server.token
    if host:
        headers["Host"] = host
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}{path}", data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, None


def _events_until(server, kind, timeout=10):
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


def _jpeg(farbe=(200, 30, 30)):
    Image = pytest.importorskip("PIL.Image")
    puffer = io.BytesIO()
    Image.new("RGB", (64, 48), farbe).save(puffer, "JPEG")
    return puffer.getvalue()


def _paket(text="Ein Hinweis-/Dialogfenster ist aufgegangen: excel.exe Fehler", bilder=None):
    return Weckpaket(text=f"[Live-Sehen]\nGerade passiert: {text}\nSonst antworte nur mit [still].",
                     anzeige="Nova hat etwas bemerkt: " + text, bilder=list(bilder or []), wichtig=0.95)


def _einschalten(server, **extra):
    return _req(server, "/api/sehen", {"aktion": "an", "einverstanden": True, **extra})[1]


def test_einschalten_nur_mit_zustimmung(app):
    server = app([])
    status, state = _req(server, "/api/state")
    assert state["sehen"]["aktiv"] is False and state["sehen"]["zustimmung_noetig"] is True
    body = _req(server, "/api/sehen", {"aktion": "an"})[1]
    assert body["ok"] is False and body["zustimmung"] is True and "Passwortfelder" in body["warnung"]
    assert "Datenschutzregeln" in body["warnung"]
    assert _req(server, "/api/sehen", {"aktion": "an"}, token=False)[0] == 403
    assert _req(server, "/api/sehen", {"aktion": "an"}, host="evil.example:80")[0] == 403
    body = _einschalten(server, quelle="bildschirm")
    assert body["ok"] and body["sehen"]["aktiv"] and body["sehen"]["quellen"] == ["bildschirm"]
    assert _req(server, "/api/state")[1]["sehen"]["zustimmung_noetig"] is False
    events = _events_until(server, "notice")
    assert events[-1]["level"] == "sehen" and "Live-Sehen ist an" in events[-1]["text"]
    assert _req(server, "/api/sehen", {"aktion": "pause"})[1]["sehen"]["pausiert"] is True
    assert _req(server, "/api/sehen", {"aktion": "aus"})[1]["sehen"]["aktiv"] is False
    assert _req(server, "/api/sehen", {"aktion": "quelle", "quelle": "alles"})[1]["ok"] is False
    assert _req(server, "/api/sehen", {"aktion": "kaputt"})[1]["ok"] is False


def test_kamera_bild_endpunkt(app):
    server = app([])
    bild = _jpeg()
    assert _req(server, "/api/kamera/bild", raw=bild, ctype="image/jpeg", token=False)[0] == 403
    assert _req(server, "/api/kamera/bild", raw=bild, ctype="image/jpeg", host="evil.example:80")[0] == 403
    assert _req(server, "/api/kamera/bild", raw=b"<svg></svg>" * 10, ctype="image/jpeg")[0] == 415
    zu_gross = b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024)
    assert _req(server, "/api/kamera/bild", raw=zu_gross, ctype="image/jpeg")[0] == 413
    status, body = _req(server, "/api/kamera/bild", raw=bild, ctype="image/jpeg")
    assert status == 200 and body["ok"] is False and body["weiter"] is False      # Webcam ist aus
    _req(server, "/api/sehen", {"aktion": "kamera", "vorhanden": True})
    body = _einschalten(server, quelle="webcam")
    assert body["ok"] and body["sehen"]["kamera_gewuenscht"] is True and server.controller.kamera_erlaubt()
    status, body = _req(server, "/api/kamera/bild", raw=bild, ctype="image/jpeg")
    assert status == 200 and body["ok"] is True
    assert server.controller.sehen.kamera.letztes() == bild
    _req(server, "/api/sehen", {"aktion": "aus"})
    assert server.controller.sehen.kamera.letztes() is None and not server.controller.kamera_erlaubt()


def test_wortmeldung_mit_text_und_bild(app):
    from assistant.bilder import vorbereiten

    server = app([_streamed("Da ist ein Fehlerfenster \u2013 soll ich helfen?")])
    ctl = server.controller
    ctl._sehen_wecken(_paket(bilder=[vorbereiten(_jpeg(), "bildschirm.jpg")]))
    events = _events_until(server, "done")
    kinds = [e["type"] for e in events]
    notice = next(e for e in events if e["type"] == "notice")
    assert notice["level"] == "sehen" and "hat etwas bemerkt" in notice["text"]
    assert "user" not in kinds and kinds.index("notice") < kinds.index("start") < kinds.index("done")
    gesendet = json.loads(ctl.brain.provider.client.messages.requests[-1])[-1]
    assert gesendet["role"] == "user" and any(b.get("type") == "image" for b in gesendet["content"])
    assert any("Gerade passiert" in b.get("text", "") for b in gesendet["content"] if b.get("type") == "text")
    assert ctl.permissions.away is False and ctl.busy is False
    rollen = [m["role"] for m in _req(server, "/api/history")[1]["messages"]]
    assert rollen == ["notice", "assistant"]


def test_nichts_zu_sagen_wird_ganz_zurueckgenommen(app):
    server = app([_streamed("[still]")])
    ctl = server.controller
    vorher = len(ctl.brain.provider.messages)
    ctl._sehen_wecken(_paket())
    events = _events_until(server, "sehen_still")
    assert events[-1]["chip"] is True and "chunk" not in [e["type"] for e in events]
    assert len(ctl.brain.provider.messages) == vorher
    assert _req(server, "/api/history")[1]["messages"] == []


def test_wortmeldung_wartet_auf_die_laufende_antwort_und_deine_nachricht_geht_vor(app):
    server = app([_streamed("Ich habe etwas gesehen"), _streamed("Antwort auf dich")])
    ctl = server.controller
    _einschalten(server, quelle="bildschirm")
    with ctl._lock:
        ctl.busy = True                       # z.B. eine laufende Antwort
    ctl._sehen_wecken(_paket())
    assert ctl._sehen_pending is not None
    ctl._release()                            # Antwort fertig -> jetzt die Wortmeldung
    _events_until(server, "done")
    assert ctl.brain.provider.client.messages.calls == 1
    # Wartet eine Wortmeldung und du schreibst: deine Nachricht kommt, die Wortmeldung verfaellt
    with ctl._lock:
        ctl.busy = True
    ctl._sehen_wecken(_paket("Neues Fenster"))
    assert ctl.submit("Hallo")["queued"] is True and ctl._sehen_pending is None
    ctl._release()
    events = _events_until(server, "done")
    assert "Hallo" in [e.get("text") for e in events if e["type"] == "user"]
    time.sleep(0.3)
    assert ctl.brain.provider.client.messages.calls == 2 and not ctl.busy


def test_alte_wortmeldung_verfaellt(app):
    server = app([_streamed("x")])
    ctl = server.controller
    _einschalten(server, quelle="bildschirm")
    with ctl._lock:
        ctl.busy = True
    paket = _paket()
    paket.zeit -= 60
    ctl._sehen_wecken(paket)
    ctl._release()
    time.sleep(0.2)
    assert ctl.brain.provider.client.messages.calls == 0


def test_deine_nachricht_unterbricht_eine_wortmeldung_ohne_abbruch_notiz(app):
    from assistant.providers.base import ABORT_NOTE

    server = app([(anthro_msg([text_block("bla bla")]), _Langsam()), _streamed("Antwort auf dich")])
    ctl = server.controller
    vorher = len(ctl.brain.provider.messages)
    ctl._sehen_wecken(_paket())
    _events_until(server, "chunk")
    body = ctl.submit("Was ist los?")
    assert body["ok"] and body["interrupt"] is True
    events = _events_until(server, "done")
    assert "sehen_still" in [e["type"] for e in events]
    texte = json.dumps(ctl.brain.provider.messages, default=str, ensure_ascii=False)
    assert ABORT_NOTE not in texte and "Gerade passiert" not in texte      # ganz zurueckgenommen
    assert len(ctl.brain.provider.messages) == vorher + 2


def test_waehrend_afk_keine_wortmeldung(app):
    server = app([_streamed("x")])
    ctl = server.controller
    ctl._afk_pending = {"auftrag": ""}
    ctl._sehen_wecken(_paket())
    time.sleep(0.2)
    assert ctl.brain.provider.client.messages.calls == 0 and ctl._sehen_pending is None


def test_befehl_sehen_im_chat(app):
    server = app([])
    _req(server, "/api/send", {"text": "/sehen status"})
    events = _events_until(server, "notice")
    assert "Live-Sehen ist aus" in events[-1]["text"]
    assert any(c["cmd"] == "/sehen" for c in _req(server, "/api/state")[1]["commands"])


def test_fenster_zu_heisst_wegschauen(app):
    server = app([])
    _einschalten(server, quelle="bildschirm")
    auge = server.controller.sehen._auge
    server.controller.shutdown()
    assert not server.controller.sehen.aktiv and auge.gestoppt


# -- Werkzeug -------------------------------------------------------------------------------
class _Dienst:
    def __init__(self, aktiv=True, bild=None, grund=""):
        self.aktiv, self._bild, self._grund = aktiv, bild, grund
        self.aus_gerufen = False

    def aus(self):
        self.aus_gerufen = True
        return "Live-Sehen ist aus."

    def pause(self):
        return "Pause."

    def aktuelles_bild(self):
        return self._bild, self._grund

    def kurz_text(self):
        return "- Wechsel zu excel.exe"

    def status(self):
        return {"quellen": ["bildschirm"], "pausiert": False, "weckungen_stunde": 2, "max_weckungen": 20}


def _werkzeug(dienst, perms=None, **extra):
    perms = perms or SimpleNamespace(require=lambda *a, **k: None, away=False)
    ctx = ToolContext(permissions=perms, extra={"sehen": dienst, **extra})
    return build_registry().get("live_sehen"), ctx


def test_werkzeug_einschalten_kann_nova_nicht_selbst():
    tool, ctx = _werkzeug(_Dienst(aktiv=False))
    assert set(tool.input_schema["properties"]["aktion"]["enum"]) == {"ansehen", "verlauf", "status", "pause", "aus"}
    assert "Einschalten kann nur dein Mensch" in tool.run(ctx, aktion="ansehen")


def test_werkzeug_liefert_ein_bild_aber_nie_im_afk_modus():
    from assistant.bilder import vorbereiten

    bild = vorbereiten(_jpeg(), "bildschirm.jpg")
    tool, ctx = _werkzeug(_Dienst(bild=bild))
    out = tool.run(ctx, aktion="ansehen")
    assert isinstance(out, ToolOutput) and out.bilder == [bild] and "nicht vertrauenswuerdig" in out.text
    tool, ctx = _werkzeug(_Dienst(bild=bild), afk_session=SimpleNamespace(ended=""))
    assert isinstance(tool.run(ctx, aktion="ansehen"), str)
    tool, ctx = _werkzeug(_Dienst(bild=None, grund="Passwortfeld aktiv"))
    assert tool.run(ctx, aktion="ansehen") == "Passwortfeld aktiv"
    tool, ctx = _werkzeug(_Dienst())
    assert "excel" in tool.run(ctx, aktion="verlauf") and "2 von 20" in tool.run(ctx, aktion="status")
    d = _Dienst()
    tool, ctx = _werkzeug(d)
    tool.run(ctx, aktion="aus")
    assert d.aus_gerufen


def test_in_einer_wortmeldung_darf_nova_nur_lesen(app):
    from tests._fakes import tool_use_block

    script = [(anthro_msg([tool_use_block("merken", "t1", {"inhalt": "Kontostand 1234"})], stop_reason="tool_use"), []),
              _streamed("Ich habe nur geschaut.")]
    server = app(script)
    ctl = server.controller
    ctl._sehen_wecken(_paket())
    _events_until(server, "done")
    assert ctl.memory.count_facts() == 0
    verlauf = json.loads(json.dumps(ctl.brain.provider.messages, default=lambda o: getattr(o, "__dict__", repr(o))))
    ergebnis = [b for m in verlauf if m["role"] == "user" and isinstance(m["content"], list)
                for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert ergebnis and ergebnis[0]["is_error"] and "nur lesen" in json.dumps(ergebnis[0], ensure_ascii=False)
    assert "nur_diese_werkzeuge" not in ctl.tool_ctx.extra and ctl.permissions.away is False
