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
from .base import (
    BILD_ABGELEHNT,
    CONNECT_TIMEOUT,
    LIMIT_NOTE,
    READ_TIMEOUT,
    SUMMARY_INSTRUCTION,
    TRUNCATED_NOTE,
    TRUNCATED_TOOL_ERROR,
    BildTeil,
    LLMProvider,
    Wortmeldung,
    StreamFn,
    aufteilen,
    bild_gewicht,
    bild_platzhalter,
    leerer_bildtext,
    summary_input,
)

logger = get_logger()

_INSTALL_HINT = (
    "Fuer DeepSeek fehlt die Bibliothek 'openai'. Installiere sie mit:\n"
    "    pip install openai\n"
    "und trage deinen DEEPSEEK_API_KEY in die .env-Datei ein."
)


class DeepSeekProvider(LLMProvider):
    name = "deepseek"
    label = "DeepSeek"  # Name in Fehlermeldungen

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._finish_reason: str | None = None
        # Lehnt DeepSeek das Nachdenken in diesem Gespraech ab (z.B. alter Verlauf ohne
        # Denk-Text), laeuft der Rest des Gespraechs ohne - statt bei jeder Frage zu scheitern.
        self._thinking_off = False
        self._error_status: int | None = None  # HTTP-Status des letzten API-Fehlers
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
        from openai import Timeout

        return OpenAI(
            api_key=key,
            base_url=self.config.deepseek.base_url,
            timeout=Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            max_retries=3,
        )

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
        self.hit_limit = False
        if self.client is None:
            hint = self._install_hint()
            if on_text:
                on_text(hint)
            return hint

        start = len(self.messages)
        if bilder:
            turn = {"role": "user", "content": self._user_content(user_text, bilder)}
            self.messages.append(turn)
            self._bild_turn = (id(turn), user_text)
        else:
            self.messages.append({"role": "user", "content": user_text})
        final_parts: list[str] = []
        rounds = self._rounds(max_tool_rounds)

        for _ in range(rounds):
            self._finish_reason = None
            self._waiting()
            text, tool_calls, reasoning = self._one_turn(on_text, tool_choice="auto" if allow_tools else "none")
            if text is None:
                if (bilder and len(self.messages) == start + 1 and _has_image_parts(self.messages[start])
                        and self._error_status in (400, 413, 422)):
                    # Neue Nachricht mit Bild wurde gar nicht angenommen -> wieder heraus (sie
                    # wurde nie beantwortet); sonst scheitert jede weitere Anfrage am selben Bild.
                    del self.messages[start:]
                    self._bild_turn = None
                    if on_text:
                        on_text("\n" + BILD_ABGELEHNT)  # sonst sieht man nur den rohen API-Fehler
                    return BILD_ABGELEHNT
                return f"Es gab ein Problem bei der Verbindung zu {self.label}."
            if text:
                final_parts.append(text)
                self.last_text = text

            # Assistenten-Nachricht (OpenAI-Format) anhaengen.
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": text or ""}
            if reasoning is not None:
                # Beim Nachdenken mit Werkzeugen will DeepSeek den Denk-Text spaeter zurueck.
                assistant_msg["reasoning_content"] = reasoning
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        # Abgeschnittenes JSON nicht zurueckschicken (koennte die API ablehnen).
                        "function": {
                            "name": tc["name"],
                            "arguments": _valid_json_or_empty(tc["arguments"]),
                        },
                    }
                    for tc in tool_calls
                ]
            self.messages.append(assistant_msg)

            if not tool_calls:
                if self._finish_reason == "length":
                    final_parts.append(TRUNCATED_NOTE.strip())
                    if on_text:
                        on_text(TRUNCATED_NOTE)
                break

            tool_images: list[tuple[str, list]] = []
            for tc in tool_calls:
                try:
                    parsed = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    # Fast immer: Antwort bei max_tokens abgeschnitten. Nicht mit
                    # leeren Argumenten ausfuehren, sondern der KI erklaeren, was los ist.
                    output = TRUNCATED_TOOL_ERROR
                else:
                    if on_text:
                        on_text(f"\n  … nutze Werkzeug: {tc['name']}\n")
                    output, _is_error = self._exec_tool(tc["name"], parsed)
                output, images = aufteilen(output)
                if images:
                    if self._sees_images():
                        tool_images.append((tc["name"], images))  # kommen nach allen tool-Antworten
                    else:
                        output = f"{output}\n\n{self._describe_images(images)}"
                # Werkzeug-Antworten bleiben bei DeepSeek immer Text.
                self.messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": output}
                )
            if tool_images:
                # Erst wenn alle Werkzeugaufrufe beantwortet sind (sonst lehnt die API ab):
                # die Bilder als Nachricht hinterher - nur dort duerfen bei DeepSeek Bilder stehen.
                self.messages.append({"role": "user", "content": _tool_image_content(tool_images)})
        else:
            # Schritt-Limit erreicht: Bescheid geben statt stumm aufzuhoeren.
            self.hit_limit = True
            if announce_limit:
                note = LIMIT_NOTE.format(n=rounds)
                final_parts.append(note.strip())
                if on_text:
                    on_text(note)

        return "\n".join(final_parts).strip() or "(keine Textantwort)"

    def _install_hint(self) -> str:
        return _INSTALL_HINT

    # -- Bilder -------------------------------------------------------------
    def _sees_images(self) -> bool:
        from ..modelle import sieht_bilder

        return sieht_bilder("deepseek", self.config.deepseek.model)

    def _user_content(self, user_text: str, bilder: list) -> Any:
        """Nachricht mit Bildern: sieht das Modell Bilder, als Text- und Bild-Teile; sonst
        beschreibt DeepSeek Flash die Bilder vorher und die Beschreibung steht als Text davor."""
        text = leerer_bildtext(user_text, len(bilder))
        if not self._sees_images():
            return f"{self._describe_images(bilder)}\n\n{text}"
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for i, bild in enumerate(bilder, 1):
            if len(bilder) > 1:
                content.append({"type": "text", "text": f"Bild {i}:"})
            content.append(_image_part(bild))
        return content

    def _describe_images(self, bilder: list) -> str:
        """'[Bild 1 - Beschreibung: ...]' je Bild (Nebenaufruf an DeepSeek Flash)."""
        lines = []
        for i, bild in enumerate(bilder, 1):
            self._waiting()
            beschreibung = self._describe_image(bild)
            if beschreibung:
                lines.append(f"[Bild {i} \u2013 Beschreibung: {beschreibung}]")
            else:
                lines.append(f"[Bild {i}: {bild.platzhalter()} \u2013 {_NOT_SEEN}]")
        return "\n".join(lines)

    def _describe_image(self, bild: Any) -> str:
        """Guenstiger Nebenaufruf (ohne Werkzeuge, ohne Nachdenken): Bild -> Beschreibung.
        Gibt "" zurueck, wenn es nicht klappt. Kosten zaehlen mit (zum Flash-Preis)."""
        from ..modelle import DEEPSEEK_SEHMODELL

        try:
            resp = self.client.chat.completions.create(
                model=DEEPSEEK_SEHMODELL,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": _DESCRIBE_PROMPT},
                    {"type": "image_url", "image_url": {"url": bild.data_url()}},
                ]}],
                max_tokens=_DESCRIBE_MAX_TOKENS,
                stream=False,
                timeout=_DESCRIBE_TIMEOUT,
                extra_body={"thinking": {"type": "disabled"}},
            )
            self._track_usage(getattr(resp, "usage", None), model=DEEPSEEK_SEHMODELL)
            text = (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001 - dann eben ohne Beschreibung
            self._check_cancel()
            logger.warning("Bildbeschreibung fehlgeschlagen: %s", type(exc).__name__)
            return ""
        return text[:_DESCRIBE_MAX_CHARS].strip()

    # -- Nachdenken ---------------------------------------------------------
    def settings_changed(self) -> None:
        self._thinking_off = False  # neue Wahl -> Nachdenken wieder probieren

    def _think_level(self) -> str:
        """aus | low | high | max - im Live-Modus zaehlt Tempo (effort_override)."""
        if self._thinking_off:
            return "aus"
        from ..modelle import deepseek_denken

        return deepseek_denken(self.config, self.effort_override)

    def _max_tokens(self, level: str) -> int:
        # Der Denk-Text zaehlt mit - beim Nachdenken mehr Platz lassen.
        extra = {"low": 16384, "high": 32768, "max": 65536}.get(level, 0)
        return max(int(self.config.deepseek.max_tokens or 0), extra)

    def _request_messages(self, thinking: bool) -> list[dict[str, Any]]:
        """Mit Nachdenken: jede Assistenten-Nachricht traegt einen Denk-Text (notfalls leer).
        Ohne: Denk-Texte weglassen (werden dann ohnehin nicht gebraucht).
        Sieht das Modell keine Bilder (z.B. nach dem Wechsel auf V4 Pro), werden Bilder im
        Verlauf beim Senden zu "[Bild: name]" - der gespeicherte Verlauf bleibt gleich."""
        sees = self._sees_images()
        out = []
        for m in self.messages:
            if m.get("role") != "assistant":
                if not sees and _has_image_parts(m):
                    m = {**m, "content": _parts_as_text(m["content"])}
                out.append(m)
            elif thinking and "reasoning_content" not in m:
                out.append({**m, "reasoning_content": ""})
            elif not thinking and "reasoning_content" in m:
                out.append({k: v for k, v in m.items() if k != "reasoning_content"})
            else:
                out.append(m)
        return out

    def _turn_kwargs(self, level: str, tool_choice: str) -> dict[str, Any]:
        """Die Anfrage fuer einen Modell-Durchlauf (von Ollama ueberschrieben)."""
        thinking = level != "aus"
        kwargs: dict[str, Any] = {
            "model": self.config.deepseek.model,
            "messages": self._request_messages(thinking),
            "tools": self.registry.specs_openai(),
            "tool_choice": tool_choice,
            "max_tokens": self._max_tokens(level),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if thinking:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}, "reasoning_effort": level}
        else:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            kwargs["temperature"] = self.config.deepseek.temperature
        return kwargs

    def _retry_after_error(self, exc: Exception) -> bool:
        """Von Ollama ueberschrieben: True = Fehler behoben, einmal neu versuchen."""
        return False

    def _error_text(self, exc: Exception, stream: bool = False) -> str:
        return f"\n[{self.label}-{'Streamfehler' if stream else 'Fehler'}: {exc}]"

    def _one_turn(self, on_text: StreamFn | None, tool_choice: str = "auto", retried: bool = False):
        """Ein Modell-Durchlauf (gestreamt). Gibt (text, tool_calls, denk_text) zurueck -
        denk_text ist None, wenn ohne Nachdenken gearbeitet wurde."""
        level = self._think_level()
        thinking = level != "aus"
        kwargs = self._turn_kwargs(level, tool_choice)
        self._error_status = None
        try:
            stream = self.client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            self._check_cancel()
            self._error_status = getattr(exc, "status_code", None)
            if thinking and _is_thinking_error(exc):
                logger.warning("%s lehnt Nachdenken in diesem Gespraech ab - weiter ohne: %s", self.label, exc)
                self._thinking_off = True
                return self._one_turn(on_text, tool_choice, retried=retried)
            # Kontext voll (sehr viele/grosse Dateien gelesen): alte Werkzeug-Ausgaben
            # kuerzen und einmal neu versuchen, statt bei jedem "weiter" erneut zu scheitern.
            if not retried and _is_context_error(exc) and self._shrink_old_tool_outputs():
                logger.warning("Kontext voll - aeltere Werkzeug-Ausgaben gekuerzt.")
                return self._one_turn(on_text, tool_choice, retried=True)
            if not retried and self._retry_after_error(exc):
                return self._one_turn(on_text, tool_choice, retried=True)
            logger.error("%s-Fehler: %s", self.label, exc)
            if on_text:
                on_text(self._error_text(exc))
            return (None, None, None)

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        # tool_calls nach Index sammeln (Fragmente kommen verteilt an).
        tool_acc: dict[int, dict[str, str]] = {}

        self._active_stream = stream
        try:
            for chunk in stream:
                self._check_cancel()
                if getattr(chunk, "usage", None):
                    self._track_usage(chunk.usage)
                if not chunk.choices:
                    continue
                if getattr(chunk.choices[0], "finish_reason", None):
                    self._finish_reason = chunk.choices[0].finish_reason
                delta = chunk.choices[0].delta
                if getattr(delta, "reasoning_content", None):
                    reasoning_parts.append(delta.reasoning_content)
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
            self._check_cancel()
            logger.error("%s-Streamfehler: %s", self.label, exc)
            if on_text:
                on_text(self._error_text(exc, stream=True))
            return (None, None, None)

        finally:
            self._active_stream = None

        tool_calls = [tool_acc[i] for i in sorted(tool_acc) if tool_acc[i]["name"]]
        return ("".join(text_parts), tool_calls, "".join(reasoning_parts) if thinking else None)

    def _track_usage(self, usage: Any, model: str | None = None) -> None:
        if not usage:
            return
        hit = getattr(usage, "prompt_cache_hit_tokens", None)
        miss = getattr(usage, "prompt_cache_miss_tokens", None)
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        if hit is None and miss is None:
            # Kein Cache-Detail -> alles als voller Input werten.
            self._count(input_full=prompt, output=getattr(usage, "completion_tokens", 0) or 0, model=model)
            return
        self._count(
            input_full=miss or 0,
            cache_hit=hit or 0,
            output=getattr(usage, "completion_tokens", 0) or 0,
            model=model,
        )

    # -- Verlauf / Kompaktierung -------------------------------------------
    def history_length(self) -> int:
        # System-Nachricht nicht mitzaehlen.
        return max(0, len(self.messages) - 1)

    def user_turns(self) -> int:
        # Bilder eines Werkzeugs (eigene user-Nachricht) zaehlen nicht als Nachricht vom Menschen.
        return sum(1 for m in self.messages
                   if m.get("role") == "user" and not isinstance(m.get("content"), _ToolImages)
                   and not isinstance(m, Wortmeldung))  # Live-Sehen: Nova hat sich selbst gemeldet

    def _close_open_tool_calls(self, messages: list) -> None:
        idx = next((i for i in range(len(messages) - 1, -1, -1)
                    if messages[i].get("role") == "assistant"), None)
        if idx is None or not messages[idx].get("tool_calls"):
            return
        answered = {m.get("tool_call_id") for m in messages[idx + 1 :] if m.get("role") == "tool"}
        for tc in messages[idx]["tool_calls"]:
            if tc["id"] not in answered:
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": "Abgebrochen (Strg+C) - nicht ausgefuehrt."})

    def _shrink_old_tool_outputs(self, keep_last: int = 2) -> bool:
        """Ersetzt grosse, aeltere Werkzeug-Ausgaben durch einen kurzen Hinweis."""
        tool_msgs = [m for m in self.messages if m.get("role") == "tool"]
        changed = False
        for m in tool_msgs[: max(0, len(tool_msgs) - keep_last)]:
            content = m.get("content") or ""
            if isinstance(content, str) and len(content) > 500:
                m["content"] = content[:300] + _SHRUNK_NOTE
                changed = True
        return changed

    def history_chars(self) -> int:
        total = 0
        for m in self.messages[1:]:
            total += _content_chars(m.get("content")) + len(m.get("reasoning_content") or "")
            for tc in m.get("tool_calls") or []:
                total += len(tc["function"]["arguments"] or "")
        return total

    def ask_once(self, prompt: str, max_tokens: int = 1500) -> str:
        if self.client is None:
            return ""
        try:
            resp = self.client.chat.completions.create(**self._simple_kwargs([
                {"role": "system", "content": self._ask_system()},
                {"role": "user", "content": prompt},
            ], max_tokens))
            self._track_usage(getattr(resp, "usage", None))
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s-Kurzfrage fehlgeschlagen: %s", self.label, exc)
            return ""

    def _simple_kwargs(self, messages: list[dict[str, Any]], max_tokens: int) -> dict[str, Any]:
        """Anfrage ohne Werkzeuge und ohne Nachdenken (Kurzfrage, Zusammenfassung)."""
        return {"model": self.config.deepseek.model, "messages": messages, "max_tokens": max_tokens,
                "stream": False, "extra_body": {"thinking": {"type": "disabled"}}}

    def _summary_limit(self) -> int:
        """So viele Zeichen Verlauf gehen hoechstens in die Zusammenfassung."""
        return 60_000

    def summarize_history(self) -> str:
        if self.client is None or self.history_length() < 2:
            return ""
        try:
            limit = self._summary_limit()
            resp = self.client.chat.completions.create(**self._simple_kwargs([
                {"role": "system", "content": SUMMARY_INSTRUCTION},
                {"role": "user", "content": summary_input(_history_as_text(self.messages), limit=limit,
                                                          head=min(8_000, limit // 4))},
            ], 4000))
            self._track_usage(getattr(resp, "usage", None))
            if getattr(resp.choices[0], "finish_reason", "stop") == "length":
                logger.warning("%s-Zusammenfassung abgeschnitten - Verlauf bleibt.", self.label)
                return ""
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s-Zusammenfassung fehlgeschlagen: %s", self.label, exc)
            return ""

    def reset_to_summary(self, summary: str) -> None:
        self.messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": "Zusammenfassung unseres bisherigen Gespraechs:\n" + summary},
            {"role": "assistant", "content": "Verstanden, ich habe den Kontext."},
        ]
        self._bild_turn = None


# Nebenaufruf, wenn das gewaehlte Modell keine Bilder sieht (V4 Pro).
_DESCRIBE_PROMPT = (
    "Beschreibe dieses Bild ausfuehrlich auf Deutsch, inklusive allem lesbaren Text (woertlich), "
    "Zahlen, Tabellen, Diagrammen, Bedienelementen und Fehlermeldungen. Antworte nur mit der "
    "Beschreibung, ohne Einleitung."
)
_DESCRIBE_MAX_TOKENS = 1500
_DESCRIBE_MAX_CHARS = 6000
_DESCRIBE_TIMEOUT = 90.0
_NOT_SEEN = ("Bild konnte nicht angesehen werden (das gewaehlte Modell sieht keine Bilder und "
             "die Bildbeschreibung hat nicht geklappt). Sag das deinem Menschen freundlich und "
             "schlag vor, es nochmal zu versuchen oder DeepSeek Flash zu waehlen.")


class _ToolImages(list):
    """Inhalt der user-Nachricht mit Bildern eines Werkzeugs - eine ganz normale Liste fuer
    die API; nur zum Wiedererkennen (zaehlt nicht als Nachricht vom Menschen)."""

    __slots__ = ()


def _image_part(bild: Any) -> BildTeil:
    return BildTeil({"type": "image_url", "image_url": {"url": bild.data_url()}}, bild_name=bild.name)


def _tool_image_content(tool_images: list[tuple[str, list]]) -> _ToolImages:
    content = _ToolImages()
    for name, images in tool_images:
        content.append({"type": "text", "text": f"Bild vom Werkzeug {name}:"})
        content.extend(_image_part(b) for b in images)
    return content


def _has_image_parts(message: dict[str, Any]) -> bool:
    content = message.get("content")
    return isinstance(content, list) and any(
        isinstance(p, dict) and p.get("type") == "image_url" for p in content)


def _parts_as_text(content: Any) -> str:
    """Teile einer Nachricht als Text - Bilder als "[Bild: name]" (nie Base64)."""
    if not isinstance(content, list):
        return str(content or "")
    parts = []
    for p in content:
        kind = p.get("type") if isinstance(p, dict) else None
        if kind == "text":
            parts.append(str(p.get("text") or ""))
        elif kind == "image_url":
            parts.append(bild_platzhalter(p))
    return "\n".join(x for x in parts if x)


def _content_chars(content: Any) -> int:
    if not isinstance(content, list):
        return len(str(content or ""))
    total = 0
    for p in content:
        kind = p.get("type") if isinstance(p, dict) else None
        if kind == "text":
            total += len(str(p.get("text") or ""))
        elif kind == "image_url":
            total += bild_gewicht(len(str((p.get("image_url") or {}).get("url") or "")))
    return total


_SHRUNK_NOTE = "\n…(aeltere Ausgabe gekuerzt, weil der Kontext voll war - bei Bedarf neu lesen)"
_CONTEXT_ERROR_HINTS = ("context length", "context_length", "maximum context", "too many tokens", "too long")


def _is_thinking_error(exc: Exception) -> bool:
    """400 wegen fehlendem/ungueltigem Denk-Text (reasoning_content) bzw. Denk-Parametern."""
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    return status in (400, 422) and ("reasoning" in text or "thinking" in text)


def _is_context_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(hint in text for hint in _CONTEXT_ERROR_HINTS)


def _valid_json_or_empty(arguments: str) -> str:
    try:
        json.loads(arguments or "{}")
        return arguments or "{}"
    except json.JSONDecodeError:
        return "{}"


def _history_as_text(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system" or isinstance(msg, Wortmeldung):
            continue  # Live-Sehen: Bildschirminhalt nie in die Zusammenfassung (-> Gedaechtnis)
        content = msg.get("content")
        if role == "tool":
            lines.append(f"werkzeug-ergebnis: {_parts_as_text(content)[:600]}")
            continue
        if isinstance(content, str) and content:
            lines.append(f"{role}: {content}")
        elif isinstance(content, list):
            text = _parts_as_text(content)
            if text:
                lines.append(f"{role}: {text}")
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                args = (tc["function"].get("arguments") or "")[:200]
                lines.append(f"{role}: [Werkzeug {tc['function']['name']}: {args}]")
    return "\n".join(lines)
