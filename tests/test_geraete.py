"""Hardware-Geraete: Smart Home, Arduino/ESP32, Bluetooth, SSH - mit Attrappen statt echter Geraete."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from assistant import geraete as g
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry


def _ctx(tmp_path, confirm=lambda m, r: True, safe=False):
    pm = PermissionManager(PermissionSettings(safe_mode=safe, auto_confirm=False), tmp_path, confirm_fn=confirm)
    return ToolContext(permissions=pm, memory=None, extra={"app_root": tmp_path})


# ---------------------------------------------------------------- Netz-Pruefung
@pytest.mark.parametrize("url,ok", [
    ("http://192.168.1.50/led", True), ("http://10.0.0.7", True), ("http://172.20.1.1", True),
    ("http://esp32.local/x", True), ("http://169.254.1.2", True),
    ("http://8.8.8.8", False), ("https://example.com", False), ("http://127.0.0.1:8080", False),
    ("file:///etc/passwd", False), ("", False),
])
def test_nur_eigenes_netz(url, ok):
    assert g.lan_adresse(url) is ok


# ---------------------------------------------------------------- Home Assistant
class FakeHA:
    def __init__(self):
        self.aufrufe = []

    def __call__(self, method, url, headers, body, timeout):
        self.aufrufe.append((method, url, headers, json.loads(body) if body else None))
        if url.endswith("/api/states"):
            return 200, json.dumps([
                {"entity_id": "light.wohnzimmer", "state": "on", "attributes": {"friendly_name": "Wohnzimmer"}},
                {"entity_id": "sensor.temp", "state": "21.5", "attributes": {"friendly_name": "Temp",
                                                                            "unit_of_measurement": "°C"}},
                {"entity_id": "automation.x", "state": "on", "attributes": {}},
            ])
        return 200, "[]"


def test_home_assistant_liste_und_schalten():
    fake = FakeHA()
    ha = g.HomeAssistant("http://ha.local:8123/", "TOKEN", http=fake)
    liste = ha.geraete()
    assert "Wohnzimmer (light.wohnzimmer): on" in liste and "21.5 °C" in liste and "automation" not in liste
    assert fake.aufrufe[0][2]["Authorization"] == "Bearer TOKEN"
    ha.dienst("light.wohnzimmer", "turn_on", {"brightness_pct": 30})
    method, url, _, body = fake.aufrufe[-1]
    assert method == "POST" and url.endswith("/api/services/light/turn_on")
    assert body == {"entity_id": "light.wohnzimmer", "brightness_pct": 30}


def test_home_assistant_grenzen():
    ha = g.HomeAssistant("http://ha.local:8123", "T", http=FakeHA())
    with pytest.raises(g.GeraetFehler):
        ha.dienst("sensor.temp", "turn_on")                     # Sensoren schaltet man nicht
    with pytest.raises(g.GeraetFehler):
        ha.dienst("light.wohnzimmer", "reload_core_config")     # nur erlaubte Aktionen
    with pytest.raises(g.GeraetFehler):
        g.HomeAssistant("", "", http=FakeHA()).geraete()        # nicht eingerichtet
    with pytest.raises(g.GeraetFehler, match="Token"):
        g.HomeAssistant("http://h", "T", http=lambda *a: (401, "")).geraete()


def test_werkzeug_smarthome_fragt_vor_dem_schalten(tmp_path, monkeypatch):
    fake = FakeHA()
    monkeypatch.setattr(g, "home_assistant", lambda: g.HomeAssistant("http://ha.local", "T", http=fake))
    gefragt = []
    reg = build_registry()
    out, _ = reg.execute(_ctx(tmp_path, confirm=lambda m, r: gefragt.append(m) or False), "smarthome",
                         {"aktion": "schalten", "entity_id": "light.wohnzimmer", "dienst": "turn_off"})
    assert gefragt and not any(a[0] == "POST" for a in fake.aufrufe)   # abgelehnt -> nichts geschaltet
    out, _ = reg.execute(_ctx(tmp_path), "smarthome", {"aktion": "geraete"})
    assert "Wohnzimmer" in out


# ---------------------------------------------------------------- Arduino / ESP32
class FakeSeriell:
    def __init__(self):
        self.geschrieben = b""
        self.antworten = [b"OK LED an\n", b""]

    def write(self, b):
        self.geschrieben += b

    def flush(self):
        pass

    def read(self, n):
        return self.antworten.pop(0) if self.antworten else b""

    def close(self):
        pass


def test_seriell_senden_und_lesen():
    s = FakeSeriell()
    out = g.seriell_senden("COM3", "LED 1", warte_ms=50, oeffnen=lambda: s)
    assert s.geschrieben == b"LED 1\n" and "OK LED an" in out


def test_seriell_port_belegt():
    def kaputt():
        raise OSError("Zugriff verweigert")
    with pytest.raises(g.GeraetFehler, match="Serielle Monitor"):
        g.seriell_senden("COM3", "x", oeffnen=kaputt)


def test_http_nur_im_netz():
    with pytest.raises(g.GeraetFehler):
        g.http_geraet("https://example.com/api")
    out = g.http_geraet("http://192.168.1.50/led?an=1", http=lambda m, u, h, b, t: (200, "an"))
    assert "HTTP 200" in out and "an" in out


def test_eingetragener_name_fuer_http(tmp_path, monkeypatch):
    g.http_eintragen(tmp_path, "esp-licht", "http://192.168.1.50")
    gerufen = []
    monkeypatch.setattr(g, "_http", lambda m, u, h, b, t: gerufen.append(u) or (200, "ok"))
    monkeypatch.setattr(g.http_geraet, "__defaults__", ("GET", "", g._http))
    build_registry().execute(_ctx(tmp_path), "mikrocontroller", {"aktion": "http", "url": "esp-licht/led?an=1"})
    assert gerufen == ["http://192.168.1.50/led?an=1"]


# ---------------------------------------------------------------- SSH
def test_ssh_nur_eingetragene_und_ohne_passwort(tmp_path):
    with pytest.raises(g.GeraetFehler, match="eingetragen"):
        g.ssh_befehl(tmp_path, "pi", "uptime")
    with pytest.raises(g.GeraetFehler):
        g.ssh_eintragen(tmp_path, "pi; rm", "pi@192.168.1.20")
    g.ssh_eintragen(tmp_path, "pi", "pi@192.168.1.20")
    gesehen = {}

    def fake_run(cmd, **kw):
        gesehen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=b"up 3 days\n", stderr=b"")
    out = g.ssh_befehl(tmp_path, "pi", "uptime", ausfuehren=fake_run)
    assert "up 3 days" in out and "BatchMode=yes" in gesehen["cmd"] and gesehen["cmd"][-2:] == ["pi@192.168.1.20", "uptime"]
    kein_schluessel = lambda cmd, **kw: SimpleNamespace(returncode=255, stdout=b"",  # noqa: E731
                                                        stderr=b"Permission denied (publickey,password).")
    with pytest.raises(g.GeraetFehler, match="SSH-Schluessel"):
        g.ssh_befehl(tmp_path, "pi", "uptime", ausfuehren=kein_schluessel)


def test_werkzeug_ssh_im_sicheren_modus_gesperrt(tmp_path):
    g.ssh_eintragen(tmp_path, "pi", "pi@192.168.1.20")
    out, err = build_registry().execute(_ctx(tmp_path, safe=True), "ssh_geraet",
                                        {"aktion": "befehl", "name": "pi", "befehl": "reboot"})
    assert "Safe Mode" in out or "Safe Mode" in str(err)


# ---------------------------------------------------------------- Bluetooth
def test_bluetooth_ohne_bleak_sagt_was_fehlt(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "_bleak", lambda: (_ for _ in ()).throw(g.GeraetFehler("Fuer Bluetooth fehlt bleak")))
    out, _ = build_registry().execute(_ctx(tmp_path), "bluetooth", {"aktion": "suchen"})
    assert "bleak" in out


def test_alle_vier_werkzeuge_registriert():
    reg = build_registry()
    for name in ("smarthome", "mikrocontroller", "bluetooth", "ssh_geraet"):
        assert reg.get(name) is not None
