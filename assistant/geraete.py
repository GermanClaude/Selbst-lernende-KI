"""Hardware-Geraete: Smart Home (Home Assistant), Arduino/ESP32 (USB-Seriell / WLAN), Bluetooth (BLE)
und andere Rechner (SSH).

Sicherheit:
- Home-Assistant-Token und -Adresse stehen nur in der .env (HA_URL, HA_TOKEN) - nie an die KI.
- SSH nur zu Geraeten, die du selbst mit Namen eingetragen hast (config/geraete.json), und nur mit
  SSH-Schluessel (BatchMode - Nova tippt nie ein Passwort ein).
- HTTP zu Mikrocontrollern nur ins eigene Netz (192.168.x.x, 10.x.x.x, 172.16-31.x.x, *.local).
- Bibliotheken (pyserial, bleak) sind optional: fehlen sie, sagt das Werkzeug, was zu tun ist.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

MAX_ANTWORT = 6000


class GeraetFehler(RuntimeError):
    pass


# -- eingetragene Geraete (config/geraete.json) ---------------------------------------------------
def _pfad(root) -> Path:
    return Path(root) / "config" / "geraete.json"


def laden(root) -> dict:
    try:
        d = json.loads(_pfad(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    d.setdefault("ssh", {})
    d.setdefault("http", {})
    return d


def speichern(root, daten: dict) -> None:
    p = _pfad(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")


_NAME = re.compile(r"^[A-Za-z0-9_.\-]{1,40}$")
_SSH_ZIEL = re.compile(r"^[A-Za-z0-9_.\-]{1,64}@[A-Za-z0-9_.\-:\[\]]{1,253}$")


def ssh_eintragen(root, name: str, ziel: str, port: int = 22) -> str:
    if not _NAME.match(name or ""):
        raise GeraetFehler("Name bitte nur aus Buchstaben, Ziffern, - _ . (z.B. 'pi' oder 'server').")
    if not _SSH_ZIEL.match(ziel or ""):
        raise GeraetFehler("Ziel bitte als benutzer@adresse, z.B. pi@192.168.1.20")
    d = laden(root)
    d["ssh"][name] = {"ziel": ziel, "port": int(port)}
    speichern(root, d)
    return name


def http_eintragen(root, name: str, url: str) -> str:
    if not _NAME.match(name or ""):
        raise GeraetFehler("Name bitte nur aus Buchstaben, Ziffern, - _ . (z.B. 'esp-licht').")
    if not lan_adresse(url):
        raise GeraetFehler("Nur Adressen im eigenen Netz, z.B. http://192.168.1.50 oder http://esp32.local")
    d = laden(root)
    d["http"][name] = {"url": url.rstrip("/")}
    speichern(root, d)
    return name


def entfernen(root, art: str, name: str) -> bool:
    d = laden(root)
    if name in d.get(art, {}):
        del d[art][name]
        speichern(root, d)
        return True
    return False


# -- Hilfen --------------------------------------------------------------------------------------
def lan_adresse(url: str) -> bool:
    """Liegt die Adresse im eigenen Netz (privat, link-lokal, *.local)? Nur http/https."""
    try:
        teile = urllib.parse.urlsplit(str(url or ""))
    except ValueError:
        return False
    if teile.scheme not in ("http", "https") or not teile.hostname:
        return False
    host = teile.hostname.lower()
    if host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (ip.is_private or ip.is_link_local) and not ip.is_loopback and not ip.is_multicast


def _kuerzen(text: str) -> str:
    text = str(text or "")
    return text if len(text) <= MAX_ANTWORT else text[:MAX_ANTWORT] + "\n... (gekuerzt)"


def _http(method: str, url: str, headers: dict | None = None, body: bytes | None = None,
          timeout: float = 10.0) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(200_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(20_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        raise GeraetFehler(f"Geraet nicht erreichbar ({exc}).") from exc


# -- Smart Home: Home Assistant --------------------------------------------------------------------
HA_BEREICHE = ("light", "switch", "fan", "cover", "climate", "media_player", "scene", "script", "lock",
               "vacuum", "input_boolean", "sensor", "binary_sensor")
HA_DIENSTE_ERLAUBT = {"turn_on", "turn_off", "toggle", "open_cover", "close_cover", "stop_cover",
                      "set_temperature", "set_hvac_mode", "media_play", "media_pause", "media_stop",
                      "volume_set", "volume_mute", "start", "stop", "return_to_base", "lock", "unlock"}


class HomeAssistant:
    def __init__(self, url: str, token: str, http: Callable[..., tuple[int, str]] = _http):
        self.url = (url or "").rstrip("/")
        self.token = token or ""
        self.http = http

    def _rufen(self, method: str, pfad: str, daten: dict | None = None):
        if not self.url or not self.token:
            raise GeraetFehler("Home Assistant ist nicht eingerichtet: /geraete smarthome <Adresse> <Token>")
        body = json.dumps(daten).encode() if daten is not None else None
        status, text = self.http(method, self.url + pfad, {"Authorization": f"Bearer {self.token}",
                                                            "Content-Type": "application/json"}, body, 15.0)
        if status in (401, 403):
            raise GeraetFehler("Home Assistant lehnt den Token ab (Profil > Langlebige Zugangs-Token neu erstellen).")
        if status >= 400:
            raise GeraetFehler(f"Home Assistant meldet Fehler {status}: {text[:300]}")
        try:
            return json.loads(text) if text.strip() else None
        except ValueError:
            return text

    def geraete(self, bereich: str = "") -> str:
        alle = self._rufen("GET", "/api/states") or []
        zeilen = []
        for e in alle if isinstance(alle, list) else []:
            eid = str(e.get("entity_id", ""))
            dom = eid.split(".", 1)[0]
            if dom not in HA_BEREICHE or (bereich and dom != bereich):
                continue
            name = (e.get("attributes") or {}).get("friendly_name") or eid
            einheit = (e.get("attributes") or {}).get("unit_of_measurement") or ""
            zeilen.append(f"- {name} ({eid}): {e.get('state')}{(' ' + einheit) if einheit else ''}")
        return _kuerzen("\n".join(zeilen[:300]) or "Keine passenden Geraete gefunden.")

    def status(self, entity_id: str) -> str:
        e = self._rufen("GET", f"/api/states/{urllib.parse.quote(entity_id)}") or {}
        attr = {k: v for k, v in (e.get("attributes") or {}).items() if k in (
            "friendly_name", "brightness", "temperature", "current_temperature", "unit_of_measurement",
            "hvac_mode", "volume_level", "media_title", "battery_level", "current_position")}
        return f"{entity_id}: {e.get('state')} {json.dumps(attr, ensure_ascii=False) if attr else ''}".strip()

    def dienst(self, entity_id: str, dienst: str, daten: dict | None = None) -> str:
        dom = entity_id.split(".", 1)[0]
        if dom not in HA_BEREICHE or dom in ("sensor", "binary_sensor"):
            raise GeraetFehler(f"'{entity_id}' laesst sich nicht schalten.")
        if dienst not in HA_DIENSTE_ERLAUBT:
            raise GeraetFehler(f"Aktion '{dienst}' ist nicht erlaubt. Erlaubt: {', '.join(sorted(HA_DIENSTE_ERLAUBT))}")
        nutzlast = {"entity_id": entity_id, **{k: v for k, v in (daten or {}).items() if k != "entity_id"}}
        self._rufen("POST", f"/api/services/{dom}/{dienst}", nutzlast)
        return f"Erledigt: {dienst} fuer {entity_id}."


def home_assistant() -> HomeAssistant:
    return HomeAssistant(os.environ.get("HA_URL", "").strip(), os.environ.get("HA_TOKEN", "").strip())


# -- Arduino / ESP32: USB-Seriell ------------------------------------------------------------------
def serielle_ports() -> list[dict]:
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError as exc:
        raise GeraetFehler("Fuer USB-Geraete fehlt pyserial (pip install pyserial).") from exc
    return [{"port": p.device, "beschreibung": p.description or "", "hwid": p.hwid or ""}
            for p in list_ports.comports()]


def seriell_senden(port: str, text: str, baud: int = 115200, warte_ms: int = 1500, oeffnen=None) -> str:
    """Schickt eine Zeile an das Geraet und liest, was es innerhalb von warte_ms antwortet."""
    if oeffnen is None:
        try:
            import serial  # type: ignore
        except ImportError as exc:
            raise GeraetFehler("Fuer USB-Geraete fehlt pyserial (pip install pyserial).") from exc
        oeffnen = lambda: serial.Serial(port, int(baud), timeout=0.2)  # noqa: E731
    try:
        verbindung = oeffnen()
    except Exception as exc:  # noqa: BLE001 - belegter Port, falscher Name ...
        raise GeraetFehler(f"Port {port} laesst sich nicht oeffnen ({exc}). Ist der Serielle Monitor noch offen?") from exc
    try:
        time.sleep(0.1)
        if text:
            verbindung.write((text.rstrip("\r\n") + "\n").encode("utf-8"))
            verbindung.flush()
        ende = time.monotonic() + max(0, min(int(warte_ms), 15000)) / 1000.0
        daten = b""
        while time.monotonic() < ende and len(daten) < 50_000:
            stueck = verbindung.read(4096)
            if stueck:
                daten += stueck
        return _kuerzen(daten.decode("utf-8", errors="replace").strip()) or "(keine Antwort)"
    finally:
        try:
            verbindung.close()
        except Exception:  # noqa: BLE001
            pass


# -- ESP32 & Co. per HTTP im eigenen Netz ----------------------------------------------------------
def http_geraet(url: str, methode: str = "GET", text: str = "", http=_http) -> str:
    if not lan_adresse(url):
        raise GeraetFehler("Nur Adressen im eigenen Netz (z.B. http://192.168.1.50/led?an=1).")
    methode = "POST" if str(methode).upper() == "POST" else "GET"
    body = text.encode("utf-8") if methode == "POST" and text else None
    status, antwort = http(methode, url, {"Content-Type": "text/plain; charset=utf-8"} if body else {}, body, 10.0)
    return _kuerzen(f"HTTP {status}\n{antwort}")


# -- Bluetooth (BLE) -------------------------------------------------------------------------------
def _bleak():
    try:
        import bleak  # type: ignore
    except ImportError as exc:
        raise GeraetFehler("Fuer Bluetooth fehlt bleak (pip install bleak).") from exc
    return bleak


def ble_suchen(sekunden: float = 6.0) -> str:
    bleak = _bleak()

    async def los():
        return await bleak.BleakScanner.discover(timeout=max(2.0, min(float(sekunden), 20.0)), return_adv=True)

    gefunden = asyncio.run(los())
    zeilen = []
    for adresse, (geraet, adv) in sorted(gefunden.items(), key=lambda kv: -(kv[1][1].rssi or -999)):
        zeilen.append(f"- {geraet.name or adv.local_name or '(ohne Namen)'}  [{adresse}]  Signal {adv.rssi} dBm")
    return "\n".join(zeilen[:60]) or "Keine Bluetooth-Geraete in der Naehe gefunden (Bluetooth an?)."


def ble_dienste(adresse: str) -> str:
    bleak = _bleak()

    async def los():
        async with bleak.BleakClient(adresse, timeout=15.0) as c:
            zeilen = []
            for s in c.services:
                zeilen.append(f"Dienst {s.uuid} {s.description or ''}".rstrip())
                for ch in s.characteristics:
                    zeilen.append(f"  - {ch.uuid} ({', '.join(ch.properties)}) {ch.description or ''}".rstrip())
            return "\n".join(zeilen)

    return _kuerzen(asyncio.run(los()) or "(keine Dienste)")


def ble_lesen(adresse: str, uuid: str) -> str:
    bleak = _bleak()

    async def los():
        async with bleak.BleakClient(adresse, timeout=15.0) as c:
            return await c.read_gatt_char(uuid)

    daten = bytes(asyncio.run(los()))
    text = daten.decode("utf-8", errors="replace")
    lesbar = all(ch.isprintable() or ch.isspace() for ch in text)
    return f"{len(daten)} Bytes: hex {daten.hex()}" + (f" | Text: {text}" if lesbar and text.strip() else "")


def ble_schreiben(adresse: str, uuid: str, wert: str) -> str:
    bleak = _bleak()
    roh = wert.strip()
    if roh.lower().startswith("hex:"):
        daten = bytes.fromhex(roh[4:].replace(" ", ""))
    else:
        daten = wert.encode("utf-8")

    async def los():
        async with bleak.BleakClient(adresse, timeout=15.0) as c:
            await c.write_gatt_char(uuid, daten, response=True)

    asyncio.run(los())
    return f"{len(daten)} Bytes an {uuid} geschrieben."


# -- Andere Rechner per SSH ------------------------------------------------------------------------
def ssh_befehl(root, name: str, befehl: str, timeout: float = 60.0, ausfuehren=subprocess.run) -> str:
    geraet = laden(root)["ssh"].get(name)
    if not geraet:
        namen = ", ".join(laden(root)["ssh"]) or "noch keine"
        raise GeraetFehler(f"Kein SSH-Geraet '{name}' eingetragen (eingetragen: {namen}). "
                           "Eintragen: /geraete ssh <name> <benutzer@adresse>")
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new",
           "-p", str(int(geraet.get("port", 22))), geraet["ziel"], befehl]
    try:
        r = ausfuehren(cmd, capture_output=True, timeout=max(5.0, min(float(timeout), 600.0)),
                       stdin=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        raise GeraetFehler("Das Programm 'ssh' fehlt (Windows: Einstellungen > Optionale Features > OpenSSH-Client).") from exc
    except subprocess.TimeoutExpired as exc:
        raise GeraetFehler(f"Der Befehl auf '{name}' hat zu lange gedauert (Abbruch).") from exc
    aus = (r.stdout or b"").decode("utf-8", errors="replace")
    fehler = (r.stderr or b"").decode("utf-8", errors="replace")
    if r.returncode == 255 and ("Permission denied" in fehler or "publickey" in fehler):
        raise GeraetFehler(f"'{name}' laesst mich nicht rein: Es braucht einen SSH-Schluessel (kein Passwort). "
                           "Einmalig einrichten: ssh-keygen und den oeffentlichen Schluessel auf dem Geraet in "
                           "~/.ssh/authorized_keys eintragen.")
    if r.returncode == 255:
        raise GeraetFehler(f"Verbindung zu '{name}' ging nicht: {fehler.strip()[:300]}")
    teile = [f"Rueckgabewert {r.returncode}"]
    if aus.strip():
        teile.append(aus.rstrip())
    if fehler.strip():
        teile.append("Fehlerausgabe:\n" + fehler.rstrip())
    return _kuerzen("\n".join(teile))
