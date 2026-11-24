"""Handy-Fernzugriff: Nova per Telegram vom Smartphone steuern - ohne eigenen Server.

Warum Telegram? Telegram hostet die Nachrichten kostenlos. Dein PC verbindet sich nur nach
aussen (Long-Poll auf https://api.telegram.org) und wartet auf neue Nachrichten - es muss also
KEIN Port freigegeben, KEIN Server gemietet und KEINE feste Adresse eingerichtet werden. Das
laeuft hinter Router und Firewall.

Einrichtung (einmalig): in Telegram den Bot "@BotFather" anschreiben -> /newbot -> Namen
vergeben -> du bekommst einen Token wie "123456:ABC-DEF...". Diesen Token legt Nova in der
.env als TELEGRAM_BOT_TOKEN ab (nie im Repo!). Danach schreibst du deinem eigenen Bot vom
Handy - die erste Nachricht legt fest, WER Nova fernsteuern darf.

Sicherheit:
- Nova gehorcht nur EINER Chat-ID (deiner). Alle anderen Absender werden ignoriert - selbst
  wenn jemand den Bot findet, kann er Nova nicht steuern.
- Der Token ist ein Geheimnis und steht nur lokal in der .env (die .gitignore schuetzt sie).
- Rueckfragen vor heiklen Aktionen gehen ans Handy ("ja"/"nein") - genau wie am PC.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 3900  # Telegram erlaubt 4096 Zeichen je Nachricht - mit etwas Reserve.

# Antworten auf eine Rueckfrage ("Darf ich ...?").
_JA = {"ja", "j", "jo", "jep", "jupp", "yes", "y", "ok", "okay", "klar", "mach", "machs",
       "mach es", "los", "go", "passt", "gerne", "sicher", "stimmt"}
_NEIN = {"nein", "n", "nee", "ne", "no", "lass", "lass es", "stopp", "stop", "abbrechen",
         "nicht", "bloss nicht", "auf keinen fall"}
# Den Fernzugriff per Handy-Nachricht beenden.
_STOP = {"stop", "stopp", "/stop", "/stopp", "/ende", "/beenden", "/aus", "aus", "ende", "beenden",
         "stop handy", "handy aus", "fernzugriff aus", "fernzugriff beenden", "feierabend", "schluss"}


class TelegramFehler(RuntimeError):
    """Etwas mit der Telegram-Verbindung stimmt nicht (Token falsch, offline ...)."""


@dataclass
class Nachricht:
    update_id: int
    chat_id: int
    text: str
    von: str = ""        # Vorname des Absenders (nur fuer die Begruessung)


def ist_ja(text: str) -> bool:
    return (text or "").strip().lower().rstrip("!.") in _JA


def ist_nein(text: str) -> bool:
    return (text or "").strip().lower().rstrip("!.") in _NEIN


def ist_stopp(text: str) -> bool:
    return (text or "").strip().lower().rstrip("!.") in _STOP


def _urllib_transport(token: str, method: str, params: dict, timeout: float) -> dict:
    """Standard-Transport ueber urllib (keine Zusatzpakete noetig)."""
    url = _API.format(token=token, method=method)
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            roh = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            beschreibung = json.loads(body).get("description", "")
        except Exception:  # noqa: BLE001
            beschreibung = body
        if exc.code in (401, 404):
            raise TelegramFehler("Der Bot-Token stimmt nicht (von @BotFather neu holen).") from exc
        raise TelegramFehler(f"Telegram meldet einen Fehler: {beschreibung or exc}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise TelegramFehler(f"Keine Verbindung zu Telegram ({exc}). Internet da?") from exc
    try:
        antwort = json.loads(roh)
    except ValueError as exc:
        raise TelegramFehler("Telegram hat etwas Unverstaendliches geschickt.") from exc
    if not antwort.get("ok"):
        raise TelegramFehler(f"Telegram: {antwort.get('description', 'unbekannter Fehler')}")
    return antwort.get("result")


@dataclass
class HandyRelay:
    """Minimaler Telegram-Bot-Client: verbinden, Nachrichten holen, antworten.

    transport(token, method, params, timeout) -> result  ist fuer Tests austauschbar."""
    token: str
    chat_id: int | None = None          # erlaubte Chat-ID; None = erste Nachricht legt sie fest
    transport: Callable[..., object] = _urllib_transport
    offset: int = 0                     # letzte verarbeitete update_id + 1
    bot_name: str = ""

    def _call(self, method: str, params: dict | None = None, timeout: float = 35.0):
        return self.transport(self.token, method, params or {}, timeout)

    def pruefe(self) -> str:
        """Prueft den Token und merkt sich den Bot-Namen. Wirft TelegramFehler, wenn er nicht geht."""
        info = self._call("getMe", timeout=15.0) or {}
        self.bot_name = info.get("username") or info.get("first_name") or "Bot"
        return self.bot_name

    def sende(self, text: str, chat_id: int | None = None) -> None:
        """Schickt Text ans Handy (lange Texte werden in mehrere Nachrichten geteilt)."""
        ziel = chat_id if chat_id is not None else self.chat_id
        if ziel is None:
            return
        text = (text or "").strip() or "(leer)"
        for stueck in _stuecke(text, MAX_LEN):
            self._call("sendMessage", {"chat_id": ziel, "text": stueck}, timeout=20.0)

    def tippt(self, chat_id: int | None = None) -> None:
        """Zeigt am Handy 'tippt ...' an (nett, aber nicht kritisch)."""
        ziel = chat_id if chat_id is not None else self.chat_id
        if ziel is None:
            return
        try:
            self._call("sendChatAction", {"chat_id": ziel, "action": "typing"}, timeout=10.0)
        except TelegramFehler:
            pass

    def hole(self, timeout: float = 30.0) -> list[Nachricht]:
        """Holt neue Text-Nachrichten (Long-Poll). Nur die der erlaubten Chat-ID - ist noch keine
        festgelegt, kommen alle (der Aufrufer legt dann die erste als Besitzer fest)."""
        result = self._call("getUpdates",
                             {"offset": self.offset, "timeout": int(timeout),
                              "allowed_updates": json.dumps(["message"])},
                             timeout=timeout + 10.0) or []
        nachrichten: list[Nachricht] = []
        for update in result:
            uid = int(update.get("update_id", 0))
            if uid >= self.offset:
                self.offset = uid + 1
            msg = update.get("message") or {}
            text = msg.get("text")
            chat = msg.get("chat") or {}
            cid = chat.get("id")
            if not text or cid is None:
                continue
            if self.chat_id is not None and int(cid) != int(self.chat_id):
                logger.info("Handy: Nachricht von fremder Chat-ID %s ignoriert", cid)
                continue
            nachrichten.append(Nachricht(update_id=uid, chat_id=int(cid), text=text,
                                         von=chat.get("first_name") or chat.get("username") or ""))
        return nachrichten

    def naechste(self, timeout: float = 30.0) -> Nachricht | None:
        """Die naechste einzelne Nachricht (oder None, wenn in der Zeit nichts kam)."""
        nachrichten = self.hole(timeout=timeout)
        return nachrichten[0] if nachrichten else None

    def leeren(self) -> None:
        """Alte, vor dem Start liegengebliebene Nachrichten ueberspringen (nicht abarbeiten)."""
        result = self._call("getUpdates", {"offset": -1, "timeout": 0}, timeout=15.0) or []
        for update in result:
            uid = int(update.get("update_id", 0))
            if uid >= self.offset:
                self.offset = uid + 1


def _stuecke(text: str, grenze: int) -> list[str]:
    """Teilt langen Text moeglichst an Zeilengrenzen in Stuecke <= grenze."""
    if len(text) <= grenze:
        return [text]
    stuecke: list[str] = []
    rest = text
    while len(rest) > grenze:
        schnitt = rest.rfind("\n", 0, grenze)
        if schnitt <= 0:
            schnitt = grenze
        stuecke.append(rest[:schnitt].rstrip("\n"))
        rest = rest[schnitt:].lstrip("\n")
    if rest:
        stuecke.append(rest)
    return stuecke


BEGRUESSUNG = (
    "Hallo! Ich bin {name} und hoere jetzt auf dein Handy. Schreib mir, was ich am PC tun soll.\n"
    "Zum Beenden: schreib \"stop\" (oder am PC Strg+C)."
)

HILFE = (
    "Fernzugriff per Telegram - Nova vom Handy steuern, ohne eigenen Server.\n"
    "So richtest du es EINMAL ein:\n"
    "  1) In Telegram den Bot \"@BotFather\" anschreiben, dann /newbot, und einen Namen vergeben.\n"
    "  2) Du bekommst einen Token wie 123456:ABC-DEF... . Den gibst du Nova so:\n"
    "       /handy token 123456:ABC-DEF...\n"
    "  3) Danach nochmal /handy: schreib deinem Bot vom Handy aus - die erste Nachricht legt\n"
    "     fest, dass NUR du Nova fernsteuern darfst. Alle anderen Absender werden ignoriert.\n"
    "Beenden: /handy aus (oder im Terminal Strg+C). Der Token bleibt lokal in der .env."
)


def relais_schleife(relay: HandyRelay,
                    beantworte: Callable[[str], str],
                    stop_event,
                    melde: Callable[[str, str], None] | None = None,
                    poll_timeout: float = 30.0) -> str:
    """Die eigentliche Fernzugriffs-Schleife (fuer Terminal UND App gleich).

    beantworte(text) -> Antworttext (ruft die KI auf). Rueckfragen vor heiklen Aktionen laufen
        NICHT hier, sondern ueber den beim Start gesetzten confirm_fn des Berechtigungssystems.
    stop_event: threading.Event - gesetzt = aufhoeren.
    melde(richtung, text): optionale Anzeige am PC ('rein' = vom Handy, 'raus' = Antwort).
    Gibt den Grund der Rueckkehr zurueck ('handy', 'pc', 'fehler')."""
    def _melde(richtung: str, text: str) -> None:
        if melde:
            try:
                melde(richtung, text)
            except Exception:  # noqa: BLE001
                pass

    try:
        while not stop_event.is_set():
            try:
                msg = relay.naechste(timeout=poll_timeout)
            except TelegramFehler as exc:
                logger.warning("Handy: %s", exc)
                time.sleep(5.0)       # kurz warten und erneut versuchen (z.B. WLAN-Aussetzer)
                continue
            if msg is None:
                continue
            if ist_stopp(msg.text):
                relay.sende("Alles klar, ich hoere auf dein Handy jetzt nicht mehr. Bis spaeter!")
                return "handy"
            _melde("rein", msg.text)
            relay.tippt()
            try:
                antwort = beantworte(msg.text)
            except Exception as exc:  # noqa: BLE001 - ein Fehler darf den Fernzugriff nicht beenden
                logger.exception("Handy: Fehler bei der Antwort")
                relay.sende(f"Da ist etwas schiefgegangen: {exc}. Versuch es nochmal.")
                continue
            antwort = (antwort or "").strip() or "(keine Antwort)"
            _melde("raus", antwort)
            try:
                relay.sende(antwort)
            except TelegramFehler as exc:
                logger.warning("Handy: Antwort kam nicht an (%s)", exc)
    except KeyboardInterrupt:
        return "pc"
    return "pc" if stop_event.is_set() else "fehler"
