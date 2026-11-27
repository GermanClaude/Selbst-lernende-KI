"""Aussehen der App - Nova passt es an die Wuensche ihres Menschen an.

Bewusst nur Aussehen (Farben, Schrift, Abstaende, Texte, Design-Vorlage, Hintergrundbild,
eigenes CSS) und kein Programm-Code: so kann nichts kaputtgehen und ein Update ueberschreibt
nichts (die Dateien hier stehen in updater._PROTECTED_* - Updates fassen sie nie an).
  config/app-anpassung.json  - einfache Einstellungen (Akzentfarbe, Schriftgroesse, Vorlage ...)
  config/app-anpassung.css   - eigenes CSS (wird nach dem App-CSS geladen)
  config/app-hintergrund.*   - selbst gewaehltes Hintergrundbild
'Zuruecksetzen' stellt das Original wieder her.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

JSON_FILE = "app-anpassung.json"
CSS_FILE = "app-anpassung.css"
HINTERGRUND_PREFIX = "app-hintergrund"
_MAX_CSS = 30_000
_MAX_HINTERGRUND = 6 * 1024 * 1024  # 6 MB - groesser macht /custom.css zu langsam

CHOICES = {
    "ecken": ("eckig", "normal", "rund"),
    "dichte": ("kompakt", "normal", "luftig"),
    "avatar": ("sphaere", "buchstabe"),           # Novas Gesicht: leuchtende Sphaere oder Buchstabe
    "bewegung": ("ruhig", "normal", "lebhaft"),   # wie lebendig die Sphaere sich bewegt
    "stil": ("cockpit", "neon", "einfach", "klassisch"),   # Gesamt-Stil der App (siehe app.css "STILE")
}
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")

# Fertige Design-Vorlagen. Jede setzt ein paar CSS-Variablen der App (die die App-Oberflaeche
# ueberall verwendet) sowie eine passende Akzent- und Sphaeren-Farbe. "schrift" (optional) stellt
# die Schriftart um (z.B. Monospace fuer den Hacker-Look).
THEMES = {
    "hacker": {
        "name": "Hacker (Terminal-Gruen)", "akzent": "#21f368", "sphaere": "#21f368",
        "schrift": "ui-monospace, 'Cascadia Code', 'Consolas', monospace",
        "vars": {"bg": "#000700", "bg-sidebar": "#020a02", "surface": "#030f03", "surface-2": "#051705",
                 "surface-3": "#0a230a", "border": "#124512", "border-strong": "#1c6b1c",
                 "text": "#6bff6b", "text-2": "#39d939", "text-3": "#27a327"},
    },
    "mitternacht": {
        "name": "Mitternacht (Tiefblau)", "akzent": "#4f8cff", "sphaere": "#4f8cff",
        "vars": {"bg": "#070b18", "bg-sidebar": "#0a1020", "surface": "#0d1426", "surface-2": "#121b31",
                 "surface-3": "#1a2642", "border": "#213052", "border-strong": "#2d4070",
                 "text": "#e6ecff", "text-2": "#aeb9d8", "text-3": "#7f8bb0"},
    },
    "dracula": {
        "name": "Dracula (Lila/Pink)", "akzent": "#bd93f9", "sphaere": "#ff79c6",
        "vars": {"bg": "#1a1b26", "bg-sidebar": "#21222e", "surface": "#282a36", "surface-2": "#333547",
                 "surface-3": "#44475a", "border": "#3b3d4f", "border-strong": "#565872",
                 "text": "#f8f8f2", "text-2": "#c9cadf", "text-3": "#9699b5"},
    },
    "retro": {
        "name": "Retro (Bernstein-Terminal)", "akzent": "#ffb000", "sphaere": "#ffb000",
        "schrift": "ui-monospace, 'Cascadia Code', 'Consolas', monospace",
        "vars": {"bg": "#140d00", "bg-sidebar": "#1b1200", "surface": "#201600", "surface-2": "#2c1f00",
                 "surface-3": "#3a2a00", "border": "#4d3900", "border-strong": "#6b5100",
                 "text": "#ffcf6b", "text-2": "#d9a93a", "text-3": "#a37f27"},
    },
    "pastell": {
        "name": "Pastell (hell & sanft)", "akzent": "#e86a9c", "sphaere": "#e86a9c",
        "vars": {"bg": "#fdf5f8", "bg-sidebar": "#fbeef3", "surface": "#ffffff", "surface-2": "#faf0f5",
                 "surface-3": "#f3e2ea", "border": "#f0d9e4", "border-strong": "#e6c2d3",
                 "text": "#3a2630", "text-2": "#6b4f5c", "text-3": "#9c7f8c"},
    },
    "sonne": {
        "name": "Sonne (warm & hell)", "akzent": "#e8690b", "sphaere": "#e8690b",
        "vars": {"bg": "#fdf8f0", "bg-sidebar": "#faf1e3", "surface": "#ffffff", "surface-2": "#fbf3e7",
                 "surface-3": "#f3e6d2", "border": "#f0e0c8", "border-strong": "#e6ceab",
                 "text": "#2b2016", "text-2": "#5f5242", "text-3": "#8a7a64"},
    },
}


def thema_namen() -> list[str]:
    return list(THEMES)


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
        if key in ("akzentfarbe", "sphaere_farbe"):
            if not _HEX.match(str(value)):
                raise ValueError(f"{key} bitte als Hex-Farbe, z.B. #22c55e")
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
    for p in _dir(root).glob(HINTERGRUND_PREFIX + ".*"):
        p.unlink(missing_ok=True)


# -- Design-Vorlagen -----------------------------------------------------------------
_THEMA_AUS = ("", "aus", "original", "standard", "keine", "keins", "none", "normal")


def set_thema(root: Path, name: str) -> dict:
    """Eine Design-Vorlage waehlen (siehe THEMES) oder mit "aus" zuruecksetzen. Setzt passend auch
    die Akzent- und Sphaeren-Farbe (die die App ueber JavaScript anwendet)."""
    name = str(name or "").strip().lower()
    current = load(root)
    if name in _THEMA_AUS:
        for key in ("thema", "akzentfarbe", "sphaere_farbe"):
            current.pop(key, None)
    elif name in THEMES:
        th = THEMES[name]
        current["thema"] = name
        current["akzentfarbe"] = th["akzent"]
        current["sphaere_farbe"] = th["sphaere"]
    else:
        raise ValueError(f"Diese Vorlage gibt es nicht. Moeglich: {', '.join(THEMES)} (oder 'aus').")
    _dir(root).mkdir(parents=True, exist_ok=True)
    (_dir(root) / JSON_FILE).write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def _thema_css(name: str) -> str:
    th = THEMES.get(name)
    if not th:
        return ""
    vars_css = ";".join(f"--{k}:{v}" for k, v in th["vars"].items())
    block = f':root,:root[data-theme="light"],:root[data-theme="dark"]{{{vars_css}}}'
    dark = f'@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{{vars_css}}}}}'
    schrift = th.get("schrift")
    body = f"body{{font-family:{schrift} !important}}" if schrift else ""
    return block + dark + body


# -- Hintergrundbild -----------------------------------------------------------------
_BILD_MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
              "webp": "image/webp", "gif": "image/gif"}


def set_hintergrund(root: Path, daten: bytes, endung: str, deckkraft: float = 0.35) -> dict:
    """Ein Hintergrundbild setzen (Bytes + Endung). Wird als config/app-hintergrund.<endung>
    gespeichert und in /custom.css als data:-URL eingebettet (ein Update fasst es nie an)."""
    endung = str(endung or "").lstrip(".").lower()
    if endung == "jpe":
        endung = "jpg"
    if endung not in _BILD_MIME:
        raise ValueError("Nur PNG, JPG, WebP oder GIF als Hintergrundbild.")
    if not daten or len(daten) > _MAX_HINTERGRUND:
        raise ValueError(f"Das Bild ist zu gross (hoechstens {_MAX_HINTERGRUND // 1024 // 1024} MB).")
    try:
        deckkraft = min(0.92, max(0.0, float(deckkraft)))
    except (TypeError, ValueError):
        deckkraft = 0.35
    _dir(root).mkdir(parents=True, exist_ok=True)
    for p in _dir(root).glob(HINTERGRUND_PREFIX + ".*"):
        p.unlink(missing_ok=True)
    (_dir(root) / f"{HINTERGRUND_PREFIX}.{endung}").write_bytes(daten)
    current = load(root)
    current["hintergrund"] = {"datei": f"{HINTERGRUND_PREFIX}.{endung}", "deckkraft": round(deckkraft, 2)}
    (_dir(root) / JSON_FILE).write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def clear_hintergrund(root: Path) -> dict:
    for p in _dir(root).glob(HINTERGRUND_PREFIX + ".*"):
        p.unlink(missing_ok=True)
    current = load(root)
    current.pop("hintergrund", None)
    _dir(root).mkdir(parents=True, exist_ok=True)
    (_dir(root) / JSON_FILE).write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def _hintergrund_css(root: Path) -> str:
    hg = load(root).get("hintergrund")
    if not isinstance(hg, dict):
        return ""
    datei = _dir(root) / str(hg.get("datei", ""))
    try:
        raw = datei.read_bytes()
    except OSError:
        return ""
    mime = _BILD_MIME.get(datei.suffix.lstrip(".").lower(), "image/jpeg")
    try:
        deck = min(0.92, max(0.0, float(hg.get("deckkraft", 0.35))))
    except (TypeError, ValueError):
        deck = 0.35
    b64 = base64.b64encode(raw).decode("ascii")
    # Bild auf den Hintergrund, mit abdunkelndem Schleier, damit der Text lesbar bleibt.
    return (f":root{{--nova-bg-schleier:rgba(0,0,0,{deck})}}"
            "body{background-image:linear-gradient(var(--nova-bg-schleier),var(--nova-bg-schleier)),"
            f"url(data:{mime};base64,{b64}) !important;background-size:cover !important;"
            "background-position:center !important;background-attachment:fixed !important;}"
            "#app,#chat-scroll,#messages{background:transparent !important}")


def generated_css(root: Path) -> str:
    """Von Nova erzeugtes CSS (Design-Vorlage + Hintergrundbild). Kommt VOR dem eigenen CSS des
    Nutzers, damit sein handgeschriebenes CSS gewinnt."""
    thema = str(load(root).get("thema") or "")
    return "\n".join(t for t in (_thema_css(thema), _hintergrund_css(root)) if t)


def describe(root: Path) -> str:
    data = load(root)
    custom = css(root)
    parts = []
    if data.get("thema") in THEMES:
        parts.append(f"Design-Vorlage: {THEMES[data['thema']]['name']}")
    if isinstance(data.get("hintergrund"), dict):
        parts.append("Hintergrundbild: gesetzt")
    parts += [f"{k} = {v}" for k, v in data.items() if k not in ("thema", "hintergrund")]
    if not parts:
        parts.append("(keine Einstellungen - Original-Aussehen)")
    parts.append(f"eigenes CSS: {len(custom)} Zeichen" if custom else "eigenes CSS: keins")
    parts.append("Dein Design bleibt bei Updates erhalten - ein Update aendert es nie.")
    return "Aktuelles Aussehen der App:\n- " + "\n- ".join(parts)
