"""OpenAI / ChatGPT als Gehirn - ueber die offizielle OpenAI-Schnittstelle (Chat Completions).

Fast alles wie bei DeepSeek (gleiche 'openai'-Bibliothek, gleiches Nachrichtenformat). Unterschiede:
  * Schluessel OPENAI_API_KEY (https://platform.openai.com/api-keys), eigene Adresse.
  * Die aktuellen Modelle sind "Denk-Modelle": sie brauchen 'max_completion_tokens' statt
    'max_tokens' und vertragen keine 'temperature'. Die Denk-Tiefe stellt man ueber
    'reasoning_effort' (none | minimal | low | medium | high) - der Denk-Text zaehlt bei der
    Laengengrenze mit.
  * Werkzeuge: Die neuesten Flaggschiffe (gpt-6.2-astra ...) nutzen Werkzeuge nur ueber die
    Responses-API, die Nova nicht verwendet - darum sind sie nicht waehlbar. gpt-6-sol/luna
    nutzen Werkzeuge nur ohne Nachdenken (dann reasoning_effort = "none"); gpt-5.2 kann beides.
  * Alle angebotenen Modelle sehen Bilder.
"""
from __future__ import annotations

from typing import Any

from ..logging_setup import get_logger
from .base import CONNECT_TIMEOUT, READ_TIMEOUT
from .deepseek_provider import DeepSeekProvider

logger = get_logger()

_INSTALL_HINT = (
    "Fuer ChatGPT (OpenAI) fehlt die Bibliothek 'openai'. Installiere sie mit:\n"
    "    pip install openai\n"
    "und trage deinen OPENAI_API_KEY in die .env-Datei ein (Schluessel: https://platform.openai.com/api-keys)."
)


class OpenAIProvider(DeepSeekProvider):
    name = "openai"
    label = "ChatGPT (OpenAI)"

    def _make_client(self) -> Any:
        try:
            from openai import OpenAI, Timeout
        except ImportError:
            return None
        key = self.config.openai_api_key
        if not key:
            return None
        return OpenAI(
            api_key=key,
            base_url=self.config.openai.base_url,
            timeout=Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            max_retries=3,
        )

    def _install_hint(self) -> str:
        return _INSTALL_HINT

    # -- Bilder ---------------------------------------------------------------
    def _sees_images(self) -> bool:
        from ..modelle import sieht_bilder

        return sieht_bilder("openai", self.config.openai.model)

    # -- Nachdenken -----------------------------------------------------------
    def _think_level(self) -> str:
        """aus | low | medium | high. 'aus' auch, wenn das Modell die Denk-Angabe abgelehnt hat."""
        if self._thinking_off:
            return "aus"
        from ..modelle import openai_denken

        return openai_denken(self.config, self.effort_override)

    def _reasoning_effort(self, level: str) -> str | None:
        """Was als 'reasoning_effort' gesendet wird (None = ganz weglassen)."""
        from ..modelle import openai_kann_denken

        if not openai_kann_denken(self.config.openai.model):
            return "none"  # gpt-6-sol/luna: Werkzeuge gehen nur ohne Nachdenken
        if self._thinking_off:
            return None  # Modell hat die Denk-Angabe abgelehnt -> dem Modell seine Vorgabe lassen
        return {"aus": "minimal", "low": "low", "medium": "medium", "high": "high"}.get(level, "low")

    def _max_tokens(self, level: str) -> int:
        # Der Denk-Text zaehlt mit - genug Platz lassen, sonst kommt eine leere Antwort.
        base = max(int(self.config.openai.max_tokens or 0), 8192)
        return base + {"low": 8192, "medium": 16384, "high": 24576}.get(level, 4096)

    def _request_messages(self, thinking: bool) -> list[dict[str, Any]]:
        """OpenAI nutzt kein 'reasoning_content' (das ist DeepSeek) - beim Senden weglassen."""
        out = []
        for m in self.messages:
            if m.get("role") == "assistant" and "reasoning_content" in m:
                m = {k: v for k, v in m.items() if k != "reasoning_content"}
            out.append(m)
        return out

    def _turn_kwargs(self, level: str, tool_choice: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.config.openai.model,
            "messages": self._request_messages(True),
            "tools": self.registry.specs_openai(),
            "tool_choice": tool_choice,
            "max_completion_tokens": self._max_tokens(level),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        effort = self._reasoning_effort(level)
        if effort is not None:
            kwargs["reasoning_effort"] = effort
        return kwargs

    def _simple_kwargs(self, messages: list[dict[str, Any]], max_tokens: int) -> dict[str, Any]:
        """Kurzfrage/Zusammenfassung: wenig nachdenken, Platz fuer den Denk-Text lassen."""
        from ..modelle import openai_kann_denken

        return {"model": self.config.openai.model, "messages": messages,
                "max_completion_tokens": max(max_tokens, 4096) + 8192, "stream": False,
                "reasoning_effort": "none" if not openai_kann_denken(self.config.openai.model) else "minimal"}

    def _error_text(self, exc: Exception, stream: bool = False) -> str:
        from ..schluessel import friendly_error

        freundlich = friendly_error(exc, "openai")
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
