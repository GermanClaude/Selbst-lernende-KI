"""Anrufe ueber Vonage - JWT-Unterschrift, Gespraechsablauf, Rueckkanal, Werkzeug. Ohne Netz und ohne echten
Schluessel (der Test-Schluessel wird hier erzeugt)."""
import base64
import hashlib
import json
import random
import urllib.error
import urllib.request

import pytest

from assistant import anruf as A
from assistant import anruf_vonage as V
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry


# ---------------------------------------------------------------- Test-Schluessel (reines Python)
def _primzahl(bits, rnd):
    while True:
        p = rnd.getrandbits(bits) | (3 << (bits - 2)) | 1      # oberste 2 Bits: n hat volle 2*bits Bit
        if all(p % q for q in _KLEINE) and all(pow(a, p - 1, p) == 1 for a in (2, 3, 5, 7, 11)):
            return p


_KLEINE = [q for q in range(3, 2000, 2) if all(q % t for t in range(3, int(q ** 0.5) + 1, 2))]


def _der(tag, inhalt):
    n = len(inhalt)
    laenge = bytes([n]) if n < 128 else bytes([0x80 | ((n.bit_length() + 7) // 8)]) + n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([tag]) + laenge + inhalt


def _int(x):
    b = x.to_bytes((x.bit_length() + 8) // 8 or 1, "big")
    return _der(0x02, b)


@pytest.fixture(scope="module")
def schluessel():
    rnd = random.Random(42)
    e = 65537
    while True:
        p, q = _primzahl(512, rnd), _primzahl(512, rnd)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            break
    n, d = p * q, pow(e, -1, phi)
    pkcs1 = _der(0x30, b"".join(_int(x) for x in (0, n, e, d, p, q, d % (p - 1), d % (q - 1), pow(q, -1, p))))
    algo = _der(0x30, _der(0x06, bytes.fromhex("2a864886f70d010101")) + b"\x05\x00")
    pkcs8 = _der(0x30, _int(0) + algo + _der(0x04, pkcs1))

    def pem(der, art):
        b64 = base64.b64encode(der).decode()
        return f"-----BEGIN {art}-----\n" + "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64)) + f"\n-----END {art}-----\n"

    return {"n": n, "e": e, "d": d, "pkcs8": pem(pkcs8, "PRIVATE KEY"), "pkcs1": pem(pkcs1, "RSA PRIVATE KEY")}


def _pruefen(signatur: bytes, daten: bytes, n: int, e: int) -> bool:
    k = (n.bit_length() + 7) // 8
    em = pow(int.from_bytes(signatur, "big"), e, n).to_bytes(k, "big")
    return em.endswith(V._SHA256_INFO + hashlib.sha256(daten).digest()) and em.startswith(b"\x00\x01\xff")


@pytest.mark.parametrize("art", ["pkcs8", "pkcs1"])
def test_schluessel_lesen_beide_formate(schluessel, art):
    assert V.schluessel_laden(schluessel[art]) == (schluessel["n"], schluessel["d"])


def test_kaputte_schluessel_werden_abgelehnt():
    for falsch in ("", "hallo", "-----BEGIN ENCRYPTED PRIVATE KEY-----\nAAAA\n-----END ENCRYPTED PRIVATE KEY-----",
                   "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----"):
        with pytest.raises(A.AnrufFehler):
            V.schluessel_laden(falsch)


def test_jwt_ist_gueltig_unterschrieben(schluessel):
    token = V.jwt_erstellen("app-123", schluessel["pkcs8"], jetzt=1_800_000_000)
    kopf, inhalt, sig = token.split(".")
    pad = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))  # noqa: E731
    assert json.loads(pad(kopf)) == {"alg": "RS256", "typ": "JWT"}
    claims = json.loads(pad(inhalt))
    assert claims["application_id"] == "app-123" and claims["iat"] == 1_800_000_000
    assert claims["exp"] - claims["iat"] == 900 and claims["jti"]
    assert _pruefen(pad(sig), f"{kopf}.{inhalt}".encode(), schluessel["n"], schluessel["e"])


# ---------------------------------------------------------------- Gespraechsablauf
def test_ansage_ohne_rueckkanal():
    ncco = V.ncco_bauen("Der Download ist fertig.", "Nova")
    assert len(ncco) == 1 and ncco[0]["action"] == "talk" and ncco[0]["language"] == "de-DE"
    assert ncco[0]["text"].startswith("Hallo, hier ist Nova") and ncco[0]["text"].count("Download ist fertig") == 2
    assert "Telegram" in ncco[0]["text"]


def test_frage_mit_rueckkanal():
    ncco = V.ncco_bauen("Soll ich die Backups loeschen?", "Nova", "https://x.trycloudflare.com/vonage/g/antwort")
    assert [a["action"] for a in ncco] == ["talk", "input"]
    assert ncco[0]["bargeIn"] is True and ncco[1]["type"] == ["speech"]
    assert ncco[1]["eventUrl"] == ["https://x.trycloudflare.com/vonage/g/antwort"]
    assert ncco[1]["speech"]["language"] == "de-DE"


def _post(url, daten):
    req = urllib.request.Request(url, data=json.dumps(daten).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read() or b"{}")


def test_rueckkanal_nimmt_die_antwort_an():
    kanal = V.Rueckkanal("Soll ich loeschen?")
    kanal.starten()
    try:
        basis = f"http://127.0.0.1:{kanal.port}"
        ncco = _post(basis + kanal.pfad("antwort"),
                     {"speech": {"results": [{"confidence": "0.9", "text": "ja mach das"}]}, "uuid": "u"})
        assert kanal.antworten == ["ja mach das"] and ncco == [V._sprich(V.DANKE)]
        _post(basis + kanal.pfad("event"), {"status": "answered"})
        assert kanal.status == ["answered"]
        with pytest.raises(urllib.error.HTTPError) as fehler:              # ohne Geheimnis: nichts
            _post(basis + "/vonage/falsch/antwort", {"speech": {"results": [{"text": "boese"}]}})
        assert fehler.value.code == 404 and kanal.antworten == ["ja mach das"]
    finally:
        kanal.stoppen()


def test_rueckkanal_fragt_einmal_nach_und_gibt_dann_auf():
    kanal = V.Rueckkanal("Soll ich loeschen?", oeffentlich="https://x.trycloudflare.com")
    erst = kanal.antwort_ncco({"speech": {"timeout_reason": "start_timeout", "results": []}})
    assert erst[0]["text"].startswith(V.NOCHMAL) and "Soll ich loeschen?" in erst[0]["text"]
    assert erst[1]["eventUrl"] == [kanal.url("antwort")]
    assert kanal.antwort_ncco({"speech": {}}) == [V._sprich(V.SPAETER)] and kanal.antworten == []


def test_tunnel_adresse_aus_cloudflared(monkeypatch):
    class FakeProzess:
        stderr = iter(["INF Requesting new quick Tunnel...\n",
                       "INF |  https://abc-def-123.trycloudflare.com  |\n"])

        def terminate(self):
            pass

    monkeypatch.setattr(V.subprocess, "Popen", lambda *a, **k: FakeProzess())
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    kanal = V.Rueckkanal("x", port=1234)
    assert kanal.tunnel_starten("cloudflared", warte=5)
    assert kanal.url("antwort").startswith("https://abc-def-123.trycloudflare.com/vonage/")


# ---------------------------------------------------------------- API
class FakeVonage:
    def __init__(self, status=("completed",)):
        self.aufrufe, self.status = [], list(status)

    def __call__(self, token, method, pfad, body, timeout):
        self.aufrufe.append((token, method, pfad, body))
        if method == "POST":
            return {"uuid": "call-1", "status": "started"}
        return {"status": self.status.pop(0) if len(self.status) > 1 else self.status[0], "duration": "42"}


def test_anruf_auftrag(schluessel):
    fake = FakeVonage()
    v = V.Vonage("app-1", schluessel["pkcs8"], transport=fake)
    assert v.anrufen("+491711234567", V.ncco_bauen("Hallo"), max_minuten=99) == "call-1"
    token, method, pfad, body = fake.aufrufe[0]
    assert (method, pfad) == ("POST", "/calls") and token.count(".") == 2
    assert body["to"] == [{"type": "phone", "number": "491711234567"}]
    assert body["from"] == {"type": "phone", "number": V.TEST_ABSENDER}      # Testzugang ohne eigene Nummer
    assert body["length_timer"] == 15 * 60 and "event_url" not in body


def test_warten_bis_ende(schluessel):
    fake = FakeVonage(status=("ringing", "answered", "completed"))
    v = V.Vonage("app-1", schluessel["pkcs8"], transport=fake)
    info = V.warte_auf_ende(v, "call-1", max_sekunden=60, intervall=0, schlafen=lambda s: None)
    assert info["status"] == "completed"


# ---------------------------------------------------------------- Werkzeug
def _ctx(tmp_path, away=True):
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=False), tmp_path,
                           confirm_fn=lambda m, r: True)
    pm.away = away
    return ToolContext(permissions=pm, memory=None, extra={"app_root": tmp_path, "ki_name": lambda: "Nova"})


@pytest.fixture
def vonage_da(tmp_path, monkeypatch, schluessel):
    monkeypatch.delenv("BLAND_API_KEY", raising=False)
    monkeypatch.delenv("ANRUF_ANBIETER", raising=False)
    monkeypatch.delenv("VONAGE_NUMMER", raising=False)
    monkeypatch.setenv("VONAGE_APP_ID", "app-1")
    monkeypatch.setenv("ANRUF_NUMMER", "0171 1234567")
    V.schluessel_speichern(tmp_path, schluessel["pkcs8"])
    fake = FakeVonage()
    monkeypatch.setattr(V.Vonage, "__init__", lambda self, app_id, pem, absender="", transport=None: (
        setattr(self, "app_id", app_id), setattr(self, "pem", pem), setattr(self, "absender", absender),
        setattr(self, "transport", fake))[0])
    return fake


def test_werkzeug_waehlt_vonage_mit_antwort(tmp_path, monkeypatch, vonage_da):
    kanal = V.Rueckkanal("x", oeffentlich="https://t.trycloudflare.com")
    kanal.antworten.append("ja bitte loeschen")
    monkeypatch.setattr(V, "rueckkanal_oeffnen", lambda frage, root=None: kanal)
    out, _ = build_registry().execute(_ctx(tmp_path), "anrufen", {"anliegen": "Soll ich loeschen?"})
    body = vonage_da.aufrufe[0][3]
    assert body["ncco"][1]["action"] == "input" and body["event_url"] == [kanal.url("event")]
    assert "ja bitte loeschen" in out and A.heute_anzahl(tmp_path) == 1


def test_werkzeug_ohne_rueckkanal_nur_ansage(tmp_path, monkeypatch, vonage_da):
    monkeypatch.setattr(V, "rueckkanal_oeffnen", lambda frage, root=None: None)
    out, _ = build_registry().execute(_ctx(tmp_path), "anrufen", {"anliegen": "Download fertig."})
    assert [a["action"] for a in vonage_da.aufrufe[0][3]["ncco"]] == ["talk"]
    assert "nur eine Ansage" in out


def test_anbieter_wahl(tmp_path, monkeypatch, vonage_da):
    from assistant.tools.anruf import einstellungen

    assert einstellungen(tmp_path)["anbieter"] == "vonage"
    monkeypatch.setenv("BLAND_API_KEY", "KEY")
    assert einstellungen(tmp_path)["anbieter"] == "bland"            # beide da: Bland bleibt Standard ...
    monkeypatch.setenv("ANRUF_ANBIETER", "vonage")
    assert einstellungen(tmp_path)["anbieter"] == "vonage"           # ... ausser du waehlst Vonage
