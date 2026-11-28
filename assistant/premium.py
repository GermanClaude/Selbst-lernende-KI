"""Nova Premium (geschlossen): Freischaltung per Code und Premium-Paket aus einem privaten Repo.

Hier steht nur das Schloss - nicht die Premium-Funktionen selbst. Die liegen in einem privaten GitHub-Repo.
Nur der Lizenzserver (Cloud-Nova des Entwicklers, assistant/lizenzserver.py) hat dafuer einen Lesezugang und
gibt das unterschriebene Paket nur gegen einen gueltigen Code heraus. Ein Code enthaelt NICHTS Geheimes.

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
import hmac
import io
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
import zipfile
import zlib
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
        "PC-Gesundheitscheck: Speicherplatz, groesste Dateien, Autostarts - mit Tipps (premium_pc_check)",
        "Lernkarten mit Wiederholungssystem - Nova fragt dich ab (premium_lernkarten)",
        "Gewohnheiten-Tracker mit Serien (premium_gewohnheiten)",
        "Haushaltsbuch mit Budgets und Monatsauswertung (premium_haushaltsbuch)",
        "Agententeam: grosse Aufgaben automatisch aufteilen und abarbeiten lassen (premium_agententeam)",
        "Edlere Premium-Optik in der App",
    ],
    "max": [
        "Alles aus Premium",
        "Fokus-Bloecke mit Erinnerungen (premium_fokus)",
        "Sehr lange Texte/Dateien gruendlich zusammenfassen (premium_lang_zusammenfassen)",
        "Ordner-Autopilot: sortiert z.B. Downloads automatisch - mit Vorschau und Rueckgaengig",
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


def uebersicht(root=None, jetzt: float | None = None) -> dict:
    """Alle Stufen mit ihren Funktionen - fuer eine Uebersicht in der App und im Terminal.
    'aktiv' ist die gerade gueltige Stufe (oder None), damit die App sie hervorheben kann."""
    aktiv = stufe(root, jetzt) if root is not None else None
    stufen = [{"stufe": s, "name": STUFEN.get(s, s), "funktionen": list(FUNKTIONEN.get(s, [])),
               "aktiv": s == aktiv} for s in ("premium", "max", "dev")]
    return {"aktiv": aktiv, "aktiv_name": (STUFEN.get(aktiv) if aktiv else None), "stufen": stufen}


def uebersicht_text(root=None, jetzt: float | None = None) -> str:
    """Dieselbe Uebersicht als lesbarer Text (fuer das Terminal und zum Vorlesen)."""
    u = uebersicht(root, jetzt)
    zeilen = ["Was die Nova-Stufen koennen:"]
    for s in u["stufen"]:
        marke = "  <- deine Stufe" if s["aktiv"] else ""
        zeilen.append(f"\n{s['name']} ({s['stufe']}){marke}")
        zeilen += ["  - " + f for f in s["funktionen"]]
    if not u["aktiv"]:
        zeilen.append("\nDu hast aktuell keine Stufe freigeschaltet.")
    return "\n".join(zeilen)
PAKET_REPO = "GermanClaude/Nova-Premium"   # privat - nur der Lizenzserver hat einen Lesezugang
SPERR_PFAD = "pakete/gesperrt.json"       # signierte Liste gesperrter Codes (Entwickler kann Zugang zuruecknehmen)
FREI_PFAD = "pakete/freischaltung.json"   # signierte Liste: Stufen, die der Entwickler per Geraete-Kennung
                                          # vergibt - ohne dass der Nutzer einen Code abtippen muss (No-Code)
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


_PRUEF_CACHE: dict = {}


def _codes(d: dict) -> list[str]:
    codes = d.get("codes")
    if isinstance(codes, list):
        return [str(c) for c in codes if isinstance(c, str)][-50:]
    return [str(d["code"])] if isinstance(d.get("code"), str) else []


def _hoechstens_bis(root, d: dict, n: int = None) -> float:
    """Obergrenze fuer 'bis', nur aus unterschriebenen Codes dieses Geraets und dieser Stufe berechnet:
    max(Einloesefrist) + Summe(Laufzeiten). So bringt es nichts, data/premium.json von Hand zu aendern."""
    schluessel = (tuple(_codes(d)), d.get("stufe"), n or OEFFENTLICH_N)
    if schluessel in _PRUEF_CACHE:
        return _PRUEF_CACHE[schluessel]
    meine, fristen, summe = kennung(root), [], 0.0
    for code in _codes(d):
        try:
            c = code_lesen(code, n)
        except PremiumFehler:
            continue
        if c.get("k") != meine or c.get("t") != d.get("stufe"):
            continue
        dauer = float(c.get("d") or 0) or max(1, int(c.get("m") or 1)) * 30 * _TAG
        summe += max(60.0, min(dauer, 10 * 365 * _TAG))
        fristen.append(float(c.get("b") or 0))
    grenze = (max(fristen) + summe) if fristen else 0.0
    if len(_PRUEF_CACHE) > 64:
        _PRUEF_CACHE.clear()
    _PRUEF_CACHE[schluessel] = grenze
    return grenze


def stufe(root, jetzt: float | None = None, n: int = None) -> str | None:
    """'premium' / 'max' / 'dev', solange die Laufzeit gilt und der Code nicht gesperrt ist - sonst None.
    Die Laufzeit muss durch die gespeicherten, unterschriebenen Codes gedeckt sein (sonst wurde gemogelt)."""
    d = lizenz(root)
    if d.get("gesperrt"):
        return None
    if d.get("stufe") not in STUFEN:
        return None
    bis = min(float(d.get("bis") or 0), _hoechstens_bis(root, d, n))
    return d["stufe"] if bis > (jetzt or time.time()) else None


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


def sperrung_pruefen(root, holen: Callable[[str], bytes] = None, n: int = None) -> bool:
    """Fragt den Lizenzserver, ob dieser Code gesperrt wurde. Gibt True zurueck, wenn JETZT gesperrt wird
    (dann ist Premium weg). Ohne Netz/ohne Server bleibt der letzte Stand - ein zahlender Nutzer wird durch
    fehlendes Netz nie ausgesperrt. Die Liste ist signiert - eine gefaelschte wird ignoriert."""
    holen = holen or _sperrliste_vom_server
    d = lizenz(root)
    server = lizenzserver(d)
    if not d.get("stufe") or not server:
        return False
    try:
        liste = sperrliste_lesen(holen(server), n)
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
        # Nichts Geheimes speichern: nur der (selbst nicht geheime) Code fuer den Lizenzserver und dessen Adresse.
        sauber = "NOVA-" + "".join((code or "").split()).removeprefix("NOVA-").removeprefix("nova-")
        frueher = _codes(alt) if alt.get("stufe") == c["t"] and float(alt.get("bis") or 0) > jetzt else []
        neu = {"benutzt": benutzt, "stufe": c["t"], "bis": start + dauer, "nonce": c.get("n"),
               "code": sauber, "codes": (frueher + [sauber])[-50:],
               "server": str(c.get("u") or ""), "eingeloest": jetzt,
               # Individuelles Abo: eigener Anzeigename und (optional) ausgewaehlte Funktionen - beide stehen
               # im Code und sind mit unterschrieben, lassen sich also nicht faelschen.
               "name": str(c.get("name") or "")[:40],
               "features": ([str(f)[:40] for f in c["f"]][:40] if isinstance(c.get("f"), list) else None)}
    else:
        raise PremiumFehler("Unbekannte Stufe im Code.")
    _speichern(root, neu)
    return neu


def freischaltliste_lesen(blob: bytes, n: int = None) -> dict:
    """Signierte Freischaltliste {"codes":[NOVA-...], "stand":ts}. Jeder Eintrag ist ein ganz normaler,
    an EINE Geraete-Kennung gebundener, unterschriebener Code. Die Liste selbst ist zusaetzlich unterschrieben.
    Wirft PremiumFehler, wenn die Unterschrift der Liste fehlt/falsch ist."""
    try:
        huelle = json.loads(blob)
        daten = _b64d(huelle["daten"]) if isinstance(huelle, dict) and "daten" in huelle else None
        sig = base64.b64decode(huelle.get("sig", "")) if isinstance(huelle, dict) else b""
    except (ValueError, KeyError, TypeError) as exc:
        raise PremiumFehler("Freischaltliste unlesbar.") from exc
    if daten is None or not signatur_ok(daten, sig, n):
        raise PremiumFehler("Freischaltliste ist nicht vom Entwickler unterschrieben.")
    liste = json.loads(daten)
    return liste if isinstance(liste, dict) else {}


def freischaltung_pruefen(root, holen: Callable[[str], bytes] = None, n: int = None,
                          jetzt: float | None = None) -> str | None:
    """No-Code-Upgrade: beim Lizenzserver nachsehen, ob der Entwickler diesem Geraet (ueber seine Kennung)
    eine Stufe vergeben/angehoben hat - OHNE dass der Nutzer einen Code abtippt. Jeder Eintrag ist ein
    signierter, an die Kennung gebundene Code; wir loesen den passenden hier einfach selbst ein. So bleibt
    die Stufe nach jedem Update erhalten, ohne dass fuer jeden Nutzer ein neuer Code noetig ist.
    Gibt die neu/weiter freigeschaltete Stufe zurueck oder None. Ohne Netz/ohne Liste bleibt der Stand."""
    holen = holen or _freischaltliste_vom_server
    d = lizenz(root)
    server = lizenzserver(d)
    if not server:
        return None
    try:
        liste = freischaltliste_lesen(holen(server), n)
    except PremiumFehler as exc:
        if "unterschrieben" in str(exc):          # da liegt was Falsches - nicht darauf hereinfallen
            logger.warning("Premium: Freischaltliste ungueltig")
        return None
    except Exception:  # noqa: BLE001 - kein Netz, 404 (noch keine Liste): Stand lassen
        return None
    meine = kennung(root)
    neu = None
    for code in (liste.get("codes") or []):
        if not isinstance(code, str):
            continue
        try:
            c = code_lesen(code, n)
        except PremiumFehler:
            continue
        if c.get("k") != meine or c.get("t") == "aus":
            continue
        try:
            ergebnis = einloesen(root, code, jetzt=jetzt, n=n)   # prueft Bindung/Frist/Einmaligkeit selbst
        except PremiumFehler:
            continue                 # schon eingeloest oder abgelaufen: der naechste Eintrag ist dran
        neu = ergebnis.get("stufe") or neu
    return neu


def anzeigename(root, jetzt: float | None = None) -> str | None:
    """Der (evtl. selbst gewaehlte) Name der aktiven Stufe - fuer die Anzeige in der App. None = kein Premium."""
    st = stufe(root, jetzt)
    if not st:
        return None
    name = (lizenz(root).get("name") or "").strip()
    return name or STUFEN.get(st, "Premium")


def features(root) -> list | None:
    """Welche Funktionen dieses Abo freischaltet (Liste von Schluesseln), oder None = alle der Stufe."""
    f = lizenz(root).get("features")
    return [str(x) for x in f] if isinstance(f, list) else None


def status_text(root) -> str:
    d, st = lizenz(root), stufe(root)
    if st:
        bis = time.strftime("%d.%m.%Y %H:%M", time.localtime(float(d["bis"])))
        if not paket_pfad(root).exists():
            paket = "noch nicht geladen"
        else:
            e = eigentum_info(root)
            paket = "geladen, Herkunft signiert" if (e and e.get("ok")) else "geladen"
        return f"{anzeigename(root)} aktiv bis {bis} (Paket {paket})."
    if d.get("stufe") in STUFEN:
        return "Premium ist abgelaufen."
    return "Kein Premium."


# ---------------------------------------------------------------- Premium-Paket (privates Repo)
def paket_pfad(root) -> Path:
    return Path(root) / "data" / "premium" / "paket.zip"


def eigentum_info(root, n: int = None) -> dict | None:
    """Liest das signierte Eigentums-/Urheber-Kennzeichen (Wasserzeichen) aus dem installierten Paket und
    prueft die Unterschrift gegen den oeffentlichen Schluessel. Gibt {'ok':bool, ...Angaben} zurueck oder
    None, wenn kein Paket/Kennzeichen vorhanden ist. Nur der Entwickler kann so eine Unterschrift erzeugen."""
    pfad = paket_pfad(root)
    if not pfad.exists():
        return None
    try:
        with zipfile.ZipFile(pfad) as z:
            roh = z.read("nova_premium/_eigentum.json")
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    try:
        huelle = json.loads(roh)
        inner = base64.b64decode(huelle["daten"])
        sig = base64.b64decode(huelle["sig"])
    except (ValueError, KeyError, TypeError):
        return None
    ok = signatur_ok(inner, sig, n)
    claim = {}
    if ok:
        try:
            geladen = json.loads(inner)
            if isinstance(geladen, dict):
                claim = {str(k): str(v) for k, v in geladen.items()}
        except ValueError:
            pass
    return {"ok": bool(ok), **claim}


def _github(zugang: str, pfad: str, timeout: float = 60.0) -> bytes:
    """Nur fuer den Codegenerator des Entwicklers (Token aus SEINER .env, nie aus einem Code)."""
    req = urllib.request.Request(f"https://api.github.com/repos/{PAKET_REPO}/contents/{pfad}",
                                 headers={"Authorization": f"Bearer {zugang}",
                                          "Accept": "application/vnd.github.raw+json",
                                          "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as exc:
        raise PremiumFehler(f"Privates Repo nicht erreichbar ({exc.code}) - NOVA_PREMIUM_TOKEN pruefen.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise PremiumFehler("Keine Verbindung - spaeter nochmal.") from exc


# ---------------------------------------------------------------- Lizenzserver (Cloud-Nova des Entwicklers)
def _server_ok(url: str) -> bool:
    """Nur https (oder http auf dem eigenen Rechner zum Testen) - ein Code soll nirgendwo anders hinschicken."""
    url = (url or "").strip()
    if url.startswith("https://") and len(url) > 12 and " " not in url:
        return True
    return url.startswith(("http://127.0.0.1", "http://localhost"))


def lizenzserver(d: dict) -> str:
    """Adresse des Lizenzservers: aus dem eingeloesten Code, sonst NOVA_LIZENZSERVER_URL (Umgebung)."""
    import os

    for kandidat in (str(d.get("server") or ""), os.environ.get("NOVA_LIZENZSERVER_URL", "")):
        if _server_ok(kandidat):
            return kandidat.strip().rstrip("/")
    return ""


def _sperrliste_vom_server(server: str, timeout: float = 20.0) -> bytes:
    with urllib.request.urlopen(server + "/lizenz/sperrliste", timeout=timeout) as r:
        return r.read()


def _freischaltliste_vom_server(server: str, timeout: float = 20.0) -> bytes:
    with urllib.request.urlopen(server + "/lizenz/freischaltung", timeout=timeout) as r:
        return r.read()


def _paket_vom_server(server: str, code: str, kenn: str, timeout: float = 90.0) -> dict:
    """Code + Geraete-Kennung an den Lizenzserver - zurueck kommt das unterschriebene Paket. Kein Token im Spiel."""
    body = json.dumps({"code": code, "kennung": kenn}).encode("utf-8")
    req = urllib.request.Request(server + "/lizenz/paket", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            meldung = json.loads(exc.read().decode("utf-8")).get("meldung")
        except Exception:  # noqa: BLE001
            meldung = None
        raise PremiumFehler(meldung or f"Der Lizenzserver lehnt ab ({exc.code}).") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise PremiumFehler("Der Lizenzserver ist gerade nicht erreichbar - spaeter nochmal /novaaiupdate.") from exc


def _alte_geheimnisse_entfernen(root, d: dict) -> dict:
    """Aeltere Versionen (bis 0.51) haben Token/Schluessel aus dem Code gespeichert - weg damit."""
    if "zugang" in d or "schluessel" in d:
        d.pop("zugang", None)
        d.pop("schluessel", None)
        _speichern(root, d)
    return d


def paket_holen(root, holen: Callable[[str, str, str], dict] = None, n: int = None) -> dict:
    """Neuestes Paket vom Lizenzserver laden (nur mit gueltiger Lizenz). Gibt die Paket-Info zurueck."""
    holen = holen or _paket_vom_server
    if not stufe(root):
        raise PremiumFehler("Kein gueltiges Premium - erst einen Code einloesen.")
    d = _alte_geheimnisse_entfernen(root, lizenz(root))
    server = lizenzserver(d)
    if not d.get("code") or not server:
        raise PremiumFehler("Fuer das Paket braucht es einen neuen Code (mit Lizenzserver) - bitte beim "
                            "Entwickler melden.")
    antwort = holen(server, d["code"], kennung(root))
    if not isinstance(antwort, dict) or not antwort.get("ok"):
        raise PremiumFehler(str((antwort or {}).get("meldung") or "Der Lizenzserver gibt kein Paket heraus."))
    try:
        roh, sig = base64.b64decode(antwort.get("zip") or ""), str(antwort.get("sig") or "")
        sig_roh = base64.b64decode(sig)
    except (ValueError, TypeError) as exc:
        raise PremiumFehler("Antwort des Lizenzservers ist kaputt.") from exc
    if not signatur_ok(roh, sig_roh, n):     # auch ein falscher Server kann kein fremdes Paket unterschieben
        raise PremiumFehler("Das Premium-Paket ist nicht vom Entwickler unterschrieben - wird nicht geladen.")
    try:
        with zipfile.ZipFile(io.BytesIO(roh)) as z:
            if "nova_premium/__init__.py" not in z.namelist():
                raise PremiumFehler("Das Premium-Paket ist unvollstaendig.")
    except zipfile.BadZipFile as exc:
        raise PremiumFehler("Das Premium-Paket ist kaputt.") from exc
    info = antwort.get("info") or {}
    ziel = paket_pfad(root)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(roh)
    (ziel.parent / "paket.sig").write_text(json.dumps({"sig": sig, "info": info}), encoding="utf-8")
    return info


def laden(root, ctl, n: int = None, sperrung=True):
    """Beim Start: gueltige Lizenz + unterschriebenes Paket -> nova_premium.registrieren(ctl, stufe).
    sperrung=True: vorher beim Lizenzserver nachsehen, ob der Code zurueckgenommen wurde."""
    import importlib

    try:
        _alte_geheimnisse_entfernen(root, lizenz(root))
    except OSError:
        pass
    if sperrung:
        try:
            freischaltung_pruefen(root, n=n)   # No-Code-Upgrade: vom Server vergebene Stufe anwenden
        except Exception:  # noqa: BLE001
            pass
        try:
            sperrung_pruefen(root, n=n)        # danach Sperren - eine Sperre hat immer Vorrang
        except Exception:  # noqa: BLE001
            pass
    st = stufe(root)
    if not st:
        return None
    pfad = paket_pfad(root)
    if not pfad.exists():
        # Die Stufe gilt (bezahlt, nicht gesperrt, nicht abgelaufen), nur das Paket fehlt - z.B. nach einem
        # Update/Neuaufsetzen. Dann holen wir es automatisch wieder (signiert), statt Premium zu verlieren.
        try:
            paket_holen(root, n=n)
        except PremiumFehler:
            return None
        if not pfad.exists():
            return None
    if ctl is None:
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
        try:
            modul.registrieren(ctl, st, features=features(root))   # nur ausgewaehlte Funktionen
        except TypeError:
            modul.registrieren(ctl, st)                            # aelteres Paket ohne features-Parameter
    return modul


# ---------------------------------------------------------------- Codegenerator (nur Entwickler)
# Der Codegenerator liegt im privaten Repo NUR VERSCHLUESSELT (mit dem Generator-Passwort). Selbst wer
# Lesezugang zum Repo bekommt, sieht keinen lesbaren Generator-Code. Entschluesselt wird erst hier, lokal,
# wenn der Entwickler sein Generator-Passwort eingibt. Format: _GENV_KOPF + salz(16) + nonce(16) + marke(32)
# + geheim; Encrypt-then-MAC, binaersicher. Dasselbe Verfahren steht im Verschluesselungs-Skript des Repos.
GENERATOR_ENC_PFAD = "werkzeuge/codegenerator.py.enc"
GENERATOR_EXE_ENC_PFAD = "werkzeuge/Nova-Codegenerator.exe.enc"
_GENV_KOPF = b"NOVAGEN1"
_GENV_RUNDEN = 200000


def _genv_schluessel(passwort: str, salz: bytes) -> tuple[bytes, bytes]:
    roh = hashlib.pbkdf2_hmac("sha256", (passwort or "").encode("utf-8"), salz, _GENV_RUNDEN, dklen=64)
    return roh[:32], roh[32:]


def _genv_strom(k: bytes, nonce: bytes, laenge: int) -> bytes:
    roh = b"".join(hmac.new(k, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
                   for i in range((laenge + 31) // 32))
    return roh[:laenge]


def generator_entschluesseln(blob: bytes, passwort: str) -> bytes:
    """Den verschluesselten Generator-Blob aus dem Repo entschluesseln (nur mit dem Generator-Passwort).
    Gibt die Klartext-Bytes zurueck (die .py-Quelle bzw. die .exe). Wirft PremiumFehler bei falschem Passwort."""
    n = len(_GENV_KOPF)
    if not blob.startswith(_GENV_KOPF) or len(blob) < n + 64:
        raise PremiumFehler("Der verschluesselte Generator ist beschaedigt oder hat ein unbekanntes Format.")
    salz, nonce, marke, geheim = blob[n:n + 16], blob[n + 16:n + 32], blob[n + 32:n + 64], blob[n + 64:]
    k_enc, k_mac = _genv_schluessel(passwort, salz)
    if not hmac.compare_digest(marke, hmac.new(k_mac, _GENV_KOPF + salz + nonce + geheim, hashlib.sha256).digest()):
        raise PremiumFehler("Das Generator-Passwort passt nicht (oder die Datei wurde veraendert).")
    strom = _genv_strom(k_enc, nonce, len(geheim))
    klar = (int.from_bytes(geheim, "big") ^ int.from_bytes(strom, "big")).to_bytes(len(geheim), "big") if geheim else b""
    try:
        return zlib.decompress(klar)
    except zlib.error as exc:
        raise PremiumFehler("Der Generator liess sich nicht entschluesseln.") from exc


GENERATOR_PFAD = "werkzeuge/codegenerator.py"   # nur noch fuer aeltere Hinweise - im Repo liegt der .enc-Blob
_CG_SALZ = b"nova-cg-1"
_CG_HASH = "93469410b2f927097437a4079870e29ceb98c0bfa10e9d8002e8a6c57f0e54f0"


def cg_pin_ok(pin: str) -> bool:
    """PIN fuer /codegenerator - nur als Hash im Code (der Klartext steht nur im privaten Generator)."""
    if not pin or len(pin) > 64:
        return False
    h = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), _CG_SALZ, 300000).hex()
    return secrets.compare_digest(h, _CG_HASH)


# -- Generator-Modus: ein Passwort, mit dem der Entwickler Nova den Generator freischaltet. In diesem Modus
#    darf Nova den Generator oeffnen und seine Einrichtung erklaeren (Tokens, Render, Rezensionen). Das Passwort
#    steht nur als Hash im Code; der Klartext liegt beim Entwickler (~/.nova-premium/pins.json).
_GEN_SALZ = b"nova-gen-1"
_GEN_HASH = "f6b29c25d528cab16b9f97223667f9a9d07fcfc19a78ec02bff056e0bec585ba"


def gen_pin_ok(pin: str) -> bool:
    if not pin or len(pin) > 64:
        return False
    h = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), _GEN_SALZ, 300000).hex()
    return secrets.compare_digest(h, _GEN_HASH)


def _gen_pfad(root) -> Path:
    return Path(root) / "data" / "generator.json"


def generator_modus_an(root) -> bool:
    try:
        return bool(json.loads(_gen_pfad(root).read_text(encoding="utf-8")).get("an"))
    except (OSError, ValueError):
        return False


def generator_modus_setzen(root, an: bool) -> None:
    p = _gen_pfad(root)
    if an:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"an": True, "seit": time.time()}), encoding="utf-8")
    else:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def generator_oeffnen(root, passwort: str = ""):
    """Generator-Modus einschalten und den Codegenerator holen + oeffnen. Gibt den Pfad zurueck."""
    generator_modus_setzen(root, True)
    pfad = codegenerator_holen(root, passwort=passwort)
    codegenerator_starten(pfad)
    return pfad


def codegenerator_holen(root, holen: Callable[[str, str], bytes] = _github, passwort: str = "") -> Path:
    """Laedt den (verschluesselten) Codegenerator aus dem privaten Repo und entschluesselt ihn lokal.
    Braucht NOVA_PREMIUM_TOKEN (Lesezugang, nur beim Entwickler) UND das Generator-Passwort (zum Entschluesseln
    - steht nirgends im Repo). Als KI.exe die .exe, aus dem Quellcode die .py."""
    import os

    token = os.environ.get("NOVA_PREMIUM_TOKEN", "").strip()
    if not token:
        raise PremiumFehler("Dafuer muss NOVA_PREMIUM_TOKEN (Lesezugang zum privaten Repo) in der .env stehen.")
    if not (passwort or "").strip():
        raise PremiumFehler("Zum Oeffnen des (verschluesselten) Generators brauche ich einmal dein "
                            "Generator-Passwort - gib es bitte ein.")
    exe = getattr(sys, "frozen", False)
    blob = holen(token, GENERATOR_EXE_ENC_PFAD if exe else GENERATOR_ENC_PFAD)
    daten = generator_entschluesseln(blob, passwort)     # nur mit richtigem Passwort lesbar
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


# ---------------------------------------------------------------- Simulation (nur Entwickler, /simulation <PIN>)
# Schaltet Premium oertlich zum TESTEN frei - ohne echten Code und ohne das private Paket. Die hier gezeigten
# "Simulations-Werkzeuge" sind nur eine Demo, nicht der echte Premium-Inhalt (der bleibt im privaten Repo).
# Nur der Hash steht im Code (PBKDF2) - wer die KI.exe auseinandernimmt, findet den PIN nicht im Klartext.
_SIM_SALZ = b"nova-sim-1"
_SIM_HASH = "01e95b1bd6f4abcd3a17c018630691da0d511458280e0434a6dc7e6a3d678739"


def sim_pin_ok(pin: str) -> bool:
    if not pin or len(pin) > 64:
        return False
    h = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), _SIM_SALZ, 300000).hex()
    return secrets.compare_digest(h, _SIM_HASH)


_SIM_DAUER = 2 * 3600


def simulation_status(root) -> str:
    sim = lizenz(root).get("sim") or {}
    if sim.get("stufe") and float(sim.get("bis") or 0) > time.time():
        rest = int((float(sim["bis"]) - time.time()) / 60)
        return f"Simulation AN ({STUFEN.get(sim['stufe'], sim['stufe'])}, noch {rest} Min.)."
    return "Simulation aus."


def simulation_umschalten(root, pin: str, stufe: str = "max") -> str:
    if not sim_pin_ok(pin):
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
    """Beim Start bzw. nach dem Umschalten: wenn Simulation aktiv ist, die Demo-Werkzeuge registrieren.
    Das echte Paket laedt die Simulation NIE - das gibt es nur mit gueltiger Lizenz (sonst waere die
    Simulation ein Weg, abgelaufenes Premium weiter zu nutzen)."""
    sim = lizenz(root).get("sim") or {}
    if not (sim.get("stufe") and float(sim.get("bis") or 0) > time.time()):
        return None
    st = sim["stufe"]
    for werkzeug in _sim_demo_werkzeuge(st):
        ctl.registry.register(werkzeug)
    return st
