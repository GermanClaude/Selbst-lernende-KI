"""Werkzeug: Nova malt ein Bild aus einer Beschreibung (kostenlos, ueber AI Horde oder Cloudflare).

Das Bild landet als neue Datei im Arbeitsordner (bilder/...). Der Pfad wird wie bei den anderen
Datei-Werkzeugen ueber den PermissionManager geprueft. Die Beschreibung verlaesst dabei den PC
(fremder Dienst) - deshalb im AFK-Modus nie, und sonst nur mit Freigabe (MODERATE).
Das Modell bekommt nur einen kurzen Text zurueck (kein Base64); die App zeigt das Bild selbst an.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .. import bildgenerator
from ..permissions import Risk
from .base import Tool, ToolContext

_AFK_TEXT = (
    "Bilder erstelle ich nur, wenn dein Mensch da ist - die Beschreibung geht dabei an einen fremden "
    "Dienst. Schreib den Bildwunsch als Vorschlag auf (Werkzeug abwesenheit, aktion 'vorschlag'), "
    "dann kann er es spaeter selbst anstossen."
)


def _sicher(fn: Callable | None) -> Callable | None:
    """Rueckruf der Oberflaeche, der nie das Werkzeug stoeren darf."""
    if not callable(fn):
        return None

    def aufruf(*args: Any) -> None:
        try:
            fn(*args)
        except Exception:  # noqa: BLE001 - Anzeige-Fehler sind egal
            pass

    return aufruf


def _freier_stamm(ordner: Path, stamm: str) -> str:
    """Dateiname (ohne Endung), den es im Ordner noch mit keiner Endung gibt."""
    kandidat, nummer = stamm, 2
    while ordner.is_dir() and any(ordner.glob(f"{kandidat}.*")):
        kandidat = f"{stamm}-{nummer}"
        nummer += 1
    return kandidat


class BildErstellenTool(Tool):
    name = "bild_erstellen"
    description = (
        "Malt ein NEUES Bild aus einer Beschreibung (kostenlos ueber AI Horde, oder Cloudflare, wenn "
        "eingerichtet) und speichert es im Arbeitsordner unter bilder/. Nur nutzen, wenn dein Mensch "
        "ein Bild moechte. 'beschreibung': eine ausfuehrliche Bildbeschreibung AUF ENGLISCH (Motiv, "
        "Stil, Farben, Licht, Perspektive, Stimmung) - englisch klappt viel besser. Keine echten "
        "Personen ohne deren Einwilligung, keine Gewalt, keine Erwachsenen-Inhalte, keine "
        "persoenlichen Daten (Namen, Adressen) - die Beschreibung geht an einen fremden Dienst. "
        "'format': quadrat (Standard), hoch oder quer. Dauert meist zehn Sekunden bis wenige "
        "Minuten. Die App zeigt das fertige Bild selbst an - nicht als Link oder Base64 einbetten."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "beschreibung": {
                "type": "string",
                "description": "Ausfuehrliche Bildbeschreibung auf Englisch (z.B. 'a cozy cabin in a snowy "
                               "forest at dusk, warm light in the windows, watercolor style').",
            },
            "format": {
                "type": "string",
                "enum": ["quadrat", "hoch", "quer"],
                "description": "Bildformat: quadrat (1:1, Standard), hoch (Hochformat) oder quer (Querformat).",
            },
        },
        "required": ["beschreibung"],
    }

    def run(self, ctx: ToolContext, beschreibung: str, format: str = "quadrat") -> str:  # noqa: A002
        permissions = ctx.permissions
        if getattr(permissions, "away", False):
            return _AFK_TEXT
        prompt = bildgenerator.bereinige(beschreibung)
        if not prompt:
            return "Bitte beschreibe das Bild (am besten ausfuehrlich auf Englisch)."
        fmt = bildgenerator.format_name(format)
        if fmt is None:
            return f"Unbekanntes format '{format}' - erlaubt sind quadrat, hoch oder quer."
        config = ctx.extra.get("config")
        dienste = bildgenerator.empfaenger(config)
        anbieter = dienste[0] + (f" (falls das nicht klappt: {', '.join(dienste[1:])})" if dienste[1:] else "")

        # Pfad VOR dem Malen pruefen und freigeben lassen: die Beschreibung verlaesst sonst
        # schon den PC, bevor der Mensch nein sagen konnte. Die Endung kommt erst mit dem Bild.
        ordner = bildgenerator.bilder_ordner(permissions.workspace_root)
        stamm = _freier_stamm(ordner, bildgenerator.dateistamm(prompt))
        vorab = permissions.resolve_path(f"{bildgenerator.ORDNER}/{stamm}.png")
        decision = permissions.check_path_write(vorab)
        if not decision.allowed:
            return f"Nicht ausgefuehrt: {decision.reason}"
        kurz = prompt if len(prompt) <= 300 else prompt[:300] + "..."
        permissions.require(
            Risk.MODERATE,
            f"Bild erstellen ueber {anbieter} (die Beschreibung wird dorthin geschickt): \"{kurz}\"\n"
            f"    Datei: {vorab.with_suffix('')}.*",
        )

        try:
            ergebnis = bildgenerator.erstellen(
                prompt, fmt, config=config,
                fortschritt=_sicher(ctx.extra.get("on_image_progress")),
                cancel_event=ctx.extra.get("cancel_event"),
            )
        except bildgenerator.GeneratorFehler as exc:
            return f"Kein Bild erstellt: {exc}"

        # Endgueltige Datei: gleicher Ordner und Name, Endung vom echten Bildtyp (webp/jpg/png).
        stamm = _freier_stamm(vorab.parent, stamm)
        ziel = permissions.resolve_path(f"{bildgenerator.ORDNER}/{stamm}.{ergebnis.endung}")
        if ziel.parent != vorab.parent:  # pragma: no cover - Sandbox hat sich mittendrin geaendert
            return "Nicht ausgefuehrt: Der Bilder-Ordner hat sich geaendert."
        ziel.parent.mkdir(parents=True, exist_ok=True)
        teil = ziel.with_name(ziel.name + ".teil")
        teil.write_bytes(ergebnis.data)
        teil.replace(ziel)  # nie eine halbe Datei unter dem richtigen Namen

        on_image = _sicher(ctx.extra.get("on_image"))
        if on_image:
            on_image({"pfad": ziel, "name": ziel.name, "prompt": prompt, "anbieter": ergebnis.anbieter})

        text = f"Bild gespeichert: {bildgenerator.ORDNER}/{ziel.name} ({ergebnis.anbieter}, Modell {ergebnis.modell})."
        if ergebnis.hinweis:
            text += f"\nHinweis: {ergebnis.hinweis}"
        if on_image:
            text += "\nDie App zeigt das Bild schon an - nicht einbetten, kein Link noetig."
        else:
            text += f"\nVoller Pfad: {ziel}"
        return text


def register(registry) -> None:
    registry.register(BildErstellenTool())
