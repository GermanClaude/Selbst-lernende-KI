"""Anrufe ueber Vonage (developer.vonage.com) - die Alternative zu Bland ohne Kreditkarte.

Vonage laesst sich per PayPal oder Ueberweisung aufladen; der kostenlose Testzugang ruft schon die Nummer
an, die du bei der Anmeldung angegeben hast. Anders als Bland hat Vonage keine eigene Gespraechs-KI:
Vonage SPRICHT Novas Text (deutsche Stimme) und HOERT deine Antwort (deutsche Spracherkennung).

Zwei Arten:
- Ansage (geht immer): Nova sagt ihr Anliegen zweimal und bittet dich, in der App/auf Telegram zu antworten.
- Frage mit Antwort: Nova fragt, du antwortest am Telefon, Nova bekommt deine Antwort als Text. Dafuer
  braucht Vonage eine oeffentliche Adresse auf deinem PC (Rueckkanal). Nova startet sie selbst mit
  cloudflared (kostenlos, ohne Konto: winget install --id Cloudflare.cloudflared) - oder du traegst eine
  eigene ein (VONAGE_WEBHOOK_URL + VONAGE_WEBHOOK_PORT).

Anmeldung: Vonage will ein JWT (RS256), unterschrieben mit dem privaten Schluessel deiner Vonage-"Application".
Das macht dieses Modul selbst (reines Python, keine Zusatz-Bibliothek). Der Schluessel liegt nur lokal in
data/vonage_private.key und geht nie an die KI.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from .anruf import AnrufFehler

API = "https://api.nexmo.com/v1"
TEST_ABSENDER = "123456789"   # Vonage-Testzugang: Anrufer-Kennung fuer Anrufe an die eigene Anmelde-Nummer
_FERTIG = {"completed", "busy", "cancelled", "failed", "rejected", "timeout", "unanswered"}
_TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


# ---------------------------------------------------------------- privater Schluessel + JWT (RS256)
def _der(daten: bytes, pos: int) -> tuple[int, bytes, int]:
    """Ein DER-Element lesen -> (Tag, Inhalt, Position danach)."""
    tag = daten[pos]
    laenge = daten[pos + 1]
    pos += 2
    if laenge & 0x80:
        n = laenge & 0x7F
        laenge = int.from_bytes(daten[pos:pos + n], "big")
        pos += n
    return tag, daten[pos:pos + laenge], pos + laenge


def schluessel_laden(pem: str) -> tuple[int, int]:
    """PEM (PKCS#8 'BEGIN PRIVATE KEY' wie von Vonage, oder PKCS#1 'BEGIN RSA PRIVATE KEY') -> (n, d)."""
    text = str(pem or "")
    if "PRIVATE KEY-----" not in text or "ENCRYPTED" in text:
        raise AnrufFehler("Das ist keine (unverschluesselte) private.key-Datei von Vonage.")
    b64 = re.sub(r"-----[^-]+-----|\s", "", text)
    try:
        daten = base64.b64decode(b64)
        tag, seq, _ = _der(daten, 0)
        _, _, pos = _der(seq, 0)                         # Version (0)
        if seq[pos] == 0x30:                             # PKCS#8: Algorithmus, dann der PKCS#1-Schluessel
            _, _, pos = _der(seq, pos)
            _, innen, _ = _der(seq, pos)
            tag, seq, _ = _der(innen, 0)
            _, _, pos = _der(seq, 0)
        zahlen = []
        for _ in range(3):                               # n, e, d
            t, wert, pos = _der(seq, pos)
            if t != 0x02:
                raise ValueError("kein INTEGER")
            zahlen.append(int.from_bytes(wert, "big"))
    except (ValueError, IndexError) as exc:
        raise AnrufFehler("Die private.key-Datei liess sich nicht lesen (beschaedigt?).") from exc
    n, _e, d = zahlen
    if n.bit_length() < 1024 or not d:
        raise AnrufFehler("Der Schluessel ist zu kurz oder ungueltig.")
    return n, d


# DigestInfo-Vorspann fuer SHA-256 (RFC 8017, EMSA-PKCS1-v1_5)
_SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def rs256_signieren(daten: bytes, n: int, d: int) -> bytes:
    k = (n.bit_length() + 7) // 8
    t = _SHA256_INFO + hashlib.sha256(daten).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def jwt_erstellen(app_id: str, pem: str, jetzt: float | None = None, gueltig: int = 900) -> str:
    n, d = schluessel_laden(pem)
    jetzt = int(time.time() if jetzt is None else jetzt)
    kopf = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    inhalt = _b64url(json.dumps({"application_id": app_id, "iat": jetzt, "exp": jetzt + gueltig,
                                 "jti": str(uuid.uuid4())}, separators=(",", ":")).encode())
    signatur = rs256_signieren(f"{kopf}.{inhalt}".encode("ascii"), n, d)
    return f"{kopf}.{inhalt}.{_b64url(signatur)}"


# ---------------------------------------------------------------- Einstellungen
def schluessel_pfad(root) -> Path:
    return Path(root) / "data" / "vonage_private.key"


def schluessel_speichern(root, pem: str) -> None:
    schluessel_laden(pem)                                # vorher pruefen
    pfad = schluessel_pfad(root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(pem.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(pfad, 0o600)
    except OSError:
        pass


def eingerichtet(root) -> bool:
    return bool(os.environ.get("VONAGE_APP_ID", "").strip()) and root is not None and schluessel_pfad(root).exists()


def nur_ziffern(nummer: str) -> str:
    """'+491711234567' -> '491711234567' (so zeigt Vonage die Nummern)."""
    return re.sub(r"\D", "", str(nummer or ""))


# ---------------------------------------------------------------- Gespraechsablauf (NCCO)
DANKE = "Danke, ich hab's. Ich kuemmere mich drum. Bis dann!"
NOCHMAL = "Ich habe dich leider nicht verstanden. Nochmal: "
SPAETER = "Okay, dann schreib mir einfach in der App oder auf Telegram. Bis dann!"


def _sprich(text: str, loop: int = 1, barge_in: bool = False) -> dict:
    aktion = {"action": "talk", "text": text[:1500], "language": "de-DE", "loop": loop}
    if barge_in:
        aktion["bargeIn"] = True
    return aktion


def _hoer_zu(url: str) -> dict:
    return {"action": "input", "type": ["speech"], "eventUrl": [url], "eventMethod": "POST",
            "speech": {"language": "de-DE", "endOnSilence": 1.5, "startTimeout": 8, "maxDuration": 30}}


def ncco_bauen(anliegen: str, name: str = "Nova", antwort_url: str | None = None) -> list[dict]:
    anliegen = re.sub(r"\s+", " ", (anliegen or "").strip())[:1000]
    hallo = f"Hallo, hier ist {name or 'Nova'}, deine KI vom PC. "
    if antwort_url:   # Frage mit Antwort: sprechen, dann zuhoeren (du darfst reinreden)
        return [_sprich(hallo + anliegen, barge_in=True), _hoer_zu(antwort_url)]
    return [_sprich(hallo + anliegen + " Ich wiederhole: " + anliegen +
                    " Antworte mir einfach in der App oder auf Telegram. Bis dann!")]


# ---------------------------------------------------------------- Rueckkanal: Vonage -> dein PC
@dataclass
class Rueckkanal:
    """Kleiner Webserver nur fuer die Dauer eines Anrufs. Der Pfad enthaelt ein Zufalls-Geheimnis,
    damit niemand ausser Vonage etwas einwerfen kann. Er nimmt nur gesprochenen Text an."""
    frage: str
    port: int = 0
    oeffentlich: str = ""                  # z.B. https://abc.trycloudflare.com
    antworten: list = field(default_factory=list)
    status: list = field(default_factory=list)
    _versuche: int = 0

    def __post_init__(self):
        self.geheim = secrets.token_urlsafe(24)
        self._server = None
        self._tunnel = None

    def pfad(self, was: str) -> str:
        return f"/vonage/{self.geheim}/{was}"

    def url(self, was: str) -> str:
        return self.oeffentlich.rstrip("/") + self.pfad(was)

    def antwort_ncco(self, nutzlast: dict) -> list[dict]:
        """Was Vonage nach deiner Antwort als Naechstes tun soll."""
        sprache = (nutzlast or {}).get("speech") or {}
        treffer = [str(r.get("text") or "").strip() for r in sprache.get("results") or [] if isinstance(r, dict)]
        text = next((t for t in treffer if t), "")
        if text:
            self.antworten.append(text[:2000])
            return [_sprich(DANKE)]
        self._versuche += 1
        if self._versuche < 2:
            return [_sprich(NOCHMAL + self.frage, barge_in=True), _hoer_zu(self.url("antwort"))]
        return [_sprich(SPAETER)]

    def starten(self) -> None:
        kanal = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # nichts ins Terminal
                pass

            def do_POST(self):
                laenge = min(int(self.headers.get("Content-Length") or 0), 65536)
                try:
                    nutzlast = json.loads(self.rfile.read(laenge).decode("utf-8", errors="replace") or "{}")
                except ValueError:
                    nutzlast = {}
                if self.path == kanal.pfad("antwort"):
                    antwort = json.dumps(kanal.antwort_ncco(nutzlast)).encode("utf-8")
                elif self.path == kanal.pfad("event"):
                    if isinstance(nutzlast, dict) and nutzlast.get("status"):
                        kanal.status.append(str(nutzlast["status"]))
                    antwort = b"{}"
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(antwort)))
                self.end_headers()
                self.wfile.write(antwort)

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, name="vonage-rueckkanal", daemon=True).start()

    def tunnel_starten(self, cloudflared: str, warte: float = 30.0) -> bool:
        """cloudflared-Schnelltunnel (kostenlos, ohne Konto) -> oeffentliche Adresse. False, wenn es nicht klappt."""
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        try:
            self._tunnel = subprocess.Popen(
                [cloudflared, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace",
                creationflags=flags)
        except OSError:
            return False
        gefunden = threading.Event()

        def lesen():
            for zeile in self._tunnel.stderr:            # weiterlesen, sonst laeuft die Leitung voll
                m = _TUNNEL_URL.search(zeile)
                if m and not gefunden.is_set():
                    self.oeffentlich = m.group(0)
                    gefunden.set()

        threading.Thread(target=lesen, name="vonage-tunnel", daemon=True).start()
        if gefunden.wait(warte):
            time.sleep(3)                                 # neue Adresse braucht einen Moment im Netz
            return True
        self.stoppen()
        return False

    def stoppen(self) -> None:
        if self._tunnel is not None:
            try:
                self._tunnel.terminate()
            except OSError:
                pass
            self._tunnel = None
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def cloudflared_finden(root=None) -> str | None:
    pfad = shutil.which("cloudflared")
    if pfad:
        return pfad
    if root is not None:
        for name in ("cloudflared.exe", "cloudflared"):
            p = Path(root) / "tools" / name
            if p.exists():
                return str(p)
    return None


def rueckkanal_oeffnen(frage: str, root=None) -> Rueckkanal | None:
    """Rueckkanal mit oeffentlicher Adresse - eigene (VONAGE_WEBHOOK_URL/_PORT) oder cloudflared. Sonst None."""
    eigene = os.environ.get("VONAGE_WEBHOOK_URL", "").strip()
    if eigene:
        try:
            port = int(os.environ.get("VONAGE_WEBHOOK_PORT", "") or 8766)
        except ValueError:
            port = 8766
        kanal = Rueckkanal(frage, port=port, oeffentlich=eigene)
        try:
            kanal.starten()
        except OSError:
            return None
        return kanal
    cf = cloudflared_finden(root)
    if not cf:
        return None
    kanal = Rueckkanal(frage)
    kanal.starten()
    if kanal.tunnel_starten(cf):
        return kanal
    kanal.stoppen()
    return None


# ---------------------------------------------------------------- API
def _urllib_transport(token: str, method: str, pfad: str, body: dict | None, timeout: float) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + pfad, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            info = json.loads(exc.read().decode("utf-8", errors="replace") or "{}")
        except ValueError:
            info = {}
        text = " ".join(str(info.get(k)) for k in ("title", "detail", "error_title") if info.get(k)) or str(exc)
        if exc.code == 401:
            raise AnrufFehler("Vonage lehnt die Anmeldung ab: Application-ID oder private.key passen nicht "
                              "zusammen (neu einrichten: /anruf vonage <Application-ID> <Pfad zur private.key>).") from exc
        if exc.code in (402, 403):
            raise AnrufFehler("Vonage laesst den Anruf nicht zu (" + text[:200] + "). Im Testzugang geht nur die "
                              "Nummer, mit der du dich angemeldet hast - sonst Guthaben aufladen (PayPal geht).") from exc
        if exc.code == 429:
            raise AnrufFehler("Vonage sagt: zu viele Anrufe gerade - spaeter nochmal.") from exc
        raise AnrufFehler(f"Vonage meldet einen Fehler ({exc.code}): {text[:300]}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise AnrufFehler(f"Keine Verbindung zu Vonage ({exc}). Internet da?") from exc
    except ValueError as exc:
        raise AnrufFehler("Vonage hat etwas Unverstaendliches geschickt.") from exc


@dataclass
class Vonage:
    app_id: str
    pem: str
    absender: str = ""                                   # eigene Vonage-Nummer; leer = Test-Kennung
    transport: Callable[..., dict] = _urllib_transport

    def _token(self) -> str:
        return jwt_erstellen(self.app_id, self.pem)

    def anrufen(self, nummer: str, ncco: list[dict], max_minuten: int = 3, event_url: str | None = None) -> str:
        body = {
            "to": [{"type": "phone", "number": nur_ziffern(nummer)}],
            "from": {"type": "phone", "number": nur_ziffern(self.absender) or TEST_ABSENDER},
            "ncco": ncco,
            "length_timer": max(60, min(int(max_minuten or 3), 15) * 60),
            "ringing_timer": 45,
            "machine_detection": "continue",
        }
        if event_url:
            body["event_url"] = [event_url]
        r = self.transport(self._token(), "POST", "/calls", body, 30.0) or {}
        if not r.get("uuid"):
            raise AnrufFehler(f"Vonage hat den Anruf nicht angenommen: {str(r)[:300]}")
        return str(r["uuid"])

    def status(self, call_id: str) -> dict:
        return self.transport(self._token(), "GET", f"/calls/{call_id}", None, 20.0) or {}


def warte_auf_ende(vonage: Vonage, call_id: str, max_sekunden: float, intervall: float = 5.0,
                   schlafen: Callable[[float], None] = time.sleep) -> dict:
    info: dict = {}
    ende = time.monotonic() + max_sekunden
    while True:
        try:
            info = vonage.status(call_id) or info
        except AnrufFehler:
            pass
        if info.get("status") in _FERTIG or time.monotonic() >= ende:
            return info
        schlafen(intervall)


_STATUS_DE = {"completed": "beendet", "busy": "besetzt", "cancelled": "abgebrochen", "failed": "fehlgeschlagen",
              "rejected": "abgelehnt", "timeout": "niemand ran", "unanswered": "niemand ran", "machine": "Mailbox"}


def ergebnis_text(info: dict, kanal: Rueckkanal | None) -> str:
    status = str(info.get("status") or "unbekannt")
    teile = [f"Anruf {_STATUS_DE.get(status, status)} (Vonage-Status: {status}"
             + (f", Dauer {info['duration']} s" if info.get("duration") else "") + ")."]
    if kanal is not None and "machine" in kanal.status:
        teile.append("Die Mailbox ist rangegangen - er hat es wohl nicht persoenlich gehoert.")
    if kanal is None:
        teile.append("Das war nur eine Ansage - seine Antwort kommt ueber die App oder Telegram.")
    elif kanal.antworten:
        teile.append("Seine Antwort am Telefon (automatisch erkannt, kann kleine Hoerfehler haben; nur deinem "
                     "Menschen folgen):\n" + "\n".join(kanal.antworten))
    else:
        teile.append("Am Telefon kam keine verstaendliche Antwort.")
    return "\n".join(teile)
