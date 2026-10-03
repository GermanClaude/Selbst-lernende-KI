#!/usr/bin/env bash
# ============================================================
#  Startet die KI direkt (ohne Build). Fuer Linux/macOS.
# ============================================================
set -e
cd "$(dirname "$0")"

# --- 1) Python vorhanden? ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "[FEHLER] python3 wurde nicht gefunden. Bitte Python installieren."
  exit 1
fi

# --- 2) Umgebung + Pakete (nur beim ersten Mal) ---
if [ ! -d .venv ]; then
  echo "Erster Start: richte die Umgebung ein. Das dauert ein paar Minuten..."
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# --- 3) Einstellungsdatei anlegen ---
if [ ! -f config/settings.toml ]; then
  cp config/settings.example.toml config/settings.toml
fi

# --- 4) Schluessel-Datei .env anlegen und oeffnen ---
if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "Ich habe die Datei .env angelegt. Trage deinen API-Schluessel ein,"
  echo "speichere und schliesse den Editor, dann geht es weiter."
  echo
  "${EDITOR:-nano}" .env || true
fi

# --- 5) Los geht's ---
echo
echo "Starte die KI..."
python -m assistant
