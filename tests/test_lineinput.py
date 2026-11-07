"""Sprechtaste F2: halten, an/aus, abbrechen - mit simulierter Tastatur und Uhr."""
import ctypes

import pytest

from assistant.ui import lineinput
from assistant.ui.lineinput import VK_ESCAPE, VK_F2, Key, VoiceLineReader, WindowsConsole

F2 = Key("", VK_F2)
ESC = Key("\x1b", VK_ESCAPE)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class FakeConsole:
    """Tasten kommen zu festen Zeitpunkten; f2_release = wann F2 losgelassen wird."""

    def __init__(self, clock, events, f2_release=None, posix=False):
        self.clock = clock
        self.events = list(events)  # [(zeit, Key)]
        self.f2_release = f2_release
        self.posix = posix
        self.flushed = 0
        self.finished = None

    def raw(self):
        return lineinput._NullContext()

    def wait_first_key(self):
        when, key = self.events[0]
        self.clock.t = max(self.clock.t, when)
        if key.is_f2:
            self.events.pop(0)  # nur F2 wird entnommen
        return key

    def read_key(self, timeout=None):
        if self.events and (timeout is None or self.events[0][0] <= self.clock.t + timeout):
            when, key = self.events.pop(0)
            self.clock.t = max(self.clock.t, when)
            return key
        self.clock.t += timeout or 0
        return None

    def f2_down(self):
        if self.posix:
            return None
        return self.f2_release is not None and self.clock.t < self.f2_release

    def flush(self):
        self.flushed += 1
        self.events = [(w, k) for w, k in self.events if w > self.clock.t]

    def finish(self, prompt_core, reprint, text, write):
        typed = "".join(k.char for _, k in self.events)
        self.finished = (reprint, text, typed)
        return text + typed


class FakeCapture:
    def __init__(self, *texts, problem=None, start_delay=0.0, clock=None):
        self.texts = list(texts) or ["Hallo Welt"]
        self._problem = problem
        self.start_delay = start_delay
        self.clock = clock
        self.calls = []

    def problem(self):
        return self._problem

    def start(self):
        self.calls.append("start")
        if self.clock:
            self.clock.t += self.start_delay

    def stop(self):
        self.calls.append("stop")
        return self.texts.pop(0)

    def cancel(self):
        self.calls.append("cancel")


def _reader(console, capture, clock):
    out = []
    reader = VoiceLineReader(capture, console=console, write=out.append, clock=clock, sleep=clock.sleep,
                             interactive=True)
    return reader, out


def test_typing_is_left_for_normal_input():
    clock = Clock()
    console = FakeConsole(clock, [(0, Key("h")), (0, Key("a")), (0, Key("l")), (0, Key("l")), (0, Key("o"))])
    capture = FakeCapture()
    reader, out = _reader(console, capture, clock)
    assert reader.read("\nDu: ") == "hallo"
    assert console.finished == (False, "", "hallo")  # nichts entnommen, nichts neu geschrieben
    assert capture.calls == [] and out[0] == "\nDu: "


def test_hold_f2_records_until_release():
    clock = Clock()
    console = FakeConsole(clock, [(0, F2)], f2_release=3.0)
    capture = FakeCapture("Wie wird das Wetter?")
    reader, out = _reader(console, capture, clock)
    assert reader.read("Du: ") == "Wie wird das Wetter?"
    assert capture.calls == ["start", "stop"]
    assert console.finished[:2] == (True, "Wie wird das Wetter?")
    assert clock.t >= 3.0
    assert any("loslassen" in o for o in out)


def test_hold_detected_even_if_microphone_starts_slowly():
    clock = Clock()
    console = FakeConsole(clock, [(0, F2)], f2_release=2.0)
    capture = FakeCapture("langsam", start_delay=1.0, clock=clock)  # Mikrofon braucht 1 s
    reader, out = _reader(console, capture, clock)
    assert reader.read("Du: ") == "langsam"
    assert any("loslassen" in o for o in out) and not any("F2 = fertig" in o for o in out)


def test_tap_f2_toggles_until_second_press():
    clock = Clock()
    # kurz gedrueckt (0,1 s), Tastenwiederholung bei 0,3 s wird verworfen, zweiter Druck bei 5 s
    console = FakeConsole(clock, [(0, F2), (0.3, F2), (5.0, F2)], f2_release=0.1)
    capture = FakeCapture("Erinnere mich morgen")
    reader, out = _reader(console, capture, clock)
    assert reader.read("Du: ") == "Erinnere mich morgen"
    assert capture.calls == ["start", "stop"]
    assert clock.t >= 5.0
    assert any("F2 = fertig" in o for o in out)


def test_escape_cancels_and_f2_works_again():
    clock = Clock()
    events = [(0, F2), (2.0, ESC), (3.0, F2), (6.0, F2)]
    console = FakeConsole(clock, events, f2_release=0.1)
    capture = FakeCapture("zweiter Versuch")
    reader, out = _reader(console, capture, clock)
    console.f2_release = 0.1
    assert reader.read("Du: ") == "zweiter Versuch"
    assert capture.calls == ["start", "cancel", "start", "stop"]
    assert any("abgebrochen" in o for o in out)


def test_nothing_understood_then_retry_with_f2():
    clock = Clock()
    console = FakeConsole(clock, [(0, F2), (5.0, F2)], f2_release=1.0)
    capture = FakeCapture("", "jetzt aber")

    def f2_down():  # zweiter Druck wird bei 5 s gehalten bis 6 s
        return clock.t < 1.0 or 5.0 <= clock.t < 6.0

    console.f2_down = f2_down
    reader, out = _reader(console, capture, clock)
    assert reader.read("Du: ") == "jetzt aber"
    assert any("Nichts verstanden" in o for o in out)
    assert capture.calls == ["start", "stop", "start", "stop"]


def test_missing_packages_explained_and_waits_for_release():
    clock = Clock()
    console = FakeConsole(clock, [(0, F2), (3.0, Key("x"))], f2_release=2.0)
    capture = FakeCapture(problem="Tippe /sprache einrichten")
    reader, out = _reader(console, capture, clock)
    assert reader.read("Du: ") == "x"
    assert capture.calls == [] and any("/sprache einrichten" in o for o in out)
    assert clock.t >= 2.0 and console.flushed  # erst nach dem Loslassen weiter


def test_posix_hold_via_key_repeat():
    clock = Clock()
    repeats = [(0.6 + i * 0.04, F2) for i in range(30)]  # gehalten bis ~1,8 s
    console = FakeConsole(clock, [(0, F2)] + repeats, posix=True)
    capture = FakeCapture("gehalten")
    reader, _ = _reader(console, capture, clock)
    assert reader.read("Du: ") == "gehalten"
    assert 1.8 <= clock.t < 3.0


def test_posix_tap_toggle():
    clock = Clock()
    console = FakeConsole(clock, [(0, F2), (4.0, F2)], posix=True)
    capture = FakeCapture("an aus")
    reader, _ = _reader(console, capture, clock)
    assert reader.read("Du: ") == "an aus"
    assert clock.t >= 4.0


def test_ctrl_c_still_works():
    clock = Clock()
    console = FakeConsole(clock, [(0, Key("\x03"))])
    reader, _ = _reader(console, FakeCapture(), clock)
    with pytest.raises(KeyboardInterrupt):
        reader.read("Du: ")


def test_broken_console_falls_back_to_input(monkeypatch):
    class Broken(FakeConsole):
        def wait_first_key(self):
            raise OSError("keine Konsole")

    clock = Clock()
    monkeypatch.setattr("builtins.input", lambda prompt="": "getippt")
    reader, _ = _reader(Broken(clock, []), FakeCapture(), clock)
    assert reader.read("Du: ") == "getippt"
    assert reader._broken  # danach immer normales input()
    assert reader.read("Du: ") == "getippt"


def test_error_while_inserting_text_falls_back(monkeypatch):
    class BadFinish(FakeConsole):
        def finish(self, *a):
            raise OSError("WriteConsoleInputW")

    clock = Clock()
    monkeypatch.setattr("builtins.input", lambda prompt="": "trotzdem")
    reader, _ = _reader(BadFinish(clock, [(0, F2)], f2_release=1.0), FakeCapture("x"), clock)
    assert reader.read("Du: ") == "trotzdem"


def test_not_interactive_uses_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "aus Datei")
    reader = VoiceLineReader(FakeCapture(), interactive=False)
    assert reader.read("Du: ") == "aus Datei"


def test_split_prompt_with_colours():
    assert lineinput._split_prompt("\nDu: ") == ("\n", "Du: ")
    assert lineinput._split_prompt("\x1b[32m\nDu: \x1b[0m") == ("\n", "\x1b[32mDu: \x1b[0m")


def test_status_line_is_fully_overwritten():
    out = []
    reader = VoiceLineReader(FakeCapture(), write=out.append)
    reader._status("[Mikrofon AN] Sprich jetzt - F2 = fertig, Esc = abbrechen  0:05")
    reader._status("[Erkenne Sprache …]")
    assert len(out[1]) == len(out[0])


# ----- echte WindowsConsole-Logik gegen einen nachgebauten Konsolenpuffer ------------
_KEY, _RECORD = lineinput._win_structs()


def _rec(vk=0, char="", down=True, mods=0, etype=1):
    rec = _RECORD()
    rec.EventType = etype
    rec.Event.KeyEvent.bKeyDown = 1 if down else 0
    rec.Event.KeyEvent.wVirtualKeyCode = vk
    rec.Event.KeyEvent.UnicodeChar = ord(char) if char else 0
    rec.Event.KeyEvent.dwControlKeyState = mods
    return rec


class FakeKernel32:
    def __init__(self, records):
        self.queue = list(records)

    def GetNumberOfConsoleInputEvents(self, handle, ref):  # noqa: N802
        ref._obj.value = len(self.queue)
        return 1

    def _copy(self, buf, n, ref, remove):
        taken = self.queue[:n]
        for i, rec in enumerate(taken):
            ctypes.memmove(ctypes.addressof(buf) + i * ctypes.sizeof(_RECORD), ctypes.addressof(rec),
                           ctypes.sizeof(_RECORD))
        ref._obj.value = len(taken)
        if remove:
            del self.queue[: len(taken)]
        return 1

    def PeekConsoleInputW(self, h, buf, n, ref):  # noqa: N802
        return self._copy(buf, n, ref, False)

    def ReadConsoleInputW(self, h, buf, n, ref):  # noqa: N802
        return self._copy(buf, n, ref, True)

    def WriteConsoleInputW(self, h, buf, n, ref):  # noqa: N802
        for i in range(n):
            rec = _RECORD()
            ctypes.memmove(ctypes.addressof(rec), ctypes.addressof(buf) + i * ctypes.sizeof(_RECORD),
                           ctypes.sizeof(_RECORD))
            self.queue.append(rec)
        ref._obj.value = n
        return 1

    def FlushConsoleInputBuffer(self, h):  # noqa: N802
        self.queue.clear()
        return 1


class FakeUser32:
    def GetAsyncKeyState(self, vk):  # noqa: N802
        return 0

    def VkKeyScanW(self, unit):  # noqa: N802
        return -1

    def MapVirtualKeyW(self, vk, kind):  # noqa: N802
        return 0


def _win(records):
    con = WindowsConsole.__new__(WindowsConsole)
    con._ctypes, con._KEY, con._RECORD, con._handle = ctypes, _KEY, _RECORD, None
    con._k32, con._u32 = FakeKernel32(records), FakeUser32()
    return con


def _chars(queue):
    units = "".join(chr(r.Event.KeyEvent.UnicodeChar) for r in queue
                    if r.Event.KeyEvent.bKeyDown and r.Event.KeyEvent.UnicodeChar)
    return units.encode("utf-16-le", "surrogatepass").decode("utf-16-le")


def test_windows_typing_stays_untouched_in_buffer():
    # Loslassen von Enter (vorige Zeile), dann getippter/eingefuegter Text inkl. Alt+Numpad-Folge
    records = [_rec(0x0D, "\r", down=False), _rec(0x48, "H"), _rec(0x48, "H", down=False),
               _rec(0x12, "", mods=0x2), _rec(0x12, "„", down=False, mods=0x2), _rec(0x49, "i")]
    con = _win(records)
    key = con.wait_first_key()
    assert key.char == "H" and not key.is_f2
    assert len(con._k32.queue) == 5  # nur das bedeutungslose Loslassen entfernt, Rest unveraendert


def test_windows_f2_is_taken_out():
    con = _win([_rec(VK_F2), _rec(0x58, "x")])
    assert con.wait_first_key().is_f2
    assert _chars(con._k32.queue) == "x"


def test_windows_shift_f2_is_not_the_speech_key():
    con = _win([_rec(VK_F2, mods=0x10)])
    assert not con.wait_first_key().is_f2


def test_windows_finish_types_text_before_later_keys(monkeypatch):
    # waehrend der Erkennung: F2-Wiederholung (verwerfen) und Enter (= gleich abschicken)
    con = _win([_rec(VK_F2), _rec(0x0D, "\r")])
    seen = {}
    monkeypatch.setattr("builtins.input", lambda prompt="": seen.setdefault("q", _chars(con._k32.queue)))
    con.finish("Du: ", True, "Grüße 😀", lambda s: None)
    assert seen["q"] == "Grüße 😀\r"
    assert not any(r.Event.KeyEvent.wVirtualKeyCode == VK_F2 for r in con._k32.queue)


def test_windows_structures_match_win32_layout():
    assert ctypes.sizeof(_KEY) == 16 and ctypes.sizeof(_RECORD) == 20
    assert _RECORD.Event.offset == 4
    assert lineinput._utf16_units("ä😀") == [0xE4, 0xD83D, 0xDE00]
    assert lineinput._utf16_units("\ud83d") == [0xD83D]  # einzelne Emoji-Haelfte: kein Absturz


def test_windows_modifier_keys_do_not_count_as_first_key():
    # Alt+Tab (Alt runter, Fokus weg/wieder da, Alt hoch) bzw. Strg zum Kopieren, dann F2
    records = [_rec(0x12, mods=0x2), _rec(0, etype=0x10), _rec(0x12, down=False),
               _rec(0x11, mods=0x8), _rec(0x11, down=False), _rec(VK_F2)]
    con = _win(records)
    assert con.wait_first_key().is_f2
    assert con._k32.queue == []


def test_windows_shift_letter_is_typing():
    con = _win([_rec(0x10, mods=0x10), _rec(0x41, "A", mods=0x10)])
    key = con.wait_first_key()
    assert key.char == "A" and len(con._k32.queue) == 1  # Umschalt-Druck weg, "A" bleibt fuer input()
