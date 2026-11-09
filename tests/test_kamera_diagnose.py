"""Handy-Kamera: Fehlersuche (Kandidaten, Netze, Gruende) und Windows-Firewall-Freigabe.

Hier laeuft nie netsh und nie eine UAC-Abfrage - der Aufruf (_runas) ist immer ersetzt."""
import ipaddress
import json
import types
import urllib.error
import urllib.request

import pytest

from assistant.kamera import firewall, netz
from assistant.kamera import signal as sig

MDNS = "3f9c2b1e-7a4d-4c1b-9e8f-0a1b2c3d4e5f.local"


def _sdp(*kandidaten, ende=True):
    zeilen = ["v=0", "o=- 1 2 IN IP4 127.0.0.1", "s=-", "t=0 0", "m=video 9 UDP/TLS/RTP/SAVPF 96",
              "c=IN IP4 0.0.0.0"]
    zeilen += [f"a=candidate:{i} 1 udp 2122260223 {adresse} {50000 + i} typ {art}"
               for i, (adresse, art) in enumerate(kandidaten)]
    if ende:
        zeilen.append("a=end-of-candidates")
    zeilen += ["a=ice-ufrag:abcd", "a=mid:0", "m=application 9 UDP/DTLS/SCTP webrtc-datachannel"]
    zeilen += [f"a=candidate:{i} 1 udp 2122260223 {adresse} {50000 + i} typ {art}"
               for i, (adresse, art) in enumerate(kandidaten)]
    return "\r\n".join(zeilen) + "\r\n"


# -- signal: Kandidaten zaehlen, mDNS ersetzen ---------------------------------------------------
def test_kandidaten_zaehlen_nach_art_und_ohne_doppelte():
    sdp = _sdp(("192.168.178.34", "host"), (MDNS, "host"), ("8.8.8.8", "host"), ("192.168.178.34", "srflx"),
               ("2003:e3::1", "host"))
    zahl = sig.kandidaten_zaehlen(sdp)
    # jede Adresse steht zweimal im SDP (Video + DataChannel) - gezaehlt wird sie einmal
    assert (zahl.ip_lan, zahl.mdns, zahl.nicht_lan) == (1, 1, 3)
    assert zahl.lan_ips == ["192.168.178.34"] and zahl.mdns_namen == [MDNS]
    assert zahl.nutzbar == 2 and zahl.als_dict() == {"ip": 1, "mdns": 1, "nicht_lan": 3}


def test_nur_mdns_angebot_gilt_als_lan_und_wird_nicht_abgelehnt():
    sdp = _sdp((MDNS, "host"))
    gefiltert, behalten, verworfen = sig.filtere_sdp(sdp)
    assert behalten == 2 and verworfen == 0
    zahl = sig.kandidaten_zaehlen(sdp)
    assert zahl.ip_lan == 0 and zahl.mdns == 1


def test_mdns_ersetzen_und_kandidaten_ende_entfernen():
    sdp = _sdp((MDNS, "host"), ("192.168.1.9", "host"))
    neu = sig.mdns_ersetzen(sdp, {MDNS.upper(): "192.168.1.20"})
    assert MDNS not in neu and neu.count(" 192.168.1.20 50000 typ host") == 2
    assert sig.mdns_ersetzen(sdp, {}) == sdp
    assert sig.mdns_ersetzen(sdp, {"anderer.local": "192.168.1.5"}).count(MDNS) == 2
    ohne = sig.ohne_kandidaten_ende(neu)
    assert "end-of-candidates" not in ohne and ohne.endswith("\r\n") and ohne.count("a=candidate:") == 4


def test_ist_mdns_name():
    assert sig.ist_mdns_name(MDNS) and sig.ist_mdns_name("abc.local")
    assert not sig.ist_mdns_name("192.168.1.2") and not sig.ist_mdns_name("a b.local")
    assert not sig.ist_mdns_name("evil.local.example.com")


# -- netz: PC-Netze, Vergleich, Aufloesen -----------------------------------------------------------
def test_netzvergleich_mit_mehreren_pc_netzwerkkarten():
    wlan, kabel = ipaddress.ip_network("192.168.178.0/24"), ipaddress.ip_network("10.0.0.0/8")
    assert netz.im_selben_netz(["192.168.178.20"], [kabel, wlan]) is True       # WLAN passt
    assert netz.im_selben_netz(["10.4.5.6"], [wlan, kabel]) is True             # Kabel passt
    assert netz.im_selben_netz(["192.168.179.5"], [wlan]) is False              # Gaeste-WLAN (Fritzbox)
    assert netz.im_selben_netz(["192.168.179.5", "192.168.178.7"], [wlan]) is True
    assert netz.im_selben_netz([], [wlan]) is None                               # nur versteckte Adressen
    assert netz.im_selben_netz(["192.168.178.20"], []) is None                  # PC-Netze unbekannt
    assert netz.im_selben_netz(["fd00::1", "169.254.3.4", "kaputt"], [wlan]) is None


def test_netz_texte_fuer_die_anzeige():
    netze = [ipaddress.ip_network("192.168.178.0/24"), ipaddress.ip_network("10.0.0.0/8"),
             ipaddress.ip_network("192.168.178.0/24")]
    assert netz.netz_text(netze) == "192.168.178.x, 10.0.0.0/8"
    assert netz.ip_text(["192.168.179.5", "192.168.179.9", "fd00::1"]) == "192.168.179.x"


def test_pc_netze_aus_allen_netzwerkkarten(monkeypatch):
    ip = types.SimpleNamespace
    karten = [ip(ips=[ip(ip="192.168.178.30", network_prefix=24), ip(ip=("fe80::1", 0, 3), network_prefix=64)]),
              ip(ips=[ip(ip="192.168.178.31", network_prefix=24)]),          # WLAN und Kabel im selben Netz
              ip(ips=[ip(ip="10.1.2.3", network_prefix=16)]),
              ip(ips=[ip(ip="127.0.0.1", network_prefix=8), ip(ip="85.1.2.3", network_prefix=24)])]
    monkeypatch.setitem(__import__("sys").modules, "ifaddr", types.SimpleNamespace(get_adapters=lambda: karten))
    assert netz.pc_netze() == [ipaddress.ip_network("192.168.178.0/24"), ipaddress.ip_network("10.1.0.0/16")]


def test_mdns_aufloesen_nur_fuer_local_namen(monkeypatch):
    gefragt = []

    def getaddrinfo(name, *a, **kw):
        gefragt.append(name)
        return [(2, 2, 17, "", ("192.168.178.44", 0))]

    monkeypatch.setattr(netz.socket, "getaddrinfo", getaddrinfo)
    assert netz.mdns_aufloesen(MDNS) == "192.168.178.44"
    assert netz.mdns_aufloesen("example.com") is None and netz.mdns_aufloesen("") is None
    assert gefragt == [MDNS]

    def kaputt(*a, **kw):
        raise OSError("nicht gefunden")

    monkeypatch.setattr(netz.socket, "getaddrinfo", kaputt)
    assert netz.mdns_aufloesen(MDNS) is None


# -- Gruende -----------------------------------------------------------------------------------------
def test_grund_reihenfolge_und_texte():
    pytest.importorskip("cryptography")
    from assistant.kamera.webrtc import GRUENDE, VERBINDUNGS_GRUENDE, Versuch, ermittle_grund, grund_texte

    def v(**kw):
        versuch = Versuch(kandidaten=sig.KandidatenZahl(ip_lan=kw.pop("ip", 1), mdns=kw.pop("mdns", 0)))
        for k, wert in kw.items():
            setattr(versuch, k, wert)
        return versuch

    assert ermittle_grund(None) == "keine-verbindung"
    assert ermittle_grund(v(eingehend=0)) == "keine-pakete"
    assert ermittle_grund(v(eingehend=None)) == "keine-verbindung"          # nicht messbar
    assert ermittle_grund(v(ip=0, mdns=2, eingehend=0)) == "mdns"
    assert ermittle_grund(v(ip=0, mdns=2, eingehend=0, mdns_aufgeloest=1)) == "keine-pakete"
    assert ermittle_grund(v(eingehend=3)) == "einseitig"
    assert ermittle_grund(v(eingehend=3, nominiert=True)) == "abbruch"
    assert ermittle_grund(v(eingehend=0, netz_passt=False)) == "anderes-netz"  # schlaegt alles andere
    assert ermittle_grund(v(eingehend=0, netz_passt=True)) == "keine-pakete"
    for grund in VERBINDUNGS_GRUENDE:
        text, tipp = grund_texte(grund, v(handy_ips=["192.168.179.5"],
                                         pc_netze=[ipaddress.ip_network("192.168.178.0/24")]))
        assert text and tipp and "{" not in text, grund
    assert grund_texte("anderes-netz", v(handy_ips=["192.168.179.5"],
                                         pc_netze=[ipaddress.ip_network("192.168.178.0/24")]))[0] == \
        "Handy (192.168.179.x) und PC (192.168.178.x) sind in verschiedenen Netzen."
    assert set(VERBINDUNGS_GRUENDE) <= set(GRUENDE)
    # Firewall-Tipp bei allem, was auf blockierte Pakete deutet
    for grund in ("keine-pakete", "keine-verbindung", "mdns"):
        assert "Firewall freigeben" in GRUENDE[grund][1]
    assert "Chrome" in GRUENDE["mdns"][1]


def test_diagnose_ohne_geheimnisse():
    pytest.importorskip("cryptography")
    from assistant.kamera.webrtc import Versuch

    d = Versuch(kandidaten=sig.KandidatenZahl(ip_lan=1), handy_ips=["192.168.178.20"],
                pc_netze=[ipaddress.ip_network("192.168.178.0/24")], eingehend=0).als_dict()
    assert d["handy_netz"] == "192.168.178.x" and d["pc_netz"] == "192.168.178.x"
    assert "192.168.178.20" not in json.dumps(d)


# -- Firewall ------------------------------------------------------------------------------------------
SYSTEM = r"C:\Windows\System32"


def test_befehl_loescht_erst_und_legt_dann_eine_regel_an():
    pfad = r"C:\Users\Tom & Jerry\Nova\KI.exe"
    programm, parameter = firewall.befehl(SYSTEM, pfad)
    assert programm == r"C:\Windows\System32\cmd.exe"
    netsh = r'"C:\Windows\System32\netsh.exe"'
    loeschen = f'{netsh} advfirewall firewall delete rule name=all dir=in program="{pfad}"'
    anlegen = (f'{netsh} advfirewall firewall add rule name="Nova Handy-Kamera" dir=in '
               f'action=allow program="{pfad}" protocol=UDP profile=private,public remoteip=localsubnet enable=yes')
    assert parameter == f'/d /v:off /s /c "{loeschen} & {anlegen}"'
    # nur EIN Aufruf mit Adminrechten: Loeschen (auch Sperr-Regeln, Doppelte) und Anlegen zusammen
    assert parameter.count("delete rule") == 1 and parameter.count("add rule") == 1
    assert parameter.index("delete rule") < parameter.index("add rule")
    for boese in ('C:\\x" & calc & ".exe', "C:\\%TEMP%\\KI.exe", "C:\\a!b!\\KI.exe", "C:\\a\nb\\KI.exe"):
        with pytest.raises(ValueError):
            firewall.befehl(SYSTEM, boese)


def test_pfad_pruefung_nur_fertige_app(tmp_path):
    for name in ("KI.exe", "KI-App.exe", "ki-app.exe", "KI (1).exe"):
        (tmp_path / name).write_bytes(b"MZ")
        assert firewall.pfad_ok(str(tmp_path / name)), name
    for name in ("python.exe", "pythonw.exe", "anderes.exe", "KI.exe.txt"):
        (tmp_path / name).write_bytes(b"MZ")
        assert not firewall.pfad_ok(str(tmp_path / name)), name
    assert not firewall.pfad_ok(str(tmp_path / "fehlt" / "KI.exe"))
    assert not firewall.pfad_ok("KI.exe")                     # relativ
    assert not firewall.pfad_ok('C:\\a"b\\KI.exe') and not firewall.pfad_ok("")


def test_freigeben_nur_unter_windows(monkeypatch):
    aufrufe = []
    monkeypatch.setattr(firewall, "_runas", lambda *a: aufrufe.append(a) or 0)
    monkeypatch.setattr(firewall, "ist_windows", lambda: False)
    ok, text = firewall.freigeben()
    assert not ok and "Windows" in text and aufrufe == []
    assert firewall.moeglich() is False and firewall.anleitung() is None


@pytest.fixture
def windows(monkeypatch, tmp_path):
    exe = tmp_path / "KI.exe"
    exe.write_bytes(b"MZ")
    aufrufe = []
    ergebnis = {"code": 0, "regel": True}

    def runas(programm, parameter, hwnd=None):
        aufrufe.append((programm, parameter, hwnd))
        return ergebnis["code"]

    monkeypatch.setattr(firewall, "ist_windows", lambda: True)
    monkeypatch.setattr(firewall, "_prozess_pfad", lambda: str(exe))
    monkeypatch.setattr(firewall.sys, "frozen", True, raising=False)
    monkeypatch.setattr(firewall, "_system_ordner", lambda: SYSTEM)
    monkeypatch.setattr(firewall, "_fenster", lambda: 4711)
    monkeypatch.setattr(firewall, "_runas", runas)
    monkeypatch.setattr(firewall, "regel_vorhanden", lambda system=None: ergebnis["regel"])
    monkeypatch.setattr(firewall, "_FREIGEGEBEN", set())
    return types.SimpleNamespace(exe=exe, aufrufe=aufrufe, ergebnis=ergebnis)


def test_freigeben_eine_uac_abfrage_vor_dem_nova_fenster(windows):
    assert firewall.moeglich() and not firewall.freigegeben() and firewall.anleitung() is None
    ok, text = firewall.freigeben()
    assert ok and "Neu verbinden" in text
    assert windows.aufrufe == [(*firewall.befehl(SYSTEM, str(windows.exe)), 4711)]
    assert firewall.freigegeben()


@pytest.mark.parametrize("code, regel, wort", [(-1, True, "Abgebrochen"), (None, True, "Unklar"),
                                                (1, True, "abgelehnt"), (0, False, "Unklar")])
def test_freigeben_nur_bei_null_und_vorhandener_regel(windows, code, regel, wort):
    windows.ergebnis.update(code=code, regel=regel)
    ok, text = firewall.freigeben()
    assert not ok and wort in text and not firewall.freigegeben()


def test_regel_ungeprueft_aber_netsh_meldet_null_zaehlt(windows):
    windows.ergebnis.update(code=0, regel=None)  # Pruefung ging nicht - netsh meldete aber Erfolg
    assert firewall.freigeben()[0] is True


def test_mit_python_gestartet_kein_knopf_sondern_anleitung(windows, monkeypatch):
    monkeypatch.setattr(firewall.sys, "frozen", False, raising=False)
    assert not firewall.moeglich() and firewall.programm_pfad() is None
    assert "Windows-Sicherheit" in firewall.anleitung()
    ok, text = firewall.freigeben()
    assert not ok and windows.aufrufe == [] and "Windows-Sicherheit" in text


def test_regel_pruefen_ohne_adminrechte(monkeypatch):
    befehle = []

    def run(befehl, **kw):
        befehle.append(befehl)
        return types.SimpleNamespace(returncode=antwort["code"])

    antwort = {"code": 0}
    monkeypatch.setattr(firewall.subprocess, "run", run)
    assert firewall.regel_vorhanden(SYSTEM) is True
    antwort["code"] = 1
    assert firewall.regel_vorhanden(SYSTEM) is False
    assert befehle[0].endswith('netsh.exe" advfirewall firewall show rule name="Nova Handy-Kamera"')

    def kaputt(*a, **kw):
        raise OSError("weg")

    monkeypatch.setattr(firewall.subprocess, "run", kaputt)
    assert firewall.regel_vorhanden(SYSTEM) is None


def _dienst(tmp_path):
    from assistant.config import load_config
    from assistant.sehen.dienst import SehDienst

    return SehDienst(load_config(tmp_path), on_notiz=lambda t: None, wecken=lambda p: None, sieht_bilder=lambda: True,
                     bildschirm_moeglich=False, speichern=lambda k, v: None, mit_thread=False)


class _Handy:
    def __init__(self, st):
        self.st = st

    def status(self):
        return self.st


def test_dienst_bietet_firewall_nur_unter_windows_an(windows, tmp_path):
    d = _dienst(tmp_path)
    d._handy = _Handy({"zustand": "fehler", "fehler": "Vom Handy kam nichts an.", "grund": "keine-pakete",
                       "tipp": "Firewall freigeben", "verbindung_gescheitert": True})
    anzeige = d.status()["handy"]
    assert anzeige["gescheitert"] is True and anzeige["grund"] == "keine-pakete" and anzeige["tipp"]
    assert anzeige["firewall"] == {"moeglich": True, "frei": False, "anbieten": True, "hinweis": None}
    d._handy = _Handy({"zustand": "verbunden"})
    assert d.status()["handy"]["firewall"]["anbieten"] is False
    firewall._FREIGEGEBEN.add(str(windows.exe).lower())
    d._handy = _Handy({"zustand": "fehler", "verbindung_gescheitert": True})
    assert d.status()["handy"]["firewall"] == {"moeglich": True, "frei": True, "anbieten": False, "hinweis": None}


def test_dienst_mit_python_zeigt_anleitung(windows, monkeypatch, tmp_path):
    monkeypatch.setattr(firewall.sys, "frozen", False, raising=False)
    d = _dienst(tmp_path)
    d._handy = _Handy({"zustand": "fehler", "verbindung_gescheitert": True})
    fw = d.status()["handy"]["firewall"]
    assert fw["moeglich"] is False and fw["anbieten"] is False and "Windows-Sicherheit" in fw["hinweis"]


def test_app_route_firewall_mit_token_und_host(monkeypatch, tmp_path):
    from assistant.app.controller import AppController
    from assistant.app.server import AppServer
    from assistant.config import load_config

    aufrufe = []
    monkeypatch.setattr(firewall, "freigeben", lambda: aufrufe.append(1) or (True, "Firewall freigegeben."))
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    server = AppServer(lambda broadcast: AppController(cfg, broadcast))
    server.start()

    def post(token=True, host=None, body=b"{}"):
        kopf = {"Content-Type": "application/json"}
        if token:
            kopf["X-KI-Token"] = server.token
        if host:
            kopf["Host"] = host
        req = urllib.request.Request(f"http://127.0.0.1:{server.port}/api/kamera/firewall", data=body,
                                     headers=kopf, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, None

    try:
        assert post(token=False)[0] == 403 and aufrufe == []
        assert post(host="boese.example:80")[0] == 403 and aufrufe == []
        status, antwort = post(body=json.dumps({"programm": "C:\\boese.exe", "befehl": "x"}).encode())
        assert status == 200 and antwort["ok"] is True and "freigegeben" in antwort["message"]
        assert "sehen" in antwort and aufrufe == [1]   # aus der Anfrage wird nichts uebernommen
    finally:
        server.controller.shutdown()
        server.stop()


# -- Oberflaechen (statisch) ------------------------------------------------------------------------
def test_handy_seite_unterscheidet_die_gruende():
    from pathlib import Path

    seite = Path(__file__).resolve().parent.parent / "web" / "kamera" / "v1"
    js = (seite / "kamera.js").read_text(encoding="utf-8")
    # drei verschiedene Texte statt einem fuer alles
    assert "throw new NutzerFehler(mitTipps(TEXTE.keinLan))" in js
    assert "status(mitTipps(TEXTE.zeitAus), \"schlecht\")" in js
    assert "mitTipps(TEXTE.iceFehler)" in js
    assert "Firewall freigeben" in js and "WLAN-Ger\u00e4te d\u00fcrfen miteinander kommunizieren" in js
    # eingebaute Browser (Google-App/WebView) erkennen und auf Chrome/Safari verweisen
    assert "; wv\\)" in js and "GSA" in js and "In Chrome \u00f6ffnen" in js and "In Safari \u00f6ffnen" in js
    # Angebot erst, wenn die Kamera laeuft (sonst nur versteckte xxxx.local-Adressen)
    pos_kamera = js.index('kamera.readyState !== "live"')
    assert pos_kamera < js.index("pc.createOffer()")
    sw = (seite / "sw.js").read_text(encoding="utf-8")
    assert 'const SPEICHER = "nova-kamera-v1-2";' in sw


def test_app_dialog_zeigt_grund_und_firewall_knopf():
    from pathlib import Path

    static = Path(__file__).resolve().parent.parent / "assistant" / "app" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    js = (static / "sehen.js").read_text(encoding="utf-8")
    for element in ('id="hd-firewall"', 'id="hd-grund"', 'id="hd-tipp"', 'id="hd-firewall-ok"',
                    'id="hd-firewall-hinweis"'):
        assert element in html
    assert "Firewall freigeben" in html
    assert "post('/api/kamera/firewall', {})" in js  # nichts aus der Seite geht in den Befehl
    assert "fw.anbieten" in js and "h.tipp" in js and "fw.hinweis" in js
