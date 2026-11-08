"""Live-Sehen mit dem Handy als Kamera (ohne Netz, ohne aiortc - mit einer gefaelschten Kopplung)."""
import io
import json
import logging
import time

import pytest

from assistant.config import load_config
from assistant.sehen.dienst import SehDienst
from assistant.sehen.quellen import waehle_quellen

GEHEIM = "https://beispiel.invalid/kamera/v1/#p=GEHEIMER-SCHLUESSEL-123"
CODE = "7KQ2-M9XD"


def _jpeg(farbe):
    Image = pytest.importorskip("PIL.Image")
    puffer = io.BytesIO()
    Image.new("RGB", (64, 48), farbe).save(puffer, "JPEG")
    return puffer.getvalue()


class FakeHandy:
    """Wie assistant.kamera.quelle.HandyQuelle - nur ohne WebRTC."""

    def __init__(self, fehler=None):
        self.fehler = fehler
        self.zustand = "wartet"
        self.gestoppt = 0
        self.nimm = None
        self.pumpe_aus = False

    def start(self):
        if self.fehler:
            raise self.fehler
        return {"link": GEHEIM, "ablauf": int(time.time()) + 300, "code": CODE}

    def stop(self):
        self.gestoppt += 1
        self.zustand = "getrennt"

    def status(self):
        return {"zustand": self.zustand, "fehler": None, "bild_alter": 0.4, "kamera": "hinten", "ablauf": 1,
                "schritt": "x", "relay": "ntfy"}

    def pumpe(self, nimm, intervall=1.0, max_kante=1280, qualitaet=75):
        self.nimm = nimm
        self.pumpe_aus = False

        def stopp():
            self.pumpe_aus = True
        return stopp


class Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def dienst(tmp_path):
    def make(zustimmung=True, sieht=True, fehler=None, **einst):
        cfg = load_config(tmp_path)
        for k, v in einst.items():
            setattr(cfg.sehen, k, v)
        handys, notizen, pakete = [], [], []

        def fabrik():
            h = FakeHandy(fehler)
            handys.append(h)
            return h

        d = SehDienst(cfg, on_notiz=notizen.append, wecken=pakete.append, sieht_bilder=lambda: sieht,
                      handy_fabrik=fabrik, bildschirm_moeglich=False, uhr=Uhr(), speichern=lambda k, v: None,
                      mit_thread=False)
        if zustimmung:
            d.zustimmen()
        d.handys, d.notizen, d.pakete = handys, notizen, pakete
        return d
    return make


def _bewegung(d, handy):
    dunkel, hell = _jpeg((10, 10, 10)), _jpeg((230, 230, 230))
    for _ in range(6):
        d.uhr.t += 1.0
        handy.nimm(dunkel)
    for _ in range(10):
        d.uhr.t += 1.0
        handy.nimm(hell)
        d.tick()


def test_koppeln_nur_mit_zustimmung(dienst):
    d = dienst(zustimmung=False)
    assert d.handy_koppeln() == {"ok": False, "zustimmung": True, "error": "Bitte erst zustimmen."}
    assert d.handys == [] and not d.aktiv


def test_koppeln_link_nur_in_der_antwort_nie_im_zustand(dienst, caplog):
    caplog.set_level(logging.DEBUG)
    d = dienst()
    antwort = d.handy_koppeln()
    assert antwort["ok"] and antwort["link"] == GEHEIM and antwort["code"] == CODE and antwort["ablauf"]
    assert "WLAN" in antwort["hinweis"] and "Firewall" in antwort["hinweis"]
    assert d.aktiv and d.quellen == {"handy"} and d.handys[0].nimm is not None
    status = d.status()
    assert status["handy"] == {"zustand": "wartet", "fehler": None, "bild_alter": 0.4, "kamera": "hinten",
                               "ablauf": 1}
    roh = json.dumps(status, ensure_ascii=False) + " ".join(d.notizen) + caplog.text
    assert "GEHEIM" not in roh and CODE not in roh and "#p=" not in roh


def test_handy_bewegung_weckt_mit_bild_vom_handy(dienst):
    d = dienst()
    d.handy_koppeln()
    handy = d.handys[0]
    handy.zustand = "verbunden"
    d.tick()
    assert any("verbunden" in n for n in d.notizen)
    _bewegung(d, handy)
    (paket,) = d.pakete
    assert paket.quelle == "handy" and paket.bilder and paket.bilder[0].name == "handy.jpg"
    assert "Handy-Kamera" in paket.text and "Handy-Kamera" in paket.anzeige
    bild, grund = d.aktuelles_bild()
    assert bild is not None and bild.name == "handy.jpg"


def test_pause_afk_aus_und_gehirnwechsel_beenden_das_handy(dienst):
    d = dienst()
    d.handy_koppeln()
    h1 = d.handys[0]
    text = d.pause()
    assert h1.gestoppt == 1 and h1.pumpe_aus and "neu koppeln" in text
    assert d.status()["handy"]["zustand"] == "getrennt"
    h1.nimm(_jpeg((1, 2, 3)))                               # was noch kommt, wird nicht angenommen
    assert d.handy_kamera.letztes() is None and d.ereignisse == 0
    antwort = d.handy_koppeln()                            # "Neu koppeln" hebt die Pause auf
    assert antwort["ok"] and not d.pausiert and len(d.handys) == 2
    d.setze_abwesend(True)
    assert d.handys[1].gestoppt == 1 and any("weg bist" in n for n in d.notizen)
    d.setze_abwesend(False)
    d.handy_koppeln()
    d.config.sehen.einverstanden_fuer = "anderes-gehirn"
    d.tick()
    assert not d.aktiv and d.handys[2].gestoppt == 1
    d2 = dienst()
    d2.handy_koppeln()
    d2.aus()
    assert d2.handys[0].gestoppt == 1


def test_handy_beenden(dienst):
    d = dienst()
    assert d.handy_beenden() == "Die Handy-Kamera war nicht an."
    d.handy_koppeln()
    text = d.handy_beenden()
    assert d.handys[0].gestoppt == 1 and not d.aktiv and "Live-Sehen ist aus" in text


def test_pakete_fehlen_dann_klarer_hinweis(dienst):
    from assistant.kamera.webrtc import HandyKameraFehler

    d = dienst(fehler=HandyKameraFehler("F\u00fcr die Handy-Kamera fehlen noch Pakete."))
    antwort = d.handy_koppeln()
    assert antwort["ok"] is False and "fehlen noch Pakete" in antwort["error"] and not d.aktiv


def test_auto_reihenfolge_webcam_dann_handy_dann_bildschirm():
    assert waehle_quellen("auto", True, True, True, handy_verbunden=True) == ({"webcam"}, "")
    assert waehle_quellen("auto", False, True, True, handy_verbunden=True) == ({"handy"}, "")
    assert waehle_quellen("auto", False, True, True, handy_verbunden=False) == ({"bildschirm"}, "")
    assert waehle_quellen("auto", False, True, False, handy_verbunden=True) == ({"bildschirm"}, "")
    quellen, hinweis = waehle_quellen("handy", False, False, False)
    assert quellen == {"handy"} and "Bewegung" in hinweis


def test_auto_behaelt_ein_verbundenes_handy(dienst):
    d = dienst()
    d.handy_koppeln()
    d.handys[0].zustand = "verbunden"
    ok, _text = d.an("auto")
    assert ok and d.quellen == {"handy"} and len(d.handys) == 1 and d.handys[0].gestoppt == 0
    assert d.handys[0].pumpe_aus is False


def test_einstellung_kennt_handy():
    from assistant.config import SehenSettings
    from assistant.sehen.einstellungen import regeln_aus

    assert regeln_aus(SehenSettings(quelle="handy")).quelle == "handy"


def test_kamera_protokoll_umbenannt():
    import assistant.kamera.quelle as q

    assert hasattr(q, "HandyQuellenProtokoll") and not hasattr(q, "KameraQuelle")


# -- App und Terminal ------------------------------------------------------------------------
def test_app_koppeln_endpunkt_und_kein_geheimnis_im_zustand(tmp_path, caplog):
    import queue as _q
    import urllib.request

    from assistant.app.controller import AppController
    from assistant.app.server import AppServer

    caplog.set_level(logging.DEBUG)
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    cfg.provider.aktiv = "claude"
    server = AppServer(lambda broadcast: AppController(cfg, broadcast))
    server.start()
    ereignisse = server.hub.subscribe()
    ctl = server.controller
    handys = []
    ctl.sehen.handy_fabrik = lambda: handys.append(FakeHandy()) or handys[-1]

    def post(body, token=True):
        req = urllib.request.Request(f"http://127.0.0.1:{server.port}/api/sehen", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              **({"X-KI-Token": server.token} if token else {})}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, None

    try:
        assert post({"aktion": "handy_koppeln"}, token=False)[0] == 403
        status, body = post({"aktion": "handy_koppeln"})
        assert body["ok"] is False and body["zustimmung"] is True and handys == []
        status, body = post({"aktion": "handy_koppeln", "einverstanden": True})
        assert status == 200 and body["ok"] is True
        assert set(body) >= {"ok", "link", "code", "svg", "ablauf", "hinweis", "tipps", "sehen"}
        assert body["link"] == GEHEIM and body["code"] == CODE and "Firewall" in body["tipps"]
        assert body["sehen"]["handy"]["zustand"] == "wartet" and body["sehen"]["quellen"] == ["handy"]
        # nirgends sonst: Zustand, Ereignisse, Verlauf, Protokoll
        ctl.sehen._status_jetzt()
        ctl._state_changed()
        alles = json.dumps(ctl.state(), ensure_ascii=False) + json.dumps(ctl.history, ensure_ascii=False)
        while True:
            try:
                alles += ereignisse.get_nowait()
            except _q.Empty:
                break
        alles += caplog.text
        assert "GEHEIM" not in alles and CODE not in alles and "#p=" not in alles
        status, body = post({"aktion": "handy_beenden"})
        assert body["ok"] and not body["sehen"]["aktiv"] and handys[0].gestoppt == 1
        # /sehen handy im Chat oeffnet nur den Dialog (der Link kommt nie in den Chat)
        ctl._sehen_command(["handy"])
        alles = ""
        while True:
            try:
                alles += ereignisse.get_nowait()
            except _q.Empty:
                break
        assert '"what": "handy"' in alles and "GEHEIM" not in alles
    finally:
        ctl.shutdown()
        server.stop()


def test_terminal_sehen_handy_zeigt_qr_link_und_code(tmp_path, capsys, monkeypatch):
    from assistant.ui.cli import CLI

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    cfg.provider.aktiv = "claude"
    cli = CLI(cfg)
    try:
        cli.sehen.handy_fabrik = FakeHandy
        monkeypatch.setattr(cli, "_ask_yes", lambda *a, **k: True)
        monkeypatch.setattr("assistant.kamera.qr.qr_text", lambda link: "##QR##\n")
        cli._handle_command("/sehen handy")
        out = capsys.readouterr().out
        assert "##QR##" in out and GEHEIM in out and CODE in out and "5 Minuten" in out
        assert cli.sehen.quellen == {"handy"}
        cli._handle_command("/sehen status")
        assert "Handy-Kamera: wartet" in capsys.readouterr().out
        cli._handle_command("/sehen handy aus")
        assert "beendet" in capsys.readouterr().out and not cli.sehen.aktiv
    finally:
        cli.sehen.aus()
        cli.memory.close()


# -- Pruefbefunde: nie versteckt koppeln, Pause waehrend des Koppelns, nicht unter der Sperre stoppen -----
def test_kein_verstecktes_koppeln_ohne_qr(dienst):
    from assistant.sehen.dienst import HANDY_PER_QR

    d = dienst()
    assert d.an("handy") == (False, HANDY_PER_QR) and d.handys == [] and not d.aktiv
    d.config.sehen.quelle = "handy"
    assert d.an() == (False, HANDY_PER_QR) and d.handys == []
    d.bildschirm_moeglich = True
    d.auge_fabrik = lambda e: type("A", (), {"start": lambda s: None, "senden": lambda s, b: None,
                                             "lies": lambda s, t=0.1: None, "lebt": lambda s: True,
                                             "stop": lambda s, w=2.0: None})()
    assert d.an("bildschirm")[0]
    assert d.an("handy") == (False, HANDY_PER_QR) and d.aktiv and d.quellen == {"bildschirm"}  # bleibt, wie es war
    d.aus()


def test_pause_waehrend_des_koppelns_stoppt_die_neue_kopplung(dienst):
    d = dienst()
    d.handy_koppeln()
    erste = d.handys[0]

    class Langsam(FakeHandy):
        def start(self):
            d.pausiert = True              # waehrend das Handy startet, drueckst du Pause
            return super().start()

    d.handy_fabrik = lambda: d.handys.append(Langsam()) or d.handys[-1]
    fehler = d._handy_neu()
    assert "Pause" in fehler and d.handys[1].gestoppt == 1 and d._handy is None and erste.gestoppt == 1


def test_handy_wird_nie_unter_der_sperre_gestoppt(dienst):
    import threading

    d = dienst()
    d.handy_koppeln()
    frei = []

    def stop():
        t = threading.Thread(target=lambda: frei.append(d._lock.acquire(timeout=0.5) and (d._lock.release() or True)))
        t.start()
        t.join()

    d.handys[0].stop = stop
    d.handys[0].zustand = "verbunden"
    ok, _text = d.an("webcam")               # keine Webcam da -> nichts an, verbundenes Handy wird beendet
    assert not ok and frei == [True]


def test_start_mit_quelle_handy_koppelt_nicht_versteckt(tmp_path, capsys):
    from assistant.ui.cli import CLI

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    cfg.provider.aktiv = "claude"
    cli = CLI(cfg)
    try:
        cli.sehen.handy_fabrik = lambda: pytest.fail("versteckte Kopplung")
        cli.sehen.zustimmen()
        cfg.sehen.aktiv, cfg.sehen.quelle = True, "handy"
        cli._sehen_beim_start()
        assert "/sehen handy" in capsys.readouterr().out and not cli.sehen.aktiv
    finally:
        cli.memory.close()


def test_sehen_an_handy_zeigt_den_qr_code(tmp_path, capsys, monkeypatch):
    from assistant.ui.cli import CLI

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    cfg.provider.aktiv = "claude"
    cli = CLI(cfg)
    try:
        cli.sehen.zustimmen()
        cli.sehen.handy_fabrik = FakeHandy
        monkeypatch.setattr("assistant.kamera.qr.qr_text", lambda link: "##QR##\n")
        cli._handle_command("/sehen an handy")
        out = capsys.readouterr().out
        assert "##QR##" in out and CODE in out and cli.sehen.quellen == {"handy"}
        cli._handle_command("/sehen an")
        assert "schon an" in capsys.readouterr().out
    finally:
        cli.sehen.aus()
        cli.memory.close()


def test_app_start_mit_quelle_handy_nur_hinweis(tmp_path):
    from assistant.app.controller import AppController

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    cfg.provider.aktiv = "claude"
    ctl = AppController(cfg, lambda e: None)
    try:
        ctl.sehen.handy_fabrik = lambda: pytest.fail("versteckte Kopplung")
        ctl.sehen.zustimmen()
        cfg.sehen.aktiv, cfg.sehen.quelle = True, "handy"
        ctl._sehen_beim_start()
        assert not ctl.sehen.aktiv and any("/sehen handy" in m["text"] for m in ctl.history)
        assert ctl.sehen_api({"aktion": "an", "quelle": "handy"})["ok"] is False
    finally:
        ctl.shutdown()
