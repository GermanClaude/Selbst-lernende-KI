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


def fehlende_pakete(plattform: str | None = None, importierbar=None) -> list[str]:
    """Welche Teile fuer Bildschirm-Sehen fehlen wirklich (auch in der KI.exe) - Namen fuer die Anzeige."""
    import sys

    from ..voice import _importable

    pruefe = importierbar or _importable

    def da(name: str) -> bool:
        try:
            return bool(pruefe(name))
        except Exception:  # noqa: BLE001
            return False

    fehlt = [name for name, modul in (("numpy", "numpy"), ("pillow", "PIL")) if not da(modul)]
    if (plattform or sys.platform) == "win32":
        if not (da("dxcam") or da("mss")):
            fehlt.append("dxcam/mss (Bildschirmaufnahme)")
        if not da("comtypes"):
            fehlt.append("comtypes (Passwortschutz - ohne ihn nur Fenstertitel)")
        if not da("winrt.windows.media.ocr"):
            fehlt.append("winrt-Windows.Media.Ocr (Texterkennung)")
    return fehlt
