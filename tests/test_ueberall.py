"""0.42: Nova ueberall - Anrufe aus der Cloud, Telefon-Gespraech, Zeitplan, Handy-App-Steuerung, Wachwort.
Alles ohne echte Anrufe, ohne Handy, ohne Mikrofon und ohne Fenster."""
import base64
import http.client
import json
import subprocess
import sys
import threading
import time
from datetime import datetime

import pytest

from assistant import anruf_gespraech as G
from assistant import anruf_vonage as V
from assistant import handy_app as H
from assistant import wachwort as W
from assistant import zeitplan as Z
from assistant.app.server import AppServer
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry

TOKEN = "cloud-schluessel-abcdefghijklmnop+xyz"


def _ctx(tmp_path, gefragt=None, ja=True):
    def confirm(m, r):
        if gefragt is not None:
            gefragt.append(m)
        return ja
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=False), tmp_path, confirm_fn=confirm)
    return ToolContext(permissions=pm, memory=None, extra={"app_root": tmp_path, "ki_name": lambda: "Nova"})


# ---------------------------------------------------------------- Vonage in der Cloud
def test_vonage_schluessel_aus_der_umgebung(monkeypatch, tmp_path):
    pem = "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----"
    monkeypatch.setenv("VONAGE_APP_ID", "app-1")
    monkeypatch.setenv("VONAGE_PRIVATE_KEY", pem.replace("\n", "\\n"))      # so steht es oft beim Anbieter
    assert V.schluessel_text(None) == pem + "\n"
    assert V.eingerichtet(None)
    monkeypatch.setenv("VONAGE_PRIVATE_KEY", base64.b64encode(pem.encode()).decode())
    assert V.schluessel_text(tmp_path) == pem + "\n"
    monkeypatch.delenv("VONAGE_PRIVATE_KEY")
    assert not V.eingerichtet(tmp_path)


def test_rueckkanal_ueber_den_cloud_server():
    V.webhook_basis_setzen("https://nova-x.onrender.com/")
    try:
        kanal = V.rueckkanal_oeffnen("Kommst du heute?")
        assert kanal.url("antwort").startswith("https://nova-x.onrender.com/vonage/")
        nutzlast = {"speech": {"results": [{"text": "ja klar"}]}}
        antwort = json.loads(V.webhook_bearbeiten(kanal.pfad("antwort"), nutzlast))
        assert antwort[0]["action"] == "talk" and kanal.antworten == ["ja klar"]
        assert V.webhook_bearbeiten("/vonage/falsch/antwort", nutzlast) is None
        kanal.stoppen()
        assert V.webhook_bearbeiten(kanal.pfad("antwort"), nutzlast) is None   # nach dem Anruf: zu
    finally:
        V.webhook_basis_setzen("")


@pytest.fixture
def server():
    class Ctl:
        def state(self):
            return {"ok": True}

        def open_asks(self):
            return []

        def aufwachen_abholen(self):
            return None

    s = AppServer(lambda b: Ctl(), port=0, token=TOKEN, hosts="*")
    s.start()
    yield s
    s.stop()


def _anfrage(server, methode, pfad, body=None, kopf=None, timeout=5):
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=timeout)
    daten = json.dumps(body).encode() if body is not None else None
    k = {"Host": "nova-ab12.onrender.com", **(kopf or {})}
    if daten is not None:
        k["Content-Type"] = "application/json"
    c.request(methode, pfad, body=daten, headers=k)
    r = c.getresponse()
    return r.status, r.read()


def test_vonage_webhook_am_server_ohne_schluessel_aber_nur_mit_geheimnis(server):
    V.webhook_basis_setzen("https://nova-ab12.onrender.com")
    try:
        kanal = V.rueckkanal_oeffnen("Frage")
        st, body = _anfrage(server, "POST", kanal.pfad("antwort"), {"speech": {"results": [{"text": "passt"}]}})
        assert st == 200 and json.loads(body)[0]["action"] == "talk"
        assert _anfrage(server, "POST", "/vonage/geraten/antwort", {})[0] == 404
        kanal.stoppen()
    finally:
        V.webhook_basis_setzen("")


# ---------------------------------------------------------------- Telefon-Gespraech
class FakeVonage:
    def __init__(self):
        self.uebergaben, self.aufgelegt = [], False

    def anrufen(self, nummer, ncco, minuten, event_url):
        self.erster = ncco
        return "call-1"

    def uebergeben(self, call_id, ncco):
        self.uebergaben.append((call_id, ncco))

    def auflegen(self, call_id):
        self.aufgelegt = True


def test_gespraech_hin_und_her():
    V.webhook_basis_setzen("https://nova-ab12.onrender.com")
    gehoert = []
    try:
        v = FakeVonage()

        def bei_text(g, text):
            gehoert.append(text)
            g.sagen("**Erledigt**: Spotify laeuft. https://x.de")
        g = G.starten(v, "+491701234567", "Ich bin da.", "Nova", 10, bei_text)
        assert v.erster[-1]["action"] == "input"
        antwort = g.antwort_ncco({"uuid": "call-1", "speech": {"results": [{"text": "Mach Spotify an"}]}})
        assert "Moment" in antwort[0]["text"] and antwort[1]["loop"] == 0       # warten statt auflegen
        for _ in range(50):
            if v.uebergaben:
                break
            time.sleep(0.02)
        call_id, ncco = v.uebergaben[0]
        assert call_id == "call-1" and gehoert == ["Mach Spotify an"]
        assert ncco[0]["text"] == "Erledigt : Spotify laeuft. (Link in der App)" and ncco[1]["action"] == "input"
        assert G.TSCHUESS.search("okay tschuess") and g.antwort_ncco(
            {"speech": {"results": [{"text": "Danke, tschuess"}]}})[0]["text"].startswith("Alles klar")
        g.stoppen()
    finally:
        V.webhook_basis_setzen("")


def test_gespraech_rueckfrage_ja_nein():
    g = G.Gespraech("x", oeffentlich="https://a.b", vonage=FakeVonage(), call_id="c")
    ergebnis = {}
    t = threading.Thread(target=lambda: ergebnis.setdefault("ok", g.darf_ich("Datei loeschen")))
    t.start()
    for _ in range(50):
        if g._frage is not None:
            break
        time.sleep(0.02)
    g.antwort_ncco({"speech": {"results": [{"text": "Ja, mach das"}]}})
    t.join(2)
    assert ergebnis["ok"] is True
    g2 = G.Gespraech("x", oeffentlich="https://a.b", vonage=FakeVonage(), call_id="c")
    g2.beendet.set()
    assert g2.darf_ich("x") is False                    # Anruf vorbei: nie "ja" annehmen


def test_anruf_werkzeug_startet_gespraech(tmp_path, monkeypatch):
    monkeypatch.setenv("VONAGE_APP_ID", "app")
    monkeypatch.setenv("VONAGE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\\nA\\n-----END PRIVATE KEY-----")
    monkeypatch.setenv("ANRUF_NUMMER", "+491701234567")
    monkeypatch.delenv("BLAND_API_KEY", raising=False)
    ctx = _ctx(tmp_path)
    ctx.extra["anruf_gespraech"] = lambda anliegen: f"GESTARTET {anliegen}"
    out, _ = build_registry().execute(ctx, "anrufen", {"anliegen": "Lass uns reden", "gespraech": True})
    assert out == "GESTARTET Lass uns reden"


# ---------------------------------------------------------------- Zeitplan
BASIS = datetime(2026, 11, 26, 22, 0)   # Donnerstag


@pytest.mark.parametrize("wann,erwartet", [
    ("08:00", "2026-11-27 08:00"), ("morgen 7:30", "2026-11-27 07:30"), ("freitag 18 uhr", "2026-11-27 18:00"),
    ("27.11. 9:00", "2026-11-27 09:00"), ("in 20 minuten", "2026-11-26 22:20"), ("2026-12-01 10:15", "2026-12-01 10:15"),
    ("donnerstag 21:00", "2026-12-03 21:00"),
])
def test_zeit_verstehen(wann, erwartet):
    assert Z.zeit_verstehen(wann, BASIS).strftime("%Y-%m-%d %H:%M") == erwartet


def test_zeit_vorbei_oder_unsinn():
    for falsch in ("", "irgendwann", "25:00", "01.01.2020 10:00"):
        with pytest.raises(Z.ZeitplanFehler):
            Z.zeit_verstehen(falsch, BASIS)


def test_berliner_zeit_ohne_zeitzonen_daten():
    from datetime import timezone
    assert Z._berlin(datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)).hour == 12     # Sommerzeit
    assert Z._berlin(datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)).hour == 11    # Winterzeit


def test_planen_faellig_wiederholen(tmp_path):
    e1 = Z.planen(tmp_path, "in 5 minuten", "Ruf mich an", basis=BASIS)
    e2 = Z.planen(tmp_path, "08:00", "Wetter aufs Handy", "werktags", basis=BASIS)
    assert len(Z.laden(tmp_path)) == 2
    assert Z.faellige_nehmen(tmp_path, BASIS) == []
    f = Z.faellige_nehmen(tmp_path, datetime(2026, 11, 26, 22, 6))
    assert [x["id"] for x in f] == [e1["id"]] and not f[0]["verpasst"]
    f = Z.faellige_nehmen(tmp_path, datetime(2026, 11, 27, 8, 1))         # Freitag
    assert [x["id"] for x in f] == [e2["id"]] and not f[0]["verpasst"]
    e3 = Z.planen(tmp_path, "in 1 minuten", "Alt", basis=BASIS)
    assert [x["verpasst"] for x in Z.faellige_nehmen(tmp_path, datetime(2026, 11, 27, 8, 2))] == [True]
    assert e3["id"] not in {r["id"] for r in Z.laden(tmp_path)}
    rest = Z.laden(tmp_path)
    assert [r["wann"] for r in rest] == ["2026-11-30 08:00"]              # werktags: Montag, nicht Samstag
    assert Z.loeschen(tmp_path, e2["id"]) and Z.laden(tmp_path) == []
    assert "Geplante Aufgabe" in Z.modell_auftrag(f[0])


def test_zeitplan_werkzeug_fragt(tmp_path):
    gefragt = []
    out, _ = build_registry().execute(_ctx(tmp_path, gefragt), "zeitplan",
                                      {"aktion": "planen", "wann": "in 30 minuten", "auftrag": "Ruf mich an"})
    assert out.startswith("Geplant") and gefragt and "Ruf mich an" in gefragt[0]
    out, _ = build_registry().execute(_ctx(tmp_path, ja=False), "zeitplan",
                                      {"aktion": "planen", "wann": "in 30 minuten", "auftrag": "Heimlich"})
    assert len(Z.laden(tmp_path)) == 1


def test_zeitplan_datei_ist_fuer_werkzeuge_gesperrt(tmp_path):
    pm = PermissionManager(PermissionSettings(), tmp_path / "ws", app_root=tmp_path)
    assert pm.ist_gesperrt((tmp_path / "data" / "zeitplan.json").resolve())
    assert pm.ist_gesperrt((tmp_path / "data" / "nova_wachwort.ps1").resolve())


# ---------------------------------------------------------------- Handy-App
def test_kanal_auftrag_und_ergebnis():
    k = H.GeraeteKanal()
    assert not k.verbunden()
    with pytest.raises(H.GeraetFehler):
        k.ausfuehren("bildschirm")
    assert k.abholen({"modell": "Pixel 8", "android": "15", "geheim": "x"}, warte=0) is None
    assert k.verbunden() and "geheim" not in k.info

    def handy():
        a = k.abholen(warte=2)
        assert k.ergebnis("fremd", {"ok": True}) is False                  # unbekannte ID: nichts annehmen
        k.ergebnis(a["id"], {"ok": True, "text": f"{a['aktion']} {a['element']}"})
    t = threading.Thread(target=handy)
    t.start()
    assert k.ausfuehren("tippen", {"element": "Senden", "leer": ""}, timeout=3) == "tippen Senden"
    t.join(2)
    assert "Pixel 8" in k.status_text()


def test_kanal_zeitueberschreitung_nimmt_auftrag_zurueck():
    k = H.GeraeteKanal()
    k.abholen(warte=0)
    with pytest.raises(H.GeraetFehler):
        k.ausfuehren("bildschirm", timeout=0.2)
    assert k.abholen(warte=0) is None                                      # nicht spaeter noch ausfuehren


def test_kanal_fehler_vom_handy():
    k = H.GeraeteKanal()
    k.abholen(warte=0)
    threading.Thread(target=lambda: k.ergebnis(k.abholen(warte=2)["id"], {"ok": False, "fehler": "Passwortfeld"})).start()
    with pytest.raises(H.GeraetFehler, match="Passwortfeld"):
        k.ausfuehren("text", {"text": "x"}, timeout=3)


def test_handy_werkzeug(tmp_path, monkeypatch):
    k = H.GeraeteKanal()
    monkeypatch.setattr(H, "KANAL", k)
    out, _ = build_registry().execute(_ctx(tmp_path), "handy_bedienen", {"aktion": "bildschirm"})
    assert "nicht verbunden" in out
    k.abholen(warte=0)
    gefragt = []
    monkeypatch.setattr(k, "ausfuehren", lambda aktion, p, timeout=45: "Getippt. Token sk-ant-api03-abcdefghijklmnopqrstu")
    out, _ = build_registry().execute(_ctx(tmp_path, gefragt), "handy_bedienen", {"aktion": "tippen", "element": "OK"})
    assert gefragt == ["Aufs Handy tippen: OK"] and "abcdefghijklmnop" not in out
    out, _ = build_registry().execute(_ctx(tmp_path), "handy_bedienen", {"aktion": "link_oeffnen", "url": "javascript:x"})
    assert "Nur Internet" in out


def test_handy_routen_nur_mit_schluessel(server, monkeypatch):
    k = H.GeraeteKanal()
    monkeypatch.setattr(H, "KANAL", k)
    monkeypatch.setattr(H, "WARTEN_ABHOLEN", 0.1)
    assert _anfrage(server, "GET", "/api/geraet/auftrag")[0] == 403
    threading.Thread(target=lambda: k.ausfuehren("akku", timeout=5) if (time.sleep(0.3) or True) else None,
                     daemon=True).start()
    k.abholen(warte=0)
    st, body = _anfrage(server, "GET", "/api/geraet/auftrag?modell=Pixel", kopf={"X-KI-Token": TOKEN})
    auftrag = json.loads(body)["auftrag"]
    assert st == 200 and auftrag["aktion"] == "akku"
    st, body = _anfrage(server, "POST", "/api/geraet/ergebnis", {"id": auftrag["id"], "ok": True, "text": "80 %"},
                        kopf={"X-KI-Token": TOKEN})
    assert json.loads(body)["ok"] is True
    assert _anfrage(server, "POST", "/api/geraet/ergebnis", {"id": "x"})[0] == 403


# ---------------------------------------------------------------- Wachwort
def test_wachwort_pruefen():
    assert W.wort_pruefen("  Hey,  Nova! ") == "Hey Nova"
    for falsch in ("", "Nova", "a b c d e f", "Hey 123"):
        with pytest.raises(W.WachwortFehler):
            W.wort_pruefen(falsch)


def test_bildschirm_ohne_spiel():
    m = [{"rechteck": (0, 0, 3440, 1440), "arbeit": (0, 0, 3440, 1392), "primaer": True},
         {"rechteck": (-1920, 352, 0, 1432), "arbeit": (-1920, 352, 0, 1384), "primaer": False}]
    spiel = [(0, 0, 3440, 1440)]
    assert W.waehle_bildschirm(m, spiel, (100, 100)) == 1                 # Spiel vorne: anderer Bildschirm
    assert W.waehle_bildschirm(m, [], (-500, 600)) == 1                   # sonst da, wo die Maus ist
    assert W.waehle_bildschirm(m, [], None) == 0
    assert W.waehle_bildschirm(m, spiel + [(-1920, 352, 0, 1432)], (100, 100)) == 0   # alles voll: Maus
    assert W.waehle_bildschirm(m, [(10, 10, 800, 600)], (100, 100)) == 0  # kleines Fenster ist kein Vollbild
    x, y, b, h = W.fenster_position(m[1])
    assert -1920 <= x and x + b <= 0 and 352 <= y and y + h <= 1384


def test_wachwort_einstellungen(tmp_path):
    assert W.laden(tmp_path)["sprechen"] is True and W.laden(tmp_path)["an"] is False   # Standard
    W.speichern(tmp_path, sprechen=False, empfindlich=5)
    e = W.laden(tmp_path)
    assert e["sprechen"] is False and e["empfindlich"] == 0.95
    out, _ = build_registry().execute(_ctx(tmp_path), "wachwort", {"aktion": "sprechen_an"})
    assert W.laden(tmp_path)["sprechen"] is True and "Spracheingabe beim Aufwachen: an" in out


def test_wachwort_an_fragt_immer(tmp_path, monkeypatch):
    gefragt = []
    monkeypatch.setattr(W, "einschalten", lambda root: (_ for _ in ()).throw(AssertionError("nicht ohne Ja")))
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=True), tmp_path,
                           confirm_fn=lambda m, r: gefragt.append(m) or False)
    ctx = ToolContext(permissions=pm, memory=None, extra={"app_root": tmp_path})
    out, _ = build_registry().execute(ctx, "wachwort", {"aktion": "an"})
    assert gefragt and "abgelehnt" in out.lower()


def test_gestartet_vom_lauscher(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "wachwort_status.json").write_text('{"pid": 4242, "status": "gehoert"}', encoding="utf-8-sig")
    assert W.gestartet_vom_lauscher(tmp_path, {1, 4242}) and not W.gestartet_vom_lauscher(tmp_path, {1})


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell")
def test_lauscher_skript_ohne_syntaxfehler(tmp_path):
    """Nur pruefen (Parser) - es wird nichts gestartet und nichts aufgenommen."""
    pfad = W.skript_schreiben(tmp_path)
    text = pfad.read_text(encoding="utf-8-sig")
    assert "__ROOT__" not in text and "__EXE__" not in text and "--aufwachen" in text
    pruefung = ("$f=$null; [void][System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$null,[ref]$f);"
                " $f | ForEach-Object { $_.Message + ' @' + $_.Extent.StartLineNumber }")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", pruefung, str(pfad)],
                       capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "", r.stdout
