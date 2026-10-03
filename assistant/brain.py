"""Das "Gehirn": orchestriert den aktiven Provider (Claude oder DeepSeek).

Brain ist bewusst schlank. Die eigentliche Modell-Kommunikation und der
Werkzeug-Loop liegen im jeweiligen Provider (assistant/providers/). Brain kuemmert
sich um den System-Prompt, die Kompaktierung langer Verlaeufe und das Speichern
von Episoden ins Gedaechtnis.
"""
from __future__ import annotations

from typing import Any, Callable

from .config import Config
from .logging_setup import get_logger
from .memory import Memory
from .personality import build_system_prompt
from .providers import LLMProvider, Usage, build_provider
from .tools import ToolContext, ToolRegistry

logger = get_logger()

StreamFn = Callable[[str], None]


class Brain:
    def __init__(
        self,
        config: Config,
        memory: Memory,
        registry: ToolRegistry,
        tool_ctx: ToolContext,
        provider: LLMProvider | None = None,
        client: Any = None,
    ):
        self.config = config
        self.memory = memory
        self.system_prompt = build_system_prompt(config, memory)
        self.provider = provider or build_provider(
            config, self.system_prompt, registry, tool_ctx, client=client
        )

    @property
    def usage(self) -> Usage:
        return self.provider.usage

    def cost(self) -> tuple[float, float]:
        return self.provider.cost()

    def respond(self, user_text: str, on_text: StreamFn | None = None) -> str:
        answer = self.provider.respond(user_text, on_text=on_text)
        self._maybe_compact()
        return answer

    def _maybe_compact(self) -> None:
        if self.provider.history_length() < self.config.compact_threshold:
            return
        logger.info("Kompaktiere Verlauf (%d Nachrichten).", self.provider.history_length())
        summary = self.provider.summarize_history()
        if summary:
            self.memory.add_episode(summary)
            self.provider.reset_to_summary(summary)

    def end_session_summary(self) -> None:
        if self.provider.history_length() < 2:
            return
        summary = self.provider.summarize_history()
        if summary:
            self.memory.add_episode(summary)
