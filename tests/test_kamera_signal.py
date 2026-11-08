"""Handy-Kamera: Kopplung, Verschluesselung, Nachrichten, Relais (ohne Netz)."""
import json

import pytest

pytest.importorskip("cryptography")

from assistant.kamera import signal as sig  # noqa: E402

# Ein realistisches Angebot (Chrome/Android, VP8+H264 nach setCodecPreferences, Video + DataChannel,
# alle Kandidaten gesammelt) - so gross wird es in der Praxis.
SDP_ANGEBOT = "\r\n".join([
    "v=0", "o=- 4611731400430051336 2 IN IP4 127.0.0.1", "s=-", "t=0 0",
    "a=group:BUNDLE 0 1", "a=extmap-allow-mixed", "a=msid-semantic: WMS 3c1d2a7e-8f5b-4e8e-9a4b-1f2e3d4c5b6a",
    "m=video 9 UDP/TLS/RTP/SAVPF 96 97 102 103 104 105 106 107",
    "c=IN IP4 0.0.0.0", "a=rtcp:9 IN IP4 0.0.0.0",
    "a=candidate:1467250027 1 udp 2122260223 192.168.178.34 56143 typ host generation 0 network-id 1 network-cost 10",
    "a=candidate:2829546383 1 udp 2122129151 fd00::1c2e:5bff:fe3a:9f01 49237 typ host generation 0 network-id 2 network-cost 10",
    "a=candidate:3156217587 1 udp 2122197247 2003:e3:7f1d:4500:1c2e:5bff:fe3a:9f01 54011 typ host generation 0 network-id 3 network-cost 10",
    "a=candidate:467250027 1 tcp 1518280447 192.168.178.34 9 typ host tcptype active generation 0 network-id 1 network-cost 10",
    "a=candidate:1829546383 1 tcp 1518149375 fd00::1c2e:5bff:fe3a:9f01 9 typ host tcptype active generation 0 network-id 2 network-cost 10",
    "a=candidate:4156217587 1 tcp 1518217471 2003:e3:7f1d:4500:1c2e:5bff:fe3a:9f01 9 typ host tcptype active generation 0 network-id 3 network-cost 10",
    "a=ice-ufrag:Xa3n", "a=ice-pwd:mP1sV8xQ2dF5gH7jK9lZ0aBcDeFgHiJk", "a=ice-options:trickle",
    "a=fingerprint:sha-256 3A:5F:8B:12:C4:D9:E0:71:2B:6C:AF:33:90:1D:E8:47:B5:62:0C:9E:F1:4A:D7:83:2E:6B:19:C0:5D:A8:F3:74",
    "a=setup:actpass", "a=mid:0",
    "a=extmap:1 urn:ietf:params:rtp-hdrext:toffset",
    "a=extmap:2 http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time",
    "a=extmap:3 urn:3gpp:video-orientation",
    "a=extmap:4 http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01",
    "a=extmap:5 http://www.webrtc.org/experiments/rtp-hdrext/playout-delay",
    "a=extmap:6 http://www.webrtc.org/experiments/rtp-hdrext/video-content-type",
    "a=extmap:7 http://www.webrtc.org/experiments/rtp-hdrext/video-timing",
    "a=extmap:8 http://www.webrtc.org/experiments/rtp-hdrext/color-space",
    "a=extmap:9 urn:ietf:params:rtp-hdrext:sdes:mid",
    "a=extmap:10 urn:ietf:params:rtp-hdrext:sdes:rtp-stream-id",
    "a=extmap:11 urn:ietf:params:rtp-hdrext:sdes:repaired-rtp-stream-id",
    "a=sendonly", "a=msid:3c1d2a7e-8f5b-4e8e-9a4b-1f2e3d4c5b6a 7b8c9d0e-1f2a-3b4c-5d6e-7f8a9b0c1d2e",
    "a=rtcp-mux", "a=rtcp-rsize",
    "a=rtpmap:96 VP8/90000", "a=rtcp-fb:96 goog-remb", "a=rtcp-fb:96 transport-cc", "a=rtcp-fb:96 ccm fir",
    "a=rtcp-fb:96 nack", "a=rtcp-fb:96 nack pli", "a=rtpmap:97 rtx/90000", "a=fmtp:97 apt=96",
    "a=rtpmap:102 H264/90000", "a=rtcp-fb:102 goog-remb", "a=rtcp-fb:102 transport-cc", "a=rtcp-fb:102 ccm fir",
    "a=rtcp-fb:102 nack", "a=rtcp-fb:102 nack pli",
    "a=fmtp:102 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42001f",
    "a=rtpmap:103 rtx/90000", "a=fmtp:103 apt=102",
    "a=rtpmap:104 H264/90000", "a=rtcp-fb:104 goog-remb", "a=rtcp-fb:104 transport-cc", "a=rtcp-fb:104 ccm fir",
    "a=rtcp-fb:104 nack", "a=rtcp-fb:104 nack pli",
    "a=fmtp:104 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f",
    "a=rtpmap:105 rtx/90000", "a=fmtp:105 apt=104",
    "a=rtpmap:106 H264/90000", "a=rtcp-fb:106 goog-remb", "a=rtcp-fb:106 transport-cc", "a=rtcp-fb:106 ccm fir",
    "a=rtcp-fb:106 nack", "a=rtcp-fb:106 nack pli",
    "a=fmtp:106 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=4d001f",
    "a=rtpmap:107 rtx/90000", "a=fmtp:107 apt=106",
    "a=ssrc-group:FID 2231627014 632943048",
    "a=ssrc:2231627014 cname:4TOk42mSjXCkVIa6", "a=ssrc:2231627014 msid:3c1d2a7e-8f5b-4e8e-9a4b-1f2e3d4c5b6a 7b8c9d0e-1f2a-3b4c-5d6e-7f8a9b0c1d2e",
    "a=ssrc:632943048 cname:4TOk42mSjXCkVIa6", "a=ssrc:632943048 msid:3c1d2a7e-8f5b-4e8e-9a4b-1f2e3d4c5b6a 7b8c9d0e-1f2a-3b4c-5d6e-7f8a9b0c1d2e",
    "m=application 9 UDP/DTLS/SCTP webrtc-datachannel", "c=IN IP4 0.0.0.0",
    "a=candidate:1467250027 1 udp 2122260223 192.168.178.34 51533 typ host generation 0 network-id 1 network-cost 10",
    "a=ice-ufrag:Xa3n", "a=ice-pwd:mP1sV8xQ2dF5gH7jK9lZ0aBcDeFgHiJk", "a=ice-options:trickle",
    "a=fingerprint:sha-256 3A:5F:8B:12:C4:D9:E0:71:2B:6C:AF:33:90:1D:E8:47:B5:62:0C:9E:F1:4A:D7:83:2E:6B:19:C0:5D:A8:F3:74",
    "a=setup:actpass", "a=mid:1", "a=sctp-port:5000", "a=max-message-size:262144", "",
])


class Uhr:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def _paar(uhr=None):
    uhr = uhr or Uhr()
    kopplung = sig.Kopplung.neu(uhr=uhr)
    return kopplung, sig.Kanal(kopplung, "n", uhr), sig.Kanal(kopplung, "h", uhr)


# -- Kopplung / Fragment -------------------------------------------------------------------
def test_kopplung_link_rundweg_und_laenge():
    uhr = Uhr()
    k = sig.Kopplung.neu(uhr=uhr)
    link = k.link()
    assert link.startswith(sig.STANDARD_BASIS_URL + "#p=")
    assert len(k.payload()) == 72
    zurueck = sig.Kopplung.aus_link(link, jetzt=uhr())
    assert zurueck == k
    assert zurueck.ablauf == int(uhr() + sig.GUELTIG_S)
    assert len(k.thema) == 22


def test_kopplung_repr_verraet_schluessel_nicht():
    k = sig.Kopplung.neu()
    assert k.schluessel.hex() not in repr(k)
    assert sig.b64u(k.schluessel) not in repr(k)


def test_kopplung_abgelaufen_wird_abgelehnt():
    uhr = Uhr()
    k = sig.Kopplung.neu(gueltig=300, uhr=uhr)
    sig.Kopplung.aus_payload(k.payload(), jetzt=uhr() + 299)
    with pytest.raises(sig.SignalFehler, match="abgelaufen"):
        sig.Kopplung.aus_payload(k.payload(), jetzt=uhr() + 301)


@pytest.mark.parametrize("kaputt", ["", "abc", "!!!!", "A" * 71, "A" * 80])
def test_kopplung_kaputt(kaputt):
    with pytest.raises(sig.SignalFehler):
        sig.Kopplung.aus_payload(kaputt)


def test_kopplung_falsche_version():
    k = sig.Kopplung.neu()
    roh = bytearray(sig.b64u_dekodieren(k.payload()))
    roh[0] = 9
    with pytest.raises(sig.SignalFehler, match="Version"):
        sig.Kopplung.aus_payload(sig.b64u(bytes(roh)))


def test_link_ohne_fragment():
    with pytest.raises(sig.SignalFehler, match="fehlt"):
        sig.Kopplung.aus_link(sig.STANDARD_BASIS_URL)


# -- Verschluesselung ----------------------------------------------------------------------
def test_verschluesselung_rundweg():
    k = sig.Kopplung.neu()
    text = sig.verschluesseln(k.schluessel, k.thema, b"hallo welt")
    assert sig.entschluesseln(k.schluessel, k.thema, text) == b"hallo welt"


def test_falscher_schluessel_wird_abgelehnt():
    k, k2 = sig.Kopplung.neu(), sig.Kopplung.neu()
    text = sig.verschluesseln(k.schluessel, k.thema, b"geheim")
    with pytest.raises(sig.SignalFehler, match="ungültig"):
        sig.entschluesseln(k2.schluessel, k.thema, text)


def test_anderes_thema_wird_abgelehnt():
    k, k2 = sig.Kopplung.neu(), sig.Kopplung.neu()
    text = sig.verschluesseln(k.schluessel, k.thema, b"geheim")
    with pytest.raises(sig.SignalFehler):
        sig.entschluesseln(k.schluessel, k2.thema, text)


def test_veraenderte_nachricht_wird_abgelehnt():
    k, nova, handy = _paar()
    text = nova.verpacke("antwort", {"sdp": "v=0"})
    roh = bytearray(sig.b64u_dekodieren(text))
    roh[20] ^= 0x01
    with pytest.raises(sig.SignalFehler):
        handy.oeffne(sig.b64u(bytes(roh)))


def test_packen_rundweg_und_bombe():
    daten = SDP_ANGEBOT.encode()
    gepackt = sig.packen(daten)
    assert gepackt[0] == 1 and len(gepackt) < len(daten)
    assert sig.entpacken(gepackt) == daten
    assert sig.packen(b"x")[0] == 0
    bombe = sig.packen(b"\x00" * (sig.MAX_KLARTEXT * 4))
    with pytest.raises(sig.SignalFehler, match="gro"):
        sig.entpacken(bombe)


# -- Nachrichten ---------------------------------------------------------------------------
def test_nachricht_mit_realistischem_sdp_bleibt_unter_4096():
    _, nova, handy = _paar()
    text = handy.verpacke("angebot", {"sdp": SDP_ANGEBOT, "g": "a1b2c3d4e5f60718"})
    assert len(text) < 4096
    nachricht = nova.oeffne(text)
    assert nachricht.typ == "angebot" and nachricht.daten["sdp"] == SDP_ANGEBOT
    assert SDP_ANGEBOT not in repr(nachricht)


def test_zu_grosse_nachricht():
    import os

    _, nova, _ = _paar()
    with pytest.raises(sig.SignalFehler, match="zu gro"):
        nova.verpacke("angebot", {"sdp": sig.b64u(os.urandom(4000))})


def test_eigene_nachricht_ist_echo():
    _, nova, _ = _paar()
    assert nova.oeffne(nova.verpacke("antwort", {})) is None


def test_wiederholung_wird_abgelehnt():
    _, nova, handy = _paar()
    t1 = handy.verpacke("angebot", {"sdp": "a"})
    t2 = handy.verpacke("tschuess", {})
    assert nova.oeffne(t1).seq == 1
    assert nova.oeffne(t2).seq == 2
    with pytest.raises(sig.SignalFehler, match="wiederholt"):
        nova.oeffne(t1)
    with pytest.raises(sig.SignalFehler, match="wiederholt"):
        nova.oeffne(t2)


def test_veraltete_nachricht_wird_abgelehnt():
    uhr = Uhr()
    _, nova, handy = _paar(uhr)
    text = handy.verpacke("angebot", {})
    uhr.t += sig.MAX_UHR_ABWEICHUNG_S + 1
    with pytest.raises(sig.SignalFehler, match="veraltet"):
        nova.oeffne(text)


def test_falsches_format_wird_abgelehnt():
    k, nova, _ = _paar()
    for inhalt in ([1, 2], {"t": "x", "s": 0, "z": 1, "f": "h", "d": {}},
                   {"t": "x", "s": 1, "z": 1, "f": "q", "d": {}}, {"t": "x", "s": True, "z": 1, "f": "h", "d": {}}):
        text = sig.verschluesseln(k.schluessel, k.thema, sig.packen(json.dumps(inhalt).encode()))
        with pytest.raises(sig.SignalFehler, match="Format"):
            nova.oeffne(text)


# -- Kurzcode ------------------------------------------------------------------------------
def test_code_normalisieren():
    assert sig.code_normalisieren("7kq2-m9xd") == "7KQ2M9XD"
    assert sig.code_normalisieren("o1l2 i3ab") == "0112" + "13AB"
    assert sig.code_anzeige("7KQ2M9XD") == "7KQ2-M9XD"
    with pytest.raises(sig.SignalFehler):
        sig.code_normalisieren("123")
    with pytest.raises(sig.SignalFehler):
        sig.code_normalisieren("ABCDEFGU")  # U gibt es nicht


def test_code_nachricht_enthaelt_kopplung():
    uhr = Uhr()
    k = sig.Kopplung.neu(uhr=uhr)
    code = sig.neuer_code()
    thema, text = sig.code_nachricht(k, code, uhr)
    ck = sig.code_kopplung(code.lower(), k.ablauf)
    assert ck.thema == thema and thema != k.thema
    nachricht = sig.Kanal(ck, "h", uhr).oeffne(text)
    assert nachricht.typ == "kopplung"
    assert sig.Kopplung.aus_payload(nachricht.daten["p"]) == k


# -- LAN-Filter ----------------------------------------------------------------------------
@pytest.mark.parametrize("adresse,ok", [
    ("192.168.1.5", True), ("10.0.0.1", True), ("172.16.5.4", True), ("172.31.255.1", True),
    ("169.254.10.1", True), ("fd00::1", True), ("fe80::1%eth0", True), ("abcd1234-5678.local", True),
    ("172.32.0.1", False), ("8.8.8.8", False), ("100.64.1.1", False), ("127.0.0.1", False),
    ("2003:e3::1", False), ("::1", False), ("::ffff:8.8.8.8", False), ("::ffff:192.168.0.2", True),
    ("evil.example.com", False), ("", False), ("a.b.local", False),
])
def test_lan_adresse(adresse, ok):
    assert sig.ist_lan_adresse(adresse) is ok


def test_filtere_sdp_wirft_oeffentliche_kandidaten_raus():
    sdp, behalten, verworfen = sig.filtere_sdp(SDP_ANGEBOT)
    assert behalten == 5 and verworfen == 2
    assert "2003:e3:" not in sdp and "192.168.178.34" in sdp
    zusatz = SDP_ANGEBOT.replace("a=ice-ufrag:Xa3n\r\n", "a=candidate:9 1 udp 1 203.0.113.9 3478 typ srflx "
                                 "raddr 192.168.178.34 rport 1\r\na=ice-ufrag:Xa3n\r\n", 1)
    _, b2, v2 = sig.filtere_sdp(zusatz)
    assert (b2, v2) == (5, 3)  # srflx wird nie genommen


# -- Relais --------------------------------------------------------------------------------
class FakeAntwort:
    def __init__(self, status=200, zeilen=(), daten=None, fehler_beim_lesen=None):
        self.status_code = status
        self._zeilen = list(zeilen)
        self._daten = daten or {}
        self._fehler = fehler_beim_lesen
        self.geschlossen = False

    def json(self):
        return self._daten

    def iter_lines(self):
        for zeile in self._zeilen:
            yield zeile.encode() if isinstance(zeile, str) else zeile
        if self._fehler:
            raise self._fehler

    def close(self):
        self.geschlossen = True


class FakeSitzung:
    def __init__(self, antworten):
        self.antworten = list(antworten)
        self.aufrufe = []

    def _naechste(self):
        a = self.antworten.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    def post(self, url, **kw):
        self.aufrufe.append(("POST", url, kw))
        return self._naechste()

    def get(self, url, **kw):
        self.aufrufe.append(("GET", url, kw))
        return self._naechste()


def test_ntfy_senden():
    s = FakeSitzung([FakeAntwort(daten={"id": "abc123", "event": "message"})])
    relay = sig.NtfyRelay(session=s)
    assert relay.senden("thema_1", "TEXT") == "abc123"
    methode, url, kw = s.aufrufe[0]
    assert (methode, url) == ("POST", "https://ntfy.sh/thema_1")
    assert kw["data"] == b"TEXT" and kw["headers"]["X-Firebase"] == "no"
    assert all(isinstance(t, (int, float)) for t in kw["timeout"])


def test_ntfy_senden_fehler():
    relay = sig.NtfyRelay(session=FakeSitzung([FakeAntwort(status=429)]))
    with pytest.raises(sig.RelayFehler, match="bremst"):
        relay.senden("t", "x")
    relay = sig.NtfyRelay(session=FakeSitzung([OSError("kein Netz")]))
    with pytest.raises(sig.RelayFehler, match="erreichbar"):
        relay.senden("t", "x")
    with pytest.raises(sig.RelayFehler, match="Kanalname"):
        relay.senden("../admin", "x")
    with pytest.raises(sig.RelayFehler, match="gro"):
        sig.NtfyRelay(session=FakeSitzung([])).senden("t", "x" * 5000)


def test_ntfy_empfangen_liest_stream():
    zeilen = [json.dumps({"id": "o1", "event": "open", "topic": "t"}), "",
              json.dumps({"id": "k1", "event": "keepalive"}),
              json.dumps({"id": "m1", "time": 1700000000, "event": "message", "message": "NACHRICHT"}),
              json.dumps({"id": "m2", "time": 1700000001, "event": "message", "message": "ZWEITE"})]
    antwort = FakeAntwort(zeilen=zeilen)
    s = FakeSitzung([antwort])
    relay = sig.NtfyRelay(session=s)
    ergebnis = relay.empfangen("t", "123", 5)
    assert [(n.id, n.text) for n in ergebnis] == [("m1", "NACHRICHT")]
    _, url, kw = s.aufrufe[0]
    assert url == "https://ntfy.sh/t/json" and kw["params"] == {"since": "123"} and kw["stream"] is True
    assert antwort.geschlossen


def test_ntfy_empfangen_timeout_ist_leer():
    class ReadTimeout(Exception):
        pass

    s = FakeSitzung([FakeAntwort(zeilen=[json.dumps({"event": "open"})], fehler_beim_lesen=ReadTimeout()),
                     ReadTimeout()])
    relay = sig.NtfyRelay(session=s)
    assert relay.empfangen("t", None, 1) == []
    assert s.aufrufe[0][2]["params"] == {"since": "all"}
    assert relay.empfangen("t", None, 1) == []


def test_ntfy_empfangen_status_fehler():
    relay = sig.NtfyRelay(session=FakeSitzung([FakeAntwort(status=500)]))
    with pytest.raises(sig.RelayFehler, match="500"):
        relay.empfangen("t", None, 1)


def test_ntfy_ist_relay():
    assert isinstance(sig.NtfyRelay(session=FakeSitzung([])), sig.Relay)
    assert isinstance(sig.SpeicherRelay(), sig.Relay)


def test_speicher_relay():
    import threading

    relay = sig.SpeicherRelay()
    assert relay.empfangen("t", None, 0.05) == []
    erste = relay.senden("t", "a")
    relay.senden("t", "b")
    assert [n.text for n in relay.empfangen("t", erste, 0)] == ["b"]
    assert [n.text for n in relay.empfangen("t", None, 0)] == ["a", "b"]
    threading.Timer(0.1, relay.senden, args=("u", "spaet")).start()
    assert [n.text for n in relay.empfangen("u", None, 3)] == ["spaet"]
    relay.schliessen()
    assert relay.empfangen("v", None, 3) == []
