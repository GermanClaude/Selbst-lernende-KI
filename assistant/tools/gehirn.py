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
        "sonnet | haiku | fable, bei DeepSeek flash | pro, bei Gemini flash | lite | hydrogen | argon | carbon, bei Ollama ein heruntergeladenes Modell (z.B. "
        "qwen3.5:4b). denken: schnell | ausgewogen | gruendlich | sehr gruendlich | maximal. Gilt ab deiner "
        "naechsten Antwort, das Gespraech bleibt erhalten. Mehr Denk-Tiefe = bessere Antworten bei schweren "
        "Aufgaben, aber laengeres Warten und hoehere Kosten. Zwischen Claude, DeepSeek, Gemini und Ollama (kostenlos, "
        "auf dem PC) wechselt dein Mensch selbst: in der App unter 'Gehirn & Schluessel' oder mit /gehirn "
        "ollama (bzw. /gehirn claude, /gehirn deepseek, /gehirn gemini) - sag ihm das, wenn er wechseln moechte. Neue "
        "Ollama-Modelle laedt er mit /ollama laden <modell>."
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
        if aktion == "anzeigen" and provider == "ollama":
            from .. import ollama

            info = ollama.status(config)
            da = ", ".join(m["name"] for m in info["modelle"]) or "noch keins"
            return (f"Jetzt: {modelle.kurzbeschreibung(config)} (Ollama, kostenlos auf dem PC, "
                    f"{'laeuft' if info['laeuft'] else 'laeuft gerade nicht'}). Heruntergeladen: {da}. "
                    "Empfohlen: " + "; ".join(f"{m['id']} ({m['info']}, {m['groesse']})" for m in ollama.EMPFOHLEN)
                    + ". Denk-Tiefen: schnell, gruendlich.")
        if aktion == "anzeigen":
            info = modelle.beschreibung(config)[provider]
            models = "; ".join(f"{m['name']} ({m['info']})" for m in info["modelle"])
            levels = ", ".join(d["name"] for d in info["denktiefen"])
            return (f"Jetzt: {modelle.kurzbeschreibung(config)}. Modelle: {models}. "
                    f"Denk-Tiefen: {levels}.")
        if aktion != "setzen":
            return f"Unbekannte aktion '{aktion}'."
        if getattr(ctx.permissions, "away", False):
            return "Nicht, solange dein Mensch weg ist (AFK-Modus) - das entscheidet er selbst."
        if not (modell or denken):
            return "Nichts angegeben - z.B. denken='schnell' oder modell='sonnet'."
        # Teure Wahl (staerkstes Modell / maximale Tiefe) nur mit Zustimmung
        wanted_model = modelle._finde_modell(provider, modell) if modell else None
        wanted_level = modelle.finde_denktiefe(provider, denken) if denken else None
        if provider == "ollama" and wanted_model:
            from .. import ollama

            info = ollama.status(config)
            if info["laeuft"] and not ollama.ist_installiert(wanted_model, [m["name"] for m in info["modelle"]]):
                return (f"Nicht geaendert: {wanted_model} ist noch nicht heruntergeladen. Dein Mensch kann es "
                        f"mit /ollama laden {wanted_model} holen (oder in der App unter Gehirn & Schluessel).")
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
