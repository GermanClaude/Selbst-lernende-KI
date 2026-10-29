"""Gemeinsame Basis fuer alle Provider: Token-Zaehlung, Kosten, Werkzeug-Hilfen."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from ..config import Config
from ..tools import ToolContext, ToolRegistry

StreamFn = Callable[[str], None]

# Wird angezeigt, wenn die KI ihr Schritt-Limit fuer eine Nachricht erreicht.
LIMIT_NOTE = (
    "\n\n[Ich habe das Limit von {n} Werkzeug-Schritten fuer diese Nachricht erreicht "
    "und halte hier an. Schreib einfach \"weiter\", dann mache ich genau an dieser "
    "Stelle weiter.]"
)
TRUNCATED_NOTE = (
    "\n\n[Meine Antwort wurde wegen der Laengenbegrenzung (max_tokens) abgeschnitten. "
    "Schreib \"weiter\", dann mache ich weiter.]"
)
# Werkzeug-Ergebnis, wenn ein Aufruf abgeschnitten wurde und nicht ausgefuehrt wird.
TRUNCATED_TOOL_ERROR = (
    "Nicht ausgefuehrt: Deine Antwort wurde wegen der Laengenbegrenzung (max_tokens) "
    "abgeschnitten, die Eingabe dieses Werkzeugs ist unvollstaendig. Schreibe grosse "
    "Dateien in mehreren kleineren Teilen (datei_schreiben mit anhaengen=true)."
)
# Platzhalter im Verlauf, wenn das Modell eine Anfrage abgelehnt hat (die Teil-
# Antwort darf nicht im Verlauf bleiben, sonst lehnt die API jede Folgeanfrage ab).
REFUSAL_PLACEHOLDER = "(Diese Anfrage habe ich abgelehnt.)"
# Anleitung fuer die Verlaufs-Zusammenfassung (fuer beide Provider gleich).
SUMMARY_INSTRUCTION = (
    "Fasse das folgende Gespraech zwischen einem Menschen und seinem KI-Assistenten auf "
    "Deutsch in knappen Stichpunkten zusammen, damit der Assistent nahtlos weiterarbeiten "
    "kann. Beginne mit der aktuellen Aufgabe und ihrem Ziel und damit, was als Naechstes "
    "zu tun ist. Behalte ausserdem: Namen, Vorlieben, Entscheidungen; was bereits erledigt "
    "ist (welche Dateien gelesen, angelegt oder geaendert wurden, mit Pfad und dem "
    "Wichtigsten zum Inhalt); offene Probleme."
)


def summary_input(history_text: str, limit: int = 60_000, head: int = 8_000) -> str:
    """Anfang (Aufgabe bzw. fruehere Zusammenfassung) + Ende (aktueller Stand)."""
    if len(history_text) <= limit:
        return history_text
    return history_text[:head] + "\n…(Mitte ausgelassen)…\n" + history_text[-(limit - head) :]


@dataclass
class Usage:
    """Verbrauchte Token - getrennt nach voll bezahltem Input, Cache-Treffern, Output."""

    input_full_tokens: int = 0  # Input ohne Cache-Treffer (voller Preis)
    cache_hit_tokens: int = 0   # aus dem Cache (sehr guenstig)
    output_tokens: int = 0

    def add(self, input_full: int = 0, cache_hit: int = 0, output: int = 0) -> None:
        self.input_full_tokens += max(0, input_full)
        self.cache_hit_tokens += max(0, cache_hit)
        self.output_tokens += max(0, output)

    @property
    def total_tokens(self) -> int:
        return self.input_full_tokens + self.cache_hit_tokens + self.output_tokens


class LLMProvider(ABC):
    """Oberklasse fuer ein 'Gehirn'. Jeder Provider verwaltet seinen eigenen Verlauf."""

    name: str = "unbekannt"

    def __init__(
        self,
        config: Config,
        system_prompt: str,
        registry: ToolRegistry,
        tool_ctx: ToolContext,
        client: Any = None,
    ):
        self.config = config
        self.system_prompt = system_prompt
        self.registry = registry
        self.tool_ctx = tool_ctx
        self.client = client
        self.usage = Usage()

    # -- von Unterklassen zu implementieren ---------------------------------
    @abstractmethod
    def respond(
        self, user_text: str, on_text: StreamFn | None = None, max_tool_rounds: int | None = None
    ) -> str: ...

    @abstractmethod
    def history_length(self) -> int: ...

    def user_turns(self) -> int:
        """Anzahl der Nachrichten vom Menschen (Werkzeug-Schritte zaehlen nicht)."""
        return self.history_length()

    def history_chars(self) -> int:
        """Ungefaehre Groesse des Verlaufs in Zeichen (fuer die Kompaktierung)."""
        return 0

    @abstractmethod
    def summarize_history(self) -> str: ...

    @abstractmethod
    def reset_to_summary(self, summary: str) -> None: ...

    # -- gemeinsam ----------------------------------------------------------
    def _rounds(self, max_tool_rounds: int | None) -> int:
        return max(1, max_tool_rounds or self.config.conversation.max_werkzeug_runden)

    def _exec_tool(self, name: str, tool_input: Any) -> tuple[str, bool]:
        """Fuehrt ein Werkzeug aus und kuerzt die Ausgabe im Sparmodus."""
        output, is_error = self.registry.execute(self.tool_ctx, name, tool_input)
        tool = self.registry.get(name)
        # Werkzeuge, die selbst abschnittsweise liefern (datei_lesen), nicht kuerzen -
        # sonst sieht die KI Dateien nie vollstaendig und liest sie immer wieder.
        if tool is not None and not getattr(tool, "sparmodus_kuerzen", True):
            return output, is_error
        cap = self.config.economy.max_werkzeug_ausgabe if self.config.economy.aktiv else 0
        if cap and len(output) > cap:
            output = output[:cap] + "\n…(Ausgabe gekuerzt, um Token zu sparen)"
        return output, is_error

    def cost(self) -> tuple[float, float]:
        """Geschaetzte Kosten dieser Sitzung in (USD, EUR)."""
        return self.config.cost_estimate(
            self.usage.input_full_tokens, self.usage.cache_hit_tokens, self.usage.output_tokens
        )
