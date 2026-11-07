# Hinweise fuer Aenderungen an diesem Projekt

- Sprache im Code, in Kommentaren und Meldungen: Deutsch (ohne Umlaute im Code,
  mit Umlauten in Markdown-Dokumenten).
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
