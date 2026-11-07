"""Sprechtaste F2: halten, an/aus, abbrechen - mit simulierter Tastatur und Uhr."""
import ctypes

import pytest

from assistant.ui import lineinput
from assistant.ui.lineinput import VK_ESCAPE, VK_F2, Key, VoiceLineReader

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

    def read_key(self, timeout=None):
        if self.events and (timeout is None or self.events[0][0] <= self.clock.t + timeout):
            when, key = self.events.pop(0)
            self.clock.t = max(self.clock.t, when)
            return key
        self.clock.t += timeout or 0
        return None

    def drain(self):
        keys = [k for when, k in self.events if when <= self.clock.t]
        self.events = [(w, k) for w, k in self.events if w > self.clock.t]
        return keys

    def f2_down(self):
        if self.posix:
            return None
        return self.f2_release is not None and self.clock.t < self.f2_release

    def flush(self):
        self.flushed += 1
        self.events = [(w, k) for w, k in self.events if w > self.clock.t]

    def finish(self, prompt_core, reprint, text, keys, write):
        self.finished = (reprint, text, [k.char for k in keys])
        return text + "".join(k.char for k in keys)


class FakeCapture:
    def __init__(self, text="Hallo Welt", problem=None):
        self.text = text
        self._problem = problem
        self.calls = []

    def problem(self):
        return self._problem

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")
        return self.text

    def cancel(self):
        self.calls.append("cancel")


def _reader(console, capture, clock):
    out = []
    reader = VoiceLineReader(capture, console=console, write=out.append, clock=clock, sleep=clock.sleep,
                             interactive=True)
    return reader, out


def test_typing_goes_to_normal_input():
    clock = Clock()
    console = FakeConsole(clock, [(0, Key("h")), (0, Key("a")), (0, Key("l")), (0, Key("l")), (0, Key("o"))])
    capture = FakeCapture()
    reader, out = _reader(console, capture, clock)
    assert reader.read("\nDu: ") == "hallo"
    assert console.finished == (False, "", ["h", "a", "l", "l", "o"])
    assert capture.calls == [] and out[0] == "\nDu: "


def test_hold_f2_records_until_release():
    clock = Clock()
    console = FakeConsole(clock, [(0, F2)], f2_release=3.0)
    capture = FakeCapture("Wie wird das Wetter?")
    reader, out = _reader(console, capture, clock)
    assert reader.read("Du: ") == "Wie wird das Wetter?"
    assert capture.calls == ["start", "stop"]
    assert console.finished[0] is True  # Eingabeaufforderung neu zeigen, Text vorbelegt
    assert clock.t >= 3.0
    assert any("loslassen" in o for o in out)


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


def test_escape_cancels_recording():
    clock = Clock()
    console = FakeConsole(clock, [(0, F2), (2.0, ESC)], f2_release=0.1)
    capture = FakeCapture()
    reader, out = _reader(console, capture, clock)
    assert reader.read("Du: ") == ""
    assert capture.calls == ["start", "cancel"]
    assert any("abgebrochen" in o for o in out)


def test_missing_packages_are_explained():
    clock = Clock()
    console = FakeConsole(clock, [(0, F2)], f2_release=0.1)
    capture = FakeCapture(problem="Tippe /sprache einrichten")
    reader, out = _reader(console, capture, clock)
    assert reader.read("Du: ") == ""
    assert capture.calls == [] and any("/sprache einrichten" in o for o in out)


def test_nothing_understood():
    clock = Clock()
    console = FakeConsole(clock, [(0, F2)], f2_release=1.0)
    reader, out = _reader(console, FakeCapture(""), clock)
    assert reader.read("Du: ") == ""
    assert any("Nichts verstanden" in o for o in out)


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
        def read_key(self, timeout=None):
            raise OSError("keine Konsole")

    clock = Clock()
    monkeypatch.setattr("builtins.input", lambda prompt="": "getippt")
    reader, _ = _reader(Broken(clock, []), FakeCapture(), clock)
    assert reader.read("Du: ") == "getippt"
    assert reader._broken  # danach immer normales input()
    assert reader.read("Du: ") == "getippt"


def test_not_interactive_uses_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "aus Datei")
    reader = VoiceLineReader(FakeCapture(), interactive=False)
    assert reader.read("Du: ") == "aus Datei"


def test_windows_structures_match_win32_layout():
    key, record = lineinput._win_structs()
    assert ctypes.sizeof(key) == 16 and ctypes.sizeof(record) == 20
    assert record.Event.offset == 4
    assert lineinput._utf16_units("ä😀") == [0xE4, 0xD83D, 0xDE00]
