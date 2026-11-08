"""Spielprofile: welches Fenster ist das Spiel, welche Tasten gibt es, was ist verboten, was weiss Nova.

Ein Profil gilt fuer genau ein Spiel (z.B. assistant/spiel/profile/manor_lords.py). Dazu:
  * ONLINE_SPIELE / klingt_online - Online- und Mehrspieler-Spiele spielt Nova nie (Regeln der
    Spiele, Anti-Cheat, Fairness gegenueber anderen Menschen)
  * Kalibrierung - wo auf dem Bildschirm die wichtigen Anzeigen des Spiels liegen (0..1), pro
    Aufloesung in data/spiele/<profil>.json gespeichert, damit Nova nicht jedes Mal suchen muss.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .eingabe import Erlaubnis

PROFIL_ORDNER = Path(__file__).with_name("profile")


@dataclass
class SpielProfil:
    id: str
    name: str
    exe_namen: tuple[str, ...]
    titel_muster: tuple[str, ...]
    tasten: dict[str, str]                 # Rolle -> Taste (pause, schneller, bau_menue ...)
    erlaubte_tasten: set[str]
    verbotene_kombis: dict[str, str] = field(default_factory=dict)
    speichern_tasten: list[str] | None = None  # Schnellspeichern (None = unbekannt -> ueber das Menue)
    laden_tasten: list[str] | None = None      # Schnellladen (nur mit quickload_erlaubt)
    pause_ist_umschalter: bool = True
    kalibrier_elemente: tuple[tuple[str, str], ...] = ()
    wissen_datei: str = ""
    spielstand_ordner: str = ""             # nur zum Anzeigen/Auflisten (nie schreiben)

    def passt(self, info: dict | None) -> bool:
        if not info:
            return False
        exe = str(info.get("exe") or "").lower()
        titel = str(info.get("titel") or "").lower()
        if exe and exe in self.exe_namen:
            return True
        return bool(titel) and any(m in titel for m in self.titel_muster) and not _ist_browser(exe)

    def erlaubnis(self) -> Erlaubnis:
        return Erlaubnis(set(self.erlaubte_tasten), dict(self.verbotene_kombis))

    def wissen(self) -> str:
        if not self.wissen_datei:
            return ""
        try:
            return (PROFIL_ORDNER / self.wissen_datei).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def tasten_text(self) -> str:
        namen = {"pause": "Pause/Weiter", "schneller": "schneller", "langsamer": "langsamer",
                 "bau_menue": "Bau-Men\u00fc", "strassen": "Stra\u00dfen", "hofstaette": "Hofst\u00e4tte",
                 "karte": "Regionskarte", "zur_stadt": "Kamera zur Stadt", "info": "Info-Schilder",
                 "abbrechen": "abbrechen/Men\u00fc schlie\u00dfen", "kamera": "Kamera bewegen"}
        return ", ".join(f"{namen.get(rolle, rolle)} = {taste}" for rolle, taste in self.tasten.items())


def _ist_browser(exe: str) -> bool:
    # Ein Browser-Tab "Manor Lords Guide" ist nicht das Spiel.
    return exe in ("chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe", "vivaldi.exe")


# Online-/Mehrspieler-Spiele mit Anti-Cheat bzw. Wettbewerb gegen Menschen - hier steuert Nova nie.
ONLINE_SPIELE = {
    "valorant.exe": "Valorant", "valorant-win64-shipping.exe": "Valorant", "cs2.exe": "Counter-Strike 2",
    "csgo.exe": "Counter-Strike", "league of legends.exe": "League of Legends", "dota2.exe": "Dota 2",
    "fortniteclient-win64-shipping.exe": "Fortnite", "r5apex.exe": "Apex Legends", "overwatch.exe": "Overwatch",
    "rocketleague.exe": "Rocket League", "tslgame.exe": "PUBG", "rainbowsix.exe": "Rainbow Six Siege",
    "rainbowsix_be.exe": "Rainbow Six Siege", "cod.exe": "Call of Duty", "destiny2.exe": "Destiny 2",
    "wow.exe": "World of Warcraft", "escapefromtarkov.exe": "Escape from Tarkov", "eldenring.exe": "Elden Ring",
    "gta5.exe": "GTA V (Online)", "rustclient.exe": "Rust", "deadlock.exe": "Deadlock",
    "marvel-win64-shipping.exe": "Marvel Rivals", "hearthstone.exe": "Hearthstone", "lostark.exe": "Lost Ark",
    "pathofexile.exe": "Path of Exile", "pathofexile_x64.exe": "Path of Exile", "fc25.exe": "EA FC",
    "fc26.exe": "EA FC", "warthunder.exe": "War Thunder", "aces.exe": "War Thunder", "eft.exe": "Tarkov",
    "worldoftanks.exe": "World of Tanks", "ffxiv_dx11.exe": "Final Fantasy XIV", "genshinimpact.exe": "Genshin",
}
_ONLINE_WORTE = re.compile(r"\b(online|mehrspieler|multiplayer|multi-player|ranked|pvp|koop|co-?op|"
                           r"gegen (andere|echte) (spieler|menschen)|matchmaking|turnier)\b", re.IGNORECASE)


def online_spiel(info: dict | None) -> str:
    """Name des Online-Spiels, wenn das Fenster eins ist ('' sonst)."""
    exe = str((info or {}).get("exe") or "").lower()
    return ONLINE_SPIELE.get(exe, "")


def klingt_online(text: str) -> bool:
    return bool(_ONLINE_WORTE.search(str(text or "")))


def alle_profile() -> dict[str, SpielProfil]:
    from .profile import manor_lords

    return {p.id: p for p in (manor_lords.PROFIL,)}


def erlaubte_profile(namen) -> list[SpielProfil]:
    profile = alle_profile()
    gewuenscht = [str(n).strip().lower() for n in (namen or []) if str(n).strip()]
    return [profile[n] for n in gewuenscht if n in profile]


def finde_profil(info: dict | None, erlaubte) -> SpielProfil | None:
    for profil in erlaubte_profile(erlaubte):
        if profil.passt(info):
            return profil
    return None


class Kalibrierung:
    """Gespeicherte Positionen der wichtigen Anzeigen (0..1 im Spielfenster), je Aufloesung."""

    def __init__(self, ordner: Path, profil_id: str):
        self.pfad = Path(ordner) / f"{profil_id}.json"
        self.profil_id = profil_id

    def _laden(self) -> dict:
        try:
            daten = json.loads(self.pfad.read_text(encoding="utf-8"))
            return daten if isinstance(daten, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def schluessel(aufloesung: tuple[int, int] | None) -> str:
        if not aufloesung:
            return "unbekannt"
        return f"{int(aufloesung[0])}x{int(aufloesung[1])}"

    def fuer(self, aufloesung: tuple[int, int] | None) -> dict | None:
        eintrag = (self._laden().get("aufloesungen") or {}).get(self.schluessel(aufloesung))
        if not isinstance(eintrag, dict) or not isinstance(eintrag.get("elemente"), dict):
            return None
        return eintrag

    def speichern(self, aufloesung: tuple[int, int] | None, elemente: dict[str, dict], notiz: str = "") -> int:
        daten = self._laden()
        daten["profil"] = self.profil_id
        alle = daten.setdefault("aufloesungen", {})
        alt = alle.get(self.schluessel(aufloesung)) or {}
        neu = dict(alt.get("elemente") or {}) if isinstance(alt, dict) else {}
        neu.update(elemente)
        alle[self.schluessel(aufloesung)] = {"am": time.strftime("%Y-%m-%d %H:%M"), "elemente": neu,
                                             "notiz": str(notiz or (alt or {}).get("notiz") or "")[:500]}
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.pfad)
        return len(neu)

    def vergessen(self, aufloesung: tuple[int, int] | None = None) -> bool:
        daten = self._laden()
        if not daten:
            return False
        if aufloesung is None:
            try:
                self.pfad.unlink()
            except OSError:
                return False
            return True
        if (daten.get("aufloesungen") or {}).pop(self.schluessel(aufloesung), None) is None:
            return False
        self.pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
        return True

    def text(self, aufloesung: tuple[int, int] | None) -> str:
        eintrag = self.fuer(aufloesung)
        if not eintrag:
            return ""
        zeilen = []
        for name, wert in sorted(eintrag["elemente"].items()):
            if isinstance(wert, dict):
                zeilen.append(f"- {name}: x={float(wert.get('x', 0)):.3f}, y={float(wert.get('y', 0)):.3f}"
                              + (f" ({str(wert.get('text'))[:80]})" if wert.get("text") else ""))
        if eintrag.get("notiz"):
            zeilen.append(f"Notiz: {eintrag['notiz']}")
        return "\n".join(zeilen)
