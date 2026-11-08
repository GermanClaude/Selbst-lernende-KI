"""Spielsichere Eingaben: jede Taste und jeder Klick geht durch einen Waechter.

Der Waechter prueft VOR jeder einzelnen Eingabe, dass genau das Spielfenster vorne ist, das beim
Start der Sitzung erkannt wurde (gleiches Fenster bzw. gleicher Prozess). Sonst wird nichts
gedrueckt, und die Sitzung pausiert, bis das Spiel wieder vorne ist. Dazu:
  * eine Sperrliste gefaehrlicher Kombinationen (Alt+F4, Windows-Taste, Strg+Alt+..., Alt+Tab,
    Umschalt+Tab = Steam-Overlay, und pro Spiel z.B. Strg+C = Kinomodus in Manor Lords),
  * eine Erlaubt-Liste: nur Tasten, die das Spielprofil freigibt,
  * Koordinaten immer 0..1 relativ zum Inhalt des Spielfensters (nie ausserhalb),
  * bewegst du selbst die Maus, haelt Nova sofort an (du uebernimmst).
Die eigentlichen Eingaben macht ein austauschbares "Tasten"-Objekt (Windows: SendInput mit
Scan-Codes, Tests: ein Rekorder).
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


class EingabeFehler(Exception):
    """Eine Eingabe wurde nicht ausgefuehrt (Text fuer die KI)."""


class FensterWeg(EingabeFehler):
    """Das Spielfenster ist nicht (mehr) vorne."""


class NutzerEingriff(EingabeFehler):
    """Dein Mensch hat die Maus bewegt - er uebernimmt."""


class Gestoppt(EingabeFehler):
    """Die Sitzung wurde angehalten (Stopp-Knopf, Not-Aus-Taste)."""


# Name -> (virtueller Tastencode, erweiterte Taste?)
TASTEN: dict[str, tuple[int, bool]] = {
    **{chr(c): (c - 32, False) for c in range(ord("a"), ord("z") + 1)},
    **{str(d): (0x30 + d, False) for d in range(10)},
    **{f"f{n}": (0x6F + n, False) for n in range(1, 13)},
    "esc": (0x1B, False), "space": (0x20, False), "enter": (0x0D, False), "tab": (0x09, False),
    "backspace": (0x08, False), "shift": (0xA0, False), "ctrl": (0xA2, False), "alt": (0xA4, False),
    "left": (0x25, True), "up": (0x26, True), "right": (0x27, True), "down": (0x28, True),
    "pageup": (0x21, True), "pagedown": (0x22, True), "end": (0x23, True), "home": (0x24, True),
    "insert": (0x2D, True), "delete": (0x2E, True), "win": (0x5B, True),
    "plus": (0xBB, False), "minus": (0xBD, False), "comma": (0xBC, False), "period": (0xBE, False),
    "num_plus": (0x6B, False), "num_minus": (0x6D, False),
    **{f"num{d}": (0x60 + d, False) for d in range(10)},
}
ALIASSE = {
    "escape": "esc", "leertaste": "space", "leer": "space", "spacebar": "space", " ": "space",
    "strg": "ctrl", "control": "ctrl", "steuerung": "ctrl", "umschalt": "shift", "hochstelltaste": "shift",
    "eingabe": "enter", "return": "enter", "eingabetaste": "enter", "entf": "delete", "del": "delete",
    "einfg": "insert", "pos1": "home", "ende": "end", "bildauf": "pageup", "bildab": "pagedown",
    "links": "left", "rechts": "right", "hoch": "up", "oben": "up", "runter": "down", "unten": "down",
    "pfeil_links": "left", "pfeil_rechts": "right", "pfeil_hoch": "up", "pfeil_runter": "down",
    "+": "plus", "-": "minus", ",": "comma", ".": "period", "windows": "win", "lwin": "win", "rwin": "win",
    "altgr": "alt", "rueck": "backspace", "ruecktaste": "backspace", "tabulator": "tab",
}
MODIFIER = ("ctrl", "shift", "alt")
# Immer gesperrt - egal, was ein Spielprofil erlaubt.
IMMER_VERBOTEN = {
    "alt+f4": "Alt+F4 würde das Spiel schließen.",
    "alt+tab": "Alt+Tab wechselt aus dem Spiel heraus.",
    "alt+esc": "Alt+Esc wechselt aus dem Spiel heraus.",
    "ctrl+esc": "Strg+Esc öffnet das Startmenü.",
    "ctrl+shift+esc": "Strg+Umschalt+Esc öffnet den Task-Manager.",
    "ctrl+w": "Strg+W schließt in vielen Programmen Fenster.",
    "ctrl+q": "Strg+Q beendet in vielen Programmen alles.",
    "shift+tab": "Umschalt+Tab öffnet das Steam-Overlay.",
    "alt+enter": "Alt+Enter wechselt den Vollbildmodus.",
}
MAX_HALTEN = 5.0     # Sekunden, laenger haelt Nova keine Taste
MAX_WARTEN = 30.0
_DEFAULT_HALTEN = 0.06
_PAUSE_ZWISCHEN = 0.12  # zwischen zwei Eingaben (Spiele verschlucken sonst Klicks)


def tastenname(name: Any) -> str:
    """'Leertaste' -> 'space', 'Strg' -> 'ctrl', 'C' -> 'c'. Unbekannt -> EingabeFehler."""
    roh = str(name or "").strip().lower()
    roh = ALIASSE.get(roh, roh)
    if roh not in TASTEN:
        raise EingabeFehler(f"Unbekannte Taste '{name}'. Erlaubt sind z.B. a-z, 0-9, f1-f12, esc, space, enter, "
                            "tab, shift, ctrl, alt, left/right/up/down, plus, minus.")
    return roh


def kombi_text(namen: list[str]) -> str:
    mods = [m for m in MODIFIER if m in namen]
    rest = sorted(n for n in namen if n not in MODIFIER)
    return "+".join(mods + rest)


@dataclass
class Zielfenster:
    """Das Spielfenster, das beim Start erkannt wurde."""

    hwnd: int = 0
    pid: int = 0
    exe: str = ""
    titel: str = ""

    def passt(self, info: dict | None) -> bool:
        if not info:
            return False
        if self.hwnd and int(info.get("hwnd") or 0) == self.hwnd:
            return True
        return bool(self.pid and int(info.get("pid") or 0) == self.pid)

    def beschreibung(self) -> str:
        return self.titel or self.exe or "Spielfenster"


@dataclass
class Erlaubnis:
    """Was das Spielprofil an Tasten zulaesst."""

    erlaubte_tasten: set[str] = field(default_factory=set)
    verbotene_kombis: dict[str, str] = field(default_factory=dict)

    def pruefen(self, namen: list[str]) -> None:
        if "win" in namen:
            raise EingabeFehler("Die Windows-Taste ist im Spielmodus gesperrt.")
        if "ctrl" in namen and "alt" in namen:
            raise EingabeFehler("Strg+Alt-Kombinationen sind im Spielmodus gesperrt (System und Not-Aus).")
        text = kombi_text(namen)
        grund = IMMER_VERBOTEN.get(text) or self.verbotene_kombis.get(text)
        if grund:
            raise EingabeFehler(f"Gesperrt: {text} – {grund}")
        for name in namen:
            if name not in MODIFIER and self.erlaubte_tasten and name not in self.erlaubte_tasten:
                raise EingabeFehler(f"Die Taste '{name}' ist für dieses Spiel nicht freigegeben.")


class Eingabe:
    """Alle Eingaben der KI im Spiel - immer mit Waechter.

    tasten: Objekt mit taste(vk, runter, erweitert), maus_absolut(x, y), maus_relativ(dx, dy),
            maus_knopf(knopf, runter), rad(rasten), cursor() -> (x, y) | None
    vordergrund: () -> {"hwnd", "pid", "exe", "titel", "rechteck": (x, y, b, h)} | None"""

    def __init__(self, ziel: Zielfenster, erlaubnis: Erlaubnis, tasten: Any,
                 vordergrund: Callable[[], dict | None], schlafe: Callable[[float], None] = time.sleep,
                 stopp: threading.Event | None = None, mausbewegung_stoppen: bool = True,
                 uhr: Callable[[], float] = time.monotonic):
        self.ziel = ziel
        self.uhr = uhr
        self.erlaubnis = erlaubnis
        self.tasten = tasten
        self.vordergrund = vordergrund
        self.schlafe = schlafe
        self.stopp = stopp or threading.Event()
        self.mausbewegung_stoppen = mausbewegung_stoppen
        self._erwartet: tuple[int, int] | None = None  # wo der Mauszeiger nach unserer letzten Bewegung ist
        self._gedrueckt_tasten: list[tuple[int, bool]] = []
        self._gedrueckt_knoepfe: list[str] = []
        self.zaehler = 0  # ausgefuehrte Eingaben (fuer Bericht/Tests)

    # -- Waechter --------------------------------------------------------------------
    def ist_vorne(self) -> bool:
        try:
            return self.ziel.passt(self.vordergrund())
        except Exception:  # noqa: BLE001
            return False

    def pruefen(self) -> dict:
        """Vor JEDER Eingabe: angehalten? Spiel vorne? Maus selbst bewegt? -> Fenster-Info."""
        if self.stopp.is_set():
            raise Gestoppt("Der Spielmodus wurde angehalten.")
        try:
            info = self.vordergrund()
        except Exception:  # noqa: BLE001
            info = None
        if not self.ziel.passt(info):
            vorne = (info or {}).get("titel") or (info or {}).get("exe") or "ein anderes Fenster"
            raise FensterWeg(f"Nicht ausgeführt: Vorne ist gerade „{str(vorne)[:60]}“, nicht das Spiel. "
                             "Ich warte, bis das Spiel wieder vorne ist.")
        rechteck = info.get("rechteck") or (0, 0, 0, 0)
        if len(rechteck) != 4 or rechteck[2] <= 0 or rechteck[3] <= 0:
            raise FensterWeg("Das Spielfenster ist minimiert oder hat keine Größe.")
        if self.mausbewegung_stoppen and self._erwartet is not None:
            try:
                jetzt = self.tasten.cursor()
            except Exception:  # noqa: BLE001
                jetzt = None
            if jetzt is not None and math.dist(jetzt, self._erwartet) > 60:
                self.stopp.set()
                raise NutzerEingriff("Du hast die Maus bewegt – ich halte an, du übernimmst.")
        return info

    def neuer_zug(self) -> None:
        """Nach dem Laufenlassen: wo die Maus jetzt ist, gilt als Ausgangspunkt (wird erneut geprueft)."""
        try:
            self._erwartet = self.tasten.cursor() if self.mausbewegung_stoppen else None
        except Exception:  # noqa: BLE001
            self._erwartet = None

    def punkt(self, nx: Any, ny: Any, rechteck) -> tuple[int, int]:
        """0..1 im Spielfenster -> Bildschirm-Pixel (nie ausserhalb des Fensters)."""
        try:
            fx, fy = float(nx), float(ny)
        except (TypeError, ValueError):
            raise EingabeFehler("x und y müssen Zahlen zwischen 0 und 1 sein.") from None
        if not (math.isfinite(fx) and math.isfinite(fy)) or not (-0.01 <= fx <= 1.01 and -0.01 <= fy <= 1.01):
            raise EingabeFehler(f"Koordinaten ({nx}, {ny}) liegen außerhalb des Spielfensters – x und y "
                                "sind Anteile 0..1 (x = Pixel-x / Bildbreite).")
        fx, fy = min(1.0, max(0.0, fx)), min(1.0, max(0.0, fy))
        x, y, b, h = rechteck
        return (int(x + round(fx * (b - 1))), int(y + round(fy * (h - 1))))

    def _warte(self, sekunden: float) -> None:
        ende = self.uhr() + max(0.0, sekunden)
        while True:
            rest = ende - self.uhr()
            if rest <= 0:
                return
            if self.stopp.is_set():
                raise Gestoppt("Der Spielmodus wurde angehalten.")
            self.schlafe(min(0.05, rest))

    # -- Grundbausteine -----------------------------------------------------------------
    def _runter(self, name: str) -> None:
        vk, erw = TASTEN[name]
        self.tasten.taste(vk, True, erw)
        self._gedrueckt_tasten.append((vk, erw))

    def _hoch(self, name: str) -> None:
        vk, erw = TASTEN[name]
        if (vk, erw) in self._gedrueckt_tasten:
            self._gedrueckt_tasten.remove((vk, erw))
        self.tasten.taste(vk, False, erw)

    def _knopf(self, knopf: str, runter: bool) -> None:
        if knopf not in ("links", "rechts", "mitte"):
            raise EingabeFehler("Maustaste: links, rechts oder mitte.")
        self.tasten.maus_knopf(knopf, runter)
        if runter:
            self._gedrueckt_knoepfe.append(knopf)
        elif knopf in self._gedrueckt_knoepfe:
            self._gedrueckt_knoepfe.remove(knopf)

    def _bewege(self, px: int, py: int) -> None:
        self.tasten.maus_absolut(px, py)
        self._erwartet = (px, py)

    def loslassen(self) -> None:
        """Alles loslassen, was noch gedrueckt ist (nach Fehlern, Stopp, Fensterwechsel)."""
        for knopf in list(self._gedrueckt_knoepfe):
            try:
                self.tasten.maus_knopf(knopf, False)
            except Exception:  # noqa: BLE001
                pass
        self._gedrueckt_knoepfe.clear()
        for vk, erw in reversed(list(self._gedrueckt_tasten)):
            try:
                self.tasten.taste(vk, False, erw)
            except Exception:  # noqa: BLE001
                pass
        self._gedrueckt_tasten.clear()

    # -- Aktionen ------------------------------------------------------------------------
    def kombi(self, namen: list[Any], halten: float = _DEFAULT_HALTEN, freigabe: bool = False,
              waehrend: Callable[[], Any] | None = None) -> str:
        """Tasten gleichzeitig druecken (z.B. ['ctrl', '1']). freigabe=True: Taste aus dem Spielprofil
        (Pause, Bau-Menue ...) - dann gilt die Erlaubt-Liste nicht, die Sperrliste schon.
        waehrend: wird bei gehaltenen Tasten aufgerufen (z.B. Bild der Info-Schilder bei gehaltenem Tab)."""
        if not namen:
            raise EingabeFehler("Keine Taste angegeben.")
        if len(namen) > 4:
            raise EingabeFehler("Höchstens 4 Tasten gleichzeitig.")
        tasten = [tastenname(n) for n in namen]
        if freigabe:
            Erlaubnis(set(), self.erlaubnis.verbotene_kombis).pruefen(tasten)
        else:
            self.erlaubnis.pruefen(tasten)
        halten = min(MAX_HALTEN, max(0.03, float(halten or _DEFAULT_HALTEN)))
        reihenfolge = [t for t in MODIFIER if t in tasten] + [t for t in tasten if t not in MODIFIER]
        self.pruefen()
        try:
            for name in reihenfolge:
                self._runter(name)
                self.schlafe(0.02)
            if waehrend is not None:
                vorher = min(0.4, halten)
                self._warte(vorher)
                waehrend()
                self._warte(max(0.0, halten - vorher))
            else:
                self._warte(halten)
        finally:
            for name in reversed(reihenfolge):
                try:
                    self._hoch(name)
                except Exception:  # noqa: BLE001
                    pass
        self.zaehler += 1
        self.schlafe(_PAUSE_ZWISCHEN)
        return kombi_text(tasten)

    def taste(self, name: Any, halten: float = _DEFAULT_HALTEN, freigabe: bool = False) -> str:
        return self.kombi([name], halten, freigabe)

    def bewegen(self, nx: Any, ny: Any) -> tuple[int, int]:
        info = self.pruefen()
        px, py = self.punkt(nx, ny, info["rechteck"])
        self._bewege(px, py)
        self.zaehler += 1
        return px, py

    def klick(self, nx: Any, ny: Any, knopf: str = "links", doppelt: bool = False) -> tuple[int, int]:
        info = self.pruefen()
        px, py = self.punkt(nx, ny, info["rechteck"])
        self._bewege(px, py)
        self.schlafe(0.05)
        for nummer in range(2 if doppelt else 1):
            if nummer:
                self.schlafe(0.08)
                self.pruefen()
            try:
                self._knopf(knopf, True)
                self.schlafe(0.05)
            finally:
                self._knopf(knopf, False)
        self.zaehler += 1
        self.schlafe(_PAUSE_ZWISCHEN)
        return px, py

    def ziehen(self, nx: Any, ny: Any, nx2: Any, ny2: Any, knopf: str = "links", relativ: bool = False,
               schritte: int = 12) -> None:
        """Maustaste halten und ziehen. relativ=True: relative Bewegungen (Gebaeude drehen u.ae.)."""
        info = self.pruefen()
        x1, y1 = self.punkt(nx, ny, info["rechteck"])
        x2, y2 = self.punkt(nx2, ny2, info["rechteck"])
        schritte = max(2, min(40, int(schritte or 12)))
        self._bewege(x1, y1)
        self.schlafe(0.05)
        try:
            self._knopf(knopf, True)
            self.schlafe(0.08)
            gesendet_x = gesendet_y = 0
            for i in range(1, schritte + 1):
                self.pruefen()
                zx, zy = x1 + round((x2 - x1) * i / schritte), y1 + round((y2 - y1) * i / schritte)
                if relativ:
                    self.tasten.maus_relativ(zx - x1 - gesendet_x, zy - y1 - gesendet_y)
                    gesendet_x, gesendet_y = zx - x1, zy - y1
                    self._erwartet = None
                else:
                    self._bewege(zx, zy)
                self.schlafe(0.015)
            self.schlafe(0.05)
        finally:
            self._knopf(knopf, False)
        if relativ:
            self._erwartet = None
            self.neuer_zug()
        self.zaehler += 1
        self.schlafe(_PAUSE_ZWISCHEN)

    def kamera_drehen(self, dx: Any, dy: Any = 0, knopf: str = "mitte") -> None:
        """Mittlere Maustaste halten und RELATIV bewegen (Unreal liest Raw Input - SetCursorPos reicht nicht)."""
        try:
            dx, dy = int(dx or 0), int(dy or 0)
        except (TypeError, ValueError):
            raise EingabeFehler("dx/dy müssen ganze Zahlen (Pixel) sein.") from None
        dx, dy = max(-2000, min(2000, dx)), max(-1000, min(1000, dy))
        if not dx and not dy:
            raise EingabeFehler("kamera_drehen braucht dx (links -, rechts +) und/oder dy.")
        info = self.pruefen()
        mitte = self.punkt(0.5, 0.5, info["rechteck"])
        self._bewege(*mitte)
        self.schlafe(0.05)
        schritte = max(4, min(60, max(abs(dx), abs(dy)) // 10))
        try:
            self._knopf(knopf, True)
            self.schlafe(0.12)  # ein kurzer Klick der mittleren Taste setzt in Manor Lords die Drehung zurueck
            sx = sy = 0
            for i in range(1, schritte + 1):
                if i % 10 == 0:
                    self.pruefen()
                zx, zy = round(dx * i / schritte), round(dy * i / schritte)
                self.tasten.maus_relativ(zx - sx, zy - sy)
                sx, sy = zx, zy
                self._erwartet = None
                self.schlafe(0.01)
            self.schlafe(0.05)
        finally:
            self._knopf(knopf, False)
        self._erwartet = None
        self.neuer_zug()
        self.zaehler += 1
        self.schlafe(_PAUSE_ZWISCHEN)

    def scrollen(self, rasten: Any, nx: Any = None, ny: Any = None) -> None:
        try:
            rasten = int(rasten or 0)
        except (TypeError, ValueError):
            raise EingabeFehler("scrollen braucht 'schritte' als ganze Zahl (+ = hinein/hoch, - = hinaus).") from None
        if not rasten:
            raise EingabeFehler("scrollen braucht 'schritte' (z.B. 3 oder -3).")
        rasten = max(-15, min(15, rasten))
        info = self.pruefen()
        if nx is not None and ny is not None:
            self._bewege(*self.punkt(nx, ny, info["rechteck"]))
            self.schlafe(0.05)
        schritt = 1 if rasten > 0 else -1
        for _ in range(abs(rasten)):
            self.pruefen()
            self.tasten.rad(schritt)
            self.schlafe(0.04)
        self.zaehler += 1
        self.schlafe(_PAUSE_ZWISCHEN)

    def warten(self, sekunden: Any) -> float:
        try:
            sekunden = float(sekunden or 0.5)
        except (TypeError, ValueError):
            sekunden = 0.5
        sekunden = min(MAX_WARTEN, max(0.0, sekunden))
        self._warte(sekunden)
        return sekunden
