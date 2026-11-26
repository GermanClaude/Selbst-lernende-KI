"""Nova Premium (geschlossen): Freischaltung per Code und Premium-Paket aus einem privaten Repo.

Hier steht nur das Schloss - nicht die Premium-Funktionen selbst. Die liegen verschluesselt in einem privaten
GitHub-Repo und kommen nur mit einem gueltigen Code auf den Rechner.

Codes erzeugt allein der Entwickler mit seinem privaten Schluessel (nie in einem Repo). Jeder Code ist:
  * an GENAU eine Installation gebunden (Geraete-Kennung),
  * nur bis zu einem Datum einloesbar und nur EINMAL (Nonce wird gemerkt),
  * fuer eine Stufe (premium / max, oder "aus" zum Abschalten) und eine Laufzeit (Stunden bis Jahre).
Pruefen: RSA-PKCS#1-v1.5/SHA-256 gegen den oeffentlichen Schluessel unten - ein veraenderter Code faellt durch.

Die KI kann Premium weder ein- noch ausschalten: kein Werkzeug dafuer, data/premium* ist fuer alle Werkzeuge
gesperrt, und ausschalten geht nur mit einem "aus"-Code. Befehl: /novaaiupdate (steht in keiner Liste).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .logging_setup import get_logger

logger = get_logger()

# Oeffentlicher Schluessel des Entwicklers (RSA-3072, e = 65537). Der private liegt nur bei ihm.
OEFFENTLICH_N = int(
    "c43005df09dd2dcdb5a70ad53c6b21cc1a58307beaf5828c0c41577e0ddf1178e6b9d137e54889865772074f24afd3eb2cd26edf18af9ae194f00ff00a2bbeeab7ec87317c579875bcb97a7e4a6bade350d677fe19d0b23890a243793ffcdcecc98f3c88f1d785e7ae8697462d00b83844481683f9af1e43bed16c0b132aa425ead55d625161ae70ecda9ea2d906827d92b2ddaee22465cf121dc45ca057905f9e80be8e98bafa8f87369195a1a1df649c27c983e0e05f5df5d306cfdb29cf9d1d2f85f184631a4af14041ff81573b8eda001c3a9128564105c39ab7181ba495d2836aa46a42d6f574e5bb1476420041aba1bbd871dd837e310a7b7686dd216489e5f162b6282d5676498700f09adc55fad9c36e2f88250c7c49f343311a3bbb7dc413fb37f07c43ce86b3fbeecc9ba1687098aed777ea0e09c197584ef8b53bf171bac4c7e97ada3518ed87bf5448959dfb92c9ba9cb5b4f275142ca035a1a3b98a12d0a8de22c231683e6c40469264b58c13f59f22da92cf5e672f46aa3e0d", 16)
OEFFENTLICH_E = 65537
STUFEN = {"premium": "Premium", "max": "Premium Max", "dev": "Entwickler"}
CODE_MUSTER = re.compile(r"^NOVA-[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}$")

# Was jede Stufe kann (fuer die Glueckwunsch-Meldung beim Freischalten).
FUNKTIONEN = {
    "premium": [
        "Tagesbriefing auf Knopfdruck (premium_tagesbriefing)",
        "Automatisches taegliches Briefing zur Wunschzeit",
        "Sandbox-Nova: bis zu 10 frische Test-Novas gleichzeitig (/sandbox)",
        "Finanz- & Boersen-Coach fuer Einsteiger (nur Bildung, keine Anlageberatung)",
        "Gruendliche Recherche mit Quellen (premium_recherche)",
        "Edlere Premium-Optik in der App",
    ],
    "max": [
        "Alles aus Premium",
        "Fokus-Bloecke mit Erinnerungen (premium_fokus)",
        "Sehr lange Texte/Dateien gruendlich zusammenfassen (premium_lang_zusammenfassen)",
        "Mehr Anrufe pro Tag (15 statt 5)",
        "Sandbox-Nova unbegrenzt gleichzeitig",
    ],
    "dev": [
        "Alles aus Premium Max",
        "Entwicklermodus: Nova kennt und erklaert dir die geschlossenen Befehle",
        "Sandbox-Nova unbegrenzt",
    ],
}


def glueckwunsch(stufe: str) -> str:
    name = STUFEN.get(stufe, "Premium")
    punkte = "\n".join("  ✓ " + f for f in FUNKTIONEN.get(stufe, []))
    return (f"\U0001F389 Herzlichen Glueckwunsch - {name} ist freigeschaltet!\n\n"
            f"Das hast du jetzt:\n{punkte}\n")
PAKET_REPO = "GermanClaude/Nova-Premium"
PAKET_PFAD = "pakete/nova-premium.bin"
SPERR_PFAD = "pakete/gesperrt.json"       # signierte Liste gesperrter Codes (Entwickler kann Zugang zuruecknehmen)
_SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
_TAG = 86400


class PremiumFehler(ValueError):
    pass


def _b64d(text: str) -> bytes:
    text = text.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def signatur_ok(daten: bytes, signatur: bytes, n: int = None, e: int = OEFFENTLICH_E) -> bool:
    n = n or OEFFENTLICH_N
    k = (n.bit_length() + 7) // 8
    if len(signatur) != k:
        return False
    em = pow(int.from_bytes(signatur, "big"), e, n).to_bytes(k, "big")
    t = _SHA256_INFO + hashlib.sha256(daten).digest()
    erwartet = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return secrets.compare_digest(em, erwartet)


def kennung(root) -> str:
    """Geraete-Kennung fuer Codes: dieselbe anonyme Installations-Kennung wie beim Feedback (kurz gefasst)."""
    from .feedback import kennung as fb_kennung

    return fb_kennung(root)[:16]


def code_lesen(code: str, n: int = None) -> dict:
    """NOVA-<inhalt>.<signatur> -> Inhalt. Wirft PremiumFehler bei falscher Form oder Unterschrift."""
    c = "".join((code or "").split())
    if c.upper().startswith("NOVA-"):
        c = c[5:]
    teil, _, sig = c.partition(".")
    try:
        inhalt, signatur = _b64d(teil), _b64d(sig)
    except (ValueError, TypeError) as exc:
        raise PremiumFehler("Das ist kein gueltiger Code (abgeschnitten?).") from exc
    if not signatur_ok(inhalt, signatur, n):
        raise PremiumFehler("Der Code ist ungueltig (falsch abgetippt oder veraendert).")
    try:
        daten = json.loads(inhalt)
    except ValueError as exc:
        raise PremiumFehler("Der Code ist ungueltig.") from exc
    if not isinstance(daten, dict) or daten.get("v") != 1:
        raise PremiumFehler("Diesen Code-Typ kennt diese Nova-Version nicht - erst normal updaten.")
    return daten


# ---------------------------------------------------------------- Lizenz (data/premium.json)
def _pfad(root) -> Path:
    return Path(root) / "data" / "premium.json"


def lizenz(root) -> dict:
    try:
        d = json.loads(_pfad(root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _speichern(root, d: dict) -> None:
    p = _pfad(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def stufe(root, jetzt: float | None = None) -> str | None:
    """'premium' / 'max', solange die Laufzeit gilt und der Code nicht gesperrt ist - sonst None."""
    d = lizenz(root)
    if d.get("gesperrt"):
        return None
    if d.get("stufe") in STUFEN and float(d.get("bis") or 0) > (jetzt or time.time()):
        return d["stufe"]
    return None


def sperrliste_lesen(blob: bytes, n: int = None) -> dict:
    """Signierte Sperrliste {"gesperrt":[nonce...], "kennungen":[...], "stand":ts}. Nur mit gueltiger
    Unterschrift des Entwicklers. Wirft PremiumFehler, wenn die Unterschrift fehlt/falsch ist."""
    try:
        huelle = json.loads(blob)
        daten = _b64d(huelle["daten"]) if isinstance(huelle, dict) and "daten" in huelle else None
        sig = base64.b64decode(huelle.get("sig", "")) if isinstance(huelle, dict) else b""
    except (ValueError, KeyError, TypeError) as exc:
        raise PremiumFehler("Sperrliste unlesbar.") from exc
    if daten is None or not signatur_ok(daten, sig, n):
        raise PremiumFehler("Sperrliste ist nicht vom Entwickler unterschrieben.")
    liste = json.loads(daten)
    return liste if isinstance(liste, dict) else {}


def sperrung_pruefen(root, holen: Callable[[str, str], bytes] = None, n: int = None) -> bool:
    """Prueft beim Entwickler-Repo, ob dieser Code gesperrt wurde. Gibt True zurueck, wenn JETZT gesperrt
    wird (dann ist Premium weg). Ohne Netz/ohne Zugang bleibt der letzte Stand - ein zahlender Nutzer wird
    durch fehlendes Netz nie ausgesperrt."""
    holen = holen or _github
    d = lizenz(root)
    if not d.get("stufe") or not d.get("zugang"):
        return False
    try:
        liste = sperrliste_lesen(holen(d["zugang"], SPERR_PFAD), n)
    except PremiumFehler as exc:
        if "unterschrieben" in str(exc):          # da liegt was Falsches - nicht darauf hereinfallen
            logger.warning("Premium: Sperrliste ungueltig")
        return False
    except Exception:  # noqa: BLE001 - kein Netz, 404 (noch keine Liste): Stand lassen
        return False
    gesperrt = (d.get("nonce") in set(liste.get("gesperrt") or [])
                or kennung(root) in set(liste.get("kennungen") or []))
    if gesperrt and not d.get("gesperrt"):
        d["gesperrt"] = True
        d["gesperrt_am"] = time.time()
        _speichern(root, d)
        try:
            paket_pfad(root).unlink(missing_ok=True)      # das Premium-Paket vom Geraet nehmen
        except OSError:
            pass
        return True
    if not gesperrt and d.get("gesperrt"):           # Entwickler hat wieder entsperrt
        d.pop("gesperrt", None)
        d.pop("gesperrt_am", None)
        _speichern(root, d)
    return False


def einloesen(root, code: str, jetzt: float | None = None, n: int = None) -> dict:
    """Code pruefen und einloesen. Gibt die neue Lizenz zurueck. Wirft PremiumFehler."""
    jetzt = jetzt or time.time()
    c = code_lesen(code, n)
    if c.get("k") != kennung(root):
        raise PremiumFehler("Dieser Code gehoert zu einem anderen Geraet. Deine Kennung: " + kennung(root))
    if float(c.get("b") or 0) < jetzt:
        raise PremiumFehler("Dieser Code ist abgelaufen (nicht rechtzeitig eingeloest) - bitte einen neuen anfordern.")
    alt = lizenz(root)
    benutzt = list(alt.get("benutzt") or [])
    if c.get("n") in benutzt:
        raise PremiumFehler("Dieser Code wurde schon eingeloest - jeder Code gilt nur einmal.")
    benutzt = (benutzt + [c.get("n")])[-200:]
    if c.get("t") == "aus":
        neu = {"benutzt": benutzt, "stufe": None, "bis": 0}
    elif c.get("t") in STUFEN:
        dauer = float(c.get("d") or 0) or max(1, int(c.get("m") or 1)) * 30 * _TAG   # Sekunden (Stunden..Jahre)
        dauer = max(60.0, min(dauer, 10 * 365 * _TAG))
        start = max(jetzt, float(alt.get("bis") or 0)) if alt.get("stufe") == c["t"] else jetzt
        neu = {"benutzt": benutzt, "stufe": c["t"], "bis": start + dauer, "nonce": c.get("n"),
               "schluessel": c.get("s", ""), "zugang": c.get("g", ""), "eingeloest": jetzt}
    else:
        raise PremiumFehler("Unbekannte Stufe im Code.")
    _speichern(root, neu)
    return neu


def status_text(root) -> str:
    d, st = lizenz(root), stufe(root)
    if st:
        bis = time.strftime("%d.%m.%Y %H:%M", time.localtime(float(d["bis"])))
        paket = "geladen" if paket_pfad(root).exists() else "noch nicht geladen"
        return f"{STUFEN[st]} aktiv bis {bis} (Paket {paket})."
    if d.get("stufe") in STUFEN:
        return "Premium ist abgelaufen."
    return "Kein Premium."


# ---------------------------------------------------------------- Premium-Paket (privates Repo)
def paket_pfad(root) -> Path:
    return Path(root) / "data" / "premium" / "paket.zip"


def _github(zugang: str, pfad: str, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(f"https://api.github.com/repos/{PAKET_REPO}/contents/{pfad}",
                                 headers={"Authorization": f"Bearer {zugang}",
                                          "Accept": "application/vnd.github.raw+json",
                                          "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as exc:
        raise PremiumFehler(f"Premium-Paket nicht erreichbar ({exc.code}) - der Zugang im Code ist evtl. "
                            "abgelaufen.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise PremiumFehler("Keine Verbindung - spaeter nochmal /novaaiupdate.") from exc


def paket_entpacken(blob: bytes, schluessel: str, n: int = None) -> tuple[bytes, str, dict]:
    """Verschluesselt (wie der Abgleich) -> (zip, signatur, info). Die Unterschrift des Entwicklers muss passen."""
    from .abgleich import AbgleichFehler, entschluesseln

    try:
        d = entschluesseln(blob, schluessel)
    except AbgleichFehler as exc:
        raise PremiumFehler("Das Premium-Paket passt nicht zu deinem Code.") from exc
    roh, sig = base64.b64decode(d.get("zip") or ""), str(d.get("sig") or "")
    if not signatur_ok(roh, base64.b64decode(sig), n):
        raise PremiumFehler("Das Premium-Paket ist nicht vom Entwickler unterschrieben - wird nicht geladen.")
    return roh, sig, d.get("info") or {}


def paket_holen(root, holen: Callable[[str, str], bytes] = _github, n: int = None) -> dict:
    """Neuestes Paket laden (nur mit gueltiger Lizenz). Gibt die Paket-Info (Version ...) zurueck."""
    if not stufe(root):
        raise PremiumFehler("Kein gueltiges Premium - erst einen Code einloesen.")
    d = lizenz(root)
    if not d.get("zugang") or not d.get("schluessel"):
        raise PremiumFehler("Dieser Code enthaelt keinen Paket-Zugang - bitte beim Entwickler melden.")
    roh, sig, info = paket_entpacken(holen(d["zugang"], PAKET_PFAD), d["schluessel"], n)
    with zipfile.ZipFile(io.BytesIO(roh)) as z:
        if "nova_premium/__init__.py" not in z.namelist():
            raise PremiumFehler("Das Premium-Paket ist unvollstaendig.")
    ziel = paket_pfad(root)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(roh)
    (ziel.parent / "paket.sig").write_text(json.dumps({"sig": sig, "info": info}), encoding="utf-8")
    return info


def laden(root, ctl, n: int = None, sperrung=True):
    """Beim Start: gueltige Lizenz + unterschriebenes Paket -> nova_premium.registrieren(ctl, stufe).
    sperrung=True: vorher beim Entwickler-Repo nachsehen, ob der Code zurueckgenommen wurde."""
    import importlib

    if sperrung:
        try:
            sperrung_pruefen(root, n=n)        # gesperrt? -> stufe() ist danach None, nichts wird geladen
        except Exception:  # noqa: BLE001
            pass
    st = stufe(root)
    pfad = paket_pfad(root)
    if not st or not pfad.exists():
        return None
    try:
        sig = json.loads((pfad.parent / "paket.sig").read_text(encoding="utf-8")).get("sig") or ""
    except (OSError, ValueError):
        return None
    if not signatur_ok(pfad.read_bytes(), base64.b64decode(sig), n):   # auf der Platte veraendert: nicht laden
        return None
    for name in [m for m in sys.modules if m == "nova_premium" or m.startswith("nova_premium.")]:
        sys.modules.pop(name, None)
    eintrag = str(pfad)
    if eintrag not in sys.path:
        sys.path.insert(0, eintrag)
    modul = importlib.import_module("nova_premium")
    if hasattr(modul, "registrieren"):
        modul.registrieren(ctl, st)
    return modul


# ---------------------------------------------------------------- Codegenerator (nur Entwickler, /codegenerator 13679)
GENERATOR_PFAD = "werkzeuge/codegenerator.py"


def codegenerator_holen(root, holen: Callable[[str, str], bytes] = _github) -> Path:
    """Laedt den Codegenerator aus dem privaten Repo. Braucht NOVA_PREMIUM_TOKEN (Lesezugang) in der Umgebung
    - das ist bewusst NICHT in einem Code, sondern nur beim Entwickler gesetzt. Als KI.exe die fertige .exe,
    aus dem Quellcode die .py."""
    import os

    token = os.environ.get("NOVA_PREMIUM_TOKEN", "").strip()
    if not token:
        raise PremiumFehler("Dafuer muss NOVA_PREMIUM_TOKEN (Lesezugang zum privaten Repo) in der .env stehen.")
    exe = getattr(sys, "frozen", False)
    daten = holen(token, "werkzeuge/Nova-Codegenerator.exe" if exe else GENERATOR_PFAD)
    ziel = Path(root) / "data" / "premium" / ("Nova-Codegenerator.exe" if exe else "codegenerator.py")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(daten)
    return ziel


def codegenerator_starten(pfad, popen=None) -> None:
    import subprocess

    popen = popen or subprocess.Popen
    pfad = Path(pfad)
    befehl = [str(pfad)] if pfad.suffix.lower() == ".exe" else [sys.executable, str(pfad)]
    popen(befehl, cwd=str(pfad.parent))


# ---------------------------------------------------------------- Simulation (nur Entwickler, /simulation novaai.13696)
# Schaltet Premium oertlich zum TESTEN frei - ohne echten Code und ohne das private Paket. Die hier gezeigten
# "Simulations-Werkzeuge" sind nur eine Demo, nicht der echte Premium-Inhalt (der bleibt im privaten Repo).
SIM_PIN = "novaai.13696"
_SIM_DAUER = 2 * 3600


def simulation_status(root) -> str:
    sim = lizenz(root).get("sim") or {}
    if sim.get("stufe") and float(sim.get("bis") or 0) > time.time():
        rest = int((float(sim["bis"]) - time.time()) / 60)
        return f"Simulation AN ({STUFEN.get(sim['stufe'], sim['stufe'])}, noch {rest} Min.)."
    return "Simulation aus."


def simulation_umschalten(root, pin: str, stufe: str = "max") -> str:
    if pin != SIM_PIN:
        raise PremiumFehler("Falscher Simulations-Code.")
    d = lizenz(root)
    sim = d.get("sim") or {}
    an = not (sim.get("stufe") and float(sim.get("bis") or 0) > time.time())
    if an:
        d["sim"] = {"stufe": stufe if stufe in STUFEN else "max", "bis": time.time() + _SIM_DAUER}
        _speichern(root, d)
        return "test_an"
    d.pop("sim", None)
    _speichern(root, d)
    return "test_aus"


def _sim_demo_werkzeuge(stufe: str):
    from assistant.permissions import Risk          # noqa: F401
    from assistant.tools.base import Tool, ToolContext

    class SimInfo(Tool):
        name = "premium_demo"
        description = ("SIMULATION: zeigt, dass Premium geladen ist (nur Demo, nicht der echte Premium-Inhalt). "
                       "Nutze es, wenn dein Mensch die Premium-Freischaltung testen will.")
        input_schema = {"type": "object", "properties": {}}

        def run(self, ctx: ToolContext) -> str:
            return (f"Simulation aktiv - Stufe {STUFEN.get(stufe, stufe)}. So wuerde sich echtes Premium anfuehlen. "
                    "Die echten Premium-Werkzeuge kommen aus dem privaten Paket (/novaaiupdate mit gueltigem Code).")

    return [SimInfo()]


def simulation_laden(root, ctl) -> str | None:
    """Beim Start bzw. nach dem Umschalten: wenn Simulation aktiv ist, Premium so registrieren wie echt -
    das echte Paket, wenn es da ist, sonst die Demo-Werkzeuge."""
    sim = lizenz(root).get("sim") or {}
    if not (sim.get("stufe") and float(sim.get("bis") or 0) > time.time()):
        return None
    st = sim["stufe"]
    if paket_pfad(root).exists():
        try:
            laden(root, ctl)
        except Exception:  # noqa: BLE001
            pass
    for werkzeug in _sim_demo_werkzeuge(st):
        ctl.registry.register(werkzeug)
    return st
