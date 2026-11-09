"""Handy-Kamera: echte WebRTC-Verbindung im selben Prozess (aiortc-"Handy" -> HandyKamera).

Das "Handy" ist hier ein aiortc-Anbieter mit einer kuenstlichen Videospur; die Signalisierung
laeuft ueber das SpeicherRelay. Netz nach aussen wird nicht gebraucht.
"""
import asyncio
import ipaddress
import json
import threading
import time
import uuid

import pytest

pytest.importorskip("aiortc")
pytest.importorskip("av")
pytest.importorskip("cryptography")

import av  # noqa: E402
import numpy as np  # noqa: E402
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack  # noqa: E402

from assistant.kamera import signal as sig  # noqa: E402
from assistant.kamera.quelle import HandyQuelle, HandyQuellenProtokoll  # noqa: E402
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

    def __init__(self, link, relay, geraet="testhandy01", zusatz_kandidat=None, oeffentlich=False,
                 antwort_setzen=True, seq_start=0, mdns=False, vor_antwort=None):
        self.kopplung = sig.Kopplung.aus_link(link, jetzt=time.time())
        self.kanal = sig.Kanal(self.kopplung, "h")
        self.relay = relay
        self.geraet = geraet
        self.zusatz_kandidat = zusatz_kandidat
        self.oeffentlich = oeffentlich        # alle eigenen Kandidaten auf eine oeffentliche Adresse biegen
        self.antwort_setzen = antwort_setzen  # False: Antwort nie verwenden (Versuch laeuft ins Leere)
        self.kanal._seq = seq_start
        self.mdns = mdns                      # eigene Adressen hinter xxxx.local verstecken (wie Chrome)
        self.mdns_namen = {}                  # name -> echte Adresse
        self.vor_antwort = vor_antwort        # wird mit Novas Antwort aufgerufen, bevor sie gesetzt wird
        self.dc_nachrichten = []
        self.signal = []
        self.pc = None
        self.dc = None

    async def verbinden(self, timeout=15):
        if self.pc is not None:
            await self.pc.close()
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
        if self.mdns:
            zeilen = []
            for zeile in sdp.split("\r\n"):
                if zeile.startswith("a=candidate:"):
                    teile = zeile.split()
                    name = next((n for n, ip in self.mdns_namen.items() if ip == teile[4]), None)
                    if name is None:
                        name = f"{uuid.uuid4()}.local"
                        self.mdns_namen[name] = teile[4]
                    teile[4] = name
                    zeile = " ".join(teile)
                zeilen.append(zeile)
            sdp = "\r\n".join(zeilen)
        if self.oeffentlich:
            zeilen = []
            for zeile in sdp.split("\r\n"):
                if zeile.startswith("a=candidate:"):
                    teile = zeile.split()
                    teile[4] = "8.8.8.8"
                    zeile = " ".join(teile)
                zeilen.append(zeile)
            sdp = "\r\n".join(zeilen)
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
                    if not self.antwort_setzen:
                        return nachricht
                    if self.vor_antwort is not None:
                        self.vor_antwort(nachricht)
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
    kw.setdefault("pc_netze", lambda: [])  # Netz-Vergleich nur, wo ein Test ihn vorgibt
    kw.setdefault("aiortc_mdns", False)     # kein Multicast im Test
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
        assert isinstance(quelle, HandyQuellenProtokoll)
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
    h1 = FakeHandy(info.link, relay, "erstes")
    h2 = FakeHandy(info.link, relay, "zweites", seq_start=100)
    t1, t2 = HandyThread(h1), HandyThread(h2)
    try:
        assert t1.rufe(h1.verbinden()).typ == "antwort"
        assert kamera.warte_auf("verbunden", 20)
        # waehrend einer laufenden Verbindung wird gar kein Angebot angenommen
        antwort = t2.rufe(h2.verbinden())
        assert (antwort.typ, antwort.daten.get("grund")) == ("fehler", "noch-verbunden")
        assert kamera.zustand == "verbunden"
        # nach dem Trennen gehoert die Kopplung weiter dem ersten Handy
        t1.loop.call_soon_threadsafe(h1.dc.send, json.dumps({"t": "stopp"}))
        assert kamera.warte_auf("getrennt", 10)
        assert t2.rufe(h2.verbinden()).typ == "besetzt"
        # ... und das erste Handy darf wieder verbinden (Folgenummern zaehlen pro Absender "h" -
        # die echte Seite startet sie bei Date.now()/100, hier von Hand weiterzaehlen)
        h1.kanal._seq = 1000
        assert t1.rufe(h1.verbinden()).typ == "antwort"
        assert kamera.warte_auf("verbunden", 20)
    finally:
        kamera.stop()
        t1.ende()
        t2.ende()


def test_laufende_verbindung_laesst_sich_nicht_uebernehmen(relay):
    """Wer den Schluessel kennt, darf mit derselben Geraete-ID kein neues Video unterschieben."""
    kamera = _kamera(relay)
    info = kamera.start()
    echt = FakeHandy(info.link, relay, "geraet-a")
    falsch = FakeHandy(info.link, relay, "geraet-a", seq_start=10_000)  # gleiche ID, hoehere Folgenummer
    t1, t2 = HandyThread(echt), HandyThread(falsch)
    try:
        assert t1.rufe(echt.verbinden()).typ == "antwort"
        assert kamera.warte_auf("verbunden", 20)
        pc_vorher = kamera._pc
        antwort = t2.rufe(falsch.verbinden())
        assert (antwort.typ, antwort.daten.get("grund")) == ("fehler", "noch-verbunden")
        time.sleep(0.5)
        assert kamera.zustand == "verbunden" and kamera._pc is pc_vorher
        # "tschuess" ueber das Relais trennt eine laufende Verbindung auch nicht
        relay.senden(falsch.kanal.thema, falsch.kanal.verpacke("tschuess", {"g": "geraet-a"}))
        time.sleep(0.8)
        assert kamera.zustand == "verbunden"
    finally:
        kamera.stop()
        t1.ende()
        t2.ende()


def test_gescheiterter_erster_versuch_sperrt_die_kopplung_nicht(relay):
    kamera = _kamera(relay)
    info = kamera.start()
    kaputt = FakeHandy(info.link, relay, "erster-versuch", oeffentlich=True)
    neu = FakeHandy(info.link, relay, "neu-gescannt", seq_start=100)
    t1, t2 = HandyThread(kaputt), HandyThread(neu)
    try:
        antwort = t1.rufe(kaputt.verbinden())
        assert (antwort.typ, antwort.daten.get("grund")) == ("fehler", "kein-lan")
        assert kamera.warte_auf("fehler", 5)
        # neu gescannt (andere Geraete-ID): wird angenommen, nicht "besetzt"
        assert t2.rufe(neu.verbinden()).typ == "antwort"
        assert kamera.warte_auf("verbunden", 20)
    finally:
        kamera.stop()
        t1.ende()
        t2.ende()


def test_abgebrochener_versuch_sperrt_nur_solange_er_laeuft(relay):
    kamera = _kamera(relay, verbinden_timeout=1.5)
    info = kamera.start()
    stumm = FakeHandy(info.link, relay, "stumm", antwort_setzen=False)
    anderes = FakeHandy(info.link, relay, "anderes", seq_start=100)
    t1, t2 = HandyThread(stumm), HandyThread(anderes)
    try:
        assert t1.rufe(stumm.verbinden()).typ == "antwort"  # Antwort kommt, wird aber nie gesetzt
        assert t2.rufe(anderes.verbinden()).typ == "besetzt"  # Versuch laeuft noch
        assert kamera.warte_auf("fehler", 10)  # Zeitueberschreitung beendet den Versuch
        assert t2.rufe(anderes.verbinden()).typ == "antwort"
        assert kamera.warte_auf("verbunden", 20)
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
    raise AssertionError("Bedingung nicht erf\u00fcllt")


def _warte_sync(bedingung, timeout=10):
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.05)
    return False


# -- Versteckte Adressen (mDNS) und Fehlersuche ----------------------------------------------------
def test_versteckte_adresse_wird_ueber_das_system_aufgeloest(relay):
    namen = {}
    gefragt = []

    def aufloeser(name):
        gefragt.append(name)
        return namen.get(name)

    kamera = _kamera(relay, mdns_aufloeser=aufloeser)
    info = kamera.start()
    handy = FakeHandy(info.link, relay, mdns=True)
    handy.mdns_namen = namen  # derselbe Speicher: der "Systemresolver" kennt die Namen
    ht = HandyThread(handy)
    try:
        assert ht.rufe(handy.verbinden()).typ == "antwort"
        assert kamera.warte_auf("verbunden", 20), kamera.status()
        diagnose = kamera.status()["diagnose"]
        assert diagnose["kandidaten"]["ip"] == 0 and diagnose["kandidaten"]["mdns"] >= 1
        assert diagnose["mdns_aufgeloest"] >= 1 and gefragt
        assert diagnose["eingehend"] > 0  # Pruefpakete vom Handy wurden gezaehlt
        assert kamera.status()["grund"] is None
    finally:
        kamera.stop()
        ht.ende()


def test_nicht_aufloesbare_adresse_verbindet_trotzdem_ueber_die_pruefpakete(relay):
    """Nur xxxx.local, nicht aufloesbar: Nova wartet auf die Pakete des Handys (peer-reflexiv)
    statt sofort aufzugeben (a=end-of-candidates wird entfernt)."""
    kamera = _kamera(relay, mdns_aufloeser=lambda name: None)
    info = kamera.start()
    handy = FakeHandy(info.link, relay, mdns=True)
    ht = HandyThread(handy)
    try:
        assert ht.rufe(handy.verbinden()).typ == "antwort"
        assert kamera.warte_auf("verbunden", 20), kamera.status()
        assert kamera.status()["diagnose"]["mdns_aufgeloest"] == 0
    finally:
        kamera.stop()
        ht.ende()


def _scheitern(relay, **kw):
    """Handy schickt ein Angebot, setzt die Antwort aber nie -> Zeitueberschreitung mit Diagnose."""
    handy_kw = {k: kw.pop(k) for k in ("mdns",) if k in kw}
    kamera = _kamera(relay, verbinden_timeout=1.5, **kw)
    info = kamera.start()
    handy = FakeHandy(info.link, relay, antwort_setzen=False, **handy_kw)
    ht = HandyThread(handy)
    try:
        assert ht.rufe(handy.verbinden()).typ == "antwort"
        assert kamera.warte_auf("fehler", 10)
        return kamera.status()
    finally:
        kamera.stop()
        ht.ende()


def test_diagnose_keine_pakete_vom_handy(relay):
    status = _scheitern(relay)
    assert status["grund"] == "keine-pakete" and status["verbindung_gescheitert"] is True
    assert status["diagnose"]["eingehend"] == 0
    assert "Firewall freigeben" in status["tipp"] and "Router" in status["tipp"]


def test_diagnose_versteckte_adresse_und_nichts_kommt_an(relay):
    status = _scheitern(relay, mdns=True, mdns_aufloeser=lambda name: None)
    assert status["grund"] == "mdns"
    assert "Chrome" in status["tipp"] and "Firewall freigeben" in status["tipp"]


def test_diagnose_anderes_netz(relay):
    status = _scheitern(relay, pc_netze=lambda: [ipaddress.ip_network("10.99.0.0/16")])
    assert status["grund"] == "anderes-netz"
    assert status["diagnose"]["netz_passt"] is False
    assert "verschiedenen Netzen" in status["fehler"] and "10.99.0.0/16" in status["fehler"]
    assert "G\u00e4ste-WLAN" in status["tipp"]


def test_kein_lan_angebot_hat_grund_und_tipp(relay):
    kamera = _kamera(relay, lan_pruefung=lambda adresse: False)
    info = kamera.start()
    handy = FakeHandy(info.link, relay)
    ht = HandyThread(handy)
    try:
        assert ht.rufe(handy.verbinden()).daten["grund"] == "kein-lan"  # Protokoll unveraendert
        assert kamera.warte_auf("fehler", 5)
        status = kamera.status()
        assert status["grund"] == "kein-lan" and status["verbindung_gescheitert"]
        assert status["diagnose"]["kandidaten"]["nicht_lan"] >= 1 and status["diagnose"]["kandidaten"]["ip"] == 0
        assert "mobile Daten" in status["tipp"]
    finally:
        kamera.stop()
        ht.ende()


# -- Nur LAN: auch aufgeloeste und peer-reflexive Adressen werden geprueft ---------------------------
def test_aufloesung_auf_oeffentliche_adresse_wird_verworfen(relay):
    kamera = _kamera(relay, lan_pruefung=sig.ist_lan_adresse, mdns_aufloeser=lambda name: "8.8.8.8")
    assert asyncio.run(kamera._mdns_aufloesen(["abc.local"])) == {}
    kamera = _kamera(relay, mdns_aufloeser=lambda name: "abc2.local")  # nie wieder ein Name
    assert asyncio.run(kamera._mdns_aufloesen(["abc.local"])) == {}


def test_aufloesung_auf_8888_verbindet_nur_ueber_die_echte_adresse(relay):
    kamera = _kamera(relay, mdns_aufloeser=lambda name: "8.8.8.8")
    info = kamera.start()
    handy = FakeHandy(info.link, relay, mdns=True)
    ht = HandyThread(handy)
    try:
        assert ht.rufe(handy.verbinden()).typ == "antwort"
        assert kamera.warte_auf("verbunden", 20), kamera.status()
        assert kamera.status()["diagnose"]["mdns_aufgeloest"] == 0
        ferne = _ferne_adressen(kamera._pc)
        assert ferne and "8.8.8.8" not in ferne and all(lan_fuer_test(a) for a in ferne)
    finally:
        kamera.stop()
        ht.ende()


def _ferne_adressen(pc):
    return [c.ip for t in pc.getTransceivers() for c in t.receiver.transport.transport.getRemoteCandidates()]


def test_windows_gemischtes_angebot_ohne_local_namen(relay):
    gefragt = []
    kamera = _kamera(relay, aiortc_mdns=False, mdns_aufloeser=lambda name: gefragt.append(name))
    info = kamera.start()
    name = "0d6f7a1e-2b3c-4d5e-8f90-a1b2c3d4e5f6.local"
    handy = FakeHandy(info.link, relay, zusatz_kandidat=f"a=candidate:77 1 udp 2122260223 {name} 40001 typ host")
    ht = HandyThread(handy)
    try:
        assert ht.rufe(handy.verbinden()).typ == "antwort"
        assert kamera.warte_auf("verbunden", 20), kamera.status()
        assert gefragt == [name]  # auch im gemischten Angebot aufgeloest (hier: ohne Erfolg) ...
        assert not any(a.endswith(".local") for a in _ferne_adressen(kamera._pc))  # ... und weggelassen
    finally:
        kamera.stop()
        ht.ende()


def test_peer_reflexive_pruefung_von_ausserhalb_des_lan_wird_getrennt(relay):
    """Handy versteckt seine Adresse; die Pruefpakete kommen von einer Adresse, die NICHT als LAN gilt
    -> Nova lernt sie (peer-reflexiv), trennt aber, statt zu verbinden."""
    verboten = set()

    def lan(adresse):
        return adresse not in verboten and (sig.ist_mdns_name(adresse) or lan_fuer_test(adresse))

    def sperren(antwort):  # ab jetzt gelten alle echten Adressen dieses Rechners als "Internet"
        for zeile in antwort.daten["sdp"].split("\r\n"):
            if zeile.startswith("a=candidate:"):
                verboten.add(zeile.split()[4])

    kamera = _kamera(relay, lan_pruefung=lan, mdns_aufloeser=lambda name: None)
    info = kamera.start()
    handy = FakeHandy(info.link, relay, mdns=True, vor_antwort=sperren)
    ht = HandyThread(handy)
    try:
        assert ht.rufe(handy.verbinden()).typ == "antwort" and verboten
        assert kamera.warte_auf("fehler", 20), kamera.status()
        assert kamera.status()["grund"] == "nicht-lan"
        time.sleep(0.5)
        assert kamera.zustand == "fehler" and kamera.latest_frame() is None
    finally:
        kamera.stop()
        ht.ende()


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _fake_pc(connection=None, ferne=()):
    ice = _Obj(getRemoteCandidates=lambda: [_Obj(ip=a) for a in ferne])
    if connection is not None:
        ice._connection = connection
    transceiver = _Obj(receiver=_Obj(transport=_Obj(transport=ice)))
    return _Obj(getTransceivers=lambda: [transceiver], sctp=None)


def test_paar_im_lan_im_zweifel_nein():
    kamera = HandyKamera(sig.SpeicherRelay(), lan_pruefung=sig.ist_lan_adresse)
    paar = lambda ip: _Obj(remote_addr=(ip, 5000))  # noqa: E731
    assert kamera._paar_im_lan(_fake_pc(_Obj(_nominated={1: paar("192.168.178.20")}))) is True
    assert kamera._paar_im_lan(_fake_pc(_Obj(_nominated={1: paar("8.8.8.8")}))) is False
    # interne Struktur fehlt -> Ersatzpruefung ueber die Kandidaten der Gegenseite
    assert kamera._paar_im_lan(_fake_pc(None, ["192.168.178.20"])) is True
    assert kamera._paar_im_lan(_fake_pc(None, ["192.168.178.20", "8.8.8.8"])) is False
    assert kamera._paar_im_lan(_fake_pc(None, [])) is False  # nichts bekannt -> trennen
    assert kamera._paar_im_lan(_fake_pc(_Obj(), ["10.0.0.5"])) is True  # ohne _nominated -> Ersatz

    def kaputt():
        raise RuntimeError("anders gebaut")

    assert kamera._paar_im_lan(_Obj(getTransceivers=kaputt, sctp=None)) is False  # Ausnahme -> trennen
