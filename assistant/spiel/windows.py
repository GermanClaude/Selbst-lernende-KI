"""Windows-Teile des Spielmodus (nur ctypes, keine Zusatzpakete).

  * SendInputTasten - Tastatur und Maus ueber SendInput mit Scan-Codes (so erkennen Spiele wie
    Unreal-Engine-Spiele die Eingaben am zuverlaessigsten), relative Mausbewegungen fuer die Kamera
  * vordergrund_info / client_rechteck - welches Fenster vorne ist und wo sein Inhalt liegt
  * dpi_bewusst - Pixel wirklich als Bildschirm-Pixel (wie pyautogui es auch macht)
  * WachHalter - PC und Bildschirm waehrend der Sitzung wach halten (SetThreadExecutionState)
  * NotAusTaste - weltweite Taste (RegisterHotKey) in einem eigenen Thread

Alles ist so gebaut, dass es ausserhalb von Windows nichts tut und eine klare Meldung liefert.
"""
from __future__ import annotations

import sys
import threading

NUR_WINDOWS = ("Der Spielmodus steuert Maus und Tastatur \u00fcber Windows (SendInput) \u2013 das geht nur "
               "unter Windows.")

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000
MAPVK_VK_TO_VSC = 0
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NOREPEAT = 0x4000

KNOEPFE = {
    "links": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "rechts": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "mitte": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def ist_windows() -> bool:
    return sys.platform == "win32"


def _strukturen():
    import ctypes
    from ctypes import wintypes as w

    ulong_ptr = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD), ("dwFlags", w.DWORD),
                    ("time", w.DWORD), ("dwExtraInfo", ulong_ptr)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD), ("time", w.DWORD),
                    ("dwExtraInfo", ulong_ptr)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", w.DWORD), ("u", _U)]

    return INPUT, MOUSEINPUT, KEYBDINPUT


class SendInputTasten:  # pragma: no cover - nur unter Windows
    """Echte Eingaben ueber SendInput. Alle Methoden arbeiten mit Bildschirm-Pixeln."""

    def __init__(self):
        if not ist_windows():
            raise OSError(NUR_WINDOWS)
        import ctypes
        from ctypes import wintypes as w

        self._ctypes = ctypes
        self._u = ctypes.WinDLL("user32", use_last_error=True)
        self._INPUT, self._MI, self._KI = _strukturen()
        self._u.SendInput.argtypes = [w.UINT, ctypes.c_void_p, ctypes.c_int]
        self._u.SendInput.restype = w.UINT
        self._u.MapVirtualKeyW.argtypes = [w.UINT, w.UINT]
        self._u.MapVirtualKeyW.restype = w.UINT
        self._u.GetSystemMetrics.argtypes = [ctypes.c_int]
        self._u.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
        self._u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

    def _senden(self, eingabe) -> None:
        ctypes = self._ctypes
        gesendet = self._u.SendInput(1, ctypes.byref(eingabe), ctypes.sizeof(self._INPUT))
        if gesendet != 1:
            fehler = ctypes.get_last_error()
            raise OSError(f"Windows hat die Eingabe nicht angenommen (Fehler {fehler}). L\u00e4uft das Spiel "
                          "als Administrator? Dann Nova ebenfalls als Administrator starten \u2013 oder das Spiel "
                          "normal starten.")

    def scancode(self, vk: int) -> int:
        """Scan-Code fuer einen virtuellen Tastencode im aktuellen Tastaturlayout (QWERTZ beachtet)."""
        return int(self._u.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)) & 0xFF

    def taste(self, vk: int, runter: bool, erweitert: bool = False) -> None:
        scan = self.scancode(vk)
        flags = (0 if runter else KEYEVENTF_KEYUP) | (KEYEVENTF_EXTENDEDKEY if erweitert else 0)
        eingabe = self._INPUT(type=INPUT_KEYBOARD)
        if scan:  # bevorzugt: Scan-Code (so lesen Spiele die Tastatur)
            eingabe.ki = self._KI(wVk=0, wScan=scan, dwFlags=flags | KEYEVENTF_SCANCODE, time=0, dwExtraInfo=0)
        else:     # Taste ohne Scan-Code im Layout: virtueller Code
            eingabe.ki = self._KI(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
        self._senden(eingabe)

    def _virtuell(self) -> tuple[int, int, int, int]:
        g = self._u.GetSystemMetrics
        return (g(SM_XVIRTUALSCREEN), g(SM_YVIRTUALSCREEN), max(1, g(SM_CXVIRTUALSCREEN)),
                max(1, g(SM_CYVIRTUALSCREEN)))

    def maus_absolut(self, x: int, y: int) -> None:
        links, oben, breite, hoehe = self._virtuell()
        nx = round((x - links) * 65535 / max(1, breite - 1))
        ny = round((y - oben) * 65535 / max(1, hoehe - 1))
        eingabe = self._INPUT(type=INPUT_MOUSE)
        eingabe.mi = self._MI(dx=nx, dy=ny, mouseData=0,
                              dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                              time=0, dwExtraInfo=0)
        self._senden(eingabe)
        self._u.SetCursorPos(int(x), int(y))  # exakt (Rundung der 0..65535-Skala)

    def maus_relativ(self, dx: int, dy: int) -> None:
        eingabe = self._INPUT(type=INPUT_MOUSE)
        eingabe.mi = self._MI(dx=int(dx), dy=int(dy), mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0)
        self._senden(eingabe)

    def maus_knopf(self, knopf: str, runter: bool) -> None:
        unten, oben = KNOEPFE[knopf]
        eingabe = self._INPUT(type=INPUT_MOUSE)
        eingabe.mi = self._MI(dx=0, dy=0, mouseData=0, dwFlags=unten if runter else oben, time=0, dwExtraInfo=0)
        self._senden(eingabe)

    def rad(self, rasten: int) -> None:
        eingabe = self._INPUT(type=INPUT_MOUSE)
        wert = int(rasten) * 120
        eingabe.mi = self._MI(dx=0, dy=0, mouseData=wert & 0xFFFFFFFF, dwFlags=MOUSEEVENTF_WHEEL, time=0,
                              dwExtraInfo=0)
        self._senden(eingabe)

    def cursor(self) -> tuple[int, int] | None:
        from ctypes import wintypes as w

        punkt = w.POINT()
        if not self._u.GetCursorPos(self._ctypes.byref(punkt)):
            return None
        return (int(punkt.x), int(punkt.y))


def dpi_bewusst() -> None:  # pragma: no cover - nur unter Windows
    """Wie pyautogui: der Prozess rechnet in echten Bildschirm-Pixeln (sonst passen Klicks und
    Bildschirmfotos bei 125/150 % Skalierung nicht zusammen)."""
    if not ist_windows():
        return
    try:
        import ctypes

        u = ctypes.WinDLL("user32")
        try:
            if u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
                return
        except Exception:  # noqa: BLE001 - aelteres Windows
            pass
        u.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def client_rechteck(hwnd) -> tuple[int, int, int, int] | None:  # pragma: no cover - nur unter Windows
    """Innenbereich des Fensters (ohne Rahmen und Titelleiste) in Bildschirm-Pixeln: (x, y, b, h)."""
    if not ist_windows() or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes as w

        u = ctypes.WinDLL("user32", use_last_error=True)
        u.GetClientRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
        u.ClientToScreen.argtypes = [w.HWND, ctypes.POINTER(w.POINT)]
        u.IsIconic.argtypes = [w.HWND]
        if u.IsIconic(hwnd):
            return None
        rect = w.RECT()
        if not u.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        punkt = w.POINT(0, 0)
        if not u.ClientToScreen(hwnd, ctypes.byref(punkt)):
            return None
        breite, hoehe = rect.right - rect.left, rect.bottom - rect.top
        if breite <= 0 or hoehe <= 0:
            return None
        return (int(punkt.x), int(punkt.y), int(breite), int(hoehe))
    except Exception:  # noqa: BLE001
        return None


def vordergrund_info() -> dict | None:  # pragma: no cover - nur unter Windows
    """{"hwnd", "pid", "exe", "titel", "rechteck"} des vorderen Fensters - rechteck = Innenbereich."""
    if not ist_windows():
        return None
    from ..sehen.windows import vordergrund

    info = vordergrund()
    if not info:
        return None
    innen = client_rechteck(info.get("hwnd"))
    if innen:
        info = dict(info, rechteck=innen)
    return info


class WachHalter:
    """Haelt PC und Bildschirm wach, solange die Sitzung laeuft (im selben Thread an- und abschalten).
    `aufruf` = SetThreadExecutionState (fuer Tests austauschbar)."""

    def __init__(self, aufruf=None):
        self.aufruf = aufruf
        self.an = False

    def _funktion(self):
        if self.aufruf is not None:
            return self.aufruf
        if not ist_windows():
            return None
        import ctypes

        k = ctypes.WinDLL("kernel32")
        k.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
        k.SetThreadExecutionState.restype = ctypes.c_uint32
        return k.SetThreadExecutionState

    def einschalten(self) -> bool:
        f = self._funktion()
        if f is None:
            return False
        try:
            self.an = bool(f(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED))
        except Exception:  # noqa: BLE001
            self.an = False
        return self.an

    def ausschalten(self) -> None:
        if not self.an:
            return
        f = self._funktion()
        self.an = False
        if f is None:
            return
        try:
            f(ES_CONTINUOUS)  # wieder wie vorher: Windows darf schlafen und sperren
        except Exception:  # noqa: BLE001
            pass


_VK_NAMEN = {"pause": 0x13, "rollen": 0x91, "scroll": 0x91, "einfg": 0x2D, "pos1": 0x24, "ende": 0x23,
             "entf": 0x2E}


def parse_taste(text: str) -> tuple[int, int] | None:
    """'Strg+Alt+Umschalt+P' -> (Modifier, VK) fuer RegisterHotKey (auch F1-F24, Pause, Pos1 ...)."""
    from ..sehen.einstellungen import parse_hotkey

    ergebnis = parse_hotkey(text)
    if ergebnis is not None:
        return ergebnis
    mods, vk = 0, None
    namen = {"strg": 0x2, "ctrl": 0x2, "alt": 0x1, "umschalt": 0x4, "shift": 0x4}
    for teil in [t.strip().lower() for t in str(text or "").split("+") if t.strip()]:
        if teil in namen:
            mods |= namen[teil]
        elif teil in _VK_NAMEN and vk is None:
            vk = _VK_NAMEN[teil]
        else:
            return None
    if vk is None or mods == 0:
        return None
    return mods, vk


class NotAusTaste(threading.Thread):  # pragma: no cover - nur unter Windows
    """Eigener Thread mit Nachrichtenschleife: ruft `gedrueckt()` bei der weltweiten Taste."""

    def __init__(self, taste: tuple[int, int], gedrueckt):
        super().__init__(name="nova-spiel-notaus", daemon=True)
        self.taste = taste
        self.gedrueckt = gedrueckt
        self.ok: bool | None = None
        self.thread_id = 0
        self.bereit = threading.Event()

    def run(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes as w

            u = ctypes.WinDLL("user32", use_last_error=True)
            k = ctypes.WinDLL("kernel32")
            u.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
            u.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]
            u.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
            mods, vk = self.taste
            self.ok = bool(u.RegisterHotKey(None, 7, mods | MOD_NOREPEAT, vk))
            self.thread_id = k.GetCurrentThreadId()
            self.bereit.set()
            msg = w.MSG()
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.gedrueckt()
                    except Exception:  # noqa: BLE001
                        pass
            if self.ok:
                u.UnregisterHotKey(None, 7)
        except Exception:  # noqa: BLE001
            self.ok = False
        finally:
            self.bereit.set()

    def stop(self) -> None:
        if not self.thread_id:
            return
        try:
            import ctypes

            ctypes.WinDLL("user32").PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        except Exception:  # noqa: BLE001
            pass


def fenster_liste(grenze: int = 300) -> list[dict]:  # pragma: no cover - nur unter Windows
    """Sichtbare Hauptfenster (fuer "welches Spiel laeuft?") - [{"hwnd", "pid", "exe", "titel", ...}]."""
    if not ist_windows():
        return []
    try:
        import ctypes
        from ctypes import wintypes as w

        from ..sehen.windows import fenster_info

        u = ctypes.WinDLL("user32", use_last_error=True)
        u.IsWindowVisible.argtypes = [w.HWND]
        u.GetWindow.argtypes = [w.HWND, w.UINT]
        u.GetWindow.restype = w.HWND
        gefunden: list[int] = []
        PROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

        def sammeln(hwnd, _lparam):
            if u.IsWindowVisible(hwnd) and not u.GetWindow(hwnd, 4):  # GW_OWNER: nur Hauptfenster
                gefunden.append(hwnd)
            return len(gefunden) < grenze

        u.EnumWindows(PROC(sammeln), 0)
        return [info for info in (fenster_info(h) for h in gefunden) if info and info.get("titel")]
    except Exception:  # noqa: BLE001
        return []
