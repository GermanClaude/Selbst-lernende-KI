"""Gemeinsame Basis fuer alle Provider: Token-Zaehlung, Kosten, Werkzeug-Hilfen."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from ..config import Config
from ..tools import ToolContext, ToolRegistry

StreamFn = Callable[[str], None]


@dataclass
class Usage:
    """Verbrauchte Token - getrennt nach voll bezahltem Input, Cache-Treffern, Output."""

    input_full_tokens: int = 0  # Input ohne Cache-Treffer (voller Preis)
    cache_hit_tokens: int = 0   # aus dem Cache (sehr guenstig)
    output_tokens: int = 0

    def add(self, input_full: int = 0, cache_hit: int = 0, output: int = 0) -> None:
        self.input_full_tokens += max(0, input_full)
        self.cache_hit_tokens += max(0, cache_hit)
        self.output_tokens += max(0, output)

    @property
    def total_tokens(self) -> int:
        return self.input_full_tokens + self.cache_hit_tokens + self.output_tokens


class LLMProvider(ABC):
    """Oberklasse fuer ein 'Gehirn'. Jeder Provider verwaltet seinen eigenen Verlauf."""

    name: str = "unbekannt"

    def __init__(
        self,
        config: Config,
        system_prompt: str,
        registry: ToolRegistry,
        tool_ctx: ToolContext,
        client: Any = None,
    ):
        self.config = config
        self.system_prompt = system_prompt
        self.registry = registry
        self.tool_ctx = tool_ctx
        self.client = client
        self.usage = Usage()

    # -- von Unterklassen zu implementieren ---------------------------------
    @abstractmethod
    def respond(self, user_text: str, on_text: StreamFn | None = None, max_tool_rounds: int = 25) -> str: ...

    @abstractmethod
    def history_length(self) -> int: ...

    @abstractmethod
    def summarize_history(self) -> str: ...

    @abstractmethod
    def reset_to_summary(self, summary: str) -> None: ...

    # -- gemeinsam ----------------------------------------------------------
    def _exec_tool(self, name: str, tool_input: Any) -> tuple[str, bool]:
        """Fuehrt ein Werkzeug aus und kuerzt die Ausgabe im Sparmodus."""
        output, is_error = self.registry.execute(self.tool_ctx, name, tool_input)
        cap = self.config.economy.max_werkzeug_ausgabe if self.config.economy.aktiv else 0
        if cap and len(output) > cap:
            output = output[:cap] + "\n…(Ausgabe gekuerzt, um Token zu sparen)"
        return output, is_error

    def cost(self) -> tuple[float, float]:
        """Geschaetzte Kosten dieser Sitzung in (USD, EUR)."""
        return self.config.cost_estimate(
            self.usage.input_full_tokens, self.usage.cache_hit_tokens, self.usage.output_tokens
        )
