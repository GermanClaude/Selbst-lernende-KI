#!/usr/bin/env bash
# ============================================================
#  Baut eine ausfuehrbare Datei unter Linux/macOS.
#  Ergebnis: dist/KI
# ============================================================
set -e
cd "$(dirname "$0")/.."

echo "[1/3] Virtuelle Umgebung vorbereiten..."
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[2/3] Abhaengigkeiten installieren..."
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt
pip install pyinstaller

echo "[3/3] Ausfuehrbare Datei bauen..."
pyinstaller packaging/ki.spec --noconfirm

echo
echo "Fertig! Die Datei liegt hier: dist/KI"
echo "Trage vorher deinen Schluessel in die Datei .env ein."
