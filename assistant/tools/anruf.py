"""Werkzeug: Nova ruft ihren Menschen an (Bland AI) - nur die hinterlegte eigene Nummer."""
from __future__ import annotations

import os

from .. import anruf as anruf_mod
from ..permissions import Risk
from .base import Tool, ToolContext


def einstellungen() -> dict:
    """Aus der .env (bzw. der Umgebung): Schluessel, Nummer, Hoechstdauer, Stimme."""
    try:
        minuten = int(os.environ.get("ANRUF_MAX_MINUTEN", "") or anruf_mod.STANDARD_MINUTEN)
    except ValueError:
        minuten = anruf_mod.STANDARD_MINUTEN
    return {"key": os.environ.get("BLAND_API_KEY", "").strip(),
            "nummer": anruf_mod.normalisiere_nummer(os.environ.get("ANRUF_NUMMER", "")) or "",
            "minuten": max(1, min(minuten, 15)),
            "stimme": os.environ.get("BLAND_STIMME", "").strip()}


class AnrufTool(Tool):
    name = "anrufen"
    description = (
        "Ruft DEINEN MENSCHEN auf seinem Handy an (echter Telefonanruf ueber Bland AI, eine KI-Stimme "
        "spricht Deutsch). Es gibt nur seine eigene, hinterlegte Nummer - niemand anderen. Nutze das nur, "
        "wenn es wirklich wichtig ist oder er es so wollte: du brauchst dringend eine Entscheidung/Antwort, "
        "etwas Wichtiges ist fertig oder schiefgegangen, oder er hat gesagt 'ruf mich an, wenn ...'. Fuer "
        "Kleinigkeiten lieber eine Nachricht. Kostet Geld pro Minute, hoechstens wenige Anrufe am Tag. "
        "'anliegen': was du ihm sagen bzw. ihn fragen willst (konkret, kurz). 'warten' (Standard: ja): bis "
        "zum Ende warten und die Mitschrift bekommen - so erfaehrst du seine Antwort."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "anliegen": {"type": "string", "description": "Was du sagen/fragen willst."},
            "warten": {"type": "boolean", "description": "Bis zum Ende warten und die Antwort holen."},
        },
        "required": ["anliegen"],
    }

    def run(self, ctx: ToolContext, anliegen: str, warten: bool = True) -> str:
        e = einstellungen()
        if not e["key"] or not e["nummer"]:
            return ("Anrufen ist noch nicht eingerichtet. Dein Mensch braucht einen Bland-AI-Schluessel und muss "
                    "seine Nummer hinterlegen: /anruf schluessel <KEY> und /anruf nummer <Nummer>.")
        if not (anliegen or "").strip():
            return "Ohne Anliegen rufe ich nicht an - sag, was du ihm sagen oder fragen willst."
        root = ctx.extra.get("app_root")
        if root is not None and anruf_mod.heute_anzahl(root) >= anruf_mod.MAX_PRO_TAG:
            return (f"Heute schon {anruf_mod.MAX_PRO_TAG} Anrufe - mehr nicht (Kostenbremse). Schreib ihm lieber "
                    "eine Nachricht oder notiere es.")
        # Am PC: wie andere Aktionen nachfragen. Im AFK-Modus nicht - dafuer ist es ja da (nur seine Nummer).
        if not ctx.permissions.away:
            ctx.permissions.require(Risk.MODERATE, f"Dich anrufen ({anruf_mod.maskiere(e['nummer'])}): "
                                                   f"{anliegen.strip()[:160]}")
        name = ctx.extra.get("ki_name", lambda: "Nova")()
        bland = anruf_mod.Bland(e["key"])
        try:
            call_id = bland.anrufen(e["nummer"], anliegen, name, e["minuten"], e["stimme"])
        except anruf_mod.AnrufFehler as exc:
            return f"Anruf ging nicht: {exc}"
        if root is not None:
            anruf_mod.heute_zaehlen(root)
        if not warten:
            return f"Anruf gestartet ({anruf_mod.maskiere(e['nummer'])}, ID {call_id})."
        info = anruf_mod.warte_auf_ende(bland, call_id, max_sekunden=e["minuten"] * 60 + 120)
        return anruf_mod.ergebnis_text(info) if info else f"Anruf gestartet (ID {call_id}), Ergebnis noch offen."


def register(registry) -> None:
    registry.register(AnrufTool())
