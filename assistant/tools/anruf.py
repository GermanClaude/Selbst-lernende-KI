"""Werkzeuge rund ums Telefon:
- 'anrufen': Nova ruft ihren Menschen an (Bland AI oder Vonage) - nur die hinterlegte eigene Nummer.
- 'telefon_waehlen': oeffnet den Dialer mit einer beliebigen Nummer - waehlt aber NIE selbst (der Mensch
  drueckt auf Anrufen). So kann Nova beim Anrufen Dritter helfen, ohne je von sich aus zu telefonieren."""
from __future__ import annotations

import os
import re

from .. import anruf as anruf_mod
from .. import anruf_vonage as vonage_mod
from ..permissions import Risk
from .base import Tool, ToolContext


def dialer_nummer(text: str) -> str | None:
    """Rufnummer fuer den Dialer: erst sauber als E.164 (normalisiere_nummer), sonst nur +, Ziffern, * und #
    behalten (z.B. Sonder-/Kurznummern). None, wenn zu wenig Ziffern uebrig bleiben."""
    n = anruf_mod.normalisiere_nummer(text)
    if n:
        return n
    roh = re.sub(r"[^+0-9*#]", "", str(text or ""))
    return roh if len(re.sub(r"\D", "", roh)) >= 3 else None


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
    pem = vonage_mod.schluessel_text(root)
    if not pem:
        return ("Anruf ging nicht: der Vonage-Schluessel fehlt (/anruf vonage <Application-ID> <Pfad zur "
                "private.key>, in der Cloud: VONAGE_PRIVATE_KEY).")
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
        "ja): bis zum Ende warten und seine Antwort bekommen. 'gespraech' (nur Vonage): ein echtes Telefonat - "
        "er sagt dir am Telefon, was du tun sollst, du erledigst es mit deinen Werkzeugen und antwortest im selben "
        "Anruf, hin und her bis 'tschuess'. Nimm das, wenn er mit dir telefonieren will ('ruf mich an', "
        "'lass uns telefonieren')."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "anliegen": {"type": "string", "description": "Was du sagen/fragen willst."},
            "warten": {"type": "boolean", "description": "Bis zum Ende warten und die Antwort holen."},
            "gespraech": {"type": "boolean", "description": "Telefonat mit Auftraegen hin und her (Vonage)."},
        },
        "required": ["anliegen"],
    }

    def run(self, ctx: ToolContext, anliegen: str, warten: bool = True, gespraech: bool = False) -> str:
        root = ctx.extra.get("app_root")
        from .. import codewort
        if not codewort.frei(root):
            return codewort.SPERR_HINWEIS
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
        starter = ctx.extra.get("anruf_gespraech")
        if gespraech and e["anbieter"] == "vonage" and starter is not None:
            return starter(anliegen)
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


class WaehlenTool(Tool):
    name = "telefon_waehlen"
    description = (
        "Oeffnet auf dem Geraet (PC oder Handy) den Telefon-Dialer mit einer Nummer schon EINGETRAGEN - "
        "waehlt aber NICHT selbst. Dein Mensch drueckt am Ende selbst auf Anrufen; Nova startet nie von "
        "allein einen Anruf. Nimm das, wenn er jemand ANDEREN anrufen moechte und du ihm das Tippen abnehmen "
        "sollst: eine Firma, einen Arzt, einen Handwerker, einen Kontakt, eine Nummer von einer Webseite. "
        "Unterschied zu 'anrufen': 'anrufen' ruft NUR seine eigene hinterlegte Nummer per KI-Stimme an - "
        "'telefon_waehlen' bereitet einen Anruf an eine beliebige Nummer vor, den er selbst ausloest. "
        "'nummer': die Rufnummer. 'wer': optional, wem sie gehoert (nur zur Anzeige)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "nummer": {"type": "string", "description": "Rufnummer, z.B. +49 30 1234567 oder 0171 2345678."},
            "wer": {"type": "string", "description": "Optional: wem die Nummer gehoert (nur zur Anzeige)."},
        },
        "required": ["nummer"],
    }

    def run(self, ctx: ToolContext, nummer: str, wer: str = "") -> str:
        from .. import codewort
        if not codewort.frei(ctx.extra.get("app_root")):
            return codewort.SPERR_HINWEIS
        n = dialer_nummer(nummer)
        if not n:
            return "Das sieht nicht nach einer Rufnummer aus - gib sie mir nochmal (z.B. +49 30 1234567)."
        wer = (wer or "").strip()[:60]
        wofuer = f"{wer} ({n})" if wer else n
        # Nur der Dialer wird geoeffnet (kein Anruf) - am PC trotzdem kurz nachfragen, im AFK nicht.
        if not ctx.permissions.away:
            ctx.permissions.require(Risk.MODERATE, f"Telefon-Dialer oeffnen mit {wofuer} - anrufen musst du selbst.")
        oeffnen = ctx.extra.get("dialer_oeffnen")
        if oeffnen is None:
            return f"Ich kann den Dialer hier nicht oeffnen. Die Nummer zum Anrufen: {n}" + (f" ({wer})" if wer else "")
        try:
            hinweis = oeffnen(n, wer)
        except Exception as exc:  # noqa: BLE001
            return f"Der Dialer liess sich nicht oeffnen ({exc}). Die Nummer: {n}"
        return hinweis or (f"\U0001F4DE Dialer geoeffnet mit {n}{(' - ' + wer) if wer else ''}. "
                           "Druecke selbst auf Anrufen - ich waehle nie von allein.")


def register(registry) -> None:
    registry.register(AnrufTool())
    registry.register(WaehlenTool())
