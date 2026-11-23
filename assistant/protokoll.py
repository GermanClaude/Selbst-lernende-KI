"""Aktivitaets-Protokoll: haelt fest, WELCHE Programme/Fenster gerade benutzt werden - wie ein
Taskmanager-Verlauf. Opt-in, laeuft bis du stoppst, schreibt lokal in eine Textdatei.

BEWUSST NICHT enthalten: Mitschreiben von Tastatureingaben oder von Nachrichten, die du (oder
andere) tippen (z.B. Discord-Nachrichten). Das waere ein Keylogger - er wuerde auch fremde private
Nachrichten und Passwoerter abgreifen. Nova baut so etwas nicht. Gesprochene Gespraeche kannst du
mit Zustimmung ueber den Mitschnitt (assistant/mitschnitt.py) transkribieren.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .logging_setup import get_logger

logger = get_logger()

KEIN_KEYLOGGER = (
    "Dieses Protokoll haelt nur fest, WELCHE Programme/Fenster offen sind - es schreibt NICHT mit, "
    "was getippt oder in Chats geschrieben wird (das waere ein Keylogger und baut Nova nicht)."
)


# ---------------------------------------------------------------------------
#  Reine Logik (testbar)
# ---------------------------------------------------------------------------
@dataclass
class Schnappschuss:
    zeit: float
    fenster: str = ""          # Titel des aktiven Fensters
    app: str = ""              # Programmname des aktiven Fensters
    apps: list[str] = field(default_factory=list)  # weitere laufende Programme (optional)


def _uhrzeit(t: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(t))


def format_eintrag(s: Schnappschuss) -> str:
    """Eine Protokollzeile: '[14:03:12] Discord - #general  (discord.exe)'."""
    teil = s.fenster or "(kein aktives Fenster)"
    if s.app:
        teil += f"  ({s.app})"
    return f"[{_uhrzeit(s.zeit)}] {teil}"


def protokoll_text(schnappschuesse: list[Schnappschuss], titel: str = "") -> str:
    zeilen = [f"# {titel}".rstrip(), KEIN_KEYLOGGER, ""] if titel else []
    zeilen += [format_eintrag(s) for s in schnappschuesse]
    return "\n".join(zeilen).strip() + "\n"


def zusammengefasst(schnappschuesse: list[Schnappschuss]) -> list[tuple[str, int]]:
    """Wie oft welches Programm aktiv war (haeufigstes zuerst) - fuer eine kurze Uebersicht."""
    zaehler: dict[str, int] = {}
    for s in schnappschuesse:
        name = s.app or s.fenster or "?"
        zaehler[name] = zaehler.get(name, 0) + 1
    return sorted(zaehler.items(), key=lambda kv: (-kv[1], kv[0]))


# ---------------------------------------------------------------------------
#  Schnappschuss der Aktivitaet (Windows) - geschuetzt/lazy
# ---------------------------------------------------------------------------
def aktives_fenster() -> tuple[str, str]:
    """(Fenstertitel, Programmname) des Vordergrundfensters. ('','') wenn nicht ermittelbar."""
    import sys
    if sys.platform != "win32":
        return "", ""
    try:
        import ctypes
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", ""
        laenge = user32.GetWindowTextLengthW(hwnd)
        puffer = ctypes.create_unicode_buffer(laenge + 1)
        user32.GetWindowTextW(hwnd, puffer, laenge + 1)
        titel = puffer.value
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = _prozessname(pid.value, ctypes, kernel32, wintypes)
        return titel, app
    except Exception as exc:  # noqa: BLE001
        logger.info("Aktives Fenster nicht lesbar: %s", exc)
        return "", ""


def _prozessname(pid: int, ctypes, kernel32, wintypes) -> str:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        groesse = wintypes.DWORD(260)
        puffer = ctypes.create_unicode_buffer(260)
        if kernel32.QueryFullProcessImageNameW(h, 0, puffer, ctypes.byref(groesse)):
            return puffer.value.replace("\\", "/").rsplit("/", 1)[-1]
    finally:
        kernel32.CloseHandle(h)
    return ""


# ---------------------------------------------------------------------------
#  Der Protokoll-Laeufer (opt-in, bis stop())
# ---------------------------------------------------------------------------
@dataclass
class ProtokollStatus:
    laeuft: bool = False
    start: float = 0.0
    eintraege: int = 0
    datei: str = ""
    letzter: str = ""


class Protokoll:
    def __init__(self, ordner: Path, intervall_sekunden: float = 15.0):
        self.ordner = Path(ordner)
        self.intervall = max(2.0, float(intervall_sekunden))
        self.status = ProtokollStatus()
        self.schnappschuesse: list[Schnappschuss] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._letzter_schluessel = ""

    def start(self) -> dict:
        if self.status.laeuft:
            return {"ok": False, "error": "Das Protokoll laeuft schon."}
        self.ordner.mkdir(parents=True, exist_ok=True)
        stempel = time.strftime("%Y-%m-%d_%H-%M-%S")
        datei = self.ordner / f"protokoll_{stempel}.log"
        self.schnappschuesse = []
        self._letzter_schluessel = ""
        self._stop.clear()
        self.status = ProtokollStatus(laeuft=True, start=time.time(), datei=str(datei))
        try:
            datei.write_text(f"# Aktivitaets-Protokoll {stempel}\n{KEIN_KEYLOGGER}\n\n", encoding="utf-8")
        except OSError as exc:
            self.status = ProtokollStatus()
            return {"ok": False, "error": f"Protokoll-Datei nicht anlegbar: {exc}"}
        self._thread = threading.Thread(target=self._laufen, name="protokoll", daemon=True)
        self._thread.start()
        return {"ok": True, "datei": str(datei), "hinweis": KEIN_KEYLOGGER}

    def stop(self) -> dict:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.intervall + 3)
        self.status.laeuft = False
        return {"ok": True, "datei": self.status.datei, "eintraege": len(self.schnappschuesse)}

    def _laufen(self) -> None:
        from .geheimnisse import verschleiere

        while not self._stop.is_set():
            titel, app = aktives_fenster()
            titel = verschleiere(titel)  # falls im Fenstertitel mal ein Token/Schluessel steht
            schluessel = f"{app}|{titel}"
            if schluessel != self._letzter_schluessel:  # nur bei Wechsel protokollieren (spart Platz)
                self._letzter_schluessel = schluessel
                s = Schnappschuss(zeit=time.time(), fenster=titel, app=app)
                with self._lock:
                    self.schnappschuesse.append(s)
                    self.status.eintraege = len(self.schnappschuesse)
                    self.status.letzter = format_eintrag(s)
                    try:
                        with open(self.status.datei, "a", encoding="utf-8") as fh:
                            fh.write(format_eintrag(s) + "\n")
                    except OSError as exc:
                        logger.warning("Protokoll nicht geschrieben: %s", exc)
            self._stop.wait(self.intervall)
        self.status.laeuft = False
