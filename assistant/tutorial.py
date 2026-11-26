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
    {"id": "jarvis", "titel": "Sprachmodus: nur reden", "ziel": "jarvis", "zeigen": None,
     "text": "Im Sprachmodus redest du einfach mit mir - ohne Tastatur. Ich hoere zu, merke selbst, wann du"
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


# Ausfuehrliche Tour (mit Sprachausgabe): erklaert jede Funktion genauer und nennt die Befehle.
STEPS_AUSFUEHRLICH = [
    {"id": "a_start", "titel": "Willkommen zur grossen Tour, ich bin {name}", "ziel": None, "zeigen": None,
     "text": "Schoen, dass du da bist! Ich fuehre dich jetzt in Ruhe durch alles, was ich kann - und lese dir "
             "jeden Schritt vor. Mit den Pfeilen gehst du vor und zurueck, mit dem Lautsprecher schaltest du "
             "die Stimme aus. Lass uns anfangen."},
    {"id": "a_chat", "titel": "So sprichst du mit mir", "ziel": "eingabe", "zeigen": None,
     "text": "Unten ist dein Eingabefeld. Schreib einfach wie mit einem Menschen - eine Frage, ein Auftrag, "
             "ein Gedanke. Enter schickt ab, Umschalt und Enter macht eine neue Zeile. Ich antworte mit Text, "
             "Listen, Tabellen oder Code. Du kannst mich jederzeit unterbrechen."},
    {"id": "a_sprechen", "titel": "Sprechen statt Tippen (F2)", "ziel": "mikrofon", "zeigen": None,
     "text": "Druecke die Taste F2 oder den Mikrofon-Knopf und sprich - dein gesprochener Text landet im Feld. "
             "Gedrueckt halten und loslassen, oder kurz druecken zum Starten und nochmal zum Beenden."},
    {"id": "a_sprachmodus", "titel": "Der Sprachmodus - einfach reden", "ziel": "jarvis", "zeigen": None,
     "text": "Im Sprachmodus unterhalten wir uns frei, ganz ohne Tastatur. Ich hoere zu, merke selbst, wann du "
             "fertig bist, antworte laut und hoere wieder zu. Du startest ihn mit dem Knopf oder dem Befehl "
             "Schraegstrich sprachmodus. 'Chat-Modus' sagen bringt dich zurueck."},
    {"id": "a_gehirn", "titel": "Mein Gehirn: welches KI-Modell", "ziel": None, "zeigen": None,
     "text": "Ich kann mit verschiedenen Modellen denken: Claude, DeepSeek, Gemini, ChatGPT oder einem "
             "kostenlosen Modell auf deinem PC ueber Ollama. Den Schluessel fuegst du einfach in den Chat ein. "
             "Umstellen kannst du das mit dem Befehl Schraegstrich gehirn."},
    {"id": "a_internet", "titel": "Ich kenne das Internet", "ziel": None,
     "text": "Ich kann live im Internet suchen und Webseiten lesen - fuer aktuelle Infos, Preise oder "
             "Nachrichten. Ich nenne dir dabei meine Quellen.",
     "zeigen": "Suche eine aktuelle, positive Nachricht aus der Wissenschaft und fasse sie in zwei Saetzen zusammen. Nenne die Quelle."},
    {"id": "a_dateien", "titel": "Dateien, Programme, der ganze PC", "ziel": None,
     "text": "Ich lese und schreibe Dateien, raeume auf, und - wenn du es erlaubst - starte Programme und "
             "bediene jede App am Bildschirm als Text, egal welches Modell. Mein Arbeitsordner ist mein "
             "Zuhause fuer deine Dateien.",
     "zeigen": "Lege in meinem Arbeitsordner die Datei willkommen.txt mit einem netten Gruss an und sag mir, wo sie liegt."},
    {"id": "a_gedaechtnis", "titel": "Ich lerne dich kennen", "ziel": "profil",
     "text": "Was ich ueber dich lerne, merke ich mir dauerhaft. Unter 'Charakter und Profil' siehst du mein "
             "Gedaechtnis und kannst einzelne Eintraege loeschen. Mit dem Befehl Schraegstrich gedaechtnis "
             "zeige ich dir, was ich gelernt habe.",
     "zeigen": "Merke dir dauerhaft, dass wir die grosse Tour gemacht haben, und sag mir kurz, was du ueber mich weisst."},
    {"id": "a_charakter", "titel": "Wie ich sein und aussehen soll", "ziel": "profil", "zeigen": None,
     "text": "Du bestimmst meinen Charakter - Butler, Kumpel oder Mentor -, ob ich dich duze oder sieze, kurz "
             "oder ausfuehrlich antworte und wie viel Humor ich habe. Und du kannst mir einfach sagen, welche "
             "Farben und Schrift die App haben soll - ich aendere es sofort."},
    {"id": "a_sicherheit", "titel": "Sicherheit: die Stuetzraeder", "ziel": "stuetzraeder", "zeigen": None,
     "text": "Mit Stuetzraedern frage ich vor jeder Aenderung nach und bleibe in meinem Arbeitsordner. Nimmst du "
             "sie ab - mit Schraegstrich stuetzraeder aus - darf ich am ganzen PC alles, ohne zu fragen. Mit "
             "'alles' sogar ohne die letzten Bremsen. Du entscheidest, wie viel Freiheit ich habe."},
    {"id": "a_afk", "titel": "Wenn du weg bist: der AFK-Modus", "ziel": None, "zeigen": None,
     "text": "Sag mir 'ich bin weg' oder nutze Schraegstrich afk, dann arbeite ich allein an einer Aufgabe "
             "weiter und gebe dir am Ende einen Bericht. Du kannst auch eine Zeit oder ein Kosten-Budget "
             "setzen."},
    {"id": "a_sehen", "titel": "Live-Sehen und Spielmodus", "ziel": None, "zeigen": None,
     "text": "Mit Live-Sehen schaue ich auf deinen Bildschirm mit und helfe bei dem, was du gerade tust - "
             "Schraegstrich sehen. Im Spielmodus kann ich sogar selbst ein Spiel spielen und dir danach "
             "berichten."},
    {"id": "a_geraete", "titel": "Handy, Anrufe und die Cloud", "ziel": None, "zeigen": None,
     "text": "Ich laufe auch auf dem Handy und kann es ganz bedienen. Wenn es wichtig ist, rufe ich dich sogar "
             "an - und du kannst mir am Telefon Auftraege geben. In der Cloud laufe ich rund um die Uhr, auch "
             "wenn dein PC aus ist. Mehr dazu mit Schraegstrich handy, Schraegstrich anruf und der Anleitung."},
    {"id": "a_wachwort", "titel": "Wachwort und Zeitplan", "ziel": None, "zeigen": None,
     "text": "Mit Schraegstrich wachwort hoere ich auf 'Hey Nova' und komme von selbst nach vorne. Und mit "
             "Schraegstrich zeitplan erledige ich Aufgaben zu einer Uhrzeit - zum Beispiel dich morgens "
             "erinnern oder dich um acht anrufen."},
    {"id": "a_befehle", "titel": "Alle Befehle auf einen Blick", "ziel": None, "zeigen": None,
     "text": "Tippe einen Schraegstrich ins Feld, dann siehst du alle Befehle mit Erklaerung. Die wichtigsten: "
             "Hilfe, Status, Gehirn, Stuetzraeder, Afk, Sprachmodus, Sehen, Handy, Anruf, Wachwort, Zeitplan, "
             "Sicherung und Deinstallieren. Du musst dir nichts merken - frag mich einfach."},
    {"id": "a_ende", "titel": "Fertig - viel Freude mit mir!", "ziel": None, "zeigen": None,
     "text": "Das war die grosse Tour. Updates hole ich mir selbst, alte Versionen bleiben gesichert. Wenn du "
             "etwas nicht weisst, frag mich einfach oder nutze Schraegstrich hilfe. Ich freue mich auf die "
             "Zusammenarbeit mit dir!"},
]


def steps(config, ausfuehrlich: bool = False) -> list[dict]:
    """Schritte mit eingesetztem Namen. ausfuehrlich=True: die grosse, vorgelesene Tour."""
    name = config.ki.name
    meaning = config.ki.bedeutung or "deine lernfaehige KI"
    quelle = STEPS_AUSFUEHRLICH if ausfuehrlich else STEPS
    return [{**s, "titel": s["titel"].format(name=name, meaning=meaning),
             "text": s["text"].format(name=name, meaning=meaning)} for s in quelle]


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
