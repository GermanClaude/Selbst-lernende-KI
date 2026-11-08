"""Ollama: kostenlose KI-Modelle, die direkt auf deinem PC laufen (ohne Schluessel, ohne Kosten).

Ollama (https://ollama.com) ist ein kleines Programm, das offene Modelle (Qwen, Gemma, Llama ...)
lokal ausfuehrt. Es lauscht standardmaessig auf http://localhost:11434. Dieses Modul spricht mit
dieser Schnittstelle:
  GET  /api/version   laeuft Ollama? welche Version?
  GET  /api/tags      welche Modelle sind heruntergeladen?
  POST /api/show      was kann ein Modell? ("capabilities": tools, vision, thinking ...)
  POST /api/pull      Modell herunterladen (Fortschritt kommt als eine JSON-Zeile je Schritt)
  POST /api/chat      Unterhaltung (gestreamt, mit Werkzeugen, Bildern, Nachdenken)

Warum /api/chat und nicht die OpenAI-kompatible Schnittstelle (/v1)? Nur hier laesst sich die
Kontext-Laenge (num_ctx) setzen. Ollama nimmt sonst auf PCs ohne grosse Grafikkarte nur 4096
Token - zu wenig fuer System-Prompt und Werkzeuge; Ollama wuerde den Anfang still abschneiden.
OllamaClient bildet deshalb das kleine Stueck der openai-Bibliothek nach, das der DeepSeek-Provider
benutzt (client.chat.completions.create), und uebersetzt in beide Richtungen.

Zeigt die Adresse auf ".../v1" (z.B. LM Studio: http://localhost:1234/v1), wird stattdessen
ganz normal die OpenAI-kompatible Schnittstelle benutzt (siehe ist_openai_adresse).

Sicherheit: Die Adresse kommt nur aus den Einstellungen (vom Menschen gesetzt), nie von der KI.
Erlaubt sind nur http(s)-Adressen ohne Benutzername/Passwort.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import threading
import time
import urllib.error
from types import SimpleNamespace
from typing import Any, Callable, Iterator
from urllib.parse import urlsplit

from .logging_setup import get_logger

logger = get_logger()

STANDARD_ADRESSE = "http://localhost:11434"
DOWNLOAD_SEITE = "https://ollama.com/download"
BIBLIOTHEK = "https://ollama.com/library"

# Empfohlene Modelle (Stand Herbst 2026, alle aus https://ollama.com/library). Groesse = Download.
# "werkzeuge": kann Werkzeuge benutzen (Dateien, Web ...), "sieht_bilder": versteht Bilder.
EMPFOHLEN = [
    {"id": "qwen3.5:4b", "name": "Qwen 3.5 (4B)", "kurz": "qwen",
     "info": "der Standard \u2013 klein, schnell, gut in Deutsch, sieht Bilder", "groesse": "3,4 GB",
     "ram": "ab 8 GB Arbeitsspeicher", "werkzeuge": True, "sieht_bilder": True, "denkt": True},
    {"id": "qwen3.5:9b", "name": "Qwen 3.5 (9B)", "kurz": "qwen-gross",
     "info": "deutlich st\u00e4rker \u2013 f\u00fcr PCs mit 16 GB oder Grafikkarte", "groesse": "6,6 GB",
     "ram": "ab 16 GB Arbeitsspeicher", "werkzeuge": True, "sieht_bilder": True, "denkt": True},
    {"id": "gemma4:e4b", "name": "Gemma 4 (E4B)", "kurz": "gemma",
     "info": "von Google \u2013 sehr gut in Deutsch, sieht Bilder", "groesse": "6,6 GB",
     "ram": "ab 16 GB Arbeitsspeicher", "werkzeuge": True, "sieht_bilder": True, "denkt": True},
    {"id": "qwen3:4b", "name": "Qwen 3 (4B)", "kurz": "qwen3",
     "info": "f\u00fcr schw\u00e4chere PCs \u2013 ohne Bilder", "groesse": "2,5 GB",
     "ram": "ab 8 GB Arbeitsspeicher", "werkzeuge": True, "sieht_bilder": False, "denkt": True},
]
STANDARD_MODELL = EMPFOHLEN[0]["id"]

# Bildformate, die Ollama annimmt (GIF nicht).
_BILD_TYPEN = ("image/png", "image/jpeg", "image/jpg", "image/webp")

VERBINDEN_TIMEOUT = 5.0      # localhost antwortet sofort - sonst laeuft Ollama nicht
LESE_TIMEOUT = 600.0         # auf dem PC kann das Lesen langer Anfragen dauern (ohne Grafikkarte)
STATUS_TIMEOUT = 3.0

# ---------------------------------------------------------------------------
# Meldungen (fuer Menschen)
# ---------------------------------------------------------------------------
NICHT_ERREICHBAR = (
    "Ollama antwortet nicht ({adresse}). Ist Ollama gestartet? Unter Windows: im Startmen\u00fc "
    "\u201eOllama\u201c \u00f6ffnen (das Lama-Symbol erscheint unten rechts). Noch nicht installiert? "
    "Kostenlos herunterladen: " + DOWNLOAD_SEITE + " \u2013 oder in \u201eGehirn & Schl\u00fcssel\u201c."
)
MODELL_FEHLT = (
    "Das Modell \u201e{modell}\u201c ist noch nicht heruntergeladen. Lade es in \u201eGehirn & "
    "Schl\u00fcssel\u201c herunter oder tippe: /ollama laden {modell}"
)
OHNE_WERKZEUGE = (
    "[Hinweis: Das Modell \u201e{modell}\u201c kann keine Werkzeuge benutzen \u2013 ich kann damit keine "
    "Dateien lesen, nicht im Web suchen und nichts am PC tun, nur antworten. Besser geeignet: "
    "{empfohlen} (/ollama laden {empfohlen}).]\n"
)
SIEHT_NICHTS = "dieses Modell kann keine Bilder sehen"


class OllamaFehler(Exception):
    """Fehler beim Gespraech mit Ollama - mit Art fuer verstaendliche Meldungen.

    art: "offline" (laeuft nicht), "modell_fehlt", "keine_werkzeuge", "kein_denken", "adresse",
         "abgebrochen", "http" (sonstiger Fehler vom Server)."""

    def __init__(self, text: str, art: str = "http", status_code: int | None = None):
        super().__init__(text)
        self.art = art
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Adresse
# ---------------------------------------------------------------------------
def pruefe_adresse(text: Any) -> str:
    """Gueltige Adresse (ohne "/" am Ende) - oder ValueError mit verstaendlicher Meldung.

    Nur http/https, mit Rechnername, ohne Benutzer/Passwort, Abfrage oder Anker. Als Pfad nur
    nichts oder "/v1" (OpenAI-kompatibler Server wie LM Studio)."""
    roh = str(text or "").strip()
    if not roh:
        return STANDARD_ADRESSE
    if len(roh) > 200 or any(c.isspace() or ord(c) < 32 for c in roh):
        raise ValueError("Die Adresse ist ungueltig (keine Leerzeichen, hoechstens 200 Zeichen).")
    if "://" not in roh:
        roh = "http://" + roh
    teile = urlsplit(roh)
    if teile.scheme.lower() not in ("http", "https"):
        raise ValueError("Die Adresse muss mit http:// oder https:// beginnen.")
    if teile.username or teile.password or "@" in teile.netloc:
        raise ValueError("Die Adresse darf keinen Benutzernamen oder kein Passwort enthalten.")
    if not teile.hostname:
        raise ValueError("In der Adresse fehlt der Rechner (z.B. http://localhost:11434).")
    try:
        teile.port  # noqa: B018 - wirft bei ungueltigem Port
    except ValueError as exc:
        raise ValueError("Der Port in der Adresse ist ungueltig.") from exc
    if teile.query or teile.fragment:
        raise ValueError("Die Adresse darf kein ? oder # enthalten.")
    pfad = teile.path.rstrip("/")
    if pfad not in ("", "/v1"):
        raise ValueError("Die Adresse darf keinen Pfad haben (ausser /v1 fuer OpenAI-kompatible Server).")
    return f"{teile.scheme.lower()}://{teile.netloc}{pfad}"


def ist_openai_adresse(adresse: str) -> bool:
    """'.../v1' = OpenAI-kompatibler Server (LM Studio & Co.) statt Ollamas eigener Schnittstelle."""
    return (adresse or "").rstrip("/").endswith("/v1")


def adresse_aus(config: Any) -> str:
    """Adresse aus den Einstellungen - ungueltig = Standard (die KI soll nie irgendwohin senden)."""
    try:
        return pruefe_adresse(getattr(getattr(config, "ollama", None), "adresse", ""))
    except ValueError:
        logger.warning("Ungueltige Ollama-Adresse in den Einstellungen - nutze %s", STANDARD_ADRESSE)
        return STANDARD_ADRESSE


def _ist_lokal(adresse: str) -> bool:
    host = (urlsplit(adresse).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")


# ---------------------------------------------------------------------------
# HTTP (austauschbar fuer Tests: http(methode, url, daten, timeout) -> Antwort)
# ---------------------------------------------------------------------------
# Offene Verbindungen einer laufenden Anfrage (je Thread gesammelt, siehe OllamaClient.abbrechen):
# so laesst sich auch eine Anfrage abbrechen, auf deren Antwort Ollama noch rechnet.
_sammler = threading.local()


def _http_standard(methode: str, url: str, daten: dict | None, timeout: float) -> Any:
    """Direkte Verbindung (ohne Proxy: eine Proxy-Einstellung von Windows soll Anfragen an den
    eigenen PC nicht umleiten). Fehler wie bei urllib (HTTPError, URLError/OSError)."""
    import http.client

    teile = urlsplit(url)
    body = json.dumps(daten).encode("utf-8") if daten is not None else None
    if teile.scheme == "https":
        import ssl

        conn: Any = http.client.HTTPSConnection(teile.hostname, teile.port, timeout=timeout,
                                                context=ssl.create_default_context())
    else:
        conn = http.client.HTTPConnection(teile.hostname, teile.port, timeout=timeout)
    liste = getattr(_sammler, "liste", None)
    if liste is not None:
        liste.append(conn)
    try:
        conn.request(methode, teile.path or "/", body=body,
                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        antwort = conn.getresponse()
    except (OSError, http.client.HTTPException) as exc:
        conn.close()
        raise urllib.error.URLError(exc) from exc
    if antwort.status >= 400:
        raise urllib.error.HTTPError(url, antwort.status, antwort.reason, antwort.headers, antwort)
    return antwort


def _server_meldung(roh: bytes) -> str:
    try:
        data = json.loads(roh.decode("utf-8", errors="replace") or "{}")
    except ValueError:
        return roh.decode("utf-8", errors="replace")[:300]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            err = err.get("message")
        if err:
            return str(err)[:300]
    return ""


def fehler_art(status: int | None, meldung: str) -> str:
    text = (meldung or "").lower()
    if "does not support tools" in text:
        return "keine_werkzeuge"
    if "does not support thinking" in text or "think value" in text:
        return "kein_denken"
    if status == 404 or ("not found" in text and "model" in text) or "try pulling" in text:
        return "modell_fehlt"
    return "http"


def _uebersetze(exc: Exception, adresse: str) -> OllamaFehler:
    if isinstance(exc, OllamaFehler):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        try:
            meldung = _server_meldung(exc.read())
        except Exception:  # noqa: BLE001
            meldung = ""
        meldung = meldung or str(exc.reason or exc)
        return OllamaFehler(meldung, fehler_art(exc.code, meldung), exc.code)
    if isinstance(exc, (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError, OSError)):
        return OllamaFehler(NICHT_ERREICHBAR.format(adresse=adresse), "offline")
    return OllamaFehler(str(exc))


class Dienst:
    """Spricht mit einem Ollama-Server. `http` ist fuer Tests austauschbar."""

    def __init__(self, adresse: str = STANDARD_ADRESSE, http: Callable | None = None):
        self.adresse = (adresse or STANDARD_ADRESSE).rstrip("/")
        self._http = http or _http_standard

    def _url(self, pfad: str) -> str:
        return self.adresse + pfad

    def anfrage(self, methode: str, pfad: str, daten: dict | None = None,
                timeout: float = STATUS_TIMEOUT) -> Any:
        """Antwort-Objekt (mit read/readline/close) - oder OllamaFehler."""
        try:
            return self._http(methode, self._url(pfad), daten, timeout)
        except Exception as exc:  # noqa: BLE001
            raise _uebersetze(exc, self.adresse) from exc

    def json(self, methode: str, pfad: str, daten: dict | None = None, timeout: float = STATUS_TIMEOUT) -> Any:
        antwort = self.anfrage(methode, pfad, daten, timeout)
        try:
            roh = antwort.read()
        except Exception as exc:  # noqa: BLE001
            raise _uebersetze(exc, self.adresse) from exc
        finally:
            _schliessen(antwort)
        try:
            return json.loads(roh.decode("utf-8", errors="replace") or "{}")
        except ValueError as exc:
            raise OllamaFehler("Unerwartete Antwort von Ollama.") from exc

    # -- Abfragen --------------------------------------------------------
    def version(self) -> str:
        data = self.json("GET", "/api/version")
        return str(data.get("version") or "") if isinstance(data, dict) else ""

    def modelle(self) -> list[dict]:
        """Heruntergeladene Modelle: [{"name", "groesse" (Bytes), "parameter", "familie"}]."""
        data = self.json("GET", "/api/tags")
        out = []
        for m in (data.get("models") if isinstance(data, dict) else None) or []:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name") or m.get("model") or "").strip()
            if not name or not gueltiger_name(name):
                continue
            details = m.get("details") if isinstance(m.get("details"), dict) else {}
            out.append({"name": name, "groesse": _int(m.get("size")),
                        "parameter": str(details.get("parameter_size") or "")[:20],
                        "familie": str(details.get("family") or "")[:40]})
        out.sort(key=lambda x: x["name"])
        return out

    def faehigkeiten(self, modell: str) -> set[str]:
        """Was das Modell kann, z.B. {"completion", "tools", "vision", "thinking"}."""
        data = self.json("POST", "/api/show", {"model": modell}, timeout=10.0)
        caps = data.get("capabilities") if isinstance(data, dict) else None
        return {str(c).strip().lower() for c in caps or [] if str(c).strip()}

    def laden(self, modell: str, fortschritt: Callable[[dict], None] | None = None,
              abbruch: threading.Event | None = None, merke: Callable[[Any], None] | None = None) -> None:
        """Laedt ein Modell herunter. fortschritt(ereignis) je Schritt (siehe pull_ereignis).
        Abbrechen: abbruch setzen (die Verbindung wird dann geschlossen - Ollama merkt sich das
        schon Geladene, ein neuer Versuch macht dort weiter). merke(antwort) bekommt die offene
        Verbindung, damit ein anderer Thread sie sofort schliessen kann."""
        if not gueltiger_name(modell):
            raise OllamaFehler(f"\u201e{modell}\u201c ist kein gueltiger Modellname.", "adresse")
        antwort = self.anfrage("POST", "/api/pull", {"model": modell, "stream": True}, timeout=LESE_TIMEOUT)
        if merke:
            merke(antwort)
        try:
            for zeile in _zeilen(antwort):
                if abbruch is not None and abbruch.is_set():
                    raise OllamaFehler("Herunterladen abgebrochen.", "abgebrochen")
                ereignis = pull_ereignis(zeile)
                if ereignis is None:
                    continue
                if ereignis.get("fehler"):
                    raise OllamaFehler(ereignis["fehler"], fehler_art(None, ereignis["fehler"]))
                if fortschritt:
                    fortschritt(ereignis)
                if ereignis.get("fertig"):
                    return
        except OllamaFehler:
            raise
        except Exception as exc:  # noqa: BLE001
            if abbruch is not None and abbruch.is_set():
                raise OllamaFehler("Herunterladen abgebrochen.", "abgebrochen") from exc
            raise _uebersetze(exc, self.adresse) from exc
        finally:
            _schliessen(antwort)
        if abbruch is not None and abbruch.is_set():
            raise OllamaFehler("Herunterladen abgebrochen.", "abgebrochen")
        raise OllamaFehler("Das Herunterladen wurde unterbrochen - bitte nochmal versuchen.")


def pull_ereignis(zeile: Any) -> dict | None:
    """Eine Zeile von /api/pull -> {"status", "erledigt", "gesamt", "prozent", "fertig", "fehler"}."""
    if isinstance(zeile, (bytes, bytearray)):
        zeile = zeile.decode("utf-8", errors="replace")
    if isinstance(zeile, str):
        zeile = zeile.strip()
        if not zeile:
            return None
        try:
            data = json.loads(zeile)
        except ValueError:
            return None
    else:
        data = zeile
    if not isinstance(data, dict):
        return None
    if data.get("error"):
        return {"status": "fehler", "fehler": str(data["error"])[:300], "fertig": False,
                "erledigt": 0, "gesamt": 0, "prozent": None}
    status = str(data.get("status") or "")[:120]
    gesamt, erledigt = _int(data.get("total")), _int(data.get("completed"))
    prozent = None
    if gesamt > 0:
        prozent = max(0.0, min(100.0, erledigt * 100.0 / gesamt))
    return {"status": status, "erledigt": erledigt, "gesamt": gesamt, "prozent": prozent,
            "fertig": status == "success", "fehler": ""}


def status_text(status: str) -> str:
    """Englischen Pull-Status in Deutsch (fuer die Anzeige)."""
    s = (status or "").lower()
    if s.startswith("pulling manifest"):
        return "Bereite vor \u2026"
    if s.startswith("pulling") or s.startswith("downloading"):
        return "Lade herunter \u2026"
    if s.startswith("verifying"):
        return "Pr\u00fcfe die Datei \u2026"
    if s.startswith("writing") or s.startswith("removing"):
        return "Fast fertig \u2026"
    if s == "success":
        return "Fertig"
    return status or "\u2026"


def groesse_text(bytes_: int) -> str:
    if bytes_ <= 0:
        return ""
    gb = bytes_ / 1_000_000_000
    if gb >= 1:
        return f"{gb:.1f} GB".replace(".", ",")
    return f"{bytes_ / 1_000_000:.0f} MB"


# Modellnamen wie "qwen3.5:4b", "library/llama3.2", "hf.co/user/repo:Q4_K_M"
def gueltiger_name(name: Any) -> bool:
    import re

    return bool(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-/:]{0,150}", name)
                and ".." not in name)


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _zeilen(antwort: Any) -> Iterator[bytes]:
    while True:
        zeile = antwort.readline()
        if not zeile:
            return
        yield zeile


def _schliessen(antwort: Any) -> None:
    """Verbindung sofort schliessen - auch wenn ein anderer Thread gerade darauf wartet."""
    if antwort is None:
        return
    try:
        sock = antwort.fp.raw._sock  # http.client.HTTPResponse
        sock.shutdown(socket.SHUT_RDWR)
    except Exception:  # noqa: BLE001 - kein echtes Socket (Tests) oder schon zu
        pass
    try:
        antwort.close()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Status fuer App und Terminal
# ---------------------------------------------------------------------------
def installiert_auf_pc() -> bool:
    """Ist das Ollama-Programm auf diesem PC installiert (auch wenn es gerade nicht laeuft)?"""
    if shutil.which("ollama"):
        return True
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        for teil in (("Programs", "Ollama", "ollama.exe"), ("Programs", "Ollama", "ollama app.exe")):
            if local and os.path.isfile(os.path.join(local, *teil)):
                return True
    elif sys.platform == "darwin":
        return os.path.isdir("/Applications/Ollama.app")
    return False


def status(config: Any, http: Callable | None = None) -> dict:
    """{"laeuft", "version", "installiert", "adresse", "modelle": [...], "modell", "modell_da",
        "empfohlen": [...], "fehler"} - nie eine Ausnahme."""
    adresse = adresse_aus(config)
    dienst = Dienst(adresse, http)
    aktiv = str(getattr(getattr(config, "ollama", None), "model", "") or "")
    out: dict[str, Any] = {"laeuft": False, "version": "", "installiert": None, "adresse": adresse,
                           "openai": ist_openai_adresse(adresse), "modelle": [], "modell": aktiv,
                           "modell_da": False, "fehler": "", "download": DOWNLOAD_SEITE}
    try:
        if out["openai"]:
            data = dienst.json("GET", "/models")
            namen = [str(m.get("id")) for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")]
            out["modelle"] = [{"name": n, "groesse": 0, "parameter": "", "familie": ""}
                              for n in namen if gueltiger_name(n)]
        else:
            out["version"] = dienst.version()
            out["modelle"] = dienst.modelle()
        out["laeuft"] = True
    except OllamaFehler as exc:
        out["fehler"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        out["fehler"] = str(exc)[:300]
    if out["laeuft"]:
        out["installiert"] = True
    elif http is None and _ist_lokal(adresse):
        out["installiert"] = installiert_auf_pc()
    namen = {m["name"] for m in out["modelle"]}
    out["modell_da"] = ist_installiert(aktiv, namen)
    out["empfohlen"] = [dict(m, installiert=ist_installiert(m["id"], namen)) for m in EMPFOHLEN]
    return out


def ist_installiert(modell: str, namen: set[str] | list[str]) -> bool:
    """"qwen3.5:4b" in {"qwen3.5:4b"}; "llama3.2" = "llama3.2:latest"."""
    if not modell:
        return False
    namen = set(namen)
    if modell in namen:
        return True
    if ":" not in modell and f"{modell}:latest" in namen:
        return True
    return modell.endswith(":latest") and modell[: -len(":latest")] in namen


def empfohlen_info(modell: str) -> dict | None:
    return next((m for m in EMPFOHLEN if m["id"] == modell), None)


def finde_empfohlen(wort: str) -> str | None:
    """'qwen', 'gemma', 'Qwen 3.5 (9B)' -> Modell-ID der Empfehlung (sonst None)."""
    w = (wort or "").strip().lower()
    for m in EMPFOHLEN:
        if w in (m["id"], m["kurz"], m["name"].lower()):
            return m["id"]
    return None


def starten() -> tuple[bool, str]:
    """Das installierte Ollama starten (nur das Programm selbst - nie ein Installer)."""
    import subprocess

    try:
        if sys.platform == "win32":
            local = os.environ.get("LOCALAPPDATA", "")
            app = os.path.join(local, "Programs", "Ollama", "ollama app.exe") if local else ""
            if app and os.path.isfile(app):
                os.startfile(app)  # noqa: S606 - das Ollama-Programm des Menschen
                return True, "Ollama wird gestartet \u2026"
            exe = shutil.which("ollama")
            if exe:
                subprocess.Popen([exe, "serve"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, "Ollama wird gestartet \u2026"
        elif sys.platform == "darwin" and os.path.isdir("/Applications/Ollama.app"):
            subprocess.Popen(["open", "-a", "Ollama"])
            return True, "Ollama wird gestartet \u2026"
        else:
            exe = shutil.which("ollama")
            if exe:
                subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                return True, "Ollama wird gestartet \u2026"
    except Exception as exc:  # noqa: BLE001
        return False, f"Ollama liess sich nicht starten ({exc})."
    return False, "Ollama ist auf diesem PC nicht installiert - kostenlos unter " + DOWNLOAD_SEITE


# ---------------------------------------------------------------------------
# Herunterladen im Hintergrund (eins zur Zeit) - fuer App und Terminal
# ---------------------------------------------------------------------------
class Lader:
    """Laedt hoechstens ein Modell zur Zeit, mit Fortschritt und Abbrechen."""

    def __init__(self):
        self._lock = threading.Lock()
        self.modell = ""
        self.letztes: dict = {}
        self._abbruch = threading.Event()
        self._antwort: Any = None
        self._thread: threading.Thread | None = None

    @property
    def laeuft(self) -> bool:
        return bool(self.modell)

    def zustand(self) -> dict | None:
        if not self.modell:
            return None
        return {"model": self.modell, **{k: self.letztes.get(k) for k in ("status", "prozent", "erledigt", "gesamt")}}

    def starten(self, dienst: Dienst, modell: str, melde: Callable[[dict], None],
                hintergrund: bool = True) -> tuple[bool, str]:
        """melde(ereignis) bekommt {"model", "status", "text", "prozent", "erledigt", "gesamt",
        "fertig", "ok", "fehler", "abgebrochen"} - am Ende genau einmal mit fertig=True."""
        if not gueltiger_name(modell):
            return False, f"\u201e{modell}\u201c ist kein gueltiger Modellname."
        with self._lock:
            if self.modell:
                return False, f"Es wird schon \u201e{self.modell}\u201c heruntergeladen - bitte warten oder abbrechen."
            self.modell = modell
            self.letztes = {}
            self._abbruch = threading.Event()
            abbruch = self._abbruch

        def merke(antwort: Any) -> None:
            self._antwort = antwort
            if abbruch.is_set():
                _schliessen(antwort)

        def schritt(ev: dict) -> None:
            self.letztes = ev
            melde({"model": modell, "status": ev.get("status", ""), "text": status_text(ev.get("status", "")),
                   "prozent": ev.get("prozent"), "erledigt": ev.get("erledigt", 0), "gesamt": ev.get("gesamt", 0),
                   "fertig": False})

        def arbeit() -> None:
            ende = {"model": modell, "fertig": True, "ok": False, "fehler": "", "abgebrochen": False}
            letzte, letzter_status = 0.0, None
            try:
                def gedrosselt(ev: dict) -> None:
                    # hoechstens 4 Meldungen je Sekunde - ausser bei einem neuen Schritt
                    nonlocal letzte, letzter_status
                    jetzt = time.monotonic()
                    if ev.get("fertig") or jetzt - letzte >= 0.25 or ev.get("status") != letzter_status:
                        letzte, letzter_status = jetzt, ev.get("status")
                        schritt(ev)
                    else:
                        self.letztes = ev

                dienst.laden(modell, gedrosselt, abbruch, merke)
                ende.update(ok=True, text=f"\u201e{modell}\u201c ist heruntergeladen.")
            except OllamaFehler as exc:
                if exc.art == "abgebrochen" or abbruch.is_set():
                    ende.update(abgebrochen=True, text="Herunterladen abgebrochen.")
                elif exc.art == "modell_fehlt" or "file does not exist" in str(exc).lower():
                    ende.update(fehler=f"Ein Modell \u201e{modell}\u201c gibt es bei Ollama nicht. Namen findest "
                                       f"du unter {BIBLIOTHEK}.")
                else:
                    ende.update(fehler=str(exc))
            except Exception as exc:  # noqa: BLE001
                ende.update(fehler=str(exc)[:300])
            finally:
                with self._lock:
                    self.modell = ""
                    self._antwort = None
            melde(ende)

        if hintergrund:
            self._thread = threading.Thread(target=arbeit, name="ollama-laden", daemon=True)
            self._thread.start()
        else:
            arbeit()
        return True, f"Lade \u201e{modell}\u201c herunter \u2026"

    def abbrechen(self) -> bool:
        with self._lock:
            if not self.modell:
                return False
            self._abbruch.set()
            antwort = self._antwort
        _schliessen(antwort)
        return True


# ---------------------------------------------------------------------------
# OllamaClient: das Stueck "openai"-Bibliothek, das der Provider braucht -> /api/chat
# ---------------------------------------------------------------------------
class OllamaClient:
    """client.chat.completions.create(**kwargs) wie bei openai - spricht aber /api/chat.

    Verstanden werden: model, messages (OpenAI-Format), tools, tool_choice ("none" = ohne
    Werkzeuge), max_tokens, temperature, stream, extra_body={"think": bool}. Die Kontext-Laenge
    (num_ctx) kommt aus den Einstellungen und bleibt immer gleich (sonst laedt Ollama neu)."""

    def __init__(self, adresse: str, kontext: int = 16384, http: Callable | None = None,
                 timeout: float = LESE_TIMEOUT):
        self.dienst = Dienst(adresse, http)
        self.kontext = max(2048, int(kontext or 16384))
        self.timeout = timeout
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self._lock = threading.Lock()
        self._laufend: list[list] = []  # Verbindungen der gerade laufenden Anfragen

    def abbrechen(self) -> None:
        """Alle laufenden Anfragen sofort beenden (Stopp-Knopf) - auch solche, auf deren erste
        Antwort Ollama noch rechnet (Modell laden, langen Text lesen)."""
        with self._lock:
            conns = [c for liste in self._laufend for c in liste]
        for conn in conns:
            sock = getattr(conn, "sock", None)
            try:
                if sock is not None:
                    sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def anfrage_aus(self, kwargs: dict) -> dict:
        body: dict[str, Any] = {"model": kwargs["model"], "messages": nachrichten_fuer_ollama(kwargs["messages"]),
                                "stream": bool(kwargs.get("stream", False))}
        tools = kwargs.get("tools")
        if tools and kwargs.get("tool_choice", "auto") != "none":
            body["tools"] = tools
        options: dict[str, Any] = {"num_ctx": self.kontext}
        if kwargs.get("max_tokens"):
            options["num_predict"] = int(kwargs["max_tokens"])
        if kwargs.get("temperature") is not None:
            options["temperature"] = kwargs["temperature"]
        body["options"] = options
        extra = kwargs.get("extra_body") or {}
        if "think" in extra:
            body["think"] = extra["think"]
        return body

    def create(self, **kwargs: Any) -> Any:
        body = self.anfrage_aus(kwargs)
        timeout = float(kwargs.get("timeout") or self.timeout)
        liste: list = []
        with self._lock:
            self._laufend.append(liste)
        _sammler.liste = liste
        try:
            antwort = self.dienst.anfrage("POST", "/api/chat", body, timeout=timeout)
        finally:
            _sammler.liste = None
            with self._lock:
                self._laufend.remove(liste)
        if body["stream"]:
            return _ChatStrom(antwort, self.dienst.adresse)
        try:
            roh = antwort.read()
        except Exception as exc:  # noqa: BLE001
            raise _uebersetze(exc, self.dienst.adresse) from exc
        finally:
            _schliessen(antwort)
        try:
            data = json.loads(roh.decode("utf-8", errors="replace") or "{}")
        except ValueError as exc:
            raise OllamaFehler("Unerwartete Antwort von Ollama.") from exc
        if isinstance(data, dict) and data.get("error"):
            meldung = str(data["error"])
            raise OllamaFehler(meldung, fehler_art(None, meldung))
        msg = data.get("message") or {}
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=msg.get("content") or ""),
                                     finish_reason=_finish(data))],
            usage=_usage(data),
        )


class _ChatStrom:
    """Gestreamte Antwort von /api/chat als OpenAI-artige Teile (choices[0].delta ...)."""

    def __init__(self, antwort: Any, adresse: str):
        self._antwort = antwort
        self._adresse = adresse
        self._tool_index = 0

    def close(self) -> None:
        _schliessen(self._antwort)

    def __iter__(self) -> Iterator[Any]:
        try:
            for zeile in _zeilen(self._antwort):
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    data = json.loads(zeile.decode("utf-8", errors="replace"))
                except ValueError:
                    continue
                if not isinstance(data, dict):
                    continue
                if data.get("error"):
                    meldung = str(data["error"])
                    raise OllamaFehler(meldung, fehler_art(None, meldung))
                yield from self._teile(data)
        except OllamaFehler:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _uebersetze(exc, self._adresse) from exc
        finally:
            self.close()

    def _teile(self, data: dict) -> Iterator[Any]:
        msg = data.get("message") or {}
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if not isinstance(args, str):
                args = json.dumps(args if args is not None else {}, ensure_ascii=False)
            calls.append(SimpleNamespace(
                index=self._tool_index, id=str(tc.get("id") or f"call_{self._tool_index}_{int(time.time() * 1000)}"),
                function=SimpleNamespace(name=fn.get("name") or "", arguments=args)))
            self._tool_index += 1
        delta = SimpleNamespace(content=msg.get("content") or None,
                                reasoning_content=msg.get("thinking") or None,
                                tool_calls=calls or None)
        fertig = bool(data.get("done"))
        if delta.content or delta.reasoning_content or calls or fertig:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=_finish(data) if fertig else None)],
                                  usage=None)
        if fertig:
            yield SimpleNamespace(choices=[], usage=_usage(data))


def _finish(data: dict) -> str:
    grund = str(data.get("done_reason") or "stop")
    return "length" if grund == "length" else "stop"


def _usage(data: dict) -> Any:
    return SimpleNamespace(prompt_tokens=_int(data.get("prompt_eval_count")),
                           completion_tokens=_int(data.get("eval_count")),
                           prompt_cache_hit_tokens=None, prompt_cache_miss_tokens=None)


def nachrichten_fuer_ollama(messages: list[dict]) -> list[dict]:
    """OpenAI-Format -> Ollama /api/chat. Werkzeug-Argumente als Objekt, Bilder als Base64-Liste,
    Denk-Text als "thinking", Werkzeug-Antworten mit Namen des Werkzeugs."""
    namen: dict[str, str] = {}
    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        neu: dict[str, Any] = {"role": role}
        text, bilder = _text_und_bilder(m.get("content"))
        neu["content"] = text
        if bilder:
            neu["images"] = bilder
        if role == "assistant":
            if m.get("reasoning_content"):
                neu["thinking"] = m["reasoning_content"]
            calls = []
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                namen[tc.get("id", "")] = fn.get("name", "")
                calls.append({"id": tc.get("id", ""), "function": {"name": fn.get("name", ""), "arguments": args}})
            if calls:
                neu["tool_calls"] = calls
        elif role == "tool":
            tid = m.get("tool_call_id", "")
            neu["tool_call_id"] = tid
            if namen.get(tid):
                neu["tool_name"] = namen[tid]
        out.append(neu)
    return out


def _text_und_bilder(content: Any) -> tuple[str, list[str]]:
    if not isinstance(content, list):
        return (str(content or ""), [])
    texte, bilder = [], []
    for p in content:
        kind = p.get("type") if isinstance(p, dict) else None
        if kind == "text":
            texte.append(str(p.get("text") or ""))
        elif kind == "image_url":
            url = str((p.get("image_url") or {}).get("url") or "")
            kopf, _, daten = url.partition(";base64,")
            mime = kopf[len("data:"):].lower() if kopf.startswith("data:") else ""
            if daten and mime in _BILD_TYPEN:
                bilder.append(daten)
            else:
                name = getattr(p, "bild_name", "") or ""
                texte.append(f"[Bild{': ' + name if name else ''} - dieses Bildformat kann Ollama nicht lesen]")
    return ("\n".join(t for t in texte if t), bilder)
