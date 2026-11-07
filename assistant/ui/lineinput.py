"""Eingabezeile mit Sprechtaste F2.

  F2 gedrueckt HALTEN  -> sprechen, loslassen = fertig
  F2 kurz DRUECKEN     -> Mikrofon an ... F2 nochmal = fertig (Esc = abbrechen)

Der erkannte Text landet in der Eingabezeile - du kannst ihn noch bearbeiten und
schickst ihn mit Enter ab.

Technik: Die erste Taste einer Zeile wird direkt gelesen. Ist es nicht F2, geht sie
(samt allem, was schon im Tastaturpuffer wartet) zurueck an die normale Eingabe -
mit allen gewohnten Bearbeitungsfunktionen (Pfeiltasten, Verlauf, Einfuegen).
  Windows: msvcrt + WriteConsoleInputW (Tasten zurueck in die Konsole legen),
           GetAsyncKeyState erkennt, ob F2 noch gehalten wird.
  Linux/macOS: Terminal im cbreak-Modus + readline zum Vorbelegen der Zeile.
Klappt etwas davon nicht, faellt die Eingabe still auf das normale input() zurueck.
"""
from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Callable

from ..logging_setup import get_logger

logger = get_logger()

HOLD_SECONDS = 0.45        # so lange gehalten = "halten"-Modus, kuerzer = an/aus
_REPEAT_GAP = 0.35         # Linux: so lange keine Tastenwiederholung = F2 losgelassen
_IGNORE_AFTER_START = 0.5  # an/aus-Modus: Tastenwiederholungen des ersten Drucks ignorieren

VK_BACK, VK_TAB, VK_RETURN, VK_ESCAPE = 0x08, 0x09, 0x0D, 0x1B
VK_UP, VK_F2 = 0x26, 0x71

# msvcrt liefert Sondertasten als '\x00' oder '\xe0' + Code.
_WIN_SPECIAL = {
    "H": 0x26, "P": 0x28, "K": 0x25, "M": 0x27,  # Pfeile hoch/runter/links/rechts
    "G": 0x24, "O": 0x23, "R": 0x2D, "S": 0x2E,  # Pos1, Ende, Einfg, Entf
    "I": 0x21, "Q": 0x22,                        # Bild hoch/runter
    ";": 0x70, "<": 0x71, "=": 0x72, ">": 0x73, "?": 0x74,  # F1-F5
    "@": 0x75, "A": 0x76, "B": 0x77, "C": 0x78, "D": 0x79,  # F6-F10
    "\x85": 0x7A, "\x86": 0x7B,                             # F11, F12
}
_CHAR_VK = {"\r": VK_RETURN, "\n": VK_RETURN, "\b": VK_BACK, "\t": VK_TAB, "\x1b": VK_ESCAPE}
# Terminal-Sequenzen fuer F2 (xterm, rxvt/Linux-Konsole, ...) und Pfeil hoch.
_POSIX_F2 = {"\x1bOQ", "\x1b[12~", "\x1b[[B", "\x1b[1Q", "\x1b[Q"}
_POSIX_UP = {"\x1b[A", "\x1bOA"}


@dataclass(frozen=True)
class Key:
    char: str = ""  # eingegebenes Zeichen ("" bei Sondertasten)
    vk: int = 0     # Windows Virtual-Key-Code (0 = unbekannt)

    @property
    def is_f2(self) -> bool:
        return self.vk == VK_F2

    @property
    def is_escape(self) -> bool:
        return self.vk == VK_ESCAPE and self.char in ("", "\x1b")


def _split_prompt(prompt: str) -> tuple[str, str]:
    """'\\nDu: ' -> ('\\n', 'Du: ')"""
    core = prompt.lstrip("\n")
    return prompt[: len(prompt) - len(core)], core


# ---------------------------------------------------------------------------
#  Windows
# ---------------------------------------------------------------------------
def _win_structs():
    import ctypes

    class KEY_EVENT_RECORD(ctypes.Structure):  # noqa: N801 - Windows-Name
        _fields_ = [
            ("bKeyDown", ctypes.c_int32),
            ("wRepeatCount", ctypes.c_uint16),
            ("wVirtualKeyCode", ctypes.c_uint16),
            ("wVirtualScanCode", ctypes.c_uint16),
            ("UnicodeChar", ctypes.c_uint16),
            ("dwControlKeyState", ctypes.c_uint32),
        ]

    class _EVENT(ctypes.Union):
        _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("_groesse", ctypes.c_byte * 16)]

    class INPUT_RECORD(ctypes.Structure):  # noqa: N801
        _fields_ = [("EventType", ctypes.c_uint16), ("Event", _EVENT)]

    return KEY_EVENT_RECORD, INPUT_RECORD


class WindowsConsole:
    KEY_EVENT = 0x0001
    STD_INPUT_HANDLE = -10

    def __init__(self):
        import ctypes
        import msvcrt

        self._ctypes = ctypes
        self._msvcrt = msvcrt
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._u32 = ctypes.WinDLL("user32", use_last_error=True)
        self._k32.GetStdHandle.restype = ctypes.c_void_p
        self._k32.GetStdHandle.argtypes = [ctypes.c_int32]
        self._handle = self._k32.GetStdHandle(self.STD_INPUT_HANDLE)
        self._KEY, self._RECORD = _win_structs()
        self._k32.WriteConsoleInputW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(self._RECORD), ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)
        ]
        self._k32.WriteConsoleInputW.restype = ctypes.c_int32
        self._k32.FlushConsoleInputBuffer.argtypes = [ctypes.c_void_p]
        self._u32.GetAsyncKeyState.argtypes = [ctypes.c_int32]
        self._u32.GetAsyncKeyState.restype = ctypes.c_int16
        self._u32.VkKeyScanW.argtypes = [ctypes.c_uint16]
        self._u32.VkKeyScanW.restype = ctypes.c_int16
        self._u32.MapVirtualKeyW.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        self._u32.MapVirtualKeyW.restype = ctypes.c_uint32

    # -- Lesen --------------------------------------------------------------
    def raw(self):
        return _NullContext()

    def read_key(self, timeout: float | None = None) -> Key | None:
        # Immer pollen statt blockierend getwch(): so bleibt Strg+C sofort wirksam
        # (getwch liefert Strg+C nicht und wuerde bis zur naechsten Taste warten).
        end = None if timeout is None else time.monotonic() + timeout
        while not self._msvcrt.kbhit():
            if end is not None and time.monotonic() >= end:
                return None
            time.sleep(0.02)
        ch = self._msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return Key("", _WIN_SPECIAL.get(self._msvcrt.getwch(), 0))
        return Key(ch, self._vk_for_char(ch))

    def drain(self) -> list[Key]:
        keys = []
        while self._msvcrt.kbhit():
            key = self.read_key()
            if key is not None:
                keys.append(key)
        return keys

    def f2_down(self) -> bool | None:
        return bool(self._u32.GetAsyncKeyState(VK_F2) & 0x8000)

    def flush(self) -> None:
        self._k32.FlushConsoleInputBuffer(self._handle)

    def _vk_for_char(self, ch: str) -> int:
        if ch in _CHAR_VK:
            return _CHAR_VK[ch]
        if len(ch) == 1 and ord(ch) <= 0xFFFF:
            res = self._u32.VkKeyScanW(ord(ch))
            if res != -1:
                return res & 0xFF
        return 0

    # -- Zurueck in die Konsole legen -> normales input() -------------------
    def push(self, keys: list[Key]) -> None:
        records = []
        for key in keys:
            units = [0] if not key.char else _utf16_units(key.char)
            for unit in units:
                for down in (1, 0):
                    rec = self._RECORD()
                    rec.EventType = self.KEY_EVENT
                    ev = rec.Event.KeyEvent
                    ev.bKeyDown = down
                    ev.wRepeatCount = 1
                    ev.wVirtualKeyCode = key.vk
                    ev.wVirtualScanCode = self._u32.MapVirtualKeyW(key.vk, 0) if key.vk else 0
                    ev.UnicodeChar = unit
                    ev.dwControlKeyState = 0
                    records.append(rec)
        if not records:
            return
        array = (self._RECORD * len(records))(*records)
        written = self._ctypes.c_uint32(0)
        if not self._k32.WriteConsoleInputW(self._handle, array, len(records), self._ctypes.byref(written)):
            raise OSError(self._ctypes.get_last_error(), "WriteConsoleInputW fehlgeschlagen")

    def finish(self, prompt_core: str, reprint: bool, text: str, keys: list[Key], write) -> str:
        if reprint:
            write(prompt_core)
        self.push([Key(c, self._vk_for_char(c)) for c in text] + keys)
        return input("")


def _utf16_units(text: str) -> list[int]:
    data = text.encode("utf-16-le")
    return [int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2)]


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------------------
#  Linux / macOS
# ---------------------------------------------------------------------------
class PosixConsole:
    def __init__(self):
        import readline  # noqa: F401 - ohne readline kein Vorbelegen -> kein F2
        import termios  # noqa: F401

        self._fd = sys.stdin.fileno()
        self._saved = None

    def raw(self):
        console = self

        class _Raw:
            def __enter__(self_inner):
                import termios
                import tty

                console._saved = termios.tcgetattr(console._fd)
                tty.setcbreak(console._fd)
                return self_inner

            def __exit__(self_inner, *exc):
                import termios

                if console._saved is not None:
                    termios.tcsetattr(console._fd, termios.TCSADRAIN, console._saved)
                    console._saved = None
                return False

        return _Raw()

    def _readable(self, timeout: float | None) -> bool:
        import select

        ready, _, _ = select.select([self._fd], [], [], timeout)
        return bool(ready)

    def _read_char(self) -> str:
        data = os.read(self._fd, 1)
        while True:  # UTF-8-Mehrbytezeichen vollstaendig lesen
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                if len(data) >= 4 or not self._readable(0.05):
                    return data.decode("utf-8", "replace")
                data += os.read(self._fd, 1)

    def read_key(self, timeout: float | None = None) -> Key | None:
        if not self._readable(timeout):
            return None
        ch = self._read_char()
        if ch != "\x1b":
            return Key(ch, _CHAR_VK.get(ch, 0))
        seq = ch
        while self._readable(0.03) and len(seq) < 8:
            seq += self._read_char()
            if seq[-1].isalpha() or seq[-1] == "~":
                break
        if seq in _POSIX_F2:
            return Key("", VK_F2)
        if seq in _POSIX_UP:
            return Key("", VK_UP)
        if seq == "\x1b":
            return Key("\x1b", VK_ESCAPE)
        return Key("", 0)  # andere Sondertaste - ignorieren

    def drain(self) -> list[Key]:
        keys = []
        while self._readable(0):
            key = self.read_key(0)
            if key is not None:
                keys.append(key)
        return keys

    def f2_down(self) -> bool | None:
        return None  # Terminals melden kein Loslassen -> Tastenwiederholung auswerten

    def flush(self) -> None:
        import termios

        termios.tcflush(self._fd, termios.TCIFLUSH)

    def finish(self, prompt_core: str, reprint: bool, text: str, keys: list[Key], write) -> str:
        import readline

        if not reprint:
            write("\r\x1b[2K")  # selbst gedruckte Eingabeaufforderung entfernen, input() malt neu
        prefill = text
        for key in keys:
            if key.vk == VK_UP and not prefill:
                last = readline.get_current_history_length()
                prefill = readline.get_history_item(last) or "" if last else ""
            elif key.char in ("\r", "\n"):
                if not prefill:
                    write(prompt_core + "\n")
                    return ""
                break
            elif key.char in ("\x7f", "\b"):
                prefill = prefill[:-1]
            elif key.char and key.char.isprintable():
                prefill += key.char
        rl_prompt = re.sub(r"(\x1b\[[0-9;]*m)", "\001\\1\002", prompt_core)
        readline.set_startup_hook(lambda: readline.insert_text(prefill))
        try:
            return input(rl_prompt)
        finally:
            readline.set_startup_hook(None)


# ---------------------------------------------------------------------------
#  Gemeinsamer Ablauf
# ---------------------------------------------------------------------------
class VoiceLineReader:
    """input() mit Sprechtaste F2. 'capture' ist eine voice.VoiceCapture."""

    def __init__(
        self,
        capture,
        enabled: bool = True,
        console=None,
        write: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        interactive: bool | None = None,
    ):
        self.capture = capture
        self.enabled = enabled
        self._console = console
        self._write = write or _stdout_write
        self._clock = clock
        self._sleep = sleep
        self._interactive = interactive
        self._broken = False

    def _get_console(self):
        if self._console is None:
            self._console = WindowsConsole() if sys.platform == "win32" else PosixConsole()
        return self._console

    def _usable(self) -> bool:
        if not self.enabled or self._broken:
            return False
        interactive = self._interactive
        if interactive is None:
            interactive = sys.stdin.isatty() and sys.stdout.isatty()
        return interactive

    def read(self, prompt: str) -> str:
        if not self._usable():
            return input(prompt)
        try:
            console = self._get_console()
        except Exception as exc:  # noqa: BLE001 - z.B. kein readline
            logger.info("Sprechtaste nicht verfuegbar: %s", exc)
            self._broken = True
            return input(prompt)

        lead, core = _split_prompt(prompt)
        self._write(lead + core)
        spoken: str | None = None
        pending: list[Key] = []
        try:
            with console.raw():
                first = console.read_key()
                if first is not None and first.char == "\x03":
                    raise KeyboardInterrupt
                if first is not None and first.is_f2:
                    spoken = self._record(console)
                else:
                    pending = ([first] if first is not None else []) + console.drain()
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - lieber ohne F2 als gar keine Eingabe
            logger.warning("Sprechtaste abgeschaltet: %s", exc)
            self._broken = True
            return input("")
        if spoken is not None:
            return console.finish(core, True, spoken, [], self._write)
        pending = [k for k in pending if not k.is_f2]
        if any(k.char == "\x03" for k in pending):
            raise KeyboardInterrupt
        return console.finish(core, False, "", pending, self._write)

    # -- Aufnahme -----------------------------------------------------------
    def _status(self, text: str) -> None:
        self._write("\r" + text + "   ")

    def _record(self, console) -> str:
        """Nimmt auf (halten oder an/aus) und gibt den erkannten Text zurueck."""
        self._write("\n")
        problem = self.capture.problem()
        if problem:
            self._write(problem + "\n")
            return ""
        try:
            self.capture.start()
        except Exception as exc:  # noqa: BLE001
            self._write(f"{exc}\n")
            return ""
        try:
            cancelled = self._wait_until_done(console)
        except BaseException:
            self.capture.cancel()
            raise
        try:
            console.flush()
        except Exception:  # noqa: BLE001
            pass
        if cancelled:
            self.capture.cancel()
            self._status("(Aufnahme abgebrochen)")
            self._write("\n")
            return ""
        self._status("[Erkenne Sprache …]")
        try:
            text = self.capture.stop()
        except Exception as exc:  # noqa: BLE001
            self._status(f"{exc}")
            self._write("\n")
            return ""
        self._status("(Nichts verstanden - nochmal F2 oder tippen)" if not text else " " * 30)
        self._write("\n")
        return text

    def _elapsed(self, start: float) -> str:
        sec = int(self._clock() - start)
        return f"{sec // 60}:{sec % 60:02d}"

    def _wait_until_done(self, console) -> bool:
        """Wartet auf das Ende der Aufnahme. True = abgebrochen (Esc)."""
        start = self._clock()
        hold_msg = "[Mikrofon AN] Sprich jetzt - F2 loslassen = fertig"
        toggle_msg = "[Mikrofon AN] Sprich jetzt - F2 = fertig, Esc = abbrechen"

        down = console.f2_down()
        if down is not None:  # Windows: Tastenzustand direkt abfragen
            held = True
            while self._clock() - start < HOLD_SECONDS:
                if not console.f2_down():
                    held = False
                    break
                self._sleep(0.02)
            if held:
                while console.f2_down():
                    self._status(f"{hold_msg}  {self._elapsed(start)}")
                    self._sleep(0.05)
                return False
            console.flush()  # Tastenwiederholungen des kurzen Drucks verwerfen
        else:  # Linux/macOS: gehaltene Taste = Tastenwiederholung
            first_repeat = console.read_key(0.8)
            if first_repeat is not None and first_repeat.is_f2:
                last = self._clock()
                while self._clock() - last < _REPEAT_GAP:
                    self._status(f"{hold_msg}  {self._elapsed(start)}")
                    key = console.read_key(0.05)
                    if key is not None and key.is_f2:
                        last = self._clock()
                return False
            if first_repeat is not None and first_repeat.is_escape:
                return True

        # an/aus-Modus: bis F2 erneut gedrueckt wird
        while True:
            self._status(f"{toggle_msg}  {self._elapsed(start)}")
            key = console.read_key(0.25)
            if key is None:
                continue
            if key.is_escape:
                return True
            if key.is_f2 and self._clock() - start >= _IGNORE_AFTER_START:
                if down is None:
                    # Linux: folgen sofort weitere F2, wird die Taste gehalten
                    # (lange Wiederholverzoegerung) -> bis zum Loslassen weiter aufnehmen.
                    last = self._clock()
                    repeat = console.read_key(0.12)
                    if repeat is not None and repeat.is_f2:
                        while self._clock() - last < _REPEAT_GAP:
                            self._status(f"{hold_msg}  {self._elapsed(start)}")
                            key = console.read_key(0.05)
                            if key is not None and key.is_f2:
                                last = self._clock()
                        return False
                return False
            if key.char == "\x03":
                raise KeyboardInterrupt


def _stdout_write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
