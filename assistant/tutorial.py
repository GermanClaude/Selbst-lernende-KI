"""Das Tutorial: Nova stellt sich vor und zeigt in der Praxis, was sie kann.

Jeder Schritt hat eine Erklaerung und oft einen Auftrag zum Vorfuehren ("Zeig es
mir"): der wird wirklich an Nova geschickt - sie sucht dann z.B. wirklich im
Internet oder legt eine Datei an. 'ziel' sagt der App, welches Element sie
hervorheben soll.
"""
from __future__ import annotations

import json
from pathlib import Path

STEPS = [
    {"id": "willkommen", "titel": "Hallo, ich bin {name}!", "ziel": None, "zeigen": None,
     "text": "Ich bin deine persoenliche KI - {meaning}. Ich lebe auf deinem Computer, lerne dich kennen "
             "und kann wirklich Dinge fuer dich tun. In ein paar Schritten zeige ich dir, was ich kann. "
             "Bei 'Zeig es mir' mache ich es dir direkt vor."},
    {"id": "chat", "titel": "Schreib einfach los", "ziel": "eingabe",
     "text": "Unten ins Feld schreiben, Enter druecken - fertig. Ich antworte in ganzen Saetzen, mit "
             "Listen, Tabellen und Code, wenn es hilft.",
     "zeigen": "Stell dich mir in drei kurzen, freundlichen Saetzen vor und nenne drei Dinge, bei denen du mir im Alltag helfen kannst."},
    {"id": "sprache", "titel": "Sprechen statt tippen", "ziel": "mikrofon", "zeigen": None,
     "text": "Halte F2 (oder den Mikrofon-Knopf) gedrueckt und sprich - loslassen, fertig. Kurz druecken = "
             "Mikrofon an, nochmal druecken = fertig. Der Text landet im Eingabefeld."},
    {"id": "jarvis", "titel": "Jarvis-Modus: nur reden", "ziel": "jarvis", "zeigen": None,
     "text": "Im Jarvis-Modus redest du einfach mit mir - ohne Tastatur. Ich hoere zu, merke selbst, wann du "
             "fertig bist, antworte laut und hoere dann wieder zu. 'Chat-Modus' sagen oder klicken bringt dich zurueck."},
    {"id": "internet", "titel": "Ich kenne das Internet", "ziel": None,
     "text": "Ich kann im Internet suchen und Webseiten lesen - fuer aktuelle Infos.",
     "zeigen": "Suche im Internet nach einer aktuellen, interessanten Nachricht aus der Wissenschaft und fasse sie in zwei Saetzen zusammen. Nenne die Quelle."},
    {"id": "dateien", "titel": "Dateien & Programme", "ziel": None,
     "text": "Ich kann Dateien lesen, schreiben und ordnen - und (wenn du es erlaubst) Programme starten "
             "und den PC bedienen.",
     "zeigen": "Lege in deinem Arbeitsordner die Datei willkommen.txt mit einem kurzen, netten Gruss an mich an und sag mir, wo sie liegt."},
    {"id": "gedaechtnis", "titel": "Ich lerne dich kennen", "ziel": "profil",
     "text": "Was ich ueber dich lerne, merke ich mir dauerhaft. Unter 'Charakter & Profil' siehst du mein "
             "Gedaechtnis und kannst Eintraege loeschen.",
     "zeigen": "Merke dir dauerhaft, dass ich das Tutorial mit dir gemacht habe, und sag mir, was du jetzt ueber mich weisst."},
    {"id": "charakter", "titel": "Wie ich sein soll", "ziel": "profil", "zeigen": None,
     "text": "Du bestimmst meinen Charakter (z.B. Butler, Kumpel, Mentor), wie ich spreche (du/Sie, kurz oder "
             "ausfuehrlich, Humor) und was ich ueber dich wissen soll - unter 'Charakter & Profil'."},
    {"id": "agenten", "titel": "Agenten & Selbstkontrolle", "ziel": None,
     "text": "Grosse Aufgaben verteile ich auf Agenten mit frischem Kopf - und bevor ich etwas Wichtiges als "
             "fertig melde, pruefe ich es selbst.",
     "zeigen": "Lass einen recherche-Agenten herausfinden, wie viele Monde der Mars hat und wie sie heissen. Pruefe das Ergebnis kurz und sag mir, wie du geprueft hast."},
    {"id": "aussehen", "titel": "Die App nach deinem Geschmack", "ziel": None,
     "text": "Sag mir einfach, wie die App aussehen soll - Farben, Schrift, Begruessung. Ich aendere es sofort.",
     "zeigen": "Mach die Akzentfarbe der App gruen (#16a34a) und sag mir, wie ich es wieder zuruecksetzen kann."},
    {"id": "stuetzraeder", "titel": "Stuetzraeder", "ziel": "stuetzraeder", "zeigen": None,
     "text": "Mit Stuetzraedern frage ich vor jeder Aenderung und bleibe im Arbeitsordner - ohne Shell und "
             "PC-Steuerung. Ohne Stuetzraeder darf ich am ganzen PC alles, ohne zu fragen. Du schaltest das "
             "jederzeit um."},
    {"id": "fertig", "titel": "Los geht's!", "ziel": None, "zeigen": None,
     "text": "Das war's! Updates hole ich mir selbst, alte Versionen bleiben gesichert. Wenn du etwas nicht "
             "weisst: frag mich einfach - oder '/hilfe'. Viel Spass!"},
]


def steps(config) -> list[dict]:
    """Schritte mit eingesetztem Namen."""
    name = config.ki.name
    meaning = config.ki.bedeutung or "deine lernfaehige KI"
    return [{**s, "titel": s["titel"].format(name=name, meaning=meaning),
             "text": s["text"].format(name=name, meaning=meaning)} for s in STEPS]


def _state_file(root: Path) -> Path:
    return Path(root) / "data" / "tutorial.json"


def is_done(root: Path) -> bool:
    try:
        return bool(json.loads(_state_file(root).read_text(encoding="utf-8")).get("fertig"))
    except (OSError, ValueError):
        return False


def mark_done(root: Path) -> None:
    path = _state_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fertig": True}), encoding="utf-8")
