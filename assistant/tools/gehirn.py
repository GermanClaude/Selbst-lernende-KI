"""Werkzeug: Modell und Denk-Tiefe auf Wunsch umstellen ("denk schneller", "nimm Sonnet")."""
from __future__ import annotations

from .. import modelle
from ..permissions import Risk
from .base import Tool, ToolContext


class GehirnEinstellenTool(Tool):
    name = "gehirn_einstellen"
    description = (
        "Zeigt oder aendert, welches Modell du nutzt und wie gruendlich du nachdenkst - NUR auf "
        "ausdruecklichen Wunsch deines Menschen (z.B. 'denk schneller', 'antworte schneller', 'nimm "
        "Sonnet', 'denk gruendlicher'). aktion: 'anzeigen' oder 'setzen'. modell: bei Claude opus | "
        "sonnet | haiku | fable, bei DeepSeek flash | pro. denken: schnell | ausgewogen | gruendlich | "
        "sehr gruendlich | maximal. Gilt ab deiner naechsten Antwort, das Gespraech bleibt erhalten. "
        "Mehr Denk-Tiefe = bessere Antworten bei schweren Aufgaben, aber laengeres Warten und hoehere "
        "Kosten. Zwischen Claude und DeepSeek wechselt dein Mensch selbst (in der App unter Gehirn)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "aktion": {"type": "string", "enum": ["anzeigen", "setzen"]},
            "modell": {"type": "string"},
            "denken": {"type": "string"},
        },
        "required": ["aktion"],
    }

    def run(self, ctx: ToolContext, aktion: str, modell: str = "", denken: str = "") -> str:
        config = ctx.extra.get("config")
        if config is None:
            return "Hier nicht moeglich (keine Einstellungen verfuegbar)."
        provider = config.active_provider
        if aktion == "anzeigen":
            info = modelle.beschreibung(config)[provider]
            models = "; ".join(f"{m['name']} ({m['info']})" for m in info["modelle"])
            levels = ", ".join(d["name"] for d in info["denktiefen"])
            return (f"Jetzt: {modelle.kurzbeschreibung(config)}. Modelle: {models}. "
                    f"Denk-Tiefen: {levels}.")
        if aktion != "setzen":
            return f"Unbekannte aktion '{aktion}'."
        if not (modell or denken):
            return "Nichts angegeben - z.B. denken='schnell' oder modell='sonnet'."
        # Teure Wahl (staerkstes Modell / maximale Tiefe) nur mit Zustimmung
        wanted_model = modelle._finde_modell(provider, modell) if modell else None
        wanted_level = modelle.finde_denktiefe(provider, denken) if denken else None
        if wanted_model == "claude-fable-5-1" or wanted_level == "max":
            ctx.permissions.require(Risk.MODERATE, "Teureres Denken einstellen "
                                    f"({modell or ''} {denken or ''})".replace("  ", " "))
        result = modelle.waehle(config, provider, model=modell or None, denken=denken or None)
        if not result["ok"]:
            return "Nicht geaendert: " + result["message"]
        notify = ctx.extra.get("on_model")
        if notify:
            notify()
        return "Eingestellt: " + result["message"]


def register(registry) -> None:
    registry.register(GehirnEinstellenTool())
