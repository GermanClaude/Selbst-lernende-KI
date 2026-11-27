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
        "sofort im App-Fenster. Alles bleibt bei Updates erhalten (ein Update aendert das Design nie). "
        "aktion: 'anzeigen' (aktuellen Stand zeigen), 'vorlage' (fertige Design-Vorlage - vorlage: "
        "hacker | mitternacht | dracula | retro | pastell | sonne, oder 'aus' = wieder Standard; "
        "setzt den ganzen Look inkl. Farben um), 'hintergrund' (ein Hintergrundbild setzen - "
        "datei = Pfad zu einem Bild PNG/JPG/WebP/GIF, z.B. ein selbst erzeugtes Bild aus bilder/; "
        "deckkraft 0..0.9 = wie stark das Bild abgedunkelt wird, damit Text lesbar bleibt), "
        "'hintergrund_aus' (Hintergrundbild entfernen), 'setzen' (einfache Einstellungen: akzentfarbe "
        "als Hex wie #22c55e, schriftgroesse 80-140 Prozent, ecken eckig|normal|rund, dichte "
        "kompakt|normal|luftig, begruessung (Text auf dem Startbildschirm), beispiele (Beispiel-Fragen), "
        "avatar sphaere|buchstabe (dein Gesicht in der App), sphaere_farbe als Hex, bewegung "
        "ruhig|normal|lebhaft, stil cockpit|neon|einfach|klassisch = der ganze Stil der App: cockpit = "
        "serioes mit Systemstatus, neon = dunkel/cool mit Leuchten, einfach = ganz reduziert, klassisch = "
        "Chat-Blasen), 'css_ersetzen' / 'css_anhaengen' (eigenes CSS fuer alles, was die "
        "Vorlagen nicht abdecken; die App nutzt CSS-Variablen wie --accent, --bg, --surface, --text, "
        "--radius, --font-scale), 'zuruecksetzen' (Original-Aussehen, loescht auch Hintergrundbild). "
        "Leerer Wert bei 'setzen' = diese Einstellung zuruecksetzen."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "aktion": {"type": "string", "enum": ["anzeigen", "vorlage", "hintergrund", "hintergrund_aus",
                                                  "setzen", "css_ersetzen", "css_anhaengen", "zuruecksetzen"]},
            "vorlage": {"type": "string"},
            "datei": {"type": "string"},
            "deckkraft": {"type": "number"},
            "akzentfarbe": {"type": "string"},
            "schriftgroesse": {"type": "integer"},
            "ecken": {"type": "string"},
            "dichte": {"type": "string"},
            "begruessung": {"type": "string"},
            "beispiele": {"type": "array", "items": {"type": "string"}},
            "avatar": {"type": "string"},
            "sphaere_farbe": {"type": "string"},
            "bewegung": {"type": "string"},
            "stil": {"type": "string", "enum": ["cockpit", "neon", "einfach", "klassisch"]},
            "css": {"type": "string"},
        },
        "required": ["aktion"],
    }

    def run(self, ctx: ToolContext, aktion: str, css: str = "", vorlage: str = "", datei: str = "",
            deckkraft: float = 0.35, **settings) -> str:
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
        elif aktion == "vorlage":
            try:
                aussehen.set_thema(root, vorlage)
            except ValueError as exc:
                return f"Nicht geaendert: {exc}"
        elif aktion == "hintergrund":
            fehler = self._set_hintergrund(ctx, root, datei, deckkraft)
            if fehler:
                return fehler
        elif aktion == "hintergrund_aus":
            aussehen.clear_hintergrund(root)
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

    def _set_hintergrund(self, ctx: ToolContext, root: Path, datei: str, deckkraft: float) -> str:
        """Liest das Bild und setzt es als Hintergrund. Gibt "" zurueck (ok) oder eine Fehlermeldung."""
        if not str(datei).strip():
            return "Fuer 'hintergrund' brauche ich 'datei' - den Pfad zu einem Bild."
        p = Path(str(datei)).expanduser()
        if not p.is_absolute():
            base = getattr(ctx.permissions, "workspace_root", None)
            p = (Path(base) / p) if base else p
        try:
            daten = p.read_bytes()
        except OSError:
            return f"Das Bild finde ich nicht: {datei}"
        try:
            aussehen.set_hintergrund(root, daten, p.suffix, deckkraft)
        except ValueError as exc:
            return f"Nicht geaendert: {exc}"
        return ""


def register(registry) -> None:
    registry.register(AppAnpassenTool())
