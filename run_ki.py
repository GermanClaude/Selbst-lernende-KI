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


def main() -> int:
    # Projektpfad in sys.path aufnehmen (fuer den Start aus dem Quellordner).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        _ensure_runtime_dir()
        from assistant.__main__ import main as app_main

        code = app_main()
    except Exception:  # noqa: BLE001 - in der .exe sonst unsichtbar
        traceback.print_exc()
        code = 1
    # Die .exe schliesst ihr Fenster sofort - Fehler sonst nicht lesbar.
    if code and getattr(sys, "frozen", False):
        try:
            input("\nEnter druecken zum Schliessen...")
        except (EOFError, KeyboardInterrupt):
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
