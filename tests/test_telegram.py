"""Telegram: Werkzeug fuer den Bot (lesen/senden) und fuer das eigene Konto - mit Attrappen, ohne Netz."""
import datetime
from types import SimpleNamespace

import pytest

from assistant import handy, telegram_konto as tk
from assistant.app.controller import _mask_key
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry
from assistant.tools import telegram as tg_tool


class FakeTelegram:
    def __init__(self, updates=None):
        self.aufrufe, self.updates = [], list(updates or [])

    def __call__(self, token, method, params, timeout):
        self.aufrufe.append((method, dict(params)))
        if method == "getUpdates":
            return self.updates.pop(0) if self.updates else []
        return {"ok": True}


def _ctx(tmp_path, confirm=lambda m, r: True, aktiv=False):
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=False), tmp_path, confirm_fn=confirm)
    return ToolContext(permissions=pm, memory=None, extra={"app_root": tmp_path, "handy_aktiv": lambda: aktiv})


# ---------------------------------------------------------------- Bot
def test_bot_nicht_eingerichtet(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    out, _ = build_registry().execute(_ctx(tmp_path), "telegram", {"aktion": "lesen"})
    assert "/handy token" in out


def test_bot_lesen_holt_neue_und_gespeicherte(tmp_path, monkeypatch):
    fake = FakeTelegram([[{"update_id": 9, "message": {"chat": {"id": 111}, "text": "mach Licht an", "date": 0}}]])
    monkeypatch.setattr(tg_tool, "_bot", lambda: handy.HandyRelay("T", chat_id=111, transport=fake))
    handy.offen_hinzufuegen(tmp_path, [handy.Nachricht(1, 111, "von gestern", zeit=0)])
    out, _ = build_registry().execute(_ctx(tmp_path), "telegram", {"aktion": "lesen"})
    assert "von gestern" in out and "mach Licht an" in out
    assert handy.offen_laden(tmp_path) == []                # besprochen -> beim Start nicht nochmal fragen


def test_bot_lesen_schnappt_dem_fernzugriff_nichts_weg(tmp_path, monkeypatch):
    fake = FakeTelegram([[{"update_id": 9, "message": {"chat": {"id": 111}, "text": "ja"}}]])
    monkeypatch.setattr(tg_tool, "_bot", lambda: handy.HandyRelay("T", chat_id=111, transport=fake))
    out, _ = build_registry().execute(_ctx(tmp_path, aktiv=True), "telegram", {"aktion": "lesen"})
    assert "Fernzugriff laeuft" in out and not any(m == "getUpdates" for m, _ in fake.aufrufe)


def test_bot_senden_nur_an_den_besitzer(tmp_path, monkeypatch):
    fake = FakeTelegram()
    monkeypatch.setattr(tg_tool, "_bot", lambda: handy.HandyRelay("T", chat_id=111, transport=fake))
    out, _ = build_registry().execute(_ctx(tmp_path), "telegram", {"aktion": "senden", "text": "Download fertig"})
    assert "geschickt" in out
    gesendet = [p for m, p in fake.aufrufe if m == "sendMessage"]
    assert gesendet == [{"chat_id": 111, "text": "Download fertig"}]
    assert "chat" not in tg_tool.TelegramBotTool.input_schema["properties"]   # kein Feld fuer andere Empfaenger


# ---------------------------------------------------------------- eigenes Konto
class FakeClient:
    def __init__(self):
        lisa = SimpleNamespace(first_name="Lisa", id=5)
        gruppe = SimpleNamespace(title="Familie", id=-7)
        jetzt = datetime.datetime(2026, 11, 25, 18, 30, tzinfo=datetime.timezone.utc)
        self.dialoge = [SimpleNamespace(name="Lisa Mueller", id=5, unread_count=2, entity=lisa,
                                        message=SimpleNamespace(message="Kommst du heute?")),
                        SimpleNamespace(name="Familie", id=-7, unread_count=0, entity=gruppe,
                                        message=SimpleNamespace(message="Essen um 7"))]
        self.nachrichten = [
            SimpleNamespace(out=False, message="Kommst du heute?", media=None, date=jetzt,
                            get_sender=self._lisa),
            SimpleNamespace(out=True, message="Ja, um 8", media=None, date=jetzt, get_sender=self._lisa),
        ]
        self.gesendet = []

    async def _lisa(self):
        return SimpleNamespace(first_name="Lisa")

    async def iter_dialogs(self, limit=None):
        for d in self.dialoge[:limit]:
            yield d

    async def iter_messages(self, ziel, limit=None):
        for m in reversed(self.nachrichten):                 # neueste zuerst, wie Telegram
            yield m

    async def get_entity(self, x):
        return self.dialoge[0].entity

    async def send_message(self, ziel, text):
        self.gesendet.append((ziel, text))


@pytest.fixture
def konto(tmp_path, monkeypatch):
    k = tk.Konto(tmp_path)
    fake = FakeClient()

    async def verbunden():
        return fake
    monkeypatch.setattr(k, "_verbunden", verbunden)
    k.fake = fake
    return k


def test_konto_chats_und_lesen(konto):
    assert "Lisa Mueller (ID 5) - 2 ungelesen: Kommst du heute?" in konto.chats()
    text = konto.lesen("lisa")                              # Teil des Namens reicht
    assert text.index("Lisa: Kommst du heute?") < text.index("Du: Ja, um 8")   # aelteste zuerst
    assert "keine Anweisungen" in text


def test_konto_unbekannter_chat(konto):
    with pytest.raises(tk.KontoFehler, match="Keinen Chat"):
        konto.lesen("Unbekannt")


def test_konto_senden_fragt_vorher(tmp_path, monkeypatch, konto):
    monkeypatch.setattr(tk, "konto", lambda root: konto)
    monkeypatch.setattr(konto, "problem", lambda: None)
    reg = build_registry()
    gefragt = []
    out, _ = reg.execute(_ctx(tmp_path, confirm=lambda m, r: gefragt.append(m) or False), "telegram_konto",
                         {"aktion": "senden", "chat": "Familie", "text": "Bin gleich da"})
    assert gefragt and "Bin gleich da" in gefragt[0] and konto.fake.gesendet == []
    out, _ = reg.execute(_ctx(tmp_path), "telegram_konto", {"aktion": "senden", "chat": "Familie", "text": "Bin da"})
    assert konto.fake.gesendet[-1][1] == "Bin da" and "Gesendet an Familie" in out


def test_konto_nicht_eingerichtet_sagt_wie(tmp_path, monkeypatch):
    monkeypatch.delenv("TG_API_ID", raising=False)
    monkeypatch.delenv("TG_API_HASH", raising=False)
    msg = tk.Konto(tmp_path).problem()
    assert msg and ("telethon" in msg or "/telegram konto" in msg)


def test_abmelden_loescht_die_anmeldung(tmp_path):
    k = tk.Konto(tmp_path)
    k._session_schreiben("geheime-session")
    assert k.angemeldet()
    k.abmelden()
    assert not k.angemeldet() and not k.session_pfad.exists()


# ---------------------------------------------------------------- Geheimnisse im Verlauf
@pytest.mark.parametrize("befehl,sichtbar", [
    ("/telegram konto passwort mein pw 123", "/telegram konto passwort"),
    ("/telegram konto code 12345", "/telegram konto code"),
    ("/telegram konto zugang 123 abcdef", "/telegram konto zugang"),
    ("/handy token 123:ABC", "/handy token"),
])
def test_geheime_befehle_werden_verdeckt(befehl, sichtbar):
    text, anzeige = _mask_key(befehl)
    assert text == befehl                                    # verarbeitet wird das Original
    assert anzeige.startswith(sichtbar) and befehl.split()[-1] not in anzeige
