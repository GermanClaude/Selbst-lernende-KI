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
        open_window(info["url"], Path(root) / "data" / "browser-fenster")  # Browser-Ersatz: Fenster dazu
    else:
        message_box("Die KI-App ist schon offen - schau in der Taskleiste nach.")
    return True


def spawn_app(root: Path, wait_for_pid: int | None = None, extra: list[str] | None = None) -> bool:
    """Startet die KI als App in einem eigenen Prozess (unter Windows ohne Konsole)."""
    env = dict(os.environ)
    if wait_for_pid:
        env["KI_NEUSTART_VON"] = str(wait_for_pid)
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--app", *(extra or [])]
        env = {k: v for k, v in env.items() if not k.startswith("_PYI_")}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    else:
        exe = sys.executable
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if sys.platform == "win32" and os.path.exists(pythonw):
            exe = pythonw
        cmd = [exe, "-m", "assistant", "--app", *(extra or [])]
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


def webview_storage(root: Path) -> Path:
    """Profilordner des App-Fensters (WebView2): lokal unter %LOCALAPPDATA% - nicht auf dem
    Desktop/OneDrive (dort kann WebView2 scheitern) und nicht im Programmordner."""
    import hashlib

    base = os.environ.get("LOCALAPPDATA")
    if sys.platform == "win32" and base:
        key = hashlib.sha1(str(Path(root).resolve()).lower().encode("utf-8")).hexdigest()[:10]
        return Path(base) / "SelbstLernendeKI" / f"fenster-{key}"
    return Path(root) / "data" / "app-fenster"


def _watch_dotnet_crash(root: Path) -> None:
    """Stuerzt das Fenster in .NET ab (pythonnet), beendet Windows sonst still das ganze
    Programm. Vorher: ins Protokoll schreiben, Bescheid sagen, Browser-Ersatz anbieten."""
    if sys.platform != "win32":
        return
    try:
        import clr  # type: ignore  # noqa: F401 - pythonnet, dieselbe Laufzeit nutzt pywebview
        from System import AppDomain, UnhandledExceptionEventHandler  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.info("Kein .NET-Absturzmelder: %s", exc)
        return

    def on_crash(_sender, args) -> None:
        try:
            logger.error("App-Fenster abgestuerzt (.NET): %s", args.ExceptionObject)
            for handler in logger.handlers:
                handler.flush()
            if ask_yes_no("Das App-Fenster ist leider abgestuerzt (Einzelheiten in logs\\ki.log).\n\n"
                          "Soll ich mich stattdessen in einem Browser-Fenster oeffnen?"):
                spawn_app(root, wait_for_pid=os.getpid(), extra=["--browser"])
        except Exception:  # noqa: BLE001
            pass

    AppDomain.CurrentDomain.UnhandledException += UnhandledExceptionEventHandler(on_crash)


def kamera_herkunft_ok(uri: str, port: int) -> bool:
    """Nur unsere eigene Seite (http://127.0.0.1:<port>/...) darf die Kamera bekommen."""
    from urllib.parse import urlsplit

    try:
        teile = urlsplit(str(uri or ""))
        return (teile.scheme == "http" and teile.hostname in ("127.0.0.1", "localhost")
                and teile.port == int(port) and not teile.username and not teile.password)
    except (ValueError, TypeError):
        return False


def kamera_entscheidung(art: str, uri: str, port: int, erlaubt: bool) -> str | None:
    """Was das Fenster bei einer Berechtigungsanfrage tun soll: "erlauben", "ablehnen" oder None
    (= Standard von WebView2, nichts anfassen). Nur die Kamera wird je von uns entschieden."""
    if art != "Camera":
        return None
    if erlaubt and kamera_herkunft_ok(uri, port):
        return "erlauben"
    return "ablehnen"  # ohne deine Zustimmung zu Live-Sehen nie die Kamera


def _kamera_erlaubnis_einrichten(window, ctl, port: int, holder: dict) -> None:
    """WebView2 (Windows): Kamera-Anfragen unserer Seite erlauben - aber nur, solange du Live-Sehen
    mit Webcam zugestimmt und eingeschaltet hast; nie dauerhaft im Profil gespeichert. Alles andere
    (Mikrofon, Standort ...) bleibt beim Standard. Geht es nicht (aeltere pywebview, anderes System),
    fragt das Fenster eben selbst nach."""
    if sys.platform != "win32" or holder.get("kamera_handler"):
        return
    try:
        form = window.native
        from Microsoft.Web.WebView2.Core import CoreWebView2PermissionState  # type: ignore
        from System import Action  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.info("Kamera-Erlaubnis im Fenster nicht eingerichtet: %s", exc)
        return

    def anfrage(_sender, args) -> None:
        try:
            art = str(args.PermissionKind).rsplit(".", 1)[-1]
            entscheidung = kamera_entscheidung(art, str(args.Uri), port, bool(ctl.kamera_erlaubt()))
            if entscheidung is None:
                return
            try:
                args.SavesInProfile = False  # nie fuer spaeter merken
            except Exception:  # noqa: BLE001 - aeltere WebView2
                pass
            args.State = (CoreWebView2PermissionState.Allow if entscheidung == "erlauben"
                          else CoreWebView2PermissionState.Deny)
            logger.info("Kamera-Anfrage im Fenster: %s", entscheidung)
        except Exception as exc:  # noqa: BLE001
            logger.info("Kamera-Anfrage: %s", exc)

    def einrichten() -> None:
        try:
            core = form.browser.webview.CoreWebView2  # nur im Fenster-Thread erlaubt
            if core is None:
                return
            core.PermissionRequested += anfrage
            holder["kamera_handler"] = anfrage  # Verweis behalten
        except Exception as exc:  # noqa: BLE001
            logger.info("Kamera-Erlaubnis im Fenster nicht eingerichtet: %s", exc)

    try:
        form.Invoke(Action(einrichten))  # WebView2 nur aus dem Fenster-Thread anfassen
    except Exception as exc:  # noqa: BLE001
        logger.info("Kamera-Erlaubnis im Fenster nicht eingerichtet: %s", exc)


def run_native_window(server, ctl, title: str, storage: Path, on_quit_holder: dict) -> bool:
    """Zeigt die App in einem echten Programmfenster. Blockiert, bis es zu ist.

    False = ging nicht (dann ersatzweise Browser-Fenster)."""
    try:
        import webview  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.info("pywebview nicht verfuegbar: %s", exc)
        return False
    shown = threading.Event()
    try:
        webview.settings["ALLOW_DOWNLOADS"] = True  # "Speichern" bei Bildern (Download-Links)
    except Exception:  # noqa: BLE001 - aeltere pywebview ohne settings
        pass
    try:
        logger.info("App: Programmfenster wird geoeffnet (pywebview %s, Profil %s)",
                    getattr(webview, "__version__", "?"), storage)
        window = webview.create_window(
            title, server.url, width=1200, height=860, min_size=(480, 560),
            background_color="#111318", text_select=True,
        )
        steps = {"initialized": "Darstellung bereit", "before_show": "Fenster wird gezeigt",
                 "shown": "Fenster sichtbar", "loaded": "Seite geladen"}
        for name, text in steps.items():
            try:
                getattr(window.events, name).__iadd__(lambda *a, _t=text: logger.info("App: %s", _t))
            except Exception:  # noqa: BLE001 - aeltere pywebview
                pass
        try:
            window.events.shown += lambda *a: shown.set()
        except Exception:  # noqa: BLE001 - aeltere pywebview: dann eben ohne diese Pruefung
            shown.set()
        try:  # Live-Sehen lief evtl. schon vor dem Fenster an: eigenes Fenster jetzt aus der Aufnahme nehmen
            window.events.shown += lambda *a: getattr(ctl, "sehen_fenster_schuetzen", lambda: None)()
        except Exception:  # noqa: BLE001 - aeltere pywebview
            pass
        try:  # Live-Sehen mit Webcam: Kamera nur fuer unsere Seite und nur mit Zustimmung
            window.events.loaded += lambda *a: _kamera_erlaubnis_einrichten(window, ctl, server.port, on_quit_holder)
        except Exception:  # noqa: BLE001 - aeltere pywebview
            pass
        on_quit_holder["close"] = window.destroy  # /beenden oder Neustart schliesst das Fenster
        if not on_quit_holder.get("started"):
            on_quit_holder["started"] = True
            ctl.startup()
        storage.mkdir(parents=True, exist_ok=True)
        if os.environ.get("KI_SELBSTTEST"):
            threading.Thread(target=_selftest, args=(webview, window, shown, server, on_quit_holder),
                             daemon=True).start()
        else:
            threading.Thread(target=_watch_blank, args=(window, shown, server, on_quit_holder),
                             daemon=True).start()
        _watch_dotnet_crash(Path(server.root) if hasattr(server, "root") else Path.cwd())
        webview.start(private_mode=False, storage_path=str(storage))  # laeuft bis das Fenster zu ist
    except Exception as exc:  # noqa: BLE001 - z.B. WebView2 fehlt
        logger.warning("Programmfenster ging nicht: %s", exc, exc_info=True)
        on_quit_holder.pop("close", None)
        return False
    if on_quit_holder.get("beendet"):
        logger.info("App: Programmfenster geschlossen (gewollt)")
        return True
    if on_quit_holder.pop("leer", False) or not server.hub.ever_connected:
        # Das Fenster hat die Oberflaeche nie geladen (z.B. WebView2 kaputt) - nicht still beenden!
        logger.warning("App: Oberflaeche wurde im Programmfenster nie geladen (gezeigt=%s)", shown.is_set())
        on_quit_holder.pop("close", None)
        return False
    logger.info("App: Programmfenster geschlossen")
    return True


def _watch_blank(window, shown: threading.Event, server, holder: dict) -> None:
    """Wachhund: Bleibt das Fenster leer (Seite laedt nie), Fenster zu -> Browser-Ersatz anbieten."""
    if not shown.wait(120):
        return
    end = time.monotonic() + 40
    while time.monotonic() < end:
        if server.hub.ever_connected:
            return
        time.sleep(0.5)
    logger.warning("App: Fenster bleibt leer - die Oberflaeche laedt nicht (WebView2?)")
    holder["leer"] = True
    try:
        window.destroy()
    except Exception as exc:  # noqa: BLE001
        logger.info("Leeres Fenster liess sich nicht schliessen: %s", exc)


def _selftest(webview, window, shown: threading.Event, server, holder: dict) -> None:
    """KI_SELBSTTEST=1 (Pruefung auf GitHub): erscheint das Fenster, laedt die Seite? Dann zu."""
    ok_shown = shown.wait(90)
    logger.info("Selbsttest: Fenster gezeigt=%s, Darstellung=%s", ok_shown, getattr(webview, "renderer", "?"))
    end = time.monotonic() + 45
    while time.monotonic() < end and not server.hub.ever_connected:
        time.sleep(0.5)
    loaded = server.hub.ever_connected
    logger.info("Selbsttest: Seite geladen und verbunden=%s", loaded)
    holder["selftest"] = "ok" if ok_shown and loaded else "fehler"
    time.sleep(2)
    try:
        window.destroy()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Selbsttest: Fenster liess sich nicht schliessen: %s", exc)


def _crashed_last_time(info: Path) -> bool:
    """Liegt noch app.json vom letzten Programmfenster da, dessen Prozess nicht mehr laeuft?
    Dann ist das Fenster damals hart abgestuerzt (sonst raeumt die App app.json weg)."""
    try:
        data = json.loads(info.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
    except (OSError, ValueError, TypeError):
        return False
    if data.get("fenster") != "programm" or not pid or pid == os.getpid():
        return False
    try:
        from ..selbststart import _pid_alive, _process_table

        return not _pid_alive(pid, _process_table())
    except Exception:  # noqa: BLE001
        return False


def run_app(config, started_by: str | None = None, browser: bool = False) -> int:
    """Startet Server + Fenster; kehrt zurueck, wenn das Fenster geschlossen ist.

    browser=True: gleich im Browser-Fenster (z.B. nachdem das Programmfenster abgestuerzt ist)."""
    root = Path(config.project_root)
    server = AppServer(lambda broadcast: AppController(config, broadcast, started_by=started_by))
    server.start()
    server.root = root
    ctl = server.controller
    quit_now = threading.Event()
    result = {"code": 0}
    holder: dict = {}

    def on_quit(code: int) -> None:
        result["code"] = code
        holder["beendet"] = True  # gewollt (z.B. Neustart nach Update) - kein Fensterfehler
        logger.info("App: wird beendet (Code %s)", code)
        quit_now.set()
        close = holder.get("close")
        if close:
            try:
                close()
            except Exception:  # noqa: BLE001
                pass

    ctl.on_quit = on_quit
    info = _info_file(root)
    if not browser and _crashed_last_time(info):
        logger.warning("App: der letzte Start ist abgestuerzt - biete das Browser-Fenster an")
        if sys.platform == "win32" and ask_yes_no(
            "Beim letzten Mal ist das App-Fenster abgestuerzt.\n\nDiesmal lieber im Browser-Fenster oeffnen?\n"
            "(Nein = das Programmfenster nochmal versuchen)"
        ):
            browser = True
    try:
        info.parent.mkdir(parents=True, exist_ok=True)
        info.write_text(json.dumps({"pid": os.getpid(), "url": server.url, "fenster": "programm"}),
                        encoding="utf-8")
    except OSError as exc:
        logger.info("app.json nicht schreibbar: %s", exc)

    from .. import __version__

    meaning = config.ki.bedeutung.strip()
    title = f"{config.ki.name} - {meaning}" if meaning else f"{config.ki.name} - Selbst-lernende KI"
    title += f"  \u00b7  Version {__version__}"  # Versionsnummer gleich im Fenstertitel
    try:
        if browser:
            logger.info("App: im Browser-Fenster (gewuenscht)")
            _browser_fallback(server, ctl, root, quit_now, holder)
            return result["code"]
        if run_native_window(server, ctl, title, webview_storage(root), holder):
            if os.environ.get("KI_SELBSTTEST"):
                logger.info("Selbsttest: Ergebnis %s", holder.get("selftest", "fehler"))
                return 0 if holder.get("selftest") == "ok" else 3
            return result["code"]
        if os.environ.get("KI_SELBSTTEST"):
            logger.warning("Selbsttest: Programmfenster ging nicht")
            return 3
        # Ersatz nur nach Rueckfrage - die App soll ein eigenes Programm sein.
        if sys.platform == "win32" and not ask_yes_no(
            "Das App-Fenster konnte nicht geoeffnet werden (fehlt die Microsoft WebView2-Laufzeit?).\n\n"
            "Stattdessen in einem Browser-Fenster oeffnen?\n\n"
            f"(Einzelheiten stehen in {root / 'logs' / 'ki.log'})"
        ):
            return 0
        _browser_fallback(server, ctl, root, quit_now, holder)
        return result["code"]
    finally:
        ctl.shutdown()
        server.stop()
        try:
            if json.loads(info.read_text(encoding="utf-8")).get("pid") == os.getpid():
                info.unlink()
        except (OSError, ValueError):
            pass


def _browser_fallback(server, ctl, root: Path, quit_now: threading.Event, holder: dict | None = None) -> None:
    """Ersatz: Edge/Chrome im App-Modus; endet, wenn kein Fenster mehr verbunden ist."""
    logger.info("App: Ersatz-Fenster im Browser")
    try:  # ein zweiter Start oeffnet dann ein weiteres Browser-Fenster statt "schon offen"
        _info_file(root).write_text(json.dumps({"pid": os.getpid(), "url": server.url, "fenster": "browser"}),
                                    encoding="utf-8")
    except OSError:
        pass
    open_window(server.url, root / "data" / "browser-fenster")
    if holder is None or not holder.get("started"):
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
