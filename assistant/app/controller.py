"""Steuerung der App: dieselbe KI wie im Terminal, nur Ein-/Ausgabe ueber das Fenster.

AppController erbt von der Terminal-Oberflaeche (CLI) und uebernimmt damit alle
Befehle, Rueckfragen, Updates, Autostart-Pruefung usw. Ersetzt wird nur, WIE mit
dem Menschen gesprochen wird:
  * Text der KI       -> Ereignisse "chunk", "tool", "agent", "info"
  * print-Ausgaben    -> Systemkarten ("notice")
  * Rueckfragen/ja-nein -> Dialoge ("ask"), Antwort per /api/answer
  * Strg+C            -> Stopp-Knopf (provider.cancel)
Die Antwort laeuft in einem eigenen Thread, damit das Fenster frei bleibt.
"""
from __future__ import annotations

import io
import itertools
import os
import re
import subprocess
import sys
import threading
import time
from contextlib import redirect_stdout
from typing import Any, Callable

from .. import __version__
from ..anzeige import schoen
from ..cancel import Abgebrochen
from ..config import Config, save_setting, toml_string
from ..logging_setup import get_logger
from ..permissions import Risk
from ..ui.cli import CLI, JARVIS_HINT, KEY_HINT, _is_exit_phrase
from ..voice import VoiceOutput

logger = get_logger()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TOOL_LINE = re.compile(r"^\s*… nutze Werkzeug: (\S+)\s*$")
_AGENT_TOOL = re.compile(r"^\s*\[Agent (\w+)\] … nutze Werkzeug: (\S+)\s*$")
_AGENT_START = re.compile(r"^\s*>> Agent '(\w+)' startet: (.*)$")
_AGENT_END = re.compile(r"^\s*<< Agent '(\w+)' fertig\s*$")
_INFO_LINE = re.compile(r"^\s*\[(Ich arbeite weiter[^\]]*)\]\s*$")

COMMANDS = [
    ("/status", "Einstellungen & Sicherheitslage"),
    ("/gedaechtnis", "was die KI gelernt hat"),
    ("/kosten", "Token-Verbrauch & Kosten"),
    ("/update", "nach einer neuen Version schauen"),
    ("/versionen", "gesicherte alte Versionen"),
    ("/zurueck", "zu einer alten Version zurueck (Nr.)"),
    ("/autostart", "was startet die KI automatisch?"),
    ("/autostart entfernen alle", "automatische Starts abstellen"),
    ("/erlauben alles", "nie mehr nachfragen"),
    ("/erlauben fragen", "wieder nachfragen"),
    ("/neu", "neues Gespraech (Charakter & Profil frisch)"),
    ("/tutorial", "Nova zeigt dir, was sie kann"),
    ("/stuetzraeder", "Stuetzraeder an/aus"),
    ("/aussehen zuruecksetzen", "App wieder im Original-Aussehen"),
    ("/charakter", "Charakter anzeigen oder waehlen"),
    ("/stil", "Anrede, Laenge, Humor, Emojis"),
    ("/ueber-mich", "was die KI ueber dich weiss"),
    ("/verknuepfung", "Symbol fuer die App auf den Desktop"),
    ("/name", "der KI einen anderen Namen geben"),
    ("/sprache", "Stand der Spracheingabe"),
    ("/sprache einrichten", "Spracheingabe installieren"),
    ("/gehirn", "DeepSeek oder Claude - Schluessel einfach in den Chat einfuegen"),
    ("/terminal", "zur Terminal-Version wechseln"),
    ("/hilfe", "alle Befehle"),
    ("/beenden", "App schliessen"),
]


class _NoticeWriter(io.TextIOBase):
    """Sammelt print-Ausgaben und gibt sie als Systemkarte weiter."""

    def __init__(self, flush_fn: Callable[[str], None]):
        self._buf: list[str] = []
        self._flush_fn = flush_fn

    def write(self, text: str) -> int:
        self._buf.append(text)
        return len(text)

    def isatty(self) -> bool:
        return False

    def flush_notice(self) -> None:
        text = _ANSI.sub("", "".join(self._buf)).strip("\n")
        self._buf.clear()
        if text.strip():
            self._flush_fn(text)


class AppController(CLI):
    def __init__(self, config: Config, broadcast: Callable[[dict], None], started_by: str | None = None):
        super().__init__(config, started_by=started_by)
        self.broadcast = broadcast
        self.brain.provider.wait_fn = lambda: self._event({"type": "thinking", "on": True})
        self.tool_ctx.extra["cancel_event"] = self.brain.provider.cancel_event
        self.busy = False
        self.history: list[dict] = []
        self.on_quit: Callable[[int], None] = lambda code: None
        self._lock = threading.Lock()
        self._asks: dict[str, dict] = {}
        self._ask_ids = itertools.count(1)
        self._writer: _NoticeWriter | None = None
        self._voice_lock = threading.Lock()
        self._live = None            # laufender Jarvis-Modus (live.LiveLoop)
        self._live_turn = None       # der Jarvis-Modus (LiveLoop), dem die laufende Antwort gehoert
        self._jarvis_lock = threading.Lock()
        self._drop_turn = False      # die angehaltene Antwort ganz zuruecknehmen (Nachtrag im Sprachmodus)
        self._live_setup = False     # Live-Mitschrift wird gerade eingerichtet
        self._live_setup_failed = False
        self._speaker = None
        self.tool_ctx.extra["on_appearance"] = lambda: self._event({"type": "appearance"})
        # Sphaere: reagiert auf deine Stimme beim Mikrofon-Knopf / F2
        self.voice_capture.on_level = lambda value: self._event({"type": "mic", "level": value})

    # -- Ereignisse -----------------------------------------------------------
    def _event(self, event: dict) -> None:
        try:
            self.broadcast(event)
        except Exception as exc:  # noqa: BLE001
            logger.info("Ereignis nicht gesendet: %s", exc)

    def _notice(self, text: str, level: str = "info") -> None:
        if not text.strip():
            return
        text = schoen(text)
        self.history.append({"role": "notice", "text": text, "level": level})
        self._event({"type": "notice", "level": level, "text": text})

    def state(self) -> dict:
        usage = self.brain.usage
        _usd, eur = self.brain.cost()
        problem = self.voice_capture.problem() if self.config.voice.f2_aufnahme else None
        return {
            "name": self.config.ki.name,
            "meaning": self.config.ki.bedeutung,
            "version": __version__,
            "provider": self.config.active_provider,
            "model": self.config.active_model,
            "busy": self.busy,
            "auto_confirm": bool(self.permissions.settings.auto_confirm),
            "safe_mode": bool(self.permissions.settings.safe_mode),
            "speak": bool(self.voice_out.enabled),
            "voice_problem": problem,
            "tokens": usage.total_tokens,
            "eur": round(eur, 4),
            "api_key_missing": not self.config.api_key,
            "provider_name": schoen({"deepseek": "DeepSeek", "claude": "Claude (Anthropic)"}.get(
                self.config.active_provider, self.config.active_provider)),
            "update": {"new": self._pending_update.new} if self._pending_update else None,
            "jarvis": self._jarvis_active(),
            "jarvis_state": self._live.state if self._jarvis_active() else "off",  # fuer ein neu geoeffnetes Fenster
            "jarvis_live": bool(self._jarvis_active() and self._live.ear.live),
            "stuetzraeder": self.training_wheels_state(),
            "full_access": bool(self.permissions.settings.allow_full_filesystem),
            "tutorial_done": self._tutorial_done(),
            "started_by": self.started_by,
            "commands": [{"cmd": c, "help": schoen(h)} for c, h in COMMANDS],
        }

    def _state_changed(self) -> None:
        self._event({"type": "state", "state": self.state()})

    # -- Ausgabe der KI in Ereignisse uebersetzen -------------------------------
    def _emit(self, chunk: str) -> None:
        self._event({"type": "thinking", "on": False})
        # Werkzeug-/Agenten-Zeilen kommen als eigene Teile; normaler Text unveraendert.
        if "nutze Werkzeug:" in chunk or "Agent '" in chunk or "[Ich arbeite weiter" in chunk:
            rest: list[str] = []
            for line in chunk.split("\n"):
                if m := _AGENT_TOOL.match(line):
                    self._event({"type": "tool", "name": m.group(2), "agent": m.group(1)})
                    self._live_hook("tool")
                elif m := _TOOL_LINE.match(line):
                    self._event({"type": "tool", "name": m.group(1), "agent": None})
                    self._live_hook("tool")
                elif m := _AGENT_START.match(line):
                    self._event({"type": "agent", "phase": "start", "role": m.group(1), "task": m.group(2)})
                    self._live_hook("tool")
                elif m := _AGENT_END.match(line):
                    self._event({"type": "agent", "phase": "end", "role": m.group(1), "task": ""})
                elif m := _INFO_LINE.match(line):
                    self._event({"type": "info", "text": m.group(1)})
                else:
                    rest.append(line)
            chunk = "\n".join(rest)
            if not chunk.strip():
                return
        self._answer_parts.append(chunk)
        self._live_hook("text", chunk)
        self._event({"type": "chunk", "text": chunk})

    # -- Rueckfragen als Dialog -------------------------------------------------
    def _ask(self, kind: str, text: str, options: list[tuple[str, str]], risk: str | None = None,
             default: str = "nein") -> str:
        """Zeigt einen Dialog und wartet (im Arbeits-Thread) auf die Antwort."""
        if self._writer:
            self._writer.flush_notice()  # erst zeigen, was vor der Frage ausgegeben wurde
        ask_id = f"q{next(self._ask_ids)}"
        waiter = {"event": threading.Event(), "value": default, "options": [v for v, _ in options]}
        self._asks[ask_id] = waiter
        clean = _ANSI.sub("", text).strip()
        self._event({"type": "ask", "id": ask_id, "kind": kind, "risk": risk, "text": clean,
                     "options": [{"value": v, "label": label} for v, label in options]})
        self._live_hook("ask", clean)
        cancel = self.brain.provider.cancel_event
        try:
            while not waiter["event"].wait(0.25):
                if cancel.is_set():
                    waiter["value"] = default
                    break
        finally:
            self._asks.pop(ask_id, None)
            self._event({"type": "ask_done", "id": ask_id})
        return waiter["value"]

    def answer(self, ask_id: str, value: str) -> bool:
        waiter = self._asks.get(ask_id)
        if waiter is None:
            return False
        waiter["value"] = value
        waiter["event"].set()
        return True

    def _permission_answer(self, message: str, risk: Risk) -> str:
        options = [("einmal", "Einmal erlauben")]
        if risk != Risk.AUTOSTART:
            options.append(("immer", "Immer erlauben"))
        options.append(("nein", "Nein"))
        return self._ask("permission", message, options, risk=risk.name)

    def _ask_yes(self, question: str, default: bool = False) -> bool:
        text = re.sub(r"\[(j/N|J/n)\]\s*$", "", question.strip()).strip()
        value = self._ask("question", text, [("ja", "Ja"), ("nein", "Nein")], default="ja" if default else "nein")
        return value == "ja"

    def _set_auto_confirm(self, value: bool) -> None:
        super()._set_auto_confirm(value)
        self._state_changed()

    # -- Senden -----------------------------------------------------------------
    def send(self, text: str, model_text: str | None = None, live=None) -> tuple[bool, str]:
        """text = was angezeigt wird; model_text = was die KI bekommt (z.B. mit Sprachmodus-Hinweis);
        live = der Jarvis-Modus, dem diese Antwort gehoert (bekommt Text, Werkzeuge und das Ende)."""
        text = (text or "").strip()
        if not text:
            return False, "Leere Nachricht"
        shown = None
        from ..schluessel import find_key, mask

        key = find_key(text)
        if key and not text.startswith("/"):
            # Schluessel eingefuegt: einrichten statt an die KI schicken; angezeigt wird er nur gekuerzt
            text, shown = f"/schluessel {key}", f"\U0001F511 Schl\u00fcssel {mask(key)}"
        elif key:
            shown = text.replace(key, mask(key))
        with self._lock:
            if self.busy:
                return False, "Ich arbeite noch an der letzten Nachricht - Stopp, um sie anzuhalten."
            self.busy = True
            self._live_turn = live
            self._drop_turn = False
        self.brain.provider.cancel_event.clear()
        threading.Thread(target=self._work, args=(text, None, model_text, shown), name="ki-antwort",
                         daemon=True).start()
        return True, ""

    def run_background(self, fn: Callable[[], Any]) -> None:
        """Etwas wie eine Nachricht ausfuehren (Ausgaben -> Systemkarten), z.B. Update-Pruefung."""
        with self._lock:
            if self.busy:
                return
            self.busy = True
        self.brain.provider.cancel_event.clear()
        threading.Thread(target=self._work, args=(None, fn), name="ki-hintergrund", daemon=True).start()

    def _work(self, text: str | None, fn: Callable[[], Any] | None = None, model_text: str | None = None,
              shown: str | None = None) -> None:
        self._state_changed()
        writer = _NoticeWriter(self._notice)
        self._writer = writer
        quit_code = None
        try:
            with redirect_stdout(writer):
                if fn is not None:
                    quit_code = fn()
                elif text.startswith("/"):
                    self.history.append({"role": "user", "text": shown or text})
                    self._event({"type": "user", "text": shown or text})
                    quit_code = self._command(text)
                elif not self.config.api_key:
                    self.history.append({"role": "user", "text": text})
                    self._event({"type": "user", "text": text})
                    self._notice(KEY_HINT.replace("\n  ", "\n- "), "warn")
                else:
                    self._answer(text, model_text)
        except Exception as exc:  # noqa: BLE001 - die App darf daran nicht sterben
            logger.exception("Fehler in der App")
            from ..schluessel import friendly_error

            hint = friendly_error(exc, self.config.active_provider)
            message = schoen(hint) if hint else f"Da ist etwas schiefgegangen: {exc}"
            self.history.append({"role": "error", "text": message})
            self._event({"type": "error", "text": message})
        finally:
            writer.flush_notice()
            self._writer = None
            with self._lock:  # erst den Besitzer der Antwort merken, dann frei geben
                live_turn, self._live_turn = self._live_turn, None
                self.busy = False
            self._state_changed()
            if live_turn is not None:
                live_turn.on_turn_end()
        if quit_code is not None:
            self.on_quit(quit_code)

    def _command(self, text: str) -> int | None:
        if text.split()[0].lower() == "/app":
            print("Du bist schon in der App.")
            return None
        if text.split()[0].lower() == "/terminal":
            return self._open_terminal()
        quit_now = self._handle_command(text)  # /beenden, oder Neustart nach Update
        if text.split()[0].lower() == "/name":
            self._state_changed()  # neuer Name gleich in der Seitenleiste
        return self.exit_code if quit_now else None

    def _answer(self, text: str, model_text: str | None = None) -> None:
        entry = {"role": "user", "text": text}
        self.history.append(entry)
        self._event({"type": "user", "text": text})
        self._event({"type": "start"})
        self._answer_parts: list[str] = []
        snapshot = self.brain.provider.history_snapshot()
        try:
            answer = self.brain.respond(model_text or text, on_text=self._emit)
        except KeyboardInterrupt:  # Stopp-Knopf (Abgebrochen) - oder Strg+C im Hintergrund
            drop, self._drop_turn = self._drop_turn, False
            if drop and self.brain.provider.drop_turn(snapshot, model_text or text):
                # Sprachmodus: "Wie wird das Wetter?" ... "in Berlin" -> eine Frage
                if entry in self.history:
                    self.history.remove(entry)
                self._event({"type": "thinking", "on": False})
                self._event({"type": "retract"})
                return
            self.brain.provider.abort_turn(snapshot, text)
            self.history.append({"role": "assistant", "text": "".join(self._answer_parts) + "\n\n*(angehalten)*"})
            self._event({"type": "thinking", "on": False})
            self._event({"type": "stopped"})
            return
        except Exception:
            self.brain.provider.abort_turn(snapshot, text)
            raise
        self.history.append({"role": "assistant", "text": "".join(self._answer_parts) or answer})
        self._event({"type": "thinking", "on": False})
        self._event({"type": "done"})
        self._last_answer = "".join(self._answer_parts) or answer
        if self.voice_out.enabled and not self._jarvis_active():
            threading.Thread(target=self._speak_aloud, args=(answer,), daemon=True).start()

    def _speak_aloud(self, answer: str) -> None:
        """Vorlesen am PC (Schalter 'Vorlesen') - die Sphaere spricht mit."""
        self._event({"type": "speaking", "on": True})
        try:
            self.voice_out.speak(answer)
        finally:
            self._event({"type": "speaking", "on": False})

    def stop(self) -> None:
        if self._live is not None:
            self._live.hush()
        self.brain.provider.cancel()
        for waiter in list(self._asks.values()):
            waiter["event"].set()
        self.voice_out.stop()

    # -- Charakter & Profil (Einstellungen-Fenster der App) --------------------------
    def profile(self) -> dict:
        from ..profil import ABOUT_FIELDS, CHARACTERS, STYLE_OPTIONS, active_character

        current = active_character(self.config)
        s = self.config.style
        return {
            "name": self.config.ki.name,
            "meaning": self.config.ki.bedeutung,
            "character": current,
            "characters": [{"id": c.key, "name": schoen(c.name), "description": schoen(c.description),
                            "active": c.key == current} for c in CHARACTERS],
            "persona_text": self.config.persona_text,
            "style": {"anrede": s.anrede, "laenge": s.laenge, "humor": s.humor, "emojis": s.emojis},
            "style_options": {k: [{"value": v, "label": schoen(label)} for v, label in opts]
                              for k, opts in STYLE_OPTIONS.items()},
            "about": dict(self.config.about),
            "about_fields": [{"key": k, "label": schoen(label), "placeholder": schoen(ph)}
                             for k, label, ph in ABOUT_FIELDS],
            "values_text": self.config.values_text,
        }

    def save_profile(self, data: dict) -> dict:
        """Speichert, was im Einstellungen-Fenster geaendert wurde. Gilt ab /neu."""
        from ..profil import apply_character, save_about, save_persona, save_values, set_style

        name = str(data.get("name", "")).strip()
        if name and name != self.config.ki.name:
            if len(name) > 40 or any(c in name for c in '\n"\\'):
                raise ValueError("Bitte einen kurzen Namen ohne Anfuehrungszeichen.")
            save_setting(self.config.project_root, "ki", "name", toml_string(name))
            self.config.ki.name = name
        if "meaning" in data:
            meaning = " ".join(str(data.get("meaning") or "").split())[:200]
            if meaning != self.config.ki.bedeutung:
                save_setting(self.config.project_root, "ki", "bedeutung", toml_string(meaning))
                self.config.ki.bedeutung = meaning
        if data.get("character") and data["character"] != "eigen":
            apply_character(self.config, str(data["character"]))
        elif isinstance(data.get("persona_text"), str) and data["persona_text"] != self.config.persona_text:
            save_persona(self.config, data["persona_text"])
        for key, value in (data.get("style") or {}).items():
            if getattr(self.config.style, key, None) != value:
                set_style(self.config, str(key), str(value))
        if isinstance(data.get("about"), dict):
            save_about(self.config, {str(k): str(v) for k, v in data["about"].items()})
        if isinstance(data.get("values_text"), str) and data["values_text"] != self.config.values_text:
            save_values(self.config, data["values_text"])
        self._state_changed()
        return self.profile()

    def memory_facts(self) -> dict:
        facts = self.memory.top_facts(500)
        return {"facts": [{"id": f.id, "category": f.category, "content": f.content,
                           "importance": f.importance} for f in facts],
                "count": self.memory.count_facts()}

    def memory_action(self, data: dict) -> dict:
        action = data.get("action")
        if action == "delete":
            ok = self.memory.forget(int(data.get("id", 0)))
        elif action == "add":
            content = str(data.get("content", "")).strip()
            ok = bool(content) and bool(self.memory.remember(content[:1000], category=str(data.get("category") or "notiz")))
        else:
            return {"ok": False, "error": f"Unbekannt: {action}"}
        return {"ok": bool(ok), **self.memory_facts()}

    def _new_conversation(self) -> None:
        super()._new_conversation()
        self.history.clear()
        self._event({"type": "reset"})  # Fenster leert den Chat
        self._state_changed()

    def _after_provider_change(self) -> None:
        self._state_changed()

    def _open_terminal(self) -> int | None:
        """Zur Terminal-Version wechseln: Terminal oeffnen, App schliessen (dasselbe Gedaechtnis)."""
        from .launcher import spawn_terminal

        if not spawn_terminal(self.config.project_root, wait_for_pid=os.getpid()):
            print("Das Terminal liess sich hier nicht oeffnen - starte start.bat (bzw. KI.exe).")
            return None
        print("Ich oeffne die Terminal-Version und schliesse die App …")
        self._event({"type": "bye"})
        return 0

    # -- Gehirn & Schluessel (Einstellungen in der App) -----------------------------
    def setup_info(self) -> dict:
        from ..schluessel import describe

        info = describe(self.config)
        for item in info["providers"]:
            item["name"], item["info"] = schoen(item["name"]), schoen(item["info"])
        return info

    def setup_save(self, data: dict) -> dict:
        """Schluessel pruefen und speichern, Gehirn waehlen."""
        from ..schluessel import PROVIDERS, find_key, setup

        provider = str(data.get("provider") or "").lower() or None
        if provider and provider not in PROVIDERS:
            return {"ok": False, "kind": "other", "error": f"Unbekanntes Gehirn '{provider}'."}
        raw = str(data.get("api_key") or "").strip()
        key = find_key(raw) or (raw or None)
        with self._lock:
            if self.busy:
                return {"ok": False, "kind": "busy", "error": "Ich arbeite gerade - gleich nochmal versuchen."}
            self.busy = True
        self._state_changed()  # andere Fenster sehen: die KI prueft gerade
        try:
            result = setup(self.config, key=key, provider=provider, test=not data.get("force"))
            if not result["ok"]:
                return {"ok": False, "kind": result["kind"], "error": schoen(result["message"])}
            fresh = self.brain.switch_provider()
            message = result["message"] + (" Wir beginnen ein neues Gespraech." if fresh else "")
            self._notice(message)
            return {"ok": True, "message": schoen(message), "setup": self.setup_info()}
        finally:
            with self._lock:
                self.busy = False
            self._state_changed()

    # In der App oeffnen /jarvis und /tutorial die Ansichten im Fenster (statt der Terminal-Versionen).
    def _jarvis_terminal(self) -> None:
        result = self.jarvis("start", "client")
        if result.get("ok"):
            self._event({"type": "open", "what": "jarvis"})
        else:
            print(result.get("error") or "Der Jarvis-Modus ging nicht.")

    def _tutorial_terminal(self) -> None:
        self._event({"type": "open", "what": "tutorial"})

    # -- Jarvis-Modus: freihaendig und live reden (live.py) ---------------------------
    def _jarvis_active(self) -> bool:
        return self._live is not None and not self._live.stop_event.is_set()

    def _live_hook(self, kind: str, text: str = "") -> None:
        live = self._live_turn
        if live is None:
            return
        if kind == "text":
            live.on_text(text)
        elif kind == "tool":
            live.on_tool()
        elif kind == "ask":
            live.on_ask(text)

    def jarvis(self, action: str, tts: str = "client", turn: Any = None, seq: Any = None,
               progress: bool = False) -> dict:
        """progress=True: das Fenster meldet jeden gesagten Satz (spoken mit seq)."""
        if action in ("start", "stop"):
            with self._jarvis_lock:  # Doppelklick / Befehl + Knopf: nur EIN Jarvis-Modus
                return self._jarvis_start_stop(action, tts, bool(progress))
        if action == "spoken":  # Fenster hat vorgelesen (seq = ein Satz, ohne seq = alles) -> weiter zuhoeren
            if self._live is not None:
                self._live.spoken(_int_or_none(turn), _int_or_none(seq))
            return {"ok": True}
        if action == "hush":  # Stopp im Jarvis-Fenster
            if self._live is not None:
                self._live.hush()
            return {"ok": True}
        return {"ok": False, "error": f"Unbekannt: {action}"}

    def _jarvis_start_stop(self, action: str, tts: str, progress: bool = False) -> dict:
        from ..live import LiveLoop, LocalVoice, WindowVoice, live_available, recognizer_factory

        if action == "start":
            if self._jarvis_active():
                return {"ok": True, "live": self._live.ear.live}
            problem = self.voice_capture.problem()
            if problem:
                return {"ok": False, "error": schoen(problem), "setup": not getattr(sys, "frozen", False)}
            root = self.config.project_root
            if tts == "server":
                from ..voice import Speaker

                if self._speaker is None:
                    self._speaker = Speaker(self.config.voice.sprache or "de")
                voice_out = LocalVoice(self._speaker, emit=self._event)
            else:
                voice_out = WindowVoice(self._event, progress=progress)
            factory = recognizer_factory(root, self.config.voice)
            host = _LiveHost(self)
            loop = LiveLoop(host, voice_out, self.config.voice, recognizer_factory=factory)
            host.loop = loop
            self._live = loop
            self.brain.provider.effort_override = (self.config.voice.live_denktiefe or "").strip() or None
            threading.Thread(target=self._run_live, args=(loop,), name="jarvis", daemon=True).start()
            if factory is None and self.config.voice.live_mitschrift and not live_available(root, self.config.voice):
                self._setup_live_in_background(loop)
            self._state_changed()
            return {"ok": True, "live": factory is not None}
        if self._live is not None:
            self._live.stop()
        self._state_changed()
        return {"ok": True}

    def _run_live(self, loop) -> None:
        try:
            loop.run()
        except Exception as exc:  # noqa: BLE001 - die App darf daran nicht sterben
            logger.exception("Jarvis-Modus")
            self._event({"type": "jarvis", "state": "off", "error": f"Sprachmodus: {exc}"})
        finally:
            with self._jarvis_lock:  # nicht mit einem gleichzeitigen Neustart kreuzen
                if self._live is loop:
                    self._live = None
                    self.brain.provider.effort_override = None
            self._state_changed()

    def _setup_live_in_background(self, loop) -> None:
        """Erster Jarvis-Start: Live-Mitschrift (vosk + Modell) nebenbei einrichten."""
        from ..live import recognizer_factory, setup_live

        from ..voice import _importable

        if self._live_setup or self._live_setup_failed or (getattr(sys, "frozen", False) and not _importable("vosk")):
            return
        self._live_setup = True

        def work() -> None:
            try:
                self._notice("Ich richte einmalig die Live-Mitschrift ein (~50 MB). Bis dahin verstehe ich "
                             "dich trotzdem - nur ohne Mitschreiben beim Sprechen.")
                last = [0.0]

                def progress(done: int, total: int) -> None:
                    now = time.monotonic()
                    if total and now - last[0] > 1.0:
                        last[0] = now
                        self._event({"type": "info", "text": f"Live-Mitschrift: {done * 100 // total} % geladen"})

                ok, message = setup_live(self.config.project_root, self.config.voice, progress=progress)
                self._live_setup_failed = not ok  # nicht bei jedem Start erneut versuchen
                self._notice(message, "info" if ok else "warn")
                factory = recognizer_factory(self.config.project_root, self.config.voice) if ok else None
                if factory is not None and self._live is loop:
                    loop.ear.enable_live(factory)
            finally:
                self._live_setup = False

        threading.Thread(target=work, name="live-einrichten", daemon=True).start()

    # -- Tutorial & Aussehen --------------------------------------------------------
    def _tutorial_done(self) -> bool:
        from ..tutorial import is_done

        return is_done(self.config.project_root)

    def tutorial(self) -> dict:
        from ..tutorial import steps

        shown = [{k: (schoen(v) if k in ("titel", "text", "zeigen") and isinstance(v, str) else v)
                  for k, v in step.items()} for step in steps(self.config)]  # ids/ziele bleiben unveraendert
        return {"steps": shown, "done": self._tutorial_done()}

    def tutorial_action(self, action: str) -> dict:
        from ..tutorial import mark_done

        if action == "done":
            mark_done(self.config.project_root)
            self._state_changed()
        return {"ok": True}

    def appearance(self) -> dict:
        from .. import aussehen

        return {"settings": aussehen.load(self.config.project_root),
                "has_css": bool(aussehen.css(self.config.project_root))}

    def custom_css(self) -> str:
        from .. import aussehen

        return aussehen.css(self.config.project_root)

    # -- Schalter -----------------------------------------------------------------
    def toggle(self, name: str, value: bool) -> None:
        if name == "stuetzraeder":  # die Oberflaeche hat beim Abschalten schon gewarnt
            self.set_training_wheels(bool(value))
            self._state_changed()
            return
        if name == "erlauben":
            self.permissions.settings.auto_confirm = bool(value)
            try:
                save_setting(self.config.project_root, "permissions", "auto_confirm", "true" if value else "false")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Einstellung nicht gespeichert: %s", exc)
        elif name == "vorlesen":
            if value and not self.voice_out.enabled:
                self.voice_out = VoiceOutput(True)
                if not self.voice_out.enabled:
                    self._notice("Vorlesen ist noch nicht eingerichtet - schreib `/sprache einrichten vorlesen`.", "warn")
            elif not value:
                self.voice_out.enabled = False
        self._state_changed()

    # -- Spracheingabe (Mikrofon-Knopf / F2 im Fenster) -------------------------------
    def voice(self, action: str) -> dict:
        with self._voice_lock:
            if action == "start":
                problem = self.voice_capture.problem()
                if problem:
                    frozen = getattr(sys, "frozen", False)
                    return {"ok": False, "error": problem, "setup": not frozen}
                try:
                    self.voice_capture.start()
                except Exception as exc:  # noqa: BLE001
                    return {"ok": False, "error": str(exc)}
                self._event({"type": "voice", "state": "recording"})
                return {"ok": True}
            if action == "cancel":
                self.voice_capture.cancel()
                self._event({"type": "voice", "state": "idle"})
                return {"ok": True}
            if action == "stop":
                self._event({"type": "voice", "state": "recognizing"})
                try:
                    text = self.voice_capture.stop()
                except Exception as exc:  # noqa: BLE001
                    self._event({"type": "voice", "state": "idle", "error": str(exc)})
                    return {"ok": False, "error": str(exc)}
                self._event({"type": "voice", "state": "idle", "text": text})
                return {"ok": True, "text": text}
        return {"ok": False, "error": f"Unbekannt: {action}"}

    # -- Start / Neustart / Ende -----------------------------------------------------
    def startup(self) -> None:
        """Nach dem Oeffnen des Fensters: Hinweise und (hoechstens taeglich) Update-Pruefung."""
        if not self.config.api_key:
            self._notice(KEY_HINT.replace("\n  ", "\n- "), "warn")
        elif self.config.provider_auto_switched:
            self._notice(f"Fuer {self.config.provider_auto_switched} ist kein Schluessel da - ich nutze deshalb "
                         f"{self.config.active_provider}. Wechseln: /gehirn")
        self._start_update_watch()

        def check() -> int | None:
            return self.exit_code if self._startup_update() else None

        self.run_background(check)

    def _restart(self, kind: str) -> bool:
        """Nach Update/Zurueck: die App mit der neuen Version neu oeffnen."""
        if kind == "exe":
            try:
                self.updater.restart_exe(["--app"])
                print("Starte die neue Version …")
            except Exception as exc:  # noqa: BLE001
                print(f"Bitte starte die App jetzt neu ({exc}).")
            self.exit_code = 0
            return True
        env = dict(os.environ, KI_NEUSTART_VON=str(os.getpid()))
        exe = sys.executable
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if sys.platform == "win32" and os.path.exists(pythonw):
            exe = pythonw  # ohne schwarzes Konsolenfenster
        try:
            subprocess.Popen([exe, "-m", "assistant", "--app"], cwd=str(self.config.project_root), env=env)
            print("Starte die neue Version …")
        except Exception as exc:  # noqa: BLE001
            print(f"Bitte starte die App jetzt neu ({exc}).")
        self.exit_code = 0
        return True

    def shutdown(self) -> None:
        if self._live is not None:
            self._live.stop()
        self._stop_watch.set()
        self.stop()
        try:
            with redirect_stdout(io.StringIO()):
                self._shutdown()  # Zusammenfassung ins Gedaechtnis, Datenbank schliessen
        except Exception as exc:  # noqa: BLE001
            logger.warning("Beim Beenden: %s", exc)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class _LiveHost:
    """Verbindet den Jarvis-Modus (live.LiveLoop) mit der App."""

    def __init__(self, ctl: AppController):
        self.ctl = ctl
        self.loop = None

    def event(self, event: dict) -> None:
        if self.ctl._live is not self.loop:
            return  # ein alter, schon beendeter Jarvis-Modus - nichts mehr anzeigen
        if event.get("error"):
            event = dict(event, error=schoen(event["error"]))
        self.ctl._event(event)

    def busy(self) -> bool:
        return bool(self.ctl.busy)

    def start_turn(self, text: str) -> bool:
        ok, _err = self.ctl.send(text, model_text=text + JARVIS_HINT, live=self.loop)
        return ok

    def cancel_turn(self, drop: bool) -> None:
        if self.ctl._live_turn is not self.loop:
            return  # nur eigene Antworten anhalten (nicht z.B. eine getippte Nachricht)
        self.ctl._drop_turn = drop
        self.ctl.brain.provider.cancel()

    def transcribe(self, pcm: bytes) -> str:
        return self.ctl.voice_capture.transcribe(pcm)

    def pending_ask(self) -> dict | None:
        for ask_id, waiter in reversed(list(self.ctl._asks.items())):
            return {"id": ask_id, "options": waiter.get("options", [])}
        return None

    def answer_ask(self, ask_id: str, value: str) -> None:
        self.ctl.answer(ask_id, value)

    def is_exit(self, text: str) -> bool:
        return _is_exit_phrase(text)
