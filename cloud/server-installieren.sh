#!/bin/sh
# Nova auf einem eigenen Linux-Server (z.B. Hetzner, Ubuntu/Debian) einrichten - einmal als root ausfuehren:
#   curl -fsSL https://raw.githubusercontent.com/GermanClaude/Selbst-lernende-KI/ccr-cfa1ff8c-wgsyxb/cloud/server-installieren.sh | sh
# Danach laeuft Nova unter https://<deine-IP-mit-Strichen>.sslip.io (oder deiner eigenen Domain: NOVA_DOMAIN=...).
set -e
ZIEL="${NOVA_ORDNER:-/opt/nova}"
ZWEIG="ccr-cfa1ff8c-wgsyxb"

if ! command -v docker >/dev/null 2>&1; then
  echo "Installiere Docker (offizielles Skript von get.docker.com) ..."
  curl -fsSL https://get.docker.com | sh
fi
command -v git >/dev/null 2>&1 || (apt-get update && apt-get install -y git)

if [ -d "$ZIEL/.git" ]; then
  git -C "$ZIEL" pull --ff-only
else
  git clone --depth 1 -b "$ZWEIG" https://github.com/GermanClaude/Selbst-lernende-KI.git "$ZIEL"
fi
cd "$ZIEL/cloud"

if [ ! -f .env ]; then
  if [ -z "$NOVA_DOMAIN" ]; then
    IP="$(curl -4fsS https://api.ipify.org)"
    NOVA_DOMAIN="$(echo "$IP" | tr . -).sslip.io"     # kostenloser Name fuer deine IP - https ohne eigene Domain
  fi
  TOKEN="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n')"
  umask 077
  cat > .env <<EOF
NOVA_DOMAIN=$NOVA_DOMAIN
NOVA_TOKEN=$TOKEN
# Mindestens EIN KI-Schluessel (oder spaeter in der App eintragen):
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=
# Telegram (aus der .env auf deinem PC kopieren, optional):
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF
  echo "Angelegt: $ZIEL/cloud/.env - trag dort deine Schluessel ein (nano $ZIEL/cloud/.env)."
fi
. ./.env
docker compose --env-file .env up -d --build
echo ""
echo "Fertig. Nova laeuft unter:  https://$NOVA_DOMAIN/?t=$NOVA_TOKEN"
echo "Diese Adresse in die Nova-Handy-App eintragen (\"Nova in der Cloud\"). Sie ist dein Schluessel - nicht weitergeben."
echo "Update spaeter: dieses Skript nochmal ausfuehren."
