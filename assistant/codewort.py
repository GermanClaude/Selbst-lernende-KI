"""Codewort-Schutz: ein vom Nutzer gesetztes Wort, das sensible Aktionen absichert.

Gedacht gegen den Fall "jemand sitzt an deinem PC und sagt Nova 'schick die Mail' / 'ruf da an' /
'melde mich an' / 'sag mir das Passwort'". Ist ein Codewort gesetzt, macht Nova solche Aktionen erst,
nachdem einmal das richtige Codewort eingegeben wurde (danach 15 Minuten frei, dann wieder gesperrt).

Sicherheit: Vom Codewort wird NUR ein PBKDF2-Hash (mit Zufalls-Salz) in data/codewort.json gespeichert -
nie das Wort selbst. Die Eingabe (/codewort ...) wird in der Oberflaeche abgefangen und geht NIE an das
KI-Modell. Die Datei ist fuer die Datei-Werkzeuge der KI gesperrt (permissions)."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path

_RUNDEN = 200000
FREI_DAUER = 15 * 60                 # nach dem Entsperren so lange frei, dann wieder gesperrt
_frei: dict[str, float] = {}         # root -> bis-wann (nur im RAM, nie auf die Platte)

SPERR_HINWEIS = ("Dafuer ist dein Codewort-Schutz aktiv. Sag mir erst dein Codewort - tippe: "
                 "/codewort <dein Codewort> - dann mache ich es. Ohne das Codewort nicht.")


def _pfad(root) -> Path:
    return Path(root) / "data" / "codewort.json"


def gesetzt(root) -> bool:
    try:
        return _pfad(root).exists()
    except OSError:
        return False


def setzen(root, wort: str) -> None:
    wort = (wort or "").strip()
    if not 3 <= len(wort) <= 128:
        raise ValueError("Das Codewort muss zwischen 3 und 128 Zeichen haben.")
    salz = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", wort.encode("utf-8"), salz, _RUNDEN).hex()
    p = _pfad(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"salz": salz.hex(), "hash": h, "seit": time.time()}), encoding="utf-8")


def pruefen(root, wort: str) -> bool:
    try:
        d = json.loads(_pfad(root).read_text(encoding="utf-8"))
        salz = bytes.fromhex(d["salz"])
        h = hashlib.pbkdf2_hmac("sha256", (wort or "").strip().encode("utf-8"), salz, _RUNDEN).hex()
        return secrets.compare_digest(h, str(d["hash"]))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def entsperren(root, wort: str) -> bool:
    if not pruefen(root, wort):
        return False
    _frei[str(root)] = time.time() + FREI_DAUER
    return True


def sperren(root) -> None:
    _frei.pop(str(root), None)


def entfernen(root, wort: str) -> bool:
    """Schutz abschalten - nur mit dem richtigen Codewort (oder wenn gar keins gesetzt ist)."""
    if gesetzt(root) and not pruefen(root, wort):
        return False
    try:
        _pfad(root).unlink(missing_ok=True)
    except OSError:
        pass
    _frei.pop(str(root), None)
    return True


def frei(root) -> bool:
    """True = die Aktion darf laufen: kein Codewort gesetzt ODER gerade entsperrt. Sonst False."""
    if not gesetzt(root):
        return True
    return _frei.get(str(root), 0.0) > time.time()


def _status(root) -> str:
    if not gesetzt(root):
        return ("Es ist KEIN Codewort gesetzt. Lege eins an mit: /codewort setzen <dein Codewort>. "
                "Danach frage ich es vor sensiblen Aktionen (senden, anrufen, anmelden, Passwort zeigen).")
    if frei(root):
        rest = int((_frei.get(str(root), 0.0) - time.time()) / 60) + 1
        return f"Codewort-Schutz ist AN und gerade entsperrt (noch ~{rest} Min). Sperren: /codewort sperren."
    return "Codewort-Schutz ist AN und gesperrt. Entsperren: /codewort <dein Codewort>."


def befehl(root, args: list[str]) -> str:
    """Behandelt /codewort ... lokal (die Eingabe geht nie ans Modell). Gibt die Antwort fuer den Nutzer zurueck."""
    args = [a for a in (args or []) if str(a).strip() != ""]
    if not args:
        return _status(root)
    kopf = args[0].lower()
    rest = " ".join(args[1:]).strip()
    if kopf == "setzen":
        if gesetzt(root) and not frei(root):
            return ("Es ist schon ein Codewort gesetzt. Entsperre es erst mit /codewort <aktuelles Codewort>, "
                    "dann /codewort setzen <neues Codewort>.")
        try:
            setzen(root, rest)
        except ValueError as exc:
            return str(exc)
        entsperren(root, rest)
        return ("Codewort gesetzt. Sensible Aktionen (senden, anrufen, anmelden, Passwort zeigen) brauchen es ab "
                "jetzt. Fuer die naechsten 15 Minuten ist es entsperrt.")
    if kopf == "aus":
        if not gesetzt(root):
            return "Es ist kein Codewort gesetzt."
        return ("Codewort entfernt - der Schutz ist aus." if entfernen(root, rest)
                else "Das Codewort stimmt nicht - der Schutz bleibt an.")
    if kopf == "sperren":
        sperren(root)
        return "Codewort-Schutz ist wieder gesperrt."
    if kopf == "status":
        return _status(root)
    wort = " ".join(args).strip()                 # alles andere: ein Entsperr-Versuch
    if not gesetzt(root):
        return "Es ist kein Codewort gesetzt. Lege eins an mit: /codewort setzen <dein Codewort>."
    return ("Codewort richtig - sensible Aktionen sind jetzt 15 Minuten frei." if entsperren(root, wort)
            else "Das Codewort stimmt nicht.")
