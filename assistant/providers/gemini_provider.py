"""Google Gemini als Gehirn - ueber Googles OpenAI-kompatible Schnittstelle.

Fast alles wie bei DeepSeek (gleiche 'openai'-Bibliothek, gleiches Nachrichtenformat). Unterschiede:
  * Schluessel GEMINI_API_KEY (https://aistudio.google.com/apikey), eigene Adresse.
  * Nachdenken laesst sich bei Gemini 3/4 nicht abschalten - nur die Tiefe waehlen
    (reasoning_effort: low | medium | high). Der Denk-Text zaehlt bei max_tokens mit.
  * Werkzeug-Aufrufe tragen eine "Denk-Signatur" (tool_calls[].extra_content.google.thought_signature),
    die unveraendert zurueck muss - sonst lehnt Gemini die naechste Anfrage ab. Fehlt sie (z.B.
    nach einem Gehirnwechsel mitten im Gespraech), schicken wir Googles dokumentierten Platzhalter.
  * Alle aktuellen Modelle sehen Bilder.
"""
from __future__ import annotations

import copy
from typing import Any

from ..logging_setup import get_logger
from .base import CONNECT_TIMEOUT, READ_TIMEOUT
from .deepseek_provider import DeepSeekProvider

logger = get_logger()

_INSTALL_HINT = (
    "Fuer Gemini fehlt die Bibliothek 'openai'. Installiere sie mit:\n"
    "    pip install openai\n"
    "und trage deinen GEMINI_API_KEY in die .env-Datei ein (Schluessel: https://aistudio.google.com/apikey)."
)
# Von Google dokumentierter Platzhalter, wenn eine Denk-Signatur fehlt.
SIGNATUR_PLATZHALTER = "skip_thought_signature_validator"
# JSON-Schema-Angaben, die Gemini nicht in jeder Version annimmt - fuer Gemini weglassen.
_SCHEMA_WEG = ("additionalProperties", "strict", "$schema")


class GeminiProvider(DeepSeekProvider):
    name = "gemini"
    label = "Gemini"

    def _make_client(self) -> Any:
        try:
            from openai import OpenAI, Timeout
        except ImportError:
            return None
        key = self.config.gemini_api_key
        if not key:
            return None
        return OpenAI(
            api_key=key,
            base_url=self.config.gemini.base_url,
            timeout=Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            max_retries=3,
        )

    def _install_hint(self) -> str:
        return _INSTALL_HINT

    # -- Bilder ---------------------------------------------------------------
    def _sees_images(self) -> bool:
        from ..modelle import sieht_bilder

        return sieht_bilder("gemini", self.config.gemini.model)

    # -- Nachdenken -----------------------------------------------------------
    def _think_level(self) -> str:
        """low | medium | high. 'aus' nur, wenn Gemini die Denk-Angabe abgelehnt hat (dann ganz ohne)."""
        if self._thinking_off:
            return "aus"
        from ..modelle import gemini_denken

        return gemini_denken(self.config, self.effort_override)

    def _max_tokens(self, level: str) -> int:
        extra = {"medium": 24576, "high": 32768}.get(level, 0)
        return max(int(self.config.gemini.max_tokens or 0), extra)

    def _request_messages(self, thinking: bool) -> list[dict[str, Any]]:
        """Denk-Texte (reasoning_content, DeepSeek) nie mitschicken; jeder Werkzeug-Aufruf im
        Verlauf traegt eine Denk-Signatur (die echte - oder den Platzhalter)."""
        out = []
        for m in self.messages:
            if m.get("role") != "assistant":
                out.append(m)
                continue
            m = {k: v for k, v in m.items() if k != "reasoning_content"}
            if m.get("tool_calls"):
                m["tool_calls"] = [_mit_signatur(tc) for tc in m["tool_calls"]]
            out.append(m)
        return out

    def _werkzeuge(self) -> list[dict[str, Any]]:
        specs = copy.deepcopy(self.registry.specs_openai())
        for spec in specs:
            fn = spec.get("function", {})
            fn.pop("strict", None)
            if isinstance(fn.get("parameters"), dict):
                _schema_saeubern(fn["parameters"])
        return specs

    def _turn_kwargs(self, level: str, tool_choice: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.config.gemini.model,
            "messages": self._request_messages(True),
            "tools": self._werkzeuge(),
            "tool_choice": tool_choice,
            "max_tokens": self._max_tokens(level),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if level != "aus":
            kwargs["reasoning_effort"] = level
        return kwargs

    def _simple_kwargs(self, messages: list[dict[str, Any]], max_tokens: int) -> dict[str, Any]:
        """Kurzfrage/Zusammenfassung: wenig nachdenken, und Platz fuer den Denk-Text lassen."""
        return {"model": self.config.gemini.model, "messages": messages,
                "max_tokens": max(max_tokens, 4096) + 4096, "stream": False, "reasoning_effort": "low"}

    def _error_text(self, exc: Exception, stream: bool = False) -> str:
        from ..schluessel import friendly_error

        freundlich = friendly_error(exc, "gemini")
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


def _mit_signatur(tc: dict[str, Any]) -> dict[str, Any]:
    extra = tc.get("extra_content") or {}
    google = extra.get("google") if isinstance(extra, dict) else None
    if isinstance(google, dict) and google.get("thought_signature"):
        return tc
    return {**tc, "extra_content": {"google": {"thought_signature": SIGNATUR_PLATZHALTER}}}


def _schema_saeubern(schema: Any) -> None:
    """Entfernt Schema-Angaben, die Gemini ablehnen koennte (auch verschachtelt)."""
    if isinstance(schema, dict):
        for key in _SCHEMA_WEG:
            schema.pop(key, None)
        for value in schema.values():
            _schema_saeubern(value)
    elif isinstance(schema, list):
        for value in schema:
            _schema_saeubern(value)
