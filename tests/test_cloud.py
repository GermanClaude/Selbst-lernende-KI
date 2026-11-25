"""Cloud-Nova: Server von aussen (nur mit Schluessel), Telegram per Webhook, Einstellungen aus der Umgebung."""
import http.client
import json
import threading
from types import SimpleNamespace

import pytest

from assistant import handy
from assistant.app import handy_server as hs
from assistant.app.server import AppServer

TOKEN = "cloud-schluessel-abcdefghijklmnop+xyz"


class FakeCtl:
    def __init__(self, chat_id=111):
        self.chat_id, self.befehle, self.aktiv = chat_id, [], False

    def _handy_chat_id(self):
        return self.chat_id

    def _handy_aktiv(self):
        return self.aktiv

    def _handy_befehl(self, args):
        self.befehle.append(args)
        self.aktiv = True

    def state(self):
        return {"ok": True}


@pytest.fixture
def server():
    s = AppServer(lambda b: FakeCtl(), port=0, token=TOKEN, hosts="*")
    s.start()
    yield s
    s.stop()


def _anfrage(server, methode, pfad, host="nova-ab12.onrender.com", body=None, kopf=None):
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    daten = json.dumps(body).encode() if body is not None else None
    k = {"Host": host, **(kopf or {})}
    if daten is not None:
        k["Content-Type"] = "application/json"
    c.request(methode, pfad, body=daten, headers=k)
    r = c.getresponse()
    return r.status, r.read()


def test_fremde_adresse_nur_mit_schluessel(server):
    assert _anfrage(server, "GET", "/api/state")[0] == 403
    assert _anfrage(server, "GET", "/api/state?t=falsch-falsch-falsch-falsch")[0] == 403
    # "+" im Schluessel kommt in Adressen als Leerzeichen an - muss trotzdem passen
    assert _anfrage(server, "GET", "/api/state?t=" + TOKEN)[0] == 200
    assert _anfrage(server, "GET", "/api/state?t=" + TOKEN.replace("+", "%2B"))[0] == 200


def test_gesund_ohne_schluessel(server):
    assert _anfrage(server, "GET", "/gesund") == (200, b"ok")


def test_am_pc_bleibt_es_bei_localhost():
    s = AppServer(lambda b: FakeCtl(), port=0, token=TOKEN)
    s.start()
    try:
        assert _anfrage(s, "GET", "/api/state?t=" + TOKEN)[0] == 403              # fremder Host
        assert _anfrage(s, "GET", "/api/state?t=" + TOKEN, host=f"127.0.0.1:{s.port}")[0] == 200
    finally:
        s.stop()


def test_erlaubte_hosts_liste():
    s = AppServer(lambda b: FakeCtl(), port=0, token=TOKEN, hosts={"nova.example.de"})
    s.start()
    try:
        assert _anfrage(s, "GET", "/api/state?t=" + TOKEN, host="nova.example.de")[0] == 200
        assert _anfrage(s, "GET", "/api/state?t=" + TOKEN, host="boese.example")[0] == 403
    finally:
        s.stop()


def test_cloud_einstellungen(tmp_path, monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.setenv("NOVA_TOKEN", TOKEN)
    monkeypatch.setenv("NOVA_HOST", "a.example, b.example")
    e = hs.cloud_einstellungen(tmp_path)
    assert e["port"] == 10000 and e["token"] == TOKEN and e["token_eigen"]
    assert e["hosts"] == {"a.example", "b.example"}
    monkeypatch.setenv("NOVA_TOKEN", "kurz")
    monkeypatch.delenv("NOVA_HOST")
    e = hs.cloud_einstellungen(tmp_path)
    assert not e["token_eigen"] and len(e["token"]) >= 24 and e["hosts"] == "*"
    assert hs.cloud_einstellungen(tmp_path)["token"] == e["token"]               # bleibt gleich


# ---------------------------------------------------------------- Telegram-Webhook
class FakeTelegram:
    def __init__(self):
        self.aufrufe = []

    def __call__(self, token, method, params, timeout):
        self.aufrufe.append((method, dict(params)))
        return {"ok": True}


def test_webhook_relay_reihe_und_doppelte():
    r = handy.WebhookRelay("T", chat_id=111, transport=FakeTelegram())
    upd = {"update_id": 5, "message": {"chat": {"id": 111}, "text": "Licht an", "date": 0}}
    r.einwerfen(upd)
    r.einwerfen(upd)                                                   # Telegram wiederholt: nur einmal
    r.einwerfen({"update_id": 6, "message": {"chat": {"id": 999}, "text": "fremd"}})   # fremde Chat-ID
    assert r.naechste(timeout=0.1).text == "Licht an"
    assert r.naechste(timeout=0.1) is None
    assert handy.rueckstand_holen(r) == []                             # Cloud: nichts "fuer spaeter"


def test_webhook_einrichten_und_empfangen(server, monkeypatch):
    fake = FakeTelegram()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:BOT")
    monkeypatch.setenv("NOVA_PUBLIC_URL", "https://nova-ab12.onrender.com")
    monkeypatch.setattr(handy, "_urllib_transport", fake)
    monkeypatch.setattr(handy.WebhookRelay.__init__, "__defaults__", (None, fake))
    monkeypatch.setattr(hs.threading, "Timer", lambda *a, **k: SimpleNamespace(start=lambda: None))
    assert hs.telegram_webhook_einrichten(server, TOKEN)
    pfad, geheim, relay = server.telegram
    methode, params = fake.aufrufe[-1]
    assert methode == "setWebhook" and params["url"] == "https://nova-ab12.onrender.com" + pfad
    assert params["secret_token"] == geheim and TOKEN not in pfad and "123:BOT" not in pfad
    upd = {"update_id": 1, "message": {"chat": {"id": 111}, "text": "Hallo Nova"}}
    # ohne die geheime Kopfzeile: abgelehnt
    assert _anfrage(server, "POST", pfad, body=upd)[0] == 403
    assert relay.naechste(timeout=0.1) is None
    status, _ = _anfrage(server, "POST", pfad, body=upd, kopf={"X-Telegram-Bot-Api-Secret-Token": geheim})
    assert status == 200 and relay.naechste(timeout=1).text == "Hallo Nova"
    assert server.controller.befehle == [[]]                           # Fernzugriff wurde geweckt
    assert server.controller._handy_relay_fabrik("x", 1) is relay


def test_webhook_ohne_https_oder_chat_id(server, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:BOT")
    monkeypatch.delenv("NOVA_PUBLIC_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    assert not hs.telegram_webhook_einrichten(server, TOKEN)           # keine oeffentliche Adresse
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "http://unsicher.example")
    assert not hs.telegram_webhook_einrichten(server, TOKEN)           # nur https
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://nova.onrender.com")
    server.controller.chat_id = None
    assert not hs.telegram_webhook_einrichten(server, TOKEN)           # ohne Chat-ID antwortet sie niemandem
    assert server.telegram is None


def test_relay_schleife_mit_webhook():
    fake = FakeTelegram()
    r = handy.WebhookRelay("T", chat_id=111, transport=fake)
    stop = threading.Event()
    antworten = []

    def beantworte(text):
        antworten.append(text)
        stop.set()
        return "Erledigt"

    r.einwerfen({"update_id": 1, "message": {"chat": {"id": 111}, "text": "Mach was"}})
    handy.relais_schleife(r, beantworte, stop, poll_timeout=0.1)
    assert antworten == ["Mach was"]
    assert ("sendMessage", {"chat_id": 111, "text": "Erledigt"}) in fake.aufrufe
