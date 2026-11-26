"""Premium anfragen: Der Nutzer stellt eine Anfrage ('ich moechte Premium Max fuer 30 Tage'), sie geht an den
Entwickler - per Gmail (derselbe Weg wie das Feedback) und/oder per Discord-Webhook. Der Entwickler erzeugt
dann im Codegenerator einen Code und schickt ihn zurueck.

WICHTIG: Hier wird KEIN echtes Geld bewegt. Ein Betrag ist nur eine SIMULATION zum Testen des Ablaufs - es
werden keine Zahlungsdaten erhoben und nichts abgebucht. Mitgeschickt wird nur: Stufe, Laufzeit, der
simulierte Betrag, eine optionale Notiz und die anonyme Geraete-Kennung (damit der Entwickler den Code dafuer
erzeugen kann). Keine sonstigen persoenlichen Daten.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

STUFEN = {"premium": "Premium", "max": "Premium Max", "dev": "Entwickler"}


def discord_webhook() -> str:
    url = (os.environ.get("NOVA_DISCORD_WEBHOOK") or "").strip()
    return url if url.startswith("https://discord.com/api/webhooks/") or \
        url.startswith("https://discordapp.com/api/webhooks/") else ""


def _discord_senden(url: str, text: str) -> bool:
    body = json.dumps({"content": text[:1900], "username": "Nova Premium"}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300
    except Exception:  # noqa: BLE001
        return False


def _text(stufe: str, tage: int, betrag: float, notiz: str, kennung: str) -> str:
    name = STUFEN.get(stufe, stufe)
    zeilen = [
        "Neue Premium-Anfrage (Ablauf-Test, KEIN echtes Geld):",
        f"  Stufe:        {name}",
        f"  Laufzeit:     {tage} Tage",
        f"  Betrag:       {betrag:.2f} EUR (SIMULATION - nichts abgebucht)",
        f"  Kennung:      {kennung}",
    ]
    if notiz.strip():
        zeilen.append(f"  Notiz:        {notiz.strip()[:400]}")
    zeilen.append("")
    zeilen.append(f"Code erzeugen: Codegenerator -> Kennung {kennung}, Stufe {name}, Laufzeit {tage} Tage.")
    return "\n".join(zeilen)


def senden(config, stufe: str, tage: int, betrag: float, notiz: str, kennung: str, post=None) -> dict:
    """Schickt die Anfrage an den Entwickler (Gmail + Discord). Gibt {ok, wege, meldung} zurueck."""
    stufe = stufe if stufe in STUFEN else "premium"
    tage = max(1, min(int(tage or 1), 3660))
    try:
        betrag = max(0.0, min(float(betrag or 0), 100000))
    except (TypeError, ValueError):
        betrag = 0.0
    text = _text(stufe, tage, betrag, str(notiz or ""), str(kennung or "?"))
    wege = []

    dc = discord_webhook()
    if dc and _discord_senden(dc, "**" + text.replace("\n", "\n> ").replace("  ", " ") + "**"):
        wege.append("Discord")

    try:
        from . import feedback

        payload = feedback.baue_payload("idee", None, "[PREMIUM-ANFRAGE]\n" + text, "", [], "menue", config)
        ergebnis = feedback.senden(payload, feedback.ziel_url(config), post, root=config)
        if getattr(ergebnis, "status", "") == "gesendet":
            wege.append("E-Mail")
        elif getattr(ergebnis, "ok", False):
            wege.append("E-Mail (folgt)")
    except Exception:  # noqa: BLE001
        pass

    if wege:
        return {"ok": True, "wege": wege,
                "meldung": "Deine Anfrage ist raus (" + ", ".join(wege) + "). Sobald sie bearbeitet ist, "
                           "bekommst du einen Code, den du hier mit /novaaiupdate einloest."}
    return {"ok": False, "wege": [],
            "meldung": "Die Anfrage konnte gerade nicht gesendet werden (kein Netz oder kein Kanal eingerichtet). "
                       "Bitte spaeter nochmal."}
