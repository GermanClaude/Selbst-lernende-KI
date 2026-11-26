"""Geplante Aufgaben: Nova handelt zu einer Uhrzeit von selbst - auch wenn niemand die App offen hat.

Beispiele: "Ruf mich morgen um 8 an und frag, ob ich den Termin bestaetigt habe", "Jeden Morgen um 7:30
das Wetter und meine Termine aufs Handy", "In 20 Minuten an den Herd erinnern".

Laeuft ueberall, wo Nova laeuft - am zuverlaessigsten in der Cloud (rund um die Uhr, PC darf aus sein).
Zur faelligen Zeit arbeitet Nova die Aufgabe wie im AFK-Modus ab (niemand sitzt davor, nachgefragt wird
nicht) und schickt das Ergebnis aufs Handy (Telegram) bzw. ruft an, wenn die Aufgabe das verlangt.

Gespeichert in data/zeitplan.json. Uhrzeiten gelten in deiner Zeitzone: NOVA_ZEITZONE (Standard in der
Cloud: Europe/Berlin, am PC die Uhr des PCs).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_EINTRAEGE = 50
WIEDERHOLUNGEN = ("", "taeglich", "werktags", "woechentlich")
_LOCK = threading.Lock()


class ZeitplanFehler(ValueError):
    pass


# ---------------------------------------------------------------- Uhrzeit (Cloud-Server laufen in UTC)
def _berlin(utc: datetime) -> datetime:
    """Mitteleuropaeische Zeit ohne Zeitzonen-Datenbank: Sommerzeit vom letzten Sonntag im Maerz bis zum
    letzten Sonntag im Oktober (jeweils 01:00 UTC)."""
    def letzter_sonntag(jahr: int, monat: int) -> datetime:
        tag = datetime(jahr, monat, 31, 1, 0, tzinfo=timezone.utc)
        return tag - timedelta(days=(tag.weekday() + 1) % 7)
    sommer = letzter_sonntag(utc.year, 3) <= utc < letzter_sonntag(utc.year, 10)
    return (utc + timedelta(hours=2 if sommer else 1)).replace(tzinfo=None)


def jetzt() -> datetime:
    """Aktuelle Ortszeit (ohne Zeitzonen-Angabe) - in NOVA_ZEITZONE, sonst die Uhr dieses Rechners."""
    zone = os.environ.get("NOVA_ZEITZONE", "").strip()
    if not zone:
        return datetime.now().replace(microsecond=0)
    utc = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        from zoneinfo import ZoneInfo

        return utc.astimezone(ZoneInfo(zone)).replace(tzinfo=None)
    except Exception:  # noqa: BLE001 - keine Zeitzonen-Daten (schlanker Container, Windows ohne tzdata)
        if zone.lower() in ("europe/berlin", "europe/vienna", "europe/zurich", "cet", "mez"):
            return _berlin(utc)
        return datetime.now().replace(microsecond=0)


# ---------------------------------------------------------------- "wann" verstehen
_WOCHENTAGE = {"montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3, "freitag": 4, "samstag": 5,
               "sonntag": 6}
_IN = re.compile(r"^in\s+(\d{1,4})\s*(min|minute|minuten|m|std|stunde|stunden|h|tag|tagen|tage|d)$")
_UHR = re.compile(r"(\d{1,2})[:.](\d{2})(?:\s*uhr)?$|(\d{1,2})\s*uhr$")
_DATUM_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ t]")
_DATUM_DE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})?\s+")


def zeit_verstehen(wann: str, basis: datetime | None = None) -> datetime:
    """'2026-11-27 08:00', '27.11.2026 8:00', '8:00' / '8 uhr' (naechstes Mal), 'morgen 7:30',
    'freitag 18:00', 'in 20 minuten', 'in 2 stunden'. Ergebnis liegt immer in der Zukunft."""
    basis = basis or jetzt()
    t = " ".join((wann or "").strip().lower().replace("um ", " ").split())
    if not t:
        raise ZeitplanFehler("Wann denn? z.B. '08:00', 'morgen 7:30' oder 'in 20 minuten'.")
    m = _IN.match(t)
    if m:
        n, einheit = int(m.group(1)), m.group(2)
        delta = (timedelta(minutes=n) if einheit[0] == "m" else
                 timedelta(hours=n) if einheit[0] in "sh" else timedelta(days=n))
        if delta < timedelta(minutes=1):
            raise ZeitplanFehler("Mindestens eine Minute in der Zukunft.")
        return (basis + delta).replace(second=0)
    tag = None
    rest = t
    m = _DATUM_ISO.match(t)
    if m:
        tag = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        rest = t[m.end():]
    else:
        m = _DATUM_DE.match(t)
        if m:
            jahr = int(m.group(3)) if m.group(3) else basis.year
            jahr = jahr + 2000 if jahr < 100 else jahr
            tag = datetime(jahr, int(m.group(2)), int(m.group(1)))
            rest = t[m.end():]
        else:
            wort, _, nachher = t.partition(" ")
            if wort in ("heute", "morgen", "uebermorgen", chr(252) + "bermorgen"):
                tage = {"heute": 0, "morgen": 1}.get(wort, 2)
                tag = basis.replace(hour=0, minute=0, second=0) + timedelta(days=tage)
                rest = nachher
            elif wort in _WOCHENTAGE:
                tage = (_WOCHENTAGE[wort] - basis.weekday()) % 7
                tag = basis.replace(hour=0, minute=0, second=0) + timedelta(days=tage)
                rest = nachher
    m = _UHR.search(rest.strip()) if rest.strip() else None
    if not m:
        raise ZeitplanFehler(f"Die Uhrzeit in '{wann}' verstehe ich nicht. Beispiele: '08:00', 'morgen 7:30', "
                             "'27.11. 18:00', 'in 20 minuten'.")
    stunde = int(m.group(1) or m.group(3))
    minute = int(m.group(2) or 0)
    if stunde > 23 or minute > 59:
        raise ZeitplanFehler("Diese Uhrzeit gibt es nicht.")
    if tag is None:
        ziel = basis.replace(hour=stunde, minute=minute, second=0)
        if ziel <= basis:
            ziel += timedelta(days=1)
        return ziel
    ziel = tag.replace(hour=stunde, minute=minute, second=0)
    if ziel <= basis:
        if t.split(" ")[0] in _WOCHENTAGE:
            return ziel + timedelta(days=7)
        raise ZeitplanFehler(f"{ziel:%d.%m.%Y %H:%M} ist schon vorbei (jetzt: {basis:%d.%m.%Y %H:%M}).")
    return ziel


def naechstes_mal(wann: datetime, wiederholen: str, nach: datetime) -> datetime | None:
    """Fuer wiederkehrende Aufgaben: der naechste Termin nach 'nach'. None = einmalig."""
    if not wiederholen:
        return None
    schritt = timedelta(days=7 if wiederholen == "woechentlich" else 1)
    ziel = wann
    while ziel <= nach or (wiederholen == "werktags" and ziel.weekday() >= 5):
        ziel += schritt
    return ziel


# ---------------------------------------------------------------- Speicher
def _pfad(root) -> Path:
    return Path(root) / "data" / "zeitplan.json"


def laden(root) -> list[dict]:
    try:
        daten = json.loads(_pfad(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in daten if isinstance(e, dict) and e.get("id") and e.get("wann") and e.get("auftrag")] \
        if isinstance(daten, list) else []


def _speichern(root, eintraege: list[dict]) -> None:
    pfad = _pfad(root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(".tmp")
    tmp.write_text(json.dumps(eintraege, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, pfad)


def planen(root, wann: str, auftrag: str, wiederholen: str = "", basis: datetime | None = None) -> dict:
    auftrag = " ".join((auftrag or "").split())
    if not auftrag:
        raise ZeitplanFehler("Was soll ich dann tun? Ohne Auftrag plane ich nichts.")
    wiederholen = (wiederholen or "").strip().lower().replace(chr(228), "ae").replace(chr(246), "oe")
    if wiederholen in ("nein", "einmalig", "keine", "nie"):
        wiederholen = ""
    if wiederholen not in WIEDERHOLUNGEN:
        raise ZeitplanFehler("Wiederholen geht: taeglich, werktags, woechentlich (oder leer = einmal).")
    ziel = zeit_verstehen(wann, basis)
    if wiederholen == "werktags":
        ziel = naechstes_mal(ziel, "werktags", ziel - timedelta(seconds=1)) or ziel
    with _LOCK:
        eintraege = laden(root)
        if len(eintraege) >= MAX_EINTRAEGE:
            raise ZeitplanFehler(f"Schon {MAX_EINTRAEGE} geplante Aufgaben - loesch erst alte.")
        eintrag = {"id": secrets.token_hex(3), "wann": ziel.strftime("%Y-%m-%d %H:%M"), "wiederholen": wiederholen,
                   "auftrag": auftrag[:1500], "erstellt": (basis or jetzt()).strftime("%Y-%m-%d %H:%M")}
        eintraege.append(eintrag)
        _speichern(root, eintraege)
    return eintrag


def loeschen(root, eintrag_id: str) -> bool:
    with _LOCK:
        eintraege = laden(root)
        rest = [e for e in eintraege if e["id"] != (eintrag_id or "").strip()]
        if len(rest) == len(eintraege):
            return False
        _speichern(root, rest)
        return True


def faellige_nehmen(root, nun: datetime | None = None) -> list[dict]:
    """Holt alle faelligen Aufgaben heraus: einmalige verschwinden, wiederkehrende ruecken weiter.
    Was laenger als 6 Stunden verpasst wurde (Nova war aus), wird nicht mehr nachgeholt - nur gemeldet."""
    nun = nun or jetzt()
    with _LOCK:
        eintraege = laden(root)
        faellig, bleiben = [], []
        for e in eintraege:
            try:
                wann = datetime.strptime(e["wann"], "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if wann > nun:
                bleiben.append(e)
                continue
            faellig.append(dict(e, verpasst=(nun - wann) > timedelta(hours=6)))
            weiter = naechstes_mal(wann, e.get("wiederholen", ""), nun)
            if weiter is not None:
                bleiben.append(dict(e, wann=weiter.strftime("%Y-%m-%d %H:%M")))
        if faellig:
            _speichern(root, bleiben)
    return faellig


def uebersicht(root) -> str:
    eintraege = sorted(laden(root), key=lambda e: e["wann"])
    kopf = f"Jetzt: {jetzt():%A %d.%m.%Y %H:%M}".replace("Monday", "Montag").replace("Tuesday", "Dienstag") \
        .replace("Wednesday", "Mittwoch").replace("Thursday", "Donnerstag").replace("Friday", "Freitag") \
        .replace("Saturday", "Samstag").replace("Sunday", "Sonntag")
    if not eintraege:
        return kopf + "\nKeine geplanten Aufgaben."
    zeilen = [kopf, f"{len(eintraege)} geplante Aufgabe(n):"]
    for e in eintraege:
        wdh = f" ({e['wiederholen']})" if e.get("wiederholen") else ""
        zeilen.append(f"- [{e['id']}] {e['wann']}{wdh}: {e['auftrag'][:200]}")
    return "\n".join(zeilen)


def modell_auftrag(eintrag: dict, name: str = "Nova") -> str:
    """Was das Modell zur faelligen Zeit bekommt."""
    verpasst = (" (Achtung: der Termin ist schon laenger vorbei - Nova war in der Zeit aus. Pruefe, ob es "
                "noch Sinn hat, und sag deinem Menschen sonst nur Bescheid.)") if eintrag.get("verpasst") else ""
    return (f"[Geplante Aufgabe {eintrag['id']}, faellig {eintrag['wann']}{verpasst}. Gerade sitzt niemand "
            "vor der App - Rueckfragen gehen nicht, arbeite wie im AFK-Modus. Erledige jetzt:]\n"
            f"{eintrag['auftrag']}\n"
            "[Soll dein Mensch etwas erfahren: Deine Antwort geht ans Handy (Telegram), falls verbunden. "
            "Verlangt die Aufgabe einen Anruf, nutze das Werkzeug 'anrufen'. Antworte kurz.]")
