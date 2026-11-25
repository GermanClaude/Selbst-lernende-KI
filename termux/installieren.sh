#!/data/data/com.termux/files/usr/bin/bash
# Nova auf dem Handy einrichten (Termux, Android). In Termux eingeben:
#
#   curl -fsSL https://raw.githubusercontent.com/GermanClaude/Selbst-lernende-KI/ccr-cfa1ff8c-wgsyxb/termux/installieren.sh | bash
#
# Was passiert: Pakete installieren (Python, Git, Termux:API-Befehle, ADB), Nova nach ~/nova holen,
# Python-Pakete installieren und den Befehl "nova" anlegen. Beim ersten Mal dauert das 10-20 Minuten
# (ein Teil wird auf dem Handy uebersetzt). Danach startet "nova" in Sekunden.
set -e

ZWEIG="ccr-cfa1ff8c-wgsyxb"
REPO="https://github.com/GermanClaude/Selbst-lernende-KI.git"
ZIEL="$HOME/nova"

if [ -z "$PREFIX" ] || [ "${PREFIX#*com.termux}" = "$PREFIX" ]; then
  echo "Dieses Skript ist fuer Termux auf Android gedacht."
  exit 1
fi

echo "==> Pakete installieren ..."
pkg update -y
pkg install -y python git termux-api android-tools openssh python-pillow
# pydantic-core (fuer die KI-Bibliotheken) wird auf dem Handy notfalls selbst uebersetzt - dafuer Rust:
pkg install -y rust binutils || true

echo "==> Nova holen ..."
if [ -d "$ZIEL/.git" ]; then
  git -C "$ZIEL" pull --ff-only
else
  git clone --depth 1 -b "$ZWEIG" "$REPO" "$ZIEL"
fi

echo "==> Python-Pakete installieren (kann dauern) ..."
cd "$ZIEL"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "==> Befehl 'nova' anlegen ..."
cat > "$PREFIX/bin/nova" <<'EOS'
#!/data/data/com.termux/files/usr/bin/bash
# Nova starten: Server auf diesem Handy, Oberflaeche in der Nova-App (oder im Browser).
#   nova            -> Oberflaeche
#   nova --terminal -> nur im Terminal chatten
cd "$HOME/nova" || exit 1
if [ "$1" = "--terminal" ]; then
  exec python -m assistant --terminal
fi
exec python -m assistant --server "$@"
EOS
chmod +x "$PREFIX/bin/nova"

echo
echo "Fertig! Starte Nova mit:   nova"
echo
echo "Tipps:"
echo " - Die App 'Termux:API' (aus F-Droid, wie Termux) installieren - dann kann Nova Akku, SMS, Kamera usw."
echo " - Die Nova-App (Nova-Handy.apk aus dem neuesten GitHub-Release) zeigt die Oberflaeche wie eine echte App."
echo " - Das ganze Handy steuern: Entwickleroptionen > Kabelloses Debugging, dann in Nova /handysteuerung"
echo " - Damit Android Nova nicht schlafen legt: Termux in den Akku-Einstellungen 'Nicht optimieren'."
