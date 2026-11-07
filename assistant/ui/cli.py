"""Die Chat-Oberflaeche: so redest du mit deiner KI (per Tastatur, optional Sprache).

Sprechen (bei leerer Eingabezeile): F2 gedrueckt HALTEN und sprechen, loslassen = fertig.
          Oder F2 kurz druecken = Mikrofon an, nochmal F2 = fertig (Esc = abbrechen).
          Der Text landet in der Eingabezeile - pruefen und mit Enter abschicken.

Sonderbefehle (mit '/' beginnen):
  /hilfe              - Hilfe anzeigen
  /sprache            - Stand der Spracheingabe (F2) anzeigen
  /sprache einrichten - Spracheingabe installieren
  /sprache vorlesen   - Antworten vorlesen an/aus
  /status             - aktuelle Einstellungen & Sicherheitslage zeigen
  /gedaechtnis        - zeigen, was die KI gelernt hat
  /kosten             - Token-Verbrauch & geschaetzte Kosten dieser Sitzung
  /update             - jetzt nach einer neuen Version schauen
  /versionen          - gesicherte alte Versionen anzeigen
  /zurueck <Nr>       - zu einer gesicherten alten Version zurueckkehren
  /autostart          - zeigen, was die KI automatisch startet (und es abstellen)
  /charakter [Name]   - Charakter anzeigen bzw. waehlen (freundlich, butler, kumpel ...)
  /stil [was wert]    - z.B. /stil anrede Sie, /stil laenge kurz, /stil humor viel
  /ueber-mich [feld = wert] - was die KI ueber dich wissen soll
  /werte bearbeiten   - deine Regeln fuer die KI im Editor oeffnen
  /neu                - neues Gespraech (Charakter & Profil frisch geladen)
  /jarvis             - reiner Sprachmodus: einfach reden (Strg+C = zurueck)
  /tutorial           - Nova stellt sich vor und zeigt, was sie kann
  /stuetzraeder an|aus - an: fragt vor allem, nur Arbeitsordner; aus: darf alles
  /aussehen [zuruecksetzen] - Aussehen der App anzeigen bzw. zuruecksetzen
  /name <Name> [= Bedeutung] - der KI einen anderen Namen geben
  /app                - zur App wechseln (eigenes Fenster statt Terminal)
  /verknuepfung       - Symbol fuer die App auf den Desktop legen
  /erlauben alles     - nie mehr nachfragen, alles erlauben (dauerhaft)
  /erlauben fragen    - wieder vor jeder Aktion nachfragen
  /beenden            - Sitzung beenden (speichert eine Zusammenfassung)

Strg+C waehrend einer Antwort haelt die KI an - du kannst gleich weiterschreiben.
"""
from __future__ import annotations

import os
import sys
import threading
import time

from .. import __version__
from ..brain import Brain
from ..config import Config, save_setting
from ..logging_setup import get_logger
from ..memory import Memory
from ..permissions import PermissionManager, Risk
from ..selbststart import StartGuard, entferne, finde_autostarts
from ..tools import ToolContext, build_registry
from ..updater import RESTART_EXIT_CODE, UpdateError, UpdateInfo, Updater
from ..voice import VoiceCapture, VoiceInput, VoiceOutput, install_voice_packages
from .lineinput import VoiceLineReader

logger = get_logger()

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
GREY = "\033[90m"


def _c(text: str, color: str) -> str:
    if not (sys.stdout and sys.stdout.isatty()):  # App (pythonw): kein Terminal
        return text
    return f"{color}{text}{RESET}"


def _confirm(message: str, risk: Risk) -> bool:
    """Fragt den Nutzer interaktiv um Bestaetigung fuer eine Aktion."""
    return _ask_permission(message, risk) in ("einmal", "immer")


def _ask_permission(message: str, risk: Risk) -> str:
    """'einmal', 'immer' oder 'nein'. 'immer' gibt es nicht fuer Autostart-Fragen."""
    label = {Risk.MODERATE: "Aktion", Risk.DANGEROUS: "GEFAEHRLICHE Aktion",
             Risk.AUTOSTART: "AUTOSTART"}.get(risk, "Aktion")
    print(_c(f"\n[{label}] {message}", YELLOW))
    if risk == Risk.AUTOSTART:
        question = "   Erlauben? [j = ja / N = nein] "
    else:
        question = "   Erlauben? [j = ja, einmal / a = ab jetzt IMMER alles erlauben / N = nein] "
    try:
        answer = input(_c(question, YELLOW)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "nein"
    if answer in ("a", "alle", "alles", "immer") and risk != Risk.AUTOSTART:
        return "immer"
    return "einmal" if answer in ("j", "ja", "y", "yes") else "nein"


class _Thinking:
    """Zeigt "denkt nach (12 s)", solange das Modell noch nichts geschickt hat -
    damit klar ist, dass die KI arbeitet und nicht haengt."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._lock = threading.Lock()
        self._active = False
        self._shown = 0
        self._token = 0

    def start(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._active:
                return
            self._active = True
            self._token += 1
            token = self._token
        threading.Thread(target=self._run, args=(token, time.monotonic()), daemon=True).start()

    def _run(self, token: int, began: float) -> None:
        time.sleep(1.5)  # kurze Antworten ohne Flackern
        while True:
            with self._lock:
                if not self._active or token != self._token:
                    return
                msg = f" … denkt nach ({int(time.monotonic() - began)} s, Strg+C = anhalten)"
                sys.stdout.write("\b" * self._shown + msg + " " * max(0, self._shown - len(msg))
                                 + "\b" * max(0, self._shown - len(msg)))
                sys.stdout.flush()
                self._shown = len(msg)
            time.sleep(1.0)

    def stop(self) -> None:
        with self._lock:
            self._active = False
            if self._shown:
                sys.stdout.write("\b" * self._shown + " " * self._shown + "\b" * self._shown)
                sys.stdout.flush()
                self._shown = 0


class CLI:
    def __init__(self, config: Config, started_by: str | None = None):
        self.config = config
        self.started_by = started_by  # gesetzt, wenn die KI unerwartet automatisch gestartet wurde
        self.memory = Memory(config.memory.db_path)
        self.thinking = _Thinking(bool(sys.stdout) and sys.stdout.isatty())
        self.permissions = PermissionManager(
            config.permissions, config.workspace_path, confirm_fn=self._confirm,
            app_root=config.project_root,
        )
        self.registry = build_registry(include_computer=True)
        self.tool_ctx = ToolContext(permissions=self.permissions, memory=self.memory)
        self.tool_ctx.extra["app_root"] = config.project_root
        self.brain = Brain(config, self.memory, self.registry, self.tool_ctx)
        self.brain.provider.wait_fn = self.thinking.start
        self.voice_out = VoiceOutput(config.voice.speak_responses)
        self.voice_in = VoiceInput(config.voice.enabled)
        self.voice_mode = config.voice.enabled and self.voice_in.available()
        self.voice_capture = VoiceCapture(config.voice)
        self.reader = VoiceLineReader(self.voice_capture, enabled=config.voice.f2_aufnahme)
        self.reader.warm_up()
        self.updater = Updater(config.update, config.project_root)
        self.exit_code = 0
        self._pending_update: UpdateInfo | None = None
        self._pending_shown = False
        self._stop_watch = threading.Event()

    def _permission_answer(self, message: str, risk: Risk) -> str:
        """'einmal', 'immer' oder 'nein' - im Terminal per Eingabe, in der App per Knopf."""
        return _ask_permission(message, risk)

    def _ask_yes(self, question: str, default: bool = False) -> bool:
        self.thinking.stop()
        return _yes(question, default)

    def _confirm(self, message: str, risk: Risk) -> bool:
        self.thinking.stop()
        answer = self._permission_answer(message, risk)
        if answer == "immer":
            self._set_auto_confirm(True)
        return answer in ("einmal", "immer")

    def _set_auto_confirm(self, value: bool) -> None:
        """Schaltet das Nachfragen dauerhaft an/aus (auch nach einem Neustart)."""
        self.permissions.settings.auto_confirm = value
        try:
            path = save_setting(self.config.project_root, "permissions", "auto_confirm",
                                "true" if value else "false")
            where = f"gespeichert in {path}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Einstellung nicht gespeichert: %s", exc)
            where = "nur fuer diese Sitzung - die Einstellungsdatei liess sich nicht aendern"
        if value:
            print(_c(f"[Ab jetzt frage ich nicht mehr nach und mache alles durch ({where}). "
                     "Zurueck mit /erlauben fragen.]", GREEN))
        else:
            print(_c(f"[Ab jetzt frage ich vor jeder Aktion wieder nach ({where}).]", GREEN))

    # -- Charakter & Profil ----------------------------------------------------
    def _character_command(self, args: list[str]) -> None:
        from ..profil import CHARACTERS, active_character, apply_character

        if not args:
            current = active_character(self.config)
            print(_c("\nCharaktere (waehlen mit /charakter <Name>):", BOLD))
            for ch in CHARACTERS:
                mark = "  <- aktiv" if ch.key == current else ""
                print(f"  {ch.key:<11} {ch.name} - {ch.description}{mark}")
            if current == "eigen":
                print(_c("  (Gerade aktiv: deine eigene Persoenlichkeit aus config/persona.md)", GREY))
            return
        try:
            chosen = apply_character(self.config, args[0].lower())
        except ValueError as exc:
            print(_c(str(exc), YELLOW))
            return
        print(_c(f"Charakter '{chosen.name}' gewaehlt (gespeichert in config/persona.md - die alte ist "
                 "in data/persona-sicherungen/).", GREEN))
        if self._ask_yes("Jetzt ein neues Gespraech beginnen, damit er gleich gilt? [J/n] ", default=True):
            self._new_conversation()

    def _style_command(self, args: list[str]) -> None:
        from ..profil import STYLE_OPTIONS, set_style

        if len(args) < 2:
            s = self.config.style
            print(_c(f"Stil: Anrede {s.anrede}, Laenge {s.laenge}, Humor {s.humor}, Emojis {s.emojis}", CYAN))
            options = "; ".join(f"{k}: {'/'.join(v for v, _ in opts)}" for k, opts in STYLE_OPTIONS.items())
            print(_c(f"Aendern z.B. mit /stil anrede Sie  -  {options}", GREY))
            return
        try:
            set_style(self.config, args[0].lower(), args[1])
        except ValueError as exc:
            print(_c(str(exc), YELLOW))
            return
        print(_c(f"Gespeichert: {args[0]} = {args[1]}. Gilt ab dem naechsten Gespraech (/neu).", GREEN))

    def _about_command(self, text: str) -> None:
        from ..profil import ABOUT_FIELDS, save_about

        key, sep, value = text.partition("=")
        key = key.strip().lower()
        fields = {k: label for k, label, _ in ABOUT_FIELDS}
        if not sep:
            print(_c("\nDas weiss die KI ueber dich (aendern: /ueber-mich feld = wert):", BOLD))
            for k, label, example in ABOUT_FIELDS:
                print(f"  {k:<11} {label}: {self.config.about.get(k) or _c(example, GREY)}")
            return
        if key not in fields:
            print(_c(f"Unbekanntes Feld '{key}'. Moeglich: {', '.join(fields)}", YELLOW))
            return
        about = dict(self.config.about)
        about[key] = value.strip()
        save_about(self.config, about)
        print(_c(f"Gespeichert: {fields[key]} = {value.strip() or '(leer)'}. Gilt ab dem naechsten Gespraech (/neu).",
                 GREEN))

    # -- Stuetzraeder ----------------------------------------------------------
    def training_wheels_state(self) -> str:
        p = self.permissions.settings
        if p.safe_mode and not p.auto_confirm and not p.allow_full_filesystem:
            return "an"
        if not p.safe_mode and p.auto_confirm and p.allow_full_filesystem:
            return "aus"
        return "teilweise"

    def set_training_wheels(self, on: bool) -> None:
        """An: Safe Mode, nur Arbeitsordner, fragt nach. Aus: ganzer PC, ohne Rueckfrage."""
        p = self.permissions.settings
        p.safe_mode, p.auto_confirm, p.allow_full_filesystem = on, not on, not on
        for key, value in (("safe_mode", on), ("auto_confirm", not on), ("allow_full_filesystem", not on)):
            save_setting(self.config.project_root, "permissions", key, "true" if value else "false")

    def _training_wheels_command(self, args: list[str]) -> None:
        sub = args[0].lower() if args else ""
        if sub not in ("an", "aus"):
            state = self.training_wheels_state()
            print(_c(f"Stuetzraeder: {state.upper()}. Umschalten: /stuetzraeder an  bzw.  /stuetzraeder aus", CYAN))
            print(_c("  an  = fragt vor jeder Aenderung, nur im Arbeitsordner, keine Shell/PC-Steuerung", GREY))
            print(_c("  aus = ganzer PC, Shell und PC-Steuerung, keine Rueckfragen", GREY))
            return
        if sub == "aus" and not self._ask_yes(
            "Stuetzraeder AB? Dann darf ich am GANZEN PC alles - Dateien aendern und loeschen, Programme "
            "starten, Maus und Tastatur steuern - ohne vorher zu fragen. [j/N] "
        ):
            return
        self.set_training_wheels(sub == "an")
        if sub == "an":
            print(_c("Stuetzraeder sind dran: ich frage vor Aenderungen und bleibe im Arbeitsordner.", GREEN))
        else:
            print(_c("Stuetzraeder sind ab: ich darf am ganzen PC alles ohne Rueckfrage. "
                     "Automatische Starts frage ich trotzdem.", GREEN))

    # -- Aussehen der App ------------------------------------------------------
    def _appearance_command(self, args: list[str]) -> None:
        from .. import aussehen

        if args[:1] == ["zuruecksetzen"]:
            aussehen.reset(self.config.project_root)
            print(_c("Die App sieht wieder aus wie im Original.", GREEN))
            notify = self.tool_ctx.extra.get("on_appearance")
            if notify:
                notify()
            return
        print(aussehen.describe(self.config.project_root))
        print(_c("Aendern: sag mir einfach, wie die App aussehen soll (z.B. 'mach sie gruen').", GREY))

    # -- Tutorial ----------------------------------------------------------------
    def _tutorial_terminal(self) -> None:
        from ..tutorial import mark_done, steps

        all_steps = steps(self.config)
        for i, step in enumerate(all_steps, start=1):
            print(_c(f"\n[{i}/{len(all_steps)}] {step['titel']}", BOLD))
            print(step["text"])
            hint = "Enter = weiter, z = zeig es mir, q = beenden" if step.get("zeigen") else "Enter = weiter, q = beenden"
            try:
                answer = input(_c(f"   ({hint}) ", GREY)).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if answer == "q":
                return
            if answer == "z" and step.get("zeigen"):
                print(_c(f"\n{self.config.ki.name}: ", CYAN), end="", flush=True)
                snapshot = self.brain.provider.history_snapshot()
                try:
                    self.brain.respond(step["zeigen"], on_text=self._emit)
                except KeyboardInterrupt:
                    self.brain.provider.abort_turn(snapshot, step["zeigen"])
                print()
        mark_done(self.config.project_root)

    # -- Jarvis-Modus im Terminal -------------------------------------------------
    def _jarvis_terminal(self) -> None:
        from ..live import LiveLoop, LocalVoice, live_available, recognizer_factory, setup_live
        from ..voice import Speaker

        problem = self.voice_capture.problem()
        if problem:
            print(_c(problem, YELLOW))
            return
        root, settings = self.config.project_root, self.config.voice
        if settings.live_mitschrift and not live_available(root, settings) and not getattr(sys, "frozen", False):
            print(_c("Ich richte einmalig die Live-Mitschrift ein (~50 MB) …", GREY))
            ok, message = setup_live(root, settings, progress=_progress_line)
            print(_c("\r" + message + " " * 10, CYAN if ok else YELLOW))
        speaker = Speaker(settings.sprache or "de")
        if not speaker.available:
            print(_c("Zum Vorlesen fehlt pyttsx3 - tippe /sprache einrichten vorlesen. Ich antworte dann nur als Text.",
                     YELLOW))
        host = _TerminalLiveHost(self)
        loop = LiveLoop(host, LocalVoice(speaker), settings, recognizer_factory=recognizer_factory(root, settings))
        host.loop = loop
        provider = self.brain.provider
        provider.effort_override = (settings.live_denktiefe or "").strip() or None
        print(_c("\n[Jarvis-Modus] Sprich einfach - ich hoere die ganze Zeit zu und du kannst mich jederzeit "
                 "unterbrechen. 'Chat-Modus' sagen oder Strg+C = zurueck.", BOLD))
        try:
            loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            provider.effort_override = None
            host.wait()
            speaker.stop()
        print(_c("\n[Zurueck im Chat-Modus]", GREY))

    def _open_in_editor(self, name: str) -> None:
        path = self.config.project_root / "config" / name
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606 - oeffnet die Datei im Standard-Editor
            else:
                import subprocess

                subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", str(path)])
            print(_c(f"{name} ist im Editor geoeffnet. Nach dem Speichern: /neu", CYAN))
        except Exception as exc:  # noqa: BLE001
            print(_c(f"Bitte selbst oeffnen: {path} ({exc})", YELLOW))

    def _new_conversation(self) -> None:
        self.brain.new_conversation()
        print(_c(f"Neues Gespraech - {self.config.ki.name} hat Charakter, Stil und dein Profil frisch "
                 "geladen. Das bisherige Gespraech ist als Zusammenfassung im Gedaechtnis.", GREEN))

    def _name_command(self, text: str) -> None:
        """'/name Max' oder '/name MAX = Mein Assistent X' - dauerhaft speichern."""
        name, _, meaning = text.partition("=")
        name, meaning = name.strip().strip('"'), meaning.strip().strip('"')
        if not name:
            k = self.config.ki
            print(_c(f"Ich heisse {k.name}" + (f" ({k.bedeutung})" if k.bedeutung else "")
                     + ". Aendern: /name Neuer Name = Bedeutung", CYAN))
            return
        if len(name) > 40 or any(c in name for c in '\n"\\'):
            print(_c("Bitte einen kurzen Namen ohne Anfuehrungszeichen.", YELLOW))
            return
        meaning = meaning.replace('"', "'")
        self.config.ki.name, self.config.ki.bedeutung = name, meaning
        try:
            save_setting(self.config.project_root, "ki", "name", f'"{name}"')
            save_setting(self.config.project_root, "ki", "bedeutung", f'"{meaning}"')
        except Exception as exc:  # noqa: BLE001
            print(_c(f"Konnte den Namen nicht speichern: {exc}", YELLOW))
            return
        print(_c(f"Ich heisse jetzt {name}" + (f" ({meaning})" if meaning else "")
                 + ". Im Gespraech wirkt der neue Name ab dem naechsten Start ganz.", GREEN))

    def _switch_to_app(self) -> bool:
        from ..app.launcher import spawn_app

        if spawn_app(self.config.project_root, wait_for_pid=os.getpid()):
            print(_c("Die App oeffnet sich gleich - dieses Fenster schliesst sich.", CYAN))
            self.exit_code = 43  # start.bat: ohne "Taste druecken" schliessen
            return True
        print(_c("Die App liess sich nicht starten.", YELLOW))
        return False

    def _shortcut_command(self) -> None:
        from ..app.launcher import create_desktop_shortcut

        try:
            path = create_desktop_shortcut(self.config.project_root, self.config.ki.name)
            print(_c(f"Auf dem Desktop liegt jetzt '{self.config.ki.name}' - Doppelklick oeffnet die App. ({path})", GREEN))
        except Exception as exc:  # noqa: BLE001
            print(_c(f"Konnte keine Verknuepfung anlegen: {exc}", YELLOW))

    def _allow_command(self, args: list[str]) -> None:
        sub = args[0].lower() if args else ""
        p = self.permissions.settings
        if sub in ("alles", "alle", "immer"):
            self._set_auto_confirm(True)
            if p.safe_mode:
                print(_c("Hinweis: Safe Mode ist noch AN - Shell, Loeschen und PC-Steuerung bleiben "
                         "gesperrt. Ausschalten: in config/settings.toml 'safe_mode = false'.", YELLOW))
        elif sub in ("fragen", "nachfragen", "aus"):
            self._set_auto_confirm(False)
        else:
            state = "AN - ich frage nicht nach" if p.auto_confirm else "AUS - ich frage vor jeder Aktion"
            print(_c(f"Alles erlauben ist {state}. Aendern: /erlauben alles  bzw.  /erlauben fragen", CYAN))

    # -- Start --------------------------------------------------------------
    def run(self) -> int:
        """Gibt den Rueckgabecode zurueck (42 = nach einem Update neu starten)."""
        self._print_banner()
        if self.started_by:
            print(
                _c(
                    f"\n[Hinweis] Ich wurde automatisch gestartet - {self.started_by}. Wenn du das "
                    "nicht willst: /autostart zeigt, was mich startet, und stellt es ab.",
                    YELLOW,
                )
            )
        if not self.config.api_key:
            key_name = "DEEPSEEK_API_KEY" if self.config.active_provider == "deepseek" else "ANTHROPIC_API_KEY"
            env_path = self.config.project_root / ".env"
            print(
                _c(
                    f"\nAchtung: Kein {key_name} gefunden. Trage deinen Schluessel in diese "
                    f"Datei ein (Zeile {key_name}=...):\n  {env_path}\n"
                    "Ohne Schluessel kann das Gehirn nicht denken.\n",
                    YELLOW,
                )
            )
        try:
            if self._startup_update():
                return self.exit_code  # Update installiert -> Neustart
            self._start_update_watch()
            self._loop()
        except (KeyboardInterrupt, EOFError):
            print()
        finally:
            self._stop_watch.set()
            self._shutdown()
        return self.exit_code

    def _loop(self) -> None:
        while True:
            self._show_pending_update()
            user_text = self._get_input()
            if user_text is None:
                continue
            user_text = user_text.strip()
            if not user_text:
                continue
            if user_text.startswith("/"):
                if self._handle_command(user_text):
                    break
                continue

            # Antwort streamen. Strg+C haelt nur diese Antwort an, nicht die ganze KI.
            print(_c(f"\n{self.config.ki.name}: ", CYAN), end="", flush=True)
            snapshot = self.brain.provider.history_snapshot()
            try:
                answer = self.brain.respond(user_text, on_text=self._emit)
            except KeyboardInterrupt:
                self.thinking.stop()
                self.brain.provider.abort_turn(snapshot, user_text)
                print(_c("\n[Angehalten. Schreib einfach weiter - z.B. was sie anders machen soll.]", YELLOW))
                continue
            except Exception as exc:  # noqa: BLE001 - ein Fehler darf die Sitzung nicht beenden
                self.thinking.stop()
                logger.exception("Fehler bei der Antwort")
                self.brain.provider.abort_turn(snapshot, user_text)
                print(_c(f"\n[Da ist etwas schiefgegangen ({exc}). Versuch es einfach nochmal.]", YELLOW))
                continue
            finally:
                self.thinking.stop()
            try:
                print()
                if self.config.economy.aktiv:
                    self._print_cost_line()
                print()
                if self.voice_out.enabled:
                    self.voice_out.speak(answer)
            except KeyboardInterrupt:
                self.voice_out.stop()  # Strg+C beim Vorlesen: nur das Vorlesen anhalten
                print(_c("\n[Vorlesen angehalten.]", GREY))

    # -- Ein-/Ausgabe -------------------------------------------------------
    def _emit(self, chunk: str) -> None:
        self.thinking.stop()
        print(chunk, end="", flush=True)

    def _get_input(self) -> str | None:
        if self.voice_mode:
            print(_c("\n[Sprich jetzt… (oder Enter druecken, um zu tippen)]", GREY))
            try:
                typed = input(_c("Du: ", GREEN))
            except (EOFError, KeyboardInterrupt):
                raise
            if typed.strip():
                return typed
            spoken = self.voice_in.listen(language="de-DE")
            if spoken:
                print(_c(f"Du (gesprochen): {spoken}", GREEN))
                return spoken
            print(_c("(nichts verstanden)", GREY))
            return None
        return self.reader.read("\n" + _c("Du: ", GREEN))

    # -- Befehle ------------------------------------------------------------
    def _handle_command(self, cmd: str) -> bool:
        """Verarbeitet /-Befehle. Gibt True zurueck, wenn beendet werden soll."""
        base = cmd.lower().split()[0]
        if base in ("/beenden", "/quit", "/exit"):
            return True
        if base in ("/hilfe", "/help"):
            print(__doc__)
        elif base == "/status":
            self._print_status()
        elif base in ("/gedaechtnis", "/memory"):
            self._print_memory()
        elif base in ("/kosten", "/cost"):
            self._print_cost_detail()
        elif base == "/sprache":
            self._voice_command(cmd.split()[1:])
        elif base == "/update":
            return self._update_command()
        elif base in ("/versionen", "/version"):
            self._print_versions()
        elif base in ("/zurueck", "/zurück"):
            return self._restore_command(cmd.split()[1:])
        elif base == "/autostart":
            self._autostart_command(cmd.split()[1:])
        elif base == "/erlauben":
            self._allow_command(cmd.split()[1:])
        elif base == "/app":
            return self._switch_to_app()
        elif base == "/charakter":
            self._character_command(cmd.split()[1:])
        elif base == "/stil":
            self._style_command(cmd.split()[1:])
        elif base in ("/ueber-mich", "/übermich", "/über-mich", "/uebermich"):
            self._about_command(cmd.split(None, 1)[1] if len(cmd.split(None, 1)) > 1 else "")
        elif base in ("/werte", "/persona"):
            self._open_in_editor("werte.md" if base == "/werte" else "persona.md")
        elif base == "/neu":
            self._new_conversation()
        elif base in ("/stuetzraeder", "/stützräder", "/stuetzrad", "/stützrad"):
            self._training_wheels_command(cmd.split()[1:])
        elif base == "/jarvis":
            self._jarvis_terminal()
        elif base in ("/tutorial", "/tour"):
            self._tutorial_terminal()
        elif base == "/aussehen":
            self._appearance_command(cmd.split()[1:])
        elif base == "/name":
            self._name_command(cmd.split(None, 1)[1] if len(cmd.split(None, 1)) > 1 else "")
        elif base in ("/verknuepfung", "/verknüpfung"):
            self._shortcut_command()
        else:
            print(_c(f"Unbekannter Befehl: {base}. /hilfe zeigt alle.", YELLOW))
        return False

    # -- Sprache --------------------------------------------------------------
    def _voice_command(self, args: list[str]) -> None:
        sub = (args[0].lower() if args else "")
        if sub == "einrichten":
            packages = ["pyttsx3"] if args[1:2] == ["vorlesen"] else self.voice_capture.packages()
            print(_c(f"Installiere {', '.join(packages)} …", GREY))
            ok, message = install_voice_packages(packages=packages)
            if not ok:
                print(_c(message, YELLOW))
            elif packages == ["pyttsx3"]:
                if VoiceOutput(True).enabled:
                    print(_c("Vorlesen ist eingerichtet - schalte es mit /sprache vorlesen ein.", CYAN))
                else:
                    print(_c("Installiert - bitte starte die KI einmal neu, dann /sprache vorlesen.", YELLOW))
            else:
                problem = self.voice_capture.problem()
                print(_c(problem or "Spracheingabe ist eingerichtet. Halte F2 gedrueckt und sprich.",
                         YELLOW if problem else CYAN))
                if not problem:
                    self.reader.warm_up()
                    if self.config.voice.live_mitschrift:
                        from ..live import setup_live

                        print(_c("Lade die Live-Mitschrift fuer den Jarvis-Modus (Vosk, ~50 MB) …", GREY))
                        ok, message = setup_live(self.config.project_root, self.config.voice,
                                                 progress=_progress_line)
                        print(_c("\r" + message + " " * 10, CYAN if ok else YELLOW))
        elif sub == "vorlesen":
            if not self.voice_out.enabled:
                self.voice_out = VoiceOutput(True)
                print(_c("Vorlesen ist AN." if self.voice_out.enabled else
                         "Vorlesen ist noch nicht eingerichtet - tippe /sprache einrichten vorlesen.", CYAN))
            else:
                self.voice_out.enabled = False
                print(_c("Vorlesen ist AUS.", CYAN))
        elif sub in ("an", "aus"):
            self._toggle_voice()
        else:
            problem = self.voice_capture.problem()
            if not self.config.voice.f2_aufnahme:
                print(_c("Die Sprechtaste F2 ist aus ([voice] f2_aufnahme = false).", YELLOW))
            elif problem:
                print(_c(problem, YELLOW))
            else:
                backend = self.voice_capture.backend()
                name = "Whisper (offline)" if backend == "whisper" else "Google (online)"
                print(_c(f"Spracheingabe bereit - Erkennung: {name}.", CYAN))
                print(_c("F2 halten = sprechen; F2 kurz druecken = Mikrofon an/aus.", GREY))

    def _toggle_voice(self) -> None:
        if not self.voice_in.available():
            print(
                _c(
                    "Sprachmodus nicht verfuegbar. Installiere: pip install SpeechRecognition sounddevice",
                    YELLOW,
                )
            )
            return
        self.voice_mode = not self.voice_mode
        print(_c(f"Sprachmodus ist jetzt {'AN' if self.voice_mode else 'AUS'}.", CYAN))

    # -- Automatische Starts ------------------------------------------------
    def _autostart_command(self, args: list[str]) -> None:
        print(_c("Suche, was die KI automatisch startet … (kann einige Sekunden dauern)", GREY))
        entries = finde_autostarts(self.config.project_root, self.config.workspace_path)
        if args[:1] == ["entfernen"] and entries:
            chosen = entries if args[1:2] == ["alle"] else [
                entries[int(a) - 1] for a in args[1:] if a.isdigit() and 1 <= int(a) <= len(entries)
            ]
            if not chosen:
                print(_c("Welche? z.B. /autostart entfernen 1  oder  /autostart entfernen alle", YELLOW))
                return
            for entry in chosen:
                if not self._ask_yes(f"\n{entry.describe()}\nEntfernen? [j/N] "):
                    continue
                try:
                    print(_c(entferne(entry, self.config.project_root), GREEN))
                except Exception as exc:  # noqa: BLE001
                    print(_c(f"Konnte nicht entfernt werden: {exc}", YELLOW))
            return
        if not entries:
            print(_c("Nichts gefunden: Weder Aufgabenplanung noch Autostart noch ein Hintergrund-"
                     "Skript startet die KI.", CYAN))
        else:
            print(_c("\nDas startet die KI (oder Skripte aus ihrem Ordner) automatisch:", BOLD))
            for i, entry in enumerate(entries, start=1):
                print(f"  {i}) {entry.describe()}")
            print(_c("\nAbstellen: /autostart entfernen <Nr>   (oder: /autostart entfernen alle)", GREY))
        starts = StartGuard(self.config.project_root).starts()[-8:]
        if starts:
            print(_c("\nLetzte Starts der KI:", BOLD))
            for s in starts:
                mark = "  <- unerwartet" if s.get("unerwartet") else ""
                print(f"  {s.get('zeit', '?').replace('T', ' ')}  gestartet {s.get('gestartet', '?')}{mark}")

    # -- Updates ------------------------------------------------------------
    def _startup_update(self) -> bool:
        """Beim Start nachschauen (hoechstens einmal pro Tag). True = neu starten."""
        up = self.updater
        if not up.enabled or up.paused or not up.due():
            return False
        info = up.check()
        if info is None:
            return False
        return self._offer_update(info, ask=not up.automatic)

    def _start_update_watch(self) -> None:
        """Laeuft die KI lange, schaut sie trotzdem regelmaessig nach."""
        if not self.updater.enabled:
            return

        def watch() -> None:
            while not self._stop_watch.wait(3600):
                try:
                    if self._pending_update or self.updater.paused or not self.updater.due():
                        continue
                    info = self.updater.check()
                    if info:
                        self._pending_update = info
                except Exception as exc:  # noqa: BLE001
                    logger.info("Update-Pruefung im Hintergrund: %s", exc)

        threading.Thread(target=watch, name="update-watch", daemon=True).start()

    def _show_pending_update(self) -> None:
        if self._pending_update and not self._pending_shown:
            self._pending_shown = True
            print(
                _c(
                    f"\n[Neue Version {self._pending_update.new} verfuegbar - tippe /update, "
                    "um zu sehen, was neu ist, und sie zu installieren.]",
                    YELLOW,
                )
            )

    def _explain_update(self, info: UpdateInfo) -> str:
        notes = info.notes.strip() or "(Zu dieser Version gibt es keine Beschreibung.)"
        if not self.config.api_key:
            return notes
        prompt = (
            f"Fuer dich gibt es ein Update: von Version {info.current} auf {info.new}. "
            f"Das steht in den Versionshinweisen:\n\n{notes[:6000]}\n\n"
            "Erklaere deinem Menschen in 2 bis 5 kurzen Stichpunkten, was neu ist und was er "
            "damit jetzt tun kann. Sprich ihn direkt mit 'du' an. Keine Einleitung, keine Rueckfragen."
        )
        print(_c("(einen Moment, ich schaue mir die Neuerungen an …)", GREY))
        return self.brain.provider.ask_once(prompt) or notes

    def _offer_update(self, info: UpdateInfo, ask: bool) -> bool:
        """Zeigt die Neuerungen, installiert (ggf. nach Rueckfrage). True = neu starten."""
        if info.kind == "quelle" and self.updater.is_git_checkout:
            # Entwickler-Ordner: kein automatisches Ueberschreiben, keine KI-Kosten.
            print(_c(f"\n[Version {info.new} liegt im Repo - dieser Ordner ist ein Git-Checkout: "
                     "bitte 'git pull'.]", YELLOW))
            return False
        print(_c(f"\nNeue Version {info.new} verfuegbar (du hast {info.current}).", BOLD))
        print(_c(f"{self.config.ki.name}: ", CYAN) + self._explain_update(info))
        if ask and not self._ask_yes("\nJetzt aktualisieren? Deine alte Version wird gesichert. [J/n] ", default=True):
            print(_c("Ok - spaeter jederzeit mit /update.", GREY))
            return False
        try:
            message = self.updater.install(info, say=lambda m: print(_c(m, GREY)))
        except UpdateError as exc:
            print(_c(f"Update nicht installiert: {exc}", YELLOW))
            return False
        except Exception as exc:  # noqa: BLE001
            logger.exception("Update fehlgeschlagen")
            print(_c(f"Update fehlgeschlagen: {exc}. Deine bisherige Version laeuft weiter.", YELLOW))
            return False
        self._pending_update = None
        print(_c(message, GREEN))
        return self._restart(info.kind)

    def _restart(self, kind: str) -> bool:
        if kind == "exe":
            try:
                self.updater.restart_exe()
                print(_c("Starte die neue Version …", CYAN))
            except Exception as exc:  # noqa: BLE001
                print(_c(f"Bitte starte KI.exe jetzt neu ({exc}).", YELLOW))
            self.exit_code = 0
        elif os.environ.get("KI_NEUSTART") == "1":  # gesetzt von start.bat / start.sh
            print(_c("Starte neu …", CYAN))
            self.exit_code = RESTART_EXIT_CODE
        else:
            print(_c("Bitte starte die KI jetzt neu, damit die neue Version laeuft.", YELLOW))
            self.exit_code = 0
        return True

    def _update_command(self) -> bool:
        print(_c("Schaue nach einer neuen Version …", GREY))
        info = self._pending_update or self.updater.check()
        if info is None:
            if self.updater.last_error:
                print(_c(f"Konnte nicht nachschauen: {self.updater.last_error}", YELLOW))
            else:
                print(_c(f"Du hast die neueste Version ({__version__}).", CYAN))
            return False
        return self._offer_update(info, ask=True)

    def _print_versions(self) -> None:
        print(_c(f"\nAktuelle Version: {__version__}", BOLD))
        backups = self.updater.backups()
        if not backups:
            print(_c("Noch keine alten Versionen gesichert (das passiert bei jedem Update).", GREY))
            return
        print("Gesicherte Versionen (neueste zuerst):")
        for i, b in enumerate(backups, start=1):
            stamp = b.name.split("_", 1)[-1].replace("_", " ")
            print(f"  {i}) Version {b.version}  - gesichert {stamp}")
        print(_c("Zurueck zu einer davon: /zurueck <Nr>", GREY))

    def _restore_command(self, args: list[str]) -> bool:
        if not args:
            self._print_versions()
            return False
        if not self._ask_yes(f"Wirklich zu '{args[0]}' zurueckkehren? Die jetzige Version wird gesichert. [j/N] "):
            return False
        try:
            message = self.updater.restore(args[0], say=lambda m: print(_c(m, GREY)))
        except UpdateError as exc:
            print(_c(str(exc), YELLOW))
            return False
        print(_c(message, GREEN))
        return self._restart("exe" if self.updater.frozen else "quelle")

    def _print_memory(self) -> None:
        facts = self.memory.top_facts(40)
        if not facts:
            print(_c("Noch nichts gelernt.", GREY))
            return
        print(_c(f"\nGelerntes ({self.memory.count_facts()} Eintraege):", BOLD))
        for f in facts:
            print(f"  #{f.id} [{f.category}] (Wichtigkeit {f.importance}) {f.content}")

    def _print_cost_line(self) -> None:
        u = self.brain.usage
        usd, eur = self.brain.cost()
        print(
            _c(
                f"[Sitzung: {u.total_tokens} Token "
                f"(Cache-Treffer: {u.cache_hit_tokens}) ~ {eur:.4f} EUR]",
                GREY,
            )
        )

    def _print_cost_detail(self) -> None:
        u = self.brain.usage
        usd, eur = self.brain.cost()
        print(_c("\nKosten dieser Sitzung:", BOLD))
        print(f"  Provider:        {self.config.active_provider} ({self.config.active_model})")
        print(f"  Input (voll):    {u.input_full_tokens} Token")
        print(f"  Input (Cache):   {u.cache_hit_tokens} Token (stark verbilligt)")
        print(f"  Output:          {u.output_tokens} Token")
        print(f"  Gesamt:          {u.total_tokens} Token")
        print(f"  Geschaetzt:      {usd:.4f} USD  (~{eur:.4f} EUR)")
        print(_c("  (Preise anpassbar in config/settings.toml unter [preise].)", GREY))

    def _print_status(self) -> None:
        p = self.config.permissions
        print(_c("\nStatus:", BOLD))
        print(f"  Provider:        {self.config.active_provider}")
        print(f"  Modell:          {self.config.active_model}")
        if self.config.active_provider == "claude":
            print(f"  Denk-Tiefe:      effort={self.config.claude.effort}")
        print(f"  Sparmodus:       {'AN' if self.config.economy.aktiv else 'aus'}")
        print(f"  Arbeitsordner:   {self.config.workspace_path}")
        print(f"  Safe Mode:       {'AN (gefaehrliche Aktionen gesperrt)' if p.safe_mode else 'AUS'}")
        print(f"  Auto-Bestaetigen: {'AN' if p.auto_confirm else 'AUS (fragt nach)'}")
        print(f"  Voller FS-Zugriff: {'JA' if p.allow_full_filesystem else 'nein (Sandbox)'}")
        print(f"  Werkzeuge:       {', '.join(self.registry.names())}")
        print(f"  Sprachmodus:     {'AN' if self.voice_mode else 'aus'}")
        print(f"  Version:         {__version__} (Updates: {self.config.update.modus})")
        env_path = self.config.project_root / ".env"
        print(f"  Einstellungen:   {self.config.settings_file or '(keine Datei - Standardwerte)'}")
        print(f"  Schluessel-Datei: {env_path} ({'gefunden' if env_path.is_file() else 'FEHLT'})")

    def _print_banner(self) -> None:
        name = self.config.ki.name
        meaning = self.config.ki.bedeutung.strip()
        print(_c(f"\n=== {name}{' - ' + meaning if meaning else ' - deine lernfaehige KI'} ===", BOLD))
        print(
            _c(
                f"Gehirn: {self.config.active_provider} ({self.config.active_model})"
                + ("  |  Sparmodus AN" if self.config.economy.aktiv else ""),
                GREY,
            )
        )
        print(_c("Rede einfach los. '/hilfe' fuer Befehle, '/beenden' zum Schluss.", GREY))
        if self.config.voice.f2_aufnahme and sys.stdin.isatty():
            print(_c("Sprechen: bei leerer Zeile F2 halten (oder kurz druecken = Mikrofon an/aus).", GREY))
        if self.config.permissions.safe_mode:
            print(
                _c(
                    "Safe Mode ist aktiv: Ich kann reden, lesen, suchen und im Arbeitsordner "
                    "schreiben. Fuer Loeschen, Shell und PC-Steuerung schalte in "
                    "config/settings.toml 'safe_mode = false' frei.",
                    GREY,
                )
            )

    def _shutdown(self) -> None:
        print(_c("Speichere, was ich gelernt habe…", GREY))
        try:
            self.brain.end_session_summary()
        except Exception:  # noqa: BLE001
            pass
        self.memory.close()
        print(_c("Bis bald!", CYAN))


JARVIS_HINT = (
    "\n\n[Sprachmodus: Antworte kurz und natuerlich gesprochen - ohne Tabellen, Code und Listen-Zeichen.]"
)
_EXIT_PHRASES = ("chat modus", "chatmodus", "chat-modus", "jarvis aus", "sprachmodus aus", "sprachmodus beenden",
                 "jarvis beenden", "zurueck zum chat", "zurück zum chat")


def _is_exit_phrase(text: str) -> bool:
    low = text.lower().strip(" .!?,")
    return any(p in low for p in _EXIT_PHRASES) or low in ("beenden", "ende", "tschuess", "tschüss")


def _yes(question: str, default: bool = False) -> bool:
    try:
        answer = input(_c(question, YELLOW)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default
    return answer in ("j", "ja", "y", "yes")


def run_cli(config: Config, started_by: str | None = None) -> int:
    return CLI(config, started_by=started_by).run()


def _progress_line(done: int, total: int) -> None:
    if total:
        print(_c(f"\r  Sprachmodell: {done * 100 // total} % ({done // 1_000_000} von {total // 1_000_000} MB)",
                 GREY), end="", flush=True)


class _TerminalLiveHost:
    """Jarvis-Modus im Terminal: Antworten laufen in einem eigenen Thread, damit
    Nova weiter zuhoert (und unterbrochen werden kann), waehrend sie antwortet."""

    def __init__(self, cli: "CLI"):
        self.cli = cli
        self.loop = None
        self.worker: threading.Thread | None = None
        self.drop = False

    def event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "heard":
            text = event.get("text", "")
            if event.get("final"):
                print("\r\x1b[K" + (_c(f"Du: {text}", GREEN) + "\n" if text else ""), end="", flush=True)
            elif text:
                print("\r\x1b[K" + _c(f"Du: {text} …", GREY), end="", flush=True)
        elif kind == "jarvis":
            if event.get("error"):
                print(_c(f"\n{event['error']}", YELLOW))
            state = event.get("state")
            if state == "listening":
                print("\r\x1b[K" + _c("[hoere zu …]", GREY), end="", flush=True)
            elif state == "recognizing":
                print("\r\x1b[K" + _c("[verstehe …]", GREY), end="", flush=True)

    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def start_turn(self, text: str) -> bool:
        if self.busy():
            return False
        provider = self.cli.brain.provider
        provider.cancel_event.clear()
        self.cli.tool_ctx.extra["cancel_event"] = provider.cancel_event
        model_text = text + JARVIS_HINT
        print(_c(f"{self.cli.config.ki.name}: ", CYAN), end="", flush=True)

        def work() -> None:
            snapshot = provider.history_snapshot()
            cancelled = False
            try:
                self.cli.brain.respond(model_text, on_text=self._on_text)
            except KeyboardInterrupt:  # angehalten (Dazwischenreden, Stopp)
                cancelled = True
                if not (self.drop and provider.drop_turn(snapshot, model_text)):
                    provider.abort_turn(snapshot, text)
            except Exception as exc:  # noqa: BLE001
                provider.abort_turn(snapshot, text)
                print(_c(f"\nFehler: {exc}", YELLOW))
            finally:
                self.drop = False
                print()
                if self.loop is not None:
                    self.loop.on_turn_end(cancelled)

        self.worker = threading.Thread(target=work, name="jarvis-antwort", daemon=True)
        self.worker.start()
        return True

    def _on_text(self, chunk: str) -> None:
        from ..live import split_tool_lines

        self.cli._emit(chunk)
        text, tool = split_tool_lines(chunk)
        if tool:
            self.loop.on_tool()
        if text.strip():
            self.loop.on_text(text)

    def cancel_turn(self, drop: bool) -> None:
        self.drop = drop
        self.cli.brain.provider.cancel()

    def transcribe(self, pcm: bytes) -> str:
        return self.cli.voice_capture.transcribe(pcm)

    def pending_ask(self) -> dict | None:
        return None

    def answer_ask(self, ask_id: str, value: str) -> None:  # noqa: ARG002
        return None

    def is_exit(self, text: str) -> bool:
        return _is_exit_phrase(text)

    def wait(self, timeout: float = 30.0) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.cli.brain.provider.cancel()
            self.worker.join(timeout)
