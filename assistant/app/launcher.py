"""Oeffnet das App-Fenster und haelt alles am Laufen, bis das Fenster zu ist.

Normalfall: ein echtes Programmfenster (pywebview) - eigenes Fenster, eigenes
Symbol in der Taskleiste, kein Browser. Unter Windows zeigt es die Oberflaeche mit
der eingebauten Windows-Komponente WebView2 an (wie Teams oder Discord).

Nur wenn das nicht geht (pywebview fehlt, WebView2 fehlt), wird nach Rueckfrage
ersatzweise ein Browser-Fenster (Edge/Chrome im App-Modus) benutzt; dann endet die
KI, sobald kein Fenster mehr verbunden ist.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from ..logging_setup import get_logger
from .controller import AppController
from .server import AppServer

logger = get_logger()

_CLOSED_AFTER = 8.0      # so lange kein Fenster verbunden = geschlossen
_FIRST_CONNECT = 45.0    # kommt bis dahin kein Fenster, Standardbrowser versuchen
_GIVE_UP = 180.0         # ... und spaetestens dann aufgeben


def find_browser() -> str | None:
    """Pfad zu Edge oder Chrome (fuer den App-Modus) - oder None."""
    if sys.platform == "win32":
        candidates = []
        try:
            import winreg  # type: ignore

            for exe in ("msedge.exe", "chrome.exe"):
                for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    try:
                        key = winreg.OpenKey(hive, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe}")
                        with key:
                            candidates.append(winreg.QueryValue(key, None))
                    except OSError:
                        continue
        except ImportError:
            pass
        for env, sub in (("ProgramFiles(x86)", r"Microsoft\Edge\Application\msedge.exe"),
                         ("ProgramFiles", r"Microsoft\Edge\Application\msedge.exe"),
                         ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
                         ("ProgramFiles", r"Google\Chrome\Application\chrome.exe"),
                         ("ProgramFiles(x86)", r"Google\Chrome\Application\chrome.exe")):
            base = os.environ.get(env)
            if base:
                candidates.append(os.path.join(base, sub))
        return next((c for c in candidates if c and os.path.isfile(c.strip('"'))), None)
    if sys.platform == "darwin":
        for app in ("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
            if os.path.isfile(app):
                return app
    for name in ("microsoft-edge", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def open_window(url: str, profile_dir: Path) -> subprocess.Popen | None:
    """Oeffnet das App-Fenster. None = es wurde der Standardbrowser benutzt (oder nichts)."""
    browser = find_browser()
    if browser:
        try:
            profile_dir.mkdir(parents=True, exist_ok=True)
            return subprocess.Popen(
                [browser.strip('"'), f"--app={url}", f"--user-data-dir={profile_dir}",
                 "--window-size=1200,860", "--no-first-run", "--no-default-browser-check",
                 "--disable-features=Translate"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            logger.warning("App-Fenster konnte nicht geoeffnet werden: %s", exc)
    webbrowser.open(url)
    return None


def _info_file(root: Path) -> Path:
    return Path(root) / "data" / "app.json"


def open_existing_window(root: Path, pid: int) -> bool:
    """Laeuft die App schon? Dann True (das vorhandene Fenster bleibt das einzige)."""
    try:
        info = json.loads(_info_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if int(info.get("pid", 0)) != pid or not info.get("url"):
        return False
    if info.get("fenster") != "programm":
        open_window(info["url"], Path(root) / "data" / "app-fenster")  # Browser-Ersatz: Fenster dazu
    else:
        message_box("Die KI-App ist schon offen - schau in der Taskleiste nach.")
    return True


def spawn_app(root: Path, wait_for_pid: int | None = None) -> bool:
    """Startet die KI als App in einem eigenen Prozess (unter Windows ohne Konsole)."""
    env = dict(os.environ)
    if wait_for_pid:
        env["KI_NEUSTART_VON"] = str(wait_for_pid)
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--app"]
        env = {k: v for k, v in env.items() if not k.startswith("_PYI_")}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    else:
        exe = sys.executable
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if sys.platform == "win32" and os.path.exists(pythonw):
            exe = pythonw
        cmd = [exe, "-m", "assistant", "--app"]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen(cmd, cwd=str(root), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=flags if sys.platform == "win32" else 0,
                         start_new_session=sys.platform != "win32")
        return True
    except OSError as exc:
        logger.warning("App konnte nicht gestartet werden: %s", exc)
        return False


def spawn_terminal(root: Path, wait_for_pid: int | None = None) -> bool:
    """Oeffnet die Terminal-Version in einem eigenen Konsolenfenster (Windows)."""
    if sys.platform != "win32":
        return False
    env = dict(os.environ)
    if wait_for_pid:
        env["KI_NEUSTART_VON"] = str(wait_for_pid)  # wartet, bis die App zu ist
    if getattr(sys, "frozen", False):
        own = Path(sys.executable)
        sibling = own.with_name("KI.exe")
        exe = sibling if sibling.exists() and sibling.resolve() != own.resolve() else own
        cmd = [str(exe), "--terminal"]
        env = {k: v for k, v in env.items() if not k.startswith("_PYI_")}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    else:
        exe = sys.executable
        if os.path.basename(exe).lower() == "pythonw.exe":
            exe = os.path.join(os.path.dirname(exe), "python.exe")  # mit Konsole
        cmd = [exe, "-m", "assistant", "--terminal"]
    try:
        subprocess.Popen(cmd, cwd=str(root), env=env, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        return True
    except OSError as exc:
        logger.warning("Terminal konnte nicht gestartet werden: %s", exc)
        return False


def create_desktop_shortcut(root: Path, name: str) -> str:
    """Legt eine Verknuepfung auf dem Desktop an, die die KI als App oeffnet."""
    root = Path(root)
    if sys.platform != "win32":
        raise OSError("Verknuepfungen gibt es hier nur unter Windows - nutze ./start.sh app")
    if getattr(sys, "frozen", False):
        target, args, workdir = sys.executable, "--app", str(Path(sys.executable).parent)
    else:
        target, args, workdir = str(root / "start-app.bat"), "", str(root)
    safe_name = "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "KI"
    script = (
        "$s = New-Object -ComObject WScript.Shell; "
        "$d = [Environment]::GetFolderPath('Desktop'); "
        f"$l = $s.CreateShortcut((Join-Path $d '{safe_name}.lnk')); "
        f"$l.TargetPath = '{target}'; $l.Arguments = '{args}'; $l.WorkingDirectory = '{workdir}'; "
        "$l.WindowStyle = 7; $l.Description = 'Selbst-lernende KI als App'; $l.Save(); "
        "Write-Output (Join-Path $d '" + safe_name + ".lnk')"
    )
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise OSError((proc.stderr or proc.stdout).strip() or "Verknuepfung konnte nicht angelegt werden")
    return proc.stdout.strip()


def message_box(text: str, title: str = "Selbst-lernende KI") -> None:
    """Meldung, auch ohne Konsole (die App laeuft unter Windows mit pythonw)."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        print(text)
    except Exception:  # noqa: BLE001
        pass


def ask_yes_no(text: str, title: str = "Selbst-lernende KI") -> bool:
    """Ja/Nein-Meldung ohne Konsole (Windows), sonst False."""
    if sys.platform == "win32":
        try:
            import ctypes

            return ctypes.windll.user32.MessageBoxW(None, text, title, 0x4 | 0x20) == 6  # MB_YESNO, IDYES
        except Exception:  # noqa: BLE001
            return False
    return False


def native_window_available() -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec("webview") is not None
    except (ImportError, ValueError):
        return False


def run_native_window(server, ctl, title: str, storage: Path, on_quit_holder: dict) -> bool:
    """Zeigt die App in einem echten Programmfenster. Blockiert, bis es zu ist.

    False = ging nicht (dann ersatzweise Browser-Fenster)."""
    try:
        import webview  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.info("pywebview nicht verfuegbar: %s", exc)
        return False
    try:
        window = webview.create_window(
            title, server.url, width=1200, height=860, min_size=(480, 560),
            background_color="#111318", text_select=True,
        )
        on_quit_holder["close"] = window.destroy  # /beenden oder Neustart schliesst das Fenster
        ctl.startup()
        storage.mkdir(parents=True, exist_ok=True)
        webview.start(private_mode=False, storage_path=str(storage))  # laeuft bis das Fenster zu ist
        return True
    except Exception as exc:  # noqa: BLE001 - z.B. WebView2 fehlt
        logger.warning("Programmfenster ging nicht: %s", exc)
        on_quit_holder.pop("close", None)
        return False


def run_app(config, started_by: str | None = None) -> int:
    """Startet Server + Fenster; kehrt zurueck, wenn das Fenster geschlossen ist."""
    root = Path(config.project_root)
    server = AppServer(lambda broadcast: AppController(config, broadcast, started_by=started_by))
    server.start()
    ctl = server.controller
    quit_now = threading.Event()
    result = {"code": 0}
    holder: dict = {}

    def on_quit(code: int) -> None:
        result["code"] = code
        quit_now.set()
        close = holder.get("close")
        if close:
            try:
                close()
            except Exception:  # noqa: BLE001
                pass

    ctl.on_quit = on_quit
    info = _info_file(root)
    try:
        info.parent.mkdir(parents=True, exist_ok=True)
        info.write_text(json.dumps({"pid": os.getpid(), "url": server.url, "fenster": "programm"}),
                        encoding="utf-8")
    except OSError as exc:
        logger.info("app.json nicht schreibbar: %s", exc)

    meaning = config.ki.bedeutung.strip()
    title = f"{config.ki.name} - {meaning}" if meaning else f"{config.ki.name} - Selbst-lernende KI"
    try:
        if run_native_window(server, ctl, title, root / "data" / "app-fenster", holder):
            return result["code"]
        # Ersatz nur nach Rueckfrage - die App soll ein eigenes Programm sein.
        if sys.platform == "win32" and not ask_yes_no(
            "Das App-Fenster konnte nicht geoeffnet werden (fehlt pywebview oder die Microsoft "
            "WebView2-Laufzeit?).\n\nStattdessen in einem Browser-Fenster oeffnen?"
        ):
            return 0
        _browser_fallback(server, ctl, root, quit_now)
        return result["code"]
    finally:
        ctl.shutdown()
        server.stop()
        try:
            if json.loads(info.read_text(encoding="utf-8")).get("pid") == os.getpid():
                info.unlink()
        except (OSError, ValueError):
            pass


def _browser_fallback(server, ctl, root: Path, quit_now: threading.Event) -> None:
    """Ersatz: Edge/Chrome im App-Modus; endet, wenn kein Fenster mehr verbunden ist."""
    open_window(server.url, root / "data" / "app-fenster")
    ctl.startup()
    began = time.monotonic()
    fallback_done = False
    try:
        while not quit_now.wait(1.0):
            hub = server.hub
            if hub.connected:
                continue
            if hub.ever_connected:
                if time.monotonic() - hub.last_seen > _CLOSED_AFTER:
                    break  # Fenster geschlossen
            elif time.monotonic() - began > _FIRST_CONNECT and not fallback_done:
                fallback_done = True
                webbrowser.open(server.url)
            elif time.monotonic() - began > _GIVE_UP:
                message_box("Das App-Fenster liess sich nicht oeffnen. Starte die KI mit start.bat im Terminal.")
                break
    except KeyboardInterrupt:
        pass
