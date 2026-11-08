"""Ollama als Gehirn - kostenlos, die Modelle laufen auf deinem PC (kein Schluessel, kein Geld).

Baut auf dem DeepSeek-Provider auf (gleicher Werkzeug-Loop im OpenAI-Format). Anders ist:
  * Gesprochen wird mit Ollamas eigener Schnittstelle /api/chat (assistant/ollama.py,
    OllamaClient) - nur dort laesst sich die Kontext-Laenge setzen. Zeigt die Adresse auf
    ".../v1" (LM Studio & Co.), geht es ueber die openai-Bibliothek.
  * Was das Modell kann, fragt der Provider bei Ollama nach (/api/show, einmal je Modell):
    ohne "tools" gibt es keine Werkzeuge (und einen einmaligen Hinweis an den Menschen),
    ohne "vision" stehen Bilder nur als "[Bild: name]" im Text (kein bezahlter Nebenaufruf),
    ohne "thinking" wird nie Nachdenken verlangt.
  * Kosten sind immer 0.
  * Lokale Modelle haben wenig Kontext: der Verlauf wird frueher zusammengefasst und grosse,
    aeltere Werkzeug-Ausgaben werden beim Senden gekuerzt (der gespeicherte Verlauf bleibt).
"""
from __future__ import annotations

import json
from typing import Any

from .. import ollama
from ..logging_setup import get_logger
from .base import StreamFn
from .deepseek_provider import DeepSeekProvider, _SHRUNK_NOTE, _content_chars

logger = get_logger()

_OPENAI_HINT = (
    "Fuer einen OpenAI-kompatiblen Server (Adresse endet auf /v1) fehlt die Bibliothek 'openai'. "
    "Installiere sie mit:  pip install openai"
)
_OHNE_WERKZEUGE_SYSTEM = (
    "\n\n[Wichtig: In diesem Gespraech stehen dir KEINE Werkzeuge zur Verfuegung (das gewaehlte Modell "
    "kann sie nicht benutzen). Behaupte nie, du haettest eine Datei gelesen, im Web gesucht oder etwas am "
    "PC getan. Antworte aus deinem Wissen und sag ehrlich, wenn du etwas dafuer nachschauen muesstest.]"
)
_ZEICHEN_PRO_TOKEN = 3       # grob, fuer Deutsch eher weniger als 4
_ANTWORT_RESERVE = 4500      # Token, die fuer die Antwort frei bleiben sollen


class OllamaProvider(DeepSeekProvider):
    name = "ollama"
    label = "Ollama"

    def __init__(self, *args: Any, **kwargs: Any):
        self._caps: dict[str, set[str]] = {}
        self._gewarnt: set[str] = set()   # Modelle, zu denen der Werkzeug-Hinweis schon kam
        self._ohne_werkzeuge: set[str] = set()  # Ollama hat Werkzeuge abgelehnt
        super().__init__(*args, **kwargs)
        self._client_pruefen()  # z.B. neues Gespraech mit dem Client des alten (evtl. andere Adresse)

    # -- Verbindung -------------------------------------------------------
    @property
    def adresse(self) -> str:
        return ollama.adresse_aus(self.config)

    @property
    def _openai(self) -> bool:
        return ollama.ist_openai_adresse(self.adresse)

    @property
    def model(self) -> str:
        return self.config.ollama.model

    def _make_client(self) -> Any:
        if self._openai:
            try:
                from openai import OpenAI, Timeout
            except ImportError:
                return None
            return OpenAI(api_key="ollama", base_url=self.adresse,
                          timeout=Timeout(ollama.LESE_TIMEOUT, connect=ollama.VERBINDEN_TIMEOUT), max_retries=1)
        return ollama.OllamaClient(self.adresse, kontext=self.config.ollama.kontext)

    def _install_hint(self) -> str:
        return _OPENAI_HINT

    def settings_changed(self) -> None:
        super().settings_changed()
        self._ohne_werkzeuge.clear()
        self._caps.clear()  # neues Modell oder neue Adresse: neu nachfragen
        self._client_pruefen()

    @staticmethod
    def _client_adresse(client: Any) -> str | None:
        """Fuer welche Adresse der Client gebaut wurde (None = unbekannt, z.B. ein Test-Client)."""
        if isinstance(client, ollama.OllamaClient):
            return client.dienst.adresse.rstrip("/")
        if type(client).__name__ == "OpenAI" and getattr(client, "base_url", None) is not None:
            return str(client.base_url).rstrip("/")
        return None

    def _client_pruefen(self) -> None:
        """Passt der Client noch zur eingestellten Adresse? Sonst neu bauen. Fehlt er (openai-
        Bibliothek fehlte fuer eine /v1-Adresse), wird es erneut versucht. Nur ein Ollama-Client
        fuer dieselbe Adresse wird weiterbenutzt (Kontext-Laenge wird angepasst)."""
        adresse = self.adresse.rstrip("/")
        if self.client is None:
            self.client = self._make_client()
            return
        gebaut = self._client_adresse(self.client)
        if gebaut is None:
            return  # fremder Client (Tests) - so lassen
        if isinstance(self.client, ollama.OllamaClient) and not self._openai and gebaut == adresse:
            self.client.kontext = max(2048, int(self.config.ollama.kontext or 16384))
            return
        self.client = self._make_client()

    def cancel(self) -> None:
        """Stopp-Knopf: auch eine Anfrage beenden, auf deren Antwort Ollama noch rechnet."""
        super().cancel()
        stop = getattr(self.client, "abbrechen", None)
        if callable(stop):
            stop()

    # -- Was kann das Modell? --------------------------------------------------
    def faehigkeiten(self) -> set[str]:
        """Faehigkeiten des eingestellten Modells (einmal nachgefragt, dann gemerkt).
        Wirft OllamaFehler (laeuft nicht / Modell fehlt)."""
        model = self.model
        if model in self._caps:
            return self._caps[model]
        if self._openai:
            caps = {"completion", "tools"}  # unbekannt - Werkzeuge versuchen, Bilder nicht
        else:
            dienst = getattr(self.client, "dienst", None) or ollama.Dienst(self.adresse)
            caps = dienst.faehigkeiten(model)
            if not caps:
                caps = {"completion", "tools"}  # aeltere Ollama-Versionen melden nichts
        self._caps[model] = caps
        return caps

    def _caps_or_empty(self) -> set[str]:
        try:
            return self.faehigkeiten()
        except Exception:  # noqa: BLE001 - dann merkt es die eigentliche Anfrage
            return set()

    def _kann_werkzeuge(self) -> bool:
        return self.model not in self._ohne_werkzeuge and "tools" in self._caps_or_empty()

    def _sees_images(self) -> bool:
        return "vision" in self._caps_or_empty()

    # -- Hauptschleife ------------------------------------------------------
    def respond(self, user_text: str, on_text: StreamFn | None = None, max_tool_rounds: int | None = None,
                announce_limit: bool = True, allow_tools: bool = True, bilder: list | None = None) -> str:
        self.hit_limit = False
        self._client_pruefen()
        if self.client is not None:
            # Vorher pruefen, ob Ollama laeuft und das Modell da ist - dann kommt eine klare
            # Meldung, und der Verlauf bleibt unberuehrt.
            try:
                caps = self.faehigkeiten()
            except ollama.OllamaFehler as exc:
                self._check_cancel()
                text = self._fehler_meldung(exc)
                if on_text:
                    on_text(text)
                return text
            if allow_tools and "tools" not in caps and self.model not in self._gewarnt:
                self._gewarnt.add(self.model)
                if on_text:
                    on_text(ollama.OHNE_WERKZEUGE.format(modell=self.model, empfohlen=ollama.STANDARD_MODELL))
        kwargs = {"bilder": bilder} if bilder else {}
        return super().respond(user_text, on_text=on_text, max_tool_rounds=max_tool_rounds,
                               announce_limit=announce_limit, allow_tools=allow_tools, **kwargs)

    def _think_level(self) -> str:
        if self._thinking_off or "thinking" not in self._caps_or_empty():
            return "aus"
        from ..modelle import ollama_denken

        return "an" if ollama_denken(self.config, self.effort_override) else "aus"

    def _max_tokens(self, level: str) -> int:
        return int(self.config.ollama.max_tokens or 8192)

    def _turn_kwargs(self, level: str, tool_choice: str) -> dict[str, Any]:
        thinking = level != "aus"
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._request_messages(thinking),
            "max_tokens": self._max_tokens(level),
            "stream": True,
        }
        if self._kann_werkzeuge():
            kwargs["tools"] = self.registry.specs_openai()
            kwargs["tool_choice"] = tool_choice
        if self._openai:
            kwargs["stream_options"] = {"include_usage": True}
        elif "thinking" in self._caps_or_empty():
            kwargs["extra_body"] = {"think": thinking}  # sonst denkt z.B. Qwen 3.5 immer
        return kwargs

    def _simple_kwargs(self, messages: list[dict[str, Any]], max_tokens: int) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": max_tokens,
                                  "stream": False}
        if not self._openai and "thinking" in self._caps_or_empty():
            kwargs["extra_body"] = {"think": False}
        return kwargs

    def _request_messages(self, thinking: bool) -> list[dict[str, Any]]:
        out = super()._request_messages(thinking)
        if self._openai:
            out = [{k: v for k, v in m.items() if k != "reasoning_content"} for m in out]
        if not self._kann_werkzeuge() and out and out[0].get("role") == "system":
            out[0] = {**out[0], "content": str(out[0].get("content") or "") + _OHNE_WERKZEUGE_SYSTEM}
        return self._kuerzen_fuer_kontext(out)

    def _kuerzen_fuer_kontext(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Passt der Verlauf nicht in den Kontext, aeltere grosse Werkzeug-Ausgaben beim Senden
        kuerzen (die letzten beiden bleiben ganz). Der gespeicherte Verlauf bleibt unveraendert."""
        budget = self.verlauf_grenze()
        total = sum(_content_chars(m.get("content")) for m in messages[1:])
        if not budget or total <= budget:
            return messages
        tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
        out = list(messages)
        for i in tool_idx[:-2]:
            content = out[i].get("content")
            if isinstance(content, str) and len(content) > 500:
                total -= len(content) - 300 - len(_SHRUNK_NOTE)
                out[i] = {**out[i], "content": content[:300] + _SHRUNK_NOTE}
                if total <= budget:
                    break
        return out

    # -- Fehler ---------------------------------------------------------------
    def _retry_after_error(self, exc: Exception) -> bool:
        if getattr(exc, "art", "") == "keine_werkzeuge" and self.model not in self._ohne_werkzeuge:
            logger.warning("Ollama-Modell %s kann keine Werkzeuge - weiter ohne.", self.model)
            self._ohne_werkzeuge.add(self.model)
            caps = self._caps.get(self.model)
            if caps is not None:
                self._caps[self.model] = caps - {"tools"}
            return True
        return False

    def _fehler_meldung(self, exc: Exception) -> str:
        art = getattr(exc, "art", "")
        if art == "offline":
            return ollama.NICHT_ERREICHBAR.format(adresse=self.adresse)
        if art == "modell_fehlt":
            return ollama.MODELL_FEHLT.format(modell=self.model)
        return f"Ollama meldet: {str(exc)[:300]}"

    def _error_text(self, exc: Exception, stream: bool = False) -> str:
        if getattr(exc, "art", "") in ("offline", "modell_fehlt"):
            return "\n[" + self._fehler_meldung(exc) + "]"
        if type(exc).__name__ in ("APIConnectionError", "APITimeoutError"):
            return "\n[" + ollama.NICHT_ERREICHBAR.format(adresse=self.adresse) + "]"
        return super()._error_text(exc, stream)

    # -- Bilder: nie ein bezahlter Nebenaufruf ------------------------------
    def _describe_images(self, bilder: list) -> str:
        lines = []
        for i, bild in enumerate(bilder, 1):
            lines.append(f"[Bild {i}: {bild.platzhalter()} \u2013 {ollama.SIEHT_NICHTS}. Sag das deinem Menschen "
                         f"freundlich; Modelle wie {ollama.STANDARD_MODELL} koennen Bilder sehen.]")
        return "\n".join(lines)

    # -- Verlauf ------------------------------------------------------------
    def _overhead_chars(self) -> int:
        """System-Prompt und (wenn benutzt) Werkzeug-Beschreibungen - gehen bei jeder Anfrage mit."""
        chars = len(self.system_prompt or "")
        if self.model not in self._caps or self._kann_werkzeuge():
            chars += len(json.dumps(self.registry.specs_openai(), ensure_ascii=False))
        return chars

    def verlauf_grenze(self) -> int:
        kontext = int(self.config.ollama.kontext or 16384)
        frei = (kontext - _ANTWORT_RESERVE) * _ZEICHEN_PRO_TOKEN - self._overhead_chars()
        grenze = max(8000, frei)
        eigene = int(self.config.conversation.max_verlauf_zeichen or 0)
        return min(grenze, eigene) if eigene else grenze

    def _summary_limit(self) -> int:
        kontext = int(self.config.ollama.kontext or 16384)
        return max(6000, (kontext - _ANTWORT_RESERVE) * _ZEICHEN_PRO_TOKEN - 1500)
