"""Die KI als App: Server-Sicherheit und der komplette Ablauf ueber HTTP + Ereignisse."""
import json
import queue
import sys
import time
import urllib.error
import urllib.request

import pytest

from assistant.app.controller import AppController
from assistant.app.server import AppServer
from assistant.config import load_config

from types import SimpleNamespace

from tests._fakes import AnthroClient, anthro_msg, text_block, tool_use_block


def _streamed(text):
    """Antwort, die - wie das echte SDK - als Text-Ereignisse gestreamt wird."""
    return (anthro_msg([text_block(text)]), [SimpleNamespace(type="text", text=t) for t in (text[:5], text[5:])])


@pytest.fixture
def app(tmp_path):
    servers = []

    def make(scripted, **perm):
        cfg = load_config(tmp_path)
        cfg.update.modus = "aus"
        cfg.anthropic_api_key = cfg.anthropic_api_key or "sk-ant-test-schluessel"
        for key, value in perm.items():
            setattr(cfg.permissions, key, value)
        server = AppServer(lambda broadcast: AppController(cfg, broadcast))
        server.start()
        server.controller.brain.provider.client = AnthroClient(scripted)
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
                                 method="POST" if body is not None else "GET")
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


def test_server_only_with_token_and_own_host(app):
    server = app([])
    assert _req(server, "/api/state", token=False)[0] == 403
    assert _req(server, "/api/state", host="evil.example:80")[0] == 403      # DNS-Rebinding
    assert _req(server, "/api/send", {"text": "x"}, token=False)[0] == 403
    assert _req(server, "/static/../server.py")[0] in (403, 404)               # kein Ausbruch
    status, state = _req(server, "/api/state")
    assert status == 200 and state["name"] and state["busy"] is False and state["commands"]


def test_message_streams_answer(app):
    server = app([_streamed("Hallo **Welt**")])
    assert _req(server, "/api/send", {"text": "Hi"}) == (200, {"ok": True})
    events = _events_until(server, "done")
    kinds = [e["type"] for e in events]
    assert kinds.index("user") < kinds.index("start") < kinds.index("done")
    assert "".join(e["text"] for e in events if e["type"] == "chunk") == "Hallo **Welt**"
    status, hist = _req(server, "/api/history")
    assert [m["role"] for m in hist["messages"]] == ["user", "assistant"]


def test_permission_dialog_and_always_allow(app, tmp_path):
    target = tmp_path / "workspace" / "notiz.txt"
    script = [
        (anthro_msg([tool_use_block("datei_schreiben", "t1", {"pfad": "notiz.txt", "inhalt": "hallo"})],
                    stop_reason="tool_use"), []),
        (anthro_msg([text_block("Gespeichert.")]), []),
    ]
    server = app(script, safe_mode=False, auto_confirm=False)
    _req(server, "/api/send", {"text": "Schreib eine Notiz"})
    first = _events_until(server, "ask")
    ask = first[-1]
    assert ask["kind"] == "permission" and [o["value"] for o in ask["options"]] == ["einmal", "immer", "nein"]
    assert _req(server, "/api/answer", {"id": ask["id"], "value": "immer"})[1] == {"ok": True}
    events = first + _events_until(server, "done")
    assert any(e["type"] == "tool" and e["name"] == "datei_schreiben" for e in events)
    assert target.read_text(encoding="utf-8") == "hallo"
    assert load_config(tmp_path).permissions.auto_confirm is True  # dauerhaft gespeichert


def test_stop_button_halts_a_running_program(app):
    cmd = f'"{sys.executable}" -c "import time; time.sleep(60)"'
    script = [(anthro_msg([tool_use_block("shell_befehl", "t1", {"befehl": cmd})], stop_reason="tool_use"), []),
              (anthro_msg([text_block("nie")]), [])]
    server = app(script, safe_mode=False, auto_confirm=True)
    _req(server, "/api/send", {"text": "Lauf"})
    _events_until(server, "tool")
    time.sleep(0.5)
    started = time.monotonic()
    assert _req(server, "/api/stop", {})[1] == {"ok": True}
    _events_until(server, "stopped", timeout=10)
    assert time.monotonic() - started < 5
    prov = server.controller.brain.provider
    assert prov.messages[-1]["role"] == "assistant"            # Verlauf bleibt gueltig
    assert _req(server, "/api/state")[1]["busy"] is False


def test_busy_and_commands_as_notices(app):
    server = app([(anthro_msg([text_block("ok")]), [])])
    _req(server, "/api/send", {"text": "/kosten"})
    events = _events_until(server, "notice")
    assert "Kosten dieser Sitzung" in events[-1]["text"]


def test_voice_without_packages_offers_setup(app, monkeypatch):
    server = app([])
    monkeypatch.setattr(server.controller.voice_capture, "problem", lambda: "Tippe /sprache einrichten")
    status, body = _req(server, "/api/voice", {"action": "start"})
    assert body["ok"] is False and body["setup"] is True


def test_toggle_allow_everything(app, tmp_path):
    server = app([])
    status, body = _req(server, "/api/toggle", {"name": "erlauben", "value": True})
    assert body["state"]["auto_confirm"] is True
    assert load_config(tmp_path).permissions.auto_confirm is True


def test_second_message_while_busy_is_refused(app):
    cmd = f'"{sys.executable}" -c "import time; time.sleep(5)"'
    script = [(anthro_msg([tool_use_block("shell_befehl", "t1", {"befehl": cmd})], stop_reason="tool_use"), []),
              (anthro_msg([text_block("fertig")]), [])]
    server = app(script, safe_mode=False, auto_confirm=True)
    _req(server, "/api/send", {"text": "eins"})
    _events_until(server, "tool")
    status, body = _req(server, "/api/send", {"text": "zwei"})
    assert body["ok"] is False and "Stopp" in body["error"]
    _req(server, "/api/stop", {})


def test_native_program_window_is_used(app, tmp_path, monkeypatch):
    """Normalfall: echtes Programmfenster (pywebview) - kein Browser."""
    import types

    from assistant.app import launcher

    server = app([])
    calls = {}
    fake = types.ModuleType("webview")

    class Window:
        def destroy(self):
            calls["destroyed"] = True

    def create_window(title, url, **kw):
        calls["title"], calls["url"], calls["kw"] = title, url, kw
        return Window()

    fake.create_window = create_window
    fake.start = lambda **kw: calls.setdefault("start", kw)
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(launcher, "open_window", lambda *a, **k: calls.setdefault("browser", True))
    holder = {}
    assert launcher.run_native_window(server, server.controller, "Aria - Selbst-lernende KI",
                                      tmp_path / "fenster", holder)
    assert calls["url"] == server.url and calls["title"].startswith("Aria")
    assert "browser" not in calls  # kein Browser geoeffnet
    holder["close"]()
    assert calls["destroyed"]


def test_window_failure_falls_back_only_after_asking(app, tmp_path, monkeypatch):
    import types

    from assistant.app import launcher

    server = app([])
    fake = types.ModuleType("webview")
    fake.create_window = lambda *a, **k: object()

    def broken_start(**kw):
        raise RuntimeError("WebView2 fehlt")

    fake.start = broken_start
    monkeypatch.setitem(sys.modules, "webview", fake)
    assert launcher.run_native_window(server, server.controller, "x", tmp_path / "f", {}) is False


def test_each_exe_updates_from_its_own_release_file(tmp_path):
    from assistant.config import UpdateSettings
    from assistant.updater import Updater

    release = {"tag_name": "v9.0.0", "assets": [
        {"name": "KI.exe", "browser_download_url": "u-terminal"},
        {"name": "KI-App.exe", "browser_download_url": "u-app"}]}

    def fetch(url, timeout=15):
        return json.dumps(release).encode() if "releases" in url else b""

    for exe, expected in (("KI.exe", "u-terminal"), ("KI-App.exe", "u-app"),
                          ("KI-App (1).exe", "u-app"), ("KI (2).exe", "u-terminal")):  # Windows benennt um
        up = Updater(UpdateSettings(), tmp_path, fetch=fetch, current_version="0.4.0", frozen=True,
                     exe_path=tmp_path / exe)
        assert up.check().download_url == expected


def test_app_exe_starts_in_app_mode(monkeypatch):
    import run_ki

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:/KI/KI-App.exe")
    assert run_ki._is_app_exe()
    monkeypatch.setattr(sys, "executable", "C:/KI/KI-App (1).exe")        # doppelt heruntergeladen
    assert run_ki._is_app_exe()
    monkeypatch.setattr(sys, "executable", "C:/KI/KI.exe")
    monkeypatch.setattr(run_ki, "_WINDOWED", False)
    assert not run_ki._is_app_exe()
    monkeypatch.setattr(run_ki, "_WINDOWED", True)                          # ohne Konsole = immer App
    assert run_ki._is_app_exe()


def test_profile_api_and_memory_management(app, tmp_path):
    server = app([])
    status, prof = _req(server, "/api/profile")
    assert prof["name"] == "Nova" and len(prof["characters"]) >= 5 and prof["about_fields"]
    status, body = _req(server, "/api/profile", {"character": "mentor", "style": {"anrede": "Sie"},
                                                  "about": {"name": "Nate", "projekte": "SCP-Spiel"}})
    assert body["ok"] and body["profile"]["character"] == "mentor"
    cfg = load_config(tmp_path)
    assert cfg.style.anrede == "Sie" and cfg.about["projekte"] == "SCP-Spiel"
    assert "Mentor" in (tmp_path / "config" / "persona.md").read_text(encoding="utf-8")
    status, mem = _req(server, "/api/memory", {"action": "add", "content": "Mag dunkles Design"})
    assert mem["ok"] and mem["facts"][0]["content"] == "Mag dunkles Design"
    fact_id = mem["facts"][0]["id"]
    status, mem = _req(server, "/api/memory", {"action": "delete", "id": fact_id})
    assert mem["ok"] and mem["count"] == 0


def test_new_conversation_clears_the_window(app):
    server = app([_streamed("Hallo du")])
    _req(server, "/api/send", {"text": "Hi"})
    _events_until(server, "done")
    _req(server, "/api/send", {"text": "/neu"})
    _events_until(server, "reset")
    status, hist = _req(server, "/api/history")
    assert all(m["role"] != "assistant" for m in hist["messages"])


def _fake_ear(monkeypatch, ctl):
    """Jarvis-Modus ohne Mikrofon: der Test 'spricht' ueber ears[0].post(...)."""
    from assistant import live

    ears = []

    class FakeEar:
        live = False

        def __init__(self, post, **kw):
            self.post = post
            self.nova = []
            ears.append(self)

        def start(self):
            pass

        def stop(self):
            pass

        def set_nova_speaking(self, value):
            self.nova.append(value)

        def enable_live(self, factory):
            pass

    monkeypatch.setattr(ctl.voice_capture, "problem", lambda: None)
    monkeypatch.setattr(live, "Ear", FakeEar)
    monkeypatch.setattr(live, "setup_live", lambda *a, **k: (False, "im Test nicht"))
    return ears


def test_jarvis_live_speaks_while_answer_streams_and_waits_for_window(app, monkeypatch):
    from assistant import live

    server = app([_streamed("Morgen wird es sonnig. Am Nachmittag bis 24 Grad - perfekt fuer draussen.")])
    ctl = server.controller
    ears = _fake_ear(monkeypatch, ctl)
    status, body = _req(server, "/api/jarvis", {"action": "start"})
    assert body["ok"] is True and body["live"] is False
    assert ctl.brain.provider.effort_override == "low"                  # schneller antworten
    ears[0].post("level", 0.6)
    ears[0].post("partial", "Wie wird das")
    ears[0].post("utterance", live.Utterance("Wie wird das Wetter morgen", b"", 1.0))
    events = _events_until(server, "say_end")
    kinds = [(e["type"], e.get("state")) for e in events]
    assert ("jarvis", "listening") in kinds and ("jarvis", "thinking") in kinds and ("level", None) in kinds
    assert {"type": "heard", "text": "Wie wird das", "final": False} in events
    says = [e for e in events if e["type"] == "say"]
    assert says[0]["text"] == "Morgen wird es sonnig." and says[0]["seq"] == 1
    assert "24 Grad" in says[-1]["text"]
    sent = ctl.brain.provider.messages[0]["content"]
    assert sent.startswith("Wie wird das Wetter morgen") and "Sprachmodus" in sent  # Hinweis nur fuer die KI
    assert ctl.brain.provider.client.messages.last_kwargs["output_config"] == {"effort": "low"}
    status, hist = _req(server, "/api/history")
    assert [m["text"] for m in hist["messages"] if m["role"] == "user"] == ["Wie wird das Wetter morgen"]
    _req(server, "/api/jarvis", {"action": "spoken", "turn": says[0]["turn"]})
    events = _events_until(server, "jarvis")
    assert events[-1]["state"] == "listening" and ears[0].nova[-1] is False
    _req(server, "/api/jarvis", {"action": "stop"})
    events = _events_until(server, "jarvis")
    while events[-1].get("state") != "off":
        events = _events_until(server, "jarvis")
    time.sleep(0.1)
    assert _req(server, "/api/state")[1]["jarvis"] is False
    assert ctl.brain.provider.effort_override is None


def test_jarvis_afterthought_replaces_the_question(app, monkeypatch):
    import threading

    from assistant import live

    gate = threading.Event()

    def slow():
        gate.wait(5)  # Nova "denkt nach"
        yield SimpleNamespace(type="text", text="Sonnig.")

    server = app([(anthro_msg([text_block("Sonnig.")]), slow()),
                  _streamed("In Berlin wird es morgen sonnig.")])
    ctl = server.controller
    ears = _fake_ear(monkeypatch, ctl)
    _req(server, "/api/jarvis", {"action": "start"})
    ears[0].post("utterance", live.Utterance("Wie wird das Wetter morgen", b"", 1.0))
    _events_until(server, "start")
    ears[0].post("utterance", live.Utterance("in Berlin", b"", 0.5))
    end = time.monotonic() + 5
    while not ctl.brain.provider.cancel_event.is_set() and time.monotonic() < end:
        time.sleep(0.02)
    gate.set()
    events = _events_until(server, "say_end")
    assert any(e["type"] == "retract" for e in events)
    assert [e["text"] for e in events if e["type"] == "user"][-1] == "Wie wird das Wetter morgen in Berlin"
    msgs = ctl.brain.provider.messages
    assert msgs[0]["content"].startswith("Wie wird das Wetter morgen in Berlin") and len(msgs) == 2
    status, hist = _req(server, "/api/history")
    assert [m["text"] for m in hist["messages"] if m["role"] == "user"] == ["Wie wird das Wetter morgen in Berlin"]
    _req(server, "/api/jarvis", {"action": "stop"})


def test_custom_css_and_appearance_api(app, tmp_path):
    from assistant import aussehen

    server = app([])
    aussehen.save(tmp_path, {"akzentfarbe": "#16a34a"})
    aussehen.set_css(tmp_path, ".bubble{border-radius:2px}")
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}/custom.css")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.read().decode() == ".bubble{border-radius:2px}" and "text/css" in resp.headers["Content-Type"]
    assert _req(server, "/api/appearance")[1]["settings"] == {"akzentfarbe": "#16a34a"}
    state = _req(server, "/api/state")[1]
    assert state["stuetzraeder"] in ("an", "aus", "teilweise") and state["tutorial_done"] is False


def test_typed_jarvis_and_tutorial_commands_open_the_views(app, monkeypatch):
    server = app([])
    ctl = server.controller
    _fake_ear(monkeypatch, ctl)
    _req(server, "/api/send", {"text": "/jarvis"})
    events = _events_until(server, "open")
    assert events[-1]["what"] == "jarvis" and ctl._jarvis_active()
    _req(server, "/api/jarvis", {"action": "stop"})
    time.sleep(0.3)
    _req(server, "/api/send", {"text": "/tutorial"})
    assert _events_until(server, "open")[-1]["what"] == "tutorial"


def test_bad_requests_get_an_answer_and_meaning_with_backslash_is_saved(app, tmp_path):
    server = app([])
    assert _req(server, "/api/memory", {"action": "delete", "id": "abc"})[0] == 400   # Antwort statt Abbruch
    assert _req(server, "/api/profile", {"style": ["kaputt"]})[0] == 400
    status, body = _req(server, "/api/profile", {"meaning": 'Mein "Assistent" C:\\Users'})
    assert body["ok"] is True and body["profile"]["meaning"] == 'Mein "Assistent" C:\\Users'
    from assistant.config import load_config

    assert load_config(tmp_path).ki.bedeutung == 'Mein "Assistent" C:\\Users'


def test_jarvis_starts_only_once_and_never_cancels_a_typed_answer(app, monkeypatch):
    import threading

    server = app([_streamed("Hallo!")])
    ctl = server.controller
    ears = _fake_ear(monkeypatch, ctl)
    results = []
    threads = [threading.Thread(target=lambda: results.append(ctl.jarvis("start"))) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ears) == 1 and all(r["ok"] for r in results)        # Doppelklick: nur EIN Jarvis-Modus
    loop = ctl._live
    gate = threading.Event()
    ctl._live_turn = None
    assert ctl.send("getippt")[0]                                   # getippte Nachricht, nicht von Jarvis
    loop.host.cancel_turn(False)
    assert not ctl.brain.provider.cancel_event.is_set()
    gate.set()
    _events_until(server, "done")
    ctl.jarvis("stop")
    old = loop
    ctl.jarvis("start")
    time.sleep(0.3)
    old.host.event({"type": "jarvis", "state": "off"})              # verspaetetes "off" der alten Sitzung
    assert ctl._jarvis_active()
    ctl.jarvis("stop")


def test_terminal_jarvis_answers_questions_by_voice(tmp_path, monkeypatch):
    import threading

    from assistant.permissions import Risk
    from assistant.ui.cli import _TerminalLiveHost
    from tests.test_erlauben import _cli

    cli = _cli(tmp_path, [], monkeypatch)
    host = _TerminalLiveHost(cli)

    class Loop:
        asked = []

        def on_ask(self, text):
            self.asked.append(text)

    host.loop = Loop()
    host.install()
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("v", cli._permission_answer("Datei schreiben?", Risk.MODERATE)),
                         daemon=True)
    t.start()
    for _ in range(100):
        if host.pending_ask() and Loop.asked:
            break
        time.sleep(0.02)
    ask = host.pending_ask()
    assert ask["options"] == ["einmal", "immer", "nein"] and Loop.asked == ["Datei schreiben?"]
    host.answer_ask(ask["id"], "immer")
    t.join(2)
    assert out["v"] == "immer"
    host.uninstall()
    assert "_permission_answer" not in cli.__dict__


def test_tutorial_keeps_ids_and_state_tells_the_jarvis_state(app, monkeypatch):
    server = app([])
    steps = _req(server, "/api/tutorial")[1]["steps"]
    assert any(s["ziel"] == "stuetzraeder" for s in steps)            # Kennung unveraendert
    assert any("ä" in s["text"] or "ü" in s["text"] for s in steps)  # Text mit Umlauten
    ctl = server.controller
    _fake_ear(monkeypatch, ctl)
    assert _req(server, "/api/state")[1]["jarvis_state"] == "off"
    ctl.jarvis("start")
    time.sleep(0.3)
    assert _req(server, "/api/state")[1]["jarvis_state"] == "listening"
    ctl.jarvis("stop")


def test_window_profile_is_local_and_blank_window_falls_back(tmp_path, monkeypatch):
    import threading as _t

    from assistant.app import launcher

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    a = launcher.webview_storage(tmp_path / "Desktop" / "NovaAI")
    assert str(a).startswith(str(tmp_path / "local")) and "SelbstLernendeKI" in str(a)
    assert a == launcher.webview_storage(tmp_path / "Desktop" / "NovaAI")       # immer derselbe Ordner
    assert a != launcher.webview_storage(tmp_path / "anderer")                  # pro Installation eigener

    class Hub:
        ever_connected = False

    class Win:
        destroyed = False

        def destroy(self):
            self.destroyed = True

    shown, holder, win = _t.Event(), {}, Win()
    shown.set()
    monkeypatch.setattr(launcher.time, "monotonic", iter([0, 0, 100, 100, 100]).__next__)
    monkeypatch.setattr(launcher.time, "sleep", lambda s: None)
    launcher._watch_blank(win, shown, SimpleNamespace(hub=Hub()), holder)
    assert holder.get("leer") and win.destroyed                                 # leeres Fenster -> Ersatz


def test_exe_kind_from_program_header_and_crash_memory(tmp_path):
    from assistant.app import launcher
    from assistant.updater import own_exe_flavor

    def fake_exe(path, subsystem):
        head = bytearray(512)
        head[0:2] = b"MZ"
        head[0x3C:0x40] = (0x80).to_bytes(4, "little")
        head[0x80:0x84] = b"PE\0\0"
        head[0x80 + 0x5C:0x80 + 0x5E] = subsystem.to_bytes(2, "little")
        path.write_bytes(bytes(head))
        return path

    # bei ausgeblendeten Endungen heisst sie schnell "KI-App.exe.exe" - der Programmkopf zaehlt
    assert own_exe_flavor(fake_exe(tmp_path / "KI-App.exe.exe", 2)) == "app"
    assert own_exe_flavor(fake_exe(tmp_path / "KI.exe", 3)) == "terminal"
    assert own_exe_flavor(tmp_path / "fehlt-App.exe") == "app"            # ohne Datei: nach Name
    info = tmp_path / "app.json"
    info.write_text(json.dumps({"pid": 999999, "fenster": "programm"}), encoding="utf-8")
    assert launcher._crashed_last_time(info)                              # Prozess weg, app.json noch da
    info.write_text(json.dumps({"pid": 999999, "fenster": "browser"}), encoding="utf-8")
    assert not launcher._crashed_last_time(info)
