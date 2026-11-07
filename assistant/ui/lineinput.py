"""Eingabezeile mit Sprechtaste F2.

  F2 gedrueckt HALTEN  -> sprechen, loslassen = fertig
  F2 kurz DRUECKEN     -> Mikrofon an ... F2 nochmal = fertig (Esc = abbrechen)

F2 wirkt bei leerer Eingabezeile. Der erkannte Text landet in der Eingabezeile - du
kannst ihn noch bearbeiten und schickst ihn mit Enter ab.

Technik:
  Windows: Die Eingabe wird nur ANGESCHAUT (PeekConsoleInputW). Ist die erste Taste
           F2, wird genau dieser Tastendruck entnommen und aufgenommen; alles andere
           bleibt unveraendert im Konsolenpuffer und das normale input() liest es -
           mit allen gewohnten Funktionen (Pfeiltasten, Verlauf, Einfuegen, Umlaute,
           Emojis). Der erkannte Text wird per WriteConsoleInputW "eingetippt".
           GetAsyncKeyState erkennt, ob F2 noch gehalten wird.
  Linux/macOS: Terminal im cbreak-Modus + readline zum Vorbelegen der Zeile.
Klappt etwas davon nicht, faellt die Eingabe still auf das normale input() zurueck.
"""
from __future__ import annotations

import os
import re
import sys
import threading
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


_SGR = re.compile(r"\x1b\[[0-9;]*m")


def _split_prompt(prompt: str) -> tuple[str, str]:
    """'\\nDu: ' -> ('\\n', 'Du: ') - auch wenn Farbcodes davor stehen."""
    plain_start = 0
    while True:
        match = _SGR.match(prompt, plain_start)
        if not match:
            break
        plain_start = match.end()
    newlines = len(prompt[plain_start:]) - len(prompt[plain_start:].lstrip("\n"))
    lead = prompt[plain_start : plain_start + newlines]
    return lead, prompt[:plain_start] + prompt[plain_start + newlines :]


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


def _utf16_units(text: str) -> list[int]:
    # surrogatepass: auch einzelne Haelften eines Emojis verarbeiten, nie abstuerzen
    data = text.encode("utf-16-le", "surrogatepass")
    return [int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2)]


_MODIFIERS = 0x001F  # Alt (rechts/links), Strg (rechts/links), Umschalt
# Tasten ohne Zeichen, die nur "nebenbei" gedrueckt werden (Alt+Tab, Strg+C zum
# Kopieren, Win, Feststelltaste): zaehlen nicht als erste Taste der Zeile.
_MODIFIER_VKS = {0x10, 0x11, 0x12, 0x13, 0x14, 0x5B, 0x5C, 0x90, 0x91, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}


class WindowsConsole:
    KEY_EVENT = 0x0001
    STD_INPUT_HANDLE = -10

    def __init__(self):
        import ctypes

        self._ctypes = ctypes
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._u32 = ctypes.WinDLL("user32", use_last_error=True)
        self._KEY, self._RECORD = _win_structs()
        k32, u32, rec_ptr, dword_ptr = self._k32, self._u32, ctypes.POINTER(self._RECORD), ctypes.POINTER(ctypes.c_uint32)
        k32.GetStdHandle.restype = ctypes.c_void_p
        k32.GetStdHandle.argtypes = [ctypes.c_int32]
        for name in ("PeekConsoleInputW", "ReadConsoleInputW", "WriteConsoleInputW"):
            fn = getattr(k32, name)
            fn.argtypes = [ctypes.c_void_p, rec_ptr, ctypes.c_uint32, dword_ptr]
            fn.restype = ctypes.c_int32
        k32.GetNumberOfConsoleInputEvents.argtypes = [ctypes.c_void_p, dword_ptr]
        k32.GetNumberOfConsoleInputEvents.restype = ctypes.c_int32
        k32.FlushConsoleInputBuffer.argtypes = [ctypes.c_void_p]
        u32.GetAsyncKeyState.argtypes = [ctypes.c_int32]
        u32.GetAsyncKeyState.restype = ctypes.c_int16
        u32.VkKeyScanW.argtypes = [ctypes.c_uint16]
        u32.VkKeyScanW.restype = ctypes.c_int16
        u32.MapVirtualKeyW.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        u32.MapVirtualKeyW.restype = ctypes.c_uint32
        self._handle = k32.GetStdHandle(self.STD_INPUT_HANDLE)

    # -- Rohzugriff auf den Konsolenpuffer ------------------------------------
    def _pending(self) -> int:
        count = self._ctypes.c_uint32(0)
        if not self._k32.GetNumberOfConsoleInputEvents(self._handle, self._ctypes.byref(count)):
            raise OSError(self._ctypes.get_last_error(), "GetNumberOfConsoleInputEvents")
        return count.value

    def _records(self, count: int, remove: bool) -> list:
        if count <= 0:
            return []
        buf = (self._RECORD * count)()
        got = self._ctypes.c_uint32(0)
        fn = self._k32.ReadConsoleInputW if remove else self._k32.PeekConsoleInputW
        if not fn(self._handle, buf, count, self._ctypes.byref(got)):
            raise OSError(self._ctypes.get_last_error(), "Peek/ReadConsoleInputW")
        return list(buf[: got.value])

    def _write_records(self, records: list) -> None:
        if not records:
            return
        buf = (self._RECORD * len(records))(*records)
        written = self._ctypes.c_uint32(0)
        if not self._k32.WriteConsoleInputW(self._handle, buf, len(records), self._ctypes.byref(written)):
            raise OSError(self._ctypes.get_last_error(), "WriteConsoleInputW")

    def _key_of(self, rec) -> Key | None:
        """Key fuer einen Tastendruck (key down), sonst None."""
        if rec.EventType != self.KEY_EVENT or not rec.Event.KeyEvent.bKeyDown:
            return None
        ev = rec.Event.KeyEvent
        vk = ev.wVirtualKeyCode
        if vk == VK_F2 and ev.dwControlKeyState & _MODIFIERS:
            vk = 0  # Umschalt/Strg/Alt+F2 nicht als Sprechtaste
        return Key(chr(ev.UnicodeChar) if ev.UnicodeChar else "", vk)

    # -- Schnittstelle fuer VoiceLineReader -----------------------------------
    def raw(self):
        return _NullContext()

    def wait_first_key(self) -> Key:
        """Wartet auf die erste Taste. F2 wird entnommen, alles andere bleibt liegen."""
        while True:
            pending = self._pending()
            if pending:
                records = self._records(min(pending, 64), remove=False)
                skip = 0
                for rec in records:
                    key = self._key_of(rec)
                    if key is None or (key.vk in _MODIFIER_VKS and not key.char):
                        skip += 1  # Loslassen, Maus, Fokus, Alt/Strg/Win: bedeutungslos
                        continue
                    if key.is_f2:
                        self._records(skip + 1, remove=True)
                    elif skip:
                        self._records(skip, remove=True)
                    return key
                if skip:
                    self._records(skip, remove=True)
                    continue
            time.sleep(0.02)  # pollen statt blockieren: Strg+C bleibt sofort wirksam

    def read_key(self, timeout: float | None = None) -> Key | None:
        """Naechsten Tastendruck entnehmen (waehrend der Aufnahme)."""
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            while self._pending():
                for rec in self._records(1, remove=True):
                    key = self._key_of(rec)
                    if key is not None:
                        return key
            if end is not None and time.monotonic() >= end:
                return None
            time.sleep(0.02)

    def f2_down(self) -> bool | None:
        return bool(self._u32.GetAsyncKeyState(VK_F2) & 0x8000)

    def flush(self) -> None:
        self._k32.FlushConsoleInputBuffer(self._handle)

    def _text_records(self, text: str) -> list:
        records = []
        for unit in _utf16_units(text):
            ch = chr(unit)
            vk = _CHAR_VK.get(ch, 0)
            if not vk and not 0xD800 <= unit <= 0xDFFF:
                res = self._u32.VkKeyScanW(unit)
                vk = res & 0xFF if res != -1 else 0
            for down in (1, 0):
                rec = self._RECORD()
                rec.EventType = self.KEY_EVENT
                ev = rec.Event.KeyEvent
                ev.bKeyDown = down
                ev.wRepeatCount = 1
                ev.wVirtualKeyCode = vk
                ev.wVirtualScanCode = self._u32.MapVirtualKeyW(vk, 0) if vk else 0
                ev.UnicodeChar = unit
                records.append(rec)
        return records

    def finish(self, prompt_core: str, reprint: bool, text: str, write) -> str:
        if reprint:
            write(prompt_core)
        if text:
            # Was waehrend der Erkennung getippt wurde, kommt HINTER den Text (Enter =
            # gleich abschicken). F2-Druecke werden verworfen - in der normalen Eingabe
            # oeffnet F2 sonst das Konsolen-Fenster "Zeichen zum Kopieren eingeben".
            later = [r for r in self._records(self._pending(), remove=True) if not self._is_f2_record(r)]
            self._write_records(self._text_records(text) + later)
        return input("")

    def _is_f2_record(self, rec) -> bool:
        return rec.EventType == self.KEY_EVENT and rec.Event.KeyEvent.wVirtualKeyCode == VK_F2


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
        self._typed: list[Key] = []

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

    def wait_first_key(self) -> Key:
        key = self.read_key()
        while key is None:
            key = self.read_key()
        if not key.is_f2:
            # Terminals erlauben kein "Zuruecklegen" - Getipptes merken und in
            # finish() per readline vorbelegen (inkl. allem, was schon wartet).
            self._typed = [key]
            while self._readable(0):
                more = self.read_key(0)
                if more is not None:
                    self._typed.append(more)
        return key

    def f2_down(self) -> bool | None:
        return None  # Terminals melden kein Loslassen -> Tastenwiederholung auswerten

    def flush(self) -> None:
        import termios

        termios.tcflush(self._fd, termios.TCIFLUSH)

    def finish(self, prompt_core: str, reprint: bool, text: str, write) -> str:
        import readline

        keys, self._typed = ([] if text else self._typed), []
        if not reprint:
            write("\r\x1b[2K")  # selbst gedruckte Eingabeaufforderung entfernen, input() malt neu
        prefill = text
        for key in keys:
            if key.is_f2:
                continue
            if key.vk == VK_UP and not prefill:
                last = readline.get_current_history_length()
                prefill = (readline.get_history_item(last) or "") if last else ""
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
        self._status_len = 0

    def _get_console(self):
        if self._console is None:
            self._console = WindowsConsole() if sys.platform == "win32" else PosixConsole()
        return self._console

    def _usable(self) -> bool:
        if not self.enabled or self._broken:
            return False
        interactive = self._interactive
        if interactive is None:
            interactive = bool(sys.stdin and sys.stdout) and sys.stdin.isatty() and sys.stdout.isatty()
        return interactive

    def warm_up(self) -> None:
        """Mikrofon-Bibliothek schon im Hintergrund laden - der erste F2-Druck reagiert sofort."""
        if self._usable() and hasattr(self.capture, "warm_up"):
            threading.Thread(target=self.capture.warm_up, name="voice-warmup", daemon=True).start()

    def _fallback(self, exc: Exception) -> str:
        logger.warning("Sprechtaste abgeschaltet: %s", exc)
        self._broken = True
        return input("")

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
        spoken = ""
        try:
            while True:
                with console.raw():
                    first = console.wait_first_key()
                    if first.char == "\x03":
                        raise KeyboardInterrupt
                    if not first.is_f2:
                        break
                    spoken = self._record(console)
                if spoken:
                    break
                self._write(core)  # nichts erkannt: leere Zeile - F2 geht gleich wieder
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - lieber ohne F2 als gar keine Eingabe
            return self._fallback(exc)
        try:
            return console.finish(core, bool(spoken), spoken, self._write)
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as exc:  # noqa: BLE001
            return self._fallback(exc)

    # -- Aufnahme -----------------------------------------------------------
    def _status(self, text: str) -> None:
        pad = max(0, self._status_len - len(text))
        self._write("\r" + text + " " * pad)
        self._status_len = len(text)

    def _end_status(self, text: str = "") -> None:
        self._status(text)
        self._write("\n")
        self._status_len = 0

    def _wait_release(self, console) -> None:
        """Erst weiter, wenn F2 losgelassen ist - sonst landet die Tastenwiederholung
        in der normalen Eingabe (dort oeffnet F2 ein Konsolen-Fenster)."""
        if console.f2_down() is not None:
            end = self._clock() + 10
            while console.f2_down() and self._clock() < end:
                self._sleep(0.05)
        else:
            while console.read_key(_REPEAT_GAP) is not None:
                pass
        console.flush()

    def _record(self, console) -> str:
        """Nimmt auf (halten oder an/aus) und gibt den erkannten Text zurueck."""
        pressed = self._clock()
        self._write("\n")
        problem = self.capture.problem()
        if problem:
            self._write(problem + "\n")
            self._wait_release(console)
            return ""
        try:
            self.capture.start()
        except Exception as exc:  # noqa: BLE001
            self._write(f"{exc}\n")
            self._wait_release(console)
            return ""
        try:
            cancelled = self._wait_until_done(console, pressed)
        except BaseException:
            self.capture.cancel()
            raise
        try:
            console.flush()  # Tastenwiederholungen von F2 verwerfen
        except Exception:  # noqa: BLE001
            pass
        if cancelled:
            self.capture.cancel()
            self._end_status("(Aufnahme abgebrochen - F2 fuer einen neuen Versuch)")
            return ""
        self._status("[Erkenne Sprache …]")
        try:
            text = self.capture.stop()
        except Exception as exc:  # noqa: BLE001
            self._end_status(f"{exc}")
            return ""
        if not text:
            self._end_status("(Nichts verstanden - nochmal F2 oder tippen)")
            return ""
        self._end_status("[Fertig - pruefen und mit Enter abschicken]")
        return text

    def _elapsed(self, start: float) -> str:
        sec = int(self._clock() - start)
        return f"{sec // 60}:{sec % 60:02d}"

    def _hold_by_repeat(self, console, start: float, msg: str) -> None:
        """Linux: solange Tastenwiederholungen kommen, ist F2 gehalten."""
        last = self._clock()
        while self._clock() - last < _REPEAT_GAP:
            self._status(f"{msg}  {self._elapsed(start)}")
            key = console.read_key(0.05)
            if key is not None and key.is_f2:
                last = self._clock()

    def _wait_until_done(self, console, pressed: float) -> bool:
        """Wartet auf das Ende der Aufnahme. True = abgebrochen (Esc)."""
        start = self._clock()
        hold_msg = "[Mikrofon AN] Sprich jetzt - F2 loslassen = fertig"
        toggle_msg = "[Mikrofon AN] Sprich jetzt - F2 = fertig, Esc = abbrechen"

        down = console.f2_down()
        if down is not None:  # Windows: Tastenzustand direkt abfragen
            # Ab dem Tastendruck gemessen (das Mikrofon zu starten dauert etwas).
            while down and self._clock() - pressed < HOLD_SECONDS:
                self._sleep(0.02)
                down = console.f2_down()
            if down:
                while console.f2_down():
                    self._status(f"{hold_msg}  {self._elapsed(start)}")
                    self._sleep(0.05)
                return False
            console.flush()  # Tastenwiederholungen des kurzen Drucks verwerfen
        else:  # Linux/macOS: gehaltene Taste = Tastenwiederholung
            first_repeat = console.read_key(0.8)
            if first_repeat is not None and first_repeat.is_f2:
                self._hold_by_repeat(console, start, hold_msg)
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
                    repeat = console.read_key(0.12)
                    if repeat is not None and repeat.is_f2:
                        self._hold_by_repeat(console, start, hold_msg)
                return False
            if key.char == "\x03":
                raise KeyboardInterrupt


def _stdout_write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
