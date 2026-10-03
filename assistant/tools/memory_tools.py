"""Gedaechtnis-Werkzeuge: die KI merkt sich Dinge selbst und ruft sie ab.

Damit lernt die KI aktiv waehrend des Gespraechs - sie entscheidet, was
wichtig genug ist, um es dauerhaft zu behalten.
"""
from __future__ import annotations

from ..permissions import Risk
from .base import Tool, ToolContext


class RememberTool(Tool):
    name = "merken"
    description = (
        "Speichert dauerhaft einen Fakt oder eine Vorliebe ueber den Nutzer, "
        "damit du dich in spaeteren Sitzungen daran erinnerst. Nutze dies, wann "
        "immer du etwas Bleibendes ueber den Menschen lernst."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "inhalt": {"type": "string", "description": "Was gemerkt werden soll"},
            "kategorie": {
                "type": "string",
                "description": "z.B. vorliebe, person, projekt, regel, technik",
            },
            "wichtigkeit": {
                "type": "integer",
                "description": "1 (nebensaechlich) bis 5 (sehr wichtig)",
            },
        },
        "required": ["inhalt"],
    }

    def run(self, ctx: ToolContext, inhalt: str, kategorie: str = "allgemein", wichtigkeit: int = 3) -> str:
        ctx.permissions.require(Risk.SAFE, "Etwas ins Gedaechtnis schreiben")
        if ctx.memory is None:
            return "Kein Gedaechtnis verfuegbar."
        fact_id = ctx.memory.remember(inhalt, category=kategorie, importance=wichtigkeit)
        return f"Gemerkt (#{fact_id}, {kategorie}): {inhalt}"


class RecallTool(Tool):
    name = "erinnern"
    description = "Durchsucht dein Gedaechtnis nach einem Stichwort und gibt passende Eintraege zurueck."
    input_schema = {
        "type": "object",
        "properties": {"stichwort": {"type": "string"}},
        "required": ["stichwort"],
    }

    def run(self, ctx: ToolContext, stichwort: str) -> str:
        ctx.permissions.require(Risk.SAFE, "Im Gedaechtnis suchen")
        if ctx.memory is None:
            return "Kein Gedaechtnis verfuegbar."
        facts = ctx.memory.search(stichwort)
        if not facts:
            return f"Nichts zu '{stichwort}' gefunden."
        return "\n".join(f"#{f.id} [{f.category}] {f.content}" for f in facts)


class ForgetTool(Tool):
    name = "vergessen"
    description = "Loescht einen gemerkten Eintrag anhand seiner ID (z.B. wenn er falsch oder veraltet ist)."
    input_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    }

    def run(self, ctx: ToolContext, id: int) -> str:  # noqa: A002 - bewusst 'id'
        ctx.permissions.require(Risk.SAFE, "Aus dem Gedaechtnis loeschen")
        if ctx.memory is None:
            return "Kein Gedaechtnis verfuegbar."
        return "Vergessen." if ctx.memory.forget(int(id)) else "Keinen Eintrag mit dieser ID gefunden."


def register(registry) -> None:
    for tool in (RememberTool(), RecallTool(), ForgetTool()):
        registry.register(tool)
