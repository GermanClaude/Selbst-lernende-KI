"""Selbst-lernende-KI: ein lokaler, lernfaehiger KI-Assistent.

Module:
    config       - Einstellungen, Persona, Werte, Umgebungsvariablen laden
    memory       - dauerhaftes Gedaechtnis / Lernen (SQLite)
    permissions  - Sicherheits- und Berechtigungssystem
    tools        - Werkzeuge (Dateien, Shell, Web, System, Computer)
    personality  - baut den System-Prompt aus Persona + Werte + Gedaechtnis
    brain        - Anbindung an das Claude-Modell + Agenten-Loop
    voice        - optionale Sprachein-/-ausgabe (F2-Sprechtaste)
    updater      - automatische Updates aus dem GitHub-Repo, alte Versionen sichern
    ui.cli       - die Chat-Oberflaeche (Tastatur)

Version: bei jeder Aenderung, die Nutzer bekommen sollen, __version__ erhoehen und
CHANGELOG.md ergaenzen - daran erkennt der Updater neue Versionen.
"""

__version__ = "0.13.1"
