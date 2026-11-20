"""Werkzeug: Nova stellt ihre eigene Stimme um (kostenlos oder realistisch)."""
from __future__ import annotations

from ..permissions import Risk
from .base import Tool, ToolContext


class StimmeTool(Tool):
    name = "stimme_waehlen"
    description = (
        "Stellt ein, mit welcher Stimme DU (die KI) sprichst bzw. vorliest. Nur umstellen, wenn dein "
        "Mensch ausdruecklich darum bittet (z.B. 'nimm eine echtere Stimme', 'sprich mit deiner "
        "normalen Stimme'). stimme: 'frei' (kostenlose Computerstimme, offline, ohne Konto), 'openai' "
        "(realistisch, nutzt denselben Schluessel wie das ChatGPT-Gehirn - guenstig) oder 'elevenlabs' "
        "(am natuerlichsten, braucht ein eigenes, kostenloses ElevenLabs-Konto, kostet pro Zeichen). "
        "name (optional): bestimmte Stimme beim Anbieter, bei OpenAI z.B. 'cedar', 'marin', 'nova', "
        "'coral'. Fehlt der noetige Schluessel, sag es deinem Menschen - trag ihn nie selbst ein."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "stimme": {"type": "string", "enum": ["frei", "openai", "elevenlabs"]},
            "name": {"type": "string"},
        },
        "required": ["stimme"],
    }

    def run(self, ctx: ToolContext, stimme: str, name: str = "") -> str:
        setter = ctx.extra.get("set_stimme")
        if not setter:
            return "Die Stimme laesst sich hier gerade nicht umstellen."
        ctx.permissions.require(Risk.MODERATE, f"Stimme umstellen auf {stimme}")
        try:
            result = setter(stimme, name)
        except ValueError as exc:
            return str(exc)
        info = result["info"]
        if result["fehlt_schluessel"]:
            if result["stimme"] == "openai":
                return ("Auf die OpenAI-Stimme umgestellt - aber der ChatGPT-Schluessel fehlt noch. "
                        "Bitte deinen Menschen, ihn einzutragen (/schluessel sk-proj-…).")
            return ("Auf ElevenLabs umgestellt - aber der ElevenLabs-Schluessel fehlt noch. Bitte deinen "
                    "Menschen, ihn einzutragen: /stimme schluessel <KEY> (kostenlos auf elevenlabs.io).")
        return f"Stimme ist jetzt: {info['name']}. Ab dem naechsten Vorlesen hoerst du sie."


def register(registry) -> None:
    registry.register(StimmeTool())
