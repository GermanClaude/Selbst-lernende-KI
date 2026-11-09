"""Windows-Firewall fuer die Handy-Kamera freigeben - nur auf ausdruecklichen Klick, nie automatisch.

Hintergrund: Ohne Freigabe verwirft Windows die Pakete, die das Handy von sich aus an Nova schickt.
Das faellt besonders auf, wenn das Handy seine Adresse versteckt (Browser-Schutz) - dann kann Nova
nicht zuerst senden. Fragt Windows nie nach (oder wurde "Abbrechen" gewaehlt), fehlt die Regel.

Der Befehl ist fest (kein Text vom Nutzer, vom Handy oder aus dem Netz). Eingesetzt wird nur der
Pfad dieses Programms, in Anfuehrungszeichen - und nur, wenn er unauffaellig ist (absolut, .exe,
vorhanden, ohne Anfuehrungszeichen). Die Regel gilt nur fuer UDP, nur fuer dieses Programm, nur
eingehend und nur aus dem eigenen Netz (remoteip=localsubnet). Windows fragt per UAC nach.

    netsh advfirewall firewall add rule name="Nova Handy-Kamera" dir=in action=allow
          program="<Programm>" protocol=UDP profile=private,public remoteip=localsubnet enable=yes
"""
from __future__ import annotations

import logging
import os
import re
import sys

log = logging.getLogger(__name__)

REGEL_NAME = "Nova Handy-Kamera"
WARTEN_MS = 120_000          # so lange darf der Nutzer fuer die UAC-Abfrage brauchen
_FREIGEGEBEN: set[str] = set()   # in dieser Sitzung freigegebene Programme (fuer die Anzeige)


def ist_windows() -> bool:
    return os.name == "nt" and sys.platform == "win32"


def moeglich() -> bool:
    """Kann Nova die Freigabe anbieten? (Windows und ein passendes Programm)"""
    return ist_windows() and programm_pfad() is not None


def freigegeben() -> bool:
    pfad = programm_pfad() if ist_windows() else None
    return pfad is not None and pfad.lower() in _FREIGEGEBEN


def _prozess_pfad() -> str:
    """Pfad der wirklich laufenden .exe (bei einer venv nicht der Starter in Scripts\\)."""
    if ist_windows():
        try:
            import ctypes  # noqa: PLC0415

            puffer = ctypes.create_unicode_buffer(32768)
            laenge = ctypes.windll.kernel32.GetModuleFileNameW(None, puffer, len(puffer))
            if 0 < laenge < len(puffer):
                return puffer.value
        except Exception:  # noqa: BLE001
            pass
    return sys.executable or ""


def pfad_ok(pfad: str, eingefroren: bool) -> bool:
    """Nur ein absoluter, vorhandener .exe-Pfad ohne Anfuehrungszeichen/Steuerzeichen.

    Nicht eingefroren (Start mit Python): nur python.exe / pythonw.exe / python3.x.exe."""
    if not pfad or any(z in pfad for z in '"\r\n\t%') or any(ord(z) < 32 for z in pfad):
        return False
    if not (os.path.isabs(pfad) and pfad.lower().endswith(".exe") and os.path.isfile(pfad)):
        return False
    if eingefroren:
        return True
    return re.fullmatch(r"pythonw?(3(\.?\d{1,2})?)?\.exe", os.path.basename(pfad).lower()) is not None


def programm_pfad() -> str | None:
    pfad = _prozess_pfad()
    return pfad if pfad_ok(pfad, bool(getattr(sys, "frozen", False))) else None


def befehl_parameter(pfad: str) -> str:
    """Die Parameter fuer netsh.exe - fest bis auf den (geprueften) Programmpfad."""
    if '"' in pfad:
        raise ValueError("Ungueltiger Pfad")
    return (f'advfirewall firewall add rule name="{REGEL_NAME}" dir=in action=allow '
            f'program="{pfad}" protocol=UDP profile=private,public remoteip=localsubnet enable=yes')


def _netsh_pfad() -> str:
    """netsh.exe aus dem echten System-Ordner (nicht ueber PATH oder Umgebungsvariablen)."""
    import ctypes  # noqa: PLC0415

    puffer = ctypes.create_unicode_buffer(520)
    laenge = ctypes.windll.kernel32.GetSystemDirectoryW(puffer, len(puffer))
    ordner = puffer.value if 0 < laenge < len(puffer) else r"C:\Windows\System32"
    return os.path.join(ordner, "netsh.exe")


def _runas(programm: str, parameter: str) -> int | None:
    """Startet ``programm`` mit Administratorrechten (UAC-Abfrage), versteckt, und wartet.

    -> Rueckgabewert des Programms; -1 = Nutzer hat die UAC-Abfrage abgelehnt; None = unbekannt."""
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                    ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                    ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

    see_mask_nocloseprocess, see_mask_noasync, sw_hide = 0x40, 0x100, 0
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = see_mask_nocloseprocess | see_mask_noasync
    info.lpVerb = "runas"
    info.lpFile = programm
    info.lpParameters = parameter
    info.nShow = sw_hide
    shell32, kernel32 = ctypes.windll.shell32, ctypes.windll.kernel32
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        return -1 if kernel32.GetLastError() == 1223 else None  # 1223 = ERROR_CANCELLED (UAC "Nein")
    if not info.hProcess:
        return None
    try:
        kernel32.WaitForSingleObject(info.hProcess, WARTEN_MS)
        code = wintypes.DWORD()
        if kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code)) and code.value != 259:  # STILL_ACTIVE
            return int(code.value)
        return None
    finally:
        kernel32.CloseHandle(info.hProcess)


def freigeben() -> tuple[bool, str]:
    """Legt die Firewall-Regel an (fragt per UAC). -> (ok, Text fuer den Nutzer)."""
    if not ist_windows():
        return False, "Das geht nur unter Windows."
    pfad = programm_pfad()
    if pfad is None:
        return False, "Nova kann die Firewall hier nicht selbst freigeben (unbekanntes Programm)."
    try:
        ergebnis = _runas(_netsh_pfad(), befehl_parameter(pfad))
    except Exception as exc:  # noqa: BLE001
        log.info("Firewall-Freigabe ging nicht (%s)", type(exc).__name__)
        return False, "Die Firewall-Freigabe ging nicht. Bitte in Windows selbst erlauben."
    if ergebnis == -1:
        return False, "Abgebrochen \u2013 Windows hat nichts ge\u00e4ndert."
    if ergebnis not in (0, None):
        log.info("Firewall-Freigabe: netsh meldet %s", ergebnis)
        return False, "Windows hat die Freigabe abgelehnt. Bitte in Windows selbst erlauben."
    _FREIGEGEBEN.add(pfad.lower())
    log.info("Firewall-Regel '%s' angelegt", REGEL_NAME)
    return True, ("Firewall freigegeben. Jetzt am Handy auf \u201eNeu verbinden\u201c tippen "
                  "(bzw. hier \u201eNeu koppeln\u201c).")
