"""Abliteration AI als Gehirn - unzensiert, OpenAI-kompatibel (Chat Completions).

Wie DeepSeek/OpenAI (gleiche 'openai'-Bibliothek, gleiches Nachrichtenformat), nur:
  * Schluessel ABLITERATION_API_KEY (Prefix "ak_", von https://abliteration.ai), eigene Adresse
    https://api.abliteration.ai/v1.
  * Normales Chat-Completions-Modell OHNE Nachdenken (kein reasoning/thinking), mit 'max_tokens'
    und 'temperature'. Werkzeuge im OpenAI-Stil werden unterstuetzt.
  * Das angebotene Modell sieht keine Bilder.
"""
from __future__ import annotations

from typing import Any

from ..logging_setup import get_logger
from .base import CONNECT_TIMEOUT, READ_TIMEOUT
from .deepseek_provider import DeepSeekProvider

logger = get_logger()

_INSTALL_HINT = (
    "Fuer Abliteration AI fehlt die Bibliothek 'openai'. Installiere sie mit:\n"
    "    pip install openai\n"
    "und trage deinen ABLITERATION_API_KEY in die .env-Datei ein (Schluessel: https://abliteration.ai)."
)


class AbliterationProvider(DeepSeekProvider):
    name = "abliteration"
    label = "Abliteration AI"

    def _make_client(self) -> Any:
        try:
            from openai import OpenAI, Timeout
        except ImportError:
            return None
        key = self.config.abliteration_api_key
        if not key:
            return None
        return OpenAI(
            api_key=key,
            base_url=self.config.abliteration.base_url,
            timeout=Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            max_retries=3,
        )

    def _install_hint(self) -> str:
        return _INSTALL_HINT

    # -- Bilder ---------------------------------------------------------------
    def _sees_images(self) -> bool:
        from ..modelle import sieht_bilder

        return sieht_bilder("abliteration", self.config.abliteration.model)

    # -- kein Nachdenken ------------------------------------------------------
    def _think_level(self) -> str:
        return "aus"

    def _max_tokens(self, level: str) -> int:  # noqa: ARG002
        return max(int(self.config.abliteration.max_tokens or 0), 512)

    def _request_messages(self, thinking: bool) -> list[dict[str, Any]]:  # noqa: ARG002
        """Kein 'reasoning_content' (das ist DeepSeek) - beim Senden weglassen."""
        out = []
        for m in self.messages:
            if m.get("role") == "assistant" and "reasoning_content" in m:
                m = {k: v for k, v in m.items() if k != "reasoning_content"}
            out.append(m)
        return out

    def _turn_kwargs(self, level: str, tool_choice: str) -> dict[str, Any]:  # noqa: ARG002
        return {
            "model": self.config.abliteration.model,
            "messages": self._request_messages(False),
            "tools": self.registry.specs_openai(),
            "tool_choice": tool_choice,
            "max_tokens": self._max_tokens(level),
            "temperature": self.config.abliteration.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

    def _simple_kwargs(self, messages: list[dict[str, Any]], max_tokens: int) -> dict[str, Any]:
        return {"model": self.config.abliteration.model, "messages": messages,
                "max_tokens": max(max_tokens, 256), "stream": False,
                "temperature": self.config.abliteration.temperature}

    def _error_text(self, exc: Exception, stream: bool = False) -> str:
        from ..schluessel import friendly_error

        freundlich = friendly_error(exc, "abliteration")
        if freundlich:
            return f"\n[{freundlich}]"
        return super()._error_text(exc, stream)

    # -- Kosten ---------------------------------------------------------------
    def _track_usage(self, usage: Any, model: str | None = None) -> None:
        if not usage:
            return
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        details = getattr(usage, "prompt_tokens_details", None)
        cached = (getattr(details, "cached_tokens", 0) if details is not None else 0) or 0
        cached = min(int(cached), int(prompt))
        self._count(input_full=prompt - cached, cache_hit=cached,
                    output=getattr(usage, "completion_tokens", 0) or 0, model=model)
