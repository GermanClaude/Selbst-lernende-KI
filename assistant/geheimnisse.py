"""Geheimnis-Filter: macht passwort- und schluesselartige Inhalte unkenntlich, BEVOR Nova etwas
speichert (Transkripte, Aktivitaets-Protokoll). So landen Passwoerter/Schluessel/2FA-Codes nie in
Novas Dateien. Passwoerter gehoeren in den Passwortmanager des Browsers, nicht hierher.

Bewusst vorsichtig (lieber ein Geheimnis mehr verschleiern als eins durchrutschen lassen), aber
nicht so aggressiv, dass normale Transkripte zerstueckelt werden: es greift nur bei klar
geheimnis-artigen Mustern (bekannte Schluessel-Praefixe, 'Passwort: …', hochentropische Tokens,
Kartennummern)."""
from __future__ import annotations

import re

ERSATZ = "[…entfernt: Geheimnis…]"

# Bekannte Schluessel-/Token-Formate (API-Keys, Tokens, JWT).
_PRAEFIX = re.compile(
    r"(?<![A-Za-z0-9_\-])("
    r"sk-[A-Za-z0-9_\-]{16,}|ak_[A-Za-z0-9_\-]{16,}|AIza[A-Za-z0-9_\-]{20,}|"
    r"ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,}|"
    r"AQ\.[A-Za-z0-9_\-]{20,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}"
    r")(?![A-Za-z0-9_\-])"
)
# "Passwort: hunter2", "password = ...", "pin: 1234", "code: 123456" u.ae.
_BENANNT = re.compile(
    r"(?i)\b(passwort|passwoerter|password|passwd|pwd|kennwort|pin|otp|2fa|code|token|secret|geheim(?:nis)?)\b"
    r"\s*[:=]\s*\S{3,}"
)
# Kreditkarten-artige 13-19-stellige Nummern (auch mit Trennern).
_KARTE = re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)")
# Lange, zufaellig wirkende Tokens (gemischt Buchstaben+Ziffern, >=20) - z.B. hingeschriebene Keys.
_ENTROPIE = re.compile(r"(?<![A-Za-z0-9_\-])[A-Za-z0-9_\-]{20,}(?![A-Za-z0-9_\-])")


def _wirkt_geheim(token: str) -> bool:
    """Grobe Entropie-Heuristik: enthaelt Gross+Klein+Ziffer (oder ist sehr lang) -> wohl ein Schluessel."""
    if len(token) < 20:
        return False
    hat_ziffer = any(c.isdigit() for c in token)
    hat_buchstabe = any(c.isalpha() for c in token)
    gemischt = any(c.islower() for c in token) and any(c.isupper() for c in token)
    return hat_ziffer and hat_buchstabe and (gemischt or len(token) >= 32)


def verschleiere(text: str) -> str:
    """Macht Geheimnisse im Text unkenntlich. Gibt den bereinigten Text zurueck."""
    if not text:
        return text
    text = _PRAEFIX.sub(ERSATZ, text)
    text = _BENANNT.sub(lambda m: re.split(r"[:=]", m.group(0), maxsplit=1)[0].rstrip() + ": " + ERSATZ, text)
    text = _KARTE.sub(lambda m: ERSATZ if sum(c.isdigit() for c in m.group(0)) >= 13 else m.group(0), text)
    text = _ENTROPIE.sub(lambda m: ERSATZ if _wirkt_geheim(m.group(0)) else m.group(0), text)
    return text


def enthaelt_geheimnis(text: str) -> bool:
    """True, wenn im Text etwas Geheimnis-Artiges steckt (fuer Hinweise)."""
    return bool(text) and verschleiere(text) != text
