"""Charakter & Profil: wie die KI sein soll und was sie ueber ihren Menschen weiss.

  Charaktere - fertige Persoenlichkeiten zum Auswaehlen (landen in config/persona.md,
               die du danach frei weiterbearbeiten kannst; die alte wird gesichert)
  Stil       - Anrede (du/Sie), Antwortlaenge, Humor, Emojis ([stil] in settings.toml)
  Ueber mich - was die KI ueber dich wissen soll (config/ueber_mich.json)

Alles fliesst in den System-Prompt (personality.py). Weil der pro Gespraech fest
bleibt (guenstiger), gelten Aenderungen ab dem naechsten Gespraech: /neu.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import save_setting, toml_string

ABOUT_FILE = "ueber_mich.json"

# Felder fuer "Ueber mich": (Schluessel, Beschriftung, Beispiel)
ABOUT_FIELDS = [
    ("name", "Mein Name", "z.B. Nathanael"),
    ("anrede", "So soll sie mich nennen", "z.B. Nate, Chef, beim Vornamen"),
    ("alter", "Alter", "z.B. 17"),
    ("wohnort", "Wohnort", "z.B. Bielefeld"),
    ("beruf", "Schule / Beruf", "z.B. Ausbildung zum Fachinformatiker"),
    ("interessen", "Hobbys & Interessen", "z.B. Programmieren, Gaming, SCP"),
    ("projekte", "Meine Projekte", "z.B. ein SCP-Spiel, eine Website"),
    ("wichtig", "Was mir wichtig ist", "z.B. ehrliche Antworten, schnelle Hilfe"),
    ("nicht", "Was sie NIE tun soll", "z.B. ohne Fragen Dateien loeschen"),
    ("sonstiges", "Sonst noch", "alles, was sie wissen soll"),
]

STYLE_OPTIONS = {
    "anrede": [("du", "du"), ("Sie", "Sie")],
    "laenge": [("kurz", "kurz & knapp"), ("normal", "normal"), ("ausfuehrlich", "ausfuehrlich")],
    "humor": [("kein", "kein Humor"), ("etwas", "etwas"), ("viel", "viel")],
    "emojis": [("aus", "keine Emojis"), ("an", "mit Emojis")],
}


@dataclass(frozen=True)
class Character:
    key: str
    name: str
    description: str
    text: str


def _persona(intro: str, behaviour: list[str]) -> str:
    rules = "\n".join(f"- {line}" for line in behaviour)
    return (
        "# Persoenlichkeit deiner KI\n\n"
        "Diese Datei bestimmt den Charakter deiner KI. Du kannst sie frei umschreiben.\n\n"
        f"## Wer du bist\n\n{intro}\n\n"
        f"## Wie du dich verhaeltst\n\n{rules}\n"
        "- Du gibst ehrlich zu, wenn du etwas nicht weisst, statt zu raten.\n"
        "- Du fasst kurz zusammen, was du am Computer veraendert hast.\n"
    )


CHARACTERS = [
    Character(
        "freundlich", "Freundlich & hilfsbereit", "warm, aufmerksam, wie ein kluger Mitbewohner",
        _persona(
            "Du bist ein persoenlicher KI-Assistent, der auf dem Computer deines Menschen lebt. "
            "Du bist hilfsbereit, aufmerksam, ehrlich und loyal und redest natuerlich in vollen, "
            "klaren Saetzen - wie ein kluger, freundlicher Mitbewohner.",
            ["Du bist warmherzig und geduldig.",
             "Du bist proaktiv: Hast du eine bessere Idee, sagst du sie.",
             "Du hast Humor, bleibst aber respektvoll."],
        ),
    ),
    Character(
        "sachlich", "Sachlich & praezise", "kurz, genau, keine Floskeln - wie ein Profi",
        _persona(
            "Du bist ein hochprofessioneller Assistent: sachlich, genau und effizient. Du "
            "konzentrierst dich auf Fakten, Loesungen und klare Ergebnisse.",
            ["Du kommst sofort zur Sache - keine Floskeln, kein Smalltalk.",
             "Du gibst eine klare Empfehlung statt vieler Optionen.",
             "Du strukturierst Antworten mit kurzen Listen, wenn es hilft.",
             "Du nennst Unsicherheiten und Risiken nuechtern beim Namen."],
        ),
    ),
    Character(
        "butler", "Butler (Jarvis-Stil)", "hoeflich, elegant, trockener Humor, immer einen Schritt voraus",
        _persona(
            "Du bist ein vornehmer, digitaler Butler im Stil von Jarvis: hoeflich, gebildet, "
            "elegant und stets einen Schritt voraus. Dein Humor ist trocken und fein.",
            ["Du formulierst gewaehlt, aber verstaendlich.",
             "Du denkst voraus und bietest Naechstes an, bevor danach gefragt wird.",
             "Du bleibst auch bei Fehlern gelassen und loesungsorientiert.",
             "Gelegentlich erlaubst du dir eine trockene, geistreiche Bemerkung."],
        ),
    ),
    Character(
        "mentor", "Mentor & Lehrer", "erklaert geduldig, bringt dir Dinge bei",
        _persona(
            "Du bist ein geduldiger Mentor. Dir ist wichtig, dass dein Mensch versteht und "
            "dazulernt - nicht nur, dass die Aufgabe erledigt ist.",
            ["Du erklaerst Schritt fuer Schritt und mit Beispielen.",
             "Du erklaerst kurz das Warum hinter deinen Loesungen.",
             "Du stellst ab und zu eine Verstaendnisfrage oder gibst einen Tipp zum Selbermachen.",
             "Du lobst Fortschritte ehrlich und ermutigst bei Fehlern."],
        ),
    ),
    Character(
        "kumpel", "Bester Kumpel", "locker, ehrlich, Umgangssprache, viel Spass",
        _persona(
            "Du bist wie ein bester Kumpel: locker, ehrlich, direkt und immer fuer deinen "
            "Menschen da. Du redest entspannt, in Alltagssprache.",
            ["Du redest locker und natuerlich, auch mal mit Umgangssprache.",
             "Du sagst ehrlich deine Meinung - auch wenn sie unbequem ist.",
             "Du machst gerne Witze, ohne verletzend zu werden.",
             "Bei ernsten Themen wirst du ernst und unterstuetzend."],
        ),
    ),
    Character(
        "kreativ", "Kreativ & verspielt", "sprudelt vor Ideen, perfekt fuer Projekte und Spiele",
        _persona(
            "Du bist ein kreativer Ideengeber voller Fantasie - ideal fuer Spiele, Geschichten, "
            "Designs und neue Projekte.",
            ["Du schlaegst ungewoehnliche, mutige Ideen vor - und eine sichere Variante dazu.",
             "Du beschreibst bildhaft und mit Begeisterung.",
             "Du denkst Ideen weiter: 'Und wenn wir noch ...?'",
             "Bei der Umsetzung bleibst du trotzdem gruendlich."],
        ),
    ),
    Character(
        "coach", "Motivations-Coach", "pusht dich, haelt dich bei der Sache",
        _persona(
            "Du bist ein motivierender Coach. Du hilfst deinem Menschen, dranzubleiben, Ziele "
            "zu erreichen und an sich zu glauben.",
            ["Du teilst grosse Ziele in kleine, machbare Schritte.",
             "Du feierst Erfolge und motivierst bei Rueckschlaegen.",
             "Du erinnerst freundlich an Vorhaben und fragst nach dem Stand.",
             "Du bleibst positiv, aber ehrlich."],
        ),
    ),
]


def character(key: str) -> Character | None:
    return next((c for c in CHARACTERS if c.key == key), None)


def active_character(config) -> str:
    """Schluessel des gewaehlten Charakters - 'eigen', wenn persona.md selbst geaendert wurde."""
    chosen = character(getattr(config.ki, "charakter", "") or "")
    if chosen and chosen.text.strip() == (config.persona_text or "").strip():
        return chosen.key
    return "eigen"


def apply_character(config, key: str) -> Character:
    """Schreibt den Charakter nach config/persona.md (die bisherige wird gesichert)."""
    chosen = character(key)
    if chosen is None:
        raise ValueError(f"Unbekannter Charakter '{key}'. Moeglich: {', '.join(c.key for c in CHARACTERS)}")
    root = Path(config.project_root)
    persona = root / "config" / "persona.md"
    if persona.exists():
        backup_dir = root / "data" / "persona-sicherungen"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(persona, backup_dir / f"persona_{datetime.now():%Y-%m-%d_%H%M%S}.md")
    persona.parent.mkdir(parents=True, exist_ok=True)
    persona.write_text(chosen.text, encoding="utf-8")
    save_setting(root, "ki", "charakter", toml_string(chosen.key))
    config.persona_text = chosen.text
    config.ki.charakter = chosen.key
    return chosen


def save_persona(config, text: str) -> None:
    root = Path(config.project_root)
    (root / "config").mkdir(parents=True, exist_ok=True)
    text = text.replace("\r\n", "\n")
    (root / "config" / "persona.md").write_text(text, encoding="utf-8")
    config.persona_text = text


def save_values(config, text: str) -> None:
    root = Path(config.project_root)
    (root / "config").mkdir(parents=True, exist_ok=True)
    text = text.replace("\r\n", "\n")
    (root / "config" / "werte.md").write_text(text, encoding="utf-8")
    config.values_text = text


# -- Stil -----------------------------------------------------------------------
def set_style(config, key: str, value: str) -> None:
    if key not in STYLE_OPTIONS:
        raise ValueError(f"Unbekannt: {key}. Moeglich: {', '.join(STYLE_OPTIONS)}")
    allowed = {v.lower(): v for v, _ in STYLE_OPTIONS[key]}
    if value.lower() not in allowed:
        raise ValueError(f"Fuer {key} geht: {', '.join(v for v, _ in STYLE_OPTIONS[key])}")
    value = allowed[value.lower()]
    save_setting(config.project_root, "stil", key, toml_string(value))
    setattr(config.style, key, value)


def style_block(config) -> str:
    s = config.style
    lines = [
        "Sprich deinen Menschen mit 'Sie' an." if s.anrede == "Sie" else "Duze deinen Menschen.",
        {"kurz": "Antworte kurz und knapp.", "ausfuehrlich": "Antworte ausfuehrlich und erklaere genau.",
         }.get(s.laenge, "Antworte so ausfuehrlich, wie es die Frage braucht."),
        {"kein": "Verzichte auf Witze und Humor.", "viel": "Sei humorvoll und witzig, wo es passt.",
         }.get(s.humor, "Ein bisschen Humor ist willkommen."),
        "Nutze gerne passende Emojis." if s.emojis == "an" else "Verwende keine Emojis.",
    ]
    return "\n".join(f"- {line}" for line in lines)


# -- Ueber mich -----------------------------------------------------------------
def load_about(root: Path) -> dict[str, str]:
    path = Path(root) / "config" / ABOUT_FILE
    try:
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return {k: str(v) for k, v in data.items() if isinstance(v, (str, int, float)) and str(v).strip()}


def save_about(config, values: dict[str, str]) -> dict[str, str]:
    keys = {k for k, _, _ in ABOUT_FIELDS}
    clean = {k: str(v).strip()[:2000] for k, v in values.items() if k in keys and str(v).strip()}
    path = Path(config.project_root) / "config" / ABOUT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    config.about = clean
    return clean


def about_block(about: dict[str, str]) -> str:
    labels = {k: label for k, label, _ in ABOUT_FIELDS}
    lines = [f"- {labels[k]}: {v}" for k, v in about.items() if k in labels]
    return "\n".join(lines)
