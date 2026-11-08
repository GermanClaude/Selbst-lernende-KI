"""Windows-Teile von Live-Sehen (nur ctypes, keine Zusatzpakete).

  * windows_build / kann_aus_aufnahme_ausschliessen - ab Windows 10 2004 (Build 19041) kann
    Nova ihr eigenes Fenster aus jeder Bildschirmaufnahme herausnehmen (WDA_EXCLUDEFROMCAPTURE).
    Aeltere Windows-Versionen zeigen das Fenster dann schwarz - dort lassen wir es.
  * eigene_fenster_schuetzen(an) - das tun (bzw. zuruecknehmen) fuer alle Fenster dieses Prozesses
  * fenster_info(hwnd) - Titel, Programm, Klasse, Rechteck des Fensters
  * dialog_text(hwnd) - Text klassischer Meldungsfenster (#32770) ohne Texterkennung
  * WinEventWaechter - meldet Vordergrund-Wechsel, Titel-Aenderungen, Dialoge, Warnungen und die
    weltweite Pause-Taste (RegisterHotKey) - ereignisgesteuert, praktisch ohne Rechenzeit.
Alles ist so gebaut, dass es ausserhalb von Windows nichts tut (und nie abstuerzt).
"""
from __future__ import annotations

import sys
import threading

WDA_NONE = 0x0
WDA_EXCLUDEFROMCAPTURE = 0x11
BUILD_AUSSCHLIESSEN = 19041  # Windows 10, Version 2004

EVENT_SYSTEM_ALERT = 0x0002
EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_SYSTEM_DIALOGSTART = 0x0010
EVENT_OBJECT_NAMECHANGE = 0x800C
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NOREPEAT = 0x4000
OBJID_WINDOW = 0


def windows_build(getwindowsversion=None, plattform: str | None = None) -> int | None:
    """Build-Nummer von Windows (z.B. 22631) - None ausserhalb von Windows."""
    if (plattform or sys.platform) != "win32":
        return None
    try:
        return int((getwindowsversion or sys.getwindowsversion)().build)
    except Exception:  # noqa: BLE001
        return None


def kann_aus_aufnahme_ausschliessen(build: int | None) -> bool:
    return build is not None and build >= BUILD_AUSSCHLIESSEN


def _user32():
    import ctypes
    from ctypes import wintypes as w

    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetWindowDisplayAffinity.argtypes = [w.HWND, w.DWORD]
    u.SetWindowDisplayAffinity.restype = w.BOOL
    u.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    u.GetWindowThreadProcessId.restype = w.DWORD
    u.IsWindowVisible.argtypes = [w.HWND]
    u.GetWindowTextLengthW.argtypes = [w.HWND]
    u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    u.GetForegroundWindow.restype = w.HWND
    u.GetAncestor.argtypes = [w.HWND, w.UINT]
    u.GetAncestor.restype = w.HWND
    return u


def eigene_fenster_schuetzen(an: bool, build: int | None = None, user32=None, pid: int | None = None) -> str:
    """Novas Fenster aus Bildschirmaufnahmen herausnehmen (an) bzw. wieder zeigen (aus).
    Gibt einen Hinweis zurueck ("" = alles gut)."""
    if sys.platform != "win32" and user32 is None:
        return ""
    build = windows_build() if build is None else build
    if not kann_aus_aufnahme_ausschliessen(build):
        return ("Hinweis: Dieses Windows ist \u00e4lter als Version 2004 \u2013 Novas eigenes Fenster kann "
                "nicht aus der Aufnahme genommen werden. Nova schaut deshalb nicht hin, solange ihr Fenster "
                "vorne ist.") if an else ""
    import ctypes
    import os
    from ctypes import wintypes as w

    u = user32 or _user32()
    pid = os.getpid() if pid is None else pid
    fenster: list[int] = []
    PROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

    def sammeln(hwnd, _lparam):
        eigner = w.DWORD(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(eigner))
        if eigner.value == pid and u.IsWindowVisible(hwnd):
            fenster.append(hwnd)
        return True

    try:
        u.EnumWindows(PROC(sammeln), 0)
        for hwnd in fenster:
            u.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE if an else WDA_NONE)
    except Exception:  # noqa: BLE001
        return ""
    return ""


def fenster_info(hwnd, user32=None) -> dict | None:
    """{"hwnd", "pid", "exe", "titel", "klasse", "rechteck": (x, y, b, h)} - None, wenn es nicht geht."""
    if not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes as w

        u = user32 or _user32()
        laenge = max(0, min(int(u.GetWindowTextLengthW(hwnd)), 1000))
        puffer = ctypes.create_unicode_buffer(laenge + 1)
        u.GetWindowTextW(hwnd, puffer, laenge + 1)
        klasse = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, klasse, 256)
        pid = w.DWORD(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = w.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rect))
        return {"hwnd": int(hwnd), "pid": int(pid.value), "exe": prozess_name(int(pid.value)),
                "titel": puffer.value, "klasse": klasse.value,
                "rechteck": (rect.left, rect.top, max(0, rect.right - rect.left), max(0, rect.bottom - rect.top))}
    except Exception:  # noqa: BLE001
        return None


def vordergrund(user32=None) -> dict | None:
    try:
        u = user32 or _user32()
        return fenster_info(u.GetForegroundWindow(), u)
    except Exception:  # noqa: BLE001
        return None


def prozess_name(pid: int) -> str:
    """'excel.exe' zu einer Prozessnummer ('' wenn unbekannt)."""
    if sys.platform != "win32" or not pid:
        return ""
    try:
        import ctypes
        from ctypes import wintypes as w

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        k.OpenProcess.restype = w.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        k.CloseHandle.argtypes = [w.HANDLE]
        handle = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            puffer = ctypes.create_unicode_buffer(1024)
            groesse = w.DWORD(1024)
            if not k.QueryFullProcessImageNameW(handle, 0, puffer, ctypes.byref(groesse)):
                return ""
            return puffer.value.replace("\\", "/").rsplit("/", 1)[-1].lower()
        finally:
            k.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return ""


def dialog_text(hwnd, user32=None, grenze: int = 600) -> str:
    """Texte der 'Static'-Felder eines klassischen Meldungsfensters (MessageBox)."""
    try:
        import ctypes
        from ctypes import wintypes as w

        u = user32 or _user32()
        texte: list[str] = []
        PROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

        def kind(h, _lparam):
            klasse = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(h, klasse, 64)
            if klasse.value.lower() == "static":
                laenge = max(0, min(int(u.GetWindowTextLengthW(h)), 2000))
                if laenge:
                    puffer = ctypes.create_unicode_buffer(laenge + 1)
                    u.GetWindowTextW(h, puffer, laenge + 1)
                    if puffer.value.strip():
                        texte.append(" ".join(puffer.value.split()))
            return sum(len(t) for t in texte) < grenze

        u.EnumChildWindows(hwnd, PROC(kind), 0)
        return " ".join(texte)[:grenze]
    except Exception:  # noqa: BLE001
        return ""


class WinEventWaechter(threading.Thread):
    """Eigener Thread mit Nachrichtenschleife: meldet ("vordergrund"|"titel"|"dialog"|"alarm", hwnd)
    und ("taste", None) fuer die Pause-Taste ueber melde(art, hwnd)."""

    def __init__(self, melde, hotkey: tuple[int, int] | None = None):
        super().__init__(name="nova-auge-fenster", daemon=True)
        self.melde = melde
        self.hotkey = hotkey
        self.thread_id = 0
        self.taste_ok: bool | None = None
        self.bereit = threading.Event()
        self.fehler = ""

    def run(self) -> None:  # pragma: no cover - nur unter Windows
        try:
            import ctypes
            from ctypes import wintypes as w

            u = ctypes.WinDLL("user32", use_last_error=True)
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            PROC = ctypes.WINFUNCTYPE(None, w.HANDLE, w.DWORD, w.HWND, w.LONG, w.LONG, w.DWORD, w.DWORD)
            u.SetWinEventHook.argtypes = [w.DWORD, w.DWORD, w.HMODULE, PROC, w.DWORD, w.DWORD, w.DWORD]
            u.SetWinEventHook.restype = w.HANDLE
            u.UnhookWinEvent.argtypes = [w.HANDLE]
            u.GetForegroundWindow.restype = w.HWND
            u.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
            u.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]
            u.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
            u.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
            u.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]

            namen = {EVENT_SYSTEM_FOREGROUND: "vordergrund", EVENT_SYSTEM_DIALOGSTART: "dialog",
                     EVENT_SYSTEM_ALERT: "alarm", EVENT_OBJECT_NAMECHANGE: "titel"}

            def rueckruf(_hook, ereignis, hwnd, id_object, _child, _thread, _zeit):
                try:
                    if ereignis == EVENT_OBJECT_NAMECHANGE:
                        if id_object != OBJID_WINDOW or hwnd != u.GetForegroundWindow():
                            return
                    self.melde(namen.get(ereignis, "?"), hwnd)
                except Exception:  # noqa: BLE001 - nie in Windows hinein werfen
                    pass

            self._proc = PROC(rueckruf)  # Verweis behalten, sonst raeumt Python ihn weg
            flags = WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS
            hooks = [u.SetWinEventHook(e, e, None, self._proc, 0, 0, flags) for e in namen]
            if self.hotkey:
                mods, vk = self.hotkey
                self.taste_ok = bool(u.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk))
            self.thread_id = k.GetCurrentThreadId()
            self.bereit.set()
            msg = w.MSG()
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    self.melde("taste", None)
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
            for hook in hooks:
                if hook:
                    u.UnhookWinEvent(hook)
            if self.taste_ok:
                u.UnregisterHotKey(None, 1)
        except Exception as exc:  # noqa: BLE001
            self.fehler = f"{type(exc).__name__}: {exc}"
        finally:
            self.bereit.set()

    def stop(self) -> None:  # pragma: no cover - nur unter Windows
        if not self.thread_id:
            return
        try:
            import ctypes

            ctypes.WinDLL("user32").PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        except Exception:  # noqa: BLE001
            pass
