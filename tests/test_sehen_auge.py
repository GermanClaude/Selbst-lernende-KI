"""Live-Sehen: Aenderungserkennung und das "Auge" (mit Ersatzteilen - kein echter Bildschirm noetig)."""
import queue
import time

import pytest

np = pytest.importorskip("numpy")

from assistant.sehen.auge import (Auge, AugenTeile, AugeVerbindung, _fake_teile, als_jpeg,  # noqa: E402
                                  hauptschleife, senden)
from assistant.sehen.differenz import Differenz  # noqa: E402
from assistant.sehen.ocr import FakeOcr  # noqa: E402
from assistant.sehen.quellen import FakeQuelle  # noqa: E402
from assistant.sehen.uia import OK, PASSWORT, FakePruefer  # noqa: E402

H, W = 180, 320


def _leer():
    return np.zeros((H, W, 4), np.uint8)


def _mit_fenster(x0=60, y0=40, x1=260, y1=120, wert=255):
    bild = _leer()
    bild[y0:y1, x0:x1] = wert
    return bild


# -- Differenz ---------------------------------------------------------------------------------
def test_geaenderter_bereich_wird_gefunden_wenn_es_ruhig_ist():
    d = Differenz(ruhe=0.4)
    assert d.vergleiche(_leer(), 0.0) is None
    neu = _mit_fenster()
    ergebnisse = [d.vergleiche(neu, 0.1 * i) for i in range(1, 12)]
    treffer = [e for e in ergebnisse if e]
    assert len(treffer) == 1
    a = treffer[0]
    assert a.art == "inhalt" and not a.unruhig and 0.2 < a.anteil < 0.4
    x, y, b, h = a.bereich
    assert x <= 60 and y <= 40 and x + b >= 260 and y + h >= 120   # umfasst das neue Fenster
    assert ergebnisse.index(a) >= 3                                 # erst nach 0,4 s Ruhe


def test_blinkender_cursor_und_uhr_werden_ignoriert():
    d = Differenz()
    leer = np.zeros((720, 1280, 4), np.uint8)
    d.vergleiche(leer, 0.0)
    for i in range(1, 40):
        bild = leer.copy()
        if i % 2:
            bild[300:318, 400:402] = 255   # Cursor
        bild[0:12, 1200:1260] = (i * 7) % 255  # Uhr
        assert d.vergleiche(bild, i * 0.1) is None


def test_video_wird_einmal_gemeldet_und_dann_still():
    d = Differenz(video_dauer=1.0)
    d.vergleiche(_leer(), 0.0)
    rng = np.random.default_rng(1)
    meldungen = []
    for i in range(1, 40):
        bild = rng.integers(0, 255, (H, W, 4), dtype=np.uint8)
        r = d.vergleiche(bild, i * 0.1)
        if r:
            meldungen.append(r.art)
    assert meldungen == ["video"]


def test_dauernde_bewegung_wird_spaetestens_nach_max_warten_gemeldet():
    d = Differenz(ruhe=0.4, max_warten=1.0, video_anteil=0.9)
    d.vergleiche(_leer(), 0.0)
    treffer = None
    for i in range(1, 30):
        bild = _mit_fenster()
        bild[150:160, (i * 7) % 300:(i * 7) % 300 + 10] = 128  # etwas bewegt sich staendig
        treffer = d.vergleiche(bild, i * 0.1)
        if treffer:
            break
    assert treffer is not None and treffer.unruhig and i <= 12


def test_schnell_genug_fuer_jedes_bild():
    d = Differenz()
    a = np.zeros((1080, 1920, 4), np.uint8)
    b = a.copy()
    b[300:520, 640:1160] = 255
    d.vergleiche(a, 0)
    start = time.perf_counter()
    for i in range(50):
        d.vergleiche(b if i % 2 else a, i * 0.01)
    assert (time.perf_counter() - start) / 50 < 0.02   # grosszuegig (CI), gemessen ~1 ms


def test_jpeg_ist_verkleinert():
    pytest.importorskip("PIL")
    jpeg = als_jpeg(np.zeros((1000, 2000, 4), np.uint8), max_kante=500)
    from PIL import Image
    import io

    assert jpeg[:3] == b"\xff\xd8\xff" and Image.open(io.BytesIO(jpeg)).size == (500, 250)


# -- Auge mit Ersatzteilen -----------------------------------------------------------------------
class Uhr:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def schlafe(self, s):
        self.t += max(s, 0.01)


def _auge(vorne=None, passwort=OK, ocr_text="Fehler: Datei fehlt", frames=None, **einst):
    uhr = Uhr()
    ocr = FakeOcr(ocr_text)
    vorne = vorne or {"hwnd": 1, "pid": 4242, "exe": "notepad.exe", "titel": "Editor", "klasse": "Notepad",
                      "rechteck": (0, 0, W, H)}
    zustand = {"vorne": vorne}
    teile = AugenTeile(quelle=FakeQuelle(frames or ([_leer()] * 3 + [_mit_fenster()] * 200)),
                       vordergrund=lambda: zustand["vorne"], passwort=FakePruefer(passwort) if passwort else None,
                       ocr=ocr, uhr=uhr, schlafe=uhr.schlafe)
    befehle, ausgang = queue.Queue(), queue.Queue(maxsize=200)
    auge = Auge(befehle, ausgang, {"fps": 20, "eigene_pid": 99, **einst}, teile)
    return auge, befehle, ausgang, ocr, zustand


def _laufen(auge, befehle, schritte=None, sekunden=3.0):
    """Schleife laufen lassen, bis die (gefaelschte) Zeit um ist."""
    alt = auge.t.schlafe

    def schlafe(s):
        alt(s)
        if auge.uhr() >= sekunden:
            befehle.put(("stop",))

    auge.t.schlafe = schlafe
    return auge.lauf()


def _meldungen(ausgang):
    out = []
    while True:
        try:
            out.append(ausgang.get_nowait())
        except queue.Empty:
            return out


def test_auge_meldet_fenster_und_gelesenen_text():
    auge, befehle, ausgang, ocr, _z = _auge()
    assert _laufen(auge, befehle) == "stop"
    m = _meldungen(ausgang)
    assert m[0][0] == "bereit" and m[0][1]["passwortschutz"] is True
    arten = [x[1]["art"] for x in m if x[0] == "ereignis"]
    assert arten[0] == "fenster" and "text" in arten
    text = next(x[1] for x in m if x[0] == "ereignis" and x[1]["art"] == "text")
    assert text["text"] == "Fehler: Datei fehlt" and text["app"] == "notepad.exe" and ocr.aufrufe == 1
    assert m[-1] != ("ende",) and auge.bild is None                 # nichts im Speicher behalten


def test_privates_fenster_nie_lesen_und_kein_bild():
    vorne = {"hwnd": 2, "pid": 1, "exe": "keepass.exe", "titel": "Geheim", "klasse": "X", "rechteck": (0, 0, W, H)}
    auge, befehle, ausgang, ocr, _z = _auge(vorne=vorne)
    befehle.put(("bild", 5))
    _laufen(auge, befehle)
    m = _meldungen(ausgang)
    ereignisse = [x[1] for x in m if x[0] == "ereignis"]
    assert [e["art"] for e in ereignisse] == ["privat"] and ereignisse[0]["privat"] is True
    assert "Geheim" not in str(ereignisse)
    assert ocr.aufrufe == 0
    assert ("bild", 5, None, "privat") in m


def test_eigenes_fenster_wird_still_uebergangen():
    vorne = {"hwnd": 3, "pid": 99, "exe": "ki-app.exe", "titel": "Nova", "klasse": "X", "rechteck": (0, 0, W, H)}
    auge, befehle, ausgang, ocr, _z = _auge(vorne=vorne)
    _laufen(auge, befehle)
    assert [x for x in _meldungen(ausgang) if x[0] == "ereignis"] == [] and ocr.aufrufe == 0


def test_eigener_titel_wird_still_uebergangen():
    vorne = {"hwnd": 3, "pid": 5, "exe": "msedge.exe", "titel": "Nova (sieht zu)", "klasse": "X",
             "rechteck": (0, 0, W, H)}
    auge, befehle, ausgang, ocr, _z = _auge(vorne=vorne, eigene_titel=["(sieht zu)"])
    _laufen(auge, befehle)
    assert [x for x in _meldungen(ausgang) if x[0] == "ereignis"] == [] and ocr.aufrufe == 0


def test_passwortfeld_kein_text_kein_bild():
    auge, befehle, ausgang, ocr, _z = _auge(passwort=PASSWORT)
    befehle.put(("bild", 1))
    _laufen(auge, befehle)
    m = _meldungen(ausgang)
    arten = [x[1]["art"] for x in m if x[0] == "ereignis"]
    assert "geschuetzt" in arten and "text" not in arten and ocr.aufrufe == 0
    assert ("bild", 1, None, "passwort") in m


def test_ohne_passwortschutz_wird_nichts_gelesen_und_kein_bild_gegeben():
    auge, befehle, ausgang, ocr, _z = _auge(passwort=None)
    _laufen(auge, befehle, sekunden=2.0)
    assert auge.schnappschuss() == (None, "unbekannt")
    m = _meldungen(ausgang)
    assert m[0][1]["passwortschutz"] is False and any("Passwortfeld" in h for h in m[0][1]["hinweise"])
    assert ocr.aufrufe == 0 and "text" not in [x[1]["art"] for x in m if x[0] == "ereignis"]


def test_schnappschuss_nur_vom_vorderen_fenster():
    pytest.importorskip("PIL")
    from PIL import Image
    import io

    vorne = {"hwnd": 1, "pid": 7, "exe": "excel.exe", "titel": "Mappe", "klasse": "X", "rechteck": (60, 40, 200, 80)}
    auge, befehle, ausgang, _ocr, _z = _auge(vorne=vorne, max_kante=1280)
    auge.vorne, auge.bild = vorne, _mit_fenster()
    jpeg, grund = auge.schnappschuss()
    assert grund == "" and Image.open(io.BytesIO(jpeg)).size == (200, 80)   # nur das Fenster, nicht alles
    auge.pause = True
    assert auge.schnappschuss() == (None, "pause")
    auge2 = _auge(frames=[_leer()], bilder=False)[0]
    auge2.vorne, auge2.bild = vorne, _mit_fenster()
    assert auge2.schnappschuss() == (None, "aus")


def test_titelwechsel_dialog_und_pausetaste():
    auge, befehle, ausgang, ocr, zustand = _auge(frames=[_leer()])
    auge._vorne_pruefen()
    zustand["vorne"] = dict(zustand["vorne"], titel="Fehler beim Speichern")
    auge._vorne_pruefen()
    zustand["vorne"] = {"hwnd": 8, "pid": 5, "exe": "excel.exe", "titel": "Microsoft Excel", "klasse": "#32770",
                        "rechteck": (0, 0, 10, 10)}
    auge.t.dialog_text = lambda hwnd: "Die Datei ist besch\u00e4digt. IBAN DE89370400440532013000"
    auge._vorne_pruefen()
    auge._vorne_pruefen("taste")
    assert auge.pause
    auge._vorne_pruefen("taste")
    assert not auge.pause
    ereignisse = [x[1] for x in _meldungen(ausgang)]
    assert [e["art"] for e in ereignisse] == ["fenster", "titel", "dialog", "pause", "weiter"]
    assert "besch\u00e4digt" in ereignisse[2]["text"] and "DE89" not in ereignisse[2]["text"]


def test_pause_haelt_die_aufnahme_sofort_an():
    auge, befehle, ausgang, ocr, _z = _auge()
    zaehler = {"n": 0}
    echte = auge.t.quelle.bild

    def bild():
        zaehler["n"] += 1
        return echte()

    auge.t.quelle.bild = bild
    befehle.put(("pause",))
    _laufen(auge, befehle, sekunden=2.0)
    assert zaehler["n"] == 0 and ocr.aufrufe == 0


def test_volle_ausgabe_verwirft_die_aelteste_meldung():
    q = queue.Queue(maxsize=2)
    for i in range(5):
        senden(q, ("ereignis", {"i": i}))
    assert [q.get_nowait()[1]["i"] for _ in range(2)] == [3, 4]


def test_quelle_kaputt_dxcam_dann_mss_dann_ende():
    class Kaputt(FakeQuelle):
        name = "dxcam"

        def bild(self):
            raise OSError("weg")

    geoeffnet = []

    def oeffne(wunsch, monitor):
        geoeffnet.append(wunsch)
        return FakeQuelle([_leer()], fehler_ab=0), ""

    uhr = Uhr()
    teile = AugenTeile(quelle=Kaputt(), vordergrund=lambda: None, oeffne=oeffne, uhr=uhr, schlafe=uhr.schlafe)
    befehle, ausgang = queue.Queue(), queue.Queue()
    grund = Auge(befehle, ausgang, {"fps": 20}, teile).lauf()
    texte = [x[1].get("text", "") for x in _meldungen(ausgang) if x[0] == "ereignis"]
    assert geoeffnet == ["mss"] and grund == "quelle"
    assert any("mss" in t for t in texte) and any("geht nicht mehr" in t for t in texte)


def test_ausserhalb_von_windows_ohne_ersatzteile_ein_klarer_grund(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    ausgang = queue.Queue()
    hauptschleife(queue.Queue(), ausgang, {})
    assert ausgang.get_nowait() == ("ende", "Bildschirm-Sehen gibt es nur unter Windows.")


def test_auge_als_thread_und_als_eigener_prozess():
    for als_prozess in (False, True):
        v = AugeVerbindung({"fake": True, "fps": 30}, als_prozess=als_prozess,
                           teile=None if als_prozess else _fake_teile({"fake": True}))
        v.start()
        try:
            gesehen, ende = [], time.monotonic() + 30
            while time.monotonic() < ende:
                m = v.lies(0.1)
                if m and m[0] == "ereignis":
                    gesehen.append(m[1]["art"])
                    if m[1]["art"] == "text":
                        break
            assert "fenster" in gesehen and "text" in gesehen, (als_prozess, gesehen)
        finally:
            v.stop()
        assert not v.lebt()
