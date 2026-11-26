"""Lizenzserver: die Cloud-Nova des Entwicklers gibt das Premium-Paket nur gegen einen gueltigen Code heraus.

Warum: Ein Code darf NICHTS Geheimes enthalten (jeder Code ist nur Base64 + Unterschrift und damit lesbar).
Deshalb haelt nur dieser Server den Lesezugang zum privaten Repo (NOVA_PREMIUM_REPO_TOKEN, nur als
Umgebungsvariable beim Anbieter). Ein Geraet schickt seinen Code, der Server prueft
  * die Unterschrift (oeffentlicher Schluessel - faelschen geht nur mit dem privaten Schluessel des Entwicklers),
  * Stufe (kein "aus"-Code), Ablauf (Einloesefrist + Laufzeit noch nicht vorbei) und Geraete-Kennung,
  * die Sperrliste (signiert, aus dem privaten Repo),
und gibt erst dann das unterschriebene Paket zurueck. Das Geraet prueft die Unterschrift des Pakets nochmal.

Einschalten (beim Cloud-Anbieter): NOVA_LIZENZSERVER=1 und NOVA_PREMIUM_REPO_TOKEN=<fein-granularer Token,
nur Repo Nova-Premium, Contents: Read-only>. Endpunkte (ohne NOVA_TOKEN, mit Bremse gegen Durchprobieren):
  POST /lizenz/paket       {"code": "NOVA-...", "kennung": "..."}  -> {"ok", "zip", "sig", "info"}
  GET  /lizenz/sperrliste  -> signierte Sperrliste (enthaelt nur gesperrte Code-Nummern)
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Callable

from . import premium as P
from .logging_setup import get_logger

logger = get_logger()

PAKET_ZIP = "pakete/nova-premium.zip"
PAKET_META = "pakete/nova-premium.json"
CACHE_SEKUNDEN = 300
_cache: dict[str, tuple[float, bytes]] = {}
_lock = threading.Lock()


class LizenzFehler(ValueError):
    pass


def aktiv() -> bool:
    return os.environ.get("NOVA_LIZENZSERVER") == "1" and bool(os.environ.get("NOVA_PREMIUM_REPO_TOKEN", "").strip())


def _repo() -> str:
    return os.environ.get("NOVA_PREMIUM_REPO", "").strip() or P.PAKET_REPO


def repo_holen(pfad: str) -> bytes:
    """Eine Datei aus dem privaten Repo (mit dem Token, der nur hier auf dem Server liegt). Zwischengespeichert."""
    with _lock:
        treffer = _cache.get(pfad)
        if treffer and time.time() - treffer[0] < CACHE_SEKUNDEN:
            return treffer[1]
    token = os.environ.get("NOVA_PREMIUM_REPO_TOKEN", "").strip()
    req = urllib.request.Request(f"https://api.github.com/repos/{_repo()}/contents/{pfad}",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Accept": "application/vnd.github.raw+json",
                                          "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            daten = r.read()
    except urllib.error.HTTPError as exc:
        # Niemals den Token oder Einzelheiten der Anfrage nach aussen geben.
        raise LizenzFehler("nicht_gefunden" if exc.code == 404 else "repo_fehler") from None
    except (urllib.error.URLError, OSError):
        raise LizenzFehler("repo_fehler") from None
    with _lock:
        _cache[pfad] = (time.time(), daten)
    return daten


def sperrliste_roh(holen: Callable[[str], bytes] | None = None) -> bytes:
    """Die signierte Sperrliste unveraendert weitergeben (Geraete pruefen die Unterschrift selbst)."""
    blob = (holen or repo_holen)(P.SPERR_PFAD)
    P.sperrliste_lesen(blob)            # nur Unterschriebenes weitergeben
    return blob


def _gesperrt(c: dict, holen: Callable[[str], bytes]) -> bool:
    try:
        liste = P.sperrliste_lesen(holen(P.SPERR_PFAD))
    except LizenzFehler as exc:
        if str(exc) == "nicht_gefunden":
            return False                # noch keine Sperrliste angelegt
        raise
    except P.PremiumFehler:
        logger.warning("Lizenzserver: Sperrliste im Repo ist nicht unterschrieben - ignoriert")
        return False
    return c.get("n") in set(liste.get("gesperrt") or []) or c.get("k") in set(liste.get("kennungen") or [])


def paket_fuer_code(code: str, kennung: str, holen: Callable[[str], bytes] | None = None,
                    jetzt: float | None = None, n: int = None) -> dict:
    """Prueft den Code und gibt das unterschriebene Paket zurueck. Wirft LizenzFehler (kurze Gruende)."""
    holen = holen or repo_holen
    jetzt = jetzt or time.time()
    try:
        c = P.code_lesen(code, n)
    except P.PremiumFehler:
        raise LizenzFehler("ungueltig") from None
    if c.get("t") not in P.STUFEN:
        raise LizenzFehler("keine_stufe")
    if not kennung or c.get("k") != kennung:
        raise LizenzFehler("anderes_geraet")
    dauer = float(c.get("d") or 0) or 30 * 86400
    if float(c.get("b") or 0) + dauer < jetzt:          # Frist + Laufzeit vorbei: dieser Code kann nichts mehr
        raise LizenzFehler("abgelaufen")
    if _gesperrt(c, holen):
        raise LizenzFehler("gesperrt")
    zip_roh = holen(PAKET_ZIP)
    meta = json.loads(holen(PAKET_META).decode("utf-8"))
    sig = str(meta.get("sig") or "")
    if not P.signatur_ok(zip_roh, base64.b64decode(sig), n):
        raise LizenzFehler("paket_unsigniert")      # im Repo liegt etwas, das nicht vom Entwickler stammt
    return {"ok": True, "zip": base64.b64encode(zip_roh).decode("ascii"), "sig": sig,
            "info": meta.get("info") or {}}


MELDUNGEN = {
    "ungueltig": "Der Code ist ungueltig.",
    "keine_stufe": "Mit diesem Code gibt es kein Paket.",
    "anderes_geraet": "Der Code gehoert zu einem anderen Geraet.",
    "abgelaufen": "Der Code ist abgelaufen.",
    "gesperrt": "Dieser Code wurde gesperrt.",
    "paket_unsigniert": "Das Paket auf dem Server ist nicht in Ordnung - bitte beim Entwickler melden.",
    "nicht_gefunden": "Auf dem Server liegt noch kein Paket.",
    "repo_fehler": "Der Lizenzserver kommt gerade nicht an das Paket - spaeter nochmal.",
}
