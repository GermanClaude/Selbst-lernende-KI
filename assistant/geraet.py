"""Stabilere Geraete-Kennung - fuers Sperren (auch von Gratis-Nutzern) und die opt-in Nutzer-Uebersicht.

EHRLICH: Eine wirklich "nicht zuruecksetzbare" Kennung gibt es auf einem fremden PC NICHT. Ein
entschlossener Nutzer kann sie immer umgehen (neue Hardware, virtuelle Maschine, frisch aufgesetztes
System, Code-Manipulation). Dieses Modul macht das Umgehen nur DEUTLICH schwerer, indem es:
  1. die Kennung an mehreren dauerhaften Stellen AUSSERHALB des App-Ordners spiegelt (ein blosses
     Neuinstallieren oder Loeschen des App-Datenordners aendert sie dann nicht), und
  2. sie notfalls deterministisch aus einem (gehashten) Hardware-Merkmal ableitet, sodass derselbe PC
     wieder dieselbe Kennung ergibt.

Diese Geraete-ID ist bewusst GETRENNT von premium.kennung() (die an Premium-Codes gebunden ist und sich
nicht aendern darf). Sie wird gehasht gespeichert - das rohe Hardware-Merkmal verlaesst das Geraet nie.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DATEI = "geraet.id"   # im App-Datenordner (data/) - plus Spiegel ausserhalb (siehe _spiegel_pfade)
_cache: dict = {}


def _spiegel_pfade() -> list[Path]:
    """Dauerhafte Orte ausserhalb des App-Ordners, damit Neuinstallation/Daten-Loeschen die ID nicht trifft."""
    pfade: list[Path] = []
    appdata = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if appdata:
        pfade.append(Path(appdata) / "Nova" / _DATEI)
    pfade.append(Path.home() / ".nova" / _DATEI)
    return pfade


def _hardware_merkmal() -> str:
    """Ein pro Geraet moeglichst stabiles, GEHASHTES Merkmal (nie im Klartext gespeichert)."""
    import platform

    teile = [platform.node(), platform.machine(), platform.system()]
    try:                                   # Windows: stabile Installations-GUID
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
            teile.append(str(winreg.QueryValueEx(k, "MachineGuid")[0]))
    except Exception:  # noqa: BLE001 - nicht Windows / kein Zugriff
        pass
    try:                                   # MAC-Adresse (kann sich aendern, daher nur als ein Teil)
        import uuid as _uuid

        teile.append(format(_uuid.getnode(), "x"))
    except Exception:  # noqa: BLE001
        pass
    roh = "|".join(t for t in teile if t)
    return hashlib.sha256(("nova-geraet|" + roh).encode("utf-8", "replace")).hexdigest()


def _gueltig(wert) -> bool:
    return isinstance(wert, str) and len(wert) == 16 and all(c in "0123456789abcdef" for c in wert)


def _lesen(pfad: Path) -> str:
    try:
        wert = pfad.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return ""
    return wert if _gueltig(wert) else ""


def _schreiben(pfad: Path, wert: str) -> None:
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(wert + "\n", encoding="utf-8")
    except OSError:
        logger.debug("Geraete-ID: konnte %s nicht schreiben", pfad, exc_info=True)


def geraet_id(root=None) -> str:
    """Die stabile Geraete-ID (16 hex). Reihenfolge: App-Datei -> Spiegel -> aus Hardware ableiten.
    Der gefundene/erzeugte Wert wird ueberall nachgezogen, damit er Neuinstallationen uebersteht."""
    schluessel = str(root or "")
    gemerkt = _cache.get(schluessel)
    if gemerkt:
        return gemerkt

    orte: list[Path] = []
    if root is not None:
        orte.append(Path(root) / "data" / _DATEI)
    orte += _spiegel_pfade()

    wert = ""
    for pfad in orte:
        wert = _lesen(pfad)
        if wert:
            break
    if not wert:                           # nirgends gefunden: aus der Hardware ableiten (deterministisch)
        wert = _hardware_merkmal()[:16]

    for pfad in orte:                      # ueberall nachziehen (best effort)
        if _lesen(pfad) != wert:
            _schreiben(pfad, wert)
    _cache[schluessel] = wert
    return wert
