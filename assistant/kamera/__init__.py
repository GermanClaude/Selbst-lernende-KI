"""Handy als Kamera: Nova sieht durch die Kamera deines Handys (nur im eigenen WLAN).

Ablauf (Kurzfassung):
  1. Nova erzeugt eine Kopplung (zufaelliges Thema + AES-Schluessel, ~5 Minuten gueltig) und zeigt
     einen QR-Code mit einem Link auf die Handy-Seite (GitHub Pages, HTTPS). Thema und Schluessel
     stehen nur im Fragment (#p=...) des Links - das schickt der Browser an keinen Server.
  2. Die Handy-Seite startet die Kamera und schickt ein WebRTC-Angebot (SDP) verschluesselt ueber
     ein oeffentliches Relais (ntfy.sh). Nova antwortet ebenso verschluesselt.
  3. Das Video laeuft danach direkt Handy -> PC im WLAN (keine STUN-/TURN-Server, nur LAN-Adressen).

Module:
  * signal.py  - Kopplung/Link, Verschluesselung, Nachrichten, Relay-Schnittstelle + NtfyRelay
  * webrtc.py  - HandyKamera: aiortc-Gegenstelle im eigenen asyncio-Thread, letztes Bild abholen
  * qr.py      - QR-Code als SVG/Text (segno, wenn installiert - sonst nur der Link)
  * quelle.py  - HandyQuellenProtokoll (Schnittstelle) + HandyQuelle (fuer das Live-Sehen-"Auge")

Zusatzpakete (alle erst bei Bedarf geladen): aiortc, av (PyAV), cryptography, segno.
"""
from __future__ import annotations

HANDY_PAKETE = ["aiortc>=1.16,<1.17 ; python_version >= '3.11'", "av>=14,<20", "cryptography>=44", "segno>=1.6"]


def fehlende_pakete() -> list[str]:
    """Welche Pakete fuer die Handy-Kamera fehlen (Namen fuer die Anzeige)."""
    import importlib.util

    fehlt = []
    for name, modul in (("aiortc", "aiortc"), ("av", "av"), ("cryptography", "cryptography"),
                        ("segno", "segno")):
        try:
            if importlib.util.find_spec(modul) is None:
                fehlt.append(name)
        except (ImportError, ValueError):
            fehlt.append(name)
    return fehlt
