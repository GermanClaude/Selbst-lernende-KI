"""Claude (Anthropic) als Gehirn - adaptives Thinking, Werkzeuge, append-only Verlauf."""
from __future__ import annotations

from typing import Any

from ..logging_setup import get_logger
from .base import LLMProvider, StreamFn

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
        }

    def _open_stream(self, kwargs: dict[str, Any]):
        if self.config.claude.server_side_fallback:
            kwargs = dict(kwargs)
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
            return self.client.beta.messages.stream(**kwargs)
        return self.client.messages.stream(**kwargs)

    # -- Hauptschleife ------------------------------------------------------
    def respond(self, user_text: str, on_text: StreamFn | None = None, max_tool_rounds: int = 25) -> str:
        self.messages.append({"role": "user", "content": user_text})
        final_parts: list[str] = []

        for _ in range(max_tool_rounds):
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

            if getattr(response, "stop_reason", None) == "pause_turn":
                continue

            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            if not tool_uses:
                break

            tool_results = []
            for block in tool_uses:
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

    def summarize_history(self) -> str:
        if len(self.messages) < 2:
            return ""
        try:
            resp = self.client.messages.create(
                model=self.config.claude.model,
                max_tokens=1000,
                system="Fasse das folgende Gespraech in 4-8 knappen Stichpunkten auf Deutsch "
                "zusammen. Behalte Namen, Entscheidungen, offene Aufgaben und Vorlieben.",
                messages=[{"role": "user", "content": _history_as_text(self.messages)[:30000]}],
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


def _history_as_text(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role, content = msg["role"], msg["content"]
        if isinstance(content, str):
            lines.append(f"{role}: {content}")
            continue
        for block in content:
            btype = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
            if btype == "text":
                text = getattr(block, "text", None) or (block.get("text", "") if isinstance(block, dict) else "")
                lines.append(f"{role}: {text}")
            elif btype == "tool_result":
                c = block.get("content", "") if isinstance(block, dict) else ""
                lines.append(f"werkzeug-ergebnis: {str(c)[:300]}")
    return "\n".join(lines)
