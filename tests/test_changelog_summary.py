"""/versionen zeigt pro Version, was sie gebracht hat (Kurzfassung aus CHANGELOG.md)."""
from assistant.updater import changelog_summary

_CHANGELOG = """# Neuigkeiten

## 0.24.0 – 2026-11-23

**Neues Gehirn: Venice AI**
- unzensiert, sieht Bilder
- nutzt Werkzeuge

## 0.23.0 – 2026-11-23

**Abliteration AI kann Bilder sehen**
- ueber ein seh-faehiges Gehirn

## 0.21.0 – 2026-11-21
- AFK arbeitet wirklich weiter
"""


def test_summary_nimmt_fette_titelzeile():
    assert changelog_summary(_CHANGELOG, "0.24.0") == "Neues Gehirn: Venice AI"
    assert changelog_summary(_CHANGELOG, "0.23.0") == "Abliteration AI kann Bilder sehen"


def test_summary_ohne_titel_nimmt_ersten_stichpunkt():
    assert changelog_summary(_CHANGELOG, "0.21.0") == "AFK arbeitet wirklich weiter"


def test_summary_unbekannte_version_leer():
    assert changelog_summary(_CHANGELOG, "0.1.0") == ""
    assert changelog_summary("", "0.24.0") == ""
