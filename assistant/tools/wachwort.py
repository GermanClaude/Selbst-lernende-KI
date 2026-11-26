"""Werkzeug: Wachwort am PC einstellen ("Hey Nova") - z.B. 'beim Aufwachen nicht gleich zuhoeren'."""
from __future__ import annotations

import sys

from .. import wachwort as W
from ..permissions import PermissionError_, Risk
from .base import Tool, ToolContext


class WachwortTool(Tool):
    name = "wachwort"
    description = (
        "Stellt das Wachwort am PC ein: Sagt dein Mensch es (Standard 'Hey Nova'), startest du bzw. kommst nach "
        "vorne - auf einem Bildschirm ohne Spiel/Vollbild - und die Spracheingabe geht an. aktion: 'status', "
        "'sprechen_an' / 'sprechen_aus' (Spracheingabe beim Aufwachen an/aus - z.B. wenn er sagt 'hoer nicht "
        "jedes Mal gleich zu'), 'wort' (text = neues Wachwort, 2-5 Woerter), 'an' / 'aus' (den Hintergrund-"
        "Lauscher ein- oder ausschalten; 'an' richtet einen Start beim Anmelden ein und braucht seine Zustimmung)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "aktion": {"type": "string", "enum": ["status", "sprechen_an", "sprechen_aus", "wort", "an", "aus"]},
            "text": {"type": "string"},
        },
        "required": ["aktion"],
    }

    def run(self, ctx: ToolContext, aktion: str, text: str = "") -> str:
        root = ctx.extra.get("app_root")
        if root is None:
            return "Geht hier nicht."
        try:
            if aktion == "status":
                return W.status_text(root)
            if aktion in ("sprechen_an", "sprechen_aus"):
                ctx.permissions.require(Risk.MODERATE, "Wachwort: Spracheingabe beim Aufwachen "
                                        + ("an" if aktion == "sprechen_an" else "aus"))
                W.speichern(root, sprechen=aktion == "sprechen_an")
                return "Erledigt. " + W.status_text(root)
            if aktion == "wort":
                ctx.permissions.require(Risk.MODERATE, f"Neues Wachwort: {text[:60]}")
                e = W.speichern(root, wort=text)
                return f"Neues Wachwort: '{e['wort']}'."
            if aktion == "aus":
                ctx.permissions.require(Risk.MODERATE, "Wachwort-Lauscher ausschalten")
                W.ausschalten(root)
                return "Wachwort aus."
            if aktion == "an":
                if sys.platform != "win32":
                    return "Das Wachwort gibt es nur unter Windows."
                # Startet beim Anmelden mit -> wie jeder Autostart: immer ausdruecklich fragen.
                d = ctx.permissions.confirm_always("Wachwort-Lauscher einschalten: ein kleines Hintergrund-Skript "
                                                   "hoert aufs Wachwort und startet beim Anmelden mit (Eintrag "
                                                   "'Nova-Wachwort').")
                if not d.allowed:
                    raise PermissionError_(d.reason)
                if not W.erkenner():
                    return ("Keine Windows-Spracherkennung installiert: Einstellungen > Zeit und Sprache > Sprache > "
                            "Deutsch > Optionen > Spracherkennung hinzufuegen.")
                W.einschalten(root)
                return "Wachwort an. " + W.status_text(root)
        except W.WachwortFehler as exc:
            return f"Ging nicht: {exc}"
        return "Unbekannte Aktion."


def register(registry) -> None:
    registry.register(WachwortTool())
