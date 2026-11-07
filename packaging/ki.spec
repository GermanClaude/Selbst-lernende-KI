# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller-Spezifikation fuer die Selbst-lernende-KI.
# Baut zwei Programme aus demselben Code:
#   KI.exe      - im Terminal (Konsolenfenster)
#   KI-App.exe  - als App in einem eigenen Programmfenster (ohne Konsole)
#
# Bauen (im Projektordner, venv aktiv, 'pip install pyinstaller'):
#     pyinstaller packaging/ki.spec
# Ergebnis liegt danach in: dist/KI(.exe) und dist/KI-App(.exe)

import sys
from pathlib import Path

block_cipher = None

# Projektordner = Ordner ueber dieser .spec-Datei. (Pfade in Analysis() wuerden
# sonst relativ zu packaging/ aufgeloest -> "run_ki.py not found".)
project_root = Path(SPECPATH).resolve().parent  # SPECPATH setzt PyInstaller

# Beispiel-Konfiguration mit ins Paket legen, damit die .exe beim ersten Start
# etwas zum Kopieren hat.
added_files = [
    (str(project_root / "config" / "settings.example.toml"), "config"),
    (str(project_root / "config" / "persona.md"), "config"),
    (str(project_root / "config" / "werte.md"), "config"),
    (str(project_root / ".env.example"), "."),
    (str(project_root / "assistant" / "app" / "static"), "assistant/app/static"),  # App-Oberflaeche
    (str(project_root / "assistant" / "umlaute.json"), "assistant"),  # schoene Texte in der App
]

a = Analysis(
    [str(project_root / "run_ki.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=added_files,
    # Optionale Extras werden nur eingebunden, wenn sie installiert sind.
    hiddenimports=["anthropic", "openai", "requests", "bs4", "webview"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_file = project_root / "packaging" / "ki.ico"
icon = str(icon_file) if icon_file.exists() else None

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
    icon=icon,
)

app_exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="KI-App",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,  # eigenes Programmfenster, keine Konsole
    disable_windowed_traceback=False,
    icon=icon,
)
