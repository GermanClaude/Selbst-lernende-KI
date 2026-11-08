#!/usr/bin/env python3
"""Start-Skript fuer die Selbst-lernende-KI.

Dieses Skript ist der Einstiegspunkt - auch fuer die .exe. Es sorgt dafuer, dass
beim ersten Start (etwa aus einer gepackten .exe heraus) eine beschreibbare
Konfiguration neben der Programmdatei angelegt wird.
"""
from __future__ import annotations

import os
import shutil
import sys
import traceback
from pathlib import Path


def _ensure_runtime_dir() -> None:
    """Legt bei Bedarf config/ und .env aus den Vorlagen im Programmordner an."""
    if not getattr(sys, "frozen", False):
        return  # Nur im gepackten Zustand noetig.
    # Derselbe Ordner, aus dem load_config spaeter liest (neben der .exe bzw. der
    # Projektordner, wenn die .exe in dessen 'dist'-Ordner liegt).
    from assistant.config import PROJECT_ROOT, bundle_dir

    root, bundle = PROJECT_ROOT, bundle_dir()
    config_dir = root / "config"
    config_dir.mkdir(exist_ok=True)
    for name in ("settings.example.toml", "persona.md", "werte.md"):
        src = bundle / "config" / name
        dst = config_dir / name
        if src.exists() and not dst.exists():
            shutil.copyfile(src, dst)
    # settings.toml aus der Vorlage erzeugen, falls noch keine da ist.
    settings = config_dir / "settings.toml"
    example = config_dir / "settings.example.toml"
    if example.exists() and not settings.exists():
        shutil.copyfile(example, settings)
    # .env-Vorlage anlegen, damit klar ist, wo der Schluessel hingehoert.
    env_example = bundle / ".env.example"
    if env_example.exists() and not (root / ".env").exists():
        shutil.copyfile(env_example, root / ".env")
        print(f"Ich habe die Datei {root / '.env'} angelegt - trage dort deinen API-Schluessel ein.")
    # Arbeitsverzeichnis auf den Programmordner setzen, damit relative Pfade passen.
    os.chdir(root)


_WINDOWED = sys.stdout is None and sys.stdin is None  # beim Start gemerkt: Programm ohne Konsole


def _is_app_exe() -> bool:
    """KI-App.exe = dasselbe Programm, aber gleich als App (ohne Konsole). Auch wenn Windows
    sie beim Herunterladen 'KI-App (1).exe' genannt hat - und jede .exe ohne Konsole."""
    if not getattr(sys, "frozen", False):
        return False
    import re

    stem = re.sub(r"\s*\(\d+\)$", "", Path(sys.executable).stem).strip().lower()
    return stem.endswith("app") or _WINDOWED


def _open_console() -> None:
    """KI-App.exe --terminal: ein Konsolenfenster oeffnen (die App-Exe hat sonst keins)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        if not kernel.GetConsoleWindow() and kernel.AllocConsole():
            kernel.SetConsoleOutputCP(65001)
            kernel.SetConsoleCP(65001)
            sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")  # noqa: SIM115
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)  # noqa: SIM115
            sys.stderr = sys.stdout
    except Exception:  # noqa: BLE001 - dann eben ohne Konsole
        pass


def _crash_log() -> None:
    """Harte Abstuerze (z.B. in einer DLL) in logs/absturz.log festhalten - sonst unsichtbar."""
    if not getattr(sys, "frozen", False):
        return
    try:
        import faulthandler

        from assistant.config import PROJECT_ROOT

        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handle = open(log_dir / "absturz.log", "a", encoding="utf-8")  # noqa: SIM115 - bleibt offen
        handle.write(f"\n--- Start {__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S} "
                     f"({' '.join(sys.argv[1:])}) ---\n")
        handle.flush()
        faulthandler.enable(handle)
    except Exception:  # noqa: BLE001
        pass


def _from_backup() -> bool:
    """Eine gesicherte alte Version aus versionen/ wurde gestartet (z.B. ueber eine alte
    Verknuepfung): die aktuelle starten und Bescheid geben. True = diese hier beendet sich."""
    if not getattr(sys, "frozen", False):
        return False
    from assistant.austausch import running_from_backup

    current = running_from_backup(Path(sys.executable))
    if current is None:
        return False
    import subprocess

    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI_")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env["KI_VERKNUEPFUNGEN_PRUEFEN"] = "1"
    try:
        subprocess.Popen([str(current), *sys.argv[1:]], cwd=str(current.parent), env=env,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    except OSError:
        return False
    try:
        from assistant.app.launcher import message_box

        message_box("Das war eine gesicherte alte Version aus dem Ordner 'versionen'. Ich starte die "
                    "aktuelle Version - und richte deine Verknuepfung wieder richtig ein.")
    except Exception:  # noqa: BLE001
        pass
    return True


def _after_start() -> None:
    """Nach einem Update: alte Helfer wegraeumen, Verknuepfungen reparieren (im Hintergrund)."""
    if not getattr(sys, "frozen", False):
        return
    try:
        from assistant import __version__
        from assistant.austausch import after_start
        from assistant.config import PROJECT_ROOT

        after_start(Path(sys.executable), PROJECT_ROOT, __version__,
                    force=os.environ.get("KI_VERKNUEPFUNGEN_PRUEFEN") == "1")
    except Exception:  # noqa: BLE001 - nie den Start stoeren
        pass


def main() -> int:
    # Projektpfad in sys.path aufnehmen (fuer den Start aus dem Quellordner).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if len(sys.argv) > 1 and sys.argv[1] == "--update-einspielen":
        # Update-Helfer (Kopie im Temp-Ordner): neue Version in die bestehende Datei schreiben
        from assistant.austausch import run_helper

        return run_helper(sys.argv[2:])
    if _from_backup():
        return 0
    if _is_app_exe() and "--terminal" in sys.argv:
        _open_console()  # aus der App heraus: Terminal-Version im eigenen Fenster
    elif _is_app_exe() and "--app" not in sys.argv:
        sys.argv.append("--app")
    from assistant.__main__ import safe_streams

    safe_streams()  # ohne Konsole: kein Absturz bei print()/isatty()
    _crash_log()
    try:
        _ensure_runtime_dir()
        _after_start()
        from assistant.__main__ import main as app_main

        code = app_main()
    except SystemExit as exc:  # z.B. argparse: falsche Argumente - in der App nicht still enden
        code = exc.code if isinstance(exc.code, int) else 1
        if code and "--app" in sys.argv:
            try:
                from assistant.app.launcher import message_box

                message_box(f"Die KI konnte nicht starten (Code {code}). Starte KI-App.exe bitte per Doppelklick.")
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001 - in der .exe sonst unsichtbar
        traceback.print_exc()
        if "--app" in sys.argv:  # kein Konsolenfenster: Fehler als Meldung zeigen
            try:
                from assistant.app.launcher import message_box

                message_box("Die KI konnte nicht starten:\n\n" + traceback.format_exc(limit=3))
            except Exception:  # noqa: BLE001
                pass
        code = 1
    # Die .exe schliesst ihr Fenster sofort - Fehler sonst nicht lesbar.
    # (43 = "laeuft schon in einem anderen Fenster" - dann still schliessen.)
    if code and code != 43 and getattr(sys, "frozen", False) and "--app" not in sys.argv:
        try:
            input("\nEnter druecken zum Schliessen...")
        except (EOFError, KeyboardInterrupt):
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
