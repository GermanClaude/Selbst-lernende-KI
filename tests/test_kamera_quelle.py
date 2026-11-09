"""Handy-Kamera: QR-Code (segno) und Quellen-Adapter fuer das Live-Sehen (ohne aiortc)."""
import time

import pytest

from assistant import kamera
from assistant.kamera import qr
from assistant.kamera.quelle import HandyQuelle, HandyQuellenProtokoll


class FakeInfo:
    def als_dict(self):
        return {"link": "https://beispiel.invalid/kamera/v1/#p=x", "ablauf": 1, "code": "ABCD-EFGH"}


class FakeKamera:
    """Verhaelt sich wie HandyKamera (ohne Netz/aiortc)."""

    def __init__(self):
        self.zustand = "wartet"
        self.bild_nr = 0
        self.gestoppt = False

    def start(self):
        return FakeInfo()

    def stop(self):
        self.gestoppt = True

    def latest_frame(self, max_kante=1280, als="pil", qualitaet=80):
        return None if self.bild_nr == 0 else b"\xff\xd8JPEG%d" % self.bild_nr

    def status(self):
        return {"zustand": self.zustand, "fehler": None}


def test_handy_quelle_erfuellt_schnittstelle():
    quelle = HandyQuelle(FakeKamera())
    assert isinstance(quelle, HandyQuellenProtokoll)
    assert quelle.start()["code"] == "ABCD-EFGH"
    assert quelle.status()["zustand"] == "wartet" and not quelle.aktiv()
    assert quelle.latest_frame() is None
    quelle.stop()
    assert quelle.kamera.gestoppt


def test_pumpe_reicht_nur_neue_bilder_weiter():
    fake = FakeKamera()
    quelle = HandyQuelle(fake)
    erhalten = []
    stopp = quelle.pumpe(erhalten.append, intervall=0.02)
    time.sleep(0.1)
    assert erhalten == []  # noch kein Bild
    fake.bild_nr = 1
    time.sleep(0.15)
    assert erhalten == [b"\xff\xd8JPEG1"]  # nur einmal, obwohl mehrfach gefragt
    fake.bild_nr = 2
    time.sleep(0.15)
    stopp()
    anzahl = len(erhalten)
    fake.bild_nr = 3
    time.sleep(0.1)
    assert erhalten[-1] == b"\xff\xd8JPEG2" and len(erhalten) == anzahl == 2


def test_pumpe_ueberlebt_fehler_im_empfaenger():
    fake = FakeKamera()
    fake.bild_nr = 1
    quelle = HandyQuelle(fake)
    aufrufe = []

    def kaputt(daten):
        aufrufe.append(daten)
        raise RuntimeError("Empfaenger kaputt")

    stopp = quelle.pumpe(kaputt, intervall=0.02)
    time.sleep(0.08)
    fake.bild_nr = 2
    time.sleep(0.08)
    quelle.stop()  # beendet auch alle Pumpen
    assert len(aufrufe) == 2
    stopp()


def test_qr_svg_und_text():
    pytest.importorskip("segno")
    link = "https://germanclaude.github.io/Selbst-lernende-KI/kamera/v1/#p=" + "A" * 72
    svg = qr.qr_svg(link)
    assert svg.startswith("<svg") and "nova-qr" in svg and "<?xml" not in svg
    # Ohne xmlns zeigt der Browser das SVG im <img> (data:-URL) nicht an -> leeres Bild im Dialog.
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg.split(">", 1)[0]
    text = qr.qr_text(link)
    assert text and any(z in text for z in ("\u2580", "\u2584", "\u2588"))
    daten = qr.qr_daten(link, "ABCD-EFGH")
    assert daten["svg"] and daten["code"] == "ABCD-EFGH" and daten["link"] == link


def test_qr_ohne_segno(monkeypatch):
    monkeypatch.setattr(qr, "_segno", lambda: None)
    assert qr.qr_svg("x") is None and qr.qr_text("x") is None
    daten = qr.qr_daten("https://x.invalid/#p=1")
    assert daten["svg"] is None and "segno" in daten["hinweis"]


def test_fehlende_pakete_liste():
    fehlt = kamera.fehlende_pakete()
    assert isinstance(fehlt, list) and set(fehlt) <= {"aiortc", "av", "cryptography", "segno"}
