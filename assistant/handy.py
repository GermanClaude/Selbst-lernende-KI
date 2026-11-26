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
import queue
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
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
    zeit: int = 0        # wann geschrieben (Unix-Zeit von Telegram)


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
        return self._auswerten(result)

    def _auswerten(self, result: list) -> list[Nachricht]:
        nachrichten: list[Nachricht] = []
        for update in result:
            uid = int(update.get("update_id", 0))
            if uid < self.offset:          # schon gesehen (Telegram schickt bei Webhooks auch mal doppelt)
                continue
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
            try:
                zeit = int(msg.get("date") or 0)
            except (TypeError, ValueError):
                zeit = 0
            nachrichten.append(Nachricht(update_id=uid, chat_id=int(cid), text=text,
                                         von=chat.get("first_name") or chat.get("username") or "", zeit=zeit))
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


class WebhookRelay(HandyRelay):
    """Fuer die Cloud: Telegram SCHICKT die Nachrichten (Webhook) statt dass Nova fragt (getUpdates).
    So weckt eine Nachricht eine schlafende Cloud-Nova auf (z.B. Render: schlaeft nach 15 Min. ohne Besuch).
    Die Webhook-Route des Servers wirft die Updates mit einwerfen() hier ein; die Fernzugriffs-Schleife
    holt sie wie gewohnt mit naechste() ab."""
    kein_rueckstand = True               # nichts "fuer spaeter" ablegen - in der Cloud wird gleich geantwortet
    still = True                         # keine Begruessung bei jedem Aufwachen

    def __init__(self, token: str, chat_id: int | None = None, transport=_urllib_transport):
        super().__init__(token, chat_id=chat_id, transport=transport)
        self._eingang: queue.Queue = queue.Queue(maxsize=200)
        self.wecken: Callable[[], None] | None = None   # Fernzugriff starten, falls er gerade nicht laeuft

    def webhook_setzen(self, url: str, geheim: str) -> None:
        self._call("setWebhook", {"url": url, "secret_token": geheim,
                                  "allowed_updates": json.dumps(["message"])}, timeout=20.0)

    def einwerfen(self, update: dict) -> None:
        for n in self._auswerten([update] if isinstance(update, dict) else []):
            try:
                self._eingang.put_nowait(n)
            except queue.Full:
                logger.warning("Handy: zu viele Nachrichten auf einmal - eine verworfen")
        if self.wecken is not None:
            try:
                self.wecken()
            except Exception:  # noqa: BLE001
                logger.exception("Handy: Fernzugriff liess sich nicht starten")

    def hole(self, timeout: float = 30.0) -> list[Nachricht]:
        try:
            erste = self._eingang.get(timeout=timeout) if timeout > 0 else self._eingang.get_nowait()
        except queue.Empty:
            return []
        alle = [erste]
        while True:
            try:
                alle.append(self._eingang.get_nowait())
            except queue.Empty:
                return alle

    def naechste(self, timeout: float = 30.0) -> Nachricht | None:
        try:
            return self._eingang.get(timeout=timeout)
        except queue.Empty:
            return None

    def leeren(self) -> None:
        while not self._eingang.empty():
            self._eingang.get_nowait()


def kopplungs_code() -> str:
    """6-stelliger Code, den nur du am PC siehst - wer ihn dem Bot schickt, ist der Besitzer."""
    import secrets

    return f"{secrets.randbelow(10 ** 6):06d}"


def ist_kopplung(text: str, code: str) -> bool:
    return bool(code) and code in "".join(str(text or "").split())


# -- Nachrichten, die ankamen, waehrend der PC/Nova aus war --------------------------------------
# Telegram hebt Nachrichten an den Bot rund 24 Stunden auf. Beim naechsten Start holt Nova sie ab,
# legt sie hier lokal ab (bleiben auch, wenn du "spaeter" sagst oder das Fenster schliesst) und fragt
# nach, ob sie sie umsetzen soll. Nur Nachrichten der festgelegten Chat-ID (siehe HandyRelay.hole).
MAX_OFFEN = 50
MAX_OFFEN_TEXT = 2000


def rueckstand_holen(relay: HandyRelay, max_runden: int = 20) -> list[Nachricht]:
    """Holt alle liegengebliebenen Nachrichten (ohne zu warten). Der letzte, leere Abruf bestaetigt sie
    bei Telegram - sie kommen also nicht noch einmal. Ohne festgelegte Chat-ID: nichts (sonst kaemen
    auch Fremde durch)."""
    if relay.chat_id is None or getattr(relay, "kein_rueckstand", False):
        return []
    alle: list[Nachricht] = []
    for _ in range(max_runden):
        neu = relay.hole(timeout=0)
        if not neu:
            break
        alle.extend(neu)
    return alle


def _offen_pfad(root) -> Path:
    return Path(root) / "data" / "handy_offen.json"


def offen_laden(root) -> list[dict]:
    try:
        roh = json.loads(_offen_pfad(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for e in roh if isinstance(roh, list) else []:
        if isinstance(e, dict) and str(e.get("text", "")).strip():
            try:
                zeit = int(e.get("zeit") or 0)
            except (TypeError, ValueError):
                zeit = 0
            out.append({"text": str(e["text"])[:MAX_OFFEN_TEXT], "zeit": zeit})
    return out[-MAX_OFFEN:]


def offen_hinzufuegen(root, nachrichten: list[Nachricht]) -> int:
    """Haengt neue Nachrichten an die gespeicherte Liste (Stopwoerter nicht). Gibt die Anzahl neuer zurueck."""
    neu = [{"text": n.text.strip()[:MAX_OFFEN_TEXT], "zeit": int(n.zeit or 0)}
           for n in nachrichten if n.text and n.text.strip() and not ist_stopp(n.text)]
    if not neu:
        return 0
    liste = (offen_laden(root) + neu)[-MAX_OFFEN:]
    pfad = _offen_pfad(root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(liste, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(neu)


def offen_leeren(root) -> None:
    try:
        _offen_pfad(root).unlink()
    except OSError:
        pass


def offen_entfernen(root, erledigt: list[dict]) -> None:
    """Entfernt genau diese Eintraege (was waehrend der Nachfrage neu dazukam, bleibt)."""
    rest = offen_laden(root)
    for e in erledigt:
        for i, r in enumerate(rest):
            if r["text"] == e.get("text") and r["zeit"] == e.get("zeit", 0):
                del rest[i]
                break
    if not rest:
        offen_leeren(root)
        return
    _offen_pfad(root).write_text(json.dumps(rest, ensure_ascii=False, indent=2), encoding="utf-8")


def _wann(zeit: int) -> str:
    if not zeit:
        return ""
    try:
        return time.strftime("%d.%m. %H:%M", time.localtime(zeit))
    except (OverflowError, OSError, ValueError):
        return ""


def offen_frage(liste: list[dict]) -> str:
    """Text fuer die Nachfrage beim Start (kurz gefasst)."""
    zeilen = []
    for e in liste[:10]:
        wann = _wann(e.get("zeit", 0))
        text = e["text"] if len(e["text"]) <= 300 else e["text"][:300] + " ..."
        zeilen.append(f"- {wann + ': ' if wann else ''}{text}")
    if len(liste) > 10:
        zeilen.append(f"- ... und {len(liste) - 10} weitere")
    eins = len(liste) == 1
    return ("Waehrend ich aus war, hast du mir vom Handy " + ("eine Nachricht" if eins else f"{len(liste)} Nachrichten")
            + " geschickt:\n\n" + "\n".join(zeilen) + "\n\nSoll ich " + ("das" if eins else "das alles")
            + " jetzt umsetzen?")


def offen_auftrag(liste: list[dict]) -> str:
    """Der Auftrag an die KI, wenn du "ja" sagst (alle Nachrichten in einer Runde, in Reihenfolge)."""
    zeilen = []
    for i, e in enumerate(liste, 1):
        wann = _wann(e.get("zeit", 0))
        zeilen.append(f"{i}) {'[' + wann + '] ' if wann else ''}{e['text']}")
    return ("\U0001F4F1 Vom Handy, waehrend du (der PC) aus warst:\n" + "\n".join(zeilen)
            + "\n\nSetz das jetzt bitte um. Ist etwas unklar oder inzwischen ueberholt, frag kurz nach.")


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
                # "Conflict": ein zweiter Nova (z.B. in der Cloud) liest denselben Bot - laenger warten.
                time.sleep(30.0 if "conflict" in str(exc).lower() else 5.0)
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
