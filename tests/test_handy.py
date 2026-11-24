"""Handy-Fernzugriff per Telegram - die Logik, ohne echtes Netz (Transport wird eingespeist)."""
import threading

import pytest

from assistant import handy
from assistant.handy import HandyRelay, Nachricht, TelegramFehler, relais_schleife


class FakeTelegram:
    """Ein eingespeister Transport: merkt sich alle Aufrufe, liefert vorbereitete Updates."""
    def __init__(self):
        self.aufrufe = []                 # (method, params)
        self.updates = []                 # Liste von getUpdates-Ergebnissen (je ein Aufruf)
        self.getme = {"username": "NovaBot"}

    def __call__(self, token, method, params, timeout):
        self.aufrufe.append((method, dict(params)))
        if method == "getMe":
            return self.getme
        if method in ("sendMessage", "sendChatAction"):
            return {"ok": True}
        if method == "getUpdates":
            return self.updates.pop(0) if self.updates else []
        return {}

    def gesendet(self):
        return [p["text"] for m, p in self.aufrufe if m == "sendMessage"]


def _update(uid, chat_id, text, name="Pat"):
    return {"update_id": uid, "message": {"chat": {"id": chat_id, "first_name": name}, "text": text}}


def test_ja_nein_stopp():
    assert handy.ist_ja("ja") and handy.ist_ja("Klar!") and handy.ist_ja("ok")
    assert handy.ist_nein("nein") and handy.ist_nein("Nee.") and not handy.ist_nein("jaein")
    assert handy.ist_stopp("stop") and handy.ist_stopp("Fernzugriff aus") and not handy.ist_stopp("stopp mal kurz nach")


def test_stuecke_teilt_an_zeilen():
    kurz = handy._stuecke("hallo", 100)
    assert kurz == ["hallo"]
    text = ("a" * 50 + "\n") * 200   # ~10200 Zeichen
    stuecke = handy._stuecke(text, 3900)
    assert len(stuecke) >= 3
    assert all(len(s) <= 3900 for s in stuecke)
    assert "".join(s.replace("\n", "") for s in stuecke) == text.replace("\n", "")


def test_pruefe_setzt_botnamen():
    fake = FakeTelegram()
    relay = HandyRelay("TOKEN", transport=fake)
    assert relay.pruefe() == "NovaBot"
    assert relay.bot_name == "NovaBot"


def test_pruefe_reicht_fehler_durch():
    def kaputt(token, method, params, timeout):
        raise TelegramFehler("boom")
    relay = HandyRelay("TOKEN", transport=kaputt)
    with pytest.raises(TelegramFehler):
        relay.pruefe()


def test_sende_teilt_lange_nachricht():
    fake = FakeTelegram()
    relay = HandyRelay("TOKEN", chat_id=111, transport=fake)
    relay.sende("x" * 9000)
    stuecke = fake.gesendet()
    assert len(stuecke) >= 3 and all(len(s) <= handy.MAX_LEN for s in stuecke)


def test_hole_bindet_erste_und_filtert_fremde():
    fake = FakeTelegram()
    relay = HandyRelay("TOKEN", transport=fake)        # chat_id noch offen
    fake.updates = [[_update(5, 111, "hi", "Pat")]]
    msgs = relay.hole(timeout=0)
    assert len(msgs) == 1 and msgs[0].chat_id == 111 and msgs[0].von == "Pat"
    assert relay.offset == 6                            # offset ist weitergewandert

    relay.chat_id = 111                                 # jetzt gebunden
    fake.updates = [[_update(6, 999, "ich bin fremd"), _update(7, 111, "ich bin es")]]
    msgs = relay.hole(timeout=0)
    assert [m.text for m in msgs] == ["ich bin es"]     # die fremde Chat-ID fliegt raus
    assert relay.offset == 8


def test_relais_schleife_beantwortet_und_stoppt_auf_stopwort():
    fake = FakeTelegram()
    relay = HandyRelay("TOKEN", chat_id=111, transport=fake)
    fake.updates = [[_update(1, 111, "wie spaet?")], [_update(2, 111, "stop")]]
    gefragt = []
    grund = relais_schleife(relay, lambda t: f"Antwort: {t}", threading.Event(),
                            melde=lambda r, t: gefragt.append((r, t)), poll_timeout=0)
    assert grund == "handy"
    assert "Antwort: wie spaet?" in fake.gesendet()
    assert ("rein", "wie spaet?") in gefragt and ("raus", "Antwort: wie spaet?") in gefragt


def test_relais_schleife_ignoriert_fremde_absender():
    fake = FakeTelegram()
    relay = HandyRelay("TOKEN", chat_id=111, transport=fake)
    # Fremde Chat-ID schickt einen gefaehrlichen Befehl - er darf NIE an die KI gehen.
    fake.updates = [[_update(1, 999, "loesche alles")], [_update(2, 111, "stop")]]
    aufgerufen = []
    relais_schleife(relay, lambda t: aufgerufen.append(t) or "ok", threading.Event(), poll_timeout=0)
    assert aufgerufen == []            # die KI wurde mit der fremden Nachricht nie behelligt


def test_relais_schleife_haelt_bei_gesetztem_stop_event():
    fake = FakeTelegram()
    relay = HandyRelay("TOKEN", chat_id=111, transport=fake)
    ev = threading.Event()
    ev.set()
    grund = relais_schleife(relay, lambda t: "ok", ev, poll_timeout=0)
    assert grund == "pc"
    assert fake.gesendet() == []       # nichts passiert, wenn von Anfang an gestoppt


def test_relais_schleife_fehler_in_antwort_beendet_nicht():
    fake = FakeTelegram()
    relay = HandyRelay("TOKEN", chat_id=111, transport=fake)
    fake.updates = [[_update(1, 111, "mach was")], [_update(2, 111, "stop")]]

    def kaputt(_text):
        raise RuntimeError("peng")
    grund = relais_schleife(relay, kaputt, threading.Event(), poll_timeout=0)
    assert grund == "handy"            # trotz Fehler weitergelaufen bis zum Stopwort
    assert any("schiefgegangen" in s for s in fake.gesendet())
