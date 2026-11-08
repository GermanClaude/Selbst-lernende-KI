"""Live-Sehen: Nova schaut (nur wenn du es willst) auf deinen Bildschirm oder durch deine Webcam.

Aufbau:
  * auge.py        - schnelles "Auge" im eigenen Prozess (Windows): Aufnahme (dxcam/mss),
                     Aenderungserkennung, Fenster-Ereignisse, Texterkennung, Passwortschutz
  * differenz.py   - billige Aenderungserkennung (numpy)
  * quellen.py     - Bildschirm-Quellen und Kamera-Quellen (Webcam im App-Fenster; spaeter Handy)
  * ereignis.py    - Ereignisse bewerten, buendeln, Weckregel (Budget), Kurzzeitgedaechtnis
  * dienst.py      - SehDienst im Hauptprogramm: an/aus, Zustimmung, Weckpakete fuer das Gehirn
  * windows.py, uia.py, ocr.py - die Windows-Teile (ctypes, UI Automation, Windows-Texterkennung)
Alle Zusatzpakete (numpy, dxcam, mss, comtypes, winrt) werden erst bei Bedarf geladen.
"""
from __future__ import annotations

SEH_PAKETE = [
    "numpy", "mss", "pillow",
    'dxcam==0.3.0 ; sys_platform == "win32" and platform_machine == "AMD64"',
    'comtypes ; sys_platform == "win32"',
    'winrt-runtime ; sys_platform == "win32"',
    'winrt-Windows.Media.Ocr ; sys_platform == "win32"',
    'winrt-Windows.Globalization ; sys_platform == "win32"',
    'winrt-Windows.Graphics.Imaging ; sys_platform == "win32"',
    'winrt-Windows.Storage.Streams ; sys_platform == "win32"',
    'winrt-Windows.Foundation ; sys_platform == "win32"',
    'winrt-Windows.Foundation.Collections ; sys_platform == "win32"',
]


def fehlende_pakete() -> list[str]:
    """Welche Pakete fuer Bildschirm-Sehen fehlen (Namen fuer die Anzeige)."""
    import sys

    from ..voice import _importable

    fehlt = [name for name, modul in (("numpy", "numpy"), ("pillow", "PIL")) if not _importable(modul)]
    if sys.platform == "win32":
        if not (_importable("dxcam") or _importable("mss")):
            fehlt.append("dxcam/mss")
        if not _importable("comtypes"):
            fehlt.append("comtypes")
    return fehlt
