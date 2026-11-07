"""Agenten: die KI gibt klar umrissene Teilaufgaben an einen Helfer mit frischem Kopf.

Ein Agent ist eine zweite KI-Sitzung mit eigenem (leerem) Verlauf, eigenen
Werkzeugen und einem Auftrag. Er arbeitet selbststaendig und gibt nur sein
Ergebnis zurueck - so bleibt das Gedaechtnis der Haupt-KI frei, auch wenn der
Agent hundert Seiten liest. Rollen:

  recherche - Internet/Dateien durchsuchen und zusammenfassen (aendert nichts)
  helfer    - eine Teilaufgabe selbst erledigen (z.B. ein Modul schreiben)
  pruefer   - Arbeit kritisch pruefen: Fehler, Luecken, falsche Behauptungen

Alle Berechtigungen und Rueckfragen gelten fuer Agenten genauso.
"""
from __future__ import annotations

from .base import Tool, ToolContext

ROLES = ("recherche", "helfer", "pruefer")


class AgentTool(Tool):
    name = "agent_beauftragen"
    description = (
        "Startet einen eigenstaendigen Agenten mit frischem Kopf fuer eine klar umrissene "
        "Teilaufgabe und gibt dessen Ergebnisbericht zurueck. Rollen: 'recherche' (Internet "
        "oder Dateien durchsuchen und zusammenfassen, aendert nichts), 'helfer' (eine "
        "Teilaufgabe selbst erledigen, z.B. eine Datei oder ein Modul schreiben), 'pruefer' "
        "(deine Arbeit kritisch pruefen: Fehler, Luecken, falsche Behauptungen; aendert "
        "nichts). Der Agent kennt das Gespraech NICHT - schreib alles Noetige in den Auftrag "
        "(Ziel, Pfade, Vorgaben, was zurueckkommen soll). Nutze ihn fuer grosse, gut "
        "abgrenzbare Teilaufgaben und um wichtige Ergebnisse vor dem Abschluss pruefen zu "
        "lassen - nicht fuer Kleinigkeiten."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "rolle": {"type": "string", "enum": list(ROLES), "description": "recherche | helfer | pruefer"},
            "auftrag": {"type": "string", "description": "Was genau zu tun ist und was zurueckkommen soll"},
            "kontext": {
                "type": "string",
                "description": "Optional: Hintergrund, relevante Pfade, bisherige Ergebnisse",
            },
        },
        "required": ["rolle", "auftrag"],
    }
    # Der Bericht ist schon verdichtet - der Sparmodus soll ihn nicht abschneiden.
    sparmodus_kuerzen = False

    def run(self, ctx: ToolContext, rolle: str, auftrag: str, kontext: str = "") -> str:
        runner = ctx.extra.get("agent_runner")
        if runner is None:
            return "Agenten sind hier nicht verfuegbar - erledige die Aufgabe selbst."
        if rolle not in ROLES:
            return f"Unbekannte Rolle '{rolle}'. Moeglich: {', '.join(ROLES)}."
        return runner(rolle, auftrag, kontext)


def register(registry) -> None:
    registry.register(AgentTool())
