"""Bildgenerator: Nova malt Bilder aus einer Beschreibung - kostenlos.

Zwei Anbieter:
  * AI Horde (Standard, ohne Anmeldung): ein Netz aus Freiwilligen-Rechnern. Kostenlos, aber
    manchmal mit Wartezeit (Warteschlange). Anonyme Auftraege samt Beschreibung teilt AI Horde
    mit LAION (oeffentlicher Datensatz) - deshalb keine persoenlichen Daten in Beschreibungen.
  * Cloudflare Workers AI (optional): eigener Gratis-Schluessel, schneller, mit Tageslimit
    (setzt sich um 0 Uhr UTC zurueck). Bei anbieter="auto" wird bei Problemen auf AI Horde
    ausgewichen.

Netz nur ueber 'requests', immer mit Timeouts und mit TLS-Pruefung. Abbrechbar ueber
cancel_event (Stopp-Knopf). Schluessel und Bildbytes erscheinen nie in Meldungen oder Logs.
"""
from __future__ import annotations

import base64
import binascii
import logging
import random
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

from . import __version__
from .bilder import ERLAUBT, erkenne_typ
from .cancel import Abgebrochen

log = logging.getLogger("ki.bilder")

# -- Anbieter -----------------------------------------------------------------
HORDE = "horde"
CLOUDFLARE = "cloudflare"
NAMEN = {HORDE: "AI Horde", CLOUDFLARE: "Cloudflare"}

# -- Formate und Dateien --------------------------------------------------------
FORMATE = {"quadrat": (1024, 1024), "hoch": (768, 1152), "quer": (1152, 768)}
_FORMAT_NAMEN = {
    "quadrat": "quadrat", "quadratisch": "quadrat", "square": "quadrat", "1:1": "quadrat",
    "hoch": "hoch", "hochformat": "hoch", "portrait": "hoch", "senkrecht": "hoch",
    "quer": "quer", "querformat": "quer", "landscape": "quer", "breit": "quer", "waagerecht": "quer",
}
ORDNER = "bilder"  # erzeugte Bilder: <Arbeitsordner>/bilder/
DATEINAME_MUSTER = re.compile(r"^[A-Za-z0-9_-]{1,100}\.(png|jpe?g|webp|gif)$")

# -- Dienste ------------------------------------------------------------------
HORDE_API = "https://aihorde.net/api/v2"
HORDE_ANON_KEY = "0000000000"  # oeffentlicher Gast-Schluessel von AI Horde (kein Geheimnis)
CLIENT_AGENT = f"Nova:{__version__}:https://github.com/GermanClaude/Selbst-lernende-KI"
CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_MODELL = "@cf/black-forest-labs/flux-1-schnell"

# -- Grenzen ------------------------------------------------------------------
MAX_BESCHREIBUNG = 2000
MAX_CLOUDFLARE_PROMPT = 2048
MAX_BILD_BYTES = 15 * 1024 * 1024
HORDE_MAX_SEKUNDEN = 540        # ~9 Minuten (Auftraege verfallen bei AI Horde nach 10)
MODELLE_CACHE_SEKUNDEN = 3600   # Modell-Liste von AI Horde 1 Stunde merken
_ETA_GRENZE = 300               # Familie mit laengerer Wartezeit hinter schnellere stellen
_MAX_FEHLVERSUCHE = 5           # Abfragen hintereinander ohne Antwort -> aufgeben
_TIMEOUT_KURZ = (10, 20)
_TIMEOUT_AUFTRAG = (10, 30)
_TIMEOUT_BILD = (10, 60)
_TIMEOUT_CLOUDFLARE = (10, 90)
_TIMEOUT_AUFRAEUMEN = (5, 10)

_KONTO_MUSTER = re.compile(r"^[0-9a-fA-F]{32}$")
_AUFTRAG_MUSTER = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_STANDARD_MODELL = "Flux.1-Schnell fp8 (Compact)"


class GeneratorFehler(Exception):
    """Das Bild konnte nicht erstellt werden (deutscher Text fuer Nutzer und Modell).

    ausweichen=True: ein anderer Anbieter koennte es noch schaffen (Netz, Limit, Schluessel).
    ausweichen=False: die Beschreibung selbst wurde abgelehnt - nicht woanders probieren."""

    def __init__(self, meldung: str, ausweichen: bool = True):
        super().__init__(meldung)
        self.ausweichen = ausweichen


class _NichtMoeglich(GeneratorFehler):
    """AI Horde hat gerade keinen passenden Rechner fuer dieses Modell."""


@dataclass
class Ergebnis:
    data: bytes = field(repr=False)
    mime: str
    anbieter: str          # Anzeigename: "AI Horde" | "Cloudflare"
    modell: str
    seed: str = ""
    hinweis: str = ""      # z.B. "Cloudflare-Limit erreicht - AI Horde genommen"
    dauer: float = 0.0     # Sekunden

    @property
    def endung(self) -> str:
        return ERLAUBT.get(self.mime, "bin")


# -- Auswahl ------------------------------------------------------------------
def _gewuenscht(config: Any) -> str:
    wert = str(getattr(getattr(config, "bilder", None), "anbieter", "") or "auto").strip().lower()
    return wert if wert in (HORDE, CLOUDFLARE) else "auto"


def _cloudflare_zugang(config: Any) -> tuple[str, str]:
    konto = str(getattr(config, "cloudflare_account_id", "") or "").strip()
    token = str(getattr(config, "cloudflare_api_key", "") or "").strip()
    return konto, token


def cloudflare_eingerichtet(config: Any) -> bool:
    """Konto-ID und Schluessel fuer Cloudflare sind eingetragen (geprueft wird hier nichts)."""
    konto, token = _cloudflare_zugang(config)
    return bool(konto and token)


def waehle_anbieter(config: Any) -> str:
    """HORDE oder CLOUDFLARE - welcher Anbieter fuer das naechste Bild gilt.

    auto (Standard) = Cloudflare, wenn Schluessel und Konto da sind, sonst AI Horde.
    "cloudflare" ohne Schluessel -> AI Horde (anders geht es nicht)."""
    if _gewuenscht(config) in ("auto", CLOUDFLARE) and cloudflare_eingerichtet(config):
        return CLOUDFLARE
    return HORDE


def aktiver_anbieter(config: Any) -> str:
    """Anzeigename des Anbieters, der gerade gilt: "AI Horde" oder "Cloudflare"."""
    return NAMEN[waehle_anbieter(config)]


def format_name(wert: str | None) -> str | None:
    """'quadrat' | 'hoch' | 'quer' (auch Synonyme wie 'landscape'); unbekannt -> None."""
    return _FORMAT_NAMEN.get(str(wert or "quadrat").strip().lower())


# -- Beschreibung und Dateiname -------------------------------------------------
_STEUERZEICHEN = re.compile(r"[\x00-\x1f\x7f]+")
_UMLAUTE = str.maketrans({"\u00e4": "ae", "\u00f6": "oe", "\u00fc": "ue", "\u00df": "ss",
                          "\u00c4": "Ae", "\u00d6": "Oe", "\u00dc": "Ue"})
_FUELLWOERTER = {"a", "an", "the", "of", "with", "and", "in", "on", "at", "very", "highly",
                 "ein", "eine", "einer", "einem", "der", "die", "das", "mit", "und", "im"}


def bereinige(beschreibung: Any) -> str:
    """Beschreibung ohne Steuerzeichen und doppelte Leerzeichen, hoechstens 2000 Zeichen."""
    text = _STEUERZEICHEN.sub(" ", str(beschreibung or ""))
    return " ".join(text.split())[:MAX_BESCHREIBUNG].strip()


def kurzname(beschreibung: str) -> str:
    """'A red cat on a roof' -> 'red-cat-roof' (nur a-z, 0-9 und '-', hoechstens 40 Zeichen)."""
    text = unicodedata.normalize("NFKD", str(beschreibung or "").translate(_UMLAUTE))
    woerter = re.findall(r"[a-z0-9]+", text.encode("ascii", "ignore").decode("ascii").lower())
    wichtig = [w for w in woerter if w not in _FUELLWOERTER] or woerter
    name = ""
    for wort in wichtig[:6]:
        neu = f"{name}-{wort}" if name else wort
        if len(neu) > 40:
            break
        name = neu
    return name or (wichtig[0][:40] if wichtig else "bild")


def bilder_ordner(arbeitsordner: Any) -> Path:
    """Ordner der erzeugten Bilder: <Arbeitsordner>/bilder (wird hier nicht angelegt)."""
    return Path(arbeitsordner) / ORDNER


def dateistamm(beschreibung: str, jetzt: datetime | None = None) -> str:
    """'20261108-153000_red-cat-roof' - Dateiname ohne Endung (passt zu DATEINAME_MUSTER)."""
    return f"{(jetzt or datetime.now()).strftime('%Y%m%d-%H%M%S')}_{kurzname(beschreibung)}"


# -- AI Horde: Modelle ----------------------------------------------------------
@dataclass(frozen=True)
class _Familie:
    name: str
    passt: Callable[[str], bool]
    params: dict
    negativ: str = ""


_SDXL_NAMEN = ("juggernaut xl", "albedobase xl (sdxl)", "albedobase xl 3.1", "albedobase xl", "sdxl 1.0")
_NEGATIV = "nsfw, nude, lowres, blurry, bad anatomy, watermark, signature, text"

# Reihenfolge = Vorliebe. Werte nach der Modell-Referenz von AI Horde (Schritte/CFG/Sampler).
_FAMILIEN = (
    _Familie("FLUX", lambda n: "flux" in n and "schnell" in n,
             {"steps": 4, "cfg_scale": 1.0, "sampler_name": "k_euler", "karras": True}),
    _Familie("Z-Image", lambda n: "z-image" in n and "turbo" in n,
             {"steps": 9, "cfg_scale": 1.0, "sampler_name": "k_euler", "karras": False}),
    _Familie("Qwen-Image", lambda n: n.startswith("qwen-image") and "edit" not in n,
             {"steps": 20, "cfg_scale": 2.5, "sampler_name": "k_euler", "karras": False}),
    _Familie("SDXL", lambda n: n in _SDXL_NAMEN,
             {"steps": 25, "cfg_scale": 6.0, "sampler_name": "k_dpmpp_2m", "karras": True}, _NEGATIV),
)

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"zeit": 0.0, "liste": None}


def modelle_cache_leeren() -> None:
    """Gemerkte Modell-Liste vergessen (fuer Tests)."""
    with _cache_lock:
        _cache["zeit"], _cache["liste"] = 0.0, None


def _zahl(wert: Any) -> float:
    try:
        return float(wert or 0)
    except (TypeError, ValueError):
        return 0.0


def _horde_headers() -> dict[str, str]:
    return {"apikey": HORDE_ANON_KEY, "Client-Agent": CLIENT_AGENT, "Accept": "application/json"}


def _horde_modelle(http: Any, uhr: Callable[[], float]) -> list | None:
    """Liste der Bildmodelle mit freien Rechnern (1 Stunde gemerkt); None, wenn nicht abrufbar."""
    with _cache_lock:
        if _cache["liste"] is not None and uhr() - _cache["zeit"] < MODELLE_CACHE_SEKUNDEN:
            return _cache["liste"]
    try:
        resp = http.get(f"{HORDE_API}/status/models?type=image", headers=_horde_headers(),
                        timeout=_TIMEOUT_KURZ)
        if int(getattr(resp, "status_code", 0)) != 200:
            return None
        daten = resp.json()
    except Exception:  # noqa: BLE001 - ohne Liste geht es mit dem Standardmodell weiter
        return None
    if not isinstance(daten, list):
        return None
    with _cache_lock:
        _cache["zeit"], _cache["liste"] = uhr(), daten
    return daten


def _waehle_modelle(liste: list | None) -> list[tuple[_Familie, list[str]]]:
    """Kandidaten in Reihenfolge: (Familie, Modellnamen mit freien Rechnern).

    Reihenfolge FLUX schnell -> Z-Image-Turbo -> Qwen-Image -> SDXL; eine Familie mit sehr
    langer Wartezeit rutscht hinter die, die schneller dran sind."""
    kandidaten: list[tuple[_Familie, list[str], float]] = []
    for familie in _FAMILIEN:
        treffer = [m for m in (liste or []) if isinstance(m, dict) and _zahl(m.get("count")) > 0
                   and familie.passt(str(m.get("name", "")).strip().lower())]
        if not treffer:
            continue
        treffer.sort(key=lambda m: -_zahl(m.get("count")))
        eta = min(_zahl(m.get("eta")) for m in treffer)
        kandidaten.append((familie, [str(m["name"]) for m in treffer[:5]], eta))
    if not kandidaten:
        return [(_FAMILIEN[0], [_STANDARD_MODELL])]
    schnell = [k for k in kandidaten if k[2] <= _ETA_GRENZE]
    langsam = [k for k in kandidaten if k[2] > _ETA_GRENZE]
    return [(familie, namen) for familie, namen, _eta in schnell + langsam]


# -- Texte --------------------------------------------------------------------
def _dauer(sekunden: float) -> str:
    sekunden = int(round(sekunden))
    if sekunden < 90:
        return f"ca. {sekunden} s"
    return f"ca. {round(sekunden / 60)} Min."


def _stand_text(daten: dict) -> str:
    """Fortschritt fuer die Oberflaeche, z.B. 'In der Warteschlange: Platz 3, ca. 40 s'."""
    platz = int(_zahl(daten.get("queue_position")))
    rest = _zahl(daten.get("wait_time"))
    if _zahl(daten.get("processing")) > 0 and _zahl(daten.get("waiting")) == 0:
        text = "Das Bild wird gemalt"
    elif platz > 0:
        text = f"In der Warteschlange: Platz {platz}"
    else:
        text = "Warte auf einen freien Rechner"
    return f"{text}, {_dauer(rest)}" if rest > 0 else text


def _reset_text(jetzt: datetime | None = None, zone: tzinfo | None = None) -> str:
    """Wann das Cloudflare-Tageslimit wieder frei ist (0 Uhr UTC), in Ortszeit:
    'ab ca. 1 Uhr nachts' (Winter in Deutschland), 'ab ca. 2 Uhr nachts' (Sommer)."""
    jetzt = (jetzt or datetime.now(timezone.utc)).astimezone(timezone.utc)
    naechste = (jetzt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    stunde = naechste.astimezone(zone).hour
    if stunde == 0:
        return "ab ca. Mitternacht"
    if stunde <= 5:
        return f"ab ca. {stunde} Uhr nachts"
    return f"ab ca. {stunde} Uhr"


def _netzfehler_text(dienst: str, exc: BaseException) -> str:
    art = type(exc).__name__.lower()
    if "timeout" in art:
        return f"{dienst} antwortet gerade nicht (Zeit\u00fcberschreitung). Bitte gleich noch einmal versuchen."
    if "ssl" in art:
        return f"Keine sichere Verbindung zu {dienst} m\u00f6glich."
    return f"Keine Verbindung zu {dienst}. Bist du online?"


_TIPP_CLOUDFLARE = ("Tipp: In \u201eGehirn & Schl\u00fcssel\u201c l\u00e4sst sich der kostenlose "
                    "Cloudflare-Zugang einrichten (schneller).")


# -- Netz-Helfer --------------------------------------------------------------
def _standard_http():
    try:
        import requests  # lokal importieren, damit das Modul ohne requests importierbar bleibt
    except ImportError as exc:  # pragma: no cover - requests ist Pflicht-Abhaengigkeit
        raise GeneratorFehler("Das Paket 'requests' fehlt. Installiere es mit: pip install requests") from exc
    return requests


def _abbrechbar(cancel_event: threading.Event | None, fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """Fuehrt einen (blockierenden) Netzaufruf aus; der Stopp-Knopf wirkt sofort.

    Mit cancel_event laeuft der Aufruf in einem Hintergrund-Thread, hier wird alle 0,2 s
    nachgesehen, ob angehalten wurde. Der Thread laeuft dann allein bis zu seinem Timeout aus."""
    if cancel_event is None:
        return fn(*args, **kwargs)
    if cancel_event.is_set():
        raise Abgebrochen()
    ergebnis: dict[str, Any] = {}
    fertig = threading.Event()

    def lauf() -> None:
        try:
            ergebnis["wert"] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - im Aufrufer-Thread erneut werfen
            ergebnis["fehler"] = exc
        finally:
            fertig.set()

    threading.Thread(target=lauf, name="bildgenerator-netz", daemon=True).start()
    while not fertig.wait(0.2):
        if cancel_event.is_set():
            raise Abgebrochen()
    if "fehler" in ergebnis:
        raise ergebnis["fehler"]
    return ergebnis["wert"]


def _json(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001 - z.B. HTML-Fehlerseite
        return None


def _schliessen(resp: Any) -> None:
    close = getattr(resp, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001
            pass


def _lies_begrenzt(resp: Any, grenze: int) -> bytes:
    """Antwort lesen, aber nie mehr als `grenze` Bytes (Schutz vor Riesen-Dateien)."""
    zu_gross = GeneratorFehler("Das fertige Bild ist zu gro\u00df.")
    headers = getattr(resp, "headers", None) or {}
    try:
        if int(headers.get("Content-Length") or 0) > grenze:
            raise zu_gross
    except (TypeError, ValueError):
        pass
    iter_content = getattr(resp, "iter_content", None)
    if callable(iter_content):
        teile, groesse = [], 0
        for stueck in iter_content(65536):
            if not stueck:
                continue
            groesse += len(stueck)
            if groesse > grenze:
                raise zu_gross
            teile.append(stueck)
        return b"".join(teile)
    data = getattr(resp, "content", b"") or b""
    if len(data) > grenze:
        raise zu_gross
    return data


def _bild_holen(http: Any, img: Any) -> bytes:
    """Fertiges Bild von AI Horde: https-Download (R2) oder Base64. Nie http oder andere Schemata."""
    if not isinstance(img, str) or not img.strip():
        raise GeneratorFehler("AI Horde hat kein Bild geliefert. Bitte noch einmal versuchen.")
    img = img.strip()
    if "://" not in img[:16]:  # ohne R2: Base64 direkt in der Antwort
        if len(img) > MAX_BILD_BYTES * 4 // 3 + 16:
            raise GeneratorFehler("Das fertige Bild ist zu gro\u00df.")
        try:
            return base64.b64decode(img, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise GeneratorFehler("Das fertige Bild kam besch\u00e4digt an.") from exc
    url = img
    for _sprung in range(4):
        teile = urlsplit(url)
        if teile.scheme != "https" or not teile.hostname or "@" in teile.netloc:
            raise GeneratorFehler("AI Horde hat eine unsichere Bild-Adresse geliefert - nicht geladen.")
        resp = http.get(url, timeout=_TIMEOUT_BILD, stream=True, allow_redirects=False)
        try:
            code = int(getattr(resp, "status_code", 0))
            ziel = (getattr(resp, "headers", None) or {}).get("Location")
            if 300 <= code < 400 and ziel:
                url = urljoin(url, str(ziel).strip())
                continue
            if code != 200:
                raise GeneratorFehler(f"Das fertige Bild lie\u00df sich nicht herunterladen (Fehler {code}).")
            return _lies_begrenzt(resp, MAX_BILD_BYTES)
        finally:
            _schliessen(resp)
    raise GeneratorFehler("Das fertige Bild lie\u00df sich nicht herunterladen (zu viele Weiterleitungen).")


def _pruefe_bild(data: bytes, dienst: str) -> str:
    mime = erkenne_typ(data or b"")
    if mime not in ERLAUBT:
        raise GeneratorFehler(f"{dienst} hat kein lesbares Bild geliefert. Bitte noch einmal versuchen.")
    return mime


def _fehler_daten(resp: Any) -> tuple[list[int], str, str]:
    """(Fehlercodes, Fehlertexte klein, rc) aus einer JSON-Fehlerantwort."""
    daten = _json(resp)
    codes: list[int] = []
    texte: list[str] = []
    rc = ""
    if isinstance(daten, dict):
        rc = str(daten.get("rc") or "")
        if daten.get("message"):
            texte.append(str(daten["message"]))
        for fehler in daten.get("errors") or []:
            if isinstance(fehler, dict):
                try:
                    codes.append(int(fehler.get("code")))
                except (TypeError, ValueError):
                    pass
                texte.append(str(fehler.get("message") or ""))
            elif isinstance(fehler, str):
                texte.append(fehler)
    return codes, " ".join(texte).lower(), rc


def _horde_fehler(resp: Any) -> GeneratorFehler:
    code = int(getattr(resp, "status_code", 0))
    _codes, text, rc = _fehler_daten(resp)
    if rc in ("CorruptPrompt", "Profanity"):
        return GeneratorFehler("AI Horde hat die Beschreibung abgelehnt (Sicherheitsfilter). Bitte anders "
                               "beschreiben - ohne Gewalt, Erwachsenen-Inhalte oder echte Personen.",
                               ausweichen=False)
    if code == 429 or rc == "TooManyPrompts":
        return GeneratorFehler("AI Horde hat gerade zu viele Auftr\u00e4ge. Bitte gleich noch einmal versuchen.")
    if code in (401, 403) or rc in ("AnonForbidden", "InvalidAPIKey"):
        return GeneratorFehler("AI Horde nimmt gerade keine Auftr\u00e4ge ohne Anmeldung an (sehr hohe Last). "
                               "Bitte sp\u00e4ter noch einmal. " + _TIPP_CLOUDFLARE)
    if code == 503:
        return GeneratorFehler("AI Horde wird gerade gewartet. Bitte sp\u00e4ter noch einmal versuchen.")
    if rc == "KudosUpfront":
        return GeneratorFehler("Dieses Bild ist f\u00fcr AI Horde ohne Anmeldung zu aufwendig. "
                               "Versuch es mit einem einfacheren Format (quadrat).")
    if code >= 500:
        return GeneratorFehler(f"AI Horde hat gerade ein Problem (Fehler {code}). Bitte sp\u00e4ter noch einmal.")
    zusatz = f", {rc}" if re.fullmatch(r"[A-Za-z]{1,40}", rc) else ""
    return GeneratorFehler(f"AI Horde hat den Auftrag abgelehnt (Fehler {code}{zusatz}).")


def _cloudflare_fehler(resp: Any) -> GeneratorFehler:
    code = int(getattr(resp, "status_code", 0))
    codes, text, _rc = _fehler_daten(resp)
    if 4006 in codes or "daily free allocation" in text or "neuron" in text:
        return GeneratorFehler(f"Das kostenlose Cloudflare-Tageslimit ist erreicht \u2013 {_reset_text()} wieder.")
    if code in (401, 403) or 10000 in codes or "authentication" in text:
        return GeneratorFehler("Der Cloudflare-Schl\u00fcssel ist ung\u00fcltig oder darf Workers AI nicht nutzen. "
                               "Bitte in \u201eGehirn & Schl\u00fcssel\u201c neu eintragen.")
    if code == 429:
        return GeneratorFehler(f"Das kostenlose Cloudflare-Tageslimit ist erreicht \u2013 {_reset_text()} wieder.")
    if "nsfw" in text or "unsafe" in text or "flagged" in text:
        return GeneratorFehler("Cloudflare hat die Beschreibung abgelehnt (Sicherheitsfilter). Bitte anders "
                               "beschreiben - ohne Gewalt, Erwachsenen-Inhalte oder echte Personen.",
                               ausweichen=False)
    if code == 404 or 7003 in codes or "could not route" in text:
        return GeneratorFehler("Die Cloudflare-Konto-ID stimmt nicht. Bitte in \u201eGehirn & Schl\u00fcssel\u201c "
                               "pr\u00fcfen.")
    if code >= 500:
        return GeneratorFehler(f"Cloudflare hat gerade ein Problem (Fehler {code}). Bitte sp\u00e4ter noch einmal.")
    return GeneratorFehler(f"Cloudflare hat den Auftrag abgelehnt (Fehler {code}).")


# -- Der Generator ------------------------------------------------------------
class Bildgenerator:
    """Erstellt ein Bild ueber den eingestellten Anbieter.

    http: requests-artig (get/post/delete) - Standard ist das Modul 'requests' (Tests: Attrappe).
    fortschritt(text): optionaler Rueckruf fuer die Oberflaeche ("In der Warteschlange: Platz 3 ...").
    cancel_event: Stopp-Knopf; dann wird Abgebrochen geworfen (wie bei Strg+C).
    uhr / warten: fuer Tests austauschbar (Standard: time.monotonic / cancel_event.wait)."""

    def __init__(self, config: Any = None, *, http: Any = None,
                 fortschritt: Callable[[str], None] | None = None,
                 cancel_event: threading.Event | None = None,
                 uhr: Callable[[], float] | None = None,
                 warten: Callable[[float], None] | None = None):
        self.config = config
        self.http = http if http is not None else _standard_http()
        self.fortschritt = fortschritt
        self.cancel_event = cancel_event
        self.uhr = uhr or time.monotonic
        self._warten = warten
        self._letzte_meldung: str | None = None
        self.aufraeum_thread: threading.Thread | None = None  # zuletzt gestartetes Aufraeumen (Tests)

    # -- kleine Helfer ----------------------------------------------------------
    def _melde(self, text: str) -> None:
        if not self.fortschritt or text == self._letzte_meldung:
            return
        self._letzte_meldung = text
        try:
            self.fortschritt(text)
        except Exception:  # noqa: BLE001 - Anzeige darf nie stoeren
            pass

    def _pruefe_abbruch(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise Abgebrochen()

    def _warte(self, sekunden: float) -> None:
        self._pruefe_abbruch()
        if sekunden > 0:
            if self._warten is not None:
                self._warten(sekunden)
            elif self.cancel_event is not None:
                self.cancel_event.wait(sekunden)
            else:
                time.sleep(sekunden)
        self._pruefe_abbruch()

    def _netz(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        return _abbrechbar(self.cancel_event, fn, *args, **kwargs)

    # -- Einstieg -----------------------------------------------------------------
    def erstellen(self, beschreibung: str, format: str = "quadrat") -> Ergebnis:
        prompt = bereinige(beschreibung)
        if not prompt:
            raise GeneratorFehler("Die Bildbeschreibung ist leer.", ausweichen=False)
        breite, hoehe = FORMATE[format_name(format) or "quadrat"]
        start = self.uhr()
        gewuenscht = _gewuenscht(self.config)
        hinweis = ""
        if gewuenscht == CLOUDFLARE and not cloudflare_eingerichtet(self.config):
            hinweis = ("Cloudflare ist nicht eingerichtet (Konto-ID oder Schl\u00fcssel fehlt) \u2013 "
                       "das Bild kommt deshalb von AI Horde.")
        if waehle_anbieter(self.config) == CLOUDFLARE:
            try:
                ergebnis = self._cloudflare(prompt)
                ergebnis.dauer = self.uhr() - start
                log.info("Bild erstellt (Cloudflare, %.0f s).", ergebnis.dauer)
                return ergebnis
            except GeneratorFehler as exc:
                if gewuenscht != "auto" or not exc.ausweichen:
                    log.info("Bild nicht erstellt (Cloudflare): %s", exc)
                    raise
                log.info("Cloudflare klappt nicht, weiche auf AI Horde aus: %s", exc)
                hinweis = f"{exc} Das Bild kommt deshalb von AI Horde."
                self._melde("Cloudflare klappt gerade nicht \u2013 ich nehme AI Horde \u2026")
        try:
            ergebnis = self._horde(prompt, breite, hoehe)
        except GeneratorFehler as exc:
            log.info("Bild nicht erstellt (AI Horde): %s", exc)
            raise
        ergebnis.hinweis = hinweis
        ergebnis.dauer = self.uhr() - start
        log.info("Bild erstellt (AI Horde, Modell %s, %.0f s).", ergebnis.modell, ergebnis.dauer)
        return ergebnis

    # -- Cloudflare ---------------------------------------------------------------
    def _cloudflare(self, prompt: str) -> Ergebnis:
        konto, token = _cloudflare_zugang(self.config)
        if not konto or not token:
            raise GeneratorFehler("Cloudflare ist nicht eingerichtet (Konto-ID oder Schl\u00fcssel fehlt).")
        if not _KONTO_MUSTER.match(konto):
            raise GeneratorFehler("Die Cloudflare-Konto-ID sieht nicht richtig aus (32 Zeichen aus 0-9 und a-f).")
        self._melde("Cloudflare malt das Bild \u2026")
        seed = random.randint(1, 2**31 - 1)
        url = f"{CLOUDFLARE_API}/accounts/{konto}/ai/run/{CLOUDFLARE_MODELL}"
        try:
            resp = self._netz(self.http.post, url,
                              headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                              json={"prompt": prompt[:MAX_CLOUDFLARE_PROMPT], "steps": 4, "seed": seed},
                              timeout=_TIMEOUT_CLOUDFLARE)
        except GeneratorFehler:
            raise
        except Exception as exc:  # noqa: BLE001 - Netzfehler (Meldung ohne Adresse/Schluessel)
            raise GeneratorFehler(_netzfehler_text("Cloudflare", exc)) from None
        try:
            code = int(getattr(resp, "status_code", 0))
            if code != 200:
                raise _cloudflare_fehler(resp)
            art = str((getattr(resp, "headers", None) or {}).get("Content-Type") or "").lower()
            if art.startswith("image/"):
                data = _lies_begrenzt(resp, MAX_BILD_BYTES)
            else:
                daten = _json(resp)
                if not isinstance(daten, dict) or daten.get("success") is False:
                    raise _cloudflare_fehler(resp)
                ergebnis = daten.get("result")
                b64 = (ergebnis.get("image") if isinstance(ergebnis, dict) else None) or daten.get("image")
                if not isinstance(b64, str) or not b64:
                    raise GeneratorFehler("Cloudflare hat kein Bild geliefert. Bitte noch einmal versuchen.")
                if len(b64) > MAX_BILD_BYTES * 4 // 3 + 16:
                    raise GeneratorFehler("Das fertige Bild ist zu gro\u00df.")
                try:
                    data = base64.b64decode(b64, validate=False)
                except (binascii.Error, ValueError):
                    raise GeneratorFehler("Das fertige Bild kam besch\u00e4digt an.") from None
        finally:
            _schliessen(resp)
        mime = _pruefe_bild(data, "Cloudflare")
        return Ergebnis(data=data, mime=mime, anbieter=NAMEN[CLOUDFLARE], modell="FLUX.1 schnell",
                        seed=str(seed))

    # -- AI Horde -------------------------------------------------------------------
    def _horde(self, prompt: str, breite: int, hoehe: int) -> Ergebnis:
        frist = self.uhr() + HORDE_MAX_SEKUNDEN
        self._melde("Schicke die Bildbeschreibung an AI Horde \u2026")
        kandidaten = _waehle_modelle(self._netz(_horde_modelle, self.http, self.uhr))
        letzter: GeneratorFehler | None = None
        for familie, modelle in kandidaten[:2]:  # hoechstens ein zweiter Versuch mit anderem Modell
            if self.uhr() >= frist:
                break
            try:
                return self._horde_auftrag(prompt, breite, hoehe, familie, modelle, frist)
            except _NichtMoeglich as exc:
                letzter = exc
        if letzter is not None:
            raise GeneratorFehler(str(letzter))
        raise self._zu_lange()

    @staticmethod
    def _zu_lange() -> GeneratorFehler:
        return GeneratorFehler("AI Horde ist gerade sehr ausgelastet \u2013 nach 9 Minuten war das Bild noch "
                               "nicht fertig. Bitte sp\u00e4ter noch einmal versuchen. " + _TIPP_CLOUDFLARE)

    def _horde_loeschen(self, auftrag: str) -> None:
        """Auftrag bei AI Horde zurueckziehen (im Hintergrund, Fehler egal)."""
        http = self.http

        def weg() -> None:
            try:
                resp = http.delete(f"{HORDE_API}/generate/status/{auftrag}", headers=_horde_headers(),
                                   timeout=_TIMEOUT_AUFRAEUMEN)
                _schliessen(resp)
            except Exception:  # noqa: BLE001
                pass

        self.aufraeum_thread = threading.Thread(target=weg, name="bildgenerator-aufraeumen", daemon=True)
        self.aufraeum_thread.start()

    def _horde_auftrag(self, prompt: str, breite: int, hoehe: int, familie: _Familie,
                       modelle: list[str], frist: float) -> Ergebnis:
        seed = str(random.randint(1, 2**31 - 1))
        text = " ".join(prompt.replace("###", " ").split())  # '###' trennt bei AI Horde den Negativ-Teil
        if familie.negativ:
            text = f"{text} ### {familie.negativ}"
        nutzlast = {
            "prompt": text,
            "params": {"width": breite, "height": hoehe, "n": 1, "seed": seed, **familie.params},
            "models": list(modelle),
            "nsfw": False,
            "censor_nsfw": True,
            "r2": True,
            "allow_downgrade": True,
            "slow_workers": True,
            "trusted_workers": False,
        }

        def senden() -> Any:
            antwort = self.http.post(f"{HORDE_API}/generate/async", headers=_horde_headers(),
                                     json=nutzlast, timeout=_TIMEOUT_AUFTRAG)
            if self.cancel_event is not None and self.cancel_event.is_set():
                # Stopp kam, waehrend der Auftrag unterwegs war: gleich wieder zurueckziehen,
                # damit kein Freiwilligen-Rechner umsonst malt (laeuft im Hintergrund-Thread).
                spaet = _json(antwort)
                spaet_id = str(spaet.get("id") or "") if isinstance(spaet, dict) else ""
                if _AUFTRAG_MUSTER.match(spaet_id):
                    self._horde_loeschen(spaet_id)
            return antwort

        try:
            resp = self._netz(senden)
        except Exception as exc:  # noqa: BLE001
            raise GeneratorFehler(_netzfehler_text("AI Horde", exc)) from None
        try:
            code = int(getattr(resp, "status_code", 0))
            daten = _json(resp)
            if code not in (200, 202):
                raise _horde_fehler(resp)
        finally:
            _schliessen(resp)
        auftrag = str(daten.get("id") or "") if isinstance(daten, dict) else ""
        if not _AUFTRAG_MUSTER.match(auftrag):
            raise GeneratorFehler("AI Horde hat den Auftrag nicht angenommen. Bitte noch einmal versuchen.")

        fertig = False
        try:
            self._horde_warten(auftrag, frist)
            fertig = True  # ab hier gibt es nichts mehr zurueckzuziehen
            self._melde("Fertig \u2013 hole das Bild \u2026")
            return self._horde_abholen(auftrag, modelle, seed)
        finally:
            if not fertig:
                self._horde_loeschen(auftrag)

    def _horde_warten(self, auftrag: str, frist: float) -> None:
        """Fragt alle 2-10 s nach, bis das Bild fertig ist (oder es nicht klappt)."""
        fehlversuche = 0
        while True:
            if self.uhr() >= frist:
                raise self._zu_lange()
            daten = None
            try:
                resp = self._netz(self.http.get, f"{HORDE_API}/generate/check/{auftrag}",
                                  headers=_horde_headers(), timeout=_TIMEOUT_KURZ)
                try:
                    code = int(getattr(resp, "status_code", 0))
                    if code == 404:
                        raise GeneratorFehler("AI Horde kennt den Auftrag nicht mehr (abgelaufen). "
                                              "Bitte noch einmal versuchen.")
                    if code == 200:
                        daten = _json(resp)
                finally:
                    _schliessen(resp)
            except GeneratorFehler:
                raise
            except Exception:  # noqa: BLE001 - Netz-Aussetzer: gleich noch einmal
                daten = None
            if not isinstance(daten, dict):
                fehlversuche += 1
                if fehlversuche >= _MAX_FEHLVERSUCHE:
                    raise GeneratorFehler("Keine Verbindung zu AI Horde. Bist du online?")
                self._warte(min(10.0, max(0.0, frist - self.uhr())))
                continue
            fehlversuche = 0
            if daten.get("faulted"):
                raise GeneratorFehler("AI Horde hat bei diesem Bild einen Fehler gemeldet. "
                                      "Bitte noch einmal versuchen.")
            if daten.get("done"):
                return
            if daten.get("is_possible") is False:
                raise _NichtMoeglich("Gerade ist bei AI Horde kein passender Rechner frei. "
                                     "Bitte sp\u00e4ter noch einmal versuchen. " + _TIPP_CLOUDFLARE)
            self._melde(_stand_text(daten))
            pause = min(10.0, max(2.0, _zahl(daten.get("wait_time")) / 4))
            self._warte(min(pause, max(0.0, frist - self.uhr())))

    def _horde_abholen(self, auftrag: str, modelle: list[str], seed: str) -> Ergebnis:
        daten = None
        for versuch in range(3):  # fertiges Bild nicht wegen eines Aussetzers verlieren
            if versuch:
                self._warte(6.0)  # /status ist bei AI Horde auf 10 Abrufe pro Minute begrenzt
            try:
                resp = self._netz(self.http.get, f"{HORDE_API}/generate/status/{auftrag}",
                                  headers=_horde_headers(), timeout=_TIMEOUT_KURZ)
            except Exception as exc:  # noqa: BLE001
                if versuch == 2:
                    raise GeneratorFehler(_netzfehler_text("AI Horde", exc)) from None
                continue
            try:
                code = int(getattr(resp, "status_code", 0))
                daten = _json(resp) if code == 200 else None
            finally:
                _schliessen(resp)
            if isinstance(daten, dict) or code == 404:
                break
        bilder = daten.get("generations") if isinstance(daten, dict) else None
        if not bilder or not isinstance(bilder[0], dict):
            raise GeneratorFehler("AI Horde hat kein Bild geliefert. Bitte noch einmal versuchen.")
        bild = bilder[0]
        if bild.get("censored") or str(bild.get("state") or "").lower() in ("censored", "csam"):
            raise GeneratorFehler("Der Sicherheitsfilter von AI Horde hat das Bild zur\u00fcckgehalten. Bitte "
                                  "anders beschreiben - ohne Gewalt, Erwachsenen-Inhalte oder echte Personen.",
                                  ausweichen=False)
        try:
            data = self._netz(_bild_holen, self.http, bild.get("img"))
        except GeneratorFehler:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GeneratorFehler(_netzfehler_text("AI Horde", exc)) from None
        mime = _pruefe_bild(data, "AI Horde")
        modell = str(bild.get("model") or (modelle[0] if modelle else "")) or "unbekannt"
        return Ergebnis(data=data, mime=mime, anbieter=NAMEN[HORDE], modell=modell,
                        seed=str(bild.get("seed") or seed))


def erstellen(beschreibung: str, format: str = "quadrat", *, config: Any = None, http: Any = None,
              fortschritt: Callable[[str], None] | None = None,
              cancel_event: threading.Event | None = None) -> Ergebnis:
    """Ein Bild erstellen - Kurzform fuer Bildgenerator(...).erstellen(...).

    Wirft GeneratorFehler (deutsche Meldung) oder Abgebrochen (Stopp-Knopf)."""
    return Bildgenerator(config, http=http, fortschritt=fortschritt,
                         cancel_event=cancel_event).erstellen(beschreibung, format)


# -- Schluessel pruefen (fuer die Einstellungen) ---------------------------------
def pruefe_cloudflare(token: str, konto: str | None = None, http: Any = None) -> tuple[bool, str]:
    """Prueft kurz einen Cloudflare-Schluessel: (ok, deutsche Meldung). Der Schluessel steht
    nie in der Meldung. Erst /user/tokens/verify, bei Konto-Schluesseln das Konto-Gegenstueck."""
    token = str(token or "").strip()
    konto = str(konto or "").strip()
    if not token:
        return False, "Kein Cloudflare-Schl\u00fcssel angegeben."
    if konto and not _KONTO_MUSTER.match(konto):
        return False, "Die Cloudflare-Konto-ID sieht nicht richtig aus (32 Zeichen aus 0-9 und a-f)."
    http = http if http is not None else _standard_http()
    adressen = [f"{CLOUDFLARE_API}/user/tokens/verify"]
    if konto:
        adressen.append(f"{CLOUDFLARE_API}/accounts/{konto}/tokens/verify")
    meldung = "Der Cloudflare-Schl\u00fcssel ist ung\u00fcltig."
    for url in adressen:
        try:
            resp = http.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT_KURZ)
        except Exception as exc:  # noqa: BLE001
            return False, _netzfehler_text("Cloudflare", exc)
        try:
            code = int(getattr(resp, "status_code", 0))
            daten = _json(resp)
        finally:
            _schliessen(resp)
        if code == 200 and isinstance(daten, dict) and daten.get("success") is not False:
            ergebnis = daten.get("result") if isinstance(daten.get("result"), dict) else {}
            if str(ergebnis.get("status") or "active").lower() == "active":
                return True, "Der Cloudflare-Schl\u00fcssel funktioniert."
            return False, "Der Cloudflare-Schl\u00fcssel ist nicht aktiv (abgelaufen oder gesperrt)."
        if code >= 500:
            meldung = f"Cloudflare hat gerade ein Problem (Fehler {code}). Bitte sp\u00e4ter noch einmal pr\u00fcfen."
    return False, meldung
