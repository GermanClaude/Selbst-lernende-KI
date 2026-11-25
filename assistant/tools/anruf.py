"""Werkzeug: Nova ruft ihren Menschen an (Bland AI oder Vonage) - nur die hinterlegte eigene Nummer."""
from __future__ import annotations

import os

from .. import anruf as anruf_mod
from .. import anruf_vonage as vonage_mod
from ..permissions import Risk
from .base import Tool, ToolContext


def einstellungen(root=None) -> dict:
    """Aus der .env (bzw. der Umgebung): Anbieter, Schluessel, Nummer, Hoechstdauer, Stimme."""
    try:
        minuten = int(os.environ.get("ANRUF_MAX_MINUTEN", "") or anruf_mod.STANDARD_MINUTEN)
    except ValueError:
        minuten = anruf_mod.STANDARD_MINUTEN
    key = os.environ.get("BLAND_API_KEY", "").strip()
    vonage = vonage_mod.eingerichtet(root)
    wahl = os.environ.get("ANRUF_ANBIETER", "").strip().lower()
    if wahl not in ("bland", "vonage"):
        wahl = "vonage" if vonage and not key else "bland"
    return {"anbieter": wahl, "key": key, "vonage": vonage,
            "bereit": vonage if wahl == "vonage" else bool(key),
            "nummer": anruf_mod.normalisiere_nummer(os.environ.get("ANRUF_NUMMER", "")) or "",
            "minuten": max(1, min(minuten, 15)),
            "stimme": os.environ.get("BLAND_STIMME", "").strip()}


def vonage_anrufen(root, nummer: str, anliegen: str, name: str, minuten: int, warten: bool = True,
                   gezaehlt=None) -> str:
    """Ein Vonage-Anruf: mit Rueckkanal (Frage + Antwort) wenn moeglich, sonst als Ansage."""
    try:
        pem = vonage_mod.schluessel_pfad(root).read_text(encoding="utf-8")
    except OSError:
        return "Anruf ging nicht: der Vonage-Schluessel fehlt (/anruf vonage <Application-ID> <Pfad zur private.key>)."
    v = vonage_mod.Vonage(os.environ.get("VONAGE_APP_ID", "").strip(), pem, os.environ.get("VONAGE_NUMMER", ""))
    kanal = vonage_mod.rueckkanal_oeffnen(anliegen, root) if warten else None
    try:
        ncco = vonage_mod.ncco_bauen(anliegen, name, kanal.url("antwort") if kanal else None)
        try:
            call_id = v.anrufen(nummer, ncco, minuten, kanal.url("event") if kanal else None)
        except anruf_mod.AnrufFehler as exc:
            return f"Anruf ging nicht: {exc}"
        if gezaehlt:
            gezaehlt()
        if not warten:
            return f"Anruf gestartet ({anruf_mod.maskiere(nummer)}, Ansage, ID {call_id})."
        info = vonage_mod.warte_auf_ende(v, call_id, max_sekunden=minuten * 60 + 90)
        return vonage_mod.ergebnis_text(info, kanal)
    finally:
        if kanal is not None:
            kanal.stoppen()


class AnrufTool(Tool):
    name = "anrufen"
    description = (
        "Ruft DEINEN MENSCHEN auf seinem Handy an (echter Telefonanruf, deutsche Stimme). Es gibt nur seine "
        "eigene, hinterlegte Nummer - niemand anderen. Nutze das nur, wenn es wirklich wichtig ist oder er es "
        "so wollte: du brauchst dringend eine Entscheidung/Antwort, etwas Wichtiges ist fertig oder "
        "schiefgegangen, oder er hat gesagt 'ruf mich an, wenn ...'. Fuer Kleinigkeiten lieber eine Nachricht. "
        "Kostet Geld pro Minute, hoechstens wenige Anrufe am Tag. 'anliegen': was du ihm sagen bzw. ihn fragen "
        "willst (konkret, kurz, als ganzer Satz - bei Vonage wird es genau so vorgelesen). 'warten' (Standard: "
        "ja): bis zum Ende warten und seine Antwort bekommen."
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
        root = ctx.extra.get("app_root")
        e = einstellungen(root)
        if not e["bereit"] or not e["nummer"]:
            return ("Anrufen ist noch nicht eingerichtet. Dein Mensch braucht Bland AI (/anruf schluessel <KEY>) "
                    "oder Vonage (/anruf vonage <Application-ID> <Pfad zur private.key>) und muss seine Nummer "
                    "hinterlegen: /anruf nummer <Nummer>. /anruf zeigt die Schritte.")
        if not (anliegen or "").strip():
            return "Ohne Anliegen rufe ich nicht an - sag, was du ihm sagen oder fragen willst."
        if root is not None and anruf_mod.heute_anzahl(root) >= anruf_mod.MAX_PRO_TAG:
            return (f"Heute schon {anruf_mod.MAX_PRO_TAG} Anrufe - mehr nicht (Kostenbremse). Schreib ihm lieber "
                    "eine Nachricht oder notiere es.")
        # Am PC: wie andere Aktionen nachfragen. Im AFK-Modus nicht - dafuer ist es ja da (nur seine Nummer).
        if not ctx.permissions.away:
            ctx.permissions.require(Risk.MODERATE, f"Dich anrufen ({anruf_mod.maskiere(e['nummer'])}): "
                                                   f"{anliegen.strip()[:160]}")
        name = ctx.extra.get("ki_name", lambda: "Nova")()
        if e["anbieter"] == "vonage":
            return vonage_anrufen(root, e["nummer"], anliegen, name, e["minuten"], warten,
                                  gezaehlt=(lambda: anruf_mod.heute_zaehlen(root)) if root is not None else None)
        bland = anruf_mod.Bland(e["key"])
        try:
            call_id = bland.anrufen(e["nummer"], anliegen, name, e["minuten"], e["stimme"],
                                    anruf_mod.persona_text(root))
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
