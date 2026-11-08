"""Bilder in der App (Teil E): Senden mit Bildern, Anzeige per /api/bild, Warteschlange,
erzeugte Bilder als Ereignis, Grenzen der Anfragegroesse - alles ueber echtes HTTP."""
import base64
import http.client
import io
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

from tests._fakes import anthro_msg, tool_use_block
from tests.test_app import _events_until, _req, _slow_script, _streamed, app

_FIXTURES = (app,)  # die App-Fixture aus test_app.py (echter Server, gefaelschtes Claude)

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

_URL_H = re.compile(r"^/api/bild/h/[0-9a-f]{16}\.(png|jpg)$")


def _png(breite=40, hoehe=30, farbe=(200, 30, 30)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (breite, hoehe), farbe).save(puffer, "PNG")
    return puffer.getvalue()


def _jpeg(breite=40, hoehe=30) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (breite, hoehe), (10, 120, 200)).save(puffer, "JPEG")
    return puffer.getvalue()


def _data_url(data: bytes, mime="image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _get_raw(server, path, token=True):
    """GET mit Bytes-Antwort -> (Status, Header, Bytes)."""
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    if token:
        path += ("&" if "?" in path else "?") + f"t={server.token}"
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, {k.lower(): v for k, v in resp.getheaders()}, body


def _user_blocks(server):
    """Inhalt des Nutzer-Turns der letzten Anfrage an (den gefaelschten) Claude."""
    sent = json.loads(server.controller.brain.provider.client.messages.requests[-1])
    users = [m for m in sent if m["role"] == "user" and not (
        isinstance(m["content"], list) and m["content"] and m["content"][0].get("type") == "tool_result")]
    return users[-1]["content"]


# -- Senden mit Bildern --------------------------------------------------------------
def test_send_with_images_reaches_the_model_and_the_window_gets_only_urls(app):
    server = app([_streamed("Eine rote Flaeche.")])
    gross = _png(3000, 1500)  # wird einmal beim Ankommen verkleinert
    status, body = _req(server, "/api/send", {"text": "Was ist das?", "client_id": "c-1",
                                              "images": [{"name": "C:\\Fotos\\urlaub.png", "data": _data_url(gross)},
                                                         {"name": "zwei.jpg", "data": _data_url(_jpeg(), "image/jpeg")}]})
    assert (status, body) == (200, {"ok": True})
    events = _events_until(server, "done")
    user = next(e for e in events if e["type"] == "user")
    assert user["text"] == "Was ist das?" and user["client_id"] == "c-1"
    assert [i["name"] for i in user["images"]] == ["urlaub.png", "zwei.jpg"]
    assert all(_URL_H.match(i["url"]) for i in user["images"])

    # Claude bekommt die Bilder (vor dem Text), schon verkleinert
    blocks = _user_blocks(server)
    kinds = [b["type"] for b in blocks]
    assert kinds.count("image") == 2 and kinds[-1] == "text" and blocks[-1]["text"] == "Was ist das?"
    erstes = base64.b64decode(next(b for b in blocks if b["type"] == "image")["source"]["data"])
    assert max(Image.open(io.BytesIO(erstes)).size) <= 1568

    # Verlauf: nur URLs, nie Base64 (auch nach dem Neuladen wieder da)
    status, hist = _req(server, "/api/history")
    raw = json.dumps(hist)
    assert "base64" not in raw and len(raw) < 5000
    entry = hist["messages"][0]
    assert entry["role"] == "user" and entry["images"] == user["images"] and entry["client_id"] == "c-1"

    # Das Fenster holt die Bilder ueber die URL (mit Schluessel) - genau die gespeicherte Datei
    url = user["images"][0]["url"]
    status, headers, data = _get_raw(server, url)
    assert status == 200 and headers["content-type"] == "image/png"
    assert headers["x-content-type-options"] == "nosniff"
    saved = server.controller.upload_dir() / url.rsplit("/", 1)[1]
    assert data == saved.read_bytes() and data == erstes
    assert _get_raw(server, url, token=False)[0] == 403


def test_message_with_only_an_image(app):
    server = app([_streamed("Ich sehe ein Bild.")])
    assert _req(server, "/api/send", {"text": "", "images": [{"name": "x.png", "data": _data_url(_png())}]})[1] == {"ok": True}
    events = _events_until(server, "done")
    user = next(e for e in events if e["type"] == "user")
    assert user["text"] == "" and len(user["images"]) == 1 and user["client_id"] is None
    blocks = _user_blocks(server)
    assert [b["type"] for b in blocks] == ["image", "text"] and blocks[-1]["text"] == "Schau dir das Bild an."
    assert [m["role"] for m in _req(server, "/api/history")[1]["messages"]] == ["user", "assistant"]


def test_too_many_or_broken_images_are_refused_with_a_german_message(app, tmp_path):
    server = app([_streamed("nie")])
    ctl = server.controller
    bild = {"name": "a.png", "data": _data_url(_png())}
    body = _req(server, "/api/send", {"text": "x", "images": [bild] * 11})[1]
    assert body["ok"] is False and "chstens 10 Bilder" in body["error"]
    ctl.config.bilder.max_bilder_pro_nachricht = 2
    assert "chstens 2 Bilder" in _req(server, "/api/send", {"text": "x", "images": [bild] * 3})[1]["error"]
    cases = [
        ([{"name": "a.txt", "data": "data:text/plain;base64,aGFsbG8="}], "nicht richtig an"),
        ([{"name": "a.png", "data": "data:image/png;base64," + base64.b64encode(b"<svg></svg>").decode()}],
         "kein Bild"),
        ([{"name": "a.png", "data": 12345}], "nicht richtig an"),
        (["data:image/png;base64,AAAA"], "nicht richtig an"),
        ({"name": "a.png"}, "nicht richtig an"),
    ]
    for images, expected in cases:
        body = _req(server, "/api/send", {"text": "x", "images": images})[1]
        assert body["ok"] is False and expected in body["error"], (images, body)
    assert _req(server, "/api/send", {"text": "  ", "images": []})[1] == {"ok": False, "error": "Leere Nachricht"}
    body = _req(server, "/api/send", {"text": "/kosten", "images": [bild]})[1]
    assert body["ok"] is False and "ohne Bilder" in body["error"]
    # Ein Schluessel mit Bild: nie an die KI, nie gespeichert
    body = _req(server, "/api/send", {"text": "sk-" + "a" * 30, "images": [bild]})[1]
    assert body["ok"] is False and "ohne Bilder" in body["error"]
    time.sleep(0.2)
    assert not ctl.upload_dir().exists() or not any(ctl.upload_dir().iterdir())  # nichts abgelegt
    assert ctl.brain.provider.client.messages.calls == 0 and ctl.history == []


# -- Grenze der Anfragegroesse ------------------------------------------------------------
def _post_raw(server, path, data: bytes, token=True):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=30)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-KI-Token"] = server.token
    conn.request("POST", path, body=data, headers=headers)
    resp = conn.getresponse()
    result = resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read()
    return conn, result


def test_body_limit_is_40_mb_only_for_send_and_feedback_and_413_closes_cleanly(app):
    server = app([_streamed("ok")])
    mittel = json.dumps({"name": "x" * 1_500_000}).encode()       # 1,5 MB
    conn, (status, headers, body) = _post_raw(server, "/api/toggle", mittel)
    assert status == 413 and headers.get("connection", "").lower() == "close"
    assert "zu gro" in json.loads(body)["error"]
    conn.close()
    # danach geht alles normal weiter (der ungelesene Rest wurde nicht als neue Anfrage gelesen)
    assert _req(server, "/api/state")[0] == 200
    # /api/send und /api/feedback nehmen grosse Anfragen an (Bilder)
    conn, (status, _h, body) = _post_raw(server, "/api/send", json.dumps({"text": "", "pad": "x" * 1_500_000}).encode())
    assert status == 200 and json.loads(body)["error"] == "Leere Nachricht"
    conn.close()
    riesig = b'{"text": "' + b"x" * (41 * 1024 * 1024) + b'"}'
    conn, (status, headers, body) = _post_raw(server, "/api/send", riesig)
    assert status == 413 and headers.get("connection", "").lower() == "close"
    conn.close()
    # Gleiche Verbindung (Keep-Alive): eine kleine Anfrage nach der grossen bekommt eine echte Antwort
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=30)
    conn.request("POST", "/api/toggle", body=mittel, headers={"X-KI-Token": server.token})
    first = conn.getresponse()
    first.read()
    assert first.status == 413 and first.will_close
    conn.close()
    # Ohne Schluessel: 403, Verbindung wird geschlossen (Inhalt bleibt ungelesen)
    conn, (status, headers, _b) = _post_raw(server, "/api/send", b'{"text": "hi"}', token=False)
    assert status == 403
    conn.close()
    assert _req(server, "/api/state")[1]["busy"] is False


def test_negative_content_length_is_a_bad_request(app):
    server = app([])
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.putrequest("POST", "/api/toggle")
    conn.putheader("X-KI-Token", server.token)
    conn.putheader("Content-Length", "-5")
    conn.endheaders()
    resp = conn.getresponse()
    assert resp.status == 400
    conn.close()


# -- GET /api/bild ------------------------------------------------------------------------
def test_image_route_serves_only_real_images_from_the_two_folders(app, tmp_path):
    server = app([])
    ctl = server.controller
    hoch = ctl.upload_dir()
    hoch.mkdir(parents=True)
    erstellt = ctl.bild_ordner("e")
    erstellt.mkdir(parents=True)
    (hoch / "abc123.png").write_bytes(_png())
    (hoch / "falsch.png").write_bytes(_jpeg())                       # Name sagt png, Inhalt ist JPEG
    (hoch / "boese.png").write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'><script>x</script></svg>")
    (hoch / "seite.gif").write_bytes(b"<html><script>alert(1)</script></html>")
    (erstellt / "20261108-120000_katze.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    (tmp_path / "geheim.png").write_bytes(_png())
    (tmp_path / "workspace" / "nicht-im-ordner.png").write_bytes(_png())

    status, headers, data = _get_raw(server, "/api/bild/h/abc123.png")
    assert status == 200 and headers["content-type"] == "image/png" and headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in headers["content-security-policy"] and "no-store" in headers["cache-control"]
    status, headers, _d = _get_raw(server, "/api/bild/h/falsch.png")
    assert status == 200 and headers["content-type"] == "image/jpeg"   # Typ an den Bytes erkannt
    status, headers, _d = _get_raw(server, "/api/bild/e/20261108-120000_katze.webp")
    assert status == 200 and headers["content-type"] == "image/webp"
    assert _get_raw(server, "/api/bild/h/boese.png")[0] == 415         # nie SVG/HTML ausliefern
    assert _get_raw(server, "/api/bild/h/seite.gif")[0] == 415
    assert _get_raw(server, "/api/bild/h/abc123.png", token=False)[0] == 403
    for bad in ["/api/bild/h/../geheim.png", "/api/bild/h/%2e%2e%2fgeheim.png", "/api/bild/h/..%2Fgeheim.png",
                "/api/bild/e/../nicht-im-ordner.png", "/api/bild/h/sub/abc123.png", "/api/bild/h/abc123.svg",
                "/api/bild/h/abc123.txt", "/api/bild/h/abc%20123.png", "/api/bild/x/abc123.png",
                "/api/bild/h/" + "a" * 101 + ".png", "/api/bild/h/fehlt.png", "/api/bild/e/abc123.png",
                "/api/bild/h/", "/api/bild/h", "/api/bild/h/.png"]:
        assert _get_raw(server, bad)[0] in (403, 404), bad
    if hasattr(os, "symlink"):
        try:
            (hoch / "link.png").symlink_to(tmp_path / "geheim.png")
        except OSError:
            pass
        else:
            assert _get_raw(server, "/api/bild/h/link.png")[0] == 404  # Verweis nach draussen


# -- Warteschlange ---------------------------------------------------------------------
def test_queued_images_show_in_the_state_and_come_back_after_stop(app):
    server = app(_slow_script(5), safe_mode=False, auto_confirm=True)
    _req(server, "/api/send", {"text": "eins"})
    _events_until(server, "tool")
    bild = {"name": "foto.png", "data": _data_url(_png())}
    body = _req(server, "/api/send", {"text": "zwei", "images": [bild], "client_id": "k2"})[1]
    assert body["ok"] and body["queued"]
    _req(server, "/api/send", {"text": "", "images": [bild, bild]})
    _req(server, "/api/send", {"text": "drei"})
    queue = _req(server, "/api/state")[1]["queue"]
    assert [q["text"] for q in queue] == ["zwei", "", "drei"]
    assert [len(q["images"]) for q in queue] == [1, 2, 0]
    assert _URL_H.match(queue[0]["images"][0]["url"]) and queue[0]["images"][0]["name"] == "foto.png"
    _req(server, "/api/stop", {})
    returned = _events_until(server, "queue_returned")[-1]
    assert returned["text"] == "zwei\ndrei"
    assert [(i["text"], len(i["images"])) for i in returned["items"]] == [("zwei", 1), ("", 2), ("drei", 0)]
    assert returned["items"][0]["images"] == queue[0]["images"]
    # die URLs funktionieren weiter (das Fenster holt die Bilder zurueck in die Eingabe)
    assert _get_raw(server, returned["items"][1]["images"][0]["url"])[0] == 200
    _events_until(server, "stopped")


def test_a_queued_message_with_an_image_reaches_the_model_later(app):
    script = _slow_script(1) + [_streamed("Ein Bild!")]
    server = app(script, safe_mode=False, auto_confirm=True)
    _req(server, "/api/send", {"text": "eins"})
    _events_until(server, "tool")
    _req(server, "/api/send", {"text": "und das?", "images": [{"name": "b.png", "data": _data_url(_png())}],
                               "client_id": "spaeter-1"})
    events = _events_until(server, "done")
    events += _events_until(server, "done")
    user = [e for e in events if e["type"] == "user"][-1]
    assert user["text"] == "und das?" and user["client_id"] == "spaeter-1" and len(user["images"]) == 1
    blocks = _user_blocks(server)
    assert [b["type"] for b in blocks] == ["image", "text"] and blocks[-1]["text"] == "und das?"


def test_interrupt_with_an_image_answers_it_right_away(app):
    server = app(_slow_script(5) + [_streamed("Sofort.")], safe_mode=False, auto_confirm=True)
    _req(server, "/api/send", {"text": "eins"})
    _events_until(server, "tool")
    started = time.monotonic()
    body = _req(server, "/api/send", {"text": "", "interrupt": True,
                                      "images": [{"name": "c.png", "data": _data_url(_png())}]})[1]
    assert body["queued"] and body["interrupt"]
    events = _events_until(server, "stopped") + _events_until(server, "done")
    assert [len(e["images"]) for e in events if e["type"] == "user"][-1] == 1
    assert time.monotonic() - started < 4.5


# -- Erzeugte Bilder (Werkzeug bild_erstellen) ------------------------------------------------
def _fake_generator(monkeypatch, data=None, anbieter="AI Horde"):
    from assistant import bildgenerator

    calls = []

    def erstellen(beschreibung, format="quadrat", *, config=None, http=None, fortschritt=None, cancel_event=None):
        calls.append(beschreibung)
        if fortschritt:
            fortschritt("In der Warteschlange: Platz 3, ca. 40 s")
            fortschritt("Das Bild wird gemalt, ca. 8 s")
        return bildgenerator.Ergebnis(data=data or _png(64, 64), mime="image/png", anbieter=anbieter,
                                      modell="FLUX.1 schnell", seed="7")

    monkeypatch.setattr(bildgenerator, "erstellen", erstellen)
    return calls


def _bild_script(beschreibung="a red cat on a roof"):
    return [(anthro_msg([tool_use_block("bild_erstellen", "b1", {"beschreibung": beschreibung})],
                        stop_reason="tool_use"), []),
            _streamed("Hier ist dein Bild.")]


def test_generated_image_becomes_an_event_and_stays_in_the_history(app, monkeypatch, tmp_path):
    calls = _fake_generator(monkeypatch)
    server = app(_bild_script(), safe_mode=False, auto_confirm=True)
    ctl = server.controller
    _req(server, "/api/send", {"text": "Mal mir eine Katze"})
    events = _events_until(server, "done")
    kinds = [e["type"] for e in events]
    assert calls == ["a red cat on a roof"]
    progress = [e["text"] for e in events if e["type"] == "image_progress"]
    assert progress == ["In der Warteschlange: Platz 3, ca. 40 s", "Das Bild wird gemalt, ca. 8 s"]
    image = next(e for e in events if e["type"] == "image")
    assert set(image) == {"type", "url", "name", "prompt", "pfad", "anbieter"}
    assert re.fullmatch(r"\d{8}-\d{6}_red-cat-roof\.png", image["name"])
    assert image["url"] == f"/api/bild/e/{image['name']}" and image["pfad"] == f"bilder/{image['name']}"
    assert image["anbieter"] == "AI Horde" and image["prompt"] == "a red cat on a roof"
    assert kinds.index("image_progress") < kinds.index("image") < kinds.index("done")
    notices = [e["text"] for e in events if e["type"] == "notice"]
    assert len(notices) == 1 and "LAION" in notices[0] and "pers\u00f6nlichen Daten" in notices[0]
    assert (tmp_path / "workspace" / image["pfad"]).is_file()
    status, headers, data = _get_raw(server, image["url"])
    assert status == 200 and headers["content-type"] == "image/png"

    hist = _req(server, "/api/history")[1]["messages"]
    assert [m["role"] for m in hist] == ["user", "image", "notice", "assistant"]
    assert hist[1] == {"role": "image", **{k: v for k, v in image.items() if k != "type"}}
    # Das Modell bekommt nur einen kurzen Text zurueck - nie das Bild als Base64
    assert "base64" not in json.dumps(json.loads(ctl.brain.provider.client.messages.requests[-1]))

    # Zweites Bild: der Hinweis kommt nicht noch einmal
    ctl.brain.provider.client.messages.calls = 0
    _req(server, "/api/send", {"text": "Noch eins"})
    events = _events_until(server, "done")
    assert any(e["type"] == "image" for e in events)
    assert not [e for e in events if e["type"] == "notice"]
    assert json.loads((tmp_path / "data" / "bilder" / "hinweis.json").read_text())["gezeigt"]


def test_terminal_prints_where_the_generated_image_is(tmp_path, monkeypatch, capsys):
    from assistant.config import load_config
    from assistant.ui.cli import CLI
    from tests._fakes import AnthroClient

    _fake_generator(monkeypatch)
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    cfg.permissions.safe_mode, cfg.permissions.auto_confirm = False, True
    cli = CLI(cfg)
    cli.brain.provider.client = AnthroClient(_bild_script("a lighthouse at night"))
    try:
        cli.brain.respond("Mal einen Leuchtturm", on_text=cli._emit)
        out = capsys.readouterr().out
        assert "In der Warteschlange: Platz 3" in out and "LAION" in out
        saved = re.search(r"\[Gespeichert: (.+?)\]", out).group(1)
        assert Path(saved).is_file() and Path(saved).parent == tmp_path / "workspace" / "bilder"
        cli.brain.provider.client.messages.calls = 0
        cli.brain.respond("Noch einer", on_text=cli._emit)
        assert "LAION" not in capsys.readouterr().out  # Hinweis nur einmal
    finally:
        cli.memory.close()


# -- Vorlesen -------------------------------------------------------------------------------
def test_voice_never_reads_image_addresses_or_markdown(app):
    from assistant.ui.cli import vorlesetext

    text = ("Hier ist es: ![Katze](/api/bild/e/20261108-120000_katze.png?t=geheim) - gespeichert unter "
            "bilder/20261108-120000_katze.png bzw. C:\\Users\\Ich\\workspace\\bilder\\x.webp, siehe "
            "https://example.org/info und data:image/png;base64,iVBORw0KGgo= **fertig**")
    spoken = vorlesetext(text)
    for bad in ("api/bild", "geheim", ".png", ".webp", "base64", "Katze](", "**", "example.org"):
        assert bad not in spoken, (bad, spoken)
    assert spoken.startswith("Hier ist es:") and spoken.endswith("fertig")

    server = app([_streamed("Schau: ![Bild](/api/bild/e/20261108-120000_x.png) bilder/20261108-120000_x.png")])
    ctl = server.controller
    said = []

    class Stimme:
        enabled = True

        def speak(self, text):
            said.append(text)

        def stop(self):
            pass

    ctl.voice_out = Stimme()
    _req(server, "/api/send", {"text": "Zeig"})
    _events_until(server, "speaking")
    end = time.monotonic() + 5
    while not said and time.monotonic() < end:
        time.sleep(0.05)
    assert said and "api/bild" not in said[0] and ".png" not in said[0] and said[0].startswith("Schau")


# -- Terminal: /bild und Bildpfade -------------------------------------------------------------
@pytest.fixture
def terminal(tmp_path, monkeypatch):
    from assistant.config import load_config
    from assistant.ui.cli import CLI
    from tests._fakes import AnthroClient

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    clis = []

    def make(inputs, replies=None):
        cli = CLI(cfg)
        cli.brain.provider.client = AnthroClient(replies or [_streamed("Gesehen.")])
        feed = iter(inputs)

        def get_input():
            try:
                return next(feed)
            except StopIteration:
                raise EOFError from None

        monkeypatch.setattr(cli, "_get_input", get_input)
        clis.append(cli)
        return cli

    yield make
    for cli in clis:
        cli.memory.close()


def _requests(cli):
    return [json.loads(r) for r in cli.brain.provider.client.messages.requests]


def _last_user(cli):
    return [m for m in _requests(cli)[-1] if m["role"] == "user"][-1]["content"]


def test_terminal_bild_command_with_paths_question_and_bare_path(terminal, tmp_path, capsys):
    ordner = tmp_path / "Meine Bilder"
    ordner.mkdir()
    (ordner / "a b.png").write_bytes(_png())
    cli = terminal([f'/bild "{ordner / "a b.png"}" zwei.jpg Was ist das?',   # relativ: im Arbeitsordner
                    f"'{ordner / 'a b.png'}'",                                # nur ein Pfad (hineingezogen)
                    f"& '{ordner / 'a b.png'}'",                               # PowerShell
                    "/bild /gibt/es/nicht.png",
                    f"Schau dir {ordner / 'a b.png'} an"])                      # Text: kein Anhang
    (tmp_path / "workspace" / "zwei.jpg").write_bytes(_jpeg())
    with pytest.raises(EOFError):
        cli._loop()
    out = capsys.readouterr().out
    reqs = _requests(cli)
    assert len(reqs) == 4
    first = [m for m in reqs[0] if m["role"] == "user"][-1]["content"]
    assert [b["type"] for b in first] == ["text", "image", "text", "image", "text"]
    assert first[-1]["text"] == "Was ist das?"
    for nummer in (1, 2):
        only = [m for m in reqs[nummer] if m["role"] == "user"][-1]["content"]
        assert [b["type"] for b in only] == ["image", "text"] and only[-1]["text"] == "Schau dir das Bild an."
    assert [m for m in reqs[3] if m["role"] == "user"][-1]["content"] == f"Schau dir {ordner / 'a b.png'} an"
    assert "Datei nicht gefunden: /gibt/es/nicht.png" in out
    assert "[Bild angehaengt: a b.png, 40x30]" in out and "[Bild angehaengt: zwei.jpg" in out


def test_terminal_bild_without_path_uses_the_clipboard(terminal, monkeypatch, capsys):
    from PIL import ImageGrab

    inhalt = {"wert": Image.new("RGB", (50, 20), (0, 200, 0))}
    monkeypatch.setattr(ImageGrab, "grabclipboard", lambda: inhalt["wert"])
    cli = terminal(["/bild Was steht da?", "/bild"])
    with pytest.raises(EOFError):
        cli._loop()
    reqs = _requests(cli)
    assert len(reqs) == 2
    erste = [m for m in reqs[0] if m["role"] == "user"][-1]["content"]
    assert [b["type"] for b in erste] == ["image", "text"] and erste[-1]["text"] == "Was steht da?"

    inhalt["wert"] = None
    cli = terminal(["/bild"])
    with pytest.raises(EOFError):
        cli._loop()
    assert "In der Zwischenablage ist kein Bild" in capsys.readouterr().out
    assert cli.brain.provider.client.messages.calls == 0

    def kaputt():
        raise OSError("xclip fehlt")

    monkeypatch.setattr(ImageGrab, "grabclipboard", kaputt)
    cli = terminal(["/bild"])
    with pytest.raises(EOFError):
        cli._loop()
    assert "Zwischenablage" in capsys.readouterr().out and cli.brain.provider.client.messages.calls == 0


def test_terminal_refuses_broken_images_and_too_many(terminal, tmp_path, capsys):
    (tmp_path / "kaputt.png").write_bytes(b"kein bild")
    (tmp_path / "ok.png").write_bytes(_png())
    ok = str(tmp_path / "ok.png")
    cli = terminal([str(tmp_path / "kaputt.png"), " ".join([ok] * 3), f"/bild {ok} {ok} {ok} Frage",
                    f"{ok} Was ist das?"])
    cli.config.bilder.max_bilder_pro_nachricht = 2
    with pytest.raises(EOFError):
        cli._loop()
    out = capsys.readouterr().out
    assert "kein Bild, das ich lesen kann" in out
    assert out.count("Hoechstens 2 Bilder pro Nachricht.") == 2
    assert cli.brain.provider.client.messages.calls == 0  # drei Bilder bei Grenze 2: nicht gesendet
    if ok.startswith("/"):  # Linux/macOS: Pfad mit Frage ist kein "unbekannter Befehl"
        assert "Bild mitschicken: /bild" in out and "Unbekannter Befehl" not in out


def test_app_explains_how_to_attach_images(app):
    server = app([])
    _req(server, "/api/send", {"text": "/bild"})
    assert "B\u00fcroklammer" in _events_until(server, "notice")[-1]["text"]


def test_old_uploads_are_cleaned_up_at_start(app):
    from assistant.app.controller import alte_uploads_loeschen

    server = app([])
    ctl = server.controller
    ordner = ctl.upload_dir()
    ordner.mkdir(parents=True)
    alt, neu, fremd = ordner / "aaaaaaaaaaaaaaaa.png", ordner / "bbbbbbbbbbbbbbbb.png", ordner / "notiz.txt"
    for pfad in (alt, neu, fremd):
        pfad.write_bytes(b"x")
    vor_40_tagen = time.time() - 40 * 86400
    os.utime(alt, (vor_40_tagen, vor_40_tagen))
    os.utime(fremd, (vor_40_tagen, vor_40_tagen))
    ctl.startup()
    assert not alt.exists() and neu.exists() and fremd.exists()  # nur alte Bilder, nichts anderes
    assert alte_uploads_loeschen(ordner.parent / "gibt-es-nicht") == 0


def test_setup_window_and_commands_know_the_new_features(app):
    server = app([])
    state = _req(server, "/api/state")[1]
    assert "/feedback" in [c["cmd"] for c in state["commands"]]
    assert state["feedback_due"] is False
    from assistant.ui import cli

    assert "/bild <pfad> [frage]" in cli.__doc__ and "/feedback" in cli.__doc__


if sys.platform == "win32":  # pragma: no cover - Pfade mit Laufwerk
    def test_windows_path_with_drive_letter_is_found(terminal, tmp_path):
        (tmp_path / "w.png").write_bytes(_png())
        cli = terminal([str(tmp_path / "w.png")])
        with pytest.raises(EOFError):
            cli._loop()
        assert cli.brain.provider.client.messages.calls == 1
