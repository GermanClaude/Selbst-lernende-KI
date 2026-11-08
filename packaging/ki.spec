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
    (str(project_root / "assistant" / "spiel" / "profile"), "assistant/spiel/profile"),  # Spielwissen (.md)
]

# Live-Mitschrift im Jarvis-Modus (Vosk): die DLL liegt im Paketordner.
extra_binaries = []
try:
    import vosk  # noqa: F401
    from PyInstaller.utils.hooks import collect_dynamic_libs

    extra_binaries += collect_dynamic_libs("vosk")
except Exception:  # noqa: BLE001 - ohne vosk: Jarvis-Modus ohne Live-Mitschrift
    pass

# Live-Sehen (Bildschirm, Texterkennung): nur, wenn die Pakete beim Bauen installiert sind.
# Die Pakete werden erst zur Laufzeit geladen - deshalb hier ausdruecklich. Kein OpenCV.
sehen_imports = []
try:
    from PyInstaller.utils.hooks import collect_submodules

    import numpy  # noqa: F401
    sehen_imports += ["numpy", "mss", "mss.windows"]
    try:
        import dxcam  # noqa: F401
        sehen_imports += collect_submodules("dxcam")
    except Exception:  # noqa: BLE001 - z.B. ARM-PC: dann mss
        pass
    try:
        import comtypes.client  # noqa: F401
        comtypes.client.GetModule("UIAutomationCore.dll")  # UIA-Huelle schon beim Bauen erzeugen
        sehen_imports += ["comtypes", "comtypes.client"] + collect_submodules("comtypes.gen")
    except Exception:  # noqa: BLE001
        pass
    # winrt bringt einen eigenen PyInstaller-Hook mit
    sehen_imports += ["winrt.windows.media.ocr", "winrt.windows.globalization", "winrt.windows.graphics.imaging",
                      "winrt.windows.storage.streams", "winrt.windows.foundation",
                      "winrt.windows.foundation.collections"]
except Exception:  # noqa: BLE001 - ohne numpy: Live-Sehen nur mit Webcam
    sehen_imports = []

# Handy als Kamera (aiortc/WebRTC, PyAV, cryptography, segno): nur, wenn beim Bauen installiert.
handy_imports, handy_binaries = [], []
try:
    from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

    import aiortc  # noqa: F401
    import av  # noqa: F401
    handy_imports += collect_submodules("aiortc") + collect_submodules("av")
    handy_binaries += collect_dynamic_libs("av")
    try:
        import pylibsrtp  # noqa: F401
        handy_binaries += collect_dynamic_libs("pylibsrtp")
        handy_imports += ["pylibsrtp"]
    except Exception:  # noqa: BLE001
        pass
except Exception:  # noqa: BLE001 - ohne aiortc: keine Handy-Kamera in dieser exe
    handy_imports, handy_binaries = [], []
for _modul in ("segno", "cryptography.hazmat.primitives.ciphers.aead"):
    try:
        __import__(_modul)
        handy_imports.append(_modul)
    except Exception:  # noqa: BLE001
        pass
extra_binaries += handy_binaries

a = Analysis(
    [str(project_root / "run_ki.py")],
    pathex=[str(project_root)],
    binaries=extra_binaries,
    datas=added_files,
    # Optionale Extras werden nur eingebunden, wenn sie installiert sind.
    # PIL: Bilder verkleinern/pruefen (nur bei Bedarf importiert, deshalb hier ausdruecklich).
    hiddenimports=["anthropic", "openai", "requests", "bs4", "webview", "PIL", "PIL.Image", "PIL.ImageOps",
                   "PIL.ImageGrab", "PIL.ImageDraw",
                   "assistant.spiel.profile.manor_lords"] + sehen_imports + handy_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["cv2"],  # OpenCV nie mitnehmen (dxcam braucht es mit processor_backend="numpy" nicht)
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_file = project_root / "packaging" / "ki.ico"
icon = str(icon_file) if icon_file.exists() else None

# Versionsnummer in die .exe schreiben (Eigenschaften -> Details -> Dateiversion)
sys.path.insert(0, str(project_root / "packaging"))
from versionsinfo import version_info  # noqa: E402

ki_version = version_info(project_root, "KI", "Nova - Selbst-lernende KI (Terminal)")
app_version = version_info(project_root, "KI-App", "Nova - Selbst-lernende KI (App)")

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
    version=ki_version,
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
    version=app_version,
)
