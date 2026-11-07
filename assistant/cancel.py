"""Abbrechen einer laufenden Antwort - im Terminal per Strg+C, in der App per Knopf.

Abgebrochen erbt von KeyboardInterrupt: Alle Stellen, die Strg+C schon richtig
behandeln (Verlauf reparieren, Zusammenfassung auslassen, ...), wirken damit auch
fuer den Stopp-Knopf der App. Wie Strg+C rutscht es durch "except Exception".
"""
from __future__ import annotations


class Abgebrochen(KeyboardInterrupt):
    """Der Mensch hat die laufende Antwort angehalten."""
