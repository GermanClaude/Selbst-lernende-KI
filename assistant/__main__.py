"""Einstiegspunkt: startet die KI.

Start:
    python -m assistant
oder nach Installation:
    ki
"""
from __future__ import annotations

import argparse
import sys

from .config import load_config
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
    args = parser.parse_args(argv)

    if args.version:
        from . import __version__

        print(f"Selbst-lernende-KI {__version__}")
        return 0

    setup_logging()
    config = load_config()

    if args.einrichten:
        _first_setup(config)
        return 0

    # Spaetimport, damit --version/--einrichten ohne anthropic funktionieren.
    try:
        from .ui.cli import run_cli
    except ImportError as exc:  # pragma: no cover
        print(f"Fehlende Abhaengigkeit: {exc}\nBitte 'pip install -r requirements.txt' ausfuehren.")
        return 1

    run_cli(config)
    return 0


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
