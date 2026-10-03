"""Die Chat-Oberflaeche: so redest du mit deiner KI (per Tastatur, optional Sprache).

Sonderbefehle (mit '/' beginnen):
  /hilfe        - Hilfe anzeigen
  /sprache      - Sprachmodus an/aus (falls verfuegbar)
  /status       - aktuelle Einstellungen & Sicherheitslage zeigen
  /gedaechtnis  - zeigen, was die KI gelernt hat
  /kosten       - Token-Verbrauch & geschaetzte Kosten dieser Sitzung
  /beenden      - Sitzung beenden (speichert eine Zusammenfassung)
"""
from __future__ import annotations

import sys

from ..brain import Brain
from ..config import Config
from ..memory import Memory
from ..permissions import PermissionManager, Risk
from ..tools import ToolContext, build_registry
from ..voice import VoiceInput, VoiceOutput

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

    # -- Start --------------------------------------------------------------
    def run(self) -> None:
        self._print_banner()
        if not self.config.api_key:
            key_name = "DEEPSEEK_API_KEY" if self.config.active_provider == "deepseek" else "ANTHROPIC_API_KEY"
            print(
                _c(
                    f"\nAchtung: Kein {key_name} gefunden. Lege eine .env-Datei an "
                    "(siehe .env.example) und trage deinen Schluessel ein.\n"
                    "Ohne Schluessel kann das Gehirn nicht denken.\n",
                    YELLOW,
                )
            )
        try:
            self._loop()
        except (KeyboardInterrupt, EOFError):
            print()
        finally:
            self._shutdown()

    def _loop(self) -> None:
        while True:
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
        try:
            return input(_c("\nDu: ", GREEN))
        except (EOFError, KeyboardInterrupt):
            raise

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
            self._toggle_voice()
        else:
            print(_c(f"Unbekannter Befehl: {base}. /hilfe zeigt alle.", YELLOW))
        return False

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


def run_cli(config: Config) -> None:
    CLI(config).run()
