"""Claude (Anthropic) als Gehirn - adaptives Thinking, Werkzeuge, append-only Verlauf."""
from __future__ import annotations

from typing import Any

from ..logging_setup import get_logger
from .base import (
    LIMIT_NOTE,
    SUMMARY_INSTRUCTION,
    TRUNCATED_NOTE,
    TRUNCATED_TOOL_ERROR,
    LLMProvider,
    StreamFn,
)

logger = get_logger()


class AnthropicProvider(LLMProvider):
    name = "claude"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.messages: list[dict[str, Any]] = []
        if self.client is None:
            self.client = self._make_client()

    def _make_client(self) -> Any:
        import anthropic

        key = self.config.anthropic_api_key
        return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()

    # -- Request ------------------------------------------------------------
    def _stream_kwargs(self) -> dict[str, Any]:
        return {
            "model": self.config.claude.model,
            "max_tokens": self.config.claude.max_tokens,
            "system": self.system_prompt,
            "messages": self.messages,
            "tools": self.registry.specs(),
            "tool_choice": {"type": "auto"},
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.config.claude.effort},
            # Automatisches Prompt-Caching: der wachsende Verlauf wird bei jedem
            # Werkzeug-Schritt erneut gesendet - aus dem Cache kostet er ~10 %.
            "extra_body": {"cache_control": {"type": "ephemeral"}},
        }

    def _open_stream(self, kwargs: dict[str, Any]):
        if self.config.claude.server_side_fallback:
            kwargs = dict(kwargs)
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
            return self.client.beta.messages.stream(**kwargs)
        return self.client.messages.stream(**kwargs)

    # -- Hauptschleife ------------------------------------------------------
    def respond(
        self, user_text: str, on_text: StreamFn | None = None, max_tool_rounds: int | None = None
    ) -> str:
        self.messages.append({"role": "user", "content": user_text})
        final_parts: list[str] = []
        rounds = self._rounds(max_tool_rounds)

        for _ in range(rounds):
            response = self._one_turn(on_text)
            if response is None:
                return "Es gab ein Problem bei der Verbindung zum Modell."

            self._track_usage(getattr(response, "usage", None))

            if getattr(response, "stop_reason", None) == "refusal":
                detail = ""
                if getattr(response, "stop_details", None):
                    detail = f" (Kategorie: {getattr(response.stop_details, 'category', '?')})"
                self.messages.append({"role": "assistant", "content": response.content})
                msg = "Das tut mir leid - diese Anfrage kann ich nicht erfuellen" + detail + "."
                if on_text:
                    on_text(msg)
                return msg

            self.messages.append({"role": "assistant", "content": response.content})
            text_this_turn = "".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            )
            if text_this_turn:
                final_parts.append(text_this_turn)

            stop_reason = getattr(response, "stop_reason", None)
            if stop_reason == "pause_turn":
                continue

            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            if not tool_uses:
                if stop_reason == "max_tokens":
                    final_parts.append(TRUNCATED_NOTE.strip())
                    if on_text:
                        on_text(TRUNCATED_NOTE)
                break

            # Bei max_tokens ist der letzte Werkzeugaufruf abgeschnitten -> nicht ausfuehren.
            truncated = stop_reason == "max_tokens"
            tool_results = []
            for i, block in enumerate(tool_uses):
                if truncated and i == len(tool_uses) - 1:
                    output, is_error = TRUNCATED_TOOL_ERROR, True
                else:
                    if on_text:
                        on_text(f"\n  … nutze Werkzeug: {block.name}\n")
                    output, is_error = self._exec_tool(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                        "is_error": is_error,
                    }
                )
            self.messages.append({"role": "user", "content": tool_results})
        else:
            # Schritt-Limit erreicht: Bescheid geben statt stumm aufzuhoeren.
            note = LIMIT_NOTE.format(n=rounds)
            final_parts.append(note.strip())
            if on_text:
                on_text(note)

        return "\n".join(final_parts).strip() or "(keine Textantwort)"

    def _one_turn(self, on_text: StreamFn | None):
        import anthropic

        try:
            with self._open_stream(self._stream_kwargs()) as stream:
                for event in stream:
                    if getattr(event, "type", None) == "text" and on_text:
                        on_text(event.text)
                return stream.get_final_message()
        except anthropic.APIStatusError as exc:
            logger.error("API-Fehler: %s", exc)
            if on_text:
                on_text(f"\n[Fehler vom Modell: {getattr(exc, 'message', exc)}]")
            return None
        except anthropic.APIConnectionError:
            logger.error("Verbindungsfehler zum Modell.")
            if on_text:
                on_text("\n[Keine Verbindung zum Modell - Internet/Schluessel pruefen.]")
            return None

    def _track_usage(self, usage: Any) -> None:
        if not usage:
            return
        input_full = getattr(usage, "input_tokens", 0) or 0
        input_full += getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_hit = getattr(usage, "cache_read_input_tokens", 0) or 0
        output = getattr(usage, "output_tokens", 0) or 0
        self.usage.add(input_full=input_full, cache_hit=cache_hit, output=output)

    # -- Verlauf / Kompaktierung -------------------------------------------
    def history_length(self) -> int:
        return len(self.messages)

    def user_turns(self) -> int:
        return sum(1 for m in self.messages if m["role"] == "user" and isinstance(m["content"], str))

    def history_chars(self) -> int:
        return sum(_content_chars(m["content"]) for m in self.messages)

    def summarize_history(self) -> str:
        if len(self.messages) < 2:
            return ""
        try:
            resp = self.client.messages.create(
                model=self.config.claude.model,
                max_tokens=4000,
                system=SUMMARY_INSTRUCTION,
                # Das Ende ist am wichtigsten (aktueller Stand) -> im Zweifel den Anfang kuerzen.
                messages=[{"role": "user", "content": _history_as_text(self.messages)[-60000:]}],
                output_config={"effort": "low"},
            )
            self._track_usage(getattr(resp, "usage", None))
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Zusammenfassung fehlgeschlagen: %s", exc)
            return ""

    def reset_to_summary(self, summary: str) -> None:
        self.messages = [
            {"role": "user", "content": "Zusammenfassung unseres bisherigen Gespraechs:\n" + summary},
            {"role": "assistant", "content": "Verstanden, ich habe den Kontext."},
        ]


def _field(block: Any, name: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(name, default)
    return getattr(block, name, default)


def _content_chars(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    total = 0
    for block in content:
        btype = _field(block, "type")
        if btype == "text":
            total += len(_field(block, "text", "") or "")
        elif btype == "tool_use":
            total += len(str(_field(block, "input", "")))
        elif btype == "tool_result":
            total += len(str(_field(block, "content", "")))
        elif btype == "thinking":
            total += len(_field(block, "thinking", "") or "")
    return total


def _history_as_text(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role, content = msg["role"], msg["content"]
        if isinstance(content, str):
            lines.append(f"{role}: {content}")
            continue
        for block in content:
            btype = _field(block, "type")
            if btype == "text":
                lines.append(f"{role}: {_field(block, 'text', '')}")
            elif btype == "tool_use":
                args = str(_field(block, "input", ""))
                lines.append(f"{role}: [Werkzeug {_field(block, 'name', '?')}: {args[:200]}]")
            elif btype == "tool_result":
                lines.append(f"werkzeug-ergebnis: {str(_field(block, 'content', ''))[:600]}")
    return "\n".join(lines)
