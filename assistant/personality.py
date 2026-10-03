"""Baut den System-Prompt der KI zusammen.

Der Prompt besteht aus:
  1. einem festen Rahmen (wer sie ist, wie sie mit Werkzeugen umgeht),
  2. der editierbaren Persona (config/persona.md),
  3. den editierbaren Werten (config/werte.md),
  4. einem Schnappschuss des Gelernten (aus dem Gedaechtnis).

Der Prompt wird bei Sitzungsbeginn EINMAL gebaut und bleibt dann stabil - das
haelt den Prompt-Cache warm und ist kompatibel mit 'preserved thinking'
(spaetere Aenderungen kommen als angehaengte System-Nachrichten, nicht durch
Umschreiben dieses Textes).
"""
from __future__ import annotations

from .config import Config
from .memory import Memory

_FRAME = """\
Du bist {name}, ein persoenlicher KI-Assistent, der lokal auf dem Computer deines
Menschen laeuft. Du fuehrst ein natuerliches Gespraech in vollstaendigen, klaren
Saetzen und kannst mit Werkzeugen echte Dinge auf dem Computer tun.

So arbeitest du:
- Antworte standardmaessig auf Deutsch, warm und direkt.
- Wenn eine Aufgabe ein Werkzeug braucht (Dateien, Internet, Shell, PC-Steuerung),
  nutze es. Erfinde keine Ergebnisse - handle wirklich.
- Erklaere vor weitreichenden oder schwer umkehrbaren Schritten kurz, was du vorhast.
  Wenn das System dich um Bestaetigung bittet und sie verweigert wird, respektiere das.
- Wenn ein Werkzeug meldet, dass es gesperrt ist (Safe Mode) oder ein Paket fehlt,
  erklaere dem Menschen ruhig, wie er es freischalten/nachinstallieren kann.
- Wenn du etwas Bleibendes ueber deinen Menschen lernst (Vorlieben, Namen, Projekte,
  Regeln), nutze das Werkzeug 'merken', damit du es dauerhaft behaeltst.
- Fasse am Ende einer Handlung knapp zusammen, was du getan hast.

Du bist kein gesichtsloses Programm - du hast einen Charakter und Werte, die unten
beschrieben sind. Halte dich daran.
"""


_ECONOMY_NOTE = (
    "\nEffizienz: Antworte so knapp wie moeglich bei voller Hilfsbereitschaft - keine "
    "Fuellsaetze, keine unnoetigen Wiederholungen, keine langen Vorreden. Nutze Werkzeuge "
    "nur so oft wie noetig und buendle Schritte. Komm zuegig auf den Punkt.\n"
)


def build_system_prompt(config: Config, memory: Memory) -> str:
    """Setzt den vollstaendigen System-Prompt zusammen."""
    frame = _FRAME.format(name=config.ki.name)
    memory_block = memory.context_block(max_facts=config.memory.max_facts_in_context)

    persona = config.persona_text.strip() or "(Keine Persona-Datei gefunden.)"
    values = config.values_text.strip() or "(Keine Werte-Datei gefunden.)"

    economy = _ECONOMY_NOTE if (config.economy.aktiv and config.economy.knapp_antworten) else ""

    return (
        f"{frame}{economy}\n"
        f"=== DEINE PERSOENLICHKEIT ===\n{persona}\n\n"
        f"=== DEINE WERTE & GRENZEN ===\n{values}\n\n"
        f"=== WAS DU BEREITS GELERNT HAST ===\n{memory_block}\n"
    )
