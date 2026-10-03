#!/usr/bin/env python3
"""Start-Skript fuer die Selbst-lernende-KI.

Dieses Skript ist der Einstiegspunkt - auch fuer die .exe. Es sorgt dafuer, dass
beim ersten Start (etwa aus einer gepackten .exe heraus) eine beschreibbare
Konfiguration neben der Programmdatei angelegt wird.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_runtime_dir() -> None:
    """Legt bei Bedarf config/ aus den Beispielen neben der .exe an."""
    if not getattr(sys, "frozen", False):
        return  # Nur im gepackten Zustand noetig.
    exe_dir = Path(sys.executable).resolve().parent
    bundle = Path(getattr(sys, "_MEIPASS", exe_dir))
    config_dir = exe_dir / "config"
    config_dir.mkdir(exist_ok=True)
    import shutil

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
    # Arbeitsverzeichnis auf den exe-Ordner setzen, damit relative Pfade passen.
    import os

    os.chdir(exe_dir)


def main() -> int:
    _ensure_runtime_dir()
    # Projektpfad in sys.path aufnehmen (fuer den Start aus dem Quellordner).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from assistant.__main__ import main as app_main

    return app_main()


if __name__ == "__main__":
    sys.exit(main())
