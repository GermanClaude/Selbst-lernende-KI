"""Tippen mit Umlauten: pyautogui.typewrite kann nur ASCII - Umlaute gehen ueber die Unicode-Eingabe."""
from types import SimpleNamespace

from assistant.tools import computer


def test_ascii_nutzt_pyautogui(monkeypatch):
    getippt = []
    fake_pg = SimpleNamespace(typewrite=lambda t, interval=0: getippt.append(t))
    monkeypatch.setattr(computer, "_tippe_unicode_windows", lambda t: getippt.append("UNICODE:" + t))
    computer._tippe(fake_pg, "hello world 123")
    assert getippt == ["hello world 123"]  # reines ASCII -> pyautogui


def test_umlaute_auf_windows_nutzen_unicode(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    genutzt = []
    monkeypatch.setattr(computer, "_tippe_unicode_windows", lambda t: genutzt.append(t))
    fake_pg = SimpleNamespace(typewrite=lambda *a, **k: genutzt.append("PYAUTOGUI"))
    computer._tippe(fake_pg, "Grüße an Nova – schöne Küche")
    assert genutzt == ["Grüße an Nova – schöne Küche"]  # Nicht-ASCII -> Unicode-Eingabe, nicht pyautogui


def test_umlaute_ohne_windows_faellt_zurueck(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    getippt = []
    fake_pg = SimpleNamespace(typewrite=lambda t, interval=0: getippt.append(t))
    computer._tippe(fake_pg, "Grüße")
    assert getippt == ["Grüße"]  # kein Windows -> der bisherige Weg
