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

    for exe, expected in (("KI.exe", "u-terminal"), ("KI-App.exe", "u-app")):
        up = Updater(UpdateSettings(), tmp_path, fetch=fetch, current_version="0.4.0", frozen=True,
                     exe_path=tmp_path / exe)
        assert up.check().download_url == expected


def test_app_exe_starts_in_app_mode(monkeypatch):
    import run_ki

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:/KI/KI-App.exe")
    assert run_ki._is_app_exe()
    monkeypatch.setattr(sys, "executable", "C:/KI/KI.exe")
    assert not run_ki._is_app_exe()


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


def test_jarvis_loop_listens_answers_and_waits_for_speaking(app, monkeypatch):
    from assistant import voice

    server = app([_streamed("Morgen wird es sonnig.")])
    ctl = server.controller
    said = iter([b"x" * 32000, None])
    monkeypatch.setattr(ctl.voice_capture, "problem", lambda: None)
    monkeypatch.setattr(ctl.voice_capture, "transcribe", lambda pcm: "Wie wird das Wetter?")

    def fake_listen(on_level=None, stop_event=None, **kw):
        if on_level:
            on_level(0.6)
        value = next(said)
        if value is None:
            stop_event.wait(5)
        return value

    monkeypatch.setattr(voice, "listen_utterance", fake_listen)
    assert _req(server, "/api/jarvis", {"action": "start"})[1] == {"ok": True}
    events = _events_until(server, "speaking" if False else "done")
    kinds = [(e["type"], e.get("state")) for e in events]
    assert ("jarvis", "listening") in kinds and ("jarvis", "thinking") in kinds
    assert any(e["type"] == "level" for e in events)
    events = _events_until(server, "jarvis")
    assert events[-1]["state"] == "speaking" and "sonnig" in events[-1]["text"]
    sent = ctl.brain.provider.messages[0]["content"]
    assert sent.startswith("Wie wird das Wetter?") and "Sprachmodus" in sent  # Hinweis nur fuer die KI
    status, hist = _req(server, "/api/history")
    assert hist["messages"][0]["text"] == "Wie wird das Wetter?"           # Anzeige ohne Hinweis
    _req(server, "/api/jarvis", {"action": "spoken"})
    _req(server, "/api/jarvis", {"action": "stop"})
    events = _events_until(server, "jarvis")
    while events[-1].get("state") != "off":
        events = _events_until(server, "jarvis")
    assert _req(server, "/api/state")[1]["jarvis"] is False


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
