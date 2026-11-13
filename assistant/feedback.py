"""Feedback & Bewertung: Rueckmeldungen der Nutzer an den Entwickler schicken.

Ablauf:
  1. baue_payload(): Sterne, Text, Art, Kontakt (optional) und bis zu 5 Bilder in eine kleine
     JSON-Nachricht packen (Bilder einmal ueber bilder.vorbereiten verkleinert).
  2. senden(): per HTTPS an ein Google-Apps-Skript (packaging/nova-feedback.gs) schicken. Das
     Skript mailt an das Konto, dem es gehoert - die App kennt KEINE E-Mail-Adresse, nur die
     Web-App-URL. Erfolg nur bei HTTP 200 + JSON + ok == true.
  3. Klappt es nicht (offline, Google gerade ueberlastet, Postfach noch nicht eingerichtet), landet
     die Nachricht im Ausgang (data/feedback_ausgang/) und ausgang_senden() schickt sie spaeter
     nach (beim Start und alle 30 Minuten). Hoechstens 3 Sendungen pro Stunde und 10 pro Tag.
  4. Nachfrage-Plan (Pop-up "Wie gefaellt dir Nova?"): nach etwa einer Stunde Nutzung, danach
     alle paar Tage - Zustand in data/feedback_state.json.
  5. Bewertungen: Sterne zaehlen (anonym, pro Installation nur die letzte) zum Durchschnitt; Text
     und Name werden nur oeffentlich, wenn die Person es ankreuzt. bewertungen() holt Durchschnitt
     und oeffentliche Rezensionen vom Apps-Skript (?aktion=bewertungen, 1 Stunde zwischengespeichert).

Ziel-URL (erste gueltige gewinnt): [feedback] adresse > FEEDBACK_URL > Datei
feedback-endpoint.txt auf dem Standard-Branch des Repos (24 h zwischengespeichert).

Datenschutz: Die URL, Texte und Bilder werden nie geloggt - nur "Feedback gesendet/gespeichert/
abgelehnt". Fehlermeldungen von requests enthalten die URL, deshalb werden sie verschluckt.
Alles unter data/ fasst der Updater nie an.
"""
from __future__ import annotations

import base64
import binascii
import json
import math
import os
import platform
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from . import __version__
from . import bilder as _bilder
from .bilder import Bild, BildFehler
from .config import PROJECT_ROOT
from .logging_setup import get_logger

logger = get_logger()

# Web-App-URL des Apps-Skripts (kommt spaeter; leer = Fern-Datei bzw. Ausgang).
FEEDBACK_URL = ""
FERN_DATEI = "feedback-endpoint.txt"

APP_NAME = "Nova"          # das Apps-Skript nimmt nur app == "Nova" an (nicht der KI-Name!)
PAYLOAD_VERSION = 2
ARTEN = ("bewertung", "feedback", "bug", "idee")
AUSLOESER = ("popup", "menue")
MAX_BILDER = 5
MAX_KANTE = 1920
MAX_BILDER_BYTES = 10 * 1024 * 1024
MAX_TEXT = 20000
MAX_KONTAKT = 200
MAX_NAME = 40
MAX_REZENSION = 600
MAX_REZENSIONEN = 30
BEWERTUNGEN_GUELTIG = timedelta(hours=1)
BEWERTUNGEN_FEHLER_WARTEN = timedelta(minutes=15)
MAX_PRO_STUNDE = 3
MAX_PRO_TAG = 10
AUSGANG_MAX_TAGE = 30
AUSGANG_MAX_DATEIEN = 50   # Schutz vor vollgelaufener Platte (aelteste zuerst weg)
TIMEOUT = (10, 90)         # (Verbinden, Antwort) in Sekunden
FERN_TIMEOUT = 8
FERN_GUELTIG = timedelta(hours=24)
FERN_FEHLER_WARTEN = timedelta(hours=1)   # offline: nicht bei jedem Aufruf neu nachschauen
_MAX_NUTZUNG_PRO_AUFRUF = 6 * 3600        # Schutz gegen Zeitspruenge (Standby, Uhr verstellt)

_URL_RE = re.compile(r"https://script\.google\.com/macros/s/[A-Za-z0-9_-]{10,}/exec")
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_STEUERZEICHEN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ZEIT_FORMAT = "%Y%m%d-%H%M%S"

_ART_ALIAS = {
    "bewertung": "bewertung", "lob": "bewertung", "sterne": "bewertung",
    "feedback": "feedback", "sonstiges": "feedback", "anderes": "feedback",
    "bug": "bug", "fehler": "bug", "problem": "bug",
    "idee": "idee", "wunsch": "idee", "vorschlag": "idee",
}
_AUSLOESER_ALIAS = {"popup": "popup", "pop-up": "popup", "nachfrage": "popup",
                    "menue": "menue", "menu": "menue", "men\u00fc": "menue", "befehl": "menue"}

# Meldungen fuer den Nutzer (Umlaute als \u-Escapes, siehe CLAUDE.md).
MELDUNGEN = {
    "ok": "Danke! Dein Feedback wurde gesendet.",
    "offline": "Keine Verbindung. Dein Feedback ist gespeichert und wird automatisch gesendet, "
               "sobald du wieder online bist.",
    "zu_gross": "Die Bilder sind zusammen zu gro\u00df (max. 10 MB). Bitte entferne ein Bild.",
    "limit": "Gerade kommen sehr viele R\u00fcckmeldungen an. Dein Feedback wird sp\u00e4ter "
             "automatisch gesendet.",
    "keine_url": "Dein Feedback ist gespeichert und wird gesendet, sobald das Feedback-Postfach "
                 "eingerichtet ist.",
    "grenze": "Danke! Du hast gerade schon einige R\u00fcckmeldungen geschickt. Diese ist "
              "gespeichert und wird sp\u00e4ter automatisch gesendet.",
    "fehler": "Senden hat gerade nicht geklappt. Dein Feedback ist gespeichert und wird "
              "sp\u00e4ter automatisch erneut gesendet.",
    "speicher": "Dein Feedback konnte gerade weder gesendet noch gespeichert werden. Bitte "
                "versuche es sp\u00e4ter noch einmal.",
}
_LOG_GRUND = {"offline": "keine Verbindung", "limit": "Postfach ausgelastet",
              "keine_url": "kein Postfach eingerichtet", "grenze": "Grenze pro Stunde/Tag",
              "fehler": "Postfach-Fehler", "zu_gross": "zu gross", "speicher": "Speichern ging nicht",
              "ungueltig": "Eingabe", "zu_alt": "aelter als 30 Tage", "kaputt": "Datei kaputt"}

_STAND_LOCK = threading.RLock()     # Lesen-Aendern-Schreiben von feedback_state.json
_AUSGANG_LOCK = threading.Lock()    # ausgang_senden laeuft nie doppelt


class FeedbackFehler(ValueError):
    """Eingabe passt nicht (Text fuer den Nutzer), z.B. leeres Feedback."""


@dataclass
class Ergebnis:
    """Ausgang eines Sendeversuchs.

    status: "gesendet" | "gespeichert" (im Ausgang, wird nachgesendet) | "abgelehnt"
    meldung: deutscher Text fuer den Nutzer
    grund: ok | offline | limit | keine_url | grenze | fehler | zu_gross | speicher | ungueltig
    """
    status: str
    meldung: str
    grund: str = ""
    datei: Path | None = field(default=None, repr=False)  # Ausgangsdatei bei "gespeichert"

    @property
    def ok(self) -> bool:
        return self.status in ("gesendet", "gespeichert")

    def als_antwort(self) -> dict:
        """Antwort fuer POST /api/feedback."""
        if self.ok:
            return {"ok": True, "status": self.status, "message": self.meldung}
        return {"ok": False, "status": self.status, "error": self.meldung}


# -- kleine Helfer ---------------------------------------------------------------
def _wurzel(quelle: Any = None) -> Path:
    """Projektordner aus Path/str, einer Config (project_root) oder dem Standard."""
    if quelle is None:
        return Path(PROJECT_ROOT)
    root = getattr(quelle, "project_root", None)
    return Path(root if root is not None else quelle)


def _stand_pfad(root: Path) -> Path:
    return root / "data" / "feedback_state.json"


def ausgang_ordner(root: Any = None) -> Path:
    return _wurzel(root) / "data" / "feedback_ausgang"


def _jetzt(jetzt: datetime | None) -> datetime:
    if jetzt is None:
        return datetime.now()
    if jetzt.tzinfo is not None:
        return jetzt.astimezone().replace(tzinfo=None)
    return jetzt


def _iso(zeit: datetime) -> str:
    return zeit.isoformat(timespec="seconds")


def _zeit(text: Any) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        zeit = datetime.fromisoformat(text)
    except ValueError:
        return None
    return zeit.astimezone().replace(tzinfo=None) if zeit.tzinfo is not None else zeit


def _zahl(wert: Any, standard: float = 0.0) -> float:
    if isinstance(wert, bool):
        return standard
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return standard
    return zahl if math.isfinite(zahl) else standard


def _ganzzahl(wert: Any, standard: int, minimum: int) -> int:
    if isinstance(wert, bool):
        return standard
    try:
        return max(minimum, int(wert))
    except (TypeError, ValueError):
        return standard


def _atomar_schreiben(pfad: Path, text: str) -> None:
    """tmp-Datei im selben Ordner schreiben und dann ersetzen (nie halbe Dateien)."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_name(f".{pfad.name}.{os.getpid()}.{secrets.token_hex(3)}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        for versuch in range(5):
            try:
                os.replace(tmp, pfad)
                return
            except PermissionError:  # Windows: Virenscanner/Indexer haelt die Datei kurz fest
                if versuch == 4:
                    raise
                time.sleep(0.05 * (versuch + 1))
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _lade_stand(root: Path) -> dict:
    with _STAND_LOCK:
        try:
            daten = json.loads(_stand_pfad(root).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return daten if isinstance(daten, dict) else {}


def _stand_aendern(root: Path, aendern: Callable[[dict], Any]) -> Any:
    """Zustand lesen, aendern, atomar speichern. Speicherfehler werden verschluckt."""
    with _STAND_LOCK:
        stand = _lade_stand(root)
        ergebnis = aendern(stand)
        try:
            _atomar_schreiben(_stand_pfad(root), json.dumps(stand, indent=2, ensure_ascii=True))
        except OSError:
            pass  # z.B. Datentraeger voll - dann eben ohne Gedaechtnis weiter
        return ergebnis


def _log(status: str, grund: str = "", wo: str = "") -> None:
    """Nur Status und Grund loggen - nie URL, Text oder Bilder."""
    zusatz = ", ".join(t for t in (wo, _LOG_GRUND.get(grund, "")) if t)
    logger.info("Feedback %s%s", status, f" ({zusatz})" if zusatz else "")


# -- Ziel-URL ----------------------------------------------------------------------
def gueltige_url(url: Any) -> bool:
    """Nur echte Apps-Skript-Web-App-URLs (https://script.google.com/macros/s/<ID>/exec)."""
    return isinstance(url, str) and len(url) <= 300 and _URL_RE.fullmatch(url) is not None


def fern_quelle(config) -> str | None:
    """URL der Datei feedback-endpoint.txt - Repo und Branch wie beim Updater ([update])."""
    update = getattr(config, "update", None)
    repo = str(getattr(update, "repo", "") or "").strip()
    if not _REPO_RE.fullmatch(repo) or ".." in repo:
        return None
    ref = str(getattr(update, "branch", "") or "").strip() or "HEAD"  # HEAD = Standard-Branch
    return f"https://raw.githubusercontent.com/{repo}/{quote(ref, safe='/')}/{FERN_DATEI}"


def _standard_fetch(url: str, timeout: float = FERN_TIMEOUT) -> bytes:
    from .updater import _http_get  # gleicher Abruf wie beim Updater (inkl. optionalem Token)

    return _http_get(url, timeout=timeout)


def _ist_404(exc: Exception) -> bool:
    antwort = getattr(exc, "response", None)
    status = getattr(antwort, "status_code", None)
    if status is None:
        status = getattr(exc, "code", None) or getattr(exc, "status", None)
    return status == 404


def _url_aus_fern_text(roh: Any) -> str | None:
    if isinstance(roh, bytes):
        roh = roh[:4096].decode("utf-8", "replace")
    for zeile in str(roh or "")[:4096].lstrip("\ufeff").splitlines()[:50]:
        zeile = zeile.strip()
        if zeile and not zeile.startswith("#"):
            return zeile if gueltige_url(zeile) else None
    return None


def _fern_url(config, fetch, jetzt: datetime, netz: bool) -> str | None:
    quelle = fern_quelle(config)
    if not quelle:
        return None
    root = _wurzel(config)
    alt = None
    cache = _lade_stand(root).get("fern")
    if isinstance(cache, dict) and cache.get("quelle") == quelle:
        alt = cache.get("url") if gueltige_url(cache.get("url")) else None
        geprueft = _zeit(cache.get("geprueft"))
        frist = FERN_GUELTIG if cache.get("ok") is True else FERN_FEHLER_WARTEN
        if geprueft is not None and geprueft <= jetzt < geprueft + frist:
            return alt
    if not netz:
        return alt  # veraltet ist besser als nichts
    try:
        url, ok = _url_aus_fern_text((fetch or _standard_fetch)(quelle, timeout=FERN_TIMEOUT)), True
    except Exception as exc:  # noqa: BLE001 - offline, GitHub weg ... (Text enthaelt die URL)
        if _ist_404(exc):
            url, ok = None, True       # Datei gibt es (noch) nicht
        else:
            url, ok = alt, False       # spaeter nochmal; bis dahin den alten Stand nehmen

    def merken(stand: dict) -> None:
        stand["fern"] = {"quelle": quelle, "url": url or "", "geprueft": _iso(jetzt), "ok": ok}

    _stand_aendern(root, merken)
    return url


def ziel_url(config, *, fetch: Callable[..., bytes] | None = None, jetzt: datetime | None = None,
             netz: bool = True) -> str | None:
    """Wohin das Feedback geht - oder None, wenn (noch) kein Postfach eingerichtet ist.

    Reihenfolge: [feedback] adresse (nur gueltig) > FEEDBACK_URL > feedback-endpoint.txt im Repo
    (24 h in data/feedback_state.json gemerkt; offline erst nach 1 h wieder versucht).
    netz=False: nur Zwischenspeicher, kein Abruf."""
    eigene = str(getattr(getattr(config, "feedback", None), "adresse", "") or "").strip()
    if gueltige_url(eigene):
        return eigene
    if gueltige_url(FEEDBACK_URL):
        return FEEDBACK_URL
    return _fern_url(config, fetch, _jetzt(jetzt), netz)


def ist_eingerichtet(config, **kwargs) -> bool:
    """Gibt es ein Feedback-Postfach? (kwargs wie bei ziel_url)"""
    return ziel_url(config, **kwargs) is not None


# -- Nachricht bauen -----------------------------------------------------------------
def _art(kind: Any) -> str:
    return _ART_ALIAS.get(str(kind or "").strip().lower(), "feedback")


def _sterne(stars: Any) -> int | None:
    if stars is None or isinstance(stars, bool):
        return None
    try:
        wert = float(str(stars).strip()) if isinstance(stars, str) else float(stars)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(wert):
        return None
    wert = int(round(wert))
    return wert if 1 <= wert <= 5 else None


def _ausloeser(trigger: Any) -> str:
    return _AUSLOESER_ALIAS.get(str(trigger or "").strip().lower(), "menue")


def _ein_bild(eintrag: Any, nummer: int) -> Bild:
    name = f"bild{nummer}"
    if isinstance(eintrag, Bild):
        return _bilder.vorbereiten(eintrag.data, eintrag.name or name, max_kante=MAX_KANTE)
    if isinstance(eintrag, (bytes, bytearray)):
        return _bilder.vorbereiten(bytes(eintrag), name, max_kante=MAX_KANTE)
    if isinstance(eintrag, Path):
        return _aus_datei(eintrag)
    if isinstance(eintrag, dict):
        name = str(eintrag.get("name") or name)
        daten = eintrag.get("data")
        if isinstance(daten, (bytes, bytearray)):
            return _bilder.vorbereiten(bytes(daten), name, max_kante=MAX_KANTE)
        text = str(daten or "").strip()
        if text.lower().startswith("data:"):
            return _bilder.aus_data_url(text, name, max_kante=MAX_KANTE)
        if not text or len(text) > _bilder.MAX_EINGANG * 4 // 3 + 200:
            raise BildFehler("Ein Bild kam nicht richtig an.")
        try:
            roh = base64.b64decode(text, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise BildFehler("Ein Bild kam nicht richtig an (fehlerhafte Daten).") from exc
        return _bilder.vorbereiten(roh, name, max_kante=MAX_KANTE)
    if isinstance(eintrag, str):
        if eintrag.strip().lower().startswith("data:"):
            return _bilder.aus_data_url(eintrag, name, max_kante=MAX_KANTE)
        return _aus_datei(eintrag)  # Pfad (Terminal)
    raise BildFehler("Ein Bild kam nicht richtig an.")


def _aus_datei(pfad: Any) -> Bild:
    try:
        return _bilder.aus_datei(pfad, max_kante=MAX_KANTE)
    except OSError as exc:  # z.B. Name zu lang, keine Leserechte
        raise BildFehler("Die Bilddatei l\u00e4sst sich nicht lesen.") from exc


def bilder_vorbereiten(eintraege: Any) -> list[Bild]:
    """Bis zu 5 Bilder (Bild, Bytes, Pfad, data:-URL oder {"name", "data"}) einmal auf
    hoechstens 1920 px verkleinern; zusammen <= 10 MB. Wirft BildFehler."""
    if eintraege is None:
        return []
    if isinstance(eintraege, (str, bytes, Path, dict, Bild)):
        eintraege = [eintraege]
    if not isinstance(eintraege, (list, tuple)):
        raise BildFehler("Die Bilder kamen nicht richtig an.")
    if len(eintraege) > MAX_BILDER:
        raise BildFehler(f"H\u00f6chstens {MAX_BILDER} Bilder pro Feedback. Bitte entferne "
                         f"{len(eintraege) - MAX_BILDER}.")
    fertig = [_ein_bild(eintrag, i) for i, eintrag in enumerate(eintraege, 1)]
    if sum(len(b.data) for b in fertig) > MAX_BILDER_BYTES:
        raise BildFehler(MELDUNGEN["zu_gross"])
    return fertig


def _gehirn(config) -> str:
    try:
        return f"{config.active_provider}/{config.active_model}"[:80]
    except Exception:  # noqa: BLE001 - ohne Config (Tests) oder unvollstaendig
        return "?"


def _system() -> str:
    try:
        return platform.platform()[:120]  # ohne Rechner- und Benutzernamen
    except Exception:  # noqa: BLE001
        return "?"


def kennung(root: Any = None) -> str:
    """Zufaellige, anonyme Kennung dieser Installation (damit pro Installation nur die letzte
    Bewertung zaehlt). Enthaelt nichts ueber den PC oder die Person."""
    def holen(stand: dict) -> str:
        wert = stand.get("kennung")
        if not (isinstance(wert, str) and re.fullmatch(r"[0-9a-f]{16,40}", wert)):
            wert = secrets.token_hex(12)
            stand["kennung"] = wert
        return wert

    return _stand_aendern(_wurzel(root), holen)


def baue_payload(kind: Any, stars: Any, text: Any, contact: Any, bilder: Any, trigger: Any,
                 config, oeffentlich: Any = False, name: Any = None) -> dict:
    """Die Nachricht an das Apps-Skript. Wirft BildFehler (Bilder) oder FeedbackFehler (leer).

    kind: bewertung | feedback | bug | idee (auch lob/fehler/sonstiges/...; sonst feedback)
    stars: 1-5 oder None; text: bis 20000 Zeichen; contact: optional, bis 200 Zeichen
    bilder: Liste aus Bild, Bytes, Pfaden, data:-URLs oder {"name", "data"} (hoechstens 5)
    trigger: popup | menue
    oeffentlich: Text (+ Name) als Rezension zeigen - nur mit Sternen; name: optional, bis 40 Zeichen"""
    sterne = _sterne(stars)
    inhalt = _STEUERZEICHEN.sub("", str(text if text is not None else "")).strip()[:MAX_TEXT]
    kontakt = " ".join(_STEUERZEICHEN.sub(" ", str(contact or "")).split())[:MAX_KONTAKT]
    fertig = bilder_vorbereiten(bilder)
    if sterne is None and not inhalt and not fertig:
        raise FeedbackFehler("Bitte gib Sterne oder einen kurzen Text ein.")
    oeffentlich = oeffentlich is True and sterne is not None
    anzeigename = " ".join(_STEUERZEICHEN.sub(" ", str(name or "")).split())[:MAX_NAME] if oeffentlich else ""
    return {
        "app": APP_NAME,
        "v": PAYLOAD_VERSION,
        "version": __version__,
        "kind": _art(kind),
        "stars": sterne,
        "text": inhalt,
        "contact": kontakt,
        "os": _system(),
        "brain": _gehirn(config),
        "trigger": _ausloeser(trigger),
        "public": oeffentlich,
        "name": anzeigename,
        "install": kennung(config) if getattr(config, "project_root", None) else "",
        "website": "",  # Honigtopf: Bots fuellen ihn, das Skript verwirft dann
        "images": [{"name": b.name, "mime": b.mime, "data": b.b64()} for b in fertig],
    }


# -- Senden --------------------------------------------------------------------------
def _requests_post(*args, **kwargs):
    import requests

    return requests.post(*args, **kwargs)


def _antwort_text(resp: Any) -> str:
    text = getattr(resp, "text", None)
    if isinstance(text, str):
        return text
    roh = getattr(resp, "content", b"")
    return roh.decode("utf-8", "replace") if isinstance(roh, (bytes, bytearray)) else ""


def _auswerten(resp: Any) -> str:
    """HTTP-Antwort -> Grund. Erfolg NUR bei 200 + JSON-Objekt + ok is True."""
    status = getattr(resp, "status_code", None)
    if status == 200:
        try:
            daten = json.loads(_antwort_text(resp))
        except ValueError:
            return "offline"  # HTML (Anmeldeseite, WLAN-Portal ...) statt JSON
        if not isinstance(daten, dict):
            return "offline"
        if daten.get("ok") is True:
            return "ok"
        fehler = daten.get("fehler")
        if fehler in ("zu_gross", "limit"):
            return fehler
        return "fehler"
    if status == 413:
        return "zu_gross"
    if status == 429:
        return "limit"
    if isinstance(status, int) and status >= 500:
        return "offline"
    return "fehler"  # 405 (Weiterleitung falsch befolgt), 403/404 (Bereitstellung falsch) ...


def _grenze_erreicht(stand: dict, jetzt: datetime) -> bool:
    zeiten = _sendungen(stand, jetzt)
    in_der_stunde = sum(1 for z in zeiten if z > jetzt - timedelta(hours=1))
    return in_der_stunde >= MAX_PRO_STUNDE or len(zeiten) >= MAX_PRO_TAG


def _sendungen(stand: dict, jetzt: datetime) -> list[datetime]:
    roh = stand.get("sendungen")
    if not isinstance(roh, list):
        return []
    zeiten = (_zeit(x) for x in roh)
    # Zeiten in der Zukunft (Uhr zurueckgestellt) zaehlen nicht - sonst ewig gesperrt.
    return [z for z in zeiten if z is not None and jetzt - timedelta(days=1) < z <= jetzt + timedelta(minutes=1)]


def _sendung_merken(root: Path, jetzt: datetime) -> None:
    def merken(stand: dict) -> None:
        stand["sendungen"] = [_iso(z) for z in _sendungen(stand, jetzt)] + [_iso(jetzt)]

    _stand_aendern(root, merken)


def grenze_erreicht(root: Any = None, jetzt: datetime | None = None) -> bool:
    """Schon 3 Sendungen in der letzten Stunde oder 10 in den letzten 24 Stunden?"""
    return _grenze_erreicht(_lade_stand(_wurzel(root)), _jetzt(jetzt))


def _versuchen(payload: dict, url: str, post, root: Path, jetzt: datetime) -> str:
    """Ein Sendeversuch -> Grund (ok | offline | limit | zu_gross | fehler)."""
    koerper = json.dumps(payload, ensure_ascii=True).encode("ascii")
    kopf = {"Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": f"Nova/{__version__} (Feedback)"}
    try:
        resp = (post or _requests_post)(url, data=koerper, headers=kopf, timeout=TIMEOUT)
    except Exception:  # noqa: BLE001 - offline/Timeout; Text enthaelt die URL -> nicht loggen
        return "offline"
    # Jede beantwortete Sendung zaehlt fuer die Grenze (schont Postfach und Datenvolumen).
    _sendung_merken(root, jetzt)
    try:
        return _auswerten(resp)
    finally:
        schliessen = getattr(resp, "close", None)
        if callable(schliessen):
            try:
                schliessen()
            except Exception:  # noqa: BLE001
                pass


def _in_ausgang_legen(root: Path, payload: dict, jetzt: datetime) -> Path:
    ordner = ausgang_ordner(root)
    ziel = ordner / f"{jetzt.strftime(_ZEIT_FORMAT)}_{secrets.token_hex(4)}.json"
    eintrag = {"art": "nova-feedback", "v": 1, "erstellt": _iso(jetzt), "payload": payload}
    _atomar_schreiben(ziel, json.dumps(eintrag, ensure_ascii=True))
    return ziel


def senden(payload: dict, url: str | None, post: Callable | None = None, *, root: Any = None,
           jetzt: datetime | None = None) -> Ergebnis:
    """Schickt das Feedback ab (post = requests.post). Klappt es nicht, landet es im Ausgang.

    Keine/ungueltige URL oder Grenze (3/Stunde, 10/Tag) erreicht -> gar nicht senden, Ausgang.
    root: Projektordner (oder Config) fuer data/; Standard: der Programmordner."""
    root, jetzt = _wurzel(root), _jetzt(jetzt)
    if not gueltige_url(url):
        grund = "keine_url"
    elif _grenze_erreicht(_lade_stand(root), jetzt):
        grund = "grenze"
    else:
        grund = _versuchen(payload, url, post, root, jetzt)
    if grund == "ok":
        _log("gesendet")
        return Ergebnis("gesendet", MELDUNGEN["ok"], grund)
    if grund == "zu_gross":
        _log("abgelehnt", grund)
        return Ergebnis("abgelehnt", MELDUNGEN["zu_gross"], grund)
    try:
        datei = _in_ausgang_legen(root, payload, jetzt)
    except (OSError, TypeError, ValueError):
        _log("abgelehnt", "speicher")
        return Ergebnis("abgelehnt", MELDUNGEN["speicher"], "speicher")
    _ausgang_begrenzen(root)
    _log("gespeichert", grund)
    return Ergebnis("gespeichert", MELDUNGEN.get(grund, MELDUNGEN["fehler"]), grund, datei)


def abschicken(config, kind: Any = "feedback", stars: Any = None, text: Any = "",
               contact: Any = None, bilder: Any = None, trigger: Any = "menue", *,
               oeffentlich: Any = False, name: Any = None,
               post: Callable | None = None, fetch: Callable | None = None,
               jetzt: datetime | None = None) -> Ergebnis:
    """Alles in einem (fuer Server und Terminal): bauen, Ziel finden, senden, Plan merken.

    Ungueltige Eingaben/Bilder -> Ergebnis "abgelehnt" mit der Meldung (nichts gespeichert).
    Gesendet oder gespeichert zaehlt als "Feedback gegeben" (keine Nachfrage in naechster Zeit)."""
    root, jetzt = _wurzel(config), _jetzt(jetzt)
    try:
        payload = baue_payload(kind, stars, text, contact, bilder, trigger, config,
                               oeffentlich=oeffentlich, name=name)
    except (BildFehler, FeedbackFehler) as exc:
        _log("abgelehnt", "ungueltig")
        return Ergebnis("abgelehnt", str(exc), "ungueltig")
    ergebnis = senden(payload, ziel_url(config, fetch=fetch, jetzt=jetzt), post, root=root, jetzt=jetzt)
    if ergebnis.ok:
        gesendet(jetzt, root=root)
        if ergebnis.status == "gesendet" and payload.get("stars"):
            # Neue Bewertung -> Durchschnitt beim naechsten Anzeigen frisch holen
            _stand_aendern(root, lambda stand: stand.pop("bewertungen", None))
    return ergebnis


# -- Bewertungen (Durchschnitt + oeffentliche Rezensionen) ----------------------------
def _google_get(url: str, timeout: float = FERN_TIMEOUT) -> bytes:
    """Abruf beim Apps-Skript - bewusst OHNE GitHub-Token (der darf nie zu Google)."""
    import requests

    resp = requests.get(url, headers={"User-Agent": f"Nova/{__version__} (Bewertungen)",
                                      "Accept": "application/json"}, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _kurz(wert: Any, laenge: int) -> str:
    return " ".join(_STEUERZEICHEN.sub(" ", str(wert if wert is not None else "")).split())[:laenge]


def sterne_text(schnitt: float) -> str:
    """4.6 -> 5 volle Sterne (gerundet auf ganze Sterne, mit leeren Sternen aufgefuellt)."""
    voll = int(min(5, max(0, round(float(schnitt or 0)))))
    return "\u2605" * voll + "\u2606" * (5 - voll)


def bewertungen_saeubern(roh: Any) -> dict | None:
    """Antwort des Apps-Skripts pruefen und auf sichere, kurze Werte bringen (oder None)."""
    if not isinstance(roh, dict) or roh.get("ok") is not True:
        return None
    anzahl = _ganzzahl(roh.get("anzahl"), 0, 0)
    schnitt = round(min(5.0, max(0.0, _zahl(roh.get("schnitt")))), 1) if anzahl else 0.0
    verteilung_roh = roh.get("verteilung") if isinstance(roh.get("verteilung"), dict) else {}
    verteilung = {str(i): _ganzzahl(verteilung_roh.get(str(i)), 0, 0) for i in range(1, 6)}
    rezensionen = []
    for r in (roh.get("oeffentlich") if isinstance(roh.get("oeffentlich"), list) else [])[:MAX_REZENSIONEN]:
        if not isinstance(r, dict):
            continue
        sterne = _sterne(r.get("sterne"))
        text = _kurz(r.get("text"), MAX_REZENSION)
        if sterne is None or not text:
            continue
        datum = _kurz(r.get("datum"), 10)
        rezensionen.append({"sterne": sterne, "text": text, "name": _kurz(r.get("name"), MAX_NAME) or "Anonym",
                            "datum": datum if re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum) else "",
                            "version": _kurz(r.get("version"), 30)})
    return {"anzahl": anzahl, "schnitt": schnitt, "verteilung": verteilung, "oeffentlich": rezensionen}


def bewertungen(config, *, fetch: Callable | None = None, holen: Callable | None = None,
                jetzt: datetime | None = None, netz: bool = True) -> dict | None:
    """Durchschnitt und oeffentliche Rezensionen - 1 Stunde zwischengespeichert. Ohne Postfach
    oder Netz: der letzte bekannte Stand (oder None).
    fetch: wie bei ziel_url (feedback-endpoint.txt); holen: Abruf beim Apps-Skript (Tests)."""
    root, jetzt = _wurzel(config), _jetzt(jetzt)
    stand = _lade_stand(root).get("bewertungen")
    alt = stand.get("daten") if isinstance(stand, dict) else None
    zeit = _zeit(stand.get("zeit")) if isinstance(stand, dict) else None
    warten = BEWERTUNGEN_GUELTIG if isinstance(stand, dict) and stand.get("ok", True) else BEWERTUNGEN_FEHLER_WARTEN
    if zeit is not None and jetzt - warten < zeit <= jetzt + timedelta(minutes=1):
        return bewertungen_saeubern({"ok": True, **alt}) if isinstance(alt, dict) else None
    if not netz:
        return bewertungen_saeubern({"ok": True, **alt}) if isinstance(alt, dict) else None
    url = ziel_url(config, fetch=fetch, jetzt=jetzt)
    if not url:
        return None
    try:
        daten = bewertungen_saeubern(json.loads((holen or _google_get)(url + "?aktion=bewertungen")))
    except Exception:  # noqa: BLE001 - offline usw.; Text enthaelt die URL -> nicht loggen
        daten = None
    neu = {"zeit": _iso(jetzt), "ok": daten is not None, "daten": daten if daten is not None else alt}
    _stand_aendern(root, lambda s: s.__setitem__("bewertungen", neu))
    if daten is None:
        return bewertungen_saeubern({"ok": True, **alt}) if isinstance(alt, dict) else None
    return daten


# -- Ausgang -------------------------------------------------------------------------
def _ausgang_dateien(root: Path) -> list[Path]:
    try:
        return sorted(p for p in ausgang_ordner(root).glob("*.json") if p.is_file())
    except OSError:
        return []


def ausgang_anzahl(root: Any = None) -> int:
    """Wie viele Rueckmeldungen warten noch auf das Nachsenden?"""
    return len(_ausgang_dateien(_wurzel(root)))


def _datei_zeit(pfad: Path) -> datetime | None:
    try:
        return datetime.strptime(pfad.name[:15], _ZEIT_FORMAT)
    except ValueError:
        pass
    try:
        return datetime.fromtimestamp(pfad.stat().st_mtime)
    except (OSError, ValueError, OverflowError):
        return None


def _loeschen(pfad: Path) -> bool:
    try:
        pfad.unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def _ausgang_begrenzen(root: Path) -> int:
    dateien = _ausgang_dateien(root)
    weg = dateien[:max(0, len(dateien) - AUSGANG_MAX_DATEIEN)]
    return sum(1 for pfad in weg if _loeschen(pfad))


def _lade_eintrag(pfad: Path) -> dict | None:
    """Payload aus einer Ausgangsdatei (None = kaputt)."""
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(daten, dict) and isinstance(daten.get("payload"), dict):
        daten = daten["payload"]
    if not isinstance(daten, dict) or daten.get("app") != APP_NAME:
        return None
    return daten


def _bilder_bytes(payload: dict) -> int:
    gesamt = 0
    for bild in payload.get("images") or []:
        if isinstance(bild, dict):
            gesamt += len(str(bild.get("data") or "")) * 3 // 4
    return gesamt


def _ausgang_aufraeumen(root: Path, jetzt: datetime) -> int:
    """Alte (> 30 Tage) Eintraege und liegengebliebene tmp-Dateien loeschen."""
    geloescht = _ausgang_begrenzen(root)
    grenze = jetzt - timedelta(days=AUSGANG_MAX_TAGE)
    for pfad in _ausgang_dateien(root):
        zeit = _datei_zeit(pfad)
        if zeit is not None and zeit < grenze and _loeschen(pfad):
            geloescht += 1
            _log("abgelehnt", "zu_alt", wo="Ausgang")
    try:
        for tmp in ausgang_ordner(root).glob(".*.tmp"):
            if time.time() - tmp.stat().st_mtime > 86400:
                _loeschen(tmp)
    except OSError:
        pass
    return geloescht


def ausgang_senden(config, post: Callable | None = None, *, fetch: Callable | None = None,
                   jetzt: datetime | None = None) -> dict:
    """Ausgang nachsenden (beim Start und alle 30 Minuten aufrufen, eigener Thread).

    Aelter als 30 Tage / kaputt / zu gross -> loeschen; sonst nachsenden (aelteste zuerst),
    bis die Grenze erreicht ist oder keine Verbindung besteht.
    Rueckgabe: {"gesendet": n, "geloescht": n, "offen": n, "uebersprungen": bool}"""
    root, jetzt = _wurzel(config), _jetzt(jetzt)
    zusammen = {"gesendet": 0, "geloescht": 0, "offen": 0, "uebersprungen": False}
    if not _AUSGANG_LOCK.acquire(blocking=False):  # laeuft schon (anderer Thread)
        zusammen["uebersprungen"] = True
        zusammen["offen"] = ausgang_anzahl(root)
        return zusammen
    try:
        zusammen["geloescht"] += _ausgang_aufraeumen(root, jetzt)
        dateien = _ausgang_dateien(root)
        url = ziel_url(config, fetch=fetch, jetzt=jetzt) if dateien else None
        for pfad in dateien if url else []:
            payload = _lade_eintrag(pfad)
            if payload is None or _bilder_bytes(payload) > MAX_BILDER_BYTES * 1.02:
                if _loeschen(pfad):
                    zusammen["geloescht"] += 1
                    _log("abgelehnt", "zu_gross" if payload else "kaputt", wo="Ausgang")
                continue
            if _grenze_erreicht(_lade_stand(root), jetzt):
                break
            grund = _versuchen(payload, url, post, root, jetzt)
            if grund == "ok":
                _loeschen(pfad)
                zusammen["gesendet"] += 1
                _log("gesendet", wo="Ausgang")
            elif grund == "zu_gross":
                if _loeschen(pfad):
                    zusammen["geloescht"] += 1
                _log("abgelehnt", grund, wo="Ausgang")
            elif grund in ("offline", "limit"):
                break  # spaeter nochmal - die anderen gar nicht erst versuchen
        zusammen["offen"] = ausgang_anzahl(root)
        return zusammen
    finally:
        _AUSGANG_LOCK.release()


# -- Nachfrage-Plan (Pop-up) ---------------------------------------------------------------
def nutzung_hinzufuegen(sekunden: Any, *, root: Any = None) -> float:
    """Nutzungszeit dazuzaehlen (Sekunden); gibt die Summe zurueck."""
    plus = _zahl(sekunden)
    wurzel = _wurzel(root)
    if plus <= 0:
        return _zahl(_lade_stand(wurzel).get("nutzung_sekunden"))
    plus = min(plus, _MAX_NUTZUNG_PRO_AUFRUF)

    def zaehlen(stand: dict) -> float:
        summe = round(max(0.0, _zahl(stand.get("nutzung_sekunden"))) + plus, 1)
        stand["nutzung_sekunden"] = summe
        return summe

    return _stand_aendern(wurzel, zaehlen)


def nutzung_sekunden(root: Any = None) -> float:
    return max(0.0, _zahl(_lade_stand(_wurzel(root)).get("nutzung_sekunden")))


def _zeit_merken(schluessel: str, jetzt: datetime | None, root: Any) -> None:
    zeit = _iso(_jetzt(jetzt))
    _stand_aendern(_wurzel(root), lambda stand: stand.__setitem__(schluessel, zeit))


def gezeigt(jetzt: datetime | None = None, *, root: Any = None) -> None:
    """Pop-up wurde gezeigt oder weggeklickt ("Spaeter")."""
    _zeit_merken("zuletzt_gezeigt", jetzt, root)


def gesendet(jetzt: datetime | None = None, *, root: Any = None) -> None:
    """Nutzer hat Feedback abgeschickt (gesendet oder im Ausgang)."""
    _zeit_merken("zuletzt_gesendet", jetzt, root)


def ist_faellig(config, jetzt: datetime | None = None) -> bool:
    """Soll das Pop-up "Wie gefaellt dir Nova?" jetzt kommen? (nur lokal, kein Netz)

    Ja, wenn nachfragen an ist, schon >= erste_nachfrage_minuten genutzt und noch nie gezeigt
    bzw. seit dem letzten Zeigen/Senden >= nachfrage_alle_tage Tage vergangen sind."""
    einstellungen = getattr(config, "feedback", None)
    if einstellungen is None or not getattr(einstellungen, "nachfragen", True):
        return False
    jetzt = _jetzt(jetzt)
    minuten = _ganzzahl(getattr(einstellungen, "erste_nachfrage_minuten", 60), 60, 0)
    tage = _ganzzahl(getattr(einstellungen, "nachfrage_alle_tage", 12), 12, 1)
    stand = _lade_stand(_wurzel(config))
    if _zahl(stand.get("nutzung_sekunden")) < minuten * 60:
        return False
    zuletzt = [z for z in (_zeit(stand.get("zuletzt_gezeigt")), _zeit(stand.get("zuletzt_gesendet")))
               if z is not None and z <= jetzt + timedelta(days=1)]  # Uhr weit vorgestellt: ignorieren
    if not zuletzt:
        return True
    return jetzt - max(zuletzt) >= timedelta(days=tage)


def status(config, *, fetch: Callable | None = None, jetzt: datetime | None = None,
           netz: bool = True) -> dict:
    """Antwort fuer GET /api/feedback."""
    return {
        "ok": True,
        "configured": ist_eingerichtet(config, fetch=fetch, jetzt=jetzt, netz=netz),
        "due": ist_faellig(config, jetzt),
        "pending": ausgang_anzahl(config),
        "max_images": MAX_BILDER,
    }
