"""Handy-Kamera: echte WebRTC-Verbindung im selben Prozess (aiortc-"Handy" -> HandyKamera).

Das "Handy" ist hier ein aiortc-Anbieter mit einer kuenstlichen Videospur; die Signalisierung
laeuft ueber das SpeicherRelay. Netz nach aussen wird nicht gebraucht.
"""
import asyncio
import ipaddress
import json
import threading
import time

import pytest

pytest.importorskip("aiortc")
pytest.importorskip("av")
pytest.importorskip("cryptography")

import av  # noqa: E402
import numpy as np  # noqa: E402
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack  # noqa: E402

from assistant.kamera import signal as sig  # noqa: E402
from assistant.kamera.quelle import HandyQuelle, KameraQuelle  # noqa: E402
from assistant.kamera.webrtc import HandyKamera  # noqa: E402

# In Test-Containern haben die Netzwerkkarten oft keine Privatadresse (z.B. 192.0.2.x) -
# fuer den Test zaehlen deshalb auch die Dokumentations-Netze als "LAN".
_TESTNETZE = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24")]


def lan_fuer_test(adresse: str) -> bool:
    if sig.ist_lan_adresse(adresse):
        return True
    try:
        return any(ipaddress.ip_address(adresse) in n for n in _TESTNETZE)
    except ValueError:
        return False


class Farbspur(VideoStreamTrack):
    """640x480, Farbe wechselt mit jedem Bild."""

    def __init__(self):
        super().__init__()
        self.n = 0

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        self.n += 1
        bild = np.zeros((480, 640, 3), dtype=np.uint8)
        bild[:, :, 0] = (self.n * 7) % 256
        bild[:, :, 1] = 128
        frame = av.VideoFrame.from_ndarray(bild, format="rgb24")
        frame.pts, frame.time_base = pts, time_base
        return frame


class FakeHandy:
    """Spielt die Handy-Seite (wie kamera.js): Angebot schicken, Antwort setzen, DataChannel."""

    def __init__(self, link, relay, geraet="testhandy01", zusatz_kandidat=None):
        self.kopplung = sig.Kopplung.aus_link(link, jetzt=time.time())
        self.kanal = sig.Kanal(self.kopplung, "h")
        self.relay = relay
        self.geraet = geraet
        self.zusatz_kandidat = zusatz_kandidat
        self.dc_nachrichten = []
        self.signal = []
        self.pc = None
        self.dc = None

    async def verbinden(self, timeout=15):
        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.pc.addTrack(Farbspur())
        self.dc = self.pc.createDataChannel("steuerung")

        @self.dc.on("message")
        def _m(roh):
            self.dc_nachrichten.append(json.loads(roh))

        await self.pc.setLocalDescription(await self.pc.createOffer())
        sdp = self.pc.localDescription.sdp
        if self.zusatz_kandidat:
            sdp = sdp.replace("a=end-of-candidates", self.zusatz_kandidat + "\r\na=end-of-candidates", 1)
        seit = await asyncio.to_thread(self.relay.senden, self.kanal.thema,
                                       self.kanal.verpacke("angebot", {"sdp": sdp, "g": self.geraet}))
        ende = time.monotonic() + timeout
        while time.monotonic() < ende:
            for n in await asyncio.to_thread(self.relay.empfangen, self.kanal.thema, seit, 0.5):
                seit = n.id
                nachricht = self.kanal.oeffne(n.text)
                if nachricht is None or nachricht.daten.get("g") != self.geraet:
                    continue
                self.signal.append(nachricht)
                if nachricht.typ == "antwort":
                    await self.pc.setRemoteDescription(RTCSessionDescription(nachricht.daten["sdp"], "answer"))
                    return nachricht
                if nachricht.typ in ("fehler", "besetzt"):
                    return nachricht
        raise AssertionError("keine Antwort von Nova")

    async def schliessen(self):
        if self.pc:
            await self.pc.close()


class HandyThread:
    """Laesst das Test-Handy in einem eigenen Event-Loop laufen (wie ein zweites Geraet)."""

    def __init__(self, handy):
        self.handy = handy
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def rufe(self, coro, timeout=20):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def ende(self):
        try:
            self.rufe(self.handy.schliessen(), 10)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(5)


@pytest.fixture
def relay():
    return sig.SpeicherRelay()


def _kamera(relay, **kw):
    kw.setdefault("lan_pruefung", lan_fuer_test)
    kw.setdefault("warte_intervall", 0.5)
    return HandyKamera(relay, **kw)


def test_loopback_bilder_kommen_an_und_stop_ist_sauber(relay):
    kamera = _kamera(relay)
    info = kamera.start()
    assert kamera.zustand == "wartet"
    assert info.link.startswith(sig.STANDARD_BASIS_URL + "#p=") and info.code
    assert "#p=" not in repr(info)
    # Kurzcode-Kanal: Nova hat die Kopplung dort abgelegt
    ck = sig.code_kopplung(info.code, info.ablauf)
    eintraege = relay.empfangen(ck.thema, None, 5)
    assert sig.Kanal(ck, "h").oeffne(eintraege[0].text).daten["p"] == sig.Kopplung.aus_link(info.link).payload()

    handy = FakeHandy(info.link, relay,
                      zusatz_kandidat="a=candidate:99 1 udp 2122260223 8.8.8.8 40000 typ host")
    ht = HandyThread(handy)
    try:
        antwort = ht.rufe(handy.verbinden())
        assert antwort.typ == "antwort"
        # Nova gibt nur LAN-Kandidaten heraus
        for zeile in antwort.daten["sdp"].split("\r\n"):
            if zeile.startswith("a=candidate:"):
                assert lan_fuer_test(zeile.split()[4])
        assert kamera.warte_auf("verbunden", 20), kamera.status()
        assert kamera.verworfene_kandidaten >= 1  # 8.8.8.8 wurde verworfen

        ende = time.monotonic() + 15
        bild = None
        while time.monotonic() < ende and bild is None:
            bild = kamera.latest_frame(max_kante=320)
            time.sleep(0.1)
        assert bild is not None, kamera.status()
        assert max(bild.size) <= 320 and bild.mode == "RGB"
        jpeg = kamera.latest_frame(als="jpeg", max_kante=200)
        assert jpeg[:2] == b"\xff\xd8"
        status = kamera.status()
        assert status["bilder"] > 0 and status["aufloesung"] == [640, 480]
        assert "link" not in status and "schluessel" not in json.dumps(status)

        # DataChannel: hallo von Nova, ping/pong, Status vom Handy
        ht.rufe(_warte(lambda: any(n.get("t") == "hallo" for n in handy.dc_nachrichten)))
        ht.loop.call_soon_threadsafe(handy.dc.send, json.dumps({"t": "ping"}))
        ht.loop.call_soon_threadsafe(handy.dc.send, json.dumps({"t": "status", "kamera": "hinten",
                                                                "sichtbar": True}))
        ht.rufe(_warte(lambda: any(n.get("t") == "pong" for n in handy.dc_nachrichten)))
        assert _warte_sync(lambda: kamera.status()["kamera"] == "hinten")

        # Quelle-Adapter
        quelle = HandyQuelle(kamera)
        assert isinstance(quelle, KameraQuelle)
        assert quelle.status()["zustand"] == "verbunden"
        assert quelle.latest_frame(max_kante=100) is not None

        t0 = time.monotonic()
        kamera.stop()
        assert time.monotonic() - t0 < 8
        assert kamera.zustand == "getrennt" and not kamera.laeuft()
        assert kamera.latest_frame() is None
        # Handy bekam "stopp" ueber den DataChannel
        ht.rufe(_warte(lambda: any(n.get("t") == "stopp" for n in handy.dc_nachrichten)))
    finally:
        kamera.stop()
        ht.ende()
    assert not any(t.name.startswith("handy-kamera") and t.name != "handy-kamera-relay" and t.is_alive()
                   for t in threading.enumerate())


def test_zweites_handy_wird_abgewiesen(relay):
    kamera = _kamera(relay)
    info = kamera.start()
    h1, h2 = FakeHandy(info.link, relay, "erstes"), FakeHandy(info.link, relay, "zweites")
    t1, t2 = HandyThread(h1), HandyThread(h2)
    try:
        assert t1.rufe(h1.verbinden()).typ == "antwort"
        assert kamera.warte_auf("verbunden", 20)
        # zweites Handy: eigener Kanal mit hoeherer Folgenummer noetig (gleiche Kopplung, anderes Geraet)
        h2.kanal._seq = 100
        assert t2.rufe(h2.verbinden()).typ == "besetzt"
        assert kamera.zustand == "verbunden"
    finally:
        kamera.stop()
        t1.ende()
        t2.ende()


def test_nur_oeffentliche_kandidaten_ergibt_wlan_fehler(relay):
    kamera = _kamera(relay, lan_pruefung=lambda adresse: False)
    info = kamera.start()
    handy = FakeHandy(info.link, relay)
    ht = HandyThread(handy)
    try:
        antwort = ht.rufe(handy.verbinden())
        assert antwort.typ == "fehler" and antwort.daten["grund"] == "kein-lan"
        assert kamera.warte_auf("fehler", 5)
        assert "WLAN" in kamera.fehler
    finally:
        kamera.stop()
        ht.ende()


def test_abgelaufene_kopplung(relay):
    kamera = _kamera(relay, gueltig=0.5, warte_intervall=0.2)
    kamera.start()
    assert kamera.warte_auf("fehler", 5)
    assert "abgelaufen" in kamera.fehler
    kamera.stop()
    assert kamera.zustand == "getrennt"


def test_fremde_und_kaputte_nachrichten_werden_ignoriert(relay):
    kamera = _kamera(relay)
    info = kamera.start()
    thema = sig.Kopplung.aus_link(info.link).thema
    fremd = sig.Kanal(sig.Kopplung.neu(), "h")
    relay.senden(thema, fremd.verpacke("angebot", {"sdp": "v=0", "g": "boese"}))
    relay.senden(thema, "Quatsch")
    time.sleep(1.0)
    assert kamera.zustand == "wartet"
    kamera.stop()


def test_ohne_aiortc_freundlicher_fehler(monkeypatch):
    import builtins

    from assistant.kamera import webrtc

    echt = builtins.__import__

    def ohne(name, *a, **kw):
        if name == "aiortc":
            raise ImportError("weg")
        return echt(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", ohne)
    with pytest.raises(webrtc.HandyKameraFehler, match="pip install aiortc"):
        HandyKamera(sig.SpeicherRelay()).start()


async def _warte(bedingung, timeout=10):
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        if bedingung():
            return True
        await asyncio.sleep(0.05)
    raise AssertionError("Bedingung nicht erfüllt")


def _warte_sync(bedingung, timeout=10):
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.05)
    return False
