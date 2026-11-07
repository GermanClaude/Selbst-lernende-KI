"""Einstiegspunkt: startet die KI.

Start:
    python -m assistant          (im Terminal)
    python -m assistant --app    (als App in einem eigenen Fenster)
oder nach Installation:
    ki
"""
from __future__ import annotations

import argparse
import sys

from .config import PROJECT_ROOT, ConfigError, load_config
from .logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ki",
        description="Selbst-lernende-KI - dein lokaler, lernfaehiger Assistent.",
    )
    parser.add_argument("--version", action="store_true", help="Version anzeigen")
    parser.add_argument(
        "--einrichten",
        action="store_true",
        help="Lege settings.toml / permissions aus den Beispielen an und beende.",
    )
    parser.add_argument("--app", action="store_true", help="Als App in einem eigenen Fenster starten")
    parser.add_argument("--terminal", action="store_true", help="Im Terminal starten (Standard)")
    args = parser.parse_args(argv)
    app_mode = args.app and not args.terminal

    if app_mode and getattr(sys, "frozen", False) and sys.platform == "win32":
        # KI.exe --app: das schwarze Konsolenfenster verschwinden lassen
        try:
            import ctypes
            import io

            ctypes.windll.kernel32.FreeConsole()
            sys.stdout = sys.stderr = io.StringIO()
        except Exception:  # noqa: BLE001
            pass

    if app_mode and sys.stdout is None:
        # pythonw (App ohne Konsole): Ausgaben ins Leere statt Absturz
        import io

        sys.stdout = sys.stderr = io.StringIO()

    if args.version:
        from . import __version__

        print(f"Selbst-lernende-KI {__version__}")
        return 0

    setup_logging(PROJECT_ROOT / "logs")
    try:
        config = load_config()
    except ConfigError as exc:
        if app_mode:
            from .app.launcher import message_box

            message_box(str(exc))
        print(exc)
        return 1

    from .selbststart import SILENT_EXIT_CODE, StartGuard

    if not app_mode and not args.terminal and config.ki.oberflaeche.strip().lower() == "app" \
            and not args.einrichten:
        # Eingestellt: als App. Das Terminal startet die App und schliesst sich still.
        from .app.launcher import spawn_app

        if spawn_app(config.project_root):
            return SILENT_EXIT_CODE

    guard = StartGuard(config.project_root)
    started_by, unexpected = guard.record_start()
    other = guard.running_pid() if config.ki.nur_ein_fenster else None
    if other and app_mode:
        from .app.launcher import message_box, open_existing_window

        # Laeuft schon als App: einfach ein Fenster dazu. Laeuft im Terminal: Bescheid sagen.
        if not open_existing_window(config.project_root, other) and not unexpected:
            message_box("Die KI laeuft schon in einem anderen Fenster (Terminal). "
                        "Schliesse es zuerst, dann startet die App.")
        return SILENT_EXIT_CODE
    if other:
        # Kein zweites Fenster: sonst stapeln sich KI-Fenster, wenn etwas sie
        # automatisch startet. /autostart im laufenden Fenster zeigt, was das ist.
        print(f"Die KI laeuft schon in einem anderen Fenster (PID {other}) - dieses schliesst sich.")
        if unexpected:
            print(f"Gestartet {started_by}. Im KI-Fenster zeigt /autostart, woher das kommt.")
        if sys.stdin.isatty():
            import time

            time.sleep(4)
        return SILENT_EXIT_CODE

    if args.einrichten:
        _first_setup(config)
        return 0

    # Spaetimport, damit --version/--einrichten ohne anthropic funktionieren.
    try:
        from .ui.cli import run_cli
        if app_mode:
            from .app.launcher import run_app
    except ImportError as exc:  # pragma: no cover
        message = f"Fehlende Abhaengigkeit: {exc}\nBitte 'pip install -r requirements.txt' ausfuehren."
        if app_mode:
            from .app.launcher import message_box

            message_box(message)
        print(message)
        return 1

    guard.acquire()
    try:
        if app_mode:
            return run_app(config, started_by=started_by if unexpected else None)
        return run_cli(config, started_by=started_by if unexpected else None)
    finally:
        guard.release()


def _first_setup(config) -> None:
    """Kopiert Beispielkonfiguration zu echten Dateien, falls noch nicht vorhanden."""
    import shutil
    from pathlib import Path

    config_dir = Path(config.project_root) / "config"
    pairs = [
        ("settings.example.toml", "settings.toml"),
    ]
    for example, target in pairs:
        src, dst = config_dir / example, config_dir / target
        if src.exists() and not dst.exists():
            shutil.copyfile(src, dst)
            print(f"Angelegt: {dst}")
        else:
            print(f"Uebersprungen (existiert schon oder Vorlage fehlt): {dst}")
    print("\nTrage jetzt deinen Schluessel in .env ein (siehe .env.example) und starte: python -m assistant")


if __name__ == "__main__":
    sys.exit(main())
