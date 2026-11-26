"""Werkzeug: Aufgaben fuer spaeter planen (Nova handelt dann von selbst - auch in der Cloud, PC aus)."""
from __future__ import annotations

from .. import zeitplan as Z
from ..permissions import Risk
from .base import Tool, ToolContext


class ZeitplanTool(Tool):
    name = "zeitplan"
    description = (
        "Plant Aufgaben, die du SPAETER von selbst erledigst - auch wenn niemand die App offen hat (in der Cloud "
        "sogar bei ausgeschaltetem PC). Fuer 'erinnere mich um ...', 'ruf mich morgen um 8 an', 'jeden Morgen "
        "um 7 das Wetter aufs Handy'. aktion 'planen': wann ('08:00', 'morgen 7:30', 'freitag 18:00', "
        "'27.11. 9:00', 'in 20 minuten'), auftrag (was du dann tust - als klare Anweisung an dich selbst, z.B. "
        "'Ruf meinen Menschen an und erinnere ihn an den Zahnarzt um 9'), wiederholen ('', 'taeglich', "
        "'werktags', 'woechentlich'). 'liste' zeigt alles (und die aktuelle Uhrzeit), 'loeschen' (id) entfernt "
        "eine Aufgabe. Zur faelligen Zeit arbeitest du wie im AFK-Modus; deine Antwort geht aufs Handy."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "aktion": {"type": "string", "enum": ["planen", "liste", "loeschen"]},
            "wann": {"type": "string"},
            "auftrag": {"type": "string"},
            "wiederholen": {"type": "string", "enum": list(Z.WIEDERHOLUNGEN)},
            "id": {"type": "string"},
        },
        "required": ["aktion"],
    }

    def run(self, ctx: ToolContext, aktion: str, wann: str = "", auftrag: str = "", wiederholen: str = "",
            id: str = "") -> str:  # noqa: A002 - so heisst die Angabe fuer das Modell
        root = ctx.extra.get("app_root")
        if root is None:
            return "Planen geht hier nicht (kein Datenordner)."
        if aktion == "liste":
            return Z.uebersicht(root)
        if aktion == "loeschen":
            ctx.permissions.require(Risk.MODERATE, f"Geplante Aufgabe {id} loeschen")
            return "Geloescht." if Z.loeschen(root, id) else "Diese Aufgabe gibt es nicht. 'liste' zeigt alle."
        if aktion != "planen":
            return "Unbekannte Aktion (planen, liste, loeschen)."
        try:
            ziel = Z.zeit_verstehen(wann)
        except Z.ZeitplanFehler as exc:
            return f"Ging nicht: {exc} (Jetzt ist {Z.jetzt():%d.%m.%Y %H:%M}.)"
        wdh = f", {wiederholen}" if wiederholen else ""
        # Nachfragen: eine Aufgabe laeuft spaeter ohne Aufsicht - so kann keine Webseite heimlich etwas planen.
        ctx.permissions.require(Risk.MODERATE, f"Fuer {ziel:%d.%m. %H:%M}{wdh} planen: {(auftrag or '')[:160]}")
        try:
            e = Z.planen(root, wann, auftrag, wiederholen)
        except Z.ZeitplanFehler as exc:
            return f"Ging nicht: {exc}"
        return (f"Geplant [{e['id']}]: {e['wann']}{wdh} - {e['auftrag'][:200]}. Ich mache das dann von selbst "
                "(dafuer muss Nova laufen: in der Cloud immer, am PC nur solange er an ist).")


def register(registry) -> None:
    registry.register(ZeitplanTool())
