"""Das "Gehirn": orchestriert den aktiven Provider (Claude oder DeepSeek).

Brain ist bewusst schlank. Die eigentliche Modell-Kommunikation und der
Werkzeug-Loop liegen im jeweiligen Provider (assistant/providers/). Brain kuemmert
sich um den System-Prompt, das Durcharbeiten langer Aufgaben (automatisch weiter
am Schritt-Limit), Agenten fuer Teilaufgaben, die Kompaktierung langer Verlaeufe
und das Speichern von Episoden ins Gedaechtnis.
"""
from __future__ import annotations

from typing import Any, Callable

from .config import Config
from .logging_setup import get_logger
from .memory import Memory
from .personality import build_agent_prompt, build_system_prompt
from .providers import LLMProvider, Usage, build_provider
from .tools import READ_ONLY_TOOLS, ToolContext, ToolRegistry, subset

logger = get_logger()

StreamFn = Callable[[str], None]

CONTINUE_PROMPT = (
    "Mach mit der Aufgabe genau dort weiter, wo du aufgehoert hast. Lies nichts erneut, "
    "was du schon kennst."
)
AGENT_REPORT_PROMPT = (
    "Dein Schritt-Limit ist erreicht. Schreibe JETZT ohne weitere Werkzeuge deinen "
    "Ergebnisbericht: was du herausgefunden bzw. erledigt hast (mit Pfaden/Quellen) und "
    "was noch offen ist."
)


class Brain:
    def __init__(
        self,
        config: Config,
        memory: Memory,
        registry: ToolRegistry,
        tool_ctx: ToolContext,
        provider: LLMProvider | None = None,
        client: Any = None,
    ):
        self.config = config
        self.memory = memory
        self.registry = registry
        self.tool_ctx = tool_ctx
        self.system_prompt = build_system_prompt(config, memory)
        self.provider = provider or build_provider(
            config, self.system_prompt, registry, tool_ctx, client=client
        )
        self._on_text: StreamFn | None = None
        self._agent_running = False
        tool_ctx.extra["agent_runner"] = self.run_agent

    @property
    def usage(self) -> Usage:
        return self.provider.usage

    def cost(self) -> tuple[float, float]:
        return self.provider.cost()

    def respond(self, user_text: str, on_text: StreamFn | None = None) -> str:
        """Antwortet; erreicht die KI ihr Schritt-Limit, arbeitet sie (bis zu
        'automatisch_weiter' mal) von selbst weiter, statt anzuhalten."""
        self._on_text = on_text
        conv = self.config.conversation
        extra = max(0, int(conv.automatisch_weiter or 0))
        parts: list[str] = []
        text = user_text
        for part in range(extra + 1):
            answer = self.provider.respond(
                text,
                on_text=on_text,
                max_tool_rounds=conv.max_werkzeug_runden,
                announce_limit=(part == extra),
            )
            parts.append(answer)
            if not getattr(self.provider, "hit_limit", False) or part == extra:
                break
            if on_text:
                on_text(f"\n\n[Ich arbeite weiter … (Abschnitt {part + 2}) - Strg+C haelt an]\n")
            # zwischendurch nur, wenn der Verlauf zu gross wird; Strg+C dabei = nicht weitermachen
            if not self._maybe_compact(only_if_large=True):
                break
            text = CONTINUE_PROMPT
        self._maybe_compact()
        return "\n".join(p for p in parts if p).strip()

    # -- Agenten ------------------------------------------------------------
    def run_agent(self, role: str, task: str, context: str = "") -> str:
        """Fuehrt einen Agenten (eigene KI-Sitzung mit frischem Verlauf) aus."""
        if self._agent_running:
            return "Ein Agent kann keine weiteren Agenten starten - erledige es selbst."
        emit = self._on_text or (lambda _s: None)
        names = self.registry.names()
        if role == "helfer":
            tool_names = [n for n in names if n != "agent_beauftragen"]
        elif role == "pruefer":
            tool_names = [*READ_ONLY_TOOLS, "shell_befehl"]  # darf Tests ausfuehren
        else:
            tool_names = list(READ_ONLY_TOOLS)
        agent = build_provider(
            self.config,
            build_agent_prompt(self.config, role),
            subset(self.registry, tool_names),
            self.tool_ctx,
            client=self.provider.client,
        )
        agent.wait_fn = self.provider.wait_fn
        agent.cancel_event = self.provider.cancel_event  # Stopp-Knopf haelt auch den Agenten an
        self.provider._children.append(agent)

        def show(chunk: str) -> None:
            # Vom Agenten nur die Werkzeug-Schritte zeigen - sein Ergebnis fasst die KI zusammen.
            if "nutze Werkzeug:" in chunk:
                emit(f"    [Agent {role}] {chunk.strip()}\n")

        short = " ".join(task.split())
        emit(f"\n  >> Agent '{role}' startet: {short[:110]}{'…' if len(short) > 110 else ''}\n")
        self._agent_running = True
        try:
            agent.respond(
                f"Auftrag:\n{task}\n\nKontext:\n{context or '(keiner)'}",
                on_text=show,
                max_tool_rounds=self.config.conversation.agent_runden,
                announce_limit=False,
            )
            limit_reached = agent.hit_limit
            if limit_reached:
                # Sonst kaeme nach vielen Schritten gar kein Bericht zurueck.
                agent.respond(AGENT_REPORT_PROMPT, on_text=show, max_tool_rounds=1,
                              announce_limit=False, allow_tools=False)
            result = agent.last_text or "(Der Agent hat keinen Bericht geliefert - evtl. Verbindungsproblem.)"
        finally:
            self._agent_running = False
            if agent in self.provider._children:
                self.provider._children.remove(agent)
            u = agent.usage  # Kosten des Agenten zaehlen zur Sitzung
            self.provider.usage.add(input_full=u.input_full_tokens, cache_hit=u.cache_hit_tokens,
                                    output=u.output_tokens)
        emit(f"  << Agent '{role}' fertig\n")
        if limit_reached:
            result += "\n(Hinweis: Der Agent hat sein Schritt-Limit erreicht - das Ergebnis ist evtl. unvollstaendig.)"
        return f"Ergebnisbericht des Agenten ({role}):\n{result}"

    def _maybe_compact(self, only_if_large: bool = False) -> bool:
        """Fasst den Verlauf ggf. zusammen. False = mit Strg+C abgebrochen."""
        try:
            self._compact(only_if_large)
        except KeyboardInterrupt:
            # Die Antwort ist schon fertig - Zusammenfassen einfach auslassen.
            logger.info("Zusammenfassung mit Strg+C uebersprungen.")
            return False
        return True

    def _compact(self, only_if_large: bool) -> None:
        # Gezaehlt werden nur DEINE Nachrichten, nicht die Werkzeug-Schritte der KI:
        # sonst wuerde mitten in einer Programmieraufgabe alles Gelesene vergessen.
        turns = self.provider.user_turns()
        chars = self.provider.history_chars()
        max_chars = self.config.conversation.max_verlauf_zeichen
        too_large = bool(max_chars and chars > max_chars)
        if only_if_large and not too_large:
            return
        if turns < self.config.compact_threshold and not too_large:
            return
        logger.info("Kompaktiere Verlauf (%d Nachrichten, ~%d Zeichen).", turns, chars)
        self.provider._waiting()  # "denkt nach" - sonst sieht es nach Haengen aus
        summary = self.provider.summarize_history()
        if summary:
            self.memory.add_episode(summary)
            self.provider.reset_to_summary(summary)

    def new_conversation(self) -> None:
        """Neues Gespraech: das bisherige landet als Zusammenfassung im Gedaechtnis,
        Charakter, Stil, 'Ueber mich' und Werte werden frisch geladen."""
        from .config import _load_about, _read_text, bundle_dir

        try:
            self.end_session_summary()
        except Exception as exc:  # noqa: BLE001
            logger.info("Zusammenfassung beim Neustart: %s", exc)
        cfg_dir = self.config.project_root / "config"
        bundled = bundle_dir() / "config"
        self.config.persona_text = _read_text(cfg_dir / "persona.md") or _read_text(bundled / "persona.md")
        self.config.values_text = _read_text(cfg_dir / "werte.md") or _read_text(bundled / "werte.md")
        self.config.about = _load_about(cfg_dir / "ueber_mich.json")
        old = self.provider
        self.system_prompt = build_system_prompt(self.config, self.memory)
        new = build_provider(self.config, self.system_prompt, self.registry, self.tool_ctx, client=old.client)
        new.usage, new.wait_fn, new.cancel_event = old.usage, old.wait_fn, old.cancel_event
        new.effort_override = getattr(old, "effort_override", None)  # z.B. Jarvis-Modus: schnell antworten
        self.provider = new

    def end_session_summary(self) -> None:
        if self.provider.user_turns() < 1 or self.provider.history_length() < 2:
            return
        summary = self.provider.summarize_history()
        if summary:
            self.memory.add_episode(summary)
