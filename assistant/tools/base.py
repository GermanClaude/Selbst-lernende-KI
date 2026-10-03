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

from ..permissions import PermissionManager


@dataclass
class ToolContext:
    """Alles, was ein Werkzeug zur Laufzeit braucht."""

    permissions: PermissionManager
    memory: Any = None  # assistant.memory.Memory (vermeidet Zirkularimport)
    extra: dict[str, Any] = field(default_factory=dict)


class Tool:
    """Oberklasse fuer alle Werkzeuge."""

    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}

    def run(self, ctx: ToolContext, **kwargs: Any) -> str:  # pragma: no cover - abstrakt
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
        return [self._tools[n].spec() for n in sorted(self._tools)]

    def specs_openai(self) -> list[dict[str, Any]]:
        """Werkzeug-Definitionen im OpenAI-/DeepSeek-Format, stabile Reihenfolge."""
        return [self._tools[n].spec_openai() for n in sorted(self._tools)]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def execute(self, ctx: ToolContext, name: str, raw_input: Any) -> tuple[str, bool]:
        """Fuehrt ein Werkzeug aus. Gibt (ergebnis_text, is_error) zurueck."""
        tool = self.get(name)
        if tool is None:
            return (f"Unbekanntes Werkzeug: {name}", True)
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
            return (str(result), False)
        except TypeError as exc:
            return (f"Falsche Argumente fuer '{name}': {exc}", True)
        except Exception as exc:  # noqa: BLE001 - Fehler als Tool-Ergebnis zurueckgeben
            return (f"Fehler bei '{name}': {exc}", True)
