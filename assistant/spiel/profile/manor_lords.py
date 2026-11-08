"""Manor Lords (Slavic Magic / Hooded Horse): mittelalterlicher Staedtebau, reines Einzelspielerspiel.

Unreal Engine 5, kein bekanntes Anti-Cheat. Stand der Tastenbelegung: Version 0.8.117 (Nov. 2026).
Die Oberflaeche wurde mit Major Update #8 neu gebaut - darum kalibriert Nova sie beim ersten Start.
Das Wissen fuer die KI steht in manor_lords.md (Bauordnung, Checklisten, Fehler, schoene Stadt).
"""
from __future__ import annotations

from ..profil import SpielProfil

_BUCHSTABEN = {chr(c) for c in range(ord("a"), ord("z") + 1)}
_ZIFFERN = {str(d) for d in range(10)}

PROFIL = SpielProfil(
    id="manor_lords",
    name="Manor Lords",
    exe_namen=("manorlords-win64-shipping.exe", "manorlords.exe", "manorlords-wingdk-shipping.exe"),
    titel_muster=("manor lords",),
    tasten={
        "pause": "space", "schneller": "x", "langsamer": "z", "bau_menue": "c", "strassen": "r",
        "hofstaette": "h", "karte": "m", "zur_stadt": "t", "info": "tab", "abbrechen": "esc",
        "kamera": "w/a/s/d",
    },
    erlaubte_tasten=_BUCHSTABEN | _ZIFFERN | {
        "esc", "space", "tab", "enter", "backspace", "delete", "left", "right", "up", "down",
        "plus", "minus", "num_plus", "num_minus", "pageup", "pagedown",
    },
    verbotene_kombis={
        "ctrl+c": "Kinomodus – blendet die ganze Oberfläche aus (dann sieht Nova nichts mehr).",
    },
    speichern_tasten=None,  # Schnellspeicher-Taste unbekannt -> ueber Esc-Menue -> Speichern
    laden_tasten=None,
    pause_ist_umschalter=True,
    kalibrier_elemente=(
        ("ressourcenleiste", "obere Leiste: Familien/Wohnraum/Zustimmung, Wohlstand, Vorräte"),
        ("zeit_widget", "Datum/Jahreszeit mit Pause- und Tempo-Knöpfen"),
        ("werkzeugleiste", "Knöpfe Straßen, Bauen, Armee, Karte, Hilfe, Einstellungen"),
        ("bau_menue_knopf", "Knopf für das Bau-Menü"),
        ("strassen_knopf", "Knopf für Straßen"),
        ("overlays", "Overlays-Panel (Fruchtbarkeit, Höhe, Versorgung ...)"),
        ("problem_banner", "Bereich der Problem-Banner (Icons)"),
        ("nachrichten", "Nachrichten-Log"),
    ),
    wissen_datei="manor_lords.md",
    spielstand_ordner=r"%LOCALAPPDATA%\ManorLords\Saved\SaveGames",
)
