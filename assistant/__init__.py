"""Selbst-lernende-KI: ein lokaler, lernfaehiger KI-Assistent.

Module:
    config       - Einstellungen, Persona, Werte, Umgebungsvariablen laden
    memory       - dauerhaftes Gedaechtnis / Lernen (SQLite)
    permissions  - Sicherheits- und Berechtigungssystem
    tools        - Werkzeuge (Dateien, Shell, Web, System, Computer)
    personality  - baut den System-Prompt aus Persona + Werte + Gedaechtnis
    brain        - Anbindung an das Claude-Modell + Agenten-Loop
    voice        - optionale Sprachein-/-ausgabe
    ui.cli       - die Chat-Oberflaeche (Tastatur)
"""

__version__ = "0.1.0"
