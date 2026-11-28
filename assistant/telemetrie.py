"""Opt-in Nutzer-Uebersicht & Sperren - STANDARD AUS, nie ohne ausdrueckliche Zustimmung.

Wenn (und nur wenn) der Nutzer in der App zustimmt, schickt Nova ab und zu ein paar Eckdaten an den
Entwickler (ueber dasselbe Feedback-Skript wie Bewertungen): Geraete-Kennung, der selbst gewaehlte Name,
die Stufe (gratis/premium), die Nutzungszeit, Version/Betriebssystem und - fuer die manuelle Pruefung durch
den Entwickler - etwaige Sicherheits-Markierungen (z. B. abgelehnte, moeglicherweise illegale Versuche).
KEINE E-Mail, ausser der Nutzer gibt sie selbst an. Jederzeit widerrufbar (dann wird nichts mehr gesendet).

Unabhaengig davon (auch ohne Zustimmung, als Missbrauchsschutz): Nova kann eine SIGNIERTE Sperrliste
abrufen und sich selbst sperren, wenn der Entwickler dieses Geraet gesperrt hat - auch bei Gratis-Nutzern.
Die Liste ist mit dem privaten Entwickler-Schluessel unterschrieben; eine gefaelschte wird ignoriert.
Das Sperren entscheidet IMMER der Entwickler von Hand - hier passiert nichts automatisch.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from . import __version__

logger = logging.getLogger(__name__)

PFAD = "data/telemetrie.json"          # Zustimmung + Name + letzter Ping (lokal, GESPERRT)
PING_ABSTAND_MIN = 180                 # hoechstens alle 3 Stunden etwas senden
_MAX_FLAGS = 50


def _pfad(root) -> Path:
    return Path(root) / "data" / "telemetrie.json"


def _laden(root) -> dict:
    try:
        d = json.loads(_pfad(root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _speichern(root, d: dict) -> None:
    p = _pfad(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        logger.debug("Telemetrie: speichern ging nicht", exc_info=True)


def aktiv(root) -> bool:
    return _laden(root).get("an") is True


def status(root) -> dict:
    d = _laden(root)
    return {"an": d.get("an") is True, "name": d.get("name", ""), "kontakt": d.get("kontakt", ""),
            "zugestimmt_am": d.get("zugestimmt_am", ""), "letzter_ping": d.get("letzter_ping", "")}


def setzen(root, *, an: bool | None = None, name: str | None = None, kontakt: str | None = None) -> dict:
    """Zustimmung setzen/aendern. an=True = erlauben (mit Zeitstempel), an=False = widerrufen."""
    d = _laden(root)
    if an is not None:
        d["an"] = bool(an)
        if an:
            d["zugestimmt_am"] = time.strftime("%Y-%m-%d %H:%M")
        else:
            d["zugestimmt_am"] = ""
    if name is not None:
        d["name"] = " ".join(str(name).split())[:40]
    if kontakt is not None:
        d["kontakt"] = " ".join(str(kontakt).split())[:120]
    _speichern(root, d)
    return status(root)


def flagge(root, grund: str) -> None:
    """Eine Sicherheits-Markierung lokal vormerken (z. B. ein abgelehnter, moeglicherweise illegaler
    Versuch). Wird beim naechsten Ping NUR mitgesendet, wenn der Nutzer zugestimmt hat - sonst bleibt sie
    lokal und dient nur der spaeteren Einordnung. Der Entwickler entscheidet von Hand."""
    grund = " ".join(str(grund or "").split())[:80]
    if not grund:
        return
    d = _laden(root)
    flags = [f for f in (d.get("flags") or []) if isinstance(f, dict)]
    flags.append({"grund": grund, "zeit": time.strftime("%Y-%m-%d %H:%M")})
    d["flags"] = flags[-_MAX_FLAGS:]
    _speichern(root, d)


def ping_faellig(root, *, jetzt: float | None = None, abstand_min: int = PING_ABSTAND_MIN) -> bool:
    if not aktiv(root):
        return False
    letzter = _laden(root).get("letzter_ping_ts")
    if not isinstance(letzter, (int, float)):
        return True
    return (jetzt or time.time()) - letzter >= abstand_min * 60


def _nutzlast(root, config) -> dict:
    from . import geraet
    from . import premium
    from . import feedback

    d = _laden(root)
    try:
        stufe = premium.stufe(root) or "gratis"
    except Exception:  # noqa: BLE001
        stufe = "gratis"
    try:
        minuten = int(feedback.nutzung_sekunden(root) // 60)
    except Exception:  # noqa: BLE001
        minuten = 0
    rezensiert = bool(feedback._lade_stand(root).get("letzte_rezension")) if hasattr(feedback, "_lade_stand") else False
    return {
        "app": "Nova",
        "aktion": "telemetrie",
        "kennung": premium.kennung(root),
        "geraet": geraet.geraet_id(root),
        "name": d.get("name", ""),
        "kontakt": d.get("kontakt", ""),
        "stufe": stufe,
        "nutzung_min": minuten,
        "rezensiert": rezensiert,
        "version": __version__,
        "os": _system(),
        "flags": [f.get("grund", "") for f in (d.get("flags") or []) if isinstance(f, dict)][-20:],
    }


def _system() -> str:
    import platform

    return f"{platform.system()} {platform.release()}"[:40]


def ping(root, config, *, post: Callable | None = None, jetzt: float | None = None) -> bool:
    """Sendet die Eckdaten - NUR wenn zugestimmt. Gibt True bei Erfolg. Fehler werden still geschluckt."""
    if not aktiv(root):
        return False
    from . import feedback

    url = feedback.ziel_url(config)
    if not url:
        return False
    nutzlast = _nutzlast(root, config)
    try:
        koerper = json.dumps(nutzlast, ensure_ascii=True).encode("ascii")
        if post is not None:
            post(url, koerper)
        else:
            import urllib.request

            req = urllib.request.Request(url, data=koerper,
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=15).read()
    except Exception:  # noqa: BLE001 - offline o. ae.: einfach spaeter nochmal
        return False
    jetzt = jetzt or time.time()
    d = _laden(root)
    d["letzter_ping"] = time.strftime("%Y-%m-%d %H:%M")
    d["letzter_ping_ts"] = jetzt
    d["flags"] = []                        # gesendete Markierungen sind beim Entwickler, lokal leeren
    _speichern(root, d)
    return True


def nachrichten_holen(root, config, *, holen: Callable[[str], bytes] | None = None) -> list[dict]:
    """Holt Nachrichten, die der Entwickler an dieses Geraet geschickt hat (Kundendienst). Nur wenn
    zugestimmt - ohne Zustimmung fragt Nova gar nicht erst nach."""
    if not aktiv(root):
        return []
    from . import feedback
    from . import premium

    url = feedback.ziel_url(config)
    if not url:
        return []
    try:
        from urllib.parse import quote

        voll = f"{url}?aktion=nachrichten&kennung={quote(premium.kennung(root))}"
        if holen is not None:
            roh = holen(voll)
        else:
            import urllib.request

            roh = urllib.request.urlopen(voll, timeout=15).read()
        antwort = json.loads(roh)
    except Exception:  # noqa: BLE001
        return []
    nachrichten = antwort.get("nachrichten") if isinstance(antwort, dict) else None
    d = _laden(root)
    gesehen = set(d.get("gesehene_nachrichten") or [])
    out, neue_ids = [], []
    for m in (nachrichten or [])[:20]:
        if not (isinstance(m, dict) and str(m.get("text") or "").strip()):
            continue
        mid = str(m.get("id", ""))[:40]
        if mid and mid in gesehen:
            continue               # schon gezeigt (v. a. Broadcasts nicht erneut melden)
        if mid:
            neue_ids.append(mid)
        out.append({"text": str(m["text"])[:2000], "zeit": str(m.get("zeit", ""))[:20], "id": mid})
    if neue_ids:
        d["gesehene_nachrichten"] = (list(gesehen) + neue_ids)[-200:]
        _speichern(root, d)
    return out


# -- Sperre (auch fuer Gratis-Nutzer; signiert) ---------------------------------------
def sperrliste_holen(root, config, *, holen: Callable[[str], bytes] | None = None, n: int = None) -> dict | None:
    """Holt die vom Entwickler signierte Geraete-Sperrliste vom Feedback-Skript und prueft die
    Unterschrift. Gibt {'geraete':[...], 'kennungen':[...]} oder None (kein Netz / ungueltig)."""
    from . import feedback
    from . import premium

    url = feedback.ziel_url(config)
    if not url:
        return None
    try:
        voll = url + "?aktion=geraete_sperre"
        if holen is not None:
            roh = holen(voll)
        else:
            import urllib.request

            roh = urllib.request.urlopen(voll, timeout=15).read()
        huelle = json.loads(roh)
        daten = feedback_b64d(huelle.get("daten", "")) if isinstance(huelle, dict) else None
        import base64

        sig = base64.b64decode(huelle.get("sig", "")) if isinstance(huelle, dict) else b""
    except Exception:  # noqa: BLE001
        return None
    if daten is None or not premium.signatur_ok(daten, sig, n):
        return None                        # nicht (richtig) unterschrieben -> ignorieren
    try:
        liste = json.loads(daten)
    except ValueError:
        return None
    return liste if isinstance(liste, dict) else None


def feedback_b64d(text: str) -> bytes | None:
    import base64

    try:
        rest = (-len(text)) % 4
        return base64.urlsafe_b64decode(text + "=" * rest)
    except Exception:  # noqa: BLE001
        return None


def ist_gesperrt(root, config, *, holen: Callable[[str], bytes] | None = None, n: int = None) -> bool:
    """True, wenn der Entwickler dieses Geraet gesperrt hat (Kennung ODER stabile Geraete-ID). Ohne Netz/
    ohne gueltige Liste: False (niemand wird durch fehlendes Netz faelschlich ausgesperrt)."""
    from . import geraet
    from . import premium

    liste = sperrliste_holen(root, config, holen=holen, n=n)
    if not liste:
        return False
    gesperrte = set(liste.get("geraete") or []) | set(liste.get("kennungen") or [])
    return premium.kennung(root) in gesperrte or geraet.geraet_id(root) in gesperrte
