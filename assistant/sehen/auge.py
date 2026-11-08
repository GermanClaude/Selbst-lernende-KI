"""Das "Auge": schaut schnell auf den Bildschirm und macht aus Veraenderungen kleine Text-Ereignisse.

Laeuft unter Windows in einem eigenen Prozess ("nova-auge"): dxcam veraendert prozessweite
Einstellungen (DPI) und kann beim Freigeben abstuerzen - das soll nie das App-Fenster treffen.
Fuer Tests (und ausserhalb von Windows mit Ersatzteilen) laeuft dieselbe Schleife in einem Thread.

Verbindung nur ueber zwei Warteschlangen (nie Pixel nach draussen, ausser auf Anfrage ein
verkleinertes JPEG des Vordergrund-Fensters):
  Befehle rein:  ("pause",) ("weiter",) ("stop",) ("bild", nummer) ("fps", n)
  Meldungen raus: ("bereit", info) ("ereignis", dict) ("bild", nummer, jpeg|None, grund) ("ende", grund)
Ist die Ausgabe voll, faellt die aelteste Meldung weg.

Was das Auge nie tut: Bilder speichern, Text aus Passwortfeldern oder ausgeschlossenen Fenstern
lesen, Novas eigenes Fenster ansehen. Weiss es nicht, ob ein Passwortfeld aktiv ist, liest es
keinen Text und gibt kein Bild heraus.
"""
from __future__ import annotations

import queue
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from .differenz import Differenz
from .einstellungen import ist_ausgeschlossen, parse_hotkey
from .ereignis import hat_fehlerwort, maskiere
from .uia import OK, PASSWORT, UNBEKANNT

MAX_EREIGNISSE_PRO_SEKUNDE = 10
OCR_ABSTAND = 0.4          # hoechstens ~2-3 Texterkennungen pro Sekunde
TITEL_ABSTAND = 1.0        # Titel-Aenderungen desselben Fensters hoechstens einmal pro Sekunde
GESCHUETZT_ABSTAND = 30.0  # "Passwortfeld aktiv" hoechstens alle 30 s melden


@dataclass
class AugenTeile:
    """Was die Schleife braucht - fuer Tests austauschbar."""

    quelle: Any = None                       # BildschirmQuelle (None = selbst oeffnen)
    vordergrund: Callable[[], dict | None] | None = None
    fenster_info: Callable[[Any], dict | None] | None = None
    dialog_text: Callable[[Any], str] | None = None
    waechter_fabrik: Callable | None = None  # (melde, hotkey) -> Thread mit stop()
    passwort: Any = None                     # PasswortPruefer
    ocr: Any = None                          # WindowsOcr
    jpeg: Callable | None = None
    oeffne: Callable | None = None           # (wunsch, monitor) -> (quelle, grund)
    uhr: Callable[[], float] = time.monotonic
    schlafe: Callable[[float], None] = time.sleep


def senden(ausgang, nachricht) -> None:
    """In die Ausgabe legen - ist sie voll, die aelteste Meldung verwerfen."""
    try:
        ausgang.put_nowait(nachricht)
        return
    except queue.Full:
        pass
    except Exception:  # noqa: BLE001 - Verbindung weg
        return
    try:
        ausgang.get_nowait()
    except Exception:  # noqa: BLE001
        pass
    try:
        ausgang.put_nowait(nachricht)
    except Exception:  # noqa: BLE001
        pass


def als_jpeg(bgra, max_kante: int = 1280, qualitaet: int = 75) -> bytes | None:
    """numpy BGRA -> verkleinertes JPEG (nur im Speicher)."""
    try:
        import io

        import numpy as np
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None
    try:
        h, w = bgra.shape[:2]
        if h < 2 or w < 2:
            return None
        bild = Image.frombytes("RGB", (w, h), np.ascontiguousarray(bgra[..., :4]).tobytes(), "raw", "BGRX")
        bild.thumbnail((max_kante, max_kante))
        puffer = io.BytesIO()
        bild.save(puffer, "JPEG", quality=int(qualitaet), optimize=True)
        return puffer.getvalue()
    except Exception:  # noqa: BLE001
        return None


def _ausschnitt(bild, rechteck, ursprung):
    """Teil des Bildes, der zum Fensterrechteck (Bildschirm-Koordinaten) gehoert - None, wenn leer."""
    if bild is None or not rechteck:
        return None
    h, w = bild.shape[:2]
    x, y, b, hh = rechteck
    x0, y0 = max(0, x - ursprung[0]), max(0, y - ursprung[1])
    x1, y1 = min(w, x - ursprung[0] + b), min(h, y - ursprung[1] + hh)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return bild[y0:y1, x0:x1]


def _schnitt(a, b):
    """Schnitt zweier Rechtecke (x, y, b, h) - None, wenn leer."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


class Auge:
    def __init__(self, befehle, ausgang, einst: dict, teile: AugenTeile):
        self.befehle = befehle
        self.ausgang = ausgang
        self.einst = einst
        self.t = teile
        self.uhr = teile.uhr
        self.pause = False
        self.laeuft = True
        self.fps = max(1, min(240, int(einst.get("fps") or 15)))
        self.ausnahmen = [str(a).lower() for a in einst.get("ausnahmen") or []]
        self.eigene_pid = int(einst.get("eigene_pid") or 0)
        # Novas eigene Fenster ohne eigenen Prozess (Browser-Ersatzfenster, Terminal): am Titel
        self.eigene_titel = [str(t).lower() for t in einst.get("eigene_titel") or [] if str(t).strip()]
        self.diff = Differenz()
        self.signale: queue.Queue = queue.Queue(maxsize=500)
        self.vorne: dict | None = None
        self.vorne_privat = False
        self.vorne_eigen = False
        self._titel_zeit = 0.0
        self._ocr_zeit = 0.0
        self._geschuetzt_zeit = -1e9
        self._letzter_text = ""
        self._raus: deque[float] = deque()
        self._fehler: deque[float] = deque()
        self._poll = 0.0
        self.bild = None
        self.quelle = teile.quelle
        self.waechter = None

    # -- Ausgabe ---------------------------------------------------------------------------
    def melde(self, art: str, **daten) -> None:
        jetzt = self.uhr()
        while self._raus and jetzt - self._raus[0] > 1.0:
            self._raus.popleft()
        if len(self._raus) >= MAX_EREIGNISSE_PRO_SEKUNDE and art not in ("pause", "weiter", "quelle_fehler"):
            return
        self._raus.append(jetzt)
        senden(self.ausgang, ("ereignis", {"art": art, **daten}))

    # -- Vordergrund-Fenster ------------------------------------------------------------------
    def _signal(self, art: str, hwnd) -> None:
        try:
            self.signale.put_nowait((art, hwnd))
        except queue.Full:
            pass

    def _ist_eigen(self, info: dict) -> bool:
        if self.eigene_pid and info.get("pid") == self.eigene_pid:
            return True
        titel = str(info.get("titel") or "").lower()
        return any(t in titel for t in self.eigene_titel)

    def _dialog_melden(self, info: dict) -> None:
        text = self.t.dialog_text(info.get("hwnd")) if self.t.dialog_text else ""
        self.melde("dialog", quelle="fenster", app=info.get("exe", ""), titel=info.get("titel", ""),
                   text=maskiere(text))

    def _vorne_pruefen(self, art: str = "poll", hwnd=None) -> None:
        if art == "taste":
            self._pause_umschalten()
            return
        if art in ("dialog", "alarm"):
            info = self.t.fenster_info(hwnd) if (hwnd and self.t.fenster_info is not None) else None
            if not info or (art == "alarm" and info.get("klasse") != "#32770"):
                return
            if self._ist_eigen(info) or ist_ausgeschlossen(info.get("exe"), info.get("titel"), self.ausnahmen):
                return
            self._dialog_melden(info)
            return
        info = self.t.vordergrund() if self.t.vordergrund is not None else None
        if not info:
            return
        vorher, self.vorne = self.vorne, info
        eigen = self._ist_eigen(info)
        privat = ist_ausgeschlossen(info.get("exe"), info.get("titel"), self.ausnahmen)
        if vorher is None or info.get("hwnd") != vorher.get("hwnd"):
            self.vorne_eigen, self.vorne_privat = eigen, privat
            self.diff.zuruecksetzen()
            self._letzter_text = ""
            self._titel_zeit = self.uhr()
            if eigen:
                return
            if privat:
                self.melde("privat", app=info.get("exe", ""), privat=True)
            elif info.get("klasse") == "#32770":
                self._dialog_melden(info)
            else:
                self.melde("fenster", quelle="fenster", app=info.get("exe", ""), titel=info.get("titel", ""))
            return
        if vorher.get("titel") == info.get("titel"):
            return
        # gleiches Fenster, neuer Titel (z.B. anderer Browser-Tab - oder ein privates Fenster)
        war_privat, self.vorne_privat, self.vorne_eigen = self.vorne_privat, privat, eigen
        if eigen:
            return
        if privat:
            if not war_privat:
                self.diff.zuruecksetzen()
                self.melde("privat", app=info.get("exe", ""), privat=True)
            return
        jetzt = self.uhr()
        if jetzt - self._titel_zeit >= TITEL_ABSTAND or hat_fehlerwort(info.get("titel", "")):
            self._titel_zeit = jetzt
            self.melde("titel", quelle="fenster", app=info.get("exe", ""), titel=info.get("titel", ""))

    def _pause_umschalten(self) -> None:
        self.pause = not self.pause
        if self.pause:
            self.bild = None  # nichts mehr im Speicher behalten
            self.diff.zuruecksetzen()
        self.melde("pause" if self.pause else "weiter", quelle="taste")

    # -- Befehle ---------------------------------------------------------------------------------
    def _befehle(self) -> None:
        while True:
            try:
                befehl = self.befehle.get_nowait()
            except queue.Empty:
                return
            except Exception:  # noqa: BLE001 - Verbindung weg: aufhoeren
                self.laeuft = False
                return
            if not isinstance(befehl, tuple) or not befehl:
                continue
            art = befehl[0]
            if art == "stop":
                self.laeuft = False
                return
            if art == "pause" and not self.pause:
                self.pause = True
                self.bild = None
                self.diff.zuruecksetzen()
            elif art == "weiter" and self.pause:
                self.pause = False
            elif art == "fps" and len(befehl) > 1:
                try:
                    self.fps = max(1, min(240, int(befehl[1])))
                except (TypeError, ValueError):
                    pass
            elif art == "bild" and len(befehl) > 1:
                daten, grund = self.schnappschuss()
                senden(self.ausgang, ("bild", befehl[1], daten, grund))

    def _passwort(self) -> str:
        pruefer = self.t.passwort
        if pruefer is None or not getattr(pruefer, "bereit", False):
            return UNBEKANNT
        return pruefer.pruefe()

    def schnappschuss(self) -> tuple[bytes | None, str]:
        """Verkleinertes JPEG des Vordergrund-Fensters - oder (None, Grund)."""
        if self.pause:
            return None, "pause"
        if not self.einst.get("bilder", True):
            return None, "aus"
        if self.vorne_eigen or self.vorne_privat:
            return None, "privat"
        status = self._passwort()
        if status != OK:
            return None, "passwort" if status == PASSWORT else "unbekannt"
        rechteck = (self.vorne or {}).get("rechteck")
        teil = _ausschnitt(self.bild, rechteck, getattr(self.quelle, "ursprung", (0, 0))) if rechteck else None
        if teil is None:
            return None, "kein_bild"
        jpeg = (self.t.jpeg or als_jpeg)(teil, int(self.einst.get("max_kante") or 1280),
                                         int(self.einst.get("jpeg_qualitaet") or 75))
        return (jpeg, "") if jpeg else (None, "kein_bild")

    # -- Bilder ----------------------------------------------------------------------------------
    def _bild_verarbeiten(self, bild, jetzt: float) -> None:
        aenderung = self.diff.vergleiche(bild, jetzt)
        if aenderung is None:
            return
        app, titel = (self.vorne or {}).get("exe", ""), (self.vorne or {}).get("titel", "")
        if aenderung.art == "video":
            self.melde("video", app=app, titel=titel, anteil=round(aenderung.anteil, 3))
            return
        text = ""
        ursprung = getattr(self.quelle, "ursprung", (0, 0))
        rechteck = (self.vorne or {}).get("rechteck")
        bereich = aenderung.bereich
        if rechteck:
            fenster_im_bild = (rechteck[0] - ursprung[0], rechteck[1] - ursprung[1], rechteck[2], rechteck[3])
            bereich = _schnitt(aenderung.bereich, fenster_im_bild)
        ocr = self.t.ocr
        if (bereich is not None and ocr is not None and getattr(ocr, "bereit", False) and self.einst.get("ocr", True)
                and jetzt - self._ocr_zeit >= OCR_ABSTAND):
            status = self._passwort()
            if status == PASSWORT:
                if jetzt - self._geschuetzt_zeit >= GESCHUETZT_ABSTAND:
                    self._geschuetzt_zeit = jetzt
                    self.melde("geschuetzt", app=app, privat=True)
                return
            if status == OK:
                self._ocr_zeit = jetzt
                x, y, b, h = bereich
                text = " ".join(maskiere(ocr.erkenne(bild[y:y + h, x:x + b])).split())[:600]
        if text and text != self._letzter_text:
            self._letzter_text = text
            self.melde("text", quelle="ocr", app=app, titel=titel, text=text, anteil=round(aenderung.anteil, 3),
                       bereich=list(aenderung.bereich))
        else:
            self.melde("inhalt", app=app, titel=titel, anteil=round(aenderung.anteil, 3),
                       bereich=list(aenderung.bereich))

    def _quelle_fehler(self, jetzt: float, exc: Exception) -> bool:
        """False = aufgeben."""
        self._fehler.append(jetzt)
        while self._fehler and jetzt - self._fehler[0] > 10:
            self._fehler.popleft()
        if len(self._fehler) < 4:
            return True
        name = getattr(self.quelle, "name", "?")
        oeffne = self.t.oeffne
        if name == "dxcam" and oeffne is not None:
            try:
                self.quelle.schliessen()
            except Exception:  # noqa: BLE001
                pass
            neu, grund = oeffne("mss", int(self.einst.get("monitor") or 0))
            if neu is not None:
                self.quelle = neu
                self._fehler.clear()
                self.melde("quelle_fehler", text="dxcam geht gerade nicht \u2013 ich nehme mss.")
                return True
        self.melde("quelle_fehler", text=f"Die Bildschirmaufnahme geht nicht mehr ({type(exc).__name__}).")
        return False

    # -- Schleife ----------------------------------------------------------------------------------
    def lauf(self) -> str:
        hinweise = []
        if self.quelle is None and self.t.oeffne is not None:
            self.quelle, grund = self.t.oeffne(str(self.einst.get("aufnahme") or "auto"),
                                               int(self.einst.get("monitor") or 0))
            if grund:
                hinweise.append(grund)
        if self.quelle is None:
            return "Keine Bildschirmaufnahme m\u00f6glich."
        hotkey = parse_hotkey(str(self.einst.get("hotkey") or ""))
        if self.t.waechter_fabrik is not None:
            try:
                self.waechter = self.t.waechter_fabrik(self._signal, hotkey)
                self.waechter.start()
                self.waechter.bereit.wait(2.0)
            except Exception:  # noqa: BLE001 - dann eben nur mit Nachschauen
                self.waechter = None
        ocr = self.t.ocr
        if ocr is not None and self.einst.get("ocr", True):
            try:
                if not ocr.start(str(self.einst.get("ocr_sprache") or "de-DE")):
                    hinweise.append(getattr(ocr, "fehler", "") or "Texterkennung nicht verf\u00fcgbar.")
                elif getattr(ocr, "hinweis", ""):
                    hinweise.append(ocr.hinweis)
            except Exception:  # noqa: BLE001
                hinweise.append("Texterkennung nicht verf\u00fcgbar.")
        pruefer = self.t.passwort
        if pruefer is not None:
            try:
                pruefer.start()
            except Exception:  # noqa: BLE001
                pass
        passwortschutz = pruefer is not None and bool(getattr(pruefer, "bereit", False))
        if not passwortschutz:
            hinweise.append("Ohne Passwortfeld-Erkennung (UI Automation) lese ich keinen Text und schicke keine "
                            "Bilder \u2013 nur Fenstertitel.")
        senden(self.ausgang, ("bereit", {
            "quelle": getattr(self.quelle, "name", "?"),
            "ocr": bool(ocr is not None and getattr(ocr, "bereit", False)),
            "passwortschutz": passwortschutz,
            "taste": getattr(self.waechter, "taste_ok", None),
            "hinweise": [h for h in hinweise if h],
        }))
        self._vorne_pruefen()
        grund = "stop"
        try:
            while self.laeuft:
                takt = self.uhr()
                self._befehle()
                if not self.laeuft:
                    break
                while True:
                    try:
                        art, hwnd = self.signale.get_nowait()
                    except queue.Empty:
                        break
                    self._vorne_pruefen(art, hwnd)
                if takt - self._poll >= 0.5:
                    self._poll = takt
                    self._vorne_pruefen()
                if self.pause:
                    self.t.schlafe(0.05)
                    continue
                if not (self.vorne_eigen or self.vorne_privat):
                    try:
                        bild = self.quelle.bild()
                    except Exception as exc:  # noqa: BLE001
                        if not self._quelle_fehler(takt, exc):
                            grund = "quelle"
                            break
                        bild = None
                    if bild is not None:
                        self.bild = bild
                        self._bild_verarbeiten(bild, takt)
                else:
                    self.bild = None  # nichts von privaten Fenstern im Speicher
                rest = 1.0 / self.fps - (self.uhr() - takt)
                if rest > 0:
                    self.t.schlafe(min(rest, 0.25))
        finally:
            self.bild = None
            if self.waechter is not None:
                try:
                    self.waechter.stop()
                except Exception:  # noqa: BLE001
                    pass
            try:
                self.quelle.schliessen()
            except Exception:  # noqa: BLE001
                pass
        return grund


def _standard_teile(einst: dict) -> AugenTeile | str:
    """Echte Teile (Windows) - oder ein Grund, warum es hier nicht geht."""
    if einst.get("fake"):
        return _fake_teile(einst)
    if sys.platform != "win32":
        return "Bildschirm-Sehen gibt es nur unter Windows."
    from . import windows
    from .ocr import WindowsOcr
    from .quellen import oeffne_bildschirm
    from .uia import PasswortPruefer

    return AugenTeile(
        vordergrund=windows.vordergrund, fenster_info=windows.fenster_info, dialog_text=windows.dialog_text,
        waechter_fabrik=lambda melde, hotkey: windows.WinEventWaechter(melde, hotkey),
        passwort=PasswortPruefer(), ocr=WindowsOcr() if einst.get("ocr", True) else None,
        oeffne=lambda wunsch, monitor: oeffne_bildschirm(wunsch, monitor),
    )


def _fake_teile(einst: dict) -> AugenTeile:
    """Fuer Tests im echten Prozess: ein schwarzer Bildschirm, auf dem ein Fenster aufgeht."""
    import numpy as np

    from .ocr import FakeOcr
    from .quellen import FakeQuelle
    from .uia import FakePruefer

    leer = np.zeros((180, 320, 4), np.uint8)
    neu = leer.copy()
    neu[40:120, 60:260] = 255
    fake = einst["fake"] if isinstance(einst["fake"], dict) else {}
    bilder = [leer] * 3 + [neu] * 400
    return AugenTeile(
        quelle=FakeQuelle(bilder),
        vordergrund=lambda: {"hwnd": 1, "pid": 4242, "exe": fake.get("exe", "notepad.exe"),
                             "titel": fake.get("titel", "Unbenannt - Editor"), "klasse": "Notepad",
                             "rechteck": (0, 0, 320, 180)},
        passwort=FakePruefer(fake.get("passwort", OK)), ocr=FakeOcr(fake.get("text", "Fehler: Datei fehlt")),
    )


def hauptschleife(befehle, ausgang, einst: dict, teile: AugenTeile | None = None) -> None:
    teile = teile if teile is not None else _standard_teile(einst)
    if isinstance(teile, str):
        senden(ausgang, ("ende", teile))
        return
    try:
        grund = Auge(befehle, ausgang, einst, teile).lauf()
    except Exception as exc:  # noqa: BLE001
        grund = f"Fehler im Auge ({type(exc).__name__})"
    senden(ausgang, ("ende", grund))


def _prozess_einstieg(befehle, ausgang, einst: dict) -> None:  # pragma: no cover - eigener Prozess
    sys.coinit_flags = 0  # COM als MTA (UI Automation, dxcam) - vor jedem comtypes-Import
    if sys.platform == "win32":
        # Nur in diesem Prozess: echte Bildpunkte (Fensterrechtecke passen dann zum aufgenommenen Bild,
        # auch mit mss und bei 125/150 % Skalierung). Das App-Fenster bleibt davon unberuehrt.
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:  # noqa: BLE001
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:  # noqa: BLE001
                pass
    hauptschleife(befehle, ausgang, einst)


class AugeVerbindung:
    """Startet das Auge (Prozess oder Thread) und spricht mit ihm."""

    def __init__(self, einst: dict, als_prozess: bool = True, teile: AugenTeile | None = None):
        self.einst = dict(einst)
        self.als_prozess = als_prozess
        self.teile = teile
        self._proc = None
        self._thread = None
        self.befehle = None
        self.ausgang = None

    def start(self) -> None:
        if self.als_prozess:
            import multiprocessing

            ctx = multiprocessing.get_context("spawn")
            self.befehle, self.ausgang = ctx.Queue(maxsize=100), ctx.Queue(maxsize=200)
            self._proc = ctx.Process(target=_prozess_einstieg, args=(self.befehle, self.ausgang, self.einst),
                                     name="nova-auge", daemon=True)
            self._proc.start()
        else:
            self.befehle, self.ausgang = queue.Queue(maxsize=100), queue.Queue(maxsize=200)
            self._thread = threading.Thread(target=hauptschleife, name="nova-auge",
                                            args=(self.befehle, self.ausgang, self.einst, self.teile), daemon=True)
            self._thread.start()

    def senden(self, befehl: tuple) -> None:
        try:
            self.befehle.put_nowait(befehl)
        except Exception:  # noqa: BLE001
            pass

    def lies(self, timeout: float = 0.1):
        try:
            return self.ausgang.get(timeout=timeout)
        except queue.Empty:
            return None
        except Exception:  # noqa: BLE001 - Prozess weg
            return None

    def lebt(self) -> bool:
        if self._proc is not None:
            return self._proc.is_alive()
        return self._thread is not None and self._thread.is_alive()

    def stop(self, warten: float = 2.0) -> None:
        self.senden(("stop",))
        if self._proc is not None:
            self._proc.join(warten)
            if self._proc.is_alive():
                self._proc.terminate()
                self._proc.join(1.0)
            for q in (self.befehle, self.ausgang):
                try:
                    q.cancel_join_thread()
                    q.close()
                except Exception:  # noqa: BLE001
                    pass
        elif self._thread is not None:
            self._thread.join(warten)
