"""Zugangs-Tresor: Logins (Dienst, Benutzer, Passwort) verschluesselt und NUR auf diesem Geraet.

Damit kann Nova sich fuer dich bei Diensten anmelden (Instagram, E-Mail, ...), ohne dass irgendwer an die
Passwoerter kommt. Sicherheitsgrundsaetze:

  * Alles liegt verschluesselt in data/tresor.bin (PBKDF2-SHA256 + HMAC, wie der Gedaechtnis-Abgleich),
    entschluesselbar NUR mit deinem Haupt-Passwort. Das Haupt-Passwort wird nie gespeichert und verlaesst
    das Geraet nie - es bleibt nur im Arbeitsspeicher, solange der Tresor offen ist.
  * Der Tresor gibt Passwoerter NIE als Text an das KI-Modell (und damit nie an den KI-Anbieter) heraus.
    Die KI kann einen Login nur ANSTOSSEN ('einloggen') - das Passwort wandert dann direkt in das Loginfeld,
    nicht durch den Chat. `eintrag()` (Klartext) ist bewusst nur fuer die App-/Terminal-Seite, nicht fuer ein
    Werkzeug.
  * data/tresor.bin ist fuer alle Werkzeuge gesperrt (permissions), damit kein eingeschleuster Befehl die
    Datei lesen oder kopieren kann. Selbst wer die Datei stiehlt, hat ohne das Haupt-Passwort nichts.

Warum ein anderer Nova-Nutzer NICHT an deine Passwoerter kommt: Jede Installation hat ihre eigene lokale
tresor.bin, verschluesselt mit DEINEM Haupt-Passwort. Es gibt keinen gemeinsamen Server, auf dem Passwoerter
liegen - es gibt nichts zentral abzugreifen.
"""
from __future__ import annotations

import time
from pathlib import Path

from .abgleich import AbgleichFehler, entschluesseln, verschluesseln
from .logging_setup import get_logger

logger = get_logger()

DATEI = "tresor.bin"
MIN_HAUPT = 8                 # Mindestlaenge Haupt-Passwort
_offen: dict[str, tuple[str, float, dict]] = {}   # root -> (haupt_passwort, bis_wann, daten) - nur im RAM
AUTO_ZU = 30 * 60            # nach 30 Minuten ohne Nutzung wieder abschliessen


class TresorFehler(RuntimeError):
    pass


def _pfad(root) -> Path:
    return Path(root) / "data" / DATEI


def existiert(root) -> bool:
    return _pfad(root).exists()


def _schluessel(root) -> str:
    return str(Path(root).resolve())


def _laden(root, haupt: str) -> dict:
    p = _pfad(root)
    if not p.exists():
        return {"dienste": {}}
    try:
        d = entschluesseln(p.read_bytes(), haupt)
    except AbgleichFehler as exc:
        raise TresorFehler("Falsches Haupt-Passwort - oder die Tresor-Datei wurde veraendert.") from exc
    return d if isinstance(d, dict) and isinstance(d.get("dienste"), dict) else {"dienste": {}}


def _sichern(root, haupt: str, daten: dict) -> None:
    p = _pfad(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(verschluesseln(daten, haupt))
    tmp.replace(p)


def _aktiv(root) -> tuple[str, dict] | None:
    eintrag = _offen.get(_schluessel(root))
    if eintrag is None:
        return None
    haupt, bis, daten = eintrag
    if bis < time.time():
        zusperren(root)
        return None
    return haupt, daten


def ist_offen(root) -> bool:
    return _aktiv(root) is not None


def einrichten(root, haupt: str) -> str:
    """Den Tresor zum ersten Mal mit einem Haupt-Passwort anlegen."""
    if existiert(root):
        raise TresorFehler("Es gibt schon einen Tresor. Zum Oeffnen das Haupt-Passwort eingeben.")
    if len(haupt or "") < MIN_HAUPT:
        raise TresorFehler(f"Das Haupt-Passwort braucht mindestens {MIN_HAUPT} Zeichen.")
    _sichern(root, haupt, {"dienste": {}, "angelegt": time.time()})
    _offen[_schluessel(root)] = (haupt, time.time() + AUTO_ZU, _laden(root, haupt))
    return "Tresor angelegt und geoeffnet. Merk dir dein Haupt-Passwort gut - ohne es kommt niemand an die Daten, auch du nicht."


def oeffnen(root, haupt: str) -> str:
    """Tresor mit dem Haupt-Passwort entsperren (fuer diese Sitzung)."""
    if not existiert(root):
        raise TresorFehler("Es gibt noch keinen Tresor. Erst mit einem Haupt-Passwort einrichten.")
    daten = _laden(root, haupt)          # wirft bei falschem Passwort
    _offen[_schluessel(root)] = (haupt, time.time() + AUTO_ZU, daten)
    return f"Tresor offen ({len(daten.get('dienste') or {})} Eintraege). Schliesst nach 30 Min. von selbst."


def zusperren(root) -> None:
    _offen.pop(_schluessel(root), None)


def _fordere_offen(root) -> tuple[str, dict]:
    a = _aktiv(root)
    if a is None:
        raise TresorFehler("Der Tresor ist zu. Erst mit dem Haupt-Passwort oeffnen.")
    # Nutzung verlaengert die Offen-Zeit
    haupt, daten = a
    _offen[_schluessel(root)] = (haupt, time.time() + AUTO_ZU, daten)
    return haupt, daten


def liste(root) -> list[dict]:
    """Nur Dienstname + Benutzer + Notiz - NIEMALS das Passwort."""
    _haupt, daten = _fordere_offen(root)
    out = []
    for name, e in sorted((daten.get("dienste") or {}).items()):
        out.append({"dienst": name, "benutzer": e.get("benutzer", ""), "notiz": e.get("notiz", ""),
                    "url": e.get("url", ""), "hat_passwort": bool(e.get("passwort"))})
    return out


def eintrag(root, dienst: str, benutzer: str = "", passwort: str = "", notiz: str = "", url: str = "") -> str:
    """Einen Login speichern/aktualisieren. NUR von der App-/Terminal-Seite aufrufen (Klartext-Passwort) -
    nie aus einem KI-Werkzeug, damit das Passwort nicht durch den Chat laeuft."""
    haupt, daten = _fordere_offen(root)
    dienst = " ".join((dienst or "").split())[:80]
    if not dienst:
        raise TresorFehler("Fuer welchen Dienst? (Name fehlt)")
    dienste = daten.setdefault("dienste", {})
    e = dienste.get(dienst, {})
    if benutzer:
        e["benutzer"] = benutzer[:200]
    if passwort:
        e["passwort"] = passwort[:500]
    if notiz:
        e["notiz"] = notiz[:300]
    if url:
        e["url"] = url[:300]
    e["geaendert"] = time.strftime("%Y-%m-%d %H:%M")
    dienste[dienst] = e
    _sichern(root, haupt, daten)
    return f"'{dienst}' gespeichert."


def entfernen(root, dienst: str) -> bool:
    haupt, daten = _fordere_offen(root)
    dienste = daten.get("dienste") or {}
    if dienst not in dienste:
        # auch gross/klein-unabhaengig
        treffer = [k for k in dienste if k.lower() == (dienst or "").strip().lower()]
        if not treffer:
            return False
        dienst = treffer[0]
    dienste.pop(dienst, None)
    _sichern(root, haupt, daten)
    return True


def _finde(daten: dict, dienst: str) -> tuple[str, dict] | None:
    dienste = daten.get("dienste") or {}
    if dienst in dienste:
        return dienst, dienste[dienst]
    for k, v in dienste.items():
        if k.lower() == (dienst or "").strip().lower():
            return k, v
    return None


def geheimnis_fuer_login(root, dienst: str) -> dict:
    """NUR fuer die Anmelde-/Ausfuell-Schicht (App/Browser/Computer-Steuerung): gibt Benutzer + Passwort
    zurueck, damit sie direkt ins Loginfeld getippt werden. Dieses Ergebnis darf NICHT in den Chat/an das
    Modell gelangen - der Aufrufer tippt es und meldet nur Erfolg zurueck."""
    _haupt, daten = _fordere_offen(root)
    gefunden = _finde(daten, dienst)
    if gefunden is None:
        raise TresorFehler(f"Fuer '{dienst}' ist nichts im Tresor.")
    name, e = gefunden
    if not e.get("passwort"):
        raise TresorFehler(f"Fuer '{name}' ist kein Passwort hinterlegt.")
    return {"dienst": name, "benutzer": e.get("benutzer", ""), "passwort": e["passwort"], "url": e.get("url", "")}


def hat(root, dienst: str) -> bool:
    a = _aktiv(root)
    if a is None:
        return False
    return _finde(a[1], dienst) is not None


def tippe_login(daten: dict, ki_name: str = "Nova") -> bool:
    """Tippt Benutzer <Tab> Passwort in das gerade ausgewaehlte Feld (ohne Absenden - das macht dein Mensch).
    Das Passwort geht nur an die Windows-Eingabe, nie zurueck an die KI. Gibt True bei Erfolg zurueck."""
    try:
        from . import windows_steuerung as W
    except ImportError:
        return False
    if not W.verfuegbar():
        return False
    try:
        if daten.get("benutzer"):
            W.ausfuehren("tasten", {"aktion": "tippen", "text": str(daten["benutzer"])}, ki_name=ki_name)
            W.ausfuehren("tasten", {"aktion": "tasten", "tasten": ["tab"]}, ki_name=ki_name)
        W.ausfuehren("tasten", {"aktion": "tippen", "text": str(daten.get("passwort") or "")}, ki_name=ki_name)
        return True
    except Exception:  # noqa: BLE001 - nie Einzelheiten (koennten das Passwort betreffen)
        logger.warning("Tresor: Login-Eingabe fehlgeschlagen")
        return False


def status_text(root) -> str:
    if not existiert(root):
        return "Kein Tresor angelegt."
    if not ist_offen(root):
        return "Tresor vorhanden, aber zu (Haupt-Passwort noetig)."
    a = _aktiv(root)
    return f"Tresor offen - {len(a[1].get('dienste') or {})} Eintraege."
