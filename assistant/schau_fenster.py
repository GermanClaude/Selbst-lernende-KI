"""Schau-Fenster: ein kleines, sichtbares Fenster, das Arbeitsschritte LIVE anzeigt - z. B. beim
Video-Schnitt, damit der Mensch sieht, was gerade passiert ("Lade … / Schneide … / Speichere … / Fertig").

Tkinter laeuft in einem eigenen Thread (ueber eine Queue angesprochen). Ohne Fenster sind alle Aufrufe
stille No-Ops. Mehrere Aufgaben koennen nacheinander dasselbe Fenster nutzen (kopf() setzt die Ueberschrift,
melde() haengt eine Zeile an, schritt() ersetzt die letzte Zeile - gut fuer einen Prozentfortschritt).
"""
from __future__ import annotations

import logging
import queue
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_fenster = None


def aktiv() -> bool:
    with _lock:
        return _fenster is not None and _fenster.lebt()


def starten(titel: str = "Nova arbeitet …") -> bool:
    """Oeffnet das Fenster (oder nutzt ein offenes weiter). False, wenn kein Fenster moeglich ist."""
    global _fenster
    with _lock:
        if _fenster is not None and _fenster.lebt():
            _fenster.sende(("kopf", titel))
            return True
        try:
            _fenster = _Fenster(titel)
        except Exception:  # noqa: BLE001
            logger.debug("Schau-Fenster nicht moeglich", exc_info=True)
            _fenster = None
            return False
        if not _fenster.lebt():
            _fenster = None
            return False
        return True


def kopf(text: str) -> None:
    _senden(("kopf", str(text)))


def melde(text: str) -> None:
    """Haengt eine neue Zeile an."""
    _senden(("zeile", str(text)))


def schritt(text: str) -> None:
    """Ersetzt die letzte Zeile (fuer einen laufenden Fortschritt, z. B. Prozent)."""
    _senden(("ersetze", str(text)))


def stoppen() -> None:
    global _fenster
    with _lock:
        f, _fenster = _fenster, None
    if f is not None:
        f.sende(("stop", ""))


def _senden(nachricht) -> None:
    with _lock:
        f = _fenster
    if f is None or not f.lebt():
        return
    try:
        f.sende(nachricht)
    except Exception:  # noqa: BLE001 - Anzeige darf die eigentliche Arbeit nie stoeren
        logger.debug("Schau-Fenster: senden fehlgeschlagen", exc_info=True)


class _Fenster:
    def __init__(self, titel: str):
        self._q: queue.Queue = queue.Queue()
        self._lebt = True
        self._bereit = threading.Event()
        self._thread = threading.Thread(target=self._lauf, args=(titel,), name="schau-fenster", daemon=True)
        self._thread.start()
        self._bereit.wait(timeout=6)

    def lebt(self) -> bool:
        return self._lebt and self._thread.is_alive()

    def sende(self, nachricht) -> None:
        self._q.put(nachricht)

    def _lauf(self, titel: str) -> None:
        try:
            import tkinter as tk
        except Exception:  # noqa: BLE001
            self._lebt = False
            self._bereit.set()
            return
        try:
            root = tk.Tk()
        except Exception:  # noqa: BLE001
            self._lebt = False
            self._bereit.set()
            return

        root.title("Nova – Video-Studio")
        root.geometry("640x420")
        try:
            root.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass
        root.configure(bg="#0d1117")

        kopf = tk.Label(root, text=titel, anchor="w", font=("Segoe UI", 11, "bold"),
                        bg="#0d1117", fg="#58a6ff", padx=12, pady=8, wraplength=610, justify="left")
        kopf.pack(fill="x")

        rahmen = tk.Frame(root, bg="#0d1117")
        rahmen.pack(fill="both", expand=True)
        yscroll = tk.Scrollbar(rahmen, orient="vertical")
        yscroll.pack(side="right", fill="y")
        txt = tk.Text(rahmen, wrap="word", bg="#0d1117", fg="#c9d1d9", insertbackground="#c9d1d9",
                      font=("Consolas", 10), padx=12, pady=8, yscrollcommand=yscroll.set,
                      borderwidth=0, highlightthickness=0, state="disabled")
        txt.pack(side="left", fill="both", expand=True)
        yscroll.config(command=txt.yview)

        def _anhaengen(zeile: str) -> None:
            txt.configure(state="normal")
            if txt.index("end-1c") != "1.0":
                txt.insert("end", "\n")
            txt.insert("end", zeile)
            txt.configure(state="disabled")
            txt.see("end")

        def _ersetze_letzte(zeile: str) -> None:
            txt.configure(state="normal")
            # letzte Zeile loeschen und neu setzen
            letzte_anfang = txt.index("end-1c linestart")
            txt.delete(letzte_anfang, "end-1c")
            txt.insert(letzte_anfang, zeile)
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
                    art, wert = self._q.get_nowait()
                    if art == "stop":
                        self._lebt = False
                        try:
                            root.destroy()
                        except Exception:  # noqa: BLE001
                            pass
                        return
                    if art == "kopf":
                        kopf.config(text=wert)
                    elif art == "zeile":
                        _anhaengen(wert)
                    elif art == "ersetze":
                        _ersetze_letzte(wert)
            except queue.Empty:
                pass
            root.after(100, pump)

        def on_close() -> None:
            self._lebt = False
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass

        root.protocol("WM_DELETE_WINDOW", on_close)
        self._bereit.set()
        root.after(100, pump)
        try:
            root.mainloop()
        finally:
            self._lebt = False
