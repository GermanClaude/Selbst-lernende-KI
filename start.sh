#!/usr/bin/env bash
# ============================================================
#  Startet die KI direkt (ohne Build). Fuer Linux/macOS.
# ============================================================
set -e
# Absoluter Pfad dieses Skripts - fuer den Neustart nach einem Update.
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$(dirname "$SELF")"

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
  pip install -r requirements.txt && cp requirements.txt .venv/requirements.installiert.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Hat ein Update requirements.txt geaendert (oder ist eine Installation
# gescheitert), die Pakete jetzt nachinstallieren.
if ! cmp -s requirements.txt .venv/requirements.installiert.txt; then
  echo "Installiere neue Pakete..."
  pip install -r requirements.txt && cp requirements.txt .venv/requirements.installiert.txt || true
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
# Die Schleife wird komplett eingelesen, bevor sie laeuft - ein Update darf diese
# Datei also ersetzen. Rueckgabecode 42 = Update installiert -> neu starten.
echo
echo "Starte die KI..."
export KI_NEUSTART=1
while true; do
  set +e
  python -m assistant
  code=$?
  set -e
  if [ "$code" -eq 43 ]; then
    exit 0  # laeuft schon in einem anderen Fenster
  fi
  if [ "$code" -ne 42 ]; then
    exit "$code"
  fi
  echo
  exec bash "$SELF"
done
