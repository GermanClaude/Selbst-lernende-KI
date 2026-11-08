"""Feedback & Bewertung und die Bildgenerator-Einstellungen in App und Terminal (Teil E).
Kein echtes Netz: Senden (post), Fern-Datei (fetch) und Cloudflare-Pruefung sind gefaelscht."""
import base64
import io
import json
import time
from types import SimpleNamespace

import pytest

from assistant import feedback
from assistant.config import load_config
from tests.test_app import _events_until, _req, app

_FIXTURES = (app,)  # die App-Fixture aus test_app.py (echter Server, gefaelschtes Claude)

ADRESSE = "https://script.google.com/macros/s/AKfycbTestTestTest_123-abc/exec"
KONTO = "0123456789abcdef0123456789abcdef"
TOKEN = "Cf_Token-abcdefghijklmnopqrstuvwxyz012345"


class Antwort:
    def __init__(self, status=200, text='{"ok": true}'):
        self.status_code = status
        self.text = text

    def close(self):
        pass


class Post:
    """Gefaelschtes requests.post - merkt sich jede Sendung."""

    def __init__(self, *antworten):
        self.antworten = list(antworten) or [Antwort()]
        self.calls = []

    def __call__(self, url, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "payload": json.loads(data), "timeout": timeout})
        antwort = self.antworten[min(len(self.calls) - 1, len(self.antworten) - 1)]
        if isinstance(antwort, BaseException):
            raise antwort
        return antwort


class _Http404(Exception):
    response = SimpleNamespace(status_code=404)


def _fetch_404(url, timeout=None):
    raise _Http404("Not Found")


def _png() -> bytes:
    from PIL import Image

    puffer = io.BytesIO()
    Image.new("RGB", (30, 20), (1, 2, 3)).save(puffer, "PNG")
    return puffer.getvalue()


def _data_url() -> str:
    return "data:image/png;base64," + base64.b64encode(_png()).decode()


@pytest.fixture
def fb_app(app):
    """App mit gefaelschtem Feedback-Netz (eigene Adresse, nie GitHub/Google)."""

    def make(scripted=None, adresse=ADRESSE, post=None):
        server = app(scripted or [])
        ctl = server.controller
        ctl.config.feedback.adresse = adresse
        ctl._feedback_post = post or Post()
        ctl._feedback_fetch = _fetch_404
        return server

    return make


# -- Status, Senden ---------------------------------------------------------------------
def test_feedback_status_and_sending_with_an_image(fb_app):
    pytest.importorskip("PIL")
    post = Post()
    server = fb_app(post=post)
    assert _req(server, "/api/feedback") == (200, {"ok": True, "configured": True, "due": False, "pending": 0,
                                                    "max_images": 5})
    status, body = _req(server, "/api/feedback", {"kind": "bug", "stars": 4, "text": "Knopf klemmt",
                                                  "contact": "rueckfrage@example.invalid", "trigger": "popup",
                                                  "images": [{"name": "fehler.png", "data": _data_url()}]})
    assert status == 200 and body == {"ok": True, "status": "gesendet", "message": feedback.MELDUNGEN["ok"]}
    assert len(post.calls) == 1 and post.calls[0]["url"] == ADRESSE
    payload = post.calls[0]["payload"]
    assert payload["app"] == "Nova" and payload["kind"] == "bug" and payload["stars"] == 4
    assert payload["trigger"] == "popup" and payload["text"] == "Knopf klemmt"
    assert payload["images"][0]["name"] == "fehler.png" and base64.b64decode(payload["images"][0]["data"])
    # Nichts davon landet im Chat-Verlauf
    assert "Knopf klemmt" not in json.dumps(_req(server, "/api/history")[1])


def test_feedback_without_mailbox_is_kept_in_the_outbox(fb_app, tmp_path):
    post = Post()
    server = fb_app(adresse="", post=post)
    assert _req(server, "/api/feedback")[1]["configured"] is False
    body = _req(server, "/api/feedback", {"kind": "idee", "stars": None, "text": "Dunkles Thema bitte"})[1]
    assert body["ok"] is True and body["status"] == "gespeichert" and "Postfach" in body["message"]
    assert post.calls == [] and _req(server, "/api/feedback")[1]["pending"] == 1
    assert len(list((tmp_path / "data" / "feedback_ausgang").glob("*.json"))) == 1


def test_bad_feedback_is_refused_with_a_message(fb_app):
    post = Post()
    server = fb_app(post=post)
    body = _req(server, "/api/feedback", {"kind": "feedback", "stars": None, "text": "   "})[1]
    assert body["ok"] is False and body["error"]
    body = _req(server, "/api/feedback", {"text": "x", "images": [{"name": "a.png", "data": "data:text/plain;base64,eA=="}]})[1]
    assert body["ok"] is False and "nicht richtig an" in body["error"]
    body = _req(server, "/api/feedback", {"text": "x", "images": [{"name": "a.png", "data": _data_url()}] * 6})[1]
    assert body["ok"] is False and "5 Bilder" in body["error"]
    body = _req(server, "/api/feedback", {"text": "x", "images": "nicht-eine-liste"})[1]
    assert body["ok"] is False
    assert post.calls == []
    # Zu gross fuer den Postfach-Dienst -> abgelehnt, nicht gespeichert
    post.antworten = [Antwort(200, '{"ok": false, "fehler": "zu_gross"}')]
    body = _req(server, "/api/feedback", {"text": "gross"})[1]
    assert body == {"ok": False, "status": "abgelehnt", "error": feedback.MELDUNGEN["zu_gross"]}


def test_double_click_sends_only_once(fb_app):
    server = fb_app()
    ctl = server.controller
    assert ctl._feedback_lock.acquire(blocking=False)  # eine Sendung laeuft gerade
    try:
        body = _req(server, "/api/feedback", {"stars": 5, "text": "zweimal"})[1]
    finally:
        ctl._feedback_lock.release()
    assert body["ok"] is False and "schon gesendet" in body["error"] and ctl._feedback_post.calls == []


# -- Nachfrage (Pop-up) ---------------------------------------------------------------------
def test_feedback_due_in_state_and_later_and_shown(fb_app, tmp_path):
    server = fb_app()
    ctl = server.controller
    assert _req(server, "/api/state")[1]["feedback_due"] is False
    feedback.nutzung_hinzufuegen(61 * 60, root=ctl.config)
    assert _req(server, "/api/state")[1]["feedback_due"] is True
    assert _req(server, "/api/feedback")[1]["due"] is True
    assert _req(server, "/api/feedback/gezeigt", {})[1] == {"ok": True, "due": False}
    assert _events_until(server, "state")[-1]["state"]["feedback_due"] is False
    assert _req(server, "/api/state")[1]["feedback_due"] is False

    # 12 Tage spaeter wieder faellig; "Spaeter" schiebt es erneut hinaus
    stand = json.loads((tmp_path / "data" / "feedback_state.json").read_text())
    stand["zuletzt_gezeigt"] = "2020-01-01T00:00:00"
    (tmp_path / "data" / "feedback_state.json").write_text(json.dumps(stand))
    assert _req(server, "/api/state")[1]["feedback_due"] is True
    assert _req(server, "/api/feedback/spaeter", {})[1]["ok"] is True
    assert _req(server, "/api/state")[1]["feedback_due"] is False

    # Abgeschickt zaehlt ebenso als erledigt
    stand = json.loads((tmp_path / "data" / "feedback_state.json").read_text())
    stand["zuletzt_gezeigt"] = "2020-01-01T00:00:00"
    (tmp_path / "data" / "feedback_state.json").write_text(json.dumps(stand))
    assert _req(server, "/api/state")[1]["feedback_due"] is True
    assert _req(server, "/api/feedback", {"stars": 5})[1]["status"] == "gesendet"
    assert _req(server, "/api/state")[1]["feedback_due"] is False


def test_usage_is_counted_while_the_app_runs_and_tells_the_window(fb_app, tmp_path):
    server = fb_app()
    ctl = server.controller
    feedback.nutzung_hinzufuegen(60 * 60 - 0.05, root=ctl.config)   # knapp unter einer Stunde
    ctl._NUTZUNG_TAKT = 0.05
    ctl._NUTZUNG_SPEICHERN = 2
    ctl._start_feedback_watch()
    ctl._start_feedback_watch()  # nur einmal
    end = time.monotonic() + 10
    while time.monotonic() < end:
        event = _events_until(server, "state")[-1]
        if event["state"]["feedback_due"]:
            break
    else:
        raise AssertionError("Nachfrage wurde nie faellig")
    assert feedback.nutzung_sekunden(ctl.config) >= 3600
    # Beim Beenden wird der Rest gespeichert
    ctl._stop_watch.set()
    time.sleep(0.15)
    vorher = feedback.nutzung_sekunden(ctl.config)
    ctl._nutzung_offen = 42.0
    ctl._shutdown()
    assert feedback.nutzung_sekunden(tmp_path) == pytest.approx(vorher + 42.0, abs=0.2)


def test_standby_does_not_count_as_usage(tmp_path, monkeypatch):
    from assistant.ui.cli import CLI

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cli = CLI(cfg)
    try:
        uhr = iter([100.0, 100.0 + 8 * 3600, 100.0 + 8 * 3600 + 60])  # dazwischen 8 h Standby
        monkeypatch.setattr("assistant.ui.cli.time.monotonic", lambda: next(uhr))
        runden = iter([False, False, True])
        cli._stop_watch = SimpleNamespace(wait=lambda _t: next(runden))
        cli._NUTZUNG_SPEICHERN = 1
        cli._nutzung_zaehlen()
        assert feedback.nutzung_sekunden(tmp_path) == pytest.approx(2 * cli._NUTZUNG_TAKT + 60, abs=0.5)
    finally:
        cli.memory.close()


def test_outbox_is_sent_at_start(fb_app, tmp_path):
    server = fb_app(adresse="")
    ctl = server.controller
    assert _req(server, "/api/feedback", {"stars": 3, "text": "offline geschrieben"})[1]["status"] == "gespeichert"
    ctl.config.feedback.adresse = ADRESSE
    ctl._NUTZUNG_TAKT = 3600
    ctl.startup()
    end = time.monotonic() + 10
    while feedback.ausgang_anzahl(tmp_path) and time.monotonic() < end:
        time.sleep(0.05)
    assert feedback.ausgang_anzahl(tmp_path) == 0
    assert [c["payload"]["text"] for c in ctl._feedback_post.calls] == ["offline geschrieben"]


def test_successful_feedback_also_sends_what_was_waiting(fb_app, tmp_path):
    server = fb_app(adresse="")
    ctl = server.controller
    _req(server, "/api/feedback", {"stars": 2, "text": "alt"})
    ctl.config.feedback.adresse = ADRESSE
    assert _req(server, "/api/feedback", {"stars": 5, "text": "neu"})[1]["status"] == "gesendet"
    end = time.monotonic() + 10
    while feedback.ausgang_anzahl(tmp_path) and time.monotonic() < end:
        time.sleep(0.05)
    assert sorted(c["payload"]["text"] for c in ctl._feedback_post.calls) == ["alt", "neu"]


# -- /feedback als Befehl --------------------------------------------------------------------
def test_feedback_command_opens_the_dialog_in_the_app(fb_app):
    server = fb_app()
    for befehl in ("/feedback", "/bewertung"):
        _req(server, "/api/send", {"text": befehl})
        assert _events_until(server, "open")[-1]["what"] == "feedback"
    assert server.controller._feedback_post.calls == []


@pytest.fixture
def terminal_fb(tmp_path, monkeypatch, capsys):
    from assistant.ui.cli import CLI

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.feedback.adresse = ADRESSE
    clis = []

    def make(answers):
        cli = CLI(cfg)
        cli._feedback_post = Post()
        cli._feedback_fetch = _fetch_404
        feed = iter(answers)

        def fake_input(prompt=""):
            try:
                return next(feed)
            except StopIteration:
                raise EOFError from None

        monkeypatch.setattr("builtins.input", fake_input)
        clis.append(cli)
        return cli

    yield make
    for cli in clis:
        cli.memory.close()


def test_terminal_feedback_asks_step_by_step_and_sends(terminal_fb, tmp_path, capsys):
    pytest.importorskip("PIL")
    (tmp_path / "mit leer.png").write_bytes(_png())
    cli = terminal_fb(["x", "3",                       # Art: erst Unsinn, dann Idee
                       "9", "4",                       # Sterne: erst ungueltig
                       "Tolle App", "Zweite Zeile", "",  # Text, leere Zeile = fertig
                       str(tmp_path / "fehlt.png"), f'"{tmp_path / "mit leer.png"}"',
                       "rueckfrage@example.invalid"])
    cli._handle_command("/feedback")
    out = capsys.readouterr().out
    assert "Bitte eine Zahl von 1 bis 4" in out and "Bitte eine Zahl von 1 bis 5" in out
    assert "nicht gefunden" in out and "1 Bild(er) angehaengt" in out
    assert "Danke! Dein Feedback wurde gesendet." in out
    assert "Passwoerter" in out  # Datenschutz-Hinweis vorher
    payload = cli._feedback_post.calls[0]["payload"]
    assert payload["kind"] == "idee" and payload["stars"] == 4 and payload["text"] == "Tolle App\nZweite Zeile"
    assert payload["contact"] == "rueckfrage@example.invalid" and payload["trigger"] == "menue"
    assert len(payload["images"]) == 1 and payload["images"][0]["name"] == "mit leer.png"


def test_terminal_feedback_can_be_cancelled_and_needs_content(terminal_fb, capsys):
    for answers in (["q"], ["1", "q"], [], ["1", "", "", ""]):
        cli = terminal_fb(list(answers))
        cli._feedback_terminal()
        out = capsys.readouterr().out
        assert "nichts" in out and cli._feedback_post.calls == []
    cli = terminal_fb(["", "5", "q", "", ""])  # "q" als erste Textzeile bricht ab
    cli._feedback_terminal()
    assert "Abgebrochen" in capsys.readouterr().out
    cli = terminal_fb(["", "*****", "", "", ""])  # Sterne als *****
    cli._feedback_terminal()
    assert cli._feedback_post.calls[0]["payload"]["stars"] == 5
    assert cli._feedback_post.calls[0]["payload"]["kind"] == "bewertung"


def test_terminal_hint_once_when_due_and_feedback_after_it_counts_as_popup(terminal_fb, tmp_path, capsys):
    cli = terminal_fb(["", "5", "Super", "", "", ""])
    feedback.nutzung_hinzufuegen(2 * 3600, root=tmp_path)
    inputs = iter(["/feedback"])

    def get_input():
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError from None

    cli._get_input = get_input
    with pytest.raises(EOFError):
        cli._loop()
    out = capsys.readouterr().out
    assert out.count("Magst du Nova bewerten? Tippe /feedback") == 1
    assert cli._feedback_post.calls[0]["payload"]["trigger"] == "popup"
    assert not feedback.ist_faellig(cli.config)  # gezeigt + gesendet gemerkt
    assert cli._show_feedback_hint() is False


# -- Bildgenerator-Einstellungen ---------------------------------------------------------
class CfHttp:
    def __init__(self, status=200, daten=None):
        self.status, self.daten = status, daten if daten is not None else {"success": True,
                                                                          "result": {"status": "active"}}
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return SimpleNamespace(status_code=self.status, json=lambda: self.daten, close=lambda: None)


@pytest.fixture
def cf_env(monkeypatch):
    for name in ("CLOUDFLARE_AI_API_KEY", "CLOUDFLARE_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)  # was die App setzt, wird danach wieder entfernt


def test_cloudflare_settings_never_echo_the_key(app, tmp_path, cf_env):
    server = app([])
    ctl = server.controller
    assert _req(server, "/api/setup")[1]["bilder"] == {"anbieter": "auto", "cloudflare": False, "aktiv": "AI Horde"}

    ctl._cloudflare_http = CfHttp(401, {"success": False, "errors": [{"code": 1000}]})
    raw = _req(server, "/api/bilder/einstellen", {"cloudflare_token": TOKEN, "cloudflare_account_id": KONTO})[1]
    assert raw["ok"] is False and "ung\u00fcltig" in raw["message"] and TOKEN not in json.dumps(raw)
    assert not (tmp_path / ".env").exists() and ctl.config.cloudflare_api_key is None

    http = CfHttp()
    ctl._cloudflare_http = http
    raw = _req(server, "/api/bilder/einstellen", {"cloudflare_token": f"  {TOKEN} ", "cloudflare_account_id": KONTO})[1]
    assert raw["ok"] is True and "Cloudflare" in raw["message"] and TOKEN not in json.dumps(raw)
    assert raw["bilder"] == {"anbieter": "auto", "cloudflare": True, "aktiv": "Cloudflare"}
    assert http.calls[0][1] == {"Authorization": f"Bearer {TOKEN}"}
    env = (tmp_path / ".env").read_text()
    assert f"CLOUDFLARE_AI_API_KEY={TOKEN}" in env and f"CLOUDFLARE_ACCOUNT_ID={KONTO}" in env
    setup = _req(server, "/api/setup")[1]
    assert setup["bilder"] == {"anbieter": "auto", "cloudflare": True, "aktiv": "Cloudflare"}
    assert TOKEN not in json.dumps(setup) and TOKEN not in json.dumps(_req(server, "/api/state")[1])
    assert TOKEN not in json.dumps(ctl.history)
    assert load_config(tmp_path).cloudflare_api_key == TOKEN  # bleibt nach dem Neustart

    # Anbieter waehlen (in den Einstellungen gespeichert)
    raw = _req(server, "/api/bilder/einstellen", {"anbieter": "horde"})[1]
    assert raw["ok"] and raw["bilder"]["aktiv"] == "AI Horde" and load_config(tmp_path).bilder.anbieter == "horde"
    assert _req(server, "/api/bilder/einstellen", {"anbieter": "quatsch"})[1]["ok"] is False

    # Nur die Konto-ID aendern: der gespeicherte Token wird damit neu geprueft
    neu = "fedcba9876543210fedcba9876543210"
    raw = _req(server, "/api/bilder/einstellen", {"cloudflare_account_id": neu})[1]
    assert raw["ok"] and ctl.config.cloudflare_account_id == neu and http.calls[-1][1]["Authorization"].endswith(TOKEN)

    # Entfernen
    raw = _req(server, "/api/bilder/einstellen", {"entfernen": True, "anbieter": "auto"})[1]
    assert raw["ok"] and raw["bilder"] == {"anbieter": "auto", "cloudflare": False, "aktiv": "AI Horde"}
    assert TOKEN not in (tmp_path / ".env").read_text()
    assert load_config(tmp_path).cloudflare_api_key is None


def test_cloudflare_settings_check_their_input(app, tmp_path, cf_env):
    server = app([])
    ctl = server.controller
    http = CfHttp()
    ctl._cloudflare_http = http
    cases = [
        ({}, "nichts zu speichern"),
        ({"cloudflare_token": TOKEN}, "Konto-ID"),
        ({"cloudflare_account_id": KONTO}, "API-Token"),
        ({"cloudflare_token": TOKEN + "\nEVIL=1", "cloudflare_account_id": KONTO}, "sieht nicht richtig aus"),
        ({"cloudflare_token": "kurz", "cloudflare_account_id": KONTO}, "sieht nicht richtig aus"),
        ({"cloudflare_token": TOKEN, "cloudflare_account_id": "123"}, "Konto-ID sieht nicht richtig aus"),
    ]
    for body, expected in cases:
        raw = _req(server, "/api/bilder/einstellen", body)[1]
        assert raw["ok"] is False and expected.lower() in raw["message"].lower(), (body, raw)
        assert TOKEN not in json.dumps(raw)
    assert http.calls == [] and not (tmp_path / ".env").exists()
    # "cloudflare" ohne Zugang: gespeichert, aber ehrlich gesagt, dass AI Horde malt
    raw = _req(server, "/api/bilder/einstellen", {"anbieter": "cloudflare"})[1]
    assert raw["ok"] and "noch nicht eingerichtet" in raw["message"] and raw["bilder"]["aktiv"] == "AI Horde"


def test_feedback_from_the_window_never_reads_file_paths(fb_app, tmp_path):
    post = Post()
    server = fb_app(post=post)
    geheim = tmp_path / "privat.png"
    geheim.write_bytes(_png())
    for images in ([str(geheim)], [{"name": "x.png", "data": str(geheim)}], [{"name": "x", "data": "\\\\server\\a.png"}]):
        body = _req(server, "/api/feedback", {"text": "x", "images": images})[1]
        assert body["ok"] is False and "nicht richtig an" in body["error"]
    assert post.calls == []


def test_upload_folder_stays_small(tmp_path):
    import os

    from assistant.app.controller import uploads_begrenzen

    for i in range(6):
        p = tmp_path / f"{i:016x}.png"
        p.write_bytes(b"x" * 100)
        os.utime(p, (1000 + i, 1000 + i))
    (tmp_path / "fremd.txt").write_text("bleibt")
    assert uploads_begrenzen(tmp_path, max_dateien=4) == 2
    rest = sorted(p.name for p in tmp_path.iterdir())
    assert rest[:4] == [f"{i:016x}.png" for i in range(2, 6)] and "fremd.txt" in rest
    assert uploads_begrenzen(tmp_path, max_dateien=10, max_bytes=250) == 2
