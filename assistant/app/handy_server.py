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


def cloud_einstellungen(root) -> dict:
    """Cloud-Server (Docker / VPS / Hugging Face): Port, Schluessel und erlaubte Adressen aus der Umgebung.
    NOVA_TOKEN (mind. 24 Zeichen) ist der Schluessel - ohne ihn wird einer erzeugt und in data/ gemerkt.
    NOVA_HOST = deine Adresse (z.B. nova-xyz.hf.space); leer = jede Adresse, dann schuetzt nur der Schluessel."""
    try:
        port = int(os.environ.get("PORT", "") or 8765)
    except ValueError:
        port = 8765
    token = os.environ.get("NOVA_TOKEN", "").strip()
    eigener = len(token) >= 24
    if not eigener:
        token = fester_token(root)
    hosts = [h.strip().lower() for h in os.environ.get("NOVA_HOST", "").replace(";", ",").split(",") if h.strip()]
    return {"port": port, "token": token, "token_eigen": eigener, "hosts": set(hosts) or "*"}


def run_cloud(config) -> int:
    """Nova als Dienst im Internet: laeuft rund um die Uhr, auch wenn dein PC aus ist. Die Handy-App (oder ein
    Browser) verbindet sich mit https://<deine-adresse>/?t=<NOVA_TOKEN>. Telegram beantwortet sie von dort."""
    e = cloud_einstellungen(config.project_root)
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        os.environ.setdefault("TELEGRAM_AUTOSTART", "1")   # Telegram immer beantworten (eigener Bot-Abruf)
    print(f"Cloud-Modus: Port {e['port']}, erlaubte Adressen: "
          f"{'alle (Schutz durch den Schluessel)' if e['hosts'] == '*' else ', '.join(sorted(e['hosts']))}")
    if not e["token_eigen"]:
        print("Kein NOVA_TOKEN gesetzt - erzeugter Schluessel (data/server_token): " + e["token"])
        print("Besser: NOVA_TOKEN als Geheimnis beim Anbieter eintragen, sonst aendert er sich nach einem Neustart "
              "ohne dauerhaften Speicher.")
    return run_server(config, port=e["port"], oeffnen=False, host="0.0.0.0", token=e["token"], hosts=e["hosts"],
                      vorbereiten=lambda server: telegram_webhook_einrichten(server, e["token"]))


def oeffentliche_adresse() -> str:
    """Die https-Adresse der Cloud-Nova (NOVA_PUBLIC_URL; Render setzt RENDER_EXTERNAL_URL selbst)."""
    adr = (os.environ.get("NOVA_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    return adr if adr.startswith("https://") else ""


def telegram_webhook_einrichten(server, nova_token: str) -> bool:
    """Cloud: Telegram schickt Nachrichten an Nova (Webhook) - das weckt auch eine schlafende Cloud-Nova.
    Braucht TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID und eine https-Adresse. Sonst False (dann Abholen wie am PC)."""
    import hashlib

    from ..handy import TelegramFehler, WebhookRelay

    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    adresse = oeffentliche_adresse()
    if not bot or not adresse or os.environ.get("TELEGRAM_WEBHOOK") == "0":
        return False
    ctl = server.controller
    chat_id = ctl._handy_chat_id()
    if chat_id is None:
        print("Telegram: TELEGRAM_CHAT_ID fehlt - trag sie beim Anbieter ein (steht in der .env auf deinem PC, "
              "sobald du /handy dort einmal benutzt hast).")
        return False
    geheim = hashlib.sha256(f"nova-telegram|{bot}|{nova_token}".encode()).hexdigest()[:48]
    pfad = "/telegram/" + geheim[:24]
    relay = WebhookRelay(bot, chat_id=chat_id)
    try:
        relay.webhook_setzen(adresse + pfad, geheim)
    except TelegramFehler as exc:
        print(f"Telegram-Webhook ging nicht ({exc}) - ich hole die Nachrichten stattdessen selbst ab.")
        return False
    server.telegram = (pfad, geheim, relay)
    ctl._handy_relay_fabrik = lambda token, chat: relay
    sperre = threading.Lock()

    def wecken() -> None:
        with sperre:
            if not ctl._handy_aktiv():
                ctl._handy_befehl([])           # startet den Fernzugriff-Thread und kehrt gleich zurueck

    relay.wecken = wecken
    # Nicht zusaetzlich beim Start automatisch losgehen (sonst zwei Schleifen) - kurz nach dem Start einmal wecken.
    os.environ["TELEGRAM_AUTOSTART"] = "0"
    threading.Timer(5.0, wecken).start()
    print("Telegram: Nachrichten an deinen Bot kommen direkt hier an (Webhook) - auch wenn der PC aus ist.")
    return True


def run_server(config, port: int = 8765, oeffnen: bool = True, host: str = "127.0.0.1",
               token: str | None = None, hosts=None, vorbereiten=None) -> int:
    from .controller import AppController
    from .server import AppServer

    root = Path(config.project_root)
    try:
        server = AppServer(lambda broadcast: AppController(config, broadcast), host=host, port=int(port),
                           token=token or fester_token(root), hosts=hosts)
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
    if vorbereiten is not None:
        try:
            vorbereiten(server)
        except Exception:  # noqa: BLE001 - Nova soll trotzdem laufen
            logger.exception("Cloud: Vorbereitung fehlgeschlagen")
    ctl.startup()
    if host == "127.0.0.1":
        print(f"\n{config.ki.name} laeuft. Oberflaeche: {server.url}")
        print("(Diese Adresse ist dein Schluessel - nicht weitergeben. Beenden: Strg+C)")
    else:  # Cloud: den Schluessel nicht ins (evtl. mitgelesene) Protokoll schreiben
        print(f"\n{config.ki.name} laeuft in der Cloud. Oberflaeche: https://<deine-adresse>/?t=<NOVA_TOKEN>")
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

