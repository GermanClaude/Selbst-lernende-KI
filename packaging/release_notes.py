#!/usr/bin/env python3
"""Hilfsskript fuer den Release-Build (GitHub Actions).

  python packaging/release_notes.py --version   -> gibt die Version aus
  python packaging/release_notes.py             -> Neuigkeiten dieser Version (Markdown)

Bewusst ohne Abhaengigkeiten, damit es vor 'pip install' laeuft.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def version() -> str:
    text = (ROOT / "assistant" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r"""__version__\s*=\s*["']([^"']+)["']""", text).group(1)


def notes(ver: str) -> str:
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.is_file():
        return f"Version {ver}"
    for section in re.split(r"(?m)^##\s+", changelog.read_text(encoding="utf-8"))[1:]:
        head = section.splitlines()[0].strip()
        if re.match(rf"v?{re.escape(ver)}\b", head):
            return "## " + section.strip() + "\n"
    return f"Version {ver}"


if __name__ == "__main__":
    ver = version()
    sys.stdout.reconfigure(encoding="utf-8")
    print(ver if "--version" in sys.argv else notes(ver))
