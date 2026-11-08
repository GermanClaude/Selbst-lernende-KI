"""Basisklasse und Registry fuer Werkzeuge.

Jedes Werkzeug beschreibt sich selbst (Name, Beschreibung, JSON-Schema) und
fuehrt eine Aktion aus. Das Schema wird unveraendert an das Claude-Modell
uebergeben; die Reihenfolge der Werkzeuge bleibt stabil (wichtig fuer den
Prompt-Cache und 'preserved thinking').
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..bilder import Bild, platzhalter_text
from ..permissions import PermissionManager


@dataclass
class ToolContext:
    """Alles, was ein Werkzeug zur Laufzeit braucht."""

    permissions: PermissionManager
    memory: Any = None  # assistant.memory.Memory (vermeidet Zirkularimport)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolOutput:
    """Werkzeug-Ergebnis mit Bildern (z.B. Bildschirmfoto), damit die KI sie wirklich sieht.

    Die Provider machen daraus ihr eigenes Format (Claude: Bild-Bloecke im tool_result,
    DeepSeek: Text + Bilder in einer Nachricht danach). Gekuerzt wird nur `text` - nie die
    Bilddaten. Werkzeuge ohne Bilder geben weiter einfach einen String zurueck.
    """

    text: str
    bilder: list[Bild] = field(default_factory=list)

    def __str__(self) -> str:
        # Fuer alle, die nur Text verstehen (Logs, Anzeige): Text + "[Bild: name]".
        hinweis = platzhalter_text(self.bilder)
        return f"{self.text} {hinweis}".strip() if hinweis else self.text


class Tool:
    """Oberklasse fuer alle Werkzeuge."""

    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}

    def run(self, ctx: ToolContext, **kwargs: Any) -> str | ToolOutput:  # pragma: no cover - abstrakt
        raise NotImplementedError

    def spec(self) -> dict[str, Any]:
        """Anthropic-Format (mit strict tool use)."""
        schema = dict(self.input_schema)
        schema.setdefault("additionalProperties", False)
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema,
            "strict": True,
        }

    def spec_openai(self) -> dict[str, Any]:
        """OpenAI-/DeepSeek-Format (function calling)."""
        schema = dict(self.input_schema)
        schema.setdefault("additionalProperties", False)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }


MAX_STRIKT = 20  # Grenze der Claude-API fuer Werkzeuge mit "strict": true
# Werkzeuge mit sehr einfachen Eingaben - die brauchen "strict" am wenigsten.
OHNE_STRIKT_ZUERST = ("system_info", "live_sehen", "bildschirmfoto", "app_anpassen", "erinnern",
                      "vergessen", "ordner_auflisten", "tastenkombination")


class ToolRegistry:
    """Haelt alle aktiven Werkzeuge in stabiler Reihenfolge."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError("Werkzeug ohne Namen kann nicht registriert werden.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict[str, Any]]:
        # Nach Namen sortiert -> stabile, cache-freundliche Reihenfolge.
        specs = [self._tools[n].spec() for n in sorted(self._tools)]
        # Claude erlaubt hoechstens MAX_STRIKT "strict"-Werkzeuge pro Anfrage (sonst Fehler 400
        # fuer JEDE Antwort). Darueber verlieren zuerst die einfachsten Werkzeuge das "strict"
        # (feste Reihenfolge -> Anfragen bleiben gleich, Prompt-Cache bleibt gueltig).
        zuviel = sum(1 for sp in specs if sp.get("strict")) - MAX_STRIKT
        if zuviel > 0:
            reihenfolge = [n for n in OHNE_STRIKT_ZUERST if n in self._tools]
            reihenfolge += [n for n in sorted(self._tools, reverse=True) if n not in reihenfolge]
            weg = set(reihenfolge[:zuviel])
            for sp in specs:
                if sp["name"] in weg:
                    sp.pop("strict", None)
        return specs

    def specs_openai(self) -> list[dict[str, Any]]:
        """Werkzeug-Definitionen im OpenAI-/DeepSeek-Format, stabile Reihenfolge."""
        return [self._tools[n].spec_openai() for n in sorted(self._tools)]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def execute(self, ctx: ToolContext, name: str, raw_input: Any) -> tuple[str | ToolOutput, bool]:
        """Fuehrt ein Werkzeug aus. Gibt (ergebnis, is_error) zurueck - ergebnis ist ein Text
        oder (bei Werkzeugen mit Bildern) ein ToolOutput, der unveraendert durchgereicht wird."""
        tool = self.get(name)
        if tool is None:
            return (f"Unbekanntes Werkzeug: {name}", True)
        erlaubt = ctx.extra.get("nur_diese_werkzeuge")
        if erlaubt is not None and name not in erlaubt:
            # Wortmeldung von Live-Sehen: nur lesen (Bildschirminhalt koennte Anweisungen enthalten)
            return ("Das geht in einer Wortmeldung von Live-Sehen nicht - hier darfst du nur lesen. Schlag es "
                    "deinem Menschen in Worten vor.", True)
        # Eingabe ist bereits ein dict (vom SDK geparst); defensiv absichern.
        if isinstance(raw_input, str):
            try:
                raw_input = json.loads(raw_input)
            except json.JSONDecodeError:
                return ("Konnte die Werkzeug-Eingabe nicht als JSON lesen.", True)
        if not isinstance(raw_input, dict):
            return ("Werkzeug-Eingabe muss ein Objekt sein.", True)
        try:
            result = tool.run(ctx, **raw_input)
            if isinstance(result, ToolOutput):
                return (result, False)
            return (str(result), False)
        except TypeError as exc:
            return (f"Falsche Argumente fuer '{name}': {exc}", True)
        except Exception as exc:  # noqa: BLE001 - Fehler als Tool-Ergebnis zurueckgeben
            return (f"Fehler bei '{name}': {exc}", True)
