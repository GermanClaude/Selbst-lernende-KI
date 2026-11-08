"""Live-Sehen im Hauptprogramm (SehDienst): Zustimmung, Wecken, Budget, AFK, Webcam, Datenschutz."""
import io
import logging

import pytest

from assistant.config import load_config
from assistant.sehen.dienst import SehDienst, StillFilter, ist_still


class Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _jpeg(farbe=(200, 30, 30), groesse=(64, 48)):
    Image = pytest.importorskip("PIL.Image")
    puffer = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(puffer, "JPEG")
    return puffer.getvalue()


class FakeAuge:
    def __init__(self, einst, jpeg=None, grund=""):
        self.einst = einst
        self.befehle = []
        self.antworten = []
        self.gestartet = self.gestoppt = False
        self.jpeg, self.grund = jpeg, grund

    def start(self):
        self.gestartet = True

    def senden(self, befehl):
        self.befehle.append(befehl)
        if befehl[0] == "bild":
            self.antworten.append(("bild", befehl[1], self.jpeg, self.grund))

    def lies(self, timeout=0.1):
        return self.antworten.pop(0) if self.antworten else None

    def lebt(self):
        return self.gestartet and not self.gestoppt

    def stop(self, warten=2.0):
        self.gestoppt = True


@pytest.fixture
def dienst(tmp_path):
    def make(sieht=True, kostenlos=False, jpeg=b"", zustimmung=True, **einst):
        cfg = load_config(tmp_path)
        for k, v in einst.items():
            setattr(cfg.sehen, k, v)
        notizen, pakete, schutz, gespeichert, augen = [], [], [], {}, []

        def fabrik(e):
            auge = FakeAuge(e, jpeg=jpeg if jpeg != b"" else _jpeg())
            augen.append(auge)
            return auge

        frei = {"kostenlos": kostenlos}
        halte = []
        d = SehDienst(cfg, on_notiz=notizen.append, wecken=pakete.append, sieht_bilder=lambda: sieht,
                      kostenlos=lambda: frei["kostenlos"], auge_fabrik=fabrik, bildschirm_moeglich=True,
                      fenster_schutz=lambda an: schutz.append(an) or "", uhr=Uhr(),
                      speichern=lambda k, v: gespeichert.__setitem__(k, v), mit_thread=False,
                      on_halt=lambda: halte.append(1))
        if zustimmung:
            d.zustimmen()
        d.t = (notizen, pakete, schutz, gespeichert, augen)
        d.frei, d.halte = frei, halte
        return d
    return make


def _fehlerfenster(d, text="Die Datei ist besch\u00e4digt und kann nicht ge\u00f6ffnet werden."):
    d.verarbeite({"art": "dialog", "quelle": "fenster", "app": "excel.exe", "titel": "Microsoft Excel", "text": text})


def _warten(d, sekunden):
    d.uhr.t += sekunden
    d.tick()


def test_ohne_zustimmung_schaut_nova_nicht_hin(dienst):
    d = dienst(zustimmung=False)
    assert d.braucht_zustimmung()
    assert d.an() == (False, "zustimmung") and not d.aktiv and d.t[4] == []
    assert "Live-Sehen einschalten?" in d.warnung() and "Passwortfelder" in d.warnung()
    d.zustimmen()
    assert set(d.t[3]) == {"einverstanden_am", "einverstanden_fuer"} and not d.braucht_zustimmung()
    d.config.sehen.einverstanden_fuer = "ein-anderes-gehirn"
    assert d.braucht_zustimmung()                       # anderes Gehirn = neu fragen


def test_an_und_aus(dienst):
    d = dienst()
    ok, text = d.an("bildschirm")
    assert ok and "Bildschirm" in text and "Strg+Alt+Umschalt+S" in text
    assert d.quellen == {"bildschirm"} and d.t[2] == [True]
    auge = d.t[4][0]
    assert auge.gestartet and auge.einst["eigene_titel"] == ["(sieht zu)"] and auge.einst["eigene_pid"] > 0
    assert d.status()["aktiv"] and d.status()["technik"] == ""
    assert "aus" in d.aus()
    assert auge.gestoppt and d.t[2] == [True, False] and not d.aktiv and d.quellen == set()
    assert d.aus() == "Live-Sehen ist schon aus."


def test_fehlerfenster_weckt_nova_mit_text_und_bild(dienst):
    d = dienst(sieht=True)
    d.an("bildschirm")
    d.verarbeite({"art": "fenster", "app": "excel.exe", "titel": "Mappe1"})
    _fehlerfenster(d)
    _warten(d, 0.2)
    assert d.t[1] == []                                   # Sammelfenster (0,5 s) noch offen
    _warten(d, 0.5)
    (paket,) = d.t[1]
    assert "Gerade passiert:" in paket.text and "besch\u00e4digt" in paket.text
    assert "NICHT vertrauenswuerdig" in paket.text and "[still]" in paket.text
    assert "Mappe1" in paket.text                         # die letzte Minute als Zusammenhang
    assert len(paket.bilder) == 1 and paket.bilder[0].mime == "image/jpeg" and paket.wichtig == 0.95
    assert paket.anzeige.startswith(d.config.ki.name + " hat etwas bemerkt")
    assert ("bild", 1) in d.t[4][0].befehle
    assert d.status()["weckungen_stunde"] == 1


def test_ohne_augen_nur_text(dienst):
    d = dienst(sieht=False)
    d.an("bildschirm")
    _fehlerfenster(d)
    _warten(d, 1.0)
    (paket,) = d.t[1]
    assert paket.bilder == [] and not any(b[0] == "bild" for b in d.t[4][0].befehle)


def test_bilder_an_ki_aus_heisst_nie_ein_bild(dienst):
    d = dienst(bilder_an_ki=False)
    d.an("bildschirm")
    _fehlerfenster(d)
    _warten(d, 1.0)
    assert d.t[1][0].bilder == []


def test_privates_fenster_weckt_nie_und_gibt_kein_bild(dienst):
    d = dienst()
    d.an("bildschirm")
    d.verarbeite({"art": "privat", "app": "keepass.exe", "privat": True})
    _warten(d, 2.0)
    assert d.t[1] == [] and d.status()["privat"]
    assert d.aktuelles_bild()[0] is None


def test_unwichtiges_weckt_nicht(dienst):
    d = dienst()
    d.an("bildschirm")
    for i in range(5):
        d.verarbeite({"art": "inhalt", "anteil": 0.05})
        d.verarbeite({"art": "titel", "app": "chrome.exe", "titel": f"Seite {i}"})
        _warten(d, 2.0)
    assert d.t[1] == [] and d.ereignisse == 10


def test_budget_pro_stunde_und_hinweis_nur_einmal(dienst):
    d = dienst(max_weckungen_pro_stunde=1)
    d.an("bildschirm")
    _fehlerfenster(d, "Fehler 1")
    _warten(d, 1.0)
    for i in range(3):
        _warten(d, 60)
        _fehlerfenster(d, f"Fehler {i + 2}")
        _warten(d, 1.0)
    assert len(d.t[1]) == 1
    assert sum("oft genug" in n for n in d.t[0]) == 1
    _warten(d, 3600)
    _fehlerfenster(d, "Fehler neu")
    _warten(d, 1.0)
    assert len(d.t[1]) == 2


def test_euro_grenze_pro_stunde_und_ollama_kostenlos(dienst):
    d = dienst(max_euro_pro_stunde=0.05)
    d.an("bildschirm")
    _fehlerfenster(d, "A")
    _warten(d, 2.0)
    d.gebucht(0.06)
    _warten(d, 60)
    _fehlerfenster(d, "B")
    _warten(d, 2.0)
    assert len(d.t[1]) == 1 and any("Budget" in n for n in d.t[0]) and d.euro_rest() == 0.0
    frei = dienst(kostenlos=True, max_euro_pro_stunde=0.01)
    frei.an("bildschirm")
    frei.gebucht(5.0)
    _fehlerfenster(frei)
    _warten(frei, 1.0)
    assert len(frei.t[1]) == 1 and frei.status()["max_eur"] is None and frei.euro_rest() is None


def test_nach_deiner_nachricht_haelt_sich_nova_zurueck(dienst):
    d = dienst()
    d.an("bildschirm")
    _fehlerfenster(d)
    d.nutzer_aktiv("Bitte sag Bescheid, wenn der Download fertig ist")
    _warten(d, 1.0)
    assert d.t[1] == []                                   # angefangenes Buendel verworfen
    _fehlerfenster(d, "anderer Fehler")
    _warten(d, 1.0)
    assert d.t[1] == []                                   # 20 s Ruhe nach deiner Nachricht
    _warten(d, 20)
    d.verarbeite({"art": "text", "quelle": "ocr", "app": "chrome.exe", "text": "Download abgeschlossen"})
    _warten(d, 2.0)
    assert len(d.t[1]) == 1 and "Download" in d.t[1][0].text    # dein Stichwort


def test_afk_ohne_erlaubnis_schaut_nicht_hin(dienst):
    d = dienst()
    d.an("bildschirm")
    d.setze_abwesend(True)
    assert ("pause",) in d.t[4][0].befehle and d.status()["abwesend"]
    _fehlerfenster(d)
    _warten(d, 2.0)
    assert d.t[1] == [] and d.aktuelles_bild()[0] is None
    d.setze_abwesend(False)
    assert d.t[4][0].befehle[-1] == ("weiter",)


def test_afk_mit_erlaubnis_nur_text_fuer_den_naechsten_schritt(dienst):
    d = dienst(bei_abwesenheit=True)
    d.an("bildschirm")
    d.setze_abwesend(True)
    _fehlerfenster(d)
    _warten(d, 1.0)
    (paket,) = d.t[1]
    assert paket.abwesend and paket.bilder == [] and paket.text == ""
    vorspann = d.afk_zeilen_nehmen()
    assert "besch\u00e4digt" in vorspann and "nicht vertrauenswuerdig" in vorspann
    assert d.afk_zeilen_nehmen() == ""


def test_schaltet_sich_nach_max_stunden_ab(dienst):
    d = dienst(max_stunden=1)
    d.an("bildschirm")
    _warten(d, 3601)
    assert not d.aktiv and any("1 Stunden" in n for n in d.t[0]) and d.t[4][0].gestoppt


def test_pause_und_weiter(dienst):
    d = dienst()
    d.an("bildschirm")
    assert "nicht hin" in d.pause() and d.status()["pausiert"] and ("pause",) in d.t[4][0].befehle
    _fehlerfenster(d)
    _warten(d, 2.0)
    assert d.t[1] == []
    d.weiter()
    assert not d.pausiert and d.t[4][0].befehle[-1] == ("weiter",)
    d.verarbeite({"art": "pause", "quelle": "taste"})        # Pause-Taste im Auge
    assert d.pausiert


def test_auge_stirbt_neustart_dann_aufgeben(dienst):
    d = dienst()
    d.an("bildschirm")
    for _ in range(3):
        d._nachricht(("ende", "Fehler im Auge (OSError)"))
        assert d.aktiv and d._auge is not None
    d._nachricht(("ende", "Fehler im Auge (OSError)"))
    assert not d.aktiv and any("nicht sehen" in n for n in d.t[0]) and len(d.t[4]) == 4
    d2 = dienst()
    d2.an("bildschirm")
    d2._nachricht(("ende", "Bildschirm-Sehen gibt es nur unter Windows."))
    assert not d2.aktiv and len(d2.t[4]) == 1               # unmoeglich: nicht neu starten


def test_bereit_meldung_zeigt_hinweise_und_belegte_taste(dienst):
    d = dienst()
    d.an("bildschirm")
    d._nachricht(("bereit", {"quelle": "dxcam", "ocr": True, "passwortschutz": True, "taste": False,
                             "hinweise": ["Die deutsche Texterkennung von Windows fehlt."]}))
    assert d.status()["technik"] == "dxcam" and d.status()["ocr"]
    assert any("Texterkennung" in n for n in d.t[0]) and any("belegt" in n for n in d.t[0])


def test_webcam_auto_wenn_da_und_gehirn_sieht(dienst):
    d = dienst(sieht=True)
    assert d.kamera_bild(_jpeg()) == (False, "Live-Sehen mit Webcam ist aus.")
    d.kamera_meldung(vorhanden=True)
    ok, _text = d.an()
    assert ok and d.quellen == {"webcam"} and d.t[4] == []    # kein Auge fuer den Bildschirm
    assert d.kamera_erlaubt() and d.status()["kamera_gewuenscht"]
    dunkel, hell = _jpeg((10, 10, 10)), _jpeg((230, 230, 230))
    for _ in range(6):
        d.uhr.t += 1.0
        assert d.kamera_bild(dunkel) == (True, "")
    for _ in range(10):
        d.uhr.t += 1.0
        d.kamera_bild(hell)
        d.tick()
    (paket,) = d.t[1]
    assert paket.quelle == "webcam" and paket.bilder and paket.bilder[0].name == "webcam.jpg"
    assert "Webcam" in paket.text
    d.aus()
    assert d.kamera.letztes() is None and not d.kamera_erlaubt()


def test_webcam_fehler_schaltet_sie_ab(dienst):
    d = dienst(sieht=True)
    d.kamera_meldung(vorhanden=True)
    d.an("webcam")
    d.kamera_meldung(fehler="Die Webcam ist blockiert.")
    assert not d.aktiv and any("blockiert" in n for n in d.t[0])


def test_aktuelles_bild_fuer_das_werkzeug(dienst):
    d = dienst()
    assert d.aktuelles_bild() == (None, "Live-Sehen ist aus.")
    d.an("bildschirm")
    bild, grund = d.aktuelles_bild()
    assert bild is not None and grund == "" and bild.name == "bildschirm.jpg"
    d2 = dienst(jpeg=None)
    d2.an("bildschirm")
    d2.t[4][0].grund = "passwort"
    assert "Passwortfeld" in d2.aktuelles_bild()[1]


def test_nichts_landet_auf_der_festplatte_und_nichts_im_protokoll(dienst, tmp_path, caplog):
    vorher = {p for p in tmp_path.rglob("*")}
    d = dienst()
    vorher = {p for p in tmp_path.rglob("*")}
    caplog.set_level(logging.DEBUG)
    d.an("bildschirm")
    _fehlerfenster(d, "Geheimer Kontostand 12.345 Euro")
    _warten(d, 1.0)
    d.aktuelles_bild()
    d.aus()
    assert {p for p in tmp_path.rglob("*")} == vorher
    assert "Kontostand" not in caplog.text


def test_still_filter():
    raus = []
    f = StillFilter(raus.append)
    for teil in ["  [st", "ill]"]:
        f(teil)
    assert f.ende() and raus == []
    raus.clear()
    f = StillFilter(raus.append)
    for teil in ["Da ", "ist ein Fehlerfenster."]:
        f(teil)
    assert not f.ende() and "".join(raus) == "Da ist ein Fehlerfenster."
    raus.clear()
    f = StillFilter(raus.append)
    f("[")
    assert not f.ende() and raus == ["["]
    assert ist_still(" [STILL]") and not ist_still("Alles still hier")


# -- Pruefbefunde: Gehirn-Wechsel, Pause, Sperren, Abgleich mit dem Auge -----------------------------
def test_gehirn_wechsel_schaltet_aus_und_fragt_neu(dienst):
    d = dienst()
    d.an("bildschirm")
    assert d.darf_melden()
    d.config.sehen.einverstanden_fuer = "anderes-gehirn"     # Zustimmung galt dem alten Gehirn
    assert not d.darf_melden()
    d.tick()
    assert not d.aktiv and any("Gehirn gewechselt" in n for n in d.t[0]) and d.halte
    assert d.aktuelles_bild()[0] is None and d.an() == (False, "zustimmung")
    d2 = dienst()
    assert d2.gehirn_gewechselt() is False                  # aus: nichts zu tun


def test_euro_grenze_gilt_auch_nach_dem_wechsel_von_ollama(dienst):
    d = dienst(kostenlos=True, max_euro_pro_stunde=0.05)
    d.an("bildschirm")
    assert d.euro_rest() is None
    d.frei["kostenlos"] = False                             # jetzt ein Gehirn, das Geld kostet
    d.gebucht(0.10)
    _fehlerfenster(d)
    _warten(d, 2.0)
    assert d.t[1] == [] and d.euro_rest() == 0.0 and any("Budget" in n for n in d.t[0])


def test_pause_aus_und_afk_verwerfen_geplante_wortmeldungen(dienst):
    d = dienst()
    d.an("bildschirm")
    d.pause()
    assert len(d.halte) == 1 and not d.darf_melden()
    d.weiter()
    assert d.darf_melden()
    d.setze_abwesend(True)
    assert len(d.halte) == 2 and not d.darf_melden()
    d.setze_abwesend(False)
    d.aus()
    assert len(d.halte) == 3


def test_pausetaste_verwirft_und_das_hauptprogramm_entscheidet(dienst):
    import time as _t

    d = dienst()
    d.an("bildschirm")
    auge = d.t[4][0]
    d.verarbeite({"art": "pause", "quelle": "taste"})
    for _ in range(50):
        if d.halte:
            break
        _t.sleep(0.01)
    assert d.pausiert and d.halte and auge.befehle[-1] == ("pause",)
    d.setze_abwesend(True)
    d.verarbeite({"art": "weiter", "quelle": "taste"})       # Bitte "wieder hinschauen" waehrend AFK
    assert auge.befehle[-1] == ("pause",)                    # bleibt weg, solange du AFK bist
    d.setze_abwesend(False)
    assert auge.befehle[-1] == ("weiter",)


def test_neustart_des_auges_behaelt_die_pause(dienst):
    d = dienst()
    d.an("bildschirm")
    d.pause()
    d._nachricht(("ende", "Fehler im Auge (OSError)"))
    assert len(d.t[4]) == 2 and d.t[4][1].befehle[0] == ("pause",)


def test_paket_wird_ausserhalb_der_sperre_gebaut_und_pause_wirkt_noch(dienst):
    import threading as _th

    d = dienst(sieht=True)
    d.an("bildschirm")
    auge = d.t[4][0]
    echt = auge.lies
    frei = []

    def lies(timeout=0.1):
        # waehrend auf das Bildschirmfoto gewartet wird: Sperre frei? Und du drueckst Pause.
        t = _th.Thread(target=lambda: frei.append(d._lock.acquire(timeout=0.5) and (d._lock.release() or True)))
        t.start()
        t.join()
        d.pause()
        return echt(timeout)

    auge.lies = lies
    _fehlerfenster(d)
    _warten(d, 1.0)
    assert frei == [True] and d.t[1] == []                   # Pause kam dazwischen: keine Wortmeldung


def test_eigenes_fenster_unsichtbar_geht_ans_auge_und_eigen_hat_einen_text(dienst):
    d = dienst()
    sichtbar = {"wert": False}
    d.eigenes_unsichtbar = lambda: sichtbar["wert"]
    d.an("bildschirm")
    auge = d.t[4][0]
    assert auge.einst["eigenes_unsichtbar"] is False
    sichtbar["wert"] = True
    d.eigenes_fenster_neu()
    assert auge.befehle[-1] == ("eigenes_unsichtbar", True)
    auge.jpeg, auge.grund = None, "eigen"
    bild, text = d.aktuelles_bild()
    assert bild is None and "eigenes Fenster" in text
