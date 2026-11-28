"""Proaktive Nova: meldet sich von selbst zur passenden Zeit - aber nur, wenn es wirklich etwas Hilfreiches
gibt, und mit strengen Grenzen (Ruhezeiten, Tageslimit, Mindestabstand, nur wenn gerade niemand mit Nova
beschaeftigt ist). Hier liegen nur die Einstellungen + die Entscheidung "darf ich jetzt?" (gut testbar);
die eigentliche Wortmeldung macht der Controller ueber brain.wortmeldung (sagt sonst nur [still]).

Aus (an=False) ist der Standard - der Nutzer schaltet es bewusst ein (Premium-Werkzeug premium_proaktiv).
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

STANDARD = {"an": False, "von": "08:00", "bis": "21:00", "max_pro_tag": 3, "min_abstand_min": 180,
            "pruef_min": 10, "heute": "", "heute_zahl": 0, "letzte": 0.0}


def _pfad(root) -> Path:
    return Path(root) / "data" / "proaktiv.json"


def einstellungen(root) -> dict:
    d = dict(STANDARD)
    try:
        geladen = json.loads(_pfad(root).read_text(encoding="utf-8"))
        if isinstance(geladen, dict):
            d.update({k: geladen[k] for k in geladen if k in STANDARD})
    except (OSError, ValueError):
        pass
    return d


def speichern(root, d: dict) -> None:
    p = _pfad(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def setzen(root, **werte) -> dict:
    d = einstellungen(root)
    for k, v in werte.items():
        if k in STANDARD and v is not None:
            d[k] = v
    speichern(root, d)
    return d


def _minute(hhmm: str, fallback: int) -> int:
    try:
        h, m = str(hhmm).split(":")
        return max(0, min(23, int(h))) * 60 + max(0, min(59, int(m)))
    except (ValueError, AttributeError):
        return fallback


def _im_fenster(jetzt_dt: datetime, von: str, bis: str) -> bool:
    n = jetzt_dt.hour * 60 + jetzt_dt.minute
    a, b = _minute(von, 8 * 60), _minute(bis, 21 * 60)
    return a <= n <= b if a <= b else (n >= a or n <= b)   # b<a = ueber Nacht


def faellig(root, now: float | None = None, idle: bool = True, e: dict | None = None) -> bool:
    """Darf Nova sich JETZT von selbst melden? Prueft Schalter, Ruhezeit, Tageslimit, Mindestabstand, Ruhe."""
    e = e or einstellungen(root)
    if not e.get("an") or not idle:
        return False
    now = now or time.time()
    jetzt_dt = datetime.fromtimestamp(now)
    if not _im_fenster(jetzt_dt, e.get("von", "08:00"), e.get("bis", "21:00")):
        return False
    heute = jetzt_dt.strftime("%Y-%m-%d")
    zahl = e.get("heute_zahl", 0) if e.get("heute") == heute else 0
    if zahl >= int(e.get("max_pro_tag", 3)):
        return False
    if now - float(e.get("letzte", 0) or 0) < int(e.get("min_abstand_min", 180)) * 60:
        return False
    return True


def notieren(root, now: float | None = None) -> None:
    """Merkt sich, dass gerade proaktiv gemeldet wurde (fuer Tageslimit + Mindestabstand)."""
    now = now or time.time()
    d = einstellungen(root)
    heute = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    d["heute_zahl"] = (d.get("heute_zahl", 0) if d.get("heute") == heute else 0) + 1
    d["heute"] = heute
    d["letzte"] = now
    speichern(root, d)


def status_text(root) -> str:
    e = einstellungen(root)
    if not e.get("an"):
        return "Proaktive Meldungen sind AUS. Einschalten: /proaktiv an (oder im Premium-Werkzeug)."
    return (f"Proaktive Meldungen sind AN: zwischen {e['von']} und {e['bis']}, hoechstens {e['max_pro_tag']} pro Tag, "
            f"Mindestabstand {e['min_abstand_min']} Min. Nova meldet sich nur, wenn es wirklich etwas Sinnvolles gibt.")
