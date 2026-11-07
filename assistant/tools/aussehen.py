"""Werkzeug: Nova passt das Aussehen der App an (nur Aussehen, kein Programm-Code)."""
from __future__ import annotations

from pathlib import Path

from .. import aussehen
from ..permissions import Risk
from .base import Tool, ToolContext


class AppAnpassenTool(Tool):
    name = "app_anpassen"
    description = (
        "Passt das Aussehen der App an die Wuensche deines Menschen an - Aenderungen erscheinen "
        "sofort im App-Fenster. aktion: 'anzeigen' (aktuellen Stand zeigen), 'setzen' (einfache "
        "Einstellungen: akzentfarbe als Hex wie #22c55e, schriftgroesse 80-140 Prozent, ecken "
        "eckig|normal|rund, dichte kompakt|normal|luftig, begruessung (Text auf dem Startbildschirm), "
        "beispiele (Beispiel-Fragen), avatar sphaere|buchstabe (dein Gesicht in der App: leuchtende "
        "Sphaere oder Buchstabe), sphaere_farbe als Hex (Farbe deiner Sphaere, sonst die Akzentfarbe), "
        "bewegung ruhig|normal|lebhaft (wie lebendig sich die Sphaere bewegt)), 'css_ersetzen' / 'css_anhaengen' (eigenes CSS; die App nutzt "
        "CSS-Variablen wie --accent, --bg, --surface, --text, --radius, --font-scale), 'zuruecksetzen' "
        "(Original-Aussehen). Leerer Wert bei 'setzen' = diese Einstellung zuruecksetzen."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "aktion": {"type": "string", "enum": ["anzeigen", "setzen", "css_ersetzen", "css_anhaengen",
                                                  "zuruecksetzen"]},
            "akzentfarbe": {"type": "string"},
            "schriftgroesse": {"type": "integer"},
            "ecken": {"type": "string"},
            "dichte": {"type": "string"},
            "begruessung": {"type": "string"},
            "beispiele": {"type": "array", "items": {"type": "string"}},
            "avatar": {"type": "string"},
            "sphaere_farbe": {"type": "string"},
            "bewegung": {"type": "string"},
            "css": {"type": "string"},
        },
        "required": ["aktion"],
    }

    def run(self, ctx: ToolContext, aktion: str, css: str = "", **settings) -> str:
        root = Path(ctx.extra.get("app_root") or ctx.permissions.app_root or ".")
        if aktion == "anzeigen":
            return aussehen.describe(root)
        ctx.permissions.require(Risk.MODERATE, f"Aussehen der App aendern ({aktion})")
        if aktion == "setzen":
            if not settings:
                return "Nichts angegeben - z.B. akzentfarbe='#22c55e' oder schriftgroesse=115."
            try:
                aussehen.save(root, settings)
            except (ValueError, TypeError) as exc:
                return f"Nicht geaendert: {exc}"
        elif aktion in ("css_ersetzen", "css_anhaengen"):
            aussehen.set_css(root, css, append=aktion == "css_anhaengen")
        elif aktion == "zuruecksetzen":
            aussehen.reset(root)
        else:
            return f"Unbekannte aktion '{aktion}'."
        notify = ctx.extra.get("on_appearance")
        if notify:
            notify()
            return "Erledigt - das App-Fenster zeigt es schon an.\n" + aussehen.describe(root)
        return "Gespeichert - sichtbar beim naechsten Start der App.\n" + aussehen.describe(root)


def register(registry) -> None:
    registry.register(AppAnpassenTool())
