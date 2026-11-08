"""Spielmodus: Nova spielt Einzelspieler-Spiele (z.B. Manor Lords) selbst - auch ueber Nacht.

  eingabe.py   spielsichere Eingaben mit Waechter (nur das Spielfenster, Sperrliste, Not-Aus)
  windows.py   SendInput mit Scan-Codes, Vordergrund, wach halten, Not-Aus-Taste (nur Windows)
  bild.py      Bilder des Spielfensters (mit Raster), Vergleich fuer "festgefahren"
  profil.py    Spielprofile, Online-Sperre, Kalibrierung (data/spiele/<spiel>.json)
  journal.py   Tagebuch der Sitzung (data/spiele/journal_*.json) - Gedaechtnis ueber Stunden
  sitzung.py   die Spielschleife (pausieren, ansehen, handeln, laufen lassen) und der Bericht
  steuerung.py Start/Stopp/Status - gemeinsam fuer Terminal und App
"""
