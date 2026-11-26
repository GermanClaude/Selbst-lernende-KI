"""Oeffentlichen Update-Kanal befuellen: nur, was jeder sehen darf - KEIN Quellcode.

    python packaging/kanal_dateien.py <Ordner des Kanal-Repos>

Kanal-Repo = GermanClaude/Selbst-lernende-KI (oeffentlich). Darin: README (Download), Neuigkeiten, Lizenz,
Nutzungsbedingungen, die Feedback-Adresse, die Webseite (web/, GitHub Pages) und eine Versionsdatei.
Die Programme selbst (KI.exe, KI-App.exe, Nova-Handy.apk) haengen als Release daran.

assistant/__init__.py im Kanal meldet immer 0.0.0: Quellcode-Installationen (auch alte ohne den Schutz von 0.44,
die Code-Dateien loeschen wuerden, die im neuen Stand fehlen) sehen dort NIE ein "Update". Die .exe-Updater
lesen ohnehin die Releases.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

LETZTE_QUELLE = "0.0.0"
DATEIEN = ("CHANGELOG.md", "LICENSE", "NUTZUNGSBEDINGUNGEN.md", "feedback-endpoint.txt")
ORDNER = ("web",)


def main(ziel: str) -> int:
    quelle = Path(__file__).resolve().parent.parent
    ziel_p = Path(ziel).resolve()
    for name in DATEIEN:
        if (quelle / name).exists():
            shutil.copy2(quelle / name, ziel_p / name)
    for name in ORDNER:
        if (quelle / name).is_dir():
            shutil.rmtree(ziel_p / name, ignore_errors=True)
            shutil.copytree(quelle / name, ziel_p / name)
    shutil.copy2(quelle / "packaging" / "KANAL_README.md", ziel_p / "README.md")
    version = re.search(r'__version__ = "([^"]+)"', (quelle / "assistant" / "__init__.py").read_text(encoding="utf-8"))
    (ziel_p / "version.json").write_text(json.dumps({"version": version.group(1) if version else "?"}) + "\n",
                                         encoding="utf-8")
    (ziel_p / "assistant").mkdir(exist_ok=True)
    (ziel_p / "assistant" / "__init__.py").write_text(
        '"""Nova - Versionsinfo des oeffentlichen Update-Kanals (kein Quellcode)."""\n'
        f'__version__ = "{LETZTE_QUELLE}"\n', encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
