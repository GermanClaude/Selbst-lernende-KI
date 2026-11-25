#!/bin/sh
# Start von Nova im Container. Gibt es einen dauerhaften Speicher (Standard /data, eigener Pfad: NOVA_DATEN),
# landen Gedaechtnis (data/), Einstellungen (config/), Arbeitsordner und .env dort - sonst gehen sie bei
# einem Neustart verloren.
set -e
cd /app
DATEN="${NOVA_DATEN:-/data}"
if [ -d "$DATEN" ] && [ -w "$DATEN" ]; then
  for d in data config workspace; do
    if [ ! -e "$DATEN/$d" ]; then
      mkdir -p "$DATEN/$d"
      cp -a "/app/$d/." "$DATEN/$d/" 2>/dev/null || true
    fi
    rm -rf "/app/$d"
    ln -s "$DATEN/$d" "/app/$d"
  done
  [ -e "$DATEN/.env" ] || : > "$DATEN/.env"
  ln -sf "$DATEN/.env" /app/.env
  echo "Dauerhafter Speicher: $DATEN"
else
  echo "Hinweis: kein dauerhafter Speicher ($DATEN) - Gedaechtnis und Verlauf gehen bei einem Neustart verloren."
fi
[ -f config/settings.toml ] || python -m assistant --einrichten
exec python -m assistant --cloud
