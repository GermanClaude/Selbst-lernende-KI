"""Werkzeug fuer den AFK-Modus (siehe assistant/abwesend.py)."""
from __future__ import annotations

from ..abwesend import AfkSession
from ..permissions import Risk
from .base import Tool, ToolContext


class AbwesenheitTool(Tool):
    name = "abwesenheit"
    description = (
        "AFK-Modus: allein weiterarbeiten, waehrend dein Mensch weg ist. aktion 'start' NUR, wenn er sagt, "
        "dass er jetzt weg/AFK/laenger nicht da ist und du solange weitermachen sollst (auftrag = woran, "
        "falls genannt; minuten = wie lange, falls genannt) - der Modus beginnt nach deiner Antwort; sag ihm "
        "kurz, was du vorhast. Waehrend des AFK-Modus: 'notiz' (Zwischenergebnis), 'vorschlag' (etwas, das "
        "du nicht allein tun darfst - z.B. loeschen, ueberschreiben, ausfuehren, verschicken, kaufen), 'frage' "
        "(an ihn, wenn er zurueck ist), 'fertig' (alles Sinnvolle erledigt; text = kurze Zusammenfassung)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "aktion": {"type": "string", "enum": ["start", "notiz", "vorschlag", "frage", "fertig"]},
            "text": {"type": "string"},
            "auftrag": {"type": "string"},
            "minuten": {"type": "integer"},
        },
        "required": ["aktion"],
    }

    def run(self, ctx: ToolContext, aktion: str, text: str = "", auftrag: str = "", minuten: int = 0) -> str:
        session: AfkSession | None = ctx.extra.get("afk_session")
        active = session is not None and not session.ended
        if aktion == "start":
            if active:
                return "Der AFK-Modus laeuft schon."
            starter = ctx.extra.get("afk_start")
            if starter is None:
                return "Der AFK-Modus geht hier nicht."
            ctx.permissions.require(Risk.SAFE, "AFK-Modus vormerken")
            if starter(auftrag or text, minuten or None) is False:
                return ("Nicht vorgemerkt: Dein Mensch hat inzwischen schon weitergeschrieben - er ist also noch da. "
                        "Kuemmere dich um seine Nachricht; den AFK-Modus kann er jederzeit neu starten.")
            return ("Vorgemerkt: Nach dieser Antwort beginnt der AFK-Modus. Sag deinem Menschen kurz, woran du "
                    "arbeitest, dass du nichts loeschst, ausfuehrst oder verschickst (das schreibst du als "
                    "Vorschlag auf) und dass er mit einer Nachricht oder 'Ich bin zurueck' wieder uebernimmt.")
        if not active:
            return "Der AFK-Modus laeuft gerade nicht - sag es deinem Menschen einfach direkt."
        text = (text or "").strip()[:1500]
        if aktion == "fertig":
            session.done = text or "Erledigt."
            return "Gut - der AFK-Modus endet nach diesem Schritt."
        if not text:
            return "Bitte einen text angeben."
        target = {"notiz": session.notes, "vorschlag": session.proposals, "frage": session.questions}.get(aktion)
        if target is None:
            return f"Unbekannte aktion '{aktion}'."
        if len(target) >= 50:
            return "Die Liste ist voll - fasse lieber zusammen."
        target.append(text)
        update = ctx.extra.get("afk_update")
        if update:
            update()
        return {"notiz": "Notiert.", "vorschlag": "Vorschlag aufgeschrieben - er entscheidet, wenn er zurueck ist.",
                "frage": "Frage aufgeschrieben."}[aktion]


def register(registry) -> None:
    registry.register(AbwesenheitTool())
