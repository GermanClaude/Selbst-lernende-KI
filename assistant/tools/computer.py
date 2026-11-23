"""PC-Steuerung: Maus bewegen/klicken und Tastatur bedienen - wie ein Mensch.

Dies ist die "Jarvis"-Faehigkeit: die KI bedient den Bildschirm direkt. Es nutzt
'pyautogui' (optional). Ohne das Paket meldet das Werkzeug freundlich, dass es
nachinstalliert werden muss - die KI bleibt ansonsten voll funktionsfaehig.

Jede Aktion gilt als DANGEROUS und ist damit im Safe Mode gesperrt bzw. erfordert
Bestaetigung. So behaelt der Mensch die Kontrolle ueber die physische Steuerung.
"""
from __future__ import annotations

from ..bilder import STANDARD_KANTE, BildFehler, vorbereiten
from ..permissions import Risk
from .base import Tool, ToolContext, ToolOutput


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


def _tippe(pyautogui, text: str) -> None:
    """Tippt Text - inkl. Umlaute/Sonderzeichen. pyautogui.typewrite kann nur ASCII (laesst
    ae/oe/ue/ss und Emojis einfach weg); darum unter Windows alles mit Nicht-ASCII ueber die
    Windows-Unicode-Eingabe tippen. Sonst (oder im Notfall) der bisherige Weg."""
    import sys

    if sys.platform == "win32" and not text.isascii():
        try:
            _tippe_unicode_windows(text)
            return
        except Exception:  # noqa: BLE001 - Notfalls der alte Weg (tippt dann wenigstens das ASCII)
            pass
    pyautogui.typewrite(text, interval=0.01)


def _tippe_unicode_windows(text: str) -> None:
    """Jeden Buchstaben als Unicode-Zeichen an das aktive Fenster schicken (SendInput mit
    KEYEVENTF_UNICODE) - unabhaengig vom Tastaturlayout, also mit Umlauten."""
    import ctypes
    import time
    from ctypes import wintypes

    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class _UNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]

    user32 = ctypes.windll.user32

    def _einheit(code: int, hoch: bool) -> None:
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if hoch else 0)
        inp = _INPUT(type=INPUT_KEYBOARD, u=_UNION(ki=_KEYBDINPUT(0, code, flags, 0, None)))
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    einheiten = text.encode("utf-16-le")
    for i in range(0, len(einheiten), 2):
        code = einheiten[i] | (einheiten[i + 1] << 8)  # 16-bit-Einheit (Surrogate: zwei Einheiten)
        _einheit(code, False)
        _einheit(code, True)
        time.sleep(0.005)


class ScreenshotTool(Tool):
    name = "bildschirmfoto"
    description = (
        "Macht ein Foto des Bildschirms, speichert es im Arbeitsordner und zeigt es dir - du "
        "siehst das Bild. Ist es verkleinert, steht im Ergebnis, wie du Bild-Koordinaten fuer "
        "maus_klick umrechnest."
    )
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, ctx: ToolContext) -> str | ToolOutput:
        ctx.permissions.require(Risk.MODERATE, "Bildschirmfoto aufnehmen")
        pyautogui, err = _load_pyautogui()
        if err:
            return err
        target = ctx.permissions.workspace_root / "bildschirmfoto.png"
        foto = pyautogui.screenshot(str(target))
        text = f"Bildschirmfoto gespeichert: {target}"
        try:
            # Einmal verkleinert - so geht es an das Modell und wird nie mehr veraendert.
            bild = vorbereiten(target.read_bytes(), target.name, max_kante=_max_kante(ctx))
        except (BildFehler, OSError) as exc:
            return f"{text} (Ich konnte es dir nicht zeigen: {exc})"
        return ToolOutput(f"{text}\n{_masstab(pyautogui, foto, bild)}", [bild])


# Claude: ab mehr als 20 Bildern in einer Anfrage darf keine Seite laenger als 2000 Pixel
# sein - Bildschirmfotos sammeln sich bei PC-Aufgaben schnell im Verlauf.
_MAX_KANTE_FOTO = 2000


def _max_kante(ctx: ToolContext) -> int:
    config = ctx.extra.get("config")
    try:
        kante = int(config.bilder.max_kantenlaenge) or STANDARD_KANTE
    except (AttributeError, TypeError, ValueError):
        kante = STANDARD_KANTE
    return max(64, min(kante, _MAX_KANTE_FOTO))


def _masstab(pyautogui, foto, bild) -> str:
    """Wie Bild-Pixel zu Bildschirm-Pixeln (fuer maus_klick) passen."""
    breite, hoehe = None, None
    try:
        breite, hoehe = (int(v) for v in pyautogui.size())
    except Exception:  # noqa: BLE001 - dann eben die Groesse des Fotos
        try:
            breite, hoehe = (int(v) for v in foto.size)
        except Exception:  # noqa: BLE001
            pass
    if not (breite and hoehe and bild.breite and bild.hoehe):
        return "(Bildgroesse unbekannt - Koordinaten fuer maus_klick bitte vorsichtig schaetzen.)"
    if (breite, hoehe) == (bild.breite, bild.hoehe):
        return f"Bild in Originalgroesse ({breite}x{hoehe}) - die Koordinaten passen direkt fuer maus_klick."
    faktor = breite / bild.breite
    return (f"Bildschirm: {breite}x{hoehe} Pixel, das Bild hier: {bild.breite}x{bild.hoehe}. "
            f"Fuer maus_klick die Bild-Koordinaten mal {faktor:.3f} nehmen.")


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
        _tippe(pyautogui, text)
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
