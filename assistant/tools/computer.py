"""PC-Steuerung: Maus bewegen/klicken und Tastatur bedienen - wie ein Mensch.

Dies ist die "Jarvis"-Faehigkeit: die KI bedient den Bildschirm direkt. Es nutzt
'pyautogui' (optional). Ohne das Paket meldet das Werkzeug freundlich, dass es
nachinstalliert werden muss - die KI bleibt ansonsten voll funktionsfaehig.

Jede Aktion gilt als DANGEROUS und ist damit im Safe Mode gesperrt bzw. erfordert
Bestaetigung. So behaelt der Mensch die Kontrolle ueber die physische Steuerung.
"""
from __future__ import annotations

from ..permissions import Risk
from .base import Tool, ToolContext


def _load_pyautogui():
    try:
        import pyautogui  # type: ignore

        pyautogui.FAILSAFE = True  # Maus in die Ecke = Not-Aus
        return pyautogui, None
    except Exception as exc:  # noqa: BLE001 - z.B. kein Display vorhanden
        return None, (
            "PC-Steuerung nicht verfuegbar. Installiere sie mit: pip install pyautogui pillow\n"
            f"(Details: {exc})"
        )


class ScreenshotTool(Tool):
    name = "bildschirmfoto"
    description = "Macht ein Foto des Bildschirms und speichert es im Arbeitsordner; gibt den Pfad zurueck."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, ctx: ToolContext) -> str:
        ctx.permissions.require(Risk.MODERATE, "Bildschirmfoto aufnehmen")
        pyautogui, err = _load_pyautogui()
        if err:
            return err
        target = ctx.permissions.workspace_root / "bildschirmfoto.png"
        pyautogui.screenshot(str(target))
        return f"Bildschirmfoto gespeichert: {target}"


class MouseClickTool(Tool):
    name = "maus_klick"
    description = "Bewegt die Maus zu (x, y) und klickt. Koordinaten in Bildschirmpixeln."
    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "taste": {"type": "string", "description": "links | rechts | doppelt"},
        },
        "required": ["x", "y"],
    }

    def run(self, ctx: ToolContext, x: int, y: int, taste: str = "links") -> str:
        ctx.permissions.require(Risk.DANGEROUS, f"Mausklick bei ({x}, {y}) [{taste}]")
        pyautogui, err = _load_pyautogui()
        if err:
            return err
        if taste == "doppelt":
            pyautogui.doubleClick(x, y)
        elif taste == "rechts":
            pyautogui.click(x, y, button="right")
        else:
            pyautogui.click(x, y, button="left")
        return f"Geklickt bei ({x}, {y}) [{taste}]."


class TypeTextTool(Tool):
    name = "tastatur_tippen"
    description = "Tippt den angegebenen Text an der aktuellen Eingabestelle."
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, ctx: ToolContext, text: str) -> str:
        ctx.permissions.require(Risk.DANGEROUS, f"Text tippen: {text[:60]}")
        pyautogui, err = _load_pyautogui()
        if err:
            return err
        pyautogui.typewrite(text, interval=0.01)
        return f"Getippt ({len(text)} Zeichen)."


class HotkeyTool(Tool):
    name = "tastenkombination"
    description = "Drueckt eine Tastenkombination, z.B. ['ctrl','s'] zum Speichern oder ['alt','tab']."
    input_schema = {
        "type": "object",
        "properties": {
            "tasten": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste von Tastennamen, gleichzeitig gedrueckt",
            }
        },
        "required": ["tasten"],
    }

    def run(self, ctx: ToolContext, tasten: list[str]) -> str:
        combo = "+".join(tasten)
        ctx.permissions.require(Risk.DANGEROUS, f"Tastenkombination: {combo}")
        pyautogui, err = _load_pyautogui()
        if err:
            return err
        pyautogui.hotkey(*tasten)
        return f"Gedrueckt: {combo}"


def register(registry) -> None:
    for tool in (ScreenshotTool(), MouseClickTool(), TypeTextTool(), HotkeyTool()):
        registry.register(tool)
