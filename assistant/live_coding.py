"""Live-Coding-Fenster (Premium): zeigt sichtbar und in Echtzeit, was Nova gerade schreibt oder aendert.

Ein eigenes kleines Fenster (Tkinter, laeuft in einem eigenen Thread) wird von den Datei-Werkzeugen
gespeist: jedes Mal, wenn Nova eine Datei schreibt oder bearbeitet, erscheint hier der Dateiname und
der neue Inhalt - der zuletzt geaenderte Teil wird kurz hervorgehoben. So ist fuer Menschen sichtbar
und nachvollziehbar, was die KI gerade programmiert.

Ohne geoeffnetes Fenster sind ALLE Aufrufe stille No-Ops (kein Overhead, keine Fehler). Tkinter wird
erst im Fenster-Thread importiert, damit der Import dieses Moduls auch ohne grafische Oberflaeche klappt.
"""
from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_fenster = None  # _Fenster-Instanz oder None


def aktiv() -> bool:
    """True, wenn gerade ein Live-Coding-Fenster offen ist."""
    with _lock:
        return _fenster is not None and _fenster.lebt()


def starten(titel: str = "Nova programmiert – live") -> bool:
    """Oeffnet das Fenster (oder laesst ein offenes offen). Gibt True bei Erfolg zurueck,
    False, wenn kein Fenster moeglich ist (z. B. keine grafische Oberflaeche)."""
    global _fenster
    with _lock:
        if _fenster is not None and _fenster.lebt():
            return True
        try:
            _fenster = _Fenster(titel)
        except Exception:  # noqa: BLE001 - ohne Display o. ae.: still scheitern
            logger.debug("Live-Coding: Fenster nicht moeglich", exc_info=True)
            _fenster = None
            return False
        if not _fenster.lebt():
            _fenster = None
            return False
        return True


def stoppen() -> None:
    """Schliesst ein offenes Fenster (falls vorhanden)."""
    global _fenster
    with _lock:
        f, _fenster = _fenster, None
    if f is not None:
        f.schliessen()


def zeige(pfad, inhalt: str, aktion: str = "schreibt") -> None:
    """Von den Datei-Werkzeugen aufgerufen, nachdem eine Datei geschrieben/geaendert wurde.
    Still, wenn kein Fenster offen ist."""
    with _lock:
        f = _fenster
    if f is None or not f.lebt():
        return
    try:
        f.anzeigen(str(pfad), inhalt if isinstance(inhalt, str) else str(inhalt), str(aktion))
    except Exception:  # noqa: BLE001 - die Anzeige darf nie den eigentlichen Schreibvorgang stoeren
        logger.debug("Live-Coding: anzeigen fehlgeschlagen", exc_info=True)


class _Fenster:
    """Tkinter-Fenster in eigenem Thread. Kommunikation nur ueber eine Queue (Tk ist nicht thread-sicher)."""

    def __init__(self, titel: str):
        self._q: queue.Queue = queue.Queue()
        self._lebt = True
        self._bereit = threading.Event()
        self._thread = threading.Thread(target=self._lauf, args=(titel,), name="live-coding", daemon=True)
        self._thread.start()
        self._bereit.wait(timeout=6)

    def lebt(self) -> bool:
        return self._lebt and self._thread.is_alive()

    def anzeigen(self, pfad: str, inhalt: str, aktion: str) -> None:
        self._q.put(("zeige", pfad, inhalt, aktion))

    def schliessen(self) -> None:
        self._q.put(("stop", "", "", ""))

    # -- laeuft komplett im eigenen Thread -------------------------------------
    def _lauf(self, titel: str) -> None:
        try:
            import tkinter as tk
        except Exception:  # noqa: BLE001
            self._lebt = False
            self._bereit.set()
            return
        try:
            root = tk.Tk()
        except Exception:  # noqa: BLE001 - keine Anzeige verfuegbar
            self._lebt = False
            self._bereit.set()
            return

        root.title(titel)
        root.geometry("780x560")
        try:
            root.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass
        root.configure(bg="#0d1117")

        kopf = tk.Label(root, text="Bereit – ich zeige dir gleich, was ich schreibe …", anchor="w",
                        font=("Segoe UI", 10, "bold"), bg="#0d1117", fg="#58a6ff", padx=10, pady=6)
        kopf.pack(fill="x")

        rahmen = tk.Frame(root, bg="#0d1117")
        rahmen.pack(fill="both", expand=True)
        yscroll = tk.Scrollbar(rahmen, orient="vertical")
        yscroll.pack(side="right", fill="y")
        txt = tk.Text(rahmen, wrap="none", bg="#0d1117", fg="#c9d1d9", insertbackground="#c9d1d9",
                      font=("Consolas", 10), padx=10, pady=8, yscrollcommand=yscroll.set,
                      borderwidth=0, highlightthickness=0)
        txt.pack(side="left", fill="both", expand=True)
        yscroll.config(command=txt.yview)
        txt.tag_configure("neu", background="#17502e")  # frisch geschriebener Teil
        txt.configure(state="disabled")

        fuss = tk.Label(root, text="Live-Coding (Premium) – nur Anzeige. Fenster schließen stoppt die Ansicht.",
                        anchor="w", font=("Segoe UI", 8), bg="#0d1117", fg="#6e7681", padx=10, pady=4)
        fuss.pack(fill="x")

        zustand = {"vorher": ""}

        def _gemeinsamer_praefix(a: str, b: str) -> int:
            n = min(len(a), len(b))
            i = 0
            while i < n and a[i] == b[i]:
                i += 1
            return i

        def _zeige(pfad: str, inhalt: str, aktion: str) -> None:
            kopf.config(text=f"Nova {aktion}:  {pfad}")
            ab = _gemeinsamer_praefix(zustand["vorher"], inhalt)
            zustand["vorher"] = inhalt
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", inhalt)
            if 0 <= ab < len(inhalt):
                txt.tag_add("neu", f"1.0 + {ab} chars", "end")
            txt.configure(state="disabled")
            txt.see("end")

        def pump() -> None:
            if not self._lebt:
                try:
                    root.destroy()
                except Exception:  # noqa: BLE001
                    pass
                return
            try:
                while True:
                    art, pfad, inhalt, aktion = self._q.get_nowait()
                    if art == "stop":
                        self._lebt = False
                        try:
                            root.destroy()
                        except Exception:  # noqa: BLE001
                            pass
                        return
                    if art == "zeige":
                        _zeige(pfad, inhalt, aktion)
            except queue.Empty:
                pass
            root.after(120, pump)

        def on_close() -> None:
            self._lebt = False
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass

        root.protocol("WM_DELETE_WINDOW", on_close)
        self._bereit.set()
        root.after(120, pump)
        try:
            root.mainloop()
        finally:
            self._lebt = False
