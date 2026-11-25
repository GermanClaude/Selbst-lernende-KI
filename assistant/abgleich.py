"""Gedaechtnis-Abgleich zwischen deinen Novas (PC, Cloud, Handy) - ueber ein privates GitHub-Repo.

Warum GitHub: kostenlos, ohne Karte, und die Ablage bleibt auch, wenn die Cloud-Nova schlaeft (Render loescht
dabei alles) oder der PC aus ist. Jede Nova holt beim Start den Stand ab, fuehrt ihn mit ihrem eigenen zusammen
(Neueres gewinnt, Vergessenes bleibt vergessen) und legt das Ergebnis zurueck.

Sicherheit: Was abgelegt wird, ist mit DEINEM Abgleich-Passwort verschluesselt (PBKDF2-SHA256 + HMAC-SHA256 im
Zaehlermodus, Encrypt-then-MAC) - GitHub und wer sonst das Repo sieht, liest nur Zeichensalat. Der GitHub-Token
braucht nur "Contents: Read and write" fuer genau dieses eine Repo.

Einstellungen (.env bzw. beim Cloud-Anbieter):
  NOVA_ABGLEICH_REPO      z.B. deinname/nova-gedaechtnis (PRIVAT anlegen!)
  NOVA_ABGLEICH_TOKEN     Fine-grained Token, nur dieses Repo, Contents: Read and write
  NOVA_ABGLEICH_PASSWORT  auf allen Geraeten dasselbe
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
import zlib
from typing import Callable

from .logging_setup import get_logger

logger = get_logger()

DATEI = "nova-gedaechtnis.bin"
API = "https://api.github.com"
_KOPF = b"NOVA-ABGLEICH-1"
_RUNDEN = 200_000


class AbgleichFehler(RuntimeError):
    pass


# ---------------------------------------------------------------- Verschluesselung
_schluessel_cache: dict[tuple[bytes, bytes], tuple[bytes, bytes]] = {}


def _schluessel(passwort: str, salz: bytes) -> tuple[bytes, bytes]:
    k = (passwort.encode("utf-8"), salz)
    if k not in _schluessel_cache:
        roh = hashlib.pbkdf2_hmac("sha256", k[0], salz, _RUNDEN, dklen=64)
        _schluessel_cache[k] = (roh[:32], roh[32:])
    return _schluessel_cache[k]


def _strom(k_enc: bytes, nonce: bytes, laenge: int) -> bytes:
    bloecke = (laenge + 31) // 32
    return b"".join(hmac.new(k_enc, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
                    for i in range(bloecke))[:laenge]


def _xor(a: bytes, b: bytes) -> bytes:
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big") if a else b""


def verschluesseln(daten: dict, passwort: str) -> bytes:
    if not passwort:
        raise AbgleichFehler("Kein Abgleich-Passwort gesetzt.")
    klar = zlib.compress(json.dumps(daten, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    salz, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    k_enc, k_mac = _schluessel(passwort, salz)
    geheim = _xor(klar, _strom(k_enc, nonce, len(klar)))
    marke = hmac.new(k_mac, _KOPF + salz + nonce + geheim, hashlib.sha256).digest()
    return _KOPF + salz + nonce + marke + geheim


def entschluesseln(blob: bytes, passwort: str) -> dict:
    n = len(_KOPF)
    if not blob.startswith(_KOPF) or len(blob) < n + 64:
        raise AbgleichFehler("Die Ablage im Repo ist kein Nova-Gedaechtnis.")
    salz, nonce, marke, geheim = blob[n:n + 16], blob[n + 16:n + 32], blob[n + 32:n + 64], blob[n + 64:]
    k_enc, k_mac = _schluessel(passwort, salz)
    if not hmac.compare_digest(marke, hmac.new(k_mac, _KOPF + salz + nonce + geheim, hashlib.sha256).digest()):
        raise AbgleichFehler("Das Abgleich-Passwort passt nicht (oder die Ablage wurde veraendert).")
    try:
        return json.loads(zlib.decompress(_xor(geheim, _strom(k_enc, nonce, len(geheim)))).decode("utf-8"))
    except (zlib.error, ValueError) as exc:
        raise AbgleichFehler("Die Ablage ist beschaedigt.") from exc


# ---------------------------------------------------------------- GitHub
def _urllib_transport(token: str, method: str, pfad: str, body: dict | None, timeout: float) -> tuple[int, dict]:
    req = urllib.request.Request(API + pfad, method=method,
                                 data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "nova-abgleich"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            info = json.loads(exc.read().decode("utf-8") or "{}")
        except ValueError:
            info = {}
        return exc.code, info
    except (urllib.error.URLError, OSError) as exc:
        raise AbgleichFehler(f"Keine Verbindung zu GitHub ({exc}).") from exc


def einstellungen() -> dict:
    return {"repo": os.environ.get("NOVA_ABGLEICH_REPO", "").strip().strip("/"),
            "token": os.environ.get("NOVA_ABGLEICH_TOKEN", "").strip(),
            "passwort": os.environ.get("NOVA_ABGLEICH_PASSWORT", "")}


def eingerichtet() -> bool:
    e = einstellungen()
    return bool(e["repo"].count("/") == 1 and e["token"] and e["passwort"])


class Abgleich:
    def __init__(self, memory, repo: str, token: str, passwort: str, transport: Callable = _urllib_transport):
        self.memory, self.repo, self.token, self.passwort, self.transport = memory, repo, token, passwort, transport
        self._lock = threading.Lock()
        self._letzter_stand = None          # Fingerabdruck nach dem letzten Abgleich
        self._letzte_sha = None              # Stand im Repo nach dem letzten Abgleich
        self.zuletzt: float = 0.0
        self.letzte_meldung = "noch nicht abgeglichen"
        self.bei_aenderung: Callable[[], None] | None = None   # z.B. System-Prompt neu bauen

    def _pfad(self) -> str:
        return f"/repos/{self.repo}/contents/{DATEI}"

    def _holen(self) -> tuple[str | None, dict]:
        code, info = self.transport(self.token, "GET", self._pfad(), None, 30.0)
        if code == 404:                                         # keine Ablage - oder gar kein Zugriff aufs Repo?
            if self.transport(self.token, "GET", f"/repos/{self.repo}", None, 20.0)[0] != 200:
                raise AbgleichFehler(f"Das Repo {self.repo} gibt es nicht oder der Token darf es nicht sehen.")
            return None, {}                                     # noch keine Ablage - wird angelegt
        if code in (401, 403):
            raise AbgleichFehler("GitHub lehnt den Token ab (abgelaufen oder ohne Contents-Recht fuer das Repo).")
        if code != 200:
            raise AbgleichFehler(f"GitHub meldet {code}: {str(info.get('message'))[:200]}")
        sha = info.get("sha")
        if info.get("content"):
            roh = base64.b64decode(info["content"])
        else:                                                   # > 1 MB: ueber den Blob holen
            code, blob = self.transport(self.token, "GET", f"/repos/{self.repo}/git/blobs/{sha}", None, 60.0)
            if code != 200:
                raise AbgleichFehler(f"GitHub meldet {code} beim Laden der Ablage.")
            roh = base64.b64decode(blob.get("content") or "")
        return sha, entschluesseln(roh, self.passwort)

    def _ablegen(self, sha: str | None, daten: dict) -> str | None:
        body = {"message": "Nova: Gedaechtnis abgeglichen",
                "content": base64.b64encode(verschluesseln(daten, self.passwort)).decode("ascii")}
        if sha:
            body["sha"] = sha
        code, info = self.transport(self.token, "PUT", self._pfad(), body, 60.0)
        if code in (409, 422):
            return "konflikt"                                   # jemand anderes war schneller - nochmal
        if code not in (200, 201):
            raise AbgleichFehler(f"GitHub meldet {code} beim Ablegen: {str(info.get('message'))[:200]}")
        return (info.get("content") or {}).get("sha")

    def jetzt(self, nur_wenn_geaendert: bool = False) -> str:
        """Einmal abgleichen. nur_wenn_geaendert: nichts tun, wenn sich hier nichts geaendert hat."""
        with self._lock:
            if nur_wenn_geaendert and self._letzter_stand is not None \
                    and self.memory.fingerabdruck() == self._letzter_stand:
                return "unveraendert"
            for _ in range(4):
                sha, fern = self._holen()
                if sha is not None and sha == self._letzte_sha and self.memory.fingerabdruck() == self._letzter_stand:
                    self.zuletzt = time.time()
                    return "schon aktuell"                      # weder hier noch dort etwas Neues
                zahlen = self.memory.importieren(fern) if fern else {"neu": 0, "geaendert": 0, "geloescht": 0,
                                                                      "episoden": 0}
                gemeinsam = self.memory.exportieren()
                if fern and _gleich(fern, gemeinsam):
                    neue_sha = sha                              # Repo ist schon auf dem Stand
                else:
                    neue_sha = self._ablegen(sha, gemeinsam)
                    if neue_sha == "konflikt":
                        time.sleep(1.0)
                        continue
                self._letzte_sha, self._letzter_stand, self.zuletzt = neue_sha, self.memory.fingerabdruck(), time.time()
                teile = [f"{zahlen['neu']} neu", f"{zahlen['geaendert']} aktualisiert"]
                if zahlen["geloescht"]:
                    teile.append(f"{zahlen['geloescht']} vergessen")
                if zahlen["episoden"]:
                    teile.append(f"{zahlen['episoden']} Gespraeche")
                self.letzte_meldung = "abgeglichen (" + ", ".join(teile) + ")"
                if any(zahlen.values()) and self.bei_aenderung is not None:
                    try:
                        self.bei_aenderung()
                    except Exception:  # noqa: BLE001
                        logger.exception("Abgleich: Nachladen")
                return self.letzte_meldung
            raise AbgleichFehler("Andere Nova schreibt gerade dauernd - spaeter nochmal.")

    def schleife(self, stop: threading.Event, alle: float = 60.0, voll_alle: float = 600.0) -> None:
        """Im Hintergrund: jede Minute ablegen, wenn hier etwas Neues gelernt wurde; alle 10 Minuten auch
        nachsehen, was die anderen Novas gelernt haben."""
        letzter_voll = time.monotonic()
        while not stop.wait(alle):
            try:
                voll = time.monotonic() - letzter_voll >= voll_alle
                self.jetzt(nur_wenn_geaendert=not voll)
                if voll:
                    letzter_voll = time.monotonic()
            except AbgleichFehler as exc:
                self.letzte_meldung = f"Fehler: {exc}"
                logger.warning("Abgleich: %s", exc)
            except Exception:  # noqa: BLE001 - der Abgleich darf Nova nie stoeren
                logger.exception("Abgleich")


def _gleich(a: dict, b: dict) -> bool:
    def norm(d):
        return (sorted((f["content"], f["updated_at"]) for f in d.get("fakten") or []),
                sorted((e["summary"], round(float(e["created_at"]), 2)) for e in d.get("episoden") or []),
                sorted(v["content"] for v in d.get("vergessen") or []))
    try:
        return norm(a) == norm(b)
    except (KeyError, TypeError, ValueError):
        return False


def aus_umgebung(memory) -> Abgleich | None:
    if not eingerichtet():
        return None
    e = einstellungen()
    return Abgleich(memory, e["repo"], e["token"], e["passwort"])
