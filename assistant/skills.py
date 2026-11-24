"""Skills: gespeicherte, wiederverwendbare Anweisungen/Verhaltensweisen fuer Nova.

Ein Skill ist eine kurze Regel in natuerlicher Sprache ("Antworte besonders knapp, um Tokens zu
sparen."). Du kannst Skills anlegen, und Nova kann sich selbst welche anlegen (Werkzeug 'skill') -
z.B. wenn du sagst "merk dir: fasse dich ab jetzt kurz". Eingeschaltete Skills werden in den
System-Prompt aufgenommen und gelten ab dem naechsten Gespraech.

BEWUSST kein Ausfuehren von beliebigem Code: ein "Skill" ist eine Anweisung, kein Python. Das haelt
es sicher (kein Nachladen/Ausfuehren fremden Codes), deckt aber genau den Wunsch ab - Nova merkt
sich Verbesserungen/Vorlieben und wendet sie an.

Gespeichert in config/skills.json (Updates fassen die Datei nicht an - siehe updater._PROTECTED_FILES).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .logging_setup import get_logger

logger = get_logger()

MAX_SKILLS = 50
MAX_LAENGE = 1000


@dataclass
class Skill:
    name: str
    anweisung: str
    an: bool = True
    provider: str = ""   # "" = gilt fuer ALLE Gehirne; sonst nur fuer dieses (z.B. "claude")

    def to_dict(self) -> dict:
        return {"name": self.name, "anweisung": self.anweisung, "an": self.an, "provider": self.provider}


def _pfad(root: Path) -> Path:
    return Path(root) / "config" / "skills.json"


def laden(root: Path) -> list[Skill]:
    try:
        roh = json.loads(_pfad(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for e in roh if isinstance(roh, list) else []:
        if isinstance(e, dict) and str(e.get("name", "")).strip() and str(e.get("anweisung", "")).strip():
            out.append(Skill(str(e["name"]).strip()[:80], str(e["anweisung"]).strip()[:MAX_LAENGE],
                             bool(e.get("an", True)), str(e.get("provider", "")).strip().lower()))
    return out


def speichern(root: Path, skills: list[Skill]) -> None:
    pfad = _pfad(root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps([s.to_dict() for s in skills], ensure_ascii=False, indent=2),
                    encoding="utf-8")


def hinzufuegen(root: Path, name: str, anweisung: str, provider: str = "") -> tuple[bool, str]:
    """Neuen Skill anlegen (oder einen gleichen Namens ueberschreiben). provider="" = fuer alle
    Gehirne, sonst nur fuer dieses (z.B. 'claude'). (ok, Meldung)."""
    name, anweisung = (name or "").strip()[:80], (anweisung or "").strip()[:MAX_LAENGE]
    provider = (provider or "").strip().lower()
    if not name or not anweisung:
        return False, "Ein Skill braucht einen Namen und eine Anweisung."
    skills = laden(root)
    skills = [s for s in skills if s.name.lower() != name.lower()]
    if len(skills) >= MAX_SKILLS:
        return False, f"Zu viele Skills (max. {MAX_SKILLS}). Loesche erst einen."
    skills.append(Skill(name, anweisung, True, provider))
    speichern(root, skills)
    wo = "alle Gehirne" if not provider else f"nur {provider}"
    return True, f"Skill '{name}' gespeichert (gilt fuer {wo}). Wirkt ab dem naechsten Gespraech (/neu)."


def entfernen(root: Path, name: str) -> bool:
    skills = laden(root)
    neu = [s for s in skills if s.name.lower() != (name or "").strip().lower()]
    if len(neu) == len(skills):
        return False
    speichern(root, neu)
    return True


def umschalten(root: Path, name: str, an: bool) -> bool:
    skills = laden(root)
    treffer = False
    for s in skills:
        if s.name.lower() == (name or "").strip().lower():
            s.an, treffer = an, True
    if treffer:
        speichern(root, skills)
    return treffer


def prompt_block(root: Path, provider: str = "") -> str:
    """Die eingeschalteten Skills als Text fuer den System-Prompt (leer, wenn keine). Es gelten die
    Skills fuer alle Gehirne plus die fuer das gerade aktive Gehirn (provider)."""
    prov = (provider or "").strip().lower()
    aktive = [s for s in laden(root) if s.an and (not s.provider or s.provider == prov)]
    if not aktive:
        return ""
    zeilen = [f"- {s.name}: {s.anweisung}" for s in aktive]
    return ("=== DEINE SKILLS (selbst/vom Menschen angelegte Regeln - halte dich daran) ===\n"
            + "\n".join(zeilen) + "\n\n")
