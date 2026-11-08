"""Live-Sehen: Einstellungen, Ereignisse, Buendeln, Weckregel, Maskieren, Quellen-Wahl, Windows-Pruefung."""
import io
import math
import sys
from types import SimpleNamespace

import pytest

from assistant.config import SehenSettings, load_config
from assistant.sehen.einstellungen import HARTE_GRENZE_WECKUNGEN, ist_ausgeschlossen, parse_hotkey, regeln_aus
from assistant.sehen.ereignis import (Buendler, Kontext, Kurzzeit, Wahrnehmung, Weckregel, bewerte, maskiere,
                                      stichworte)
from assistant.sehen.quellen import (BrowserKamera, FakeQuelle, MssQuelle, QuellenFehler, oeffne_bildschirm,
                                     waehle_quellen)
from assistant.sehen.windows import eigene_fenster_schuetzen, kann_aus_aufnahme_ausschliessen, windows_build


# -- Einstellungen --------------------------------------------------------------------------
def test_standard_ist_aus_und_vernuenftig():
    s = SehenSettings()
    assert s.aktiv is False and s.quelle == "auto" and s.bilder_an_ki is True and s.einverstanden_am == ""
    r = regeln_aus(s)
    assert r.fps == 15 and r.max_pro_stunde == 20 and math.isclose(r.max_euro_pro_stunde, 0.30)
    assert r.schwelle == 0.6 and r.bei_abwesenheit is False


def test_unsinnige_werte_werden_begrenzt():
    s = SehenSettings(fps=10000, max_weckungen_pro_stunde=100000, max_euro_pro_stunde=float("nan"),
                      min_abstand_sekunden=-5, quelle="alles", aufnahme="opencv", aufmerksamkeit="panisch",
                      max_kante=99999, bilder_an_ki="ja", ausnahmen="Banking", ocr_sprache="de-DE; rm -rf",
                      max_stunden=float("inf"))
    r = regeln_aus(s)
    assert r.fps == 240
    assert r.max_pro_stunde == HARTE_GRENZE_WECKUNGEN == 360    # harte Grenze, nicht ueberschreibbar
    assert math.isclose(r.max_euro_pro_stunde, 0.30)             # NaN -> Standard
    assert r.min_abstand == 5 and r.quelle == "auto" and r.aufnahme == "auto" and r.schwelle == 0.6
    assert r.max_kante == 1568 and r.bilder_an_ki is True and r.ausnahmen == ["banking"]
    assert r.ocr_sprache == "de-DE" and r.max_stunden == 3.0
    assert regeln_aus(SehenSettings(fps=-3, max_weckungen_pro_stunde=True)).fps == 1


def test_sehen_abschnitt_aus_der_datei(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_text(
        '[sehen]\naktiv = true\nquelle = "webcam"\nausnahmen = ["bank.exe", "Online-Banking"]\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.sehen.aktiv is True and cfg.sehen.quelle == "webcam"
    assert regeln_aus(cfg.sehen).ausnahmen == ["bank.exe", "online-banking"]


def test_beispiel_datei_hat_den_abschnitt():
    import tomllib
    from pathlib import Path

    data = tomllib.loads((Path(__file__).resolve().parents[1] / "config" / "settings.example.toml")
                         .read_text(encoding="utf-8"))
    assert data["sehen"]["aktiv"] is False and data["sehen"]["quelle"] == "auto"
    assert data["sehen"]["bei_abwesenheit"] is False and data["sehen"]["ausnahmen"] == []
    for key in data["sehen"]:
        assert hasattr(SehenSettings(), key), key


def test_ausnahmen_passwortmanager_private_fenster_und_eigene():
    assert ist_ausgeschlossen("C:\\Programme\\KeePass\\KeePass.exe", "Datenbank")
    assert ist_ausgeschlossen("msedge.exe", "Neuer Tab \u2013 [InPrivate] \u2013 Microsoft Edge")
    assert ist_ausgeschlossen("chrome.exe", "Neuer Tab - Google Chrome (Inkognito)")
    assert ist_ausgeschlossen("credentialuibroker.exe", "")
    assert not ist_ausgeschlossen("excel.exe", "Mappe1 - Excel")
    assert ist_ausgeschlossen("meinebank.exe", "Start", ["meinebank.exe"])
    assert ist_ausgeschlossen("firefox.exe", "Sparkasse Online-Banking", ["online-banking"])


def test_pausetaste_lesen():
    assert parse_hotkey("Strg+Alt+Umschalt+S") == (0x2 | 0x1 | 0x4, ord("S"))
    assert parse_hotkey("ctrl+shift+F9") == (0x2 | 0x4, 0x78)
    assert parse_hotkey("S") is None and parse_hotkey("Strg+") is None and parse_hotkey("Strg+A+B") is None
    assert parse_hotkey("Strg+\u00c4") is None


# -- Ereignisse ------------------------------------------------------------------------------
def test_bewertung():
    assert bewerte(Wahrnehmung("dialog", titel="Microsoft Excel", text="Die Datei ist besch\u00e4digt")) == 0.95
    assert bewerte(Wahrnehmung("dialog", titel="Speichern unter")) == 0.8
    assert bewerte(Wahrnehmung("text", text="Traceback (most recent call last)")) == 0.85
    assert bewerte(Wahrnehmung("text", text="Hallo Welt")) == 0.3
    k = Kontext(stichworte=stichworte("Sag Bescheid, wenn der Download fertig ist"))
    assert "download" in k.stichworte and "bescheid" not in k.stichworte
    assert bewerte(Wahrnehmung("text", text="Download abgeschlossen"), k) == 0.65
    k.zuletzt_app["excel.exe"] = 1000.0
    assert bewerte(Wahrnehmung("fenster", app="excel.exe"), k, jetzt=1100.0) == 0.4   # gerade erst gesehen
    assert bewerte(Wahrnehmung("fenster", app="excel.exe"), k, jetzt=3000.0) == 0.6   # lange nicht
    for art in ("privat", "geschuetzt", "pause", "hinweis"):
        assert bewerte(Wahrnehmung(art, text="Fehler!")) == 0.0
    assert bewerte(Wahrnehmung("video", anteil=0.9)) < 0.1
    assert bewerte(Wahrnehmung("text", text="Fehler", privat=True)) == 0.0


def test_zeile_verraet_bei_privaten_fenstern_nichts():
    z = Wahrnehmung("privat", app="keepass.exe", titel="Meine Passw\u00f6rter", privat=True).zeile()
    assert "Passw" not in z and "keepass" not in z.lower()
    assert "Fehler" in Wahrnehmung("dialog", app="x.exe", titel="Fehler", text="Weg").zeile()


def test_maskieren():
    text = ("IBAN DE89 3704 0044 0532 0130 00, Karte 4111 1111 1111 1111, Key sk-ant-api03-abcdefghijklmnop, "
            "Passwort: geheim123, Token ghp_0123456789abcdefghijABCDEFGHIJ, Bestellung 12345")
    m = maskiere(text)
    for geheim in ("3704", "4111 1111", "abcdefghijklmnop", "geheim123", "ghp_"):
        assert geheim not in m, geheim
    assert "Bestellung 12345" in m and "[IBAN verdeckt]" in m


def test_buendeln_entprellen_und_doppelte():
    b = Buendler(schwelle=0.6, doppelt=30, fenster=1.5, fenster_dringend=0.5)
    leise = Wahrnehmung("titel", app="a.exe", titel="x", wichtig=0.3)
    assert b.hinzu(leise, 0.0) and b.faellig(10.0) is None          # unwichtig: kein Buendel
    dialog = Wahrnehmung("dialog", app="a.exe", titel="Hinweis", wichtig=0.8)
    assert b.hinzu(dialog, 1.0)
    assert not b.hinzu(Wahrnehmung("dialog", app="a.exe", titel="Hinweis", wichtig=0.8), 1.2)  # doppelt
    b.hinzu(Wahrnehmung("text", app="a.exe", text="mehr", wichtig=0.3), 1.3)
    assert b.faellig(2.0) is None
    buendel = b.faellig(2.6)
    assert [e.art for e in buendel] == ["dialog", "text"] and b.faellig(5.0) is None
    assert b.hinzu(Wahrnehmung("dialog", app="a.exe", titel="Hinweis", wichtig=0.8), 40.0)  # nach 30 s wieder
    b.verwerfen()
    assert b.faellig(100.0) is None
    b.hinzu(Wahrnehmung("dialog", app="b.exe", text="Fehler", wichtig=0.95), 200.0)
    assert b.faellig(200.4) is None and b.faellig(200.5)              # dringend: 0,5 s


def test_weckregel_abstand_anzahl_euro_und_ruhe_nach_dir():
    r = Weckregel(min_abstand=20, max_pro_stunde=3, max_euro_pro_stunde=0.10, ruhe_nach_nutzer=20)
    assert r.darf(0, 0.6) == (True, "")
    r.gebucht(0)
    assert r.darf(10, 0.6) == (False, "abstand")
    assert r.darf(10, 0.95)[0]                                   # sehr wichtig: nur 5 s Abstand
    r.gebucht(10)
    r.gebucht(40)
    assert r.darf(100, 0.6) == (False, "anzahl")
    assert r.darf(3601, 0.6)[0]                                  # gleitende Stunde
    r.kosten(3601, 0.11)
    assert r.darf(3700, 0.6) == (False, "budget") and r.euro_rest(3700) == 0.0
    assert 3500 < r.wieder_ab(3700) <= 3601
    r.nutzer(7300)
    assert r.darf(7310, 0.95) == (False, "nutzer") and r.darf(7330, 0.95)[0]
    frei = Weckregel(max_pro_stunde=99999, max_euro_pro_stunde=None)
    assert frei.max_pro_stunde == 360 and frei.euro_rest(0) is None
    frei.kosten(0, 50.0)
    assert frei.darf(0, 0.6)[0]                                 # Ollama: Euro spielen keine Rolle


def test_kurzzeit_vergisst_nach_einer_minute():
    k = Kurzzeit(sekunden=60)
    k.hinzu(0, "a")
    k.hinzu(1, "a")
    k.hinzu(30, "b")
    assert k.zeilen(40) == ["a", "b"] and k.zeilen(70) == ["b"]


# -- Quellen -------------------------------------------------------------------------------------
def test_dxcam_wird_nie_beim_laden_importiert():
    import assistant.sehen.auge  # noqa: F401
    import assistant.sehen.dienst  # noqa: F401

    assert "dxcam" not in sys.modules and "mss" not in sys.modules and "comtypes" not in sys.modules


def test_dxcam_fehlt_dann_mss_dann_aus():
    np = pytest.importorskip("numpy")

    class KaputtDx:
        @staticmethod
        def create(**_kw):
            raise OSError("DXGI_ERROR_UNSUPPORTED")

    class FakeMss:
        class mss:
            monitors = [{"left": 0, "top": 0, "width": 40, "height": 30},
                        {"left": -1920, "top": 0, "width": 40, "height": 30}]

            def grab(self, mon):
                return np.zeros((mon["height"], mon["width"], 4), np.uint8)

            def close(self):
                pass

    quelle, grund = oeffne_bildschirm("auto", 0, dxcam_modul=KaputtDx, mss_modul=FakeMss, np_modul=np)
    assert isinstance(quelle, MssQuelle) and "mss" in grund and quelle.ursprung == (-1920, 0)
    assert quelle.bild().shape == (30, 40, 4)

    class KaputtMss:
        @staticmethod
        def mss():
            raise OSError("kein Bildschirm")

    quelle, grund = oeffne_bildschirm("auto", 0, dxcam_modul=KaputtDx, mss_modul=KaputtMss, np_modul=np)
    assert quelle is None and "dxcam" in grund and "mss" in grund
    with pytest.raises(QuellenFehler):
        MssQuelle(0, modul=KaputtMss, np=np)


def test_fake_quelle():
    q = FakeQuelle(["a", "b"], fehler_ab=3)
    assert [q.bild(), q.bild(), q.bild()] == ["a", "b", "b"]
    with pytest.raises(OSError):
        q.bild()


def test_quellen_wahl_auto():
    # Webcam da + Gehirn mit Augen -> Webcam; sonst Bildschirm
    assert waehle_quellen("auto", True, True, True) == ({"webcam"}, "")
    assert waehle_quellen("auto", True, True, False) == ({"bildschirm"}, "")
    assert waehle_quellen("auto", False, True, True) == ({"bildschirm"}, "")
    assert waehle_quellen("auto", True, False, False) == ({"webcam"}, "")      # kein Windows: Webcam
    assert waehle_quellen("auto", False, False, True)[0] == set()
    assert waehle_quellen("beides", True, True, True) == ({"bildschirm", "webcam"}, "")
    quellen, hinweis = waehle_quellen("beides", False, True, True)
    assert quellen == {"bildschirm"} and hinweis
    assert waehle_quellen("webcam", False, True, True)[0] == set()
    quellen, hinweis = waehle_quellen("webcam", True, True, False)
    assert quellen == {"webcam"} and "Augen" in hinweis
    assert waehle_quellen("bildschirm", True, False, True)[0] == set()


def _jpeg(farbe, groesse=(64, 48)):
    Image = pytest.importorskip("PIL.Image")
    puffer = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(puffer, "JPEG")
    return puffer.getvalue()


def test_webcam_meldet_veraenderung_erst_nach_ruhe():
    jetzt = [0.0]
    kamera = BrowserKamera(uhr=lambda: jetzt[0], ruhe=2.0)
    dunkel, hell = _jpeg((10, 10, 10)), _jpeg((220, 220, 220))
    for t in range(4):
        jetzt[0] = t
        assert kamera.nimm(dunkel) is None
    jetzt[0] = 4.0
    assert kamera.nimm(hell) is None                         # bewegt sich noch
    ereignisse = []
    for t in (5.0, 6.0, 7.0, 8.0):
        jetzt[0] = t
        ereignisse.append(kamera.nimm(hell))
    treffer = [e for e in ereignisse if e]
    assert len(treffer) == 1 and treffer[0]["art"] == "bewegung" and treffer[0]["quelle"] == "webcam"
    assert kamera.letztes() == hell and kamera.aktiv()
    jetzt[0] = 100.0
    assert kamera.letztes() is None                          # zu alt = Kamera aus
    kamera.vergessen()
    assert kamera.nimm(b"kein bild") is None


# -- Windows-Version ---------------------------------------------------------------------------------
def test_eigenes_fenster_nur_ab_windows_2004():
    assert windows_build(lambda: SimpleNamespace(build=19041), plattform="win32") == 19041
    assert windows_build(lambda: SimpleNamespace(build=19041), plattform="linux") is None
    assert kann_aus_aufnahme_ausschliessen(19041) and kann_aus_aufnahme_ausschliessen(22631)
    assert not kann_aus_aufnahme_ausschliessen(18363) and not kann_aus_aufnahme_ausschliessen(None)
    gesetzt = []

    class User32:
        def SetWindowDisplayAffinity(self, hwnd, wert):  # noqa: N802
            gesetzt.append((hwnd, wert))

    hinweis = eigene_fenster_schuetzen(True, build=18363, user32=User32())
    assert "2004" in hinweis and gesetzt == []                # altes Windows: nichts setzen, nur Hinweis
    assert eigene_fenster_schuetzen(False, build=18363, user32=User32()) == ""


def test_kamera_nur_fuer_eigene_seite():
    from assistant.app.launcher import kamera_entscheidung, kamera_herkunft_ok

    assert kamera_herkunft_ok("http://127.0.0.1:5123/?t=x", 5123)
    assert kamera_herkunft_ok("http://localhost:5123/", 5123)
    assert not kamera_herkunft_ok("http://127.0.0.1:5124/", 5123)
    assert not kamera_herkunft_ok("https://127.0.0.1:5123/", 5123)
    assert not kamera_herkunft_ok("http://evil.example:5123/", 5123)
    assert not kamera_herkunft_ok("http://user:pw@127.0.0.1:5123/", 5123)
    assert kamera_entscheidung("Camera", "http://127.0.0.1:5123/", 5123, True) == "erlauben"
    assert kamera_entscheidung("Camera", "http://127.0.0.1:5123/", 5123, False) == "ablehnen"
    assert kamera_entscheidung("Camera", "http://evil.example/", 5123, True) == "ablehnen"
    assert kamera_entscheidung("Microphone", "http://127.0.0.1:5123/", 5123, True) is None  # Standard bleibt
    assert kamera_entscheidung("Geolocation", "http://127.0.0.1:5123/", 5123, True) is None


def test_wortmeldung_kennzeichnen_aendert_die_anfrage_nicht():
    import json
    from types import SimpleNamespace as NS

    from assistant.providers.base import LLMProvider, Wortmeldung

    p = NS(messages=[{"role": "user", "content": "hallo"}, {"role": "assistant", "content": [{"type": "text",
                                                                                           "text": "hi"}]}],
           _bild_turn=(1, "x"))
    vorher = json.dumps(p.messages)
    assert LLMProvider.als_wortmeldung(p, 1) == 1
    assert json.dumps(p.messages) == vorher                 # byte-gleich fuer die API (append-only)
    assert not isinstance(p.messages[0], Wortmeldung) and isinstance(p.messages[1], Wortmeldung)
    assert LLMProvider.als_wortmeldung(p, 1) == 0 and p._bild_turn is None


def test_deepseek_zaehlt_und_fasst_wortmeldungen_nicht_zusammen():
    from assistant.providers.base import Wortmeldung
    from assistant.providers.deepseek_provider import _history_as_text

    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "Hallo"},
            Wortmeldung({"role": "user", "content": "Bildschirm: Kontostand"}),
            Wortmeldung({"role": "assistant", "content": "Ich sehe den Kontostand"})]
    text = _history_as_text(msgs)
    assert "Hallo" in text and "Kontostand" not in text


def test_eigenes_fenster_nur_unsichtbar_wenn_windows_es_bestaetigt():
    class User32:
        def __init__(self, ok):
            self.ok, self.gesetzt = ok, []

        def EnumWindows(self, proc, _l):  # noqa: N802
            proc(11, 0)
            proc(12, 0)

        def GetWindowThreadProcessId(self, hwnd, zeiger):  # noqa: N802
            zeiger._obj.value = 42 if hwnd == 11 else 7

        def IsWindowVisible(self, hwnd):  # noqa: N802
            return True

        def SetWindowDisplayAffinity(self, hwnd, wert):  # noqa: N802
            self.gesetzt.append((hwnd, wert))
            return self.ok

    for ok, erwartet in ((1, True), (0, False)):
        ergebnis, u = {}, User32(ok)
        assert eigene_fenster_schuetzen(True, build=22631, user32=u, pid=42, ergebnis=ergebnis) == ""
        assert u.gesetzt == [(11, 0x11)] and ergebnis["unsichtbar"] is erwartet
    ergebnis = {}
    eigene_fenster_schuetzen(True, build=22631, user32=User32(1), pid=999, ergebnis=ergebnis)
    assert ergebnis["unsichtbar"] is False                 # kein eigenes Fenster (Terminal, Browser)
    eigene_fenster_schuetzen(True, build=18363, user32=User32(1), pid=42, ergebnis=ergebnis)
    assert ergebnis["unsichtbar"] is False                 # altes Windows


def test_kurzzeit_verkraftet_gleichzeitiges_anhaengen():
    import threading

    k = Kurzzeit(sekunden=1e9, max_zeilen=50)
    stopp = threading.Event()

    def schreiben():
        i = 0
        while not stopp.is_set():
            k.hinzu(float(i), f"zeile {i}")
            i += 1

    t = threading.Thread(target=schreiben)
    t.start()
    try:
        for _ in range(3000):
            k.zeilen(0.0)
    finally:
        stopp.set()
        t.join()
