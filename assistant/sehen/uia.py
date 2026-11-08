"""Passwortfelder erkennen (Windows UI Automation ueber comtypes).

Bevor Nova Text liest oder einen Ausschnitt an das Gehirn schickt, fragt sie: Ist gerade ein
Passwortfeld im Fokus (UIA IsPassword)? Dann schaut sie nicht hin. Weiss sie es nicht (comtypes
fehlt, UIA antwortet nicht), schaut sie sicherheitshalber auch nicht hin ("fail closed").

Muss im Thread laufen, der COM als MTA eingerichtet hat (im Auge-Prozess: der Hauptthread).
"""
from __future__ import annotations

OK = "ok"
PASSWORT = "passwort"
UNBEKANNT = "unbekannt"

_CUIAUTOMATION = "{ff48dba4-60ef-4201-aa87-54103eef594e}"


class PasswortPruefer:
    def __init__(self):
        self._uia = None
        self.fehler = ""

    def start(self) -> bool:
        try:
            import comtypes  # noqa: PLC0415
            import comtypes.client  # noqa: PLC0415

            try:
                comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
            except OSError:
                pass  # schon eingerichtet
            modul = comtypes.client.GetModule("UIAutomationCore.dll")
            self._uia = comtypes.client.CreateObject(_CUIAUTOMATION, interface=modul.IUIAutomation)
            return True
        except Exception as exc:  # noqa: BLE001
            self.fehler = f"{type(exc).__name__}"
            self._uia = None
            return False

    @property
    def bereit(self) -> bool:
        return self._uia is not None

    def pruefe(self) -> str:
        """'passwort', 'ok' oder 'unbekannt'."""
        if self._uia is None:
            return UNBEKANNT
        try:
            element = self._uia.GetFocusedElement()
            if element is None:
                return UNBEKANNT
            return PASSWORT if bool(element.CurrentIsPassword) else OK
        except Exception:  # noqa: BLE001 - Element weg, Fenster zu ...
            return UNBEKANNT


class FakePruefer:
    """Fuer Tests."""

    def __init__(self, antwort: str = OK):
        self.antwort = antwort

    def start(self) -> bool:
        return True

    bereit = True

    def pruefe(self) -> str:
        return self.antwort
