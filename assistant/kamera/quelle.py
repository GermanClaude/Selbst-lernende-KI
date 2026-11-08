"""Kamera-Quellen fuer das Live-Sehen-"Auge": eine gemeinsame Schnittstelle + Handy-Adapter.

Schnittstelle (``HandyQuellenProtokoll``, Abfrage-Modell - das Auge holt sich Bilder, wenn es will):
    name: str                         - Anzeigename, z.B. "Handy"
    start() -> dict                   - Quelle einschalten; Rueckgabe je nach Quelle
                                        (HandyQuelle: {"link", "ablauf", "code"} fuer den QR-Code)
    stop() -> None                    - ausschalten, alles freigeben (mehrfach aufrufbar)
    latest_frame(max_kante=1280, als="pil") -> PIL.Image | bytes | None
                                      - letztes Bild (als="jpeg" -> JPEG-Bytes), None = gerade keins
    status() -> dict                  - mind. {"zustand": "wartet"|"verbunden"|"getrennt"|"fehler",
                                        "fehler": str|None}

So nutzt das Live-Sehen das Handy (Vorschlag fuer die Einbindung):
  * Abfragen: Das Auge/der SehDienst ruft z.B. jede Sekunde ``quelle.latest_frame(max_kante=1280,
    als="jpeg")`` und behandelt das Bild wie ein Webcam-Bild. None heisst: nichts Neues/getrennt.
  * Schieben (so macht es Live-Sehen): ``assistant.sehen.quellen.HandyKameraQuelle`` (eine
    KameraQuelle im Schieben-Modell - Bilder kommen per ``nimm(jpeg)`` herein, wie bei der Browser-
    Webcam; deshalb heisst die Schnittstelle hier HandyQuellenProtokoll) wird so gefuettert:
    ``stopp = handy.pumpe(sehen_kamera.nimm, intervall=1.0)`` - nur neue Bilder werden
    weitergereicht; ``stopp()`` beendet das. Dann funktionieren Bewegungserkennung und
    "letztes Bild" der Sehen-Quelle ohne Aenderung.
  * Zustimmung/Anzeige: Das Handy zeigt selbst "Nova sieht zu", solange verbunden. Nova sollte
    trotzdem im eigenen Fenster anzeigen, dass die Handy-Kamera aktiv ist (status()["zustand"]).
"""
from __future__ import annotations

import threading
from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class HandyQuellenProtokoll(Protocol):
    name: str

    def start(self) -> dict: ...

    def stop(self) -> None: ...

    def latest_frame(self, max_kante: int | None = 1280, als: str = "pil"): ...

    def status(self) -> dict: ...


class HandyQuelle:
    """Adapter: HandyKamera als HandyQuellenProtokoll (plus ``pumpe`` fuer das Schieben-Modell)."""

    name = "Handy"
    art = "handy"

    def __init__(self, kamera=None, **kamera_optionen):
        if kamera is None:
            from .webrtc import HandyKamera  # noqa: PLC0415 - aiortc erst bei Bedarf

            kamera = HandyKamera(**kamera_optionen)
        self.kamera = kamera
        self._pumpen: list[threading.Event] = []

    def start(self) -> dict:
        """Neue Kopplung -> {"link", "ablauf", "code"}. Wirft HandyKameraFehler (z.B. Pakete fehlen)."""
        return self.kamera.start().als_dict()

    def stop(self) -> None:
        for halt in self._pumpen:
            halt.set()
        self._pumpen.clear()
        self.kamera.stop()

    def latest_frame(self, max_kante: int | None = 1280, als: str = "pil"):
        return self.kamera.latest_frame(max_kante=max_kante, als=als)

    def status(self) -> dict:
        return self.kamera.status()

    def aktiv(self) -> bool:
        return self.kamera.zustand == "verbunden"

    def pumpe(self, nimm: Callable[[bytes], object], intervall: float = 1.0, max_kante: int = 1280,
              qualitaet: int = 75) -> Callable[[], None]:
        """Reicht alle ``intervall`` Sekunden ein NEUES Bild als JPEG an ``nimm`` weiter.
        Gibt eine Funktion zurueck, die das Weiterreichen beendet."""
        halt = threading.Event()
        self._pumpen.append(halt)

        def lauf():
            zuletzt = -1
            while not halt.wait(intervall):
                nr = self.kamera.bild_nr
                if nr == zuletzt:
                    continue
                jpeg = self.kamera.latest_frame(max_kante=max_kante, als="jpeg", qualitaet=qualitaet)
                if jpeg is None:
                    continue
                zuletzt = nr
                try:
                    nimm(jpeg)
                except Exception:  # noqa: BLE001 - Empfaenger-Fehler duerfen die Pumpe nicht stoppen
                    pass

        threading.Thread(target=lauf, name="handy-kamera-pumpe", daemon=True).start()
        return halt.set
