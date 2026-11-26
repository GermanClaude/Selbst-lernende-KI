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
    r"ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|ghs_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,}|"
    r"AQ\.[A-Za-z0-9_\-]{20,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}"
    r")(?![A-Za-z0-9_\-])"
)
# Discord-/Slack-Webhook-Adressen: wer sie kennt, kann in deinem Namen posten.
_WEBHOOK = re.compile(r"https://(?:(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks|hooks\.slack\.com/services)/\S+")
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
    text = _WEBHOOK.sub(ERSATZ, text)
    text = _PRAEFIX.sub(ERSATZ, text)
    text = _BENANNT.sub(lambda m: re.split(r"[:=]", m.group(0), maxsplit=1)[0].rstrip() + ": " + ERSATZ, text)
    text = _KARTE.sub(lambda m: ERSATZ if sum(c.isdigit() for c in m.group(0)) >= 13 else m.group(0), text)
    text = _ENTROPIE.sub(lambda m: ERSATZ if _wirkt_geheim(m.group(0)) else m.group(0), text)
    return text


# Umgebungsvariablen, die Schluessel/Passwoerter enthalten (aus der .env geladen): API-Keys, Tokens ...
_GEHEIMER_NAME = re.compile(r"(?i)(_?API_?KEY|_KEY|TOKEN|PASSWORT|PASSWORD|PASSWD|SECRET|_HASH|_PAT|WEBHOOK|_PIN)$"
                            r"|^(NOVA_ABGLEICH_|TG_API_)")


def ist_geheimer_name(name: str) -> bool:
    return bool(_GEHEIMER_NAME.search(str(name or "")))


def umgebung_ohne_geheimnisse(env: dict | None = None) -> dict:
    """Kopie der Umgebung ohne Schluessel/Tokens - fuer Befehle, die die KI startet. Sonst koennte ein
    eingeschleuster Befehl (z.B. aus einer Webseite: "fuehre env aus") alle Schluessel ausgeben."""
    import os

    quelle = os.environ if env is None else env
    return {k: v for k, v in quelle.items() if not ist_geheimer_name(k)}


def geheime_werte(env: dict | None = None) -> list[str]:
    import os

    quelle = os.environ if env is None else env
    return sorted({v.strip() for k, v in quelle.items() if ist_geheimer_name(k) and len(v.strip()) >= 10},
                  key=len, reverse=True)


def werte_schwaerzen(text: str, env: dict | None = None) -> str:
    """Ersetzt die ECHTEN Schluessel/Tokens dieser Nova (aus der Umgebung) im Text - egal wie sie dort
    hingekommen sind (Datei gelesen, Befehl ausgegeben ...). So gelangen sie nie zur KI oder in den Chat."""
    if not text:
        return text
    for wert in geheime_werte(env):
        if wert in text:
            text = text.replace(wert, ERSATZ)
    return text


def enthaelt_geheimnis(text: str) -> bool:
    """True, wenn im Text etwas Geheimnis-Artiges steckt (fuer Hinweise)."""
    return bool(text) and verschleiere(text) != text
