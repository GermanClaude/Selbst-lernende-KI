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
import math
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Callable

from .. import __version__
from ..anzeige import schoen
from ..cancel import Abgebrochen
from ..config import Config, save_setting, toml_string
from ..live import staying, wait_until_quiet
from ..logging_setup import get_logger
from ..modelle import kurzbeschreibung
from ..permissions import Risk
from ..ui.cli import BILD_HINWEIS, CLI, JARVIS_HINT, KEY_HINT, _is_exit_phrase, upload_kante, vorlesetext
from ..sehen.dienst import ist_still
from ..voice import VoiceOutput

logger = get_logger()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TOOL_LINE = re.compile(r"^\s*… nutze Werkzeug: (\S+)\s*$")
_AGENT_TOOL = re.compile(r"^\s*\[Agent (\w+)\] … nutze Werkzeug: (\S+)\s*$")
_AGENT_START = re.compile(r"^\s*>> Agent '(\w+)' startet: (.*)$")
_AGENT_END = re.compile(r"^\s*<< Agent '(\w+)' fertig\s*$")
_INFO_LINE = re.compile(r"^\s*\[(Ich arbeite weiter[^\]]*)\]\s*$")
_CLIENT_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_CF_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{20,200}$")
_CF_KONTO = re.compile(r"^[0-9a-fA-F]{32}$")
_UPLOAD_TAGE = 30  # hochgeladene Bilder (nur fuer die Anzeige) so lange aufheben

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
    ("/gehirn", "DeepSeek, Claude oder Ollama - Schluessel einfach in den Chat einfuegen"),
    ("/ollama", "Ollama: kostenlose KI auf deinem PC (Stand, Modelle laden)"),
    ("/afk", "ich bin weg - die KI arbeitet allein weiter (mit Bericht)"),
    ("/sehen", "Live-Sehen: Nova schaut auf Bildschirm/Webcam (an, aus, pause, status)"),
    ("/modell", "Modell waehlen - schnell oder besonders stark"),
    ("/denken", "wie gruendlich die KI nachdenkt (schnell ... maximal)"),
    ("/feedback", "Feedback & Bewertung an den Entwickler schicken"),
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
        self.tool_ctx.extra["on_model"] = self._model_changed
        # Warteschlange: Nachrichten, die waehrend einer Antwort geschickt werden, kommen danach dran.
        self._queue: list[dict] = []
        self._queue_ids = itertools.count(1)
        self._front = 0              # so viele Eintraege vorne sind "sofort" (Unterbrechen/Rueckkehr)
        self._last_qid = 0           # zuletzt vergebene Warteschlangen-Nummer
        self._turn_mark = 0          # ... beim Beginn der laufenden Antwort (spaeter = waehrenddessen getippt)
        self._afk_dropped = False    # vorgemerkter AFK-Modus verworfen -> Hinweis zeigen
        self._closing = False
        # AFK-Modus (abwesend.py): vorgemerkt / laufend / Bericht fuer die Rueckkehr
        self._afk_pending: dict | None = None
        self._afk = None
        self._afk_return: tuple[float, str] | None = None  # (Beginn der Abwesenheit, Bericht)
        self.tool_ctx.extra["afk_start"] = self._afk_request
        self.tool_ctx.extra["afk_update"] = self._state_changed
        self._cloudflare_http = None  # fuer Tests austauschbar (None = echtes Netz)
        self._ollama_caps: dict[tuple[str, str], list] = {}  # (Adresse, Modell) -> Faehigkeiten
        # Live-Sehen: wartende Wortmeldung (nur die neueste) und ob gerade eine laeuft
        self._sehen_pending = None
        self._sehen_turn = False
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
            "model_name": schoen(kurzbeschreibung(self.config)),
            "busy": self.busy,
            "max_bilder": max(1, int(self.config.bilder.max_bilder_pro_nachricht or 10)),
            "queue": [{"id": item["id"], "text": item["shown"] or item["text"],
                       "images": list(item.get("images") or [])} for item in list(self._queue)],
            "afk": self._afk.status() if self._afk is not None else None,
            "afk_pending": self._afk_pending is not None,
            "sehen": self.sehen.status(),
            "auto_confirm": bool(self.permissions.settings.auto_confirm),
            "safe_mode": bool(self.permissions.settings.safe_mode),
            "speak": bool(self.voice_out.enabled),
            "voice_problem": problem,
            "tokens": usage.total_tokens,
            "eur": round(eur, 4),
            "kostenlos": bool(self.config.kostenlos),
            "ollama_pull": self.ollama_lader.zustand() if hasattr(self, "ollama_lader") else None,
            "api_key_missing": not self.config.api_key,
            "provider_name": schoen({"deepseek": "DeepSeek", "claude": "Claude (Anthropic)",
                                     "ollama": "Ollama (kostenlos)"}.get(
                self.config.active_provider, self.config.active_provider)),
            "update": {"new": self._pending_update.new} if self._pending_update else None,
            "update_status": self._update_status(),
            "voice_autosend": bool(self.config.voice.sofort_senden),
            "jarvis": self._jarvis_active(),
            "jarvis_state": self._live.state if self._jarvis_active() else "off",  # fuer ein neu geoeffnetes Fenster
            "jarvis_live": bool(self._jarvis_active() and self._live.ear.live),
            "stuetzraeder": self.training_wheels_state(),
            "full_access": bool(self.permissions.settings.allow_full_filesystem),
            "tutorial_done": self._tutorial_done(),
            "feedback_due": self._feedback_due(),
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
        clean = _ANSI.sub("", text).strip()
        event = {"type": "ask", "id": ask_id, "kind": kind, "risk": risk, "text": clean,
                 "options": [{"value": v, "label": label} for v, label in options]}
        waiter["ask"] = event  # fuer neu verbundene Fenster (open_asks)
        self._asks[ask_id] = waiter
        self._event(event)
        self._live_hook("ask", clean)
        cancel = self.brain.provider.cancel_event
        try:
            while not waiter["event"].wait(0.25):
                if cancel.is_set():  # angehalten: nie "ja" daraus machen
                    waiter["value"] = "nein" if "nein" in waiter["options"] else default
                    break
        finally:
            self._asks.pop(ask_id, None)
            self._event({"type": "ask_done", "id": ask_id})
        return waiter["value"]

    def open_asks(self) -> list[dict]:
        """Rueckfragen, die gerade auf eine Antwort warten (fuer ein neu verbundenes Fenster)."""
        return [dict(w["ask"]) for w in list(self._asks.values()) if "ask" in w]

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
    def send(self, text: str, model_text: str | None = None, live=None, bilder: list | None = None,
             images: list | None = None, client_id: str | None = None) -> tuple[bool, str]:
        """text = was angezeigt wird; model_text = was die KI bekommt (z.B. mit Sprachmodus-Hinweis);
        live = der Jarvis-Modus, dem diese Antwort gehoert (bekommt Text, Werkzeuge und das Ende).
        bilder = schon vorbereitete Bilder (assistant.bilder.Bild) fuer die KI, images = deren
        Anzeige [{url, name}], client_id = Kennung des Fensters fuer das Echo."""
        text = (text or "").strip()
        if not text and not bilder:
            return False, "Leere Nachricht"
        text, shown = _mask_key(text)
        with self._lock:
            if self.busy:
                return False, "Ich arbeite noch an der letzten Nachricht - Stopp, um sie anzuhalten."
            self.busy = True
            self._live_turn = live
            self._drop_turn = False
            self._turn_mark = self._last_qid
            self.brain.provider.cancel_event.clear()  # unter der Sperre: ein Stopp gleich danach zaehlt
        threading.Thread(target=self._work, args=(text, None, model_text, shown), name="ki-antwort",
                         kwargs={"bilder": bilder, "images": images, "client_id": client_id},
                         daemon=True).start()
        return True, ""

    def submit(self, text: str, interrupt: bool = False, images: Any = None, client_id: Any = None) -> dict:
        """Getippte Nachricht aus dem Fenster. Arbeitet die KI noch, kommt sie in die Warteschlange
        (interrupt=True: die laufende Antwort anhalten und diese gleich beantworten). Laeuft der
        AFK-Modus, heisst jede Nachricht: Ich bin zurueck.

        images = [{"name", "data": "data:image/...;base64,..."}] (Text darf dann leer sein): jedes
        Bild wird hier EINMAL geprueft und verkleinert und fuer die Anzeige abgelegt."""
        from ..bilder import BildFehler

        text = (text or "").strip()
        cid = client_id if isinstance(client_id, str) and _CLIENT_ID.match(client_id) else None
        if images is not None and not isinstance(images, list):
            return {"ok": False, "error": "Die Bilder kamen nicht richtig an."}
        if not text and not images:
            return {"ok": False, "error": "Leere Nachricht"}
        from ..schluessel import CLOUDFLARE_HINWEIS, find_cloudflare_token

        if not text.startswith("/") and find_cloudflare_token(text):
            return {"ok": False, "error": CLOUDFLARE_HINWEIS}
        if images and _mask_key(text)[0].startswith("/"):
            return {"ok": False, "error": schoen("Befehle (mit / am Anfang) und Schluessel bitte ohne Bilder "
                                                 "schicken.")}
        try:
            bilder, anzeigen = self._bilder_annehmen(images)
        except BildFehler as exc:
            return {"ok": False, "error": str(exc)}
        self.sehen.nutzer_aktiv(text)  # du schreibst: Live-Sehen haelt sich kurz zurueck
        for _attempt in range(3):
            with self._lock:
                busy = self.busy
                if busy:
                    sent, shown = _mask_key(text)
                    self._last_qid = next(self._queue_ids)
                    item = {"id": self._last_qid, "text": sent, "model_text": None, "shown": shown,
                            "bilder": bilder, "images": anzeigen, "client_id": cid}
                    afk = self._afk
                    # Nur die ERSTE Nachricht beendet den AFK-Modus und kommt nach vorn; weitere,
                    # die kommen, waehrend er noch endet, reihen sich normal dahinter ein.
                    back = afk is not None and not afk.ended and not afk.stop_event.is_set()
                    self._sehen_pending = None  # du bist dran - eine wartende Wortmeldung ist ueberholt
                    if self._sehen_turn and not back:
                        # Nova meldet sich gerade von selbst: deine Nachricht geht vor, die Wortmeldung
                        # wird ganz zurueckgenommen (kein "abgebrochen" im Verlauf)
                        interrupt = True
                        self._drop_turn = True
                    if back or interrupt:
                        self._queue.insert(self._front, item)
                        self._front += 1
                    elif len(self._queue) >= 20:
                        return {"ok": False, "error": "Die Warteschlange ist voll - warte kurz oder halte mich an."}
                    else:
                        self._queue.append(item)
                    dropped = self._afk_pending is not None  # du schreibst noch -> du bist ja da
                    self._afk_pending = None
                    if back:
                        afk.stop_event.set()
                    if back or interrupt:
                        self.brain.provider.cancel()  # unter der Sperre: trifft sicher die laufende Antwort
            if busy:
                if back or interrupt:
                    self._cancel_rest()
                if dropped:
                    self._notice("AFK-Modus nicht gestartet \u2013 du bist ja noch da.", "afk")
                self._state_changed()
                return {"ok": True, "queued": True, "id": item["id"], "interrupt": bool(back or interrupt),
                        "afk_ended": back}
            ok, error = self.send(text, bilder=bilder, images=anzeigen, client_id=cid)
            if ok:
                return {"ok": True}
            if not self.busy:  # anderer Grund (z.B. leer) - nicht "gerade beschaeftigt"
                return {"ok": False, "error": error}
        return {"ok": False, "error": "Ich arbeite noch - gleich nochmal versuchen."}

    def _bilder_annehmen(self, images: list | None) -> tuple[list, list[dict]]:
        """Bilder aus /api/send -> (Bilder fuer die KI, Anzeige [{url, name}]). Wirft BildFehler.

        Jedes Bild wird genau hier einmal verkleinert (danach nie mehr veraendert - Claude-Verlauf
        ist nur anhaengend) und unter data/bilder/hochgeladen/<16 hex>.<endung> fuer die Anzeige
        abgelegt. Base64 steht danach nirgends mehr (Verlauf, Ereignisse) - nur die URL."""
        from ..bilder import BildFehler, aus_data_url

        if not images:
            return [], []
        grenze = max(1, int(self.config.bilder.max_bilder_pro_nachricht or 10))
        if len(images) > grenze:
            raise BildFehler(f"H\u00f6chstens {grenze} Bilder pro Nachricht \u2013 bitte entferne "
                             f"{len(images) - grenze}.")
        kante = upload_kante(self.config)
        fertig = []
        for nummer, eintrag in enumerate(images, start=1):
            if not isinstance(eintrag, dict):
                raise BildFehler("Ein Bild kam nicht richtig an.")
            name = str(eintrag.get("name") or f"bild{nummer}")[:200]
            daten = eintrag.get("data")
            fertig.append(aus_data_url(daten if isinstance(daten, str) else "", name, max_kante=kante))
        ordner = self.upload_dir()
        anzeigen = []
        for bild in fertig:
            try:
                pfad = bild.speichern(ordner, stamm=secrets.token_hex(8))
            except OSError as exc:
                logger.warning("Bild nicht gespeichert: %s", type(exc).__name__)
                raise BildFehler("Das Bild lie\u00df sich nicht speichern (ist die Festplatte voll?).") from exc
            anzeigen.append({"url": f"/api/bild/h/{pfad.name}", "name": bild.name})
        try:
            alte_uploads_loeschen(ordner)
            uploads_begrenzen(ordner)
        except OSError:
            pass
        return fertig, anzeigen

    def upload_dir(self) -> Path:
        """Hochgeladene Bilder (nur fuer die Anzeige im Fenster): data/bilder/hochgeladen."""
        return Path(self.config.project_root) / "data" / "bilder" / "hochgeladen"

    def bild_ordner(self, kind: str) -> Path | None:
        """Ordner fuer GET /api/bild/<kind>/<name>: h = hochgeladen, e = erstellt (Arbeitsordner)."""
        from ..bildgenerator import bilder_ordner

        if kind == "h":
            return self.upload_dir()
        if kind == "e":
            return bilder_ordner(self.permissions.workspace_root)
        return None

    def _remove_queued_locked(self, item: dict) -> None:
        index = self._queue.index(item)
        self._queue.pop(index)
        if index < self._front:
            self._front -= 1

    def queue_action(self, action: str, item_id: Any = None) -> dict:
        """Warteschlange: 'remove' (eine Nachricht raus), 'clear' (alle), 'now' (diese jetzt - unterbricht)."""
        with self._lock:
            if action == "clear":
                self._queue.clear()
                self._front = 0
            elif action in ("remove", "now"):
                item = next((q for q in self._queue if str(q["id"]) == str(item_id)), None)
                if item is None:
                    return {"ok": False, "error": "Diese Nachricht wartet nicht mehr."}
                self._remove_queued_locked(item)
                if action == "now":
                    self._queue.insert(0, item)
                    self._front += 1
                    if self.busy:
                        self.brain.provider.cancel()
                        if self._afk_pending is not None:  # du klickst gerade -> du bist da
                            self._afk_pending = None
                            self._afk_dropped = True
            else:
                return {"ok": False, "error": f"Unbekannte Aktion '{action}'."}
        if action == "now" and self.busy:
            self._cancel_rest()
        self._state_changed()
        return {"ok": True}

    def _cancel_current(self) -> None:
        """Nur die laufende Antwort anhalten (die Warteschlange bleibt)."""
        self.brain.provider.cancel()
        self._cancel_rest()

    def _cancel_rest(self) -> None:
        """Alles ausser dem Modell-Abbruch: Sprachmodus still, offene Rueckfragen, Vorlesen."""
        if self._live is not None:
            self._live.hush()
        for waiter in list(self._asks.values()):
            if "nein" in waiter.get("options", []):
                waiter["value"] = "nein"  # abgebrochen heisst nie "ja"
            waiter["event"].set()
        self.voice_out.stop()

    def _next_job_locked(self) -> dict | None:
        """Was als Naechstes drankommt (unter self._lock aufrufen). Setzt das Abbruch-Signal
        hier zurueck - ein Stopp/Unterbrechen danach trifft sicher die neue Aufgabe."""
        if self._closing:
            return None
        if self._queue:
            self.brain.provider.cancel_event.clear()
            self._drop_turn = False  # galt der vorigen Antwort (z.B. einer Wortmeldung von Live-Sehen)
            self._front = max(0, self._front - 1)
            self._turn_mark = self._last_qid
            return {"message": self._queue.pop(0)}
        if self._afk_pending is not None:
            request, self._afk_pending = self._afk_pending, None
            live = self._live
            if live is not None and not live.stop_event.is_set() and getattr(live, "pending", None):
                self._afk_dropped = True  # im Sprachmodus wartet schon dein naechster Satz -> du bist da
                return None
            try:
                session = self._new_afk_session_locked(request)
            except Exception:  # noqa: BLE001 - nie mit busy=True haengen bleiben
                logger.exception("AFK-Modus konnte nicht beginnen")
                self._afk_dropped = "fehler"
                return None
            self.brain.provider.cancel_event.clear()
            return {"afk": session}
        if self._sehen_pending is not None:
            from ..live import SEEN_HOLD

            paket, self._sehen_pending = self._sehen_pending, None
            if time.monotonic() - paket.zeit <= SEEN_HOLD and self.sehen.darf_melden() and self._afk is None:
                self.brain.provider.cancel_event.clear()
                self._drop_turn = False
                self._sehen_turn = True  # schon jetzt: eine Nachricht von dir unterbricht sie sicher
                return {"sehen": paket}
        return None

    def _afk_dropped_notice(self) -> None:
        reason, self._afk_dropped = self._afk_dropped, False
        if reason == "fehler":
            self._notice("Der AFK-Modus ging nicht (interner Fehler) - ich bin weiter normal fuer dich da.", "afk")
        elif reason:
            self._notice("AFK-Modus nicht gestartet \u2013 du bist ja noch da.", "afk")

    def _new_afk_session_locked(self, request: dict):
        """AFK-Sitzung sofort sichtbar machen (unter self._lock): eine Nachricht, die jetzt kommt,
        heisst schon 'zurueck'."""
        from ..abwesend import settings_session

        session = settings_session(self.config.afk, request.get("auftrag", ""), request.get("minutes"),
                                   request.get("budget"), start_eur=self.brain.cost_now_eur())
        self._afk = session
        self.tool_ctx.extra["afk_session"] = session
        return session

    def _release(self) -> None:
        """Arbeit fertig (ausser _work): naechste Aufgabe beginnen oder frei geben."""
        with self._lock:
            job = self._next_job_locked()
            if job is None:
                self.busy = False
        self._afk_dropped_notice()
        self._state_changed()
        if job is not None:
            self._start_job(job)

    def _start_job(self, job: dict) -> None:
        """Naechste Aufgabe beginnen - self.busy ist dabei schon True."""
        kwargs: dict = {}
        if "afk" in job:
            target, args = self._work, (None, lambda: self._run_afk(job["afk"]))
        elif "sehen" in job:
            target, args = self._work, (None, lambda: self._run_sehen(job["sehen"]))
        else:
            item = job["message"]
            target, args = self._work, (item["text"], None, item["model_text"], item["shown"])
            kwargs = {"bilder": item.get("bilder"), "images": item.get("images"),
                      "client_id": item.get("client_id")}
        threading.Thread(target=target, args=args, kwargs=kwargs, name="ki-warteschlange", daemon=True).start()

    def run_background(self, fn: Callable[[], Any]) -> None:
        """Etwas wie eine Nachricht ausfuehren (Ausgaben -> Systemkarten), z.B. Update-Pruefung."""
        with self._lock:
            if self.busy:
                return
            self.busy = True
            self.brain.provider.cancel_event.clear()
        threading.Thread(target=self._work, args=(None, fn), name="ki-hintergrund", daemon=True).start()

    def _work(self, text: str | None, fn: Callable[[], Any] | None = None, model_text: str | None = None,
              shown: str | None = None, bilder: list | None = None, images: list | None = None,
              client_id: str | None = None) -> None:
        self._state_changed()
        writer = _NoticeWriter(self._notice)
        self._writer = writer
        quit_code = None
        try:
            with redirect_stdout(writer):
                if fn is not None:
                    quit_code = fn()
                elif text.startswith("/"):
                    self._user_message(shown or text, None, client_id)
                    quit_code = self._command(text)
                elif not self.config.api_key:
                    self._user_message(text, images, client_id)
                    self._notice(KEY_HINT.replace("\n  ", "\n- "), "warn")
                else:
                    self._answer(text, model_text, bilder=bilder, images=images, client_id=client_id)
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
                job = self._next_job_locked() if quit_code is None else None
                if job is None:
                    self.busy = False
            self._afk_dropped_notice()
            self._state_changed()
            if live_turn is not None:
                live_turn.on_turn_end()
        if quit_code is not None:
            self.on_quit(quit_code)
        elif job is not None:
            self._start_job(job)

    def _user_message(self, text: str, images: list | None, client_id: str | None) -> dict:
        """Deine Nachricht in den Verlauf und ins Fenster (Bilder nur als URL, nie Base64)."""
        entry: dict = {"role": "user", "text": text}
        if images:
            entry["images"] = [dict(i) for i in images]
        if client_id:
            entry["client_id"] = client_id
        self.history.append(entry)
        self._event({"type": "user", "text": text, "images": [dict(i) for i in images or []],
                     "client_id": client_id})
        return entry

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

    def _answer(self, text: str, model_text: str | None = None, as_notice: bool = False,
                max_tool_rounds: int | None = None, bilder: list | None = None, images: list | None = None,
                client_id: str | None = None, notice_level: str = "afk", sehen: bool = False) -> None:
        """sehen=True: Wortmeldung von Live-Sehen - "[still]" (nichts zu sagen) wird ganz
        zurueckgenommen, angehalten heisst immer zuruecknehmen (kein "abgebrochen")."""
        from ..sehen.dienst import StillFilter

        entry: dict = {"role": "user", "text": text}
        if as_notice:  # AFK-Schritt / Live-Sehen: keine Sprechblase "von dir"
            self._notice(text, notice_level)
            if sehen and self.history:
                entry = self.history[-1]  # bei "[still]" verschwindet der Hinweis wieder
        else:
            entry = self._user_message(text, images, client_id)
            model_text = self._with_afk_hints(text, model_text)
        self._event({"type": "start"})
        self._answer_parts: list[str] = []
        snapshot = self.brain.provider.history_snapshot()
        filter_ = StillFilter(self._emit) if sehen else None
        mit_bildern = {"bilder": list(bilder)} if bilder else {}
        try:
            if sehen:  # Live-Sehen: eigene Runde - kein Weiterarbeiten, nie ins Gedaechtnis
                answer = self.brain.wortmeldung(model_text or text, on_text=filter_, bilder=bilder)
            elif as_notice:  # AFK-Schritt: begrenzt, kein automatisches Weiterarbeiten
                answer = self.brain.respond(model_text or text, on_text=self._emit,
                                            max_tool_rounds=max_tool_rounds, auto_continue=0, **mit_bildern)
            else:
                answer = self.brain.respond(model_text or text, on_text=self._emit, **mit_bildern)
        except KeyboardInterrupt:  # Stopp-Knopf (Abgebrochen) - oder Strg+C im Hintergrund
            # (Ein vorgemerkter AFK-Modus wird beim Anhalten dort verworfen, wo angehalten wird:
            # Stopp/Unterbrechen/Rueckkehr im Fenster, Stopp/Nachtrag/Chat-Modus im Sprachmodus.
            # Hier nicht - sonst traefe es auch einen AFK-Knopf, der NACH dem Stopp gedrueckt wurde.)
            drop, self._drop_turn = self._drop_turn, False
            if sehen:
                if not self.brain.provider.drop_turn(snapshot, model_text or text):
                    self.brain.provider.abort_turn(snapshot, text)
                    self.brain.provider.als_wortmeldung(snapshot)
                self._event({"type": "thinking", "on": False})
                self._event({"type": "sehen_still", "chip": False})
                return
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
            if sehen:
                self.brain.provider.als_wortmeldung(snapshot)
            raise
        if filter_ is not None and (filter_.ende() or ist_still(answer)):
            # Nichts zu sagen: Wortmeldung ganz zuruecknehmen (spart Verlauf) und nichts zeigen
            if not self.brain.provider.drop_turn(snapshot, model_text or text):
                self.brain.provider.als_wortmeldung(snapshot)  # mit Werkzeug: bleibt, aber gekennzeichnet
            if entry in self.history:
                self.history.remove(entry)
            self._event({"type": "thinking", "on": False})
            self._event({"type": "sehen_still", "chip": True})
            return
        if sehen:
            self.brain.provider.als_wortmeldung(snapshot)  # zaehlt nicht als deine Nachricht, nie ins Gedaechtnis
        self.history.append({"role": "assistant", "text": "".join(self._answer_parts) or answer})
        self._event({"type": "thinking", "on": False})
        self._event({"type": "done"})
        self._last_answer = "".join(self._answer_parts) or answer
        speak = not as_notice or (sehen and self.sehen.regeln.sprechen)
        if self.voice_out.enabled and not self._jarvis_active() and speak:
            threading.Thread(target=self._speak_aloud, args=(answer,), daemon=True).start()

    def _speak_aloud(self, answer: str) -> None:
        """Vorlesen am PC (Schalter 'Vorlesen') - die Sphaere spricht mit."""
        self._event({"type": "speaking", "on": True})
        try:
            self.voice_out.speak(vorlesetext(answer))  # ohne Bild-Adressen und Markdown
        finally:
            self._event({"type": "speaking", "on": False})

    def stop(self) -> None:
        """Stopp-Knopf: Antwort anhalten, AFK-Modus beenden. Wartende Nachrichten werden nicht
        einfach abgeschickt, sondern kommen zurueck ins Eingabefeld (nichts geht verloren)."""
        with self._lock:
            waiting, self._queue = self._queue, []
            self._front = 0
            self._afk_pending = None
            if self._afk is not None:
                self._afk.stop_event.set()
            self.brain.provider.cancel()
        self._cancel_rest()
        if waiting:
            # Schluessel nie zurueck; Bilder kommen als URL zurueck (das Fenster holt sie wieder)
            items = [{"text": item["text"], "images": [dict(i) for i in item.get("images") or []]}
                     for item in waiting if not item["shown"]]
            if items:
                self._event({"type": "queue_returned", "text": "\n".join(i["text"] for i in items if i["text"]),
                             "items": items})
            self._state_changed()

    # -- AFK-Modus: allein weiterarbeiten, waehrend du weg bist (abwesend.py) -------
    def _afk_request(self, auftrag: str = "", minutes: int | None = None, budget: float | None = None) -> bool:
        """Vormerken (Werkzeug abwesenheit, /afk) - beginnt, sobald die laufende Antwort fertig ist.
        Wurde waehrend dieser Antwort schon weitergeschrieben, bist du offensichtlich noch da.
        Hast du schon den AFK-Knopf gedrueckt, gelten dessen Grenzen (die KI fuellt hoechstens den
        Auftrag auf). True = vorgemerkt."""
        auftrag = str(auftrag or "")[:2000]
        with self._lock:
            if self._afk is not None:
                return False
            existing = self._afk_pending
            if existing is not None:  # Knopf schon gedrueckt: dessen Wahl bleibt
                if not existing.get("auftrag") and auftrag:
                    existing["auftrag"] = auftrag
                kept = True
            elif any(item["id"] > self._turn_mark for item in self._queue):
                self._afk_dropped = True  # waehrend dieser Antwort weitergeschrieben -> du bist da
                kept = False
            else:
                self._afk_pending = {"auftrag": auftrag, "minutes": _int_or_none(minutes),
                                     "budget": _float_or_none(budget)}
                kept = True
        self._state_changed()
        return kept

    def afk(self, data: dict) -> dict:
        """POST /api/afk: {"action": "start", "auftrag", "minuten", "budget"} | {"action": "stop"}."""
        action = str(data.get("action") or "")
        if action == "stop":
            with self._lock:
                running, self._afk_pending = self._afk, None
                if running is not None:
                    running.stop_event.set()
                    self.brain.provider.cancel()
            if running is not None:
                self._cancel_rest()
            self._state_changed()
            return {"ok": True}
        if action != "start":
            return {"ok": False, "error": schoen(f"Unbekannte Aktion '{action}'.")}
        if not self.config.api_key:
            return {"ok": False, "error": schoen("Dafuer brauche ich erst einen Schluessel (Gehirn & Schluessel).")}
        request = {"auftrag": str(data.get("auftrag") or "")[:2000],
                   "minutes": _int_or_none(data.get("minuten")),
                   "budget": _float_or_none(data.get("budget"))}
        with self._lock:
            if self._afk is not None:
                return {"ok": False, "error": schoen("Der AFK-Modus laeuft schon.")}
            if self.busy:
                self._afk_pending = request  # nach der laufenden Antwort
                job = None
            else:
                try:
                    session = self._new_afk_session_locked(request)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("AFK-Modus konnte nicht beginnen")
                    return {"ok": False, "error": schoen(f"Der AFK-Modus ging nicht: {exc}")}
                self.busy = True
                self.brain.provider.cancel_event.clear()
                job = {"afk": session}
        if job is not None:
            self._start_job(job)
        self._state_changed()
        return {"ok": True, "started": job is not None}

    def _run_afk(self, session) -> None:
        from ..abwesend import run_session

        try:
            live = self._live
            if live is not None and not live.stop_event.is_set():
                # Erst die Bestaetigung zu Ende sprechen lassen; sprichst du dabei wieder, bist du da.
                if not wait_until_quiet(live, session.stop_event):
                    session.ended = "nicht_gestartet"
                    return
                live.stop()  # allein arbeiten heisst: nicht mithoeren und nichts vorlesen
            if live is not None:
                with self._jarvis_lock:  # Jarvis-Denktiefe nicht in die AFK-Schritte mitnehmen
                    if self._live is live:
                        self._live = None
                        self.brain.provider.effort_override = None
            self.permissions.begin_away()
            self.sehen.setze_abwesend(True)
            task = (f"Auftrag: {session.auftrag}" if session.auftrag
                    else "Ich mache mit dem weiter, woran wir zuletzt gearbeitet haben.")
            cost = f"{session.max_eur:.2f}".replace(".", ",")
            self._notice(f"AFK-Modus an \u2013 ich arbeite allein weiter (hoechstens {session.max_minutes} Min., ca. "
                         f"{cost} EUR). {task} Ich loesche, ueberschreibe, verschicke und starte dabei nichts \u2013 "
                         "das schreibe ich dir als Vorschlag auf. Zurueck? Einfach eine Nachricht schreiben.", "afk")
            self._state_changed()

            def one_round(prompt: str) -> None:
                self.brain.provider.cancel_event.clear()  # erst zuruecksetzen, dann pruefen (kein Rennen)
                if session.stop_event.is_set():
                    return
                gesehen = self.sehen.afk_zeilen_nehmen()  # nur mit [sehen] bei_abwesenheit
                self._answer(f"AFK \u2013 Schritt {session.rounds}", model_text=gesehen + prompt, as_notice=True,
                             max_tool_rounds=session.max_tool_rounds)

            run_session(session, one_round, cost_eur=self.brain.cost_now_eur, on_update=self._state_changed,
                        cancel=self.brain.provider.cancel)
        finally:
            self.permissions.end_away()
            self.sehen.setze_abwesend(False)
            self.tool_ctx.extra.pop("afk_session", None)
            if session.ended == "nicht_gestartet":
                with self._lock:
                    self._afk = None
                self._notice("AFK-Modus nicht gestartet \u2013 du bist ja noch da.", "afk")
                self._state_changed()
                return
            if not session.ended:
                session.ended = "fehler"
            report = session.report()
            with self._lock:
                self._afk = None
                self._afk_return = (session.started, report)
            self._notice(report, "afk")
            self._event({"type": "afk_report", "text": schoen(report), "reason": session.ended})
            self._state_changed()

    def _with_afk_hints(self, text: str, model_text: str | None) -> str | None:
        """Rueckkehr nach dem AFK-Modus: Bericht vor die Nachricht; 'bin jetzt weg': Hinweis."""
        from ..abwesend import model_text_for

        with self._lock:
            back, self._afk_return = self._afk_return, None
        base = model_text or text
        result = model_text_for(base, back=back, active=self._afk is not None)
        return result if result != base else model_text

    def _afk_command(self, args: list[str]) -> None:
        """/afk [Auftrag] im Fenster: beginnt, sobald dieser Befehl durch ist."""
        if not self.config.api_key:
            print("Dafuer brauche ich erst einen Schluessel (Gehirn & Schluessel).")
            return
        from ..abwesend import budget_abtrennen

        budget, auftrag = budget_abtrennen(" ".join(args))  # /afk 0,30€ ...
        if self._afk_request(auftrag, budget=budget):
            print("AFK-Modus vorgemerkt - geht gleich los. Zurueck? Einfach eine Nachricht schreiben.")
        else:
            print("AFK-Modus nicht gestartet - du hast ja schon weitergeschrieben.")

    # -- Live-Sehen (assistant/sehen) -------------------------------------------------
    def _sehen_notiz(self, text: str) -> None:
        self._notice(text, "sehen")

    def _sehen_status(self) -> None:
        # klein (hoechstens einmal pro Sekunde): nur der Stand von Live-Sehen, nicht der ganze Zustand
        self._event({"type": "sehen", "sehen": self.sehen.status()})

    def _sehen_wecken(self, paket) -> None:
        """Live-Sehen hat etwas bemerkt: als niedrigste Aufgabe einreihen - nie mitten in eine
        laufende Antwort, nur die neueste wartet (hoechstens 20 s). Im Jarvis-Modus entscheidet
        der Sprachmodus, wann Nova ausgeredet hat und du nicht sprichst."""
        if paket.abwesend or not self.config.api_key or not self.sehen.darf_melden():
            return
        live = self._live
        if live is not None and not live.stop_event.is_set():
            live.seen_event(paket)
            return
        with self._lock:
            if self._closing or self._afk is not None or self._afk_pending is not None:
                return
            if self.busy:
                self._sehen_pending = paket
                return
            self.busy = True
            self._sehen_turn = True  # unter der Sperre: eine Nachricht ab jetzt unterbricht sie
            self._live_turn = None
            self._drop_turn = False
            self.brain.provider.cancel_event.clear()
        self._start_job({"sehen": paket})

    def _sehen_starten(self, paket, live) -> bool:
        """Jarvis-Modus: Wortmeldung als Runde dieses Sprachmodus (er spricht sie)."""
        if not self.config.api_key or not self.sehen.darf_melden():
            return False
        with self._lock:
            if self.busy or self._closing:
                return False
            self.busy = True
            self._sehen_turn = True
            self._live_turn = live
            self._drop_turn = False
            self.brain.provider.cancel_event.clear()
        threading.Thread(target=self._work, args=(None, lambda: self._run_sehen(paket, jarvis=True)),
                         name="ki-sehen", daemon=True).start()
        return True

    def _run_sehen(self, paket, jarvis: bool = False) -> None:
        """Eine Wortmeldung: nur lesende Werkzeuge (wie im AFK-Modus), hoechstens ein Werkzeug-Schritt,
        Euro-Grenze pro Stunde mit Waechter."""
        from ..sehen.dienst import WORTMELDUNG_WERKZEUGE, euro_waechter

        self._sehen_turn = True
        if not self.sehen.darf_melden():  # inzwischen Pause/aus/anderes Gehirn
            self._sehen_turn = False
            return
        away = self.permissions.away
        if not away:
            self.permissions.begin_away()
        self.tool_ctx.extra["nur_diese_werkzeuge"] = WORTMELDUNG_WERKZEUGE
        start = self.brain.cost_now_eur()
        fertig = euro_waechter(self.brain.cost_now_eur, self.brain.provider.cancel,
                               None if self.config.kostenlos else self.sehen.euro_rest())
        try:
            self._answer(paket.anzeige, model_text=paket.text + (JARVIS_HINT if jarvis else ""), as_notice=True,
                         notice_level="sehen", bilder=paket.bilder, sehen=True)
        finally:
            fertig.set()
            self.tool_ctx.extra.pop("nur_diese_werkzeuge", None)
            if not away:
                self.permissions.end_away()
            self._sehen_turn = False
            try:
                self.sehen.gebucht(max(0.0, self.brain.cost_now_eur() - start))
            except Exception:  # noqa: BLE001
                pass

    def _sehen_halt(self) -> None:
        """Pause/Aus/Pause-Taste/AFK: schon geplante Wortmeldungen verwerfen, eine laufende anhalten."""
        with self._lock:
            self._sehen_pending = None
            laufend = self._sehen_turn
            if laufend:
                self._drop_turn = True
                self.brain.provider.cancel()
        live = self._live
        if live is not None:
            live.seen = None
            if laufend:
                live.hush()
        if laufend:
            self.voice_out.stop()

    def sehen_fenster_schuetzen(self) -> None:
        """Programmfenster ist jetzt da (Live-Sehen lief evtl. schon vor dem Fenster an): eigenes Fenster
        aus der Aufnahme nehmen."""
        if self.sehen.aktiv and "bildschirm" in self.sehen.quellen:
            hinweis = self._fenster_schutz(True)
            self.sehen.eigenes_fenster_neu()
            if hinweis:
                self._notice(hinweis, "sehen")

    def sehen_api(self, data: dict) -> dict:
        """POST /api/sehen: {"aktion": "an"|"aus"|"pause"|"weiter"|"quelle"|"kamera"|"status", ...}."""
        from ..sehen.einstellungen import QUELLEN

        aktion = str(data.get("aktion") or "status")
        dienst = self.sehen
        ergebnis: dict = {"ok": True}
        if aktion == "an":
            if data.get("einverstanden") is True and dienst.braucht_zustimmung():
                dienst.zustimmen()
            if dienst.braucht_zustimmung():
                return {"ok": False, "zustimmung": True, "warnung": schoen(dienst.warnung()),
                        "error": schoen("Bitte erst zustimmen."), "sehen": dienst.status()}
            quelle = str(data.get("quelle") or "").lower() or None
            if quelle is not None and quelle not in QUELLEN:
                return {"ok": False, "error": schoen(f"Unbekannte Quelle '{quelle}'.")}
            if quelle:
                self._sehen_quelle_speichern(quelle)
            ok, text = dienst.an(quelle)
            ergebnis = {"ok": ok, "message": schoen(text), "error": "" if ok else schoen(text)}
            if ok:
                self._notice(text, "sehen")
        elif aktion == "aus":
            self._notice(dienst.aus(), "sehen")
        elif aktion == "pause":
            ergebnis["message"] = schoen(dienst.pause())
        elif aktion == "weiter":
            ergebnis["message"] = schoen(dienst.weiter())
        elif aktion == "quelle":
            quelle = str(data.get("quelle") or "").lower()
            if quelle not in QUELLEN:
                return {"ok": False, "error": schoen(f"Unbekannte Quelle '{quelle}'.")}
            self._sehen_quelle_speichern(quelle)
            if dienst.aktiv:
                ok, text = dienst.an(quelle)
                ergebnis = {"ok": ok, "message": schoen(text), "error": "" if ok else schoen(text)}
                self._notice(text, "sehen")
        elif aktion == "kamera":
            vorhanden = data.get("vorhanden")
            dienst.kamera_meldung(vorhanden=None if vorhanden is None else bool(vorhanden),
                                  fehler=" ".join(str(data.get("fehler") or "").split())[:300])
        elif aktion != "status":
            return {"ok": False, "error": schoen(f"Unbekannte Aktion '{aktion}'.")}
        self._state_changed()
        ergebnis["sehen"] = dienst.status()
        return ergebnis

    def _sehen_quelle_speichern(self, quelle: str) -> None:
        try:
            save_setting(self.config.project_root, "sehen", "quelle", toml_string(quelle))
        except Exception as exc:  # noqa: BLE001
            logger.info("Quelle nicht gespeichert: %s", type(exc).__name__)
        self.config.sehen.quelle = quelle

    def kamera_bild(self, data: bytes) -> dict:
        """POST /api/kamera/bild (JPEG/PNG/WebP, schon am Server geprueft) - nur im Speicher."""
        ok, fehler = self.sehen.kamera_bild(data)
        return {"ok": ok, "error": schoen(fehler) if fehler else "", "weiter": ok}

    def kamera_erlaubt(self) -> bool:
        """Fuer das Programmfenster (WebView2): darf die Seite gerade die Kamera nutzen?"""
        return self.sehen.kamera_erlaubt()

    def _sehen_beim_start(self) -> None:
        if not self.config.sehen.aktiv:
            return
        if self.sehen.braucht_zustimmung():
            self._notice("Live-Sehen ist in den Einstellungen an, aber du hast noch nicht zugestimmt \u2013 "
                         "schalte es im Reiter \u201eSicherheit\u201c ein.", "sehen")
            return
        ok, text = self.sehen.an()
        self._notice(text, "sehen" if ok else "warn")

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
        super()._after_provider_change()  # Live-Sehen: Zustimmung galt dem alten Gehirn
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
            item["model_name"] = schoen(item["model_name"])
        info["aktuell"] = schoen(info["aktuell"])
        for group in info["modelle"].values():
            for entry in group["modelle"] + group["denktiefen"]:
                for k in ("name", "info", "tempo", "preis"):
                    if entry.get(k):
                        entry[k] = schoen(entry[k])
        info["bilder"] = self._bilder_info()
        return info

    # -- Bildgenerator: Einstellungen (Abschnitt "Bilder" in Gehirn & Schluessel) ---------
    def _bilder_info(self) -> dict:
        """Fuer /api/setup - nie der Schluessel, nur ob einer da ist."""
        from ..bildgenerator import aktiver_anbieter, cloudflare_eingerichtet

        wahl = str(self.config.bilder.anbieter or "auto").strip().lower()
        return {"anbieter": wahl if wahl in ("auto", "horde", "cloudflare") else "auto",
                "cloudflare": cloudflare_eingerichtet(self.config),
                "aktiv": aktiver_anbieter(self.config)}

    def bilder_einstellen(self, data: dict) -> dict:
        """POST /api/bilder/einstellen: {"anbieter"?, "cloudflare_account_id"?, "cloudflare_token"?,
        "entfernen"?}. Schluessel in die .env (erst kurz pruefen), Anbieter in die Einstellungen.
        Der Schluessel kommt nie zurueck - auch nicht in Fehlermeldungen."""
        from ..bildgenerator import aktiver_anbieter, cloudflare_eingerichtet, pruefe_cloudflare
        from ..config import save_env_value

        def nein(text: str) -> dict:
            return {"ok": False, "message": text, "error": text}

        cfg, root = self.config, self.config.project_root
        anbieter = data.get("anbieter")
        if anbieter is not None and anbieter != "":
            anbieter = str(anbieter).strip().lower()
            if anbieter not in ("auto", "horde", "cloudflare"):
                return nein("Unbekannter Bildgenerator \u2013 m\u00f6glich sind auto, horde und cloudflare.")
        else:
            anbieter = None
        konto = str(data.get("cloudflare_account_id") or "").strip()
        token = str(data.get("cloudflare_token") or "").strip()
        entfernen = bool(data.get("entfernen"))
        if not (anbieter or konto or token or entfernen):
            return nein("Es gibt nichts zu speichern.")
        teile: list[str] = []
        try:
            if entfernen:
                for name in ("CLOUDFLARE_AI_API_KEY", "CLOUDFLARE_ACCOUNT_ID"):
                    save_env_value(root, name, "")
                    os.environ.pop(name, None)
                cfg.cloudflare_api_key = cfg.cloudflare_account_id = None
                teile.append("Der Cloudflare-Zugang ist entfernt.")
            elif konto or token:
                token = token or str(cfg.cloudflare_api_key or "").strip()
                konto = konto or str(cfg.cloudflare_account_id or "").strip()
                if not token:
                    return nein("Bitte auch den Cloudflare-API-Token eintragen.")
                if not konto:
                    return nein("Bitte auch die Cloudflare-Konto-ID eintragen (steht auf derselben Seite "
                                "wie der Token).")
                if not _CF_TOKEN.match(token):
                    return nein("Der API-Token sieht nicht richtig aus \u2013 bitte komplett kopieren "
                                "(ohne Leerzeichen).")
                if not _CF_KONTO.match(konto):
                    return nein("Die Cloudflare-Konto-ID sieht nicht richtig aus (32 Zeichen aus 0-9 und a-f).")
                ok, meldung = pruefe_cloudflare(token, konto, http=self._cloudflare_http)
                if not ok:
                    return nein(meldung)
                save_env_value(root, "CLOUDFLARE_AI_API_KEY", token)
                save_env_value(root, "CLOUDFLARE_ACCOUNT_ID", konto)
                os.environ["CLOUDFLARE_AI_API_KEY"], os.environ["CLOUDFLARE_ACCOUNT_ID"] = token, konto
                cfg.cloudflare_api_key, cfg.cloudflare_account_id = token, konto
                teile.append(meldung)
            if anbieter:
                save_setting(root, "bilder", "anbieter", toml_string(anbieter))
                cfg.bilder.anbieter = anbieter
        except OSError as exc:
            logger.warning("Bild-Einstellung nicht gespeichert: %s", type(exc).__name__)
            return nein(schoen("Konnte die Einstellung nicht speichern (ist die Datei schreibgeschuetzt?)."))
        teile.append(f"Neue Bilder kommen jetzt von {aktiver_anbieter(cfg)}.")
        if cfg.bilder.anbieter == "cloudflare" and not cloudflare_eingerichtet(cfg):
            teile.append("Cloudflare ist noch nicht eingerichtet \u2013 bis dahin nutze ich AI Horde.")
        return {"ok": True, "message": " ".join(teile), "bilder": self._bilder_info()}

    def _model_changed(self) -> None:
        self.brain.model_changed()
        self.sehen.gehirn_gewechselt()
        self._state_changed()

    def choose_model(self, data: dict) -> dict:
        """Modell und/oder Denk-Tiefe waehlen (gilt ab der naechsten Anfrage, Gespraech bleibt)."""
        from ..modelle import waehle

        provider = str(data.get("provider") or "").lower() or None
        model = str(data.get("model") or "").strip() or None
        denken = str(data.get("denken") or "").strip() or None
        if not model and not denken:
            return {"ok": False, "error": "Bitte ein Modell oder eine Denk-Tiefe angeben."}
        try:
            result = waehle(self.config, provider, model=model, denken=denken, http=self._ollama_http)
        except Exception as exc:  # noqa: BLE001 - z.B. settings.toml nicht beschreibbar
            logger.warning("Modell-Wahl: %s", exc)
            return {"ok": False, "error": schoen(f"Konnte die Einstellung nicht speichern: {exc}")}
        if not result["ok"]:
            return {"ok": False, "error": schoen(result["message"])}
        self._model_changed()
        return {"ok": True, "message": schoen(result["message"]), "setup": self.setup_info()}

    def setup_save(self, data: dict) -> dict:
        """Schluessel pruefen und speichern, Gehirn waehlen."""
        from ..schluessel import PROVIDERS, find_key, setup

        provider = str(data.get("provider") or "").lower() or None
        if provider and provider not in PROVIDERS:
            return {"ok": False, "kind": "other", "error": f"Unbekanntes Gehirn '{provider}'."}
        raw = str(data.get("api_key") or "").strip()
        key = find_key(raw) or (raw or None)
        if provider == "ollama":
            key = None  # Ollama braucht keinen Schluessel (ein Schluessel im Feld geht nirgendwohin)
        with self._lock:
            if self.busy:
                return {"ok": False, "kind": "busy", "error": "Ich arbeite gerade - gleich nochmal versuchen."}
            self.busy = True
        self._state_changed()  # andere Fenster sehen: die KI prueft gerade
        try:
            extra = {"http": self._ollama_http} if provider == "ollama" else {}
            result = setup(self.config, key=key, provider=provider, test=not data.get("force"), **extra)
            if not result["ok"]:
                return {"ok": False, "kind": result["kind"], "error": schoen(result["message"])}
            fresh = self.brain.switch_provider()
            message = result["message"] + (" Wir beginnen ein neues Gespraech." if fresh else "")
            self._notice(message)
            self.sehen.gehirn_gewechselt()
            return {"ok": True, "message": schoen(message), "setup": self.setup_info()}
        finally:
            self._release()

    # -- Ollama (kostenlos, auf dem PC): Stand, Modelle laden, Adresse -------------------
    def ollama_info(self) -> dict:
        """GET /api/ollama: laeuft Ollama? welche Modelle (mit Faehigkeiten)? was wird geladen?"""
        from .. import ollama
        from ..modelle import kurzbeschreibung

        info = ollama.status(self.config, http=self._ollama_http)
        dienst = ollama.Dienst(info["adresse"], self._ollama_http)
        for m in info["modelle"]:
            caps = self._ollama_caps.get((info["adresse"], m["name"]))
            if caps is None and info["laeuft"] and not info["openai"]:
                try:
                    caps = sorted(dienst.faehigkeiten(m["name"]))
                except ollama.OllamaFehler:
                    caps = None
                if caps is not None:
                    self._ollama_caps[(info["adresse"], m["name"])] = caps
            m["werkzeuge"] = None if caps is None else "tools" in caps
            m["sieht_bilder"] = None if caps is None else "vision" in caps
            m["denkt"] = None if caps is None else "thinking" in caps
            m["groesse_text"] = ollama.groesse_text(m["groesse"])
            m["aktiv"] = ollama.ist_installiert(self.config.ollama.model, [m["name"]])
            emp = ollama.empfohlen_info(m["name"])
            m["anzeige"] = emp["name"] if emp else m["name"]
        info["fehler"] = schoen(info["fehler"])
        info["empfohlen"] = [{**m, "info": schoen(m["info"])} for m in info["empfohlen"]]
        info["laden"] = self.ollama_lader.zustand()
        info["aktiv"] = self.config.active_provider == "ollama"
        info["model_name"] = schoen(kurzbeschreibung(self.config, "ollama"))
        info["kontext"] = int(self.config.ollama.kontext)
        return info

    def ollama_laden(self, data: dict) -> dict:
        """POST /api/ollama/laden {"model"}: im Hintergrund herunterladen; Fortschritt als Ereignis
        {"type": "ollama_pull", "model", "text", "prozent", "erledigt", "gesamt", "fertig", "ok", ...}."""
        from .. import ollama

        modell = str(data.get("model") or "").strip()
        if not ollama.gueltiger_name(modell):
            return {"ok": False, "error": "Bitte einen g\u00fcltigen Modellnamen angeben (z.B. qwen3.5:4b)."}
        dienst = ollama.Dienst(ollama.adresse_aus(self.config), self._ollama_http)
        ok, message = self.ollama_lader.starten(dienst, modell, self._ollama_melde)
        if not ok:
            return {"ok": False, "error": schoen(message)}
        self._state_changed()
        return {"ok": True, "message": schoen(message)}

    def _ollama_melde(self, ev: dict) -> None:
        ev = dict(ev)
        if ev.get("fertig"):
            if ev.get("ok"):
                try:
                    extra = self._ollama_nach_laden(ev["model"])
                except Exception as exc:  # noqa: BLE001
                    logger.info("Nach dem Herunterladen: %s", exc)
                    extra = ""
                if extra:
                    ev["text"] = f"{ev.get('text', '')} {extra}".strip()
            for k in ("text", "fehler"):
                if ev.get(k):
                    ev[k] = schoen(ev[k])
        self._event({"type": "ollama_pull", **ev})
        if ev.get("fertig"):
            self._state_changed()

    def ollama_abbrechen(self) -> dict:
        return {"ok": self.ollama_lader.abbrechen()}

    def ollama_adresse(self, data: dict) -> dict:
        """POST /api/ollama/adresse {"adresse"}: nur http(s); leer = Standard."""
        from .. import ollama

        try:
            adresse = ollama.pruefe_adresse(data.get("adresse"))
        except ValueError as exc:
            return {"ok": False, "error": schoen(str(exc))}
        try:
            save_setting(self.config.project_root, "ollama", "adresse", toml_string(adresse))
        except OSError:
            return {"ok": False, "error": schoen("Konnte die Einstellung nicht speichern.")}
        self.config.ollama.adresse = adresse
        self._ollama_caps.clear()
        self._model_changed()
        return {"ok": True, "message": f"Ollama-Adresse: {adresse}", "ollama": self.ollama_info()}

    def ollama_starten(self) -> dict:
        from .. import ollama

        ok, message = ollama.starten()
        return {"ok": ok, "message": schoen(message), "error": "" if ok else schoen(message)}

    def _ollama_laden(self, modell: str) -> None:
        """'/ollama laden <modell>' im Chat der App: im Hintergrund, Fortschritt im Fenster."""
        result = self.ollama_laden({"model": modell})
        print(result.get("message") or result.get("error") or "")

    # In der App oeffnen /jarvis und /tutorial die Ansichten im Fenster (statt der Terminal-Versionen).
    def _jarvis_terminal(self) -> None:
        result = self.jarvis("start", "client")
        if result.get("ok"):
            self._event({"type": "open", "what": "jarvis"})
        else:
            print(result.get("error") or "Der Jarvis-Modus ging nicht.")

    def _bildpfad_hinweis(self, pfad: str) -> None:
        print("Bilder bitte \u00fcber die B\u00fcroklammer, mit Strg+V oder durch Hineinziehen anh\u00e4ngen.")

    def _tutorial_terminal(self) -> None:
        self._event({"type": "open", "what": "tutorial"})

    def _feedback_terminal(self) -> None:
        self._event({"type": "open", "what": "feedback"})

    def _bild_hilfe(self) -> None:
        print("Bilder schickst du in der App \u00fcber die B\u00fcroklammer neben dem Eingabefeld, mit Strg+V "
              "oder indem du sie ins Fenster ziehst.")

    # -- Bildgenerator: fertige Bilder und Fortschritt ins Fenster -----------------------
    def _on_image(self, info: dict) -> None:
        """Werkzeug bild_erstellen: {"pfad", "name", "prompt", "anbieter"} -> Ereignis "image"
        (und Verlauf, damit das Bild nach dem Neuladen wieder erscheint)."""
        from ..bildgenerator import DATEINAME_MUSTER, bilder_ordner

        self._bild_fortschritt = ""
        pfad = Path(str(info.get("pfad") or ""))
        name = str(info.get("name") or pfad.name)
        root = Path(self.permissions.workspace_root)
        try:
            rel = pfad.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            rel = name
        try:
            im_ordner = pfad.resolve().parent == bilder_ordner(root).resolve()
        except OSError:
            im_ordner = False
        entry = {"name": name, "prompt": str(info.get("prompt") or "")[:2000], "pfad": rel,
                 "anbieter": str(info.get("anbieter") or "")}
        if im_ordner and DATEINAME_MUSTER.match(name):
            entry = {"url": f"/api/bild/e/{name}", **entry}
            self.history.append({"role": "image", **entry})
            self._event({"type": "image", **entry})
        else:  # kann die App nicht anzeigen - wenigstens sagen, wo es liegt
            self._notice(f"Bild gespeichert: {rel}")
        if self._bild_hinweis_faellig():
            self._notice(BILD_HINWEIS)

    def _on_image_progress(self, text: str) -> None:
        text = " ".join(str(text or "").split())[:300]
        if text:
            self._event({"type": "image_progress", "text": schoen(text)})

    # -- Feedback & Bewertung -------------------------------------------------------------
    def feedback_status(self) -> dict:
        """GET /api/feedback (kann einmal am Tag kurz im Netz nachsehen, ob ein Postfach da ist)."""
        from .. import feedback

        try:
            return feedback.status(self.config, fetch=self._feedback_fetch)
        except Exception as exc:  # noqa: BLE001
            logger.info("Feedback-Status: %s", type(exc).__name__)
            return {"ok": True, "configured": False, "due": self._feedback_due(), "pending": 0,
                    "max_images": feedback.MAX_BILDER}

    def feedback_send(self, data: dict) -> dict:
        """POST /api/feedback - laeuft im Anfrage-Thread des Servers (der Chat bleibt frei)."""
        from .. import feedback

        images = data.get("images")
        if images is not None and not isinstance(images, list):
            return {"ok": False, "status": "abgelehnt", "error": "Die Bilder kamen nicht richtig an."}
        # Aus dem Fenster nur eingebettete Bilder - nie Dateipfade (sonst liest die Anfrage beliebige
        # Dateien, unter Windows auch \\server\freigabe).
        if images and not all(isinstance(e, dict) and isinstance(e.get("data"), str)
                              and e["data"].strip().lower().startswith("data:image/") for e in images):
            return {"ok": False, "status": "abgelehnt", "error": "Die Bilder kamen nicht richtig an."}
        contact = data.get("contact")
        if not self._feedback_lock.acquire(blocking=False):  # Doppelklick: nur EINE Sendung
            return {"ok": False, "status": "abgelehnt", "error": "Dein Feedback wird gerade schon gesendet."}
        try:
            ergebnis = feedback.abschicken(
                self.config, kind=str(data.get("kind") or "feedback"), stars=data.get("stars"),
                text=str(data.get("text") or ""), contact=str(contact) if contact else None,
                bilder=images or None, trigger=str(data.get("trigger") or "menue"),
                post=self._feedback_post, fetch=self._feedback_fetch)
        finally:
            self._feedback_lock.release()
        if ergebnis.ok:
            self._state_changed()  # Nachfrage erledigt
        if ergebnis.status == "gesendet":
            self._feedback_ausgang_bald()
        return ergebnis.als_antwort()

    def feedback_seen(self, which: str = "gezeigt") -> dict:
        """POST /api/feedback/gezeigt (Pop-up erscheint) und /api/feedback/spaeter (weggeklickt):
        beides heisst "jetzt gezeigt" - die naechste Nachfrage kommt erst in ein paar Tagen."""
        from .. import feedback

        feedback.gezeigt(root=self.config)
        self._state_changed()
        return {"ok": True, "due": self._feedback_due()}

    def _feedback_changed(self) -> None:
        self._state_changed()

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
            with self._lock:  # Jarvis oeffnen heisst: du bist zurueck
                if self._afk_pending is not None:
                    self._afk_dropped = True
                afk, self._afk_pending = self._afk, None
                back = afk is not None and not afk.ended
                if back:
                    afk.stop_event.set()
                    self.brain.provider.cancel()
            if back:
                self._cancel_rest()
            self._afk_dropped_notice()
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
            # Knopf "Chat-Modus"/Fenster schliessen: du bleibst am PC (wie gesagtes "Chat-Modus")
            self._live.exit_reason = self._live.exit_reason or "chat"
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
        elif name == "sofort_senden":
            self.config.voice.sofort_senden = bool(value)
            try:
                save_setting(self.config.project_root, "voice", "sofort_senden", "true" if value else "false")
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

    # -- Updates: Anzeige "auf dem neuesten Stand" -------------------------------------
    def _update_status(self) -> dict:
        try:
            status = self.updater.status()
        except Exception:  # noqa: BLE001
            status = {"state": "unbekannt", "current": __version__}
        if self._pending_update:
            status.update(state="neu", latest=self._pending_update.new)
        if getattr(self, "_checking_update", False):
            status["state"] = "pruefe"
        return status

    def check_update_now(self) -> dict:
        """Knopf 'Jetzt pruefen': nur nachschauen (installiert nichts - dafuer /update)."""
        if getattr(self, "_checking_update", False):
            return {"ok": True}
        self._checking_update = True
        self._state_changed()

        def work() -> None:
            try:
                info = self.updater.check()
                if info or self.updater.last_error is None:
                    self._pending_update = info  # nichts Neueres mehr -> Hinweis weg
            except Exception as exc:  # noqa: BLE001
                logger.info("Update-Pruefung: %s", exc)
            finally:
                self._checking_update = False
                self._state_changed()

        threading.Thread(target=work, name="update-pruefen", daemon=True).start()
        return {"ok": True}

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
        try:
            failed = self.updater.take_install_failure()
        except OSError:
            failed = None
        if failed:
            self._notice(failed, "warn")
        if not self.config.api_key:
            self._notice(KEY_HINT.replace("\n  ", "\n- "), "warn")
        elif self.config.provider_auto_switched:
            self._notice(f"Fuer {self.config.provider_auto_switched} ist kein Schluessel da - ich nutze deshalb "
                         f"{self.config.active_provider}. Wechseln: /gehirn")
        if self.config.active_provider == "ollama":
            def ollama_check() -> None:
                hinweis = self._ollama_starthinweis()
                if hinweis:
                    self._notice(hinweis, "warn")

            threading.Thread(target=ollama_check, name="ollama-pruefen", daemon=True).start()
        self._start_update_watch()
        self._start_feedback_watch()  # Nutzungszeit zaehlen, Feedback-Ausgang nachsenden
        try:
            self._sehen_beim_start()
        except Exception as exc:  # noqa: BLE001
            logger.info("Live-Sehen beim Start: %s", type(exc).__name__)
        try:
            alte_uploads_loeschen(self.upload_dir())
        except Exception as exc:  # noqa: BLE001
            logger.info("Alte Bilder nicht aufgeraeumt: %s", type(exc).__name__)

        def check() -> int | None:
            return self.exit_code if self._startup_update() else None

        self.run_background(check)

    def _restart(self, kind: str) -> bool:
        """Nach Update/Zurueck: die App mit der neuen Version neu oeffnen."""
        if kind == "exe":
            from ..updater import UpdateError

            try:
                self.updater.restart_exe(["--app"])
                print("Starte die neue Version …")
            except UpdateError as exc:  # z.B. neue Version vom Virenscanner entfernt: weiterlaufen
                print(str(exc))
                return False
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
        self._closing = True
        try:
            self.sehen.aus()  # Fenster zu: sofort wegschauen
        except Exception:  # noqa: BLE001
            pass
        if self._live is not None:
            self._live.stop()
        self._stop_watch.set()
        self.stop()
        try:
            with redirect_stdout(io.StringIO()):
                self._shutdown()  # Zusammenfassung ins Gedaechtnis, Datenbank schliessen
        except Exception as exc:  # noqa: BLE001
            logger.warning("Beim Beenden: %s", exc)


def _mask_key(text: str) -> tuple[str, str | None]:
    """Eingefuegter API-Schluessel: einrichten statt an die KI schicken; angezeigt nur gekuerzt.
    -> (Text fuer die Verarbeitung, Anzeige-Text oder None)."""
    from ..schluessel import find_key, mask

    key = find_key(text)
    if key and not text.startswith("/"):
        return f"/schluessel {key}", f"\U0001F511 Schl\u00fcssel {mask(key)}"
    if key:
        return text, text.replace(key, mask(key))
    return text, None


def uploads_begrenzen(ordner: Path, max_dateien: int = 1000, max_bytes: int = 500 * 1024 * 1024) -> int:
    """Hochgeladene Bilder: hoechstens so viele/so gross - die aeltesten zuerst weg -> Anzahl."""
    from ..bildgenerator import DATEINAME_MUSTER

    if not Path(ordner).is_dir():
        return 0
    dateien = []
    for pfad in Path(ordner).iterdir():
        try:
            if pfad.is_file() and DATEINAME_MUSTER.match(pfad.name):
                st = pfad.stat()
                dateien.append((st.st_mtime, st.st_size, pfad))
        except OSError:
            continue
    dateien.sort()
    gesamt = sum(groesse for _t, groesse, _p in dateien)
    weg = 0
    while dateien and (len(dateien) > max_dateien or gesamt > max_bytes):
        _t, groesse, pfad = dateien.pop(0)
        try:
            pfad.unlink()
            weg += 1
        except OSError:
            pass
        gesamt -= groesse
    return weg


def alte_uploads_loeschen(ordner: Path, tage: int = _UPLOAD_TAGE, jetzt: float | None = None) -> int:
    """Hochgeladene Bilder (data/bilder/hochgeladen) aelter als `tage` loeschen -> Anzahl."""
    from ..bildgenerator import DATEINAME_MUSTER

    grenze = (time.time() if jetzt is None else jetzt) - tage * 86400
    weg = 0
    if not Path(ordner).is_dir():
        return 0
    for pfad in Path(ordner).iterdir():
        try:
            if pfad.is_file() and DATEINAME_MUSTER.match(pfad.name) and pfad.stat().st_mtime < grenze:
                pfad.unlink()
                weg += 1
        except OSError:
            continue
    return weg


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value) if value not in (None, "") else None
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number is None or math.isfinite(number) else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
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
        self.ctl.sehen.nutzer_aktiv(text)  # du sprichst: Live-Sehen haelt sich kurz zurueck
        ok, _err = self.ctl.send(text, model_text=text + JARVIS_HINT, live=self.loop)
        return ok

    def start_seen_turn(self, paket) -> bool:
        return self.ctl._sehen_starten(paket, self.loop)

    def seen_pause(self) -> None:
        self.ctl.sehen.pause()

    def seen_ok(self) -> bool:
        return self.ctl.sehen.darf_melden()

    def cancel_turn(self, drop: bool) -> None:
        if self.ctl._live_turn is not self.loop:
            return  # nur eigene Antworten anhalten (nicht z.B. eine getippte Nachricht)
        leaving = self.loop.stop_event.is_set() and not staying(self.loop)  # "Tschuess" = du gehst
        with self.ctl._lock:
            if self.ctl._afk_pending is not None and not leaving:
                self.ctl._afk_pending = None  # "Stopp"/Nachtrag/"Chat-Modus": du bist noch da
                self.ctl._afk_dropped = True
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
