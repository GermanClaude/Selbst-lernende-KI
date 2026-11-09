"""Windows-Firewall fuer die Handy-Kamera freigeben - nur auf ausdruecklichen Klick, nie automatisch.

Hintergrund: Ohne Freigabe verwirft Windows die Pakete, die das Handy von sich aus an Nova schickt.
Das faellt besonders auf, wenn das Handy seine Adresse versteckt (Browser-Schutz) - dann kann Nova
nicht zuerst senden. Fragt Windows nie nach, fehlt eine Erlaubnis-Regel. Wurde die Windows-Abfrage
mit "Abbrechen" geschlossen (oder nur "Privat" erlaubt), legt Windows sogar SPERR-Regeln fuer das
Programm an - und eine Sperre gilt immer vor einer Erlaubnis. Deshalb loescht Nova im selben Schritt
erst alle eingehenden Regeln dieses Programms (auch eigene doppelte) und legt dann die eine Regel an.

Nur fuer die fertige App (KI.exe / KI-App.exe). Wer Nova mit Python startet, bekommt eine Anleitung
(anleitung()) - sonst stuende die Firewall fuer jedes Python-Skript offen.

Ein einziger Schritt mit Administratorrechten (eine UAC-Abfrage): cmd.exe aus dem System-Ordner mit
festem Befehl. Eingesetzt wird nur der Pfad dieses Programms, in Anfuehrungszeichen - und nur, wenn
er unauffaellig ist (absolut, vorhanden, KI*.exe, ohne Anfuehrungszeichen, %, ! oder Steuerzeichen).

    netsh advfirewall firewall delete rule name=all dir=in program="<Programm>"
    netsh advfirewall firewall add rule name="Nova Handy-Kamera" dir=in action=allow
          program="<Programm>" protocol=UDP profile=private,public remoteip=localsubnet enable=yes

Die Regel gilt nur eingehend, nur fuer UDP, nur fuer dieses Programm und nur aus dem eigenen
Netz (remoteip=localsubnet) - auch im Profil "Oeffentlich", weil viele Heim-WLANs von Windows
als "Oeffentlich" eingestuft werden. Danach prueft Nova ohne Adminrechte, ob die Regel da ist
(nur Rueckgabewert von "netsh ... show rule", kein uebersetzter Text).
"""
from __future__ import annotations

import logging
import ntpath
import os
import re
import subprocess
import sys

log = logging.getLogger(__name__)

REGEL_NAME = "Nova Handy-Kamera"
WARTEN_MS = 120_000          # so lange darf der Nutzer fuer die UAC-Abfrage brauchen
_FREIGEGEBEN: set[str] = set()   # in dieser Sitzung freigegebene Programme (fuer die Anzeige)
_EXE_NAMEN = re.compile(r"ki(-app)?( \(\d{1,3}\))?\.exe")   # auch "KI (1).exe" aus dem Download-Ordner

ANLEITUNG = ("Windows-Firewall selbst freigeben: Start \u2192 \u201eWindows-Sicherheit\u201c \u2192 "
             "\u201eFirewall- & Netzwerkschutz\u201c \u2192 \u201eZugriff von App durch Firewall zulassen\u201c \u2192 "
             "\u201eEinstellungen \u00e4ndern\u201c \u2192 bei \u201ePython\u201c ein H\u00e4kchen bei \u201ePrivat\u201c "
             "setzen (und das WLAN in den Windows-Einstellungen auf \u201ePrivates Netzwerk\u201c stellen).")


def ist_windows() -> bool:
    return os.name == "nt" and sys.platform == "win32"


def eingefroren() -> bool:
    return bool(getattr(sys, "frozen", False))


def moeglich() -> bool:
    """Kann Nova die Freigabe per Klick anbieten? Nur Windows und nur die fertige App."""
    return ist_windows() and programm_pfad() is not None


def anleitung() -> str | None:
    """Text-Tipp statt Knopf: unter Windows, wenn Nova mit Python laeuft (nicht als KI.exe)."""
    return ANLEITUNG if ist_windows() and not eingefroren() else None


def freigegeben() -> bool:
    pfad = programm_pfad() if ist_windows() else None
    return pfad is not None and pfad.lower() in _FREIGEGEBEN


def _prozess_pfad() -> str:
    """Pfad der wirklich laufenden .exe."""
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


def pfad_ok(pfad: str) -> bool:
    """Nur ein absoluter, vorhandener Pfad auf KI.exe/KI-App.exe ohne Zeichen, die cmd.exe auswertet
    (Anfuehrungszeichen, %, !) und ohne Steuerzeichen. & ( ) ^ sind in Anfuehrungszeichen harmlos."""
    if not pfad_ok_text(pfad):
        return False
    if not (os.path.isabs(pfad) and os.path.isfile(pfad)):
        return False
    return _EXE_NAMEN.fullmatch(os.path.basename(pfad).lower()) is not None


def pfad_ok_text(pfad: str) -> bool:
    """Keine Zeichen, die cmd.exe auch in Anfuehrungszeichen auswertet, keine Steuerzeichen."""
    return bool(pfad) and not any(z in pfad for z in '"%!') and not any(ord(z) < 32 for z in pfad)


def programm_pfad() -> str | None:
    if not eingefroren():
        return None
    pfad = _prozess_pfad()
    return pfad if pfad_ok(pfad) else None


def _system_ordner() -> str:
    """Der echte System-Ordner (nicht ueber PATH oder Umgebungsvariablen)."""
    import ctypes  # noqa: PLC0415

    puffer = ctypes.create_unicode_buffer(520)
    laenge = ctypes.windll.kernel32.GetSystemDirectoryW(puffer, len(puffer))
    return puffer.value if 0 < laenge < len(puffer) else r"C:\Windows\System32"


def befehl(system: str, pfad: str) -> tuple[str, str]:
    """-> (cmd.exe, Parameter): erst alle eingehenden Regeln des Programms loeschen (auch Sperren,
    die Windows nach "Abbrechen" anlegt), dann die eine Erlaubnis-Regel. Fest bis auf den Pfad."""
    if not pfad_ok_text(pfad) or not pfad_ok_text(system):
        raise ValueError("Ungueltiger Pfad")
    netsh = ntpath.join(system, "netsh.exe")
    loeschen = f'"{netsh}" advfirewall firewall delete rule name=all dir=in program="{pfad}"'
    anlegen = (f'"{netsh}" advfirewall firewall add rule name="{REGEL_NAME}" dir=in action=allow '
               f'program="{pfad}" protocol=UDP profile=private,public remoteip=localsubnet enable=yes')
    # /d: keine AutoRun-Befehle, /v:off: kein !-Ersetzen, /s /c "...": aeussere Anfuehrungszeichen weg,
    # Rest woertlich. "&": das Anlegen laeuft auch, wenn es nichts zu loeschen gab; Rueckgabe = Anlegen.
    return ntpath.join(system, "cmd.exe"), f'/d /v:off /s /c "{loeschen} & {anlegen}"'


def _fenster() -> int | None:
    """Das Nova-Fenster als Eltern der UAC-Abfrage (dann erscheint sie davor, nicht dahinter).

    Der Klick kam gerade aus dem Fenster -> es ist im Vordergrund. Nur nehmen, wenn es zu Nova gehoert."""
    try:
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415

        user32, kernel32 = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32")
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        hwnd = user32.GetForegroundWindow()
        prozess = wintypes.DWORD()
        if hwnd and user32.GetWindowThreadProcessId(hwnd, ctypes.byref(prozess)) \
                and prozess.value == kernel32.GetCurrentProcessId():
            return int(hwnd)
    except Exception:  # noqa: BLE001
        pass
    return None


def _runas(programm: str, parameter: str, hwnd: int | None = None) -> int | None:
    """Startet ``programm`` mit Administratorrechten (UAC-Abfrage), versteckt, und wartet.

    -> Rueckgabewert des Programms; -1 = Nutzer hat die UAC-Abfrage abgelehnt; None = unklar."""
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
    info.hwnd = hwnd
    info.lpVerb = "runas"
    info.lpFile = programm
    info.lpParameters = parameter
    info.nShow = sw_hide
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        fehler = ctypes.get_last_error()
        log.info("Firewall-Freigabe: ShellExecuteEx-Fehler %s", fehler)
        return -1 if fehler == 1223 else None  # 1223 = ERROR_CANCELLED (UAC "Nein")
    if not info.hProcess:
        return None
    try:
        if kernel32.WaitForSingleObject(info.hProcess, WARTEN_MS) != 0:  # 0 = WAIT_OBJECT_0 (beendet)
            return None
        code = wintypes.DWORD()
        if kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code)) and code.value != 259:  # STILL_ACTIVE
            return int(code.value)
        return None
    finally:
        kernel32.CloseHandle(info.hProcess)


def regel_vorhanden(system: str | None = None) -> bool | None:
    """Gibt es die Regel? Ohne Adminrechte, nur am Rueckgabewert (0 = gefunden). None = unklar."""
    try:
        netsh = ntpath.join(system or _system_ordner(), "netsh.exe")
        ergebnis = subprocess.run(f'"{netsh}" advfirewall firewall show rule name="{REGEL_NAME}"',
                                  capture_output=True, timeout=20,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:  # noqa: BLE001
        log.info("Firewall-Regel nicht pruefbar (%s)", type(exc).__name__)
        return None
    return ergebnis.returncode == 0


def freigeben() -> tuple[bool, str]:
    """Raeumt alte Regeln weg und legt die Firewall-Regel an (eine UAC-Abfrage). -> (ok, Text)."""
    if not ist_windows():
        return False, "Das geht nur unter Windows."
    pfad = programm_pfad()
    if pfad is None:
        return False, ANLEITUNG if not eingefroren() else \
            "Nova kann die Firewall hier nicht selbst freigeben (unbekannter Programmname)."
    try:
        system = _system_ordner()
        programm, parameter = befehl(system, pfad)
        ergebnis = _runas(programm, parameter, _fenster())
    except Exception as exc:  # noqa: BLE001
        log.info("Firewall-Freigabe ging nicht (%s)", type(exc).__name__)
        return False, "Die Firewall-Freigabe ging nicht. Bitte in Windows selbst erlauben."
    if ergebnis == -1:
        return False, "Abgebrochen \u2013 Windows hat nichts ge\u00e4ndert."
    if ergebnis is None:
        return False, "Unklar, ob es geklappt hat \u2013 bitte noch einmal versuchen."
    if ergebnis != 0:
        log.info("Firewall-Freigabe: netsh meldet %s", ergebnis)
        return False, "Windows hat die Freigabe abgelehnt. Bitte in Windows selbst erlauben."
    if regel_vorhanden(system) is False:
        log.info("Firewall-Freigabe: Regel danach nicht gefunden")
        return False, "Unklar, ob es geklappt hat \u2013 bitte noch einmal versuchen."
    _FREIGEGEBEN.add(pfad.lower())
    log.info("Firewall-Regel '%s' angelegt (alte Regeln des Programms entfernt)", REGEL_NAME)
    return True, ("Firewall freigegeben. Jetzt am Handy auf \u201eNeu verbinden\u201c tippen "
                  "(bzw. hier \u201eNeu koppeln\u201c).")
