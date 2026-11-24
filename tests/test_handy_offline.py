"""Handy-Nachrichten, die ankamen, waehrend Nova aus war: abholen, speichern, beim Start nachfragen."""
import threading
import time

import pytest

from assistant import handy
from assistant.app.controller import AppController
from assistant.config import load_config
from assistant.handy import HandyRelay, Nachricht


class FakeTelegram:
    def __init__(self, updates=None):
        self.aufrufe = []
        self.updates = list(updates or [])

    def __call__(self, token, method, params, timeout):
        self.aufrufe.append((method, dict(params)))
        if method == "getUpdates":
            return self.updates.pop(0) if self.updates else []
        return {"ok": True}


def _update(uid, chat_id, text, date=1795500000):
    return {"update_id": uid, "message": {"chat": {"id": chat_id, "first_name": "Pat"}, "text": text, "date": date}}


# ---------------------------------------------------------------- Abholen
def test_rueckstand_holt_alles_und_bestaetigt(tmp_path):
    fake = FakeTelegram([[_update(1, 111, "mach A"), _update(2, 999, "fremd")], [_update(3, 111, "mach B")]])
    relay = HandyRelay("T", chat_id=111, transport=fake)
    msgs = handy.rueckstand_holen(relay)
    assert [m.text for m in msgs] == ["mach A", "mach B"]       # Fremdes fliegt raus
    assert msgs[0].zeit == 1795500000
    letzte = [p for m, p in fake.aufrufe if m == "getUpdates"][-1]
    assert letzte["offset"] == 4 and letzte["timeout"] == 0       # letzter Abruf bestaetigt bei Telegram


def test_rueckstand_ohne_besitzer_holt_nichts():
    fake = FakeTelegram([[_update(1, 111, "x")]])
    assert handy.rueckstand_holen(HandyRelay("T", transport=fake)) == []
    assert fake.aufrufe == []                                     # gar nicht erst abgefragt


# ---------------------------------------------------------------- Speichern
def test_speichern_laden_entfernen(tmp_path):
    assert handy.offen_laden(tmp_path) == []
    n = handy.offen_hinzufuegen(tmp_path, [Nachricht(1, 111, "mach A", zeit=10), Nachricht(2, 111, "stop"),
                                           Nachricht(3, 111, "mach B", zeit=20)])
    assert n == 2                                                 # Stopwort wird nicht gespeichert
    liste = handy.offen_laden(tmp_path)
    assert [e["text"] for e in liste] == ["mach A", "mach B"]
    handy.offen_hinzufuegen(tmp_path, [Nachricht(4, 111, "mach C", zeit=30)])  # kam waehrend der Frage dazu
    handy.offen_entfernen(tmp_path, liste)                        # nur die gefragten weg
    assert [e["text"] for e in handy.offen_laden(tmp_path)] == ["mach C"]
    handy.offen_entfernen(tmp_path, handy.offen_laden(tmp_path))
    assert not (tmp_path / "data" / "handy_offen.json").exists()


def test_texte_fuer_frage_und_auftrag():
    eins = [{"text": "Lade das Video herunter", "zeit": 0}]
    assert "eine Nachricht" in handy.offen_frage(eins) and "Lade das Video" in handy.offen_frage(eins)
    zwei = eins + [{"text": "Und schick es mir", "zeit": 0}]
    assert "2 Nachrichten" in handy.offen_frage(zwei)
    auftrag = handy.offen_auftrag(zwei)
    assert "1) Lade das Video herunter" in auftrag and "2) Und schick es mir" in auftrag


# ---------------------------------------------------------------- Ablauf im Controller
@pytest.fixture
def ctl(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = cfg.anthropic_api_key or "sk-ant-test-schluessel"
    c = AppController(cfg, lambda e: None)
    if not c.config.api_key:
        pytest.skip("kein Gehirn-Schluessel in der Testumgebung")
    yield c
    c.shutdown()


def _ablegen(ctl, *texte):
    handy.offen_hinzufuegen(ctl.config.project_root, [Nachricht(i, 111, t, zeit=i) for i, t in enumerate(texte, 1)])


def test_ja_schickt_einen_auftrag_und_leert(ctl, monkeypatch):
    _ablegen(ctl, "mach A", "mach B")
    gesendet = []
    monkeypatch.setattr(ctl, "submit", lambda text: gesendet.append(text) or {"ok": True})
    monkeypatch.setattr(ctl, "_handy_offen_entscheidung", lambda frage: "ja")
    ctl._handy_offen_fragen()
    assert len(gesendet) == 1 and "1) " in gesendet[0] and "mach A" in gesendet[0] and "mach B" in gesendet[0]
    assert handy.offen_laden(ctl.config.project_root) == []


def test_spaeter_behaelt_und_verwerfen_loescht(ctl, monkeypatch):
    _ablegen(ctl, "mach A")
    monkeypatch.setattr(ctl, "submit", lambda text: pytest.fail("darf nichts schicken"))
    monkeypatch.setattr(ctl, "_handy_offen_entscheidung", lambda frage: "spaeter")
    ctl._handy_offen_fragen()
    assert len(handy.offen_laden(ctl.config.project_root)) == 1
    monkeypatch.setattr(ctl, "_handy_offen_entscheidung", lambda frage: "verwerfen")
    ctl._handy_offen_fragen()
    assert handy.offen_laden(ctl.config.project_root) == []


def test_abschicken_klappt_nicht_dann_bleibt_es(ctl, monkeypatch):
    _ablegen(ctl, "mach A")
    monkeypatch.setattr(ctl, "submit", lambda text: {"ok": False, "error": "busy"})
    monkeypatch.setattr(ctl, "_handy_offen_entscheidung", lambda frage: "ja")
    ctl._handy_offen_fragen()
    assert [e["text"] for e in handy.offen_laden(ctl.config.project_root)] == ["mach A"]


def test_dialog_in_der_app(ctl):
    """Echter Rueckfrage-Dialog: Fenster antwortet - und Stopp heisst 'spaeter', nie 'verwerfen'."""
    ergebnis = {}
    t = threading.Thread(target=lambda: ergebnis.setdefault("v", ctl._handy_offen_entscheidung("Frage?")))
    t.start()
    for _ in range(100):
        offen = ctl.open_asks()
        if offen:
            break
        time.sleep(0.02)
    werte = [o["value"] for o in offen[0]["options"]]
    assert werte == ["ja", "spaeter", "verwerfen"] and offen[0]["kind"] == "question"
    ctl.answer(offen[0]["id"], "ja")
    t.join(2)
    assert ergebnis["v"] == "ja"

    t = threading.Thread(target=lambda: ergebnis.__setitem__("v", ctl._handy_offen_entscheidung("Frage?")))
    t.start()
    for _ in range(100):
        if ctl.open_asks():
            break
        time.sleep(0.02)
    ctl.brain.provider.cancel_event.set()                         # Stopp-Knopf
    t.join(2)
    ctl.brain.provider.cancel_event.clear()
    assert ergebnis["v"] == "spaeter"


def test_rueckstand_sichern_mit_relay(ctl):
    fake = FakeTelegram([[_update(5, 111, "druck das PDF")]])
    n = ctl._handy_rueckstand_sichern(HandyRelay("T", chat_id=111, transport=fake))
    assert n == 1 and handy.offen_laden(ctl.config.project_root)[0]["text"] == "druck das PDF"


def test_ohne_einrichtung_passiert_beim_start_nichts(ctl, monkeypatch):
    monkeypatch.setattr(ctl, "_handy_offen_entscheidung", lambda frage: pytest.fail("keine Frage ohne Nachrichten"))
    ctl._handy_beim_start()                                        # kein Token -> kein Netz, keine Frage
