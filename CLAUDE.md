# Hinweise fuer Aenderungen an diesem Projekt

- **Zuerst `docs/ENTWICKLUNG.md` lesen** (Projektkarte, Stand, offene Punkte) und sie am Ende
  jeder groesseren Aenderung aktualisieren - sie ist das Gedaechtnis des Projekts, falls ein
  Chat verloren geht.

- Sprache im Code, in Kommentaren und Meldungen: Deutsch (ohne Umlaute im
  Python-Code, mit Umlauten in Markdown-Dokumenten und in sichtbaren Texten der
  App-Oberflaeche `assistant/app/static/`).
- **Versionen / Updates:** Nutzer bekommen Aenderungen ueber den eingebauten Updater
  (`assistant/updater.py`). Er vergleicht `__version__` in `assistant/__init__.py`
  auf dem Standard-Branch mit der installierten Version. Bei jeder Aenderung, die
  Nutzer bekommen sollen:
  1. `__version__` erhoehen (z.B. 0.2.0 -> 0.2.1 fuer Korrekturen, 0.3.0 fuer
     neue Funktionen),
  2. in `CHANGELOG.md` oben einen Abschnitt `## <Version> – <Datum>` mit
     verstaendlichen Stichpunkten fuer Nicht-Techniker ergaenzen (die KI liest ihn
     dem Nutzer beim Update vor).
  Die GitHub-Action `.github/workflows/release-exe.yml` baut daraus auf dem
  Standard-Branch automatisch eine KI.exe als Release `v<Version>`.
- Dateien, die ein Update nie anfassen darf (Nutzerdaten), stehen in
  `assistant/updater.py` (`_PROTECTED_*`, `_CREATE_ONLY`).
- Tests: `python -m pytest -q`.
