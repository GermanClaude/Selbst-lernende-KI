# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller-Spezifikation fuer die Selbst-lernende-KI.
# Baut eine einzelne ausfuehrbare Datei (unter Windows: KI.exe).
#
# Bauen (im Projektordner, venv aktiv, 'pip install pyinstaller'):
#     pyinstaller packaging/ki.spec
# Ergebnis liegt danach in: dist/KI(.exe)

import sys
from pathlib import Path

block_cipher = None

# Beispiel-Konfiguration mit ins Paket legen, damit die .exe beim ersten Start
# etwas zum Kopieren hat.
project_root = Path.cwd()
added_files = [
    (str(project_root / "config" / "settings.example.toml"), "config"),
    (str(project_root / "config" / "persona.md"), "config"),
    (str(project_root / "config" / "werte.md"), "config"),
    (str(project_root / ".env.example"), "."),
]

a = Analysis(
    ["run_ki.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=added_files,
    # Optionale Extras werden nur eingebunden, wenn sie installiert sind.
    hiddenimports=["anthropic", "openai", "requests", "bs4"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="KI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True,  # Konsolenfenster (die KI redet dort mit dir)
    disable_windowed_traceback=False,
    icon=None,
)
