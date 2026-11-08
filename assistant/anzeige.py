"""Schoene Texte fuer die App: echte Umlaute statt ae/oe/ue.

Im Python-Code dieses Projekts stehen Umlaute als ae/oe/ue (Projektregel). Die App
soll aber echte Umlaute zeigen (H-oe-flich -> mit o-Umlaut). schoen() wandelt deshalb GENAU die
Woerter aus umlaute.json um - nichts wird geraten (sonst wuerde aus "neue" oder
"Steuer" Unsinn). Woerter mit Pfad- oder Code-Zeichen bleiben unveraendert.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

# Wortgrenzen: nicht in Pfaden, Dateinamen, Optionen (--x, -x) - aber in "DeepSeek-Schluessel".
_WORD = re.compile(r"(?<![\w\\/.=$%])(?<!--)(?<!\s-)[A-Za-z]+(?![\w\\/=(-]|\.\w)")


@lru_cache(maxsize=1)
def _words() -> dict[str, str]:
    try:
        return json.loads((Path(__file__).with_name("umlaute.json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def schoen(text: str) -> str:
    """'Hoeflich, fuer dich' -> dieselben Woerter mit Umlauten (nur bekannte Woerter)."""
    if not text or not isinstance(text, str):
        return text
    words = _words()

    def swap(match: re.Match) -> str:
        word = match.group(0)
        new = words.get(word.lower())
        if new is None or (word.isupper() and len(word) > 1):
            return word
        return new[0].upper() + new[1:] if word[0].isupper() else new

    return _WORD.sub(swap, text)


def schoen_alles(value):
    """Wie schoen(), aber fuer verschachtelte Listen/Dicts (nur die Texte)."""
    if isinstance(value, str):
        return schoen(value)
    if isinstance(value, list):
        return [schoen_alles(v) for v in value]
    if isinstance(value, dict):
        return {k: schoen_alles(v) for k, v in value.items()}
    return value
