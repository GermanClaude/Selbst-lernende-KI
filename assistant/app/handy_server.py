"""Nova als reiner Server - fuer das Handy (Termux) oder jeden Rechner ohne Programmfenster.

Anders als das Browser-Ersatzfenster beendet sich der Server NICHT, wenn gerade kein Fenster verbunden ist
(auf dem Handy wechselst du staendig die App). Er laeuft, bis du ihn mit Strg+C oder /beenden stoppst.

- Fester Port (Standard 8765) und ein fester Schluessel in data/server_token - so merkt sich die Nova-APK
  die Adresse und findet Nova nach jedem Neustart wieder.
- Nur auf 127.0.0.1: andere Geraete im WLAN kommen nicht heran, andere Apps nur mit dem Schluessel.
- Oeffnet die Oberflaeche: in Termux zuerst die Nova-APK (falls installiert), sonst den Browser.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import threading
from pathlib import Path

from ..logging_setup import get_logger

logger = get_logger()

APK_PAKET = "de.nova.handy"
APK_AKTIVITAET = "de.nova.handy/.MainActivity"


from ..handy_steuerung import ist_termux  # noqa: E402,F401 - hier gebraucht und fuer andere Module


def fester_token(root) -> str:
    """Der dauerhafte Schluessel fuer den Server (wird einmal erzeugt, nur fuer dich lesbar)."""
    pfad = Path(root) / "data" / "server_token"
    try:
        token = pfad.read_text(encoding="utf-8").strip()
        if len(token) >= 24:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(token, encoding="utf-8")
    try:
        os.chmod(pfad, 0o600)
    except OSError:
        pass
    return token


def oberflaeche_oeffnen(url: str, ausfuehren=subprocess.run) -> str:
    """Oeffnet die Oberflaeche. Gibt zurueck, womit ('apk', 'termux-browser', 'browser' oder '')."""
    if ist_termux():
        if shutil.which("am"):
            r = ausfuehren(["am", "start", "-n", APK_AKTIVITAET, "-a", "android.intent.action.VIEW", "-d", url],
                           capture_output=True, text=True)
            ausgabe = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
            if getattr(r, "returncode", 1) == 0 and "Error" not in ausgabe:
                return "apk"
        if shutil.which("termux-open-url"):
            ausfuehren(["termux-open-url", url])
            return "termux-browser"
        return ""
    import webbrowser

    return "browser" if webbrowser.open(url) else ""


def run_server(config, port: int = 8765, oeffnen: bool = True) -> int:
    from .controller import AppController
    from .server import AppServer

    root = Path(config.project_root)
    try:
        server = AppServer(lambda broadcast: AppController(config, broadcast), port=int(port),
                           token=fester_token(root))
    except OSError as exc:
        print(f"Port {port} ist belegt ({exc}). Laeuft Nova schon? Sonst: --port 8766")
        return 1
    server.start()
    server.root = root
    ctl = server.controller
    fertig = threading.Event()
    ergebnis = {"code": 0}

    def on_quit(code: int) -> None:
        ergebnis["code"] = code
        fertig.set()

    ctl.on_quit = on_quit
    try:
        info = root / "data" / "app.json"
        info.parent.mkdir(parents=True, exist_ok=True)
        info.write_text(json.dumps({"pid": os.getpid(), "url": server.url, "fenster": "server"}), encoding="utf-8")
    except OSError:
        pass
    ctl.startup()
    print(f"\n{config.ki.name} laeuft. Oberflaeche: {server.url}")
    print("(Diese Adresse ist dein Schluessel - nicht weitergeben. Beenden: Strg+C)")
    if oeffnen:
        womit = oberflaeche_oeffnen(server.url)
        if womit == "apk":
            print("Die Nova-App wurde geoeffnet.")
        elif womit:
            print("Im Browser geoeffnet. Tipp: Mit der Nova-APK sieht es aus wie eine echte App.")
        else:
            print("Oeffne die Adresse oben im Browser.")
    if ist_termux() and shutil.which("termux-wake-lock"):
        subprocess.run(["termux-wake-lock"])  # Android soll Nova im Hintergrund nicht schlafen legen
    try:
        while not fertig.wait(1.0):
            pass
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        ctl.shutdown()
        server.stop()
        if ist_termux() and shutil.which("termux-wake-unlock"):
            subprocess.run(["termux-wake-unlock"])
    return ergebnis["code"]

