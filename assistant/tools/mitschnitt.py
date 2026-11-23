"""Werkzeug: Nova startet/stoppt den Mitschnitt (lokale Transkription), wenn der Mensch darum bittet."""
from __future__ import annotations

from ..permissions import Risk
from .base import Tool, ToolContext


class TranskriptTool(Tool):
    name = "transkription"
    description = (
        "Schneidet Ton mit und transkribiert ihn LOKAL (kostet keine Token), bis dein Mensch stoppt. "
        "Nur auf ausdruecklichen Wunsch starten. aktion: 'start' (quelle: 'system' = alles, was der PC "
        "ausgibt - Spiele, Calls, Videos; oder 'mikrofon'), 'stop', 'status'. Hinweis dem Menschen, "
        "dass das Mitschneiden von Gespraechen mit anderen deren Zustimmung brauchen kann. Mehrere "
        "Sprecher auseinanderzuhalten geht nur mit Zusatzmodell; sonst wird ohne Sprecher-Aufteilung "
        "transkribiert. Das fertige Transkript liegt als Datei im Arbeitsordner (mitschnitte/)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "aktion": {"type": "string", "enum": ["start", "stop", "status"]},
            "quelle": {"type": "string", "enum": ["system", "mikrofon"]},
        },
        "required": ["aktion"],
    }

    def run(self, ctx: ToolContext, aktion: str, quelle: str = "system") -> str:
        start = ctx.extra.get("mitschnitt_start")
        stop = ctx.extra.get("mitschnitt_stop")
        status = ctx.extra.get("mitschnitt_status")
        if not (start and stop and status):
            return "Der Mitschnitt laesst sich hier gerade nicht steuern."
        if aktion == "status":
            st = status()
            if not st.get("laeuft"):
                return "Es laeuft gerade kein Mitschnitt."
            return (f"Mitschnitt laeuft ({st.get('quelle')}, {st.get('minuten',0)} Min., "
                    f"{st.get('segmente',0)} Abschnitte). Datei: {st.get('datei','')}")
        if aktion == "stop":
            r = stop()
            if not r.get("ok"):
                return r.get("error", "Es laeuft kein Mitschnitt.")
            return (f"Mitschnitt gestoppt ({r.get('segmente',0)} Abschnitte, {r.get('minuten',0)} Min.). "
                    f"Transkript: {r.get('datei','')}")
        # start
        ctx.permissions.require(Risk.MODERATE, "Ton mitschneiden und transkribieren")
        r = start("mikrofon" if quelle == "mikrofon" else "system")
        if not r.get("ok"):
            return r.get("error", "Mitschnitt nicht gestartet.")
        return (f"Mitschnitt laeuft ({r.get('quelle')}), ich transkribiere lokal mit bis du 'stopp' sagst. "
                f"Datei: {r.get('datei','')}. {r.get('hinweis','')}")


def register(registry) -> None:
    registry.register(TranskriptTool())
