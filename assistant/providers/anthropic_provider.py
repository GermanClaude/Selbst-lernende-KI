"""Claude (Anthropic) als Gehirn - adaptives Thinking, Werkzeuge, append-only Verlauf."""
from __future__ import annotations

from typing import Any

from ..logging_setup import get_logger
from .base import (
    BILD_ABGELEHNT,
    CONNECT_TIMEOUT,
    LIMIT_NOTE,
    READ_TIMEOUT,
    REFUSAL_PLACEHOLDER,
    SUMMARY_INSTRUCTION,
    TRUNCATED_NOTE,
    TRUNCATED_TOOL_ERROR,
    BildTeil,
    LLMProvider,
    StreamFn,
    aufteilen,
    bild_gewicht,
    bild_platzhalter,
    leerer_bildtext,
    summary_input,
)

logger = get_logger()


class AnthropicProvider(LLMProvider):
    name = "claude"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.messages: list[dict[str, Any]] = []
        self._error_status: int | None = None  # HTTP-Status des letzten API-Fehlers
        if self.client is None:
            self.client = self._make_client()

    def _make_client(self) -> Any:
        import anthropic

        key = self.config.anthropic_api_key
        timeout = anthropic.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)
        if key:
            return anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=3)
        return anthropic.Anthropic(timeout=timeout, max_retries=3)

    # -- Request ------------------------------------------------------------
    def _stream_kwargs(self, allow_tools: bool = True) -> dict[str, Any]:
        kwargs = {
            "model": self.config.claude.model,
            "max_tokens": self.config.claude.max_tokens,
            "system": self.system_prompt,
            "messages": self.messages,
            "tools": self.registry.specs(),
            "tool_choice": {"type": "auto"},
            # "summarized": waehrend des Nachdenkens kommen weiter Daten - sonst wirkt eine
            # lange Denkpause wie eine tote Verbindung (Zeitlimit) und Strg+C reagiert spaet.
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": self.effort_override or self.config.claude.effort},
            # Automatisches Prompt-Caching: der wachsende Verlauf wird bei jedem
            # Werkzeug-Schritt erneut gesendet - aus dem Cache kostet er ~10 %.
            "extra_body": {"cache_control": {"type": "ephemeral"}},
        }
        if not allow_tools:
            kwargs["tool_choice"] = {"type": "none"}  # z.B. Abschlussbericht eines Agenten
        return kwargs

    def _open_stream(self, kwargs: dict[str, Any]):
        # Haiku hat keinen Ersatz bei Ablehnungen - dort wuerde der Parameter abgelehnt.
        if self.config.claude.server_side_fallback and "haiku" not in str(kwargs.get("model", "")):
            kwargs = dict(kwargs)
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
            return self.client.beta.messages.stream(**kwargs)
        return self.client.messages.stream(**kwargs)

    # -- Hauptschleife ------------------------------------------------------
    def respond(
        self,
        user_text: str,
        on_text: StreamFn | None = None,
        max_tool_rounds: int | None = None,
        announce_limit: bool = True,
        allow_tools: bool = True,
        bilder: list | None = None,
    ) -> str:
        start = len(self.messages)
        if bilder:
            # Einmal beim Ankommen gebaut und danach nie mehr veraendert (append-only).
            turn = {"role": "user", "content": self._user_content(user_text, bilder)}
            self.messages.append(turn)
            self._bild_turn = (id(turn), user_text)
        else:
            self.messages.append({"role": "user", "content": user_text})
        final_parts: list[str] = []
        rounds = self._rounds(max_tool_rounds)
        self.hit_limit = False

        for _ in range(rounds):
            self._waiting()
            response = self._one_turn(on_text, allow_tools)
            if response is None:
                if bilder and len(self.messages) == start + 1 and self._rejected():
                    # Die API hat die neue Nachricht mit Bild gar nicht angenommen (z.B. Bild
                    # unlesbar) -> wieder herausnehmen. Sie wurde nie beantwortet, alles Fruehere
                    # bleibt unveraendert; sonst scheiterte jede weitere Anfrage am selben Bild.
                    del self.messages[start:]
                    self._bild_turn = None
                    if on_text:
                        on_text("\n" + BILD_ABGELEHNT)  # sonst sieht man nur den rohen API-Fehler
                    return BILD_ABGELEHNT
                return "Es gab ein Problem bei der Verbindung zum Modell."

            self._track_usage(getattr(response, "usage", None))

            if getattr(response, "stop_reason", None) == "refusal":
                detail = ""
                if getattr(response, "stop_details", None):
                    detail = f" (Kategorie: {getattr(response.stop_details, 'category', '?')})"
                # Teil-Antwort verwerfen (kann leer sein oder einen Werkzeugaufruf ohne
                # Ergebnis enthalten - beides liesse jede weitere Anfrage scheitern).
                self.messages.append({"role": "assistant", "content": REFUSAL_PLACEHOLDER})
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
                self.last_text = text_this_turn

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
                        "content": _tool_content(output),
                        "is_error": is_error,
                    }
                )
            self.messages.append({"role": "user", "content": tool_results})
        else:
            # Schritt-Limit erreicht: Bescheid geben statt stumm aufzuhoeren.
            self.hit_limit = True
            if announce_limit:
                note = LIMIT_NOTE.format(n=rounds)
                final_parts.append(note.strip())
                if on_text:
                    on_text(note)

        return "\n".join(final_parts).strip() or "(keine Textantwort)"

    def _user_content(self, user_text: str, bilder: list) -> list[dict[str, Any]]:
        """Bilder vor dem Text (so versteht Claude sie am besten); bei mehreren Bildern
        steht vor jedem ein kurzes "Bild 1:", damit die KI sie auseinanderhalten kann."""
        from ..modelle import sieht_bilder

        text = leerer_bildtext(user_text, len(bilder))
        if not sieht_bilder("claude", self.config.claude.model):
            # (gibt es derzeit nicht - alle Claude-Modelle sehen Bilder)
            namen = " ".join(b.platzhalter() for b in bilder)
            return [{"type": "text", "text": f"{namen} (Dieses Modell sieht keine Bilder.)\n\n{text}"}]
        content: list[dict[str, Any]] = []
        for i, bild in enumerate(bilder, 1):
            if len(bilder) > 1:
                content.append({"type": "text", "text": f"Bild {i}:"})
            content.append(_bild_block(bild))
        content.append({"type": "text", "text": text})
        return content

    def _rejected(self) -> bool:
        """Hat die API die Anfrage selbst abgelehnt (4xx, nicht Ueberlast/Verbindung)?"""
        return self._error_status in (400, 413, 422)

    def _one_turn(self, on_text: StreamFn | None, allow_tools: bool = True):
        import anthropic

        self._error_status = None
        for attempt in (1, 2):
            emitted = False
            try:
                with self._open_stream(self._stream_kwargs(allow_tools)) as stream:
                    self._active_stream = stream
                    for event in stream:
                        self._check_cancel()
                        if getattr(event, "type", None) == "text" and on_text:
                            on_text(event.text)
                            emitted = True
                    return stream.get_final_message()
            except anthropic.APIStatusError as exc:
                self._error_status = getattr(exc, "status_code", None)
                logger.error("API-Fehler: %s", exc)
                if on_text:
                    on_text(f"\n[Fehler vom Modell: {getattr(exc, 'message', exc)}]")
                return None
            except Exception as exc:  # noqa: BLE001 - Verbindung weg/haengt (auch mitten im Stream)
                self._check_cancel()  # vom Stopp-Knopf geschlossen -> kein neuer Versuch
                logger.warning("Verbindung zum Modell unterbrochen: %s", exc)
                if attempt == 1 and not emitted:
                    continue  # noch nichts gezeigt -> einfach noch einmal versuchen
                if on_text:
                    if isinstance(exc, anthropic.APIConnectionError) and not emitted:
                        on_text("\n[Keine Verbindung zum Modell - Internet/Schluessel pruefen.]")
                    else:
                        on_text("\n[Verbindung zum Modell unterbrochen - bitte nochmal versuchen.]")
                return None
            finally:
                self._active_stream = None
        return None

    def _close_open_tool_calls(self, messages: list) -> None:
        last = messages[-1]
        if last.get("role") != "assistant" or isinstance(last.get("content"), str):
            return
        open_ids = [_field(b, "id") for b in last["content"] if _field(b, "type") == "tool_use"]
        if open_ids:
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid, "is_error": True,
                 "content": "Abgebrochen (Strg+C) - nicht ausgefuehrt."}
                for tid in open_ids
            ]})

    def _track_usage(self, usage: Any) -> None:
        if not usage:
            return
        input_full = getattr(usage, "input_tokens", 0) or 0
        input_full += getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_hit = getattr(usage, "cache_read_input_tokens", 0) or 0
        output = getattr(usage, "output_tokens", 0) or 0
        self._count(input_full=input_full, cache_hit=cache_hit, output=output)

    # -- Verlauf / Kompaktierung -------------------------------------------
    def history_length(self) -> int:
        return len(self.messages)

    def user_turns(self) -> int:
        # Nachrichten vom Menschen: Text oder Bilder+Text - nicht die Werkzeug-Ergebnisse.
        return sum(1 for m in self.messages if m["role"] == "user" and _is_human_turn(m["content"]))

    def history_chars(self) -> int:
        return sum(_content_chars(m["content"]) for m in self.messages)

    def ask_once(self, prompt: str, max_tokens: int = 1500) -> str:
        try:
            resp = self.client.messages.create(
                model=self.config.claude.model,
                # Denken ist bei Opus 5.5 immer an und zaehlt mit -> etwas Luft lassen.
                max_tokens=max_tokens + 2000,
                system=self._ask_system(),
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low"},
            )
            self._track_usage(getattr(resp, "usage", None))
            if getattr(resp, "stop_reason", None) == "refusal":
                return ""
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Kurzfrage fehlgeschlagen: %s", exc)
            return ""

    def summarize_history(self) -> str:
        if len(self.messages) < 2:
            return ""
        try:
            resp = self.client.messages.create(
                model=self.config.claude.model,
                max_tokens=8000,
                system=SUMMARY_INSTRUCTION,
                messages=[{"role": "user", "content": summary_input(_history_as_text(self.messages))}],
                output_config={"effort": "low"},
            )
            self._track_usage(getattr(resp, "usage", None))
            if getattr(resp, "stop_reason", None) in ("max_tokens", "refusal"):
                # Abgeschnittene/abgelehnte Zusammenfassung -> lieber Verlauf behalten.
                logger.warning("Zusammenfassung unvollstaendig (%s).", getattr(resp, "stop_reason", None))
                return ""
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Zusammenfassung fehlgeschlagen: %s", exc)
            return ""

    def reset_to_summary(self, summary: str) -> None:
        self.messages = [
            {"role": "user", "content": "Zusammenfassung unseres bisherigen Gespraechs:\n" + summary},
            {"role": "assistant", "content": "Verstanden, ich habe den Kontext."},
        ]
        self._bild_turn = None


def _bild_block(bild: Any) -> BildTeil:
    return BildTeil(
        {"type": "image", "source": {"type": "base64", "media_type": bild.mime, "data": bild.b64()}},
        bild_name=bild.name,
    )


def _tool_content(output: Any) -> Any:
    """tool_result-Inhalt: Text wie bisher - mit Bildern eine Liste aus Text und Bild-Bloecken."""
    text, bilder = aufteilen(output)
    if not bilder:
        return text
    return [{"type": "text", "text": text or "Bild:"}, *(_bild_block(b) for b in bilder)]


def _is_human_turn(content: Any) -> bool:
    if isinstance(content, str):
        return True
    return bool(content) and not any(_field(b, "type") == "tool_result" for b in content)


def _field(block: Any, name: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(name, default)
    return getattr(block, name, default)


def _content_chars(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    total = 0
    for block in content or []:
        btype = _field(block, "type")
        if btype == "text":
            total += len(_field(block, "text", "") or "")
        elif btype == "tool_use":
            total += len(str(_field(block, "input", "")))
        elif btype == "tool_result":
            inner = _field(block, "content", "")
            total += _content_chars(inner) if isinstance(inner, list) else len(str(inner or ""))
        elif btype == "thinking":
            total += len(_field(block, "thinking", "") or "")
        elif btype == "image":
            source = _field(block, "source", None) or {}
            total += bild_gewicht(len(str(_field(source, "data", "") or "")))
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
                lines.append(f"werkzeug-ergebnis: {_result_text(_field(block, 'content', ''))[:600]}")
            elif btype == "image":
                lines.append(f"{role}: {bild_platzhalter(block)}")
    return "\n".join(lines)


def _result_text(content: Any) -> str:
    """Werkzeug-Ergebnis als Text - Bilder als "[Bild: name]", nie Base64."""
    if not isinstance(content, list):
        return str(content or "")
    parts = []
    for block in content:
        btype = _field(block, "type")
        if btype == "text":
            parts.append(_field(block, "text", "") or "")
        elif btype == "image":
            parts.append(bild_platzhalter(block))
    return " ".join(p for p in parts if p)
