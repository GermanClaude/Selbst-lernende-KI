"""Das Handy steuern - fuer Nova in Termux auf Android (oder vom PC aus ein per ADB verbundenes Handy).

Zwei Wege:
1. Termux:API (App "Termux:API" + `pkg install termux-api`): Akku, Benachrichtigung, Taschenlampe,
   Zwischenablage, Standort, SMS, Kontakte, Anrufliste, Kamera, Vorlesen, Links oeffnen.
2. ADB ueber "Kabelloses Debugging" (Android 11+, kein Root): tippen, wischen, Text eingeben, Tasten,
   Bildschirm als Liste der Elemente lesen, Apps starten, Apps installieren - also das ganze Handy.
   Einmalig koppeln: Entwickleroptionen > Kabelloses Debugging > "Mit Kopplungscode koppeln", dann
   /handysteuerung koppeln <Kopplungsport> <Code> und /handysteuerung verbinden <Port>.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


class HandyFehler(RuntimeError):
    pass


def ist_termux() -> bool:
    return "com.termux" in os.environ.get("PREFIX", "") or bool(os.environ.get("TERMUX_VERSION"))


def verfuegbar() -> bool:
    """Gibt es hier ueberhaupt ein Handy zum Steuern (Termux oder ein ADB-Programm)?"""
    return ist_termux() or bool(shutil.which("adb"))


def _lauf(cmd: list[str], timeout: float = 30.0, eingabe: str | None = None, ausfuehren=subprocess.run) -> str:
    if not shutil.which(cmd[0]):
        if cmd[0].startswith("termux-"):
            raise HandyFehler("Termux:API fehlt: die App 'Termux:API' (F-Droid) installieren und in Termux "
                              "'pkg install termux-api' ausfuehren.")
        if cmd[0] == "adb":
            raise HandyFehler("ADB fehlt: in Termux 'pkg install android-tools' ausfuehren.")
        raise HandyFehler(f"Programm '{cmd[0]}' fehlt.")
    try:
        r = ausfuehren(cmd, capture_output=True, text=True, timeout=timeout, input=eingabe)
    except subprocess.TimeoutExpired as exc:
        raise HandyFehler(f"'{cmd[0]}' hat zu lange gebraucht.") from exc
    aus = (r.stdout or "").strip()
    if r.returncode != 0:
        raise HandyFehler(((r.stderr or "").strip() or aus or f"Fehler {r.returncode}")[:500])
    return aus


# -- Termux:API ----------------------------------------------------------------------------------
def termux(aktion: str, **p) -> str:
    """Ein Termux:API-Befehl. Gibt die Ausgabe (oft JSON) zurueck."""
    n = lambda k, d=10: str(max(1, min(int(p.get(k) or d), 200)))  # noqa: E731
    befehle = {
        "akku": ["termux-battery-status"],
        "wlan": ["termux-wifi-connectioninfo"],
        "standort": ["termux-location", "-p", "network", "-r", "once"],
        "zwischenablage_lesen": ["termux-clipboard-get"],
        "sms_lesen": ["termux-sms-list", "-l", n("anzahl"), "-t", "inbox"],
        "kontakte": ["termux-contact-list"],
        "anrufliste": ["termux-call-log", "-l", n("anzahl")],
        "vibrieren": ["termux-vibrate", "-d", "400"],
        "taschenlampe": ["termux-torch", "on" if p.get("an", True) else "off"],
    }
    if aktion in befehle:
        return _lauf(befehle[aktion], timeout=40.0) or "OK"
    if aktion == "zwischenablage_schreiben":
        _lauf(["termux-clipboard-set"], eingabe=str(p.get("text", "")))
        return "In die Zwischenablage kopiert."
    if aktion == "benachrichtigung":
        _lauf(["termux-notification", "--title", str(p.get("titel") or "Nova"), "--content", str(p.get("text", ""))])
        return "Benachrichtigung gezeigt."
    if aktion == "vorlesen":
        _lauf(["termux-tts-speak", "-l", "de", str(p.get("text", ""))], timeout=120.0)
        return "Vorgelesen."
    if aktion == "sms_senden":
        nummer, text = str(p.get("nummer", "")).strip(), str(p.get("text", ""))
        if not re.fullmatch(r"\+?[0-9 ]{3,20}", nummer) or not text:
            raise HandyFehler("Fuer eine SMS brauche ich nummer und text.")
        _lauf(["termux-sms-send", "-n", nummer.replace(" ", ""), text])
        return f"SMS an {nummer} gesendet."
    if aktion == "foto":
        ziel = Path(str(p.get("datei") or "foto.jpg"))
        _lauf(["termux-camera-photo", "-c", str(int(p.get("kamera") or 0)), str(ziel)], timeout=60.0)
        return f"Foto gespeichert: {ziel}"
    if aktion == "link_oeffnen":
        url = str(p.get("text", ""))
        if not url.startswith(("http://", "https://")):
            raise HandyFehler("Nur http(s)-Links.")
        _lauf(["termux-open-url", url])
        return "Geoeffnet."
    raise HandyFehler(f"Unbekannte Aktion: {aktion}")


# -- ADB: das ganze Handy -------------------------------------------------------------------------
_TASTEN = {"zurueck": 4, "home": 3, "apps": 187, "enter": 66, "loeschen": 67, "an_aus": 26, "lauter": 24,
           "leiser": 25, "menue": 82, "suchen": 84}


def adb_geraet(ausfuehren=subprocess.run) -> str:
    """Seriennummer des verbundenen Geraets (bevorzugt das eigene Handy per localhost)."""
    zeilen = _lauf(["adb", "devices"], ausfuehren=ausfuehren).splitlines()[1:]
    geraete = [z.split()[0] for z in zeilen if z.strip().endswith("device")]
    if not geraete:
        raise HandyFehler("Kein Handy per ADB verbunden. Einmalig: Entwickleroptionen > Kabelloses Debugging an, "
                          "dann /handysteuerung koppeln <Kopplungsport> <Code> und /handysteuerung verbinden <Port>.")
    lokal = [s for s in geraete if s.startswith(("localhost:", "127.0.0.1:"))]
    return (lokal or geraete)[0]


def adb(args: list[str], timeout: float = 30.0, ausfuehren=subprocess.run) -> str:
    return _lauf(["adb", "-s", adb_geraet(ausfuehren), *args], timeout=timeout, ausfuehren=ausfuehren)


def koppeln(port: int, code: str, ausfuehren=subprocess.run) -> str:
    return _lauf(["adb", "pair", f"localhost:{int(port)}", str(code)], ausfuehren=ausfuehren)


def verbinden(port: int, ausfuehren=subprocess.run) -> str:
    aus = _lauf(["adb", "connect", f"localhost:{int(port)}"], ausfuehren=ausfuehren)
    if "connected" not in aus:
        raise HandyFehler(aus or "Verbinden ging nicht.")
    return aus


def _mitte(bounds: str) -> tuple[int, int] | None:
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def elemente_aus_xml(xml: str, max_zeilen: int = 150) -> str:
    """uiautomator-Dump -> knappe Liste: was steht wo (Mitte zum Antippen)."""
    try:
        wurzel = ET.fromstring(xml[xml.find("<"):] if "<" in xml else xml)
    except ET.ParseError as exc:
        raise HandyFehler(f"Bildschirm liess sich nicht lesen ({exc}).") from exc
    zeilen = []
    for k in wurzel.iter("node"):
        text = (k.get("text") or "").strip()
        desc = (k.get("content-desc") or "").strip()
        klickbar = k.get("clickable") == "true"
        if not (text or desc or (klickbar and k.get("resource-id"))):
            continue
        mitte = _mitte(k.get("bounds", ""))
        if not mitte:
            continue
        rid = (k.get("resource-id") or "").split("/")[-1]
        teile = [f'"{text[:80]}"' if text else "", f"({desc[:60]})" if desc else "", f"[{rid}]" if rid else ""]
        zeilen.append(f"- {' '.join(t for t in teile if t)} @ {mitte[0]},{mitte[1]}{' klickbar' if klickbar else ''}")
        if len(zeilen) >= max_zeilen:
            zeilen.append("- ... (gekuerzt)")
            break
    return "\n".join(zeilen) or "(nichts Lesbares auf dem Bildschirm)"


def bildschirm_lesen(ausfuehren=subprocess.run) -> str:
    xml = adb(["exec-out", "uiautomator", "dump", "/dev/tty"], timeout=40.0, ausfuehren=ausfuehren)
    if "<hierarchy" not in xml:  # manche Geraete schreiben nur in eine Datei
        adb(["shell", "uiautomator", "dump", "/sdcard/nova_ui.xml"], timeout=40.0, ausfuehren=ausfuehren)
        xml = adb(["shell", "cat", "/sdcard/nova_ui.xml"], ausfuehren=ausfuehren)
    return elemente_aus_xml(xml)


def steuern(aktion: str, ausfuehren=subprocess.run, **p) -> str:
    zahl = lambda k: int(p.get(k) or 0)  # noqa: E731
    if aktion == "tippen":
        adb(["shell", "input", "tap", str(zahl("x")), str(zahl("y"))], ausfuehren=ausfuehren)
        return f"Getippt bei {zahl('x')},{zahl('y')}."
    if aktion == "wischen":
        adb(["shell", "input", "swipe", str(zahl("x")), str(zahl("y")), str(zahl("x2")), str(zahl("y2")),
             str(max(50, zahl("ms") or 300))], ausfuehren=ausfuehren)
        return "Gewischt."
    if aktion == "text":
        text = str(p.get("text", ""))
        # input text kennt keine Leerzeichen/Sonderzeichen direkt - %s ist das Leerzeichen
        sicher = re.sub(r"([\\'\"`$&|;<>()])", r"\\\1", text).replace(" ", "%s")
        adb(["shell", "input", "text", sicher], ausfuehren=ausfuehren)
        return "Text eingegeben."
    if aktion == "taste":
        code = _TASTEN.get(str(p.get("text", "")).lower())
        if code is None:
            raise HandyFehler(f"Unbekannte Taste. Moeglich: {', '.join(_TASTEN)}")
        adb(["shell", "input", "keyevent", str(code)], ausfuehren=ausfuehren)
        return "Taste gedrueckt."
    if aktion == "bildschirm":
        return bildschirm_lesen(ausfuehren)
    if aktion == "apps":
        aus = adb(["shell", "pm", "list", "packages", "-3"], ausfuehren=ausfuehren)
        return "\n".join(sorted(z.replace("package:", "- ") for z in aus.splitlines() if z.strip()))[:6000]
    if aktion == "app_starten":
        paket = str(p.get("text", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.]{3,200}", paket):
            raise HandyFehler("Bitte den Paketnamen, z.B. com.whatsapp (aktion 'apps' listet sie).")
        adb(["shell", "monkey", "-p", paket, "-c", "android.intent.category.LAUNCHER", "1"], ausfuehren=ausfuehren)
        return f"{paket} gestartet."
    if aktion == "installieren":
        datei = Path(str(p.get("datei", "")))
        if datei.suffix.lower() != ".apk" or not datei.is_file():
            raise HandyFehler("Bitte den Pfad zu einer .apk-Datei.")
        aus = adb(["install", "-r", str(datei)], timeout=300.0, ausfuehren=ausfuehren)
        return f"Installiert: {datei.name}\n{aus[-300:]}"
    if aktion == "screenshot":
        ziel = Path(str(p.get("datei") or "handy_screenshot.png"))
        adb(["shell", "screencap", "-p", "/sdcard/nova_screen.png"], ausfuehren=ausfuehren)
        adb(["pull", "/sdcard/nova_screen.png", str(ziel)], ausfuehren=ausfuehren)
        return f"Screenshot gespeichert: {ziel}"
    raise HandyFehler(f"Unbekannte Aktion: {aktion}")
