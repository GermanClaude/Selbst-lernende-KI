"""Einstellungen fuer Live-Sehen ([sehen] in settings.toml) - immer geprueft und begrenzt.

Die Datei kann alles enthalten (Tippfehler, NaN, 10000 Bilder pro Sekunde): hier wird daraus
ein Satz sicherer Werte. Die harte Grenze von 360 Wortmeldungen pro Stunde laesst sich nicht
ueberschreiben.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

QUELLEN = ("auto", "bildschirm", "webcam", "beides")
AUFNAHMEN = ("auto", "dxcam", "mss")
AUFMERKSAMKEIT = {"niedrig": 0.8, "normal": 0.6, "hoch": 0.4}
HARTE_GRENZE_WECKUNGEN = 360

# Hier schaut Nova nie hin: Passwort-Manager, Windows-Anmeldung/-Sicherheit, private Browserfenster.
STANDARD_PROGRAMME = (
    "keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe", "dashlane.exe", "enpass.exe",
    "nordpass.exe", "lastpass.exe", "roboform.exe", "credentialuibroker.exe", "consent.exe", "logonui.exe",
    "lockapp.exe",
)
STANDARD_TITEL = (
    "inprivate", "inkognito", "incognito", "privates fenster", "private browsing", "privater modus",
    "keepass", "bitwarden", "1password",
)


def _zahl(wert, unten, oben, standard, ganz: bool = False):
    try:
        if isinstance(wert, bool):
            raise TypeError
        zahl = float(wert)
        if not math.isfinite(zahl):
            return standard
    except (TypeError, ValueError, OverflowError):
        return standard
    zahl = min(oben, max(unten, zahl))
    return int(round(zahl)) if ganz else zahl


def _wahl(wert, erlaubt, standard: str) -> str:
    text = str(wert or "").strip().lower()
    return text if text in erlaubt else standard


def _janein(wert, standard: bool) -> bool:
    if isinstance(wert, bool):
        return wert
    if isinstance(wert, str) and wert.strip().lower() in ("true", "ja", "an", "1"):
        return True
    if isinstance(wert, str) and wert.strip().lower() in ("false", "nein", "aus", "0"):
        return False
    return standard


@dataclass
class SehRegeln:
    """Gepruefte Werte (aus SehenSettings)."""

    quelle: str = "auto"
    aufnahme: str = "auto"
    fps: int = 15
    monitor: int = 0
    schwelle: float = 0.6
    min_abstand: float = 20.0
    max_pro_stunde: int = 20
    max_euro_pro_stunde: float = 0.30
    max_stunden: float = 3.0
    bilder_an_ki: bool = True
    max_kante: int = 1280
    jpeg_qualitaet: int = 75
    ocr: bool = True
    ocr_sprache: str = "de-DE"
    sprechen: bool = True
    bei_abwesenheit: bool = False
    hotkey: str = "Strg+Alt+Umschalt+S"
    ausnahmen: list[str] = field(default_factory=list)


def regeln_aus(settings) -> SehRegeln:
    """SehenSettings (oder etwas Aehnliches) -> SehRegeln mit sicheren Werten."""
    g = lambda name, standard=None: getattr(settings, name, standard)  # noqa: E731
    ausnahmen = g("ausnahmen", []) or []
    if isinstance(ausnahmen, str):
        ausnahmen = [ausnahmen]
    if not isinstance(ausnahmen, (list, tuple)):
        ausnahmen = []
    sauber = [str(a).strip().lower()[:120] for a in ausnahmen if str(a).strip()][:100]
    sprache = str(g("ocr_sprache", "de-DE") or "de-DE").strip()
    if not (2 <= len(sprache) <= 15 and all(c.isalnum() or c == "-" for c in sprache)):
        sprache = "de-DE"
    hotkey = str(g("hotkey_pause", "Strg+Alt+Umschalt+S") or "").strip()[:40]
    return SehRegeln(
        quelle=_wahl(g("quelle"), QUELLEN, "auto"),
        aufnahme=_wahl(g("aufnahme"), AUFNAHMEN, "auto"),
        fps=_zahl(g("fps"), 1, 240, 15, ganz=True),
        monitor=_zahl(g("monitor"), 0, 16, 0, ganz=True),
        schwelle=AUFMERKSAMKEIT[_wahl(g("aufmerksamkeit"), AUFMERKSAMKEIT, "normal")],
        min_abstand=_zahl(g("min_abstand_sekunden"), 5, 600, 20.0),
        max_pro_stunde=_zahl(g("max_weckungen_pro_stunde"), 1, HARTE_GRENZE_WECKUNGEN, 20, ganz=True),
        max_euro_pro_stunde=_zahl(g("max_euro_pro_stunde"), 0.01, 5.0, 0.30),
        max_stunden=_zahl(g("max_stunden"), 0.1, 24.0, 3.0),
        bilder_an_ki=_janein(g("bilder_an_ki"), True),
        max_kante=_zahl(g("max_kante"), 320, 1568, 1280, ganz=True),
        jpeg_qualitaet=_zahl(g("jpeg_qualitaet"), 30, 95, 75, ganz=True),
        ocr=_janein(g("ocr"), True),
        ocr_sprache=sprache,
        sprechen=_janein(g("sprechen"), True),
        bei_abwesenheit=_janein(g("bei_abwesenheit"), False),
        hotkey=hotkey,
        ausnahmen=sauber,
    )


def ist_ausgeschlossen(exe: str | None, titel: str | None, ausnahmen=()) -> bool:
    """Gehoert das Fenster zu einem Programm/Titel, auf das Nova nie schauen darf?

    Eintraege mit .exe am Ende sind Programmnamen, alles andere Teile eines Fenstertitels.
    Gross-/Kleinschreibung egal."""
    name = str(exe or "").replace("\\", "/").rsplit("/", 1)[-1].strip().lower()
    titel_klein = str(titel or "").lower()
    programme = set(STANDARD_PROGRAMME) | {a for a in ausnahmen if a.endswith(".exe")}
    if name and name in programme:
        return True
    muster = list(STANDARD_TITEL) + [a for a in ausnahmen if a and not a.endswith(".exe")]
    return any(m in titel_klein for m in muster)


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """'Strg+Alt+Umschalt+S' -> (Modifier fuer RegisterHotKey, virtueller Tastencode) oder None."""
    mods, vk = 0, None
    namen = {"strg": 0x2, "ctrl": 0x2, "control": 0x2, "alt": 0x1, "umschalt": 0x4, "shift": 0x4,
             "win": 0x8, "windows": 0x8}
    for teil in [t.strip().lower() for t in str(text or "").split("+") if t.strip()]:
        if teil in namen:
            mods |= namen[teil]
        elif len(teil) == 1 and (teil.isalpha() or teil.isdigit()) and teil.isascii():
            if vk is not None:
                return None
            vk = ord(teil.upper())
        elif teil.startswith("f") and teil[1:].isdigit() and 1 <= int(teil[1:]) <= 24:
            if vk is not None:
                return None
            vk = 0x70 + int(teil[1:]) - 1
        else:
            return None
    if vk is None or mods == 0:
        return None
    return mods, vk
