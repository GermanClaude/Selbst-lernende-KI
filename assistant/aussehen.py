"""Aussehen der App - Nova passt es an die Wuensche ihres Menschen an.

Bewusst nur Aussehen (Farben, Schrift, Abstaende, Texte, eigenes CSS) und kein
Programm-Code: so kann nichts kaputtgehen und ein Update ueberschreibt nichts.
  config/app-anpassung.json  - einfache Einstellungen (Akzentfarbe, Schriftgroesse ...)
  config/app-anpassung.css   - eigenes CSS (wird nach dem App-CSS geladen)
'Zuruecksetzen' stellt das Original wieder her.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

JSON_FILE = "app-anpassung.json"
CSS_FILE = "app-anpassung.css"
_MAX_CSS = 30_000

CHOICES = {
    "ecken": ("eckig", "normal", "rund"),
    "dichte": ("kompakt", "normal", "luftig"),
}
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")


def _dir(root: Path) -> Path:
    return Path(root) / "config"


def load(root: Path) -> dict:
    try:
        data = json.loads((_dir(root) / JSON_FILE).read_bytes().decode("utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def css(root: Path) -> str:
    try:
        return (_dir(root) / CSS_FILE).read_text(encoding="utf-8")
    except OSError:
        return ""


def validate(changes: dict) -> dict:
    """Prueft die Werte; wirft ValueError mit verstaendlicher Meldung."""
    clean: dict = {}
    for key, value in changes.items():
        if value is None or value == "":
            clean[key] = None  # = zuruecksetzen
            continue
        if key == "akzentfarbe":
            if not _HEX.match(str(value)):
                raise ValueError("akzentfarbe bitte als Hex-Farbe, z.B. #22c55e")
            clean[key] = str(value)
        elif key == "schriftgroesse":
            size = int(value)
            if not 80 <= size <= 140:
                raise ValueError("schriftgroesse bitte zwischen 80 und 140 (Prozent)")
            clean[key] = size
        elif key in CHOICES:
            if value not in CHOICES[key]:
                raise ValueError(f"{key}: moeglich sind {', '.join(CHOICES[key])}")
            clean[key] = value
        elif key == "begruessung":
            clean[key] = str(value)[:300]
        elif key == "beispiele":
            items = [str(v)[:120] for v in (value if isinstance(value, list) else [value]) if str(v).strip()]
            clean[key] = items[:6]
        else:
            raise ValueError(f"Unbekannte Einstellung '{key}'")
    return clean


def save(root: Path, changes: dict) -> dict:
    current = load(root)
    for key, value in validate(changes).items():
        if value is None:
            current.pop(key, None)
        else:
            current[key] = value
    _dir(root).mkdir(parents=True, exist_ok=True)
    (_dir(root) / JSON_FILE).write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def clean_css(text: str) -> str:
    """Nur Aussehen: keine nachgeladenen Dateien/Adressen (das CSP blockt sie ohnehin)."""
    text = re.sub(r"@import[^;]*;?", "", text, flags=re.I)
    text = re.sub(r"url\(\s*['\"]?(?!data:)[^)]*\)", "none", text, flags=re.I)
    text = re.sub(r"expression\s*\(", "(", text, flags=re.I)
    return text[:_MAX_CSS]


def set_css(root: Path, text: str, append: bool = False) -> str:
    new = (css(root) + "\n" + text) if append else text
    new = clean_css(new)
    _dir(root).mkdir(parents=True, exist_ok=True)
    (_dir(root) / CSS_FILE).write_text(new, encoding="utf-8")
    return new


def reset(root: Path) -> None:
    for name in (JSON_FILE, CSS_FILE):
        (_dir(root) / name).unlink(missing_ok=True)


def describe(root: Path) -> str:
    data = load(root)
    custom = css(root)
    parts = [f"{k} = {v}" for k, v in data.items()] or ["(keine Einstellungen - Original-Aussehen)"]
    parts.append(f"eigenes CSS: {len(custom)} Zeichen" if custom else "eigenes CSS: keins")
    return "Aktuelles Aussehen der App:\n- " + "\n- ".join(parts)
