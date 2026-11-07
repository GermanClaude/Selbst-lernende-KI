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
  /beenden            - Sitzung beenden (speichert eine Zusammenfassung)
"""
from __future__ import annotations

import os
import sys
import threading

from .. import __version__
from ..brain import Brain
from ..config import Config
from ..logging_setup import get_logger
from ..memory import Memory
from ..permissions import PermissionManager, Risk
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
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{RESET}"


def _confirm(message: str, risk: Risk) -> bool:
    """Fragt den Nutzer interaktiv um Bestaetigung fuer eine Aktion."""
    label = {Risk.MODERATE: "Aktion", Risk.DANGEROUS: "GEFAEHRLICHE Aktion"}.get(risk, "Aktion")
    print(_c(f"\n[{label}] {message}", YELLOW))
    try:
        answer = input(_c("   Erlauben? [j/N] ", YELLOW)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("j", "ja", "y", "yes")


class CLI:
    def __init__(self, config: Config):
        self.config = config
        self.memory = Memory(config.memory.db_path)
        self.permissions = PermissionManager(
            config.permissions, config.workspace_path, confirm_fn=_confirm
        )
        self.registry = build_registry(include_computer=True)
        self.tool_ctx = ToolContext(permissions=self.permissions, memory=self.memory)
        self.brain = Brain(config, self.memory, self.registry, self.tool_ctx)
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

    # -- Start --------------------------------------------------------------
    def run(self) -> int:
        """Gibt den Rueckgabecode zurueck (42 = nach einem Update neu starten)."""
        self._print_banner()
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

            # Antwort streamen.
            print(_c(f"\n{self.config.ki.name}: ", CYAN), end="", flush=True)
            answer = self.brain.respond(user_text, on_text=self._emit)
            print()
            if self.config.economy.aktiv:
                self._print_cost_line()
            print()
            if self.voice_out.enabled:
                self.voice_out.speak(answer)

    # -- Ein-/Ausgabe -------------------------------------------------------
    def _emit(self, chunk: str) -> None:
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
        if ask and not _yes("\nJetzt aktualisieren? Deine alte Version wird gesichert. [J/n] ", default=True):
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
        if not _yes(f"Wirklich zu '{args[0]}' zurueckkehren? Die jetzige Version wird gesichert. [j/N] "):
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
        print(_c(f"\n=== {name} - deine lernfaehige KI ===", BOLD))
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


def _yes(question: str, default: bool = False) -> bool:
    try:
        answer = input(_c(question, YELLOW)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default
    return answer in ("j", "ja", "y", "yes")


def run_cli(config: Config) -> int:
    return CLI(config).run()
