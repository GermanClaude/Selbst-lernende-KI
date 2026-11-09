"""Signalisierung fuer die Handy-Kamera: Kopplung, Verschluesselung, Nachrichten, Relais.

Kopplung (steht im QR-Code, nur im URL-Fragment hinter "#p="):
    base64url( Version(1) | Thema(16 Zufallsbytes) | Schluessel(32 Zufallsbytes, AES-256-GCM)
               | Ablauf(uint32, Unix-Sekunden, big endian) | Flags(1) )      -> 54 Bytes, 72 Zeichen
    Das Thema (base64url der 16 Bytes, 22 Zeichen) ist der Kanalname beim Relais (ntfy.sh).

Nachricht (Text beim Relais, < 4096 Bytes - Grenze von ntfy.sh):
    base64url( 0x01 | Nonce(12) | AES-GCM(Schluessel, Nonce, Klartext, AAD="nova-kamera/1|<Thema>") )
    Klartext = Packart(1: 0=roh, 1=deflate-raw) | JSON {"t": Typ, "s": Folgenummer, "z": Zeit in ms,
                                                        "f": "n" (Nova) | "h" (Handy), "d": {...}}
    Abgelehnt werden: falscher Schluessel/veraenderte Daten, Wiederholungen (Folgenummer nicht
    groesser als die letzte dieses Absenders), zu alte/zu neue Zeitstempel.

Kurzcode (Alternative zum QR-Code, 8 Zeichen, z.B. "7KQ2-M9XD"): PBKDF2 macht daraus ein eigenes
Thema + Schluessel; dort legt Nova die Kopplung (verschluesselt) ab. Das Handy holt sie mit dem Code.

Sicherheit: Schluessel und SDP werden nie geloggt (``repr`` der Kopplung verbirgt den Schluessel).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import struct
import threading
import time
import zlib
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

PROTOKOLL = 1
STANDARD_BASIS_URL = "https://germanclaude.github.io/Selbst-lernende-KI/kamera/v1/"
STANDARD_NTFY = "https://ntfy.sh"
GUELTIG_S = 300                 # so lange gilt ein QR-Code
MAX_TEXT = 4000                 # ntfy.sh: bis 4096 Bytes bleibt es eine Textnachricht
MAX_KLARTEXT = 64 * 1024        # Schutz gegen "Zip-Bomben"
MAX_UHR_ABWEICHUNG_S = 300      # Handy-Uhr darf so weit von der PC-Uhr abweichen
FLAG_NTFY = 0x01
FLAG_MQTT = 0x02                # vorgesehen: Ersatz-Relais (MQTT ueber WSS)
ABSENDER = ("n", "h")           # n = Nova (PC), h = Handy

CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford-Base32 (ohne I, L, O, U)
CODE_LAENGE = 8
CODE_SALZ = b"nova-kamera/code/1"
CODE_RUNDEN = 200_000

_THEMA_MUSTER = re.compile(r"^[-_A-Za-z0-9]{1,64}$")
_PAYLOAD_LAENGE = 1 + 16 + 32 + 4 + 1


class SignalFehler(ValueError):
    """Ungueltige, veraenderte, wiederholte oder zu grosse Nachricht (Text fuer Protokoll/Nutzer)."""


class RelayFehler(RuntimeError):
    """Das Relais (ntfy.sh) ist nicht erreichbar oder lehnt ab (Text fuer den Nutzer)."""


# -- Hilfen -------------------------------------------------------------------------------
def b64u(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).rstrip(b"=").decode("ascii")


def b64u_dekodieren(text: str) -> bytes:
    if not isinstance(text, str) or not re.fullmatch(r"[-_A-Za-z0-9]*", text):
        raise SignalFehler("Ung\u00fcltige Zeichen in den Daten.")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as exc:
        raise SignalFehler("Ung\u00fcltige Daten.") from exc


def _aesgcm(schluessel: bytes):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise SignalFehler("F\u00fcr die Handy-Kamera fehlt das Paket 'cryptography' "
                           "(pip install cryptography).") from exc
    return AESGCM(schluessel)


def _aad(thema: str) -> bytes:
    return f"nova-kamera/{PROTOKOLL}|{thema}".encode("ascii")


# -- Kopplung -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Kopplung:
    """Ein Kopplungsgeheimnis (Thema + Schluessel + Ablauf). Gilt fuer genau ein Handy."""

    thema_roh: bytes
    schluessel: bytes = field(repr=False)
    ablauf: int
    flags: int = FLAG_NTFY
    version: int = PROTOKOLL

    def __post_init__(self):
        if len(self.thema_roh) != 16 or len(self.schluessel) != 32:
            raise SignalFehler("Kopplung unvollst\u00e4ndig.")

    @classmethod
    def neu(cls, gueltig: float = GUELTIG_S, uhr=time.time, flags: int = FLAG_NTFY) -> "Kopplung":
        return cls(secrets.token_bytes(16), secrets.token_bytes(32), int(uhr() + gueltig), flags)

    @property
    def thema(self) -> str:
        return b64u(self.thema_roh)

    def abgelaufen(self, jetzt: float | None = None) -> bool:
        return (time.time() if jetzt is None else jetzt) > self.ablauf

    def payload(self) -> str:
        roh = struct.pack(">B16s32sIB", self.version, self.thema_roh, self.schluessel,
                          self.ablauf & 0xFFFFFFFF, self.flags & 0xFF)
        return b64u(roh)

    def link(self, basis: str = STANDARD_BASIS_URL) -> str:
        return f"{basis.split('#', 1)[0]}#p={self.payload()}"

    @classmethod
    def aus_payload(cls, text: str, jetzt: float | None = None) -> "Kopplung":
        """Liest eine Kopplung. Mit ``jetzt`` wird auch der Ablauf geprueft."""
        roh = b64u_dekodieren((text or "").strip())
        if len(roh) != _PAYLOAD_LAENGE:
            raise SignalFehler("Der Kopplungs-Code ist unvollst\u00e4ndig.")
        version, thema, schluessel, ablauf, flags = struct.unpack(">B16s32sIB", roh)
        if version != PROTOKOLL:
            raise SignalFehler("Diese Kopplung stammt von einer anderen Nova-Version.")
        kopplung = cls(thema, schluessel, ablauf, flags, version)
        if jetzt is not None and kopplung.abgelaufen(jetzt):
            raise SignalFehler("Der QR-Code ist abgelaufen. Bitte in Nova einen neuen anzeigen lassen.")
        return kopplung

    @classmethod
    def aus_link(cls, link: str, jetzt: float | None = None) -> "Kopplung":
        fragment = urlsplit(link or "").fragment
        for teil in fragment.split("&"):
            if teil.startswith("p="):
                return cls.aus_payload(teil[2:], jetzt)
        raise SignalFehler("Im Link fehlt die Kopplung (#p=...).")


# -- Verschluesselung + Packen ------------------------------------------------------------
def packen(daten: bytes) -> bytes:
    """deflate-raw (wie CompressionStream("deflate-raw") im Browser) - nur wenn es kleiner wird."""
    kompressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    gepackt = kompressor.compress(daten) + kompressor.flush()
    return b"\x01" + gepackt if len(gepackt) < len(daten) else b"\x00" + daten


def entpacken(daten: bytes, grenze: int = MAX_KLARTEXT) -> bytes:
    if not daten:
        raise SignalFehler("Leere Nachricht.")
    art, rest = daten[0], daten[1:]
    if art == 0:
        if len(rest) > grenze:
            raise SignalFehler("Nachricht zu gro\u00df.")
        return rest
    if art != 1:
        raise SignalFehler("Unbekannte Packart.")
    try:
        entpacker = zlib.decompressobj(-15)
        ergebnis = entpacker.decompress(rest, grenze + 1)
    except zlib.error as exc:
        raise SignalFehler("Nachricht l\u00e4sst sich nicht entpacken.") from exc
    if len(ergebnis) > grenze or entpacker.unconsumed_tail:
        raise SignalFehler("Nachricht zu gro\u00df.")
    return ergebnis


def verschluesseln(schluessel: bytes, thema: str, klartext: bytes) -> str:
    nonce = os.urandom(12)
    return b64u(bytes([PROTOKOLL]) + nonce + _aesgcm(schluessel).encrypt(nonce, klartext, _aad(thema)))


def entschluesseln(schluessel: bytes, thema: str, text: str) -> bytes:
    roh = b64u_dekodieren((text or "").strip())
    if len(roh) < 1 + 12 + 16 or roh[0] != PROTOKOLL:
        raise SignalFehler("Keine Nova-Nachricht.")
    try:
        from cryptography.exceptions import InvalidTag  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise SignalFehler("Paket 'cryptography' fehlt.") from exc
    try:
        return _aesgcm(schluessel).decrypt(roh[1:13], roh[13:], _aad(thema))
    except InvalidTag as exc:
        raise SignalFehler("Nachricht ung\u00fcltig (falscher Schl\u00fcssel oder ver\u00e4ndert).") from exc


# -- Nachrichten --------------------------------------------------------------------------
@dataclass(frozen=True)
class Nachricht:
    typ: str
    seq: int
    zeit_ms: int
    absender: str
    daten: dict

    def __repr__(self) -> str:  # nie SDP oder andere Inhalte ins Protokoll
        return f"Nachricht(typ={self.typ!r}, seq={self.seq}, absender={self.absender!r})"


class Kanal:
    """Eine Seite (Nova oder Handy) einer Kopplung: verpackt/oeffnet Nachrichten, merkt Folgenummern."""

    def __init__(self, kopplung: Kopplung, absender: str = "n", uhr=time.time,
                 max_abweichung: float = MAX_UHR_ABWEICHUNG_S):
        if absender not in ABSENDER:
            raise ValueError("absender muss 'n' oder 'h' sein")
        self.kopplung = kopplung
        self.absender = absender
        self._uhr = uhr
        self._seq = 0
        self._zuletzt: dict[str, int] = {}
        self.max_abweichung = max_abweichung
        self._sperre = threading.Lock()

    @property
    def thema(self) -> str:
        return self.kopplung.thema

    def verpacke(self, typ: str, daten: dict | None = None) -> str:
        with self._sperre:
            self._seq += 1
            seq = self._seq
        inhalt = {"t": typ, "s": seq, "z": int(self._uhr() * 1000), "f": self.absender, "d": daten or {}}
        klartext = packen(json.dumps(inhalt, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        text = verschluesseln(self.kopplung.schluessel, self.thema, klartext)
        if len(text) > MAX_TEXT:
            raise SignalFehler(f"Nachricht zu gro\u00df f\u00fcr das Relais ({len(text)} > {MAX_TEXT} Bytes).")
        return text

    def oeffne(self, text: str) -> Nachricht | None:
        """Gibt die Nachricht der Gegenseite zurueck, None fuer eigene (Echo vom Relais)."""
        if not isinstance(text, str) or len(text) > MAX_TEXT + 96:
            raise SignalFehler("Nachricht zu gro\u00df.")
        klartext = entpacken(entschluesseln(self.kopplung.schluessel, self.thema, text))
        try:
            inhalt = json.loads(klartext.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise SignalFehler("Nachricht ist kein JSON.") from exc
        if not isinstance(inhalt, dict):
            raise SignalFehler("Nachricht hat das falsche Format.")
        typ, seq, zeit, absender, daten = (inhalt.get(k) for k in ("t", "s", "z", "f", "d"))
        if (not isinstance(typ, str) or not typ or len(typ) > 32
                or not isinstance(seq, int) or isinstance(seq, bool) or seq < 1
                or not isinstance(zeit, int) or isinstance(zeit, bool)
                or absender not in ABSENDER or not isinstance(daten, dict)):
            raise SignalFehler("Nachricht hat das falsche Format.")
        if absender == self.absender:
            return None
        if abs(self._uhr() * 1000 - zeit) > self.max_abweichung * 1000:
            raise SignalFehler("Nachricht ist veraltet (oder die Uhr von Handy/PC geht falsch).")
        with self._sperre:
            if seq <= self._zuletzt.get(absender, 0):
                raise SignalFehler("Nachricht wurde wiederholt - abgelehnt.")
            self._zuletzt[absender] = seq
        return Nachricht(typ, seq, zeit, absender, daten)


# -- Kurzcode -----------------------------------------------------------------------------
def neuer_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LAENGE))


def code_normalisieren(text: str) -> str:
    """Grossbuchstaben, ohne Leer-/Bindestriche; O->0, I/L->1. Wirft SignalFehler bei Unsinn."""
    roh = re.sub(r"[\s\-_.]", "", (text or "")).upper().translate(str.maketrans("OIL", "011"))
    if len(roh) != CODE_LAENGE or any(z not in CODE_ALPHABET for z in roh):
        raise SignalFehler(f"Der Code hat {CODE_LAENGE} Zeichen (Buchstaben und Ziffern).")
    return roh


def code_anzeige(code: str) -> str:
    code = code_normalisieren(code)
    return f"{code[:4]}-{code[4:]}"


def code_kopplung(code: str, ablauf: int) -> Kopplung:
    """Thema + Schluessel des Code-Kanals (PBKDF2-SHA256, wie im Browser per WebCrypto)."""
    roh = hashlib.pbkdf2_hmac("sha256", code_normalisieren(code).encode("ascii"), CODE_SALZ,
                              CODE_RUNDEN, dklen=48)
    return Kopplung(roh[:16], roh[16:], ablauf)


def code_nachricht(kopplung: Kopplung, code: str, uhr=time.time) -> tuple[str, str]:
    """(Thema des Code-Kanals, Text) - die eigentliche Kopplung, verschluesselt mit dem Code."""
    kanal = Kanal(code_kopplung(code, kopplung.ablauf), "n", uhr)
    return kanal.thema, kanal.verpacke("kopplung", {"p": kopplung.payload()})


# -- Relais -------------------------------------------------------------------------------
@dataclass(frozen=True)
class RelayNachricht:
    id: str
    zeit: float
    text: str = field(repr=False)


@runtime_checkable
class Relay(Protocol):
    """Briefkasten fuer die Signalisierung. Beide Seiten schreiben in dasselbe Thema.

    ``empfangen`` wartet hoechstens ``warten`` Sekunden und liefert Nachrichten NACH ``seit``
    (Relais-ID einer frueheren Nachricht, Unix-Zeit als Text, oder None = alles Vorhandene).
    Doppelte Zustellungen sind moeglich - der Aufrufer sortiert sie per ``id`` aus.
    """

    name: str

    def senden(self, thema: str, text: str) -> str | None: ...

    def empfangen(self, thema: str, seit: str | None, warten: float) -> list[RelayNachricht]: ...

    def schliessen(self) -> None: ...


def pruefe_thema(thema: str) -> str:
    if not isinstance(thema, str) or not _THEMA_MUSTER.match(thema):
        raise RelayFehler("Ung\u00fcltiger Kanalname.")
    return thema


class NtfyRelay:
    """ntfy.sh (ohne Konto): POST /<thema> zum Senden, GET /<thema>/json?since=... zum Lesen."""

    name = "ntfy"

    def __init__(self, basis: str = STANDARD_NTFY, session=None, verbinden_timeout: float = 6.0,
                 senden_timeout: float = 10.0):
        self.basis = basis.rstrip("/")
        self._session = session
        self.verbinden_timeout = verbinden_timeout
        self.senden_timeout = senden_timeout
        self._offen = None  # laufende Lese-Antwort (zum Abbrechen in schliessen())
        self._geschlossen = False

    def _sitzung(self):
        if self._session is None:
            import requests  # noqa: PLC0415

            self._session = requests.Session()
        return self._session

    def senden(self, thema: str, text: str) -> str | None:
        pruefe_thema(thema)
        if len(text.encode("utf-8")) > 4096:
            raise RelayFehler("Nachricht zu gro\u00df f\u00fcr ntfy.sh.")
        try:
            antwort = self._sitzung().post(
                f"{self.basis}/{thema}", data=text.encode("utf-8"),
                headers={"X-Firebase": "no", "Content-Type": "text/plain; charset=utf-8"},
                timeout=(self.verbinden_timeout, self.senden_timeout))
        except Exception as exc:  # noqa: BLE001 - requests.RequestException u.a.
            raise RelayFehler("ntfy.sh ist nicht erreichbar \u2013 ist der PC online?") from exc
        self._pruefe_status(antwort)
        try:
            return str(antwort.json().get("id") or "") or None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _pruefe_status(antwort) -> None:
        code = getattr(antwort, "status_code", 0)
        if code == 429:
            raise RelayFehler("ntfy.sh bremst gerade (zu viele Anfragen). Bitte eine Minute warten.")
        if not 200 <= code < 300:
            raise RelayFehler(f"ntfy.sh antwortet mit Fehler {code}.")

    def empfangen(self, thema: str, seit: str | None, warten: float) -> list[RelayNachricht]:
        pruefe_thema(thema)
        if self._geschlossen:
            return []
        start = time.monotonic()
        try:
            antwort = self._sitzung().get(
                f"{self.basis}/{thema}/json", params={"since": seit or "all"}, stream=True,
                timeout=(self.verbinden_timeout, max(1.0, warten)))
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ in ("ReadTimeout", "Timeout"):
                return []
            raise RelayFehler("ntfy.sh ist nicht erreichbar \u2013 ist der PC online?") from exc
        self._offen = antwort
        ergebnis: list[RelayNachricht] = []
        try:
            self._pruefe_status(antwort)
            # chunk_size=1: sonst wartet requests auf 512 Bytes, und kurze Zeilen eines
            # laufenden Datenstroms bleiben im Puffer haengen (ntfy schickt nur ab und zu etwas).
            for zeile in antwort.iter_lines(chunk_size=1):
                if self._geschlossen:
                    break
                if zeile:
                    nachricht = self._zeile(zeile)
                    if nachricht is not None:
                        ergebnis.append(nachricht)
                        break  # weitere kommen beim naechsten Aufruf (seit=id)
                if time.monotonic() - start >= warten:
                    break
        except RelayFehler:
            raise
        except Exception:  # noqa: BLE001 - Lese-Timeout oder abgebrochen: einfach leer
            pass
        finally:
            self._offen = None
            try:
                antwort.close()
            except Exception:  # noqa: BLE001
                pass
        return ergebnis

    @staticmethod
    def _zeile(zeile) -> RelayNachricht | None:
        try:
            daten = json.loads(zeile if isinstance(zeile, str) else zeile.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        if not isinstance(daten, dict) or daten.get("event") != "message":
            return None
        text = daten.get("message")
        if not isinstance(text, str) or not text:
            return None
        return RelayNachricht(str(daten.get("id", "")), float(daten.get("time") or 0), text)

    def schliessen(self) -> None:
        self._geschlossen = True
        offen = self._offen
        if offen is not None:
            try:
                offen.close()
            except Exception:  # noqa: BLE001
                pass


class SpeicherRelay:
    """Relais im Arbeitsspeicher (Tests, Probelauf). Thread-sicher; mehrere Leser moeglich."""

    name = "speicher"

    def __init__(self, uhr=time.time):
        self._uhr = uhr
        self._themen: dict[str, list[RelayNachricht]] = {}
        self._bedingung = threading.Condition()
        self._zaehler = 0
        self._geschlossen = False
        self.gesendet: list[tuple[str, str]] = []

    def senden(self, thema: str, text: str) -> str:
        pruefe_thema(thema)
        with self._bedingung:
            self._zaehler += 1
            nid = f"m{self._zaehler:08d}"
            self._themen.setdefault(thema, []).append(RelayNachricht(nid, self._uhr(), text))
            self.gesendet.append((thema, text))
            self._bedingung.notify_all()
        return nid

    def _nach(self, thema: str, seit: str | None) -> list[RelayNachricht]:
        alle = self._themen.get(thema, [])
        if not seit or seit == "all":
            return list(alle)
        if seit.isdigit():
            return [n for n in alle if n.zeit >= int(seit)]
        return [n for n in alle if n.id > seit]

    def empfangen(self, thema: str, seit: str | None, warten: float) -> list[RelayNachricht]:
        pruefe_thema(thema)
        ende = time.monotonic() + warten
        with self._bedingung:
            while not self._geschlossen:
                neu = self._nach(thema, seit)
                if neu:
                    return neu
                rest = ende - time.monotonic()
                if rest <= 0:
                    break
                self._bedingung.wait(min(rest, 0.5))
        return []

    def schliessen(self) -> None:
        with self._bedingung:
            self._geschlossen = True
            self._bedingung.notify_all()

    def wieder_oeffnen(self) -> None:
        with self._bedingung:
            self._geschlossen = False


# -- SDP: nur LAN-Kandidaten ---------------------------------------------------------------
def ist_lan_adresse(adresse: str) -> bool:
    """RFC1918, IPv6-ULA (fc00::/7), Link-local (169.254/16, fe80::/10) oder mDNS-Name (*.local).

    mDNS-Namen (Browser verstecken so ihre Adresse) loest nur das eigene Netz auf - also LAN.
    Loopback, oeffentliche Adressen, CGNAT (100.64/10) usw. werden abgelehnt.
    """
    import ipaddress  # noqa: PLC0415

    adresse = (adresse or "").strip().strip("[]")
    if adresse.lower().endswith(".local"):
        return bool(re.fullmatch(r"[A-Za-z0-9\-]{1,63}\.local", adresse))
    try:
        ip = ipaddress.ip_address(adresse.split("%", 1)[0])
    except ValueError:
        return False
    if ip.version == 4:
        return any(ip in ipaddress.ip_network(n) for n in
                   ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"))
    if ip.ipv4_mapped is not None:
        return ist_lan_adresse(str(ip.ipv4_mapped))
    return ip in ipaddress.ip_network("fc00::/7") or ip in ipaddress.ip_network("fe80::/10")


def kandidat_erlaubt(zeile: str, pruefung=None) -> bool:
    """Eine 'candidate:'-Zeile: nur Host-Kandidaten (UDP/TCP) mit LAN-Adresse (``pruefung``)."""
    teile = zeile.strip().split()
    # a=candidate:<foundation> <component> <transport> <priority> <address> <port> typ <type> ...
    if len(teile) < 8 or teile[6] != "typ":
        return False
    return teile[7] == "host" and (pruefung or ist_lan_adresse)(teile[4])


def filtere_sdp(sdp: str, pruefung=None) -> tuple[str, int, int]:
    """Entfernt Kandidaten, die nicht ins LAN zeigen. -> (SDP, behalten, verworfen).

    ``pruefung(adresse) -> bool`` ersetzt ist_lan_adresse (Tests in Netzen ohne Privatadressen)."""
    behalten = verworfen = 0
    zeilen = []
    for zeile in (sdp or "").replace("\r\n", "\n").split("\n"):
        if zeile.startswith("a=candidate:"):
            if kandidat_erlaubt(zeile[2:], pruefung):
                behalten += 1
            else:
                verworfen += 1
                continue
        zeilen.append(zeile)
    text = "\r\n".join(zeilen).rstrip("\r\n") + "\r\n"
    return text, behalten, verworfen


# -- SDP: Kandidaten zaehlen (Diagnose), mDNS-Namen ersetzen --------------------------------
def _kandidat_teile(zeile: str) -> list[str] | None:
    teile = zeile.strip().split()
    if len(teile) < 8 or teile[6] != "typ":
        return None
    return teile


def ist_mdns_name(adresse: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9\-]{1,63}\.local", (adresse or "").strip()))


@dataclass
class KandidatenZahl:
    """Was ein Angebot an Kandidaten enthielt (fuer Protokoll und Fehlersuche - ohne SDP)."""

    ip_lan: int = 0              # Host-Kandidat mit Privatadresse
    mdns: int = 0                # Host-Kandidat mit verstecktem Namen (xxxx.local)
    nicht_lan: int = 0           # oeffentliche Adresse, srflx/relay, kaputt ...
    lan_ips: list = field(default_factory=list)   # die Privatadressen (fuer den Netz-Vergleich)
    mdns_namen: list = field(default_factory=list)

    @property
    def nutzbar(self) -> int:
        return self.ip_lan + self.mdns

    def als_dict(self) -> dict:
        return {"ip": self.ip_lan, "mdns": self.mdns, "nicht_lan": self.nicht_lan}


def kandidaten_zaehlen(sdp: str, pruefung=None) -> KandidatenZahl:
    """Zaehlt die Kandidaten eines SDP nach Art (doppelte Adressen, z.B. je m-Zeile, nur einmal)."""
    pruefe = pruefung or ist_lan_adresse
    zahl = KandidatenZahl()
    gesehen: set[tuple[str, str]] = set()
    for zeile in (sdp or "").replace("\r\n", "\n").split("\n"):
        if not zeile.startswith("a=candidate:"):
            continue
        teile = _kandidat_teile(zeile[2:])
        if teile is None:
            zahl.nicht_lan += 1
            continue
        schluessel = (teile[4].lower(), teile[5])
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        adresse = teile[4]
        if teile[7] != "host" or not pruefe(adresse):
            zahl.nicht_lan += 1
        elif ist_mdns_name(adresse):
            zahl.mdns += 1
            if adresse.lower() not in zahl.mdns_namen:
                zahl.mdns_namen.append(adresse.lower())
        else:
            zahl.ip_lan += 1
            if adresse not in zahl.lan_ips:
                zahl.lan_ips.append(adresse)
    return zahl


def mdns_ersetzen(sdp: str, adressen: dict) -> str:
    """Ersetzt mDNS-Namen in Kandidaten-Zeilen durch aufgeloeste Adressen ({name: ip}).

    Nicht aufgeloeste Namen bleiben stehen (aiortc versucht es dann selbst)."""
    if not adressen:
        return sdp
    klein = {str(k).lower(): str(v) for k, v in adressen.items() if v}
    zeilen = []
    for zeile in (sdp or "").replace("\r\n", "\n").split("\n"):
        if zeile.startswith("a=candidate:"):
            teile = zeile.split(" ")
            if len(teile) > 4 and teile[4].lower() in klein:
                teile[4] = klein[teile[4].lower()]
                zeile = " ".join(teile)
        zeilen.append(zeile)
    return "\r\n".join(zeilen).rstrip("\r\n") + "\r\n"


def ohne_kandidaten_ende(sdp: str) -> str:
    """Entfernt "a=end-of-candidates": sonst gibt aiortc sofort auf, wenn kein Kandidat des Handys
    nutzbar ist - statt auf dessen Pruefpakete zu warten (daraus lernt es die echte Adresse)."""
    zeilen = [z for z in (sdp or "").replace("\r\n", "\n").split("\n") if z.strip() != "a=end-of-candidates"]
    return "\r\n".join(zeilen).rstrip("\r\n") + "\r\n"
