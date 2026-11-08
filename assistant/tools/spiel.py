"""Werkzeuge fuer den Spielmodus (siehe assistant/spiel).

spiel_starten gehoert zum normalen Gespraech: es schlaegt eine Spielsitzung nur VOR - beginnen
kann sie erst, wenn dein Mensch im Fenster (bzw. im Terminal) zustimmt.
spiel_aktion, spiel_notiz und spiel_ende gibt es nur in einer laufenden Spielsitzung (eigenes
Gespraech mit genau diesen drei Werkzeugen - nie Dateien, Befehle oder Internet).
"""
from __future__ import annotations

from ..permissions import PermissionError_, Risk
from .base import Tool, ToolContext, ToolOutput

AKTION_TYPEN = ["taste", "tasten_halten", "klick", "doppelklick", "rechtsklick", "ziehen", "ziehen_relativ",
                "kamera_drehen", "scrollen", "maus_bewegen", "warten", "pause", "weiter", "schneller", "langsamer",
                "speichern"]

# Bewusst schlank: Claude erlaubt in allen "strict"-Werkzeugen zusammen nur 24 optionale Angaben.
_AKTION = {
    "type": "object",
    "properties": {
        "typ": {"type": "string", "enum": AKTION_TYPEN},
        "taste": {"type": "string", "description": "z.B. 'c', 'esc', 'space', 'tab' oder 'ctrl+1'"},
        "x": {"type": "number", "description": "0..1 im Spielfenster (Pixel-x / Bildbreite)"},
        "y": {"type": "number", "description": "0..1 im Spielfenster (Pixel-y / Bildhoehe)"},
        "x2": {"type": "number"},
        "y2": {"type": "number"},
        "zahl": {"type": "number", "description": "warten/tasten_halten: Sekunden, scrollen: Rasten (+ hinein, "
                                                  "- hinaus), kamera_drehen: Pixel (- links, + rechts)"},
        "knopf": {"type": "string", "enum": ["links", "rechts", "mitte"]},
    },
    "required": ["typ"],
    "additionalProperties": False,
}


def _sitzung(ctx: ToolContext):
    sitzung = ctx.extra.get("spiel_sitzung")
    if sitzung is None or not getattr(sitzung, "laeuft", False):
        return None
    return sitzung


def _erlaubt(ctx: ToolContext) -> str:
    try:
        ctx.permissions.require_spiel()
    except PermissionError_ as exc:
        return str(exc)
    return ""


class SpielAktionTool(Tool):
    name = "spiel_aktion"
    description = (
        "Spielmodus: steuert das Spiel mit Maus und Tastatur - nur, solange das Spielfenster vorne ist. "
        "aktionen = Liste (der Reihe nach, hoechstens 12): taste (taste, auch 'ctrl+1'), tasten_halten (taste, "
        "zahl = Sekunden; das neue Bild entsteht, waehrend die Taste gehalten wird), klick/doppelklick/rechtsklick "
        "(x, y, knopf), ziehen (x, y -> x2, y2, knopf), ziehen_relativ (wie ziehen, mit relativen Mausbewegungen - "
        "z.B. Gebaeude drehen), kamera_drehen (zahl = Pixel), scrollen (zahl = Rasten, optional x, y), "
        "maus_bewegen (x, y), warten (zahl = Sekunden), pause/weiter (Pausentaste einmal), schneller/langsamer, "
        "speichern. Koordinaten 0..1 relativ zum Spielfenster. Danach kommt ein neues Bild (bild_danach=false "
        "spart es). laufen_sekunden: wie lange das Spiel nach diesem Zug laufen soll (0-120)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "aktionen": {"type": "array", "items": _AKTION},
            "laufen_sekunden": {"type": "number"},
            "bild_danach": {"type": "boolean"},
        },
        "required": ["aktionen"],
    }
    sparmodus_kuerzen = False

    def run(self, ctx: ToolContext, aktionen: list, laufen_sekunden: float | None = None,
            bild_danach: bool = True) -> str | ToolOutput:
        sitzung = _sitzung(ctx)
        if sitzung is None:
            return "Der Spielmodus läuft gerade nicht."
        gesperrt = _erlaubt(ctx)
        if gesperrt:
            return gesperrt
        return sitzung.aktionen_ausfuehren(aktionen, laufen_sekunden, bild_danach)


class SpielNotizTool(Tool):
    name = "spiel_notiz"
    description = (
        "Spielmodus: Tagebuch (dein Gedaechtnis ueber lange Sitzungen). art 'plan' (aktueller Plan), "
        "'fortschritt' (was erledigt ist, mit Datum im Spiel), 'problem' (was nicht klappt), 'kalibrierung' "
        "(elemente = Positionen wichtiger Anzeigen: name, x, y 0..1, text = kurze Beschreibung)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "art": {"type": "string", "enum": ["plan", "fortschritt", "problem", "kalibrierung"]},
            "text": {"type": "string", "description": "kalibrierung: kurze Notiz oder ''"},
            "elemente": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"},
                                   "text": {"type": "string"}},
                    "required": ["name", "x", "y", "text"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["art", "text"],
    }

    def run(self, ctx: ToolContext, art: str, text: str = "", elemente: list | None = None) -> str:
        sitzung = _sitzung(ctx)
        if sitzung is None:
            return "Der Spielmodus läuft gerade nicht."
        return sitzung.notiz(art, text, elemente)


class SpielEndeTool(Tool):
    name = "spiel_ende"
    description = ("Spielmodus beenden: grund 'fertig' (Ziel erreicht) oder 'aufgeben' (es geht wirklich nicht "
                   "weiter); text = kurzes Ergebnis fuer deinen Menschen.")
    input_schema = {
        "type": "object",
        "properties": {"grund": {"type": "string", "enum": ["fertig", "aufgeben"]}, "text": {"type": "string"}},
        "required": ["grund", "text"],
    }

    def run(self, ctx: ToolContext, grund: str, text: str = "") -> str:
        sitzung = _sitzung(ctx)
        if sitzung is None:
            return "Der Spielmodus läuft gerade nicht."
        return sitzung.beenden_wunsch(grund, text)


class SpielStartenTool(Tool):
    name = "spiel_starten"
    description = (
        "Spielmodus vorschlagen: NUR wenn dein Mensch ausdruecklich will, dass du ein Einzelspieler-Spiel selbst "
        "spielst (z.B. 'spiel Manor Lords', 'bau mir eine schoene Stadt', 'spiel heute Nacht weiter'). ziel = was "
        "du im Spiel erreichen sollst, modus 'normal' oder 'nacht' (Spiel-AFK, waehrend er schlaeft). Es beginnt "
        "erst, wenn er im Fenster zustimmt - sag ihm, dass er danach ins Spiel wechseln soll. Nie fuer Online- "
        "oder Mehrspieler-Spiele."
    )
    input_schema = {
        "type": "object",
        "properties": {"ziel": {"type": "string"}, "modus": {"type": "string", "enum": ["normal", "nacht"]}},
        "required": ["ziel", "modus"],
    }

    def run(self, ctx: ToolContext, ziel: str, modus: str = "normal") -> str:
        vorschlag = ctx.extra.get("spiel_vorschlag")
        if vorschlag is None:
            return "Den Spielmodus gibt es hier nicht."
        ctx.permissions.require(Risk.SAFE, "Spielmodus vorschlagen")
        return str(vorschlag(str(ziel or "")[:2000], "nacht" if modus == "nacht" else "normal"))


SPIEL_WERKZEUGE = ("spiel_aktion", "spiel_notiz", "spiel_ende")


def spiel_registry():
    """Eigenes Registry nur fuer die Spielsitzung - genau diese drei Werkzeuge."""
    from .base import ToolRegistry

    registry = ToolRegistry()
    for tool in (SpielAktionTool(), SpielNotizTool(), SpielEndeTool()):
        registry.register(tool)
    return registry


def register(registry) -> None:
    registry.register(SpielStartenTool())
