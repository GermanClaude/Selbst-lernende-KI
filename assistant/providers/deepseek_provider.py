"""DeepSeek als Gehirn - OpenAI-kompatibel, extrem guenstig.

Nutzt die 'openai'-Bibliothek, auf den DeepSeek-Endpunkt gezeigt. DeepSeek hat
automatisches Kontext-Caching: wiederholter, gleichbleibender Anfang (System-Prompt
+ bisheriger Verlauf) wird als "Cache-Treffer" stark verbilligt. Deshalb halten wir
den Verlauf strikt append-only und den System-Prompt stabil - das spart am meisten.
"""
from __future__ import annotations

import json
from typing import Any

from ..logging_setup import get_logger
from .base import LLMProvider, StreamFn

logger = get_logger()

_INSTALL_HINT = (
    "Fuer DeepSeek fehlt die Bibliothek 'openai'. Installiere sie mit:\n"
    "    pip install openai\n"
    "und trage deinen DEEPSEEK_API_KEY in die .env-Datei ein."
)


class DeepSeekProvider(LLMProvider):
    name = "deepseek"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        # OpenAI-Format: System-Prompt ist die erste Nachricht.
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        if self.client is None:
            self.client = self._make_client()

    def _make_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError:
            return None
        key = self.config.deepseek_api_key
        if not key:
            return None
        return OpenAI(api_key=key, base_url=self.config.deepseek.base_url)

    # -- Hauptschleife ------------------------------------------------------
    def respond(self, user_text: str, on_text: StreamFn | None = None, max_tool_rounds: int = 25) -> str:
        if self.client is None:
            if on_text:
                on_text(_INSTALL_HINT)
            return _INSTALL_HINT

        self.messages.append({"role": "user", "content": user_text})
        final_parts: list[str] = []

        for _ in range(max_tool_rounds):
            text, tool_calls = self._one_turn(on_text)
            if text is None:
                return "Es gab ein Problem bei der Verbindung zu DeepSeek."
            if text:
                final_parts.append(text)

            # Assistenten-Nachricht (OpenAI-Format) anhaengen.
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": text or ""}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls
                ]
            self.messages.append(assistant_msg)

            if not tool_calls:
                break

            for tc in tool_calls:
                if on_text:
                    on_text(f"\n  … nutze Werkzeug: {tc['name']}\n")
                try:
                    parsed = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    parsed = {}
                output, _is_error = self._exec_tool(tc["name"], parsed)
                self.messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": output}
                )

        return "\n".join(final_parts).strip() or "(keine Textantwort)"

    def _one_turn(self, on_text: StreamFn | None):
        """Ein Modell-Durchlauf (gestreamt). Gibt (text, tool_calls) zurueck."""
        try:
            stream = self.client.chat.completions.create(
                model=self.config.deepseek.model,
                messages=self.messages,
                tools=self.registry.specs_openai(),
                tool_choice="auto",
                max_tokens=self.config.deepseek.max_tokens,
                temperature=self.config.deepseek.temperature,
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("DeepSeek-Fehler: %s", exc)
            if on_text:
                on_text(f"\n[DeepSeek-Fehler: {exc}]")
            return (None, None)

        text_parts: list[str] = []
        # tool_calls nach Index sammeln (Fragmente kommen verteilt an).
        tool_acc: dict[int, dict[str, str]] = {}

        try:
            for chunk in stream:
                if getattr(chunk, "usage", None):
                    self._track_usage(chunk.usage)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    text_parts.append(delta.content)
                    if on_text:
                        on_text(delta.content)
                for tc in getattr(delta, "tool_calls", None) or []:
                    idx = tc.index
                    slot = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if getattr(tc, "id", None):
                        slot["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn:
                        if getattr(fn, "name", None):
                            slot["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            slot["arguments"] += fn.arguments
        except Exception as exc:  # noqa: BLE001
            logger.error("DeepSeek-Streamfehler: %s", exc)
            if on_text:
                on_text(f"\n[DeepSeek-Streamfehler: {exc}]")
            return (None, None)

        tool_calls = [tool_acc[i] for i in sorted(tool_acc) if tool_acc[i]["name"]]
        return ("".join(text_parts), tool_calls)

    def _track_usage(self, usage: Any) -> None:
        if not usage:
            return
        hit = getattr(usage, "prompt_cache_hit_tokens", None)
        miss = getattr(usage, "prompt_cache_miss_tokens", None)
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        if hit is None and miss is None:
            # Kein Cache-Detail -> alles als voller Input werten.
            self.usage.add(input_full=prompt, output=getattr(usage, "completion_tokens", 0) or 0)
            return
        self.usage.add(
            input_full=miss or 0,
            cache_hit=hit or 0,
            output=getattr(usage, "completion_tokens", 0) or 0,
        )

    # -- Verlauf / Kompaktierung -------------------------------------------
    def history_length(self) -> int:
        # System-Nachricht nicht mitzaehlen.
        return max(0, len(self.messages) - 1)

    def summarize_history(self) -> str:
        if self.client is None or self.history_length() < 2:
            return ""
        try:
            resp = self.client.chat.completions.create(
                model=self.config.deepseek.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Fasse das folgende Gespraech in 4-8 knappen deutschen "
                        "Stichpunkten zusammen. Behalte Namen, Entscheidungen, offene "
                        "Aufgaben und Vorlieben.",
                    },
                    {"role": "user", "content": _history_as_text(self.messages)[:30000]},
                ],
                max_tokens=600,
                stream=False,
            )
            self._track_usage(getattr(resp, "usage", None))
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek-Zusammenfassung fehlgeschlagen: %s", exc)
            return ""

    def reset_to_summary(self, summary: str) -> None:
        self.messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": "Zusammenfassung unseres bisherigen Gespraechs:\n" + summary},
            {"role": "assistant", "content": "Verstanden, ich habe den Kontext."},
        ]


def _history_as_text(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content:
            lines.append(f"{role}: {content}")
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                lines.append(f"{role}: [Werkzeug {tc['function']['name']}]")
    return "\n".join(lines)
