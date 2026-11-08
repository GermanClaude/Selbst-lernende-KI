"""Gemeinsame Basis fuer alle Provider: Token-Zaehlung, Kosten, Werkzeug-Hilfen."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from ..cancel import Abgebrochen
from ..config import Config
from ..tools import ToolContext, ToolRegistry
from ..tools.base import ToolOutput

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
# Steht im Verlauf, wenn du eine Antwort mit Strg+C abgebrochen hast.
ABORT_NOTE = "(Mein Mensch hat diese Antwort mit Strg+C abgebrochen. Ich warte auf seine naechste Nachricht.)"
# Zeitlimits fuer die Verbindung zum Modell: kommt so lange nichts an, gilt die
# Verbindung als tot (statt bis zu 10 Minuten zu warten) - dann neuer Versuch.
CONNECT_TIMEOUT = 15.0
READ_TIMEOUT = 180.0
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


# Bilder im Verlauf: so viele Zeichen zaehlt ein Bild fuer die Kompaktierung (grob seine
# Token-Kosten). Sehr grosse Bilder zaehlen nach ihrer Base64-Laenge mehr, damit die Anfrage
# nie die Groessengrenze der API sprengt (400 000 Zeichen ~ hoechstens ~25 MB Bilddaten).
BILD_ZEICHEN = 6000
_BILD_BYTES_PRO_ZEICHEN = 64
# Text, wenn jemand nur ein Bild ohne Worte schickt (die APIs wollen keinen leeren Text).
LEER_EIN_BILD = "Schau dir das Bild an."
LEER_BILDER = "Schau dir die Bilder an."
# Antwort, wenn die API eine neue Nachricht mit Bild ablehnt (sie bleibt dann nicht im Verlauf).
BILD_ABGELEHNT = ("Das Modell hat die Nachricht mit Bild abgelehnt (siehe Fehler oben). "
                  "Bitte nochmal senden - wenn es wieder nicht klappt, mit einem anderen Bild.")


class BildTeil(dict):
    """Bild-Block im Verlauf - ein ganz normales dict fuer die API, merkt sich aber nebenbei
    den Dateinamen (fuer "[Bild: name]" in Zusammenfassungen). Der Name geht nie mit an die
    API; der Block selbst wird nach dem Anlegen nie mehr veraendert (append-only)."""

    __slots__ = ("bild_name",)

    def __init__(self, *args: Any, bild_name: str = "", **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.bild_name = bild_name


def bild_platzhalter(block: Any) -> str:
    name = getattr(block, "bild_name", "") or ""
    return f"[Bild: {name}]" if name else "[Bild]"


def bild_gewicht(base64_laenge: int) -> int:
    """Wie viele Zeichen ein Bild fuer die Kompaktierung zaehlt (siehe BILD_ZEICHEN)."""
    return max(BILD_ZEICHEN, int(base64_laenge or 0) // _BILD_BYTES_PRO_ZEICHEN)


def leerer_bildtext(user_text: str, anzahl: int) -> str:
    """Der Text zur Nachricht - bei nur Bildern ein kurzer Auftrag statt leerem Text."""
    if (user_text or "").strip():
        return user_text
    return LEER_BILDER if anzahl > 1 else LEER_EIN_BILD


def aufteilen(output: Any) -> tuple[str, list]:
    """Werkzeug-Ergebnis -> (Text, Bilder). Strings haben keine Bilder."""
    if isinstance(output, ToolOutput):
        return (output.text, list(output.bilder))
    return (str(output), [])


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
    usd: float = 0.0            # Kosten, mit dem Preis des Modells, das gerade lief

    def add(self, input_full: int = 0, cache_hit: int = 0, output: int = 0, usd: float = 0.0) -> None:
        self.input_full_tokens += max(0, input_full)
        self.cache_hit_tokens += max(0, cache_hit)
        self.output_tokens += max(0, output)
        self.usd += max(0.0, usd)

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
        self.hit_limit = False          # hat die letzte Antwort am Schritt-Limit aufgehoert?
        self.last_text = ""             # Text der letzten Modell-Antwort (z.B. Bericht eines Agenten)
        self.wait_fn: Callable[[], None] | None = None  # "denkt nach"-Anzeige der Oberflaeche
        # Stopp-Knopf der App: von einem anderen Thread gesetzt, hier regelmaessig geprueft.
        self.cancel_event = threading.Event()
        self._active_stream: Any = None
        self._children: list["LLMProvider"] = []  # laufende Agenten (mit anhalten)
        # Sprachmodus: schneller antworten (Claude denkt weniger tief). None = Einstellung.
        self.effort_override: str | None = None
        # Letzte Nachricht mit Bildern: (id der Verlaufs-Nachricht, Text des Menschen) - damit
        # drop_turn sie wiedererkennt, obwohl dort Bild-Bloecke/Beschreibungen mit drinstehen.
        self._bild_turn: tuple[int, str] | None = None

    # -- von Unterklassen zu implementieren ---------------------------------
    @abstractmethod
    def respond(
        self,
        user_text: str,
        on_text: StreamFn | None = None,
        max_tool_rounds: int | None = None,
        announce_limit: bool = True,
        allow_tools: bool = True,
        bilder: list | None = None,
    ) -> str:
        """Eine Nachricht beantworten. `bilder` (list[assistant.bilder.Bild]) haengt Bilder an
        diese eine Nachricht an - schon verkleinert, sie werden danach nie mehr veraendert."""

    # -- Abbrechen mit Strg+C ------------------------------------------------
    def history_snapshot(self) -> int:
        return len(getattr(self, "messages", []))

    def abort_turn(self, snapshot: int | None = None, user_text: str = "") -> None:
        """Nach Strg+C (oder einem Fehler): den Verlauf wieder gueltig machen.

        Alles Fertige bleibt erhalten - die KI weiss also noch, was sie schon getan
        hat. Nur ein angefangener Werkzeugaufruf ohne Ergebnis wird als "abgebrochen"
        geschlossen (sonst scheitert jede weitere Anfrage). Es wird nur angehaengt,
        nichts frueheres veraendert.
        """
        messages = getattr(self, "messages", None)
        if not messages:
            return
        self._close_open_tool_calls(messages)
        if messages[-1].get("role") != "assistant":
            messages.append({"role": "assistant", "content": ABORT_NOTE})
        self.hit_limit = False

    def drop_turn(self, snapshot: int | None, user_text: str) -> bool:
        """Nimmt eine gerade angefangene Runde ganz zurueck - nur, wenn darin noch
        nichts passiert ist (kein Werkzeug). Fuer den Sprachmodus: "Wie wird das
        Wetter?" ... "in Berlin" wird zu einer Frage zusammengefasst."""
        messages = getattr(self, "messages", None)
        if messages is None or snapshot is None or not 0 <= snapshot < len(messages):
            return False
        first = messages[snapshot]
        if first.get("role") != "user":
            return False
        same = _plain_text(first.get("content")).strip() == user_text.strip()
        if not same and self._bild_turn is not None:
            # Nachricht mit Bildern: dort stehen noch Bild-Bloecke/Beschreibungen mit drin.
            same = self._bild_turn[0] == id(first) and self._bild_turn[1].strip() == user_text.strip()
        if not same:
            return False
        if any(_has_tool_parts(m) for m in messages[snapshot:]):
            return False
        del messages[snapshot:]
        self.hit_limit = False
        self._bild_turn = None
        return True

    def _close_open_tool_calls(self, messages: list) -> None:
        """Von den Providern ueberschrieben: offene Werkzeugaufrufe schliessen."""

    # -- Anhalten aus einem anderen Thread (App) ---------------------------------
    def cancel(self) -> None:
        """Haelt die laufende Antwort an: setzt das Signal und schliesst offene Streams,
        damit auch eine still wartende Verbindung sofort endet."""
        self.cancel_event.set()
        for provider in [self, *list(self._children)]:
            stream = provider._active_stream
            if stream is not None:
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Abgebrochen()

    def _waiting(self) -> None:
        self._check_cancel()
        if self.wait_fn:
            try:
                self.wait_fn()
            except Exception:  # noqa: BLE001 - Anzeige darf nie stoeren
                pass

    @abstractmethod
    def history_length(self) -> int: ...

    def ask_once(self, prompt: str, max_tokens: int = 1500) -> str:
        """Einmalige Frage ohne Verlauf und Werkzeuge (z.B. Update-Neuigkeiten erklaeren).

        Gibt "" zurueck, wenn es nicht klappt - Aufrufer haben einen Rueckfall.
        """
        return ""

    def _ask_system(self) -> str:
        return (
            f"Du bist {self.config.ki.name}, ein freundlicher KI-Assistent, der lokal auf dem "
            "Computer deines Menschen laeuft. Antworte auf Deutsch, kurz und klar."
        )

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

    def _exec_tool(self, name: str, tool_input: Any) -> tuple[str | ToolOutput, bool]:
        """Fuehrt ein Werkzeug aus und kuerzt die Ausgabe im Sparmodus.

        Ergebnis ist ein Text - oder ein ToolOutput, wenn das Werkzeug Bilder mitliefert
        (gekuerzt wird dann nur der Text, nie die Bilddaten)."""
        self._check_cancel()
        output, is_error = self.registry.execute(self.tool_ctx, name, tool_input)
        self._check_cancel()
        text, bilder = aufteilen(output)
        tool = self.registry.get(name)
        # Werkzeuge, die selbst abschnittsweise liefern (datei_lesen), nicht kuerzen -
        # sonst sieht die KI Dateien nie vollstaendig und liest sie immer wieder.
        if tool is None or getattr(tool, "sparmodus_kuerzen", True):
            cap = self.config.economy.max_werkzeug_ausgabe if self.config.economy.aktiv else 0
            if cap and len(text) > cap:
                text = text[:cap] + "\n…(Ausgabe gekuerzt, um Token zu sparen)"
        if bilder:
            return ToolOutput(text, bilder), is_error
        return text, is_error

    def settings_changed(self) -> None:
        """Modell oder Denk-Tiefe wurde umgestellt (gilt ab der naechsten Anfrage)."""

    def _count(self, input_full: int = 0, cache_hit: int = 0, output: int = 0,
               model: str | None = None) -> None:
        """Verbrauch zaehlen - mit dem Preis des Modells, das gerade eingestellt ist
        (wer mitten im Gespraech das Modell wechselt, bekommt trotzdem stimmige Kosten).
        `model`: ein anderes Modell hat gearbeitet (z.B. DeepSeek Flash beschreibt ein Bild)."""
        usd, _eur = self.config.cost_estimate(input_full, cache_hit, output, provider=self.name,
                                              model=model, per_request=True)
        self.usage.add(input_full=input_full, cache_hit=cache_hit, output=output, usd=usd)

    def cost(self) -> tuple[float, float]:
        """Geschaetzte Kosten dieser Sitzung in (USD, EUR)."""
        u = self.usage
        if u.usd <= 0 and u.total_tokens:
            usd, _ = self.config.cost_estimate(u.input_full_tokens, u.cache_hit_tokens, u.output_tokens)
        else:
            usd = u.usd
        return (usd, usd * self.config.prices.usd_zu_eur)


def _plain_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "".join(parts)


def _has_tool_parts(message: dict) -> bool:
    if message.get("role") == "tool" or message.get("tool_calls"):
        return True
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if kind in ("tool_use", "tool_result", "server_tool_use"):
                return True
    return False
