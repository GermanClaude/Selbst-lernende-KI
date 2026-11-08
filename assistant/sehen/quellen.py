"""Woher Nova ihre Bilder bekommt.

Bildschirm (nur Windows, im eigenen Prozess "Auge"):
  * DxcamQuelle - schnell (DXGI Desktop Duplication, bis zur Bildwiederholrate)
  * MssQuelle   - Ersatz, wenn dxcam fehlt oder nicht geht (z.B. Remote-Desktop, ARM-PCs)
  * FakeQuelle  - fuer Tests
  Alle Pakete werden erst beim Oeffnen geladen - fehlen sie, gibt es einen deutschen Hinweis.

Kamera (KameraQuelle): Bilder kommen von aussen herein, z.B. vom App-Fenster (BrowserKamera,
per getUserMedia) - spaeter auch vom Handy. Nur das letzte Bild bleibt im Arbeitsspeicher.

`waehle_quellen` entscheidet bei "auto": Webcam, wenn eine da ist und dein Gehirn Bilder sehen
kann - sonst der Bildschirm.
"""
from __future__ import annotations

import io
import sys
import time

PAKET_HINWEIS = ("F\u00fcr Live-Sehen am Bildschirm fehlen noch Pakete. Im Terminal: /sehen einrichten "
                 "(oder: pip install numpy mss dxcam comtypes winrt-Windows.Media.Ocr).")


class QuellenFehler(RuntimeError):
    """Bildschirm laesst sich nicht aufnehmen (Text fuer den Nutzer)."""


class BildschirmQuelle:
    name = "?"
    ursprung = (0, 0)  # linke obere Ecke des Bildes in Bildschirm-Koordinaten

    def bild(self):  # pragma: no cover - abstrakt
        """Neues Bild als numpy-Array (H x W x 4, BGRA) oder None (gerade keins)."""
        raise NotImplementedError

    def schliessen(self) -> None:
        pass


class DxcamQuelle(BildschirmQuelle):
    name = "dxcam"

    def __init__(self, monitor: int = 0, modul=None):
        if modul is None:
            if sys.platform != "win32":
                raise QuellenFehler("dxcam gibt es nur unter Windows.")
            try:
                import dxcam as modul  # noqa: PLC0415 - bewusst erst hier
            except Exception as exc:  # noqa: BLE001
                raise QuellenFehler(f"dxcam fehlt oder l\u00e4sst sich nicht laden ({type(exc).__name__}).") from exc
        try:
            self._cam = modul.create(output_idx=(monitor or None), output_color="BGRA", processor_backend="numpy")
        except Exception as exc:  # noqa: BLE001 - z.B. DXGI_ERROR_UNSUPPORTED (Hybrid-Laptop, Remote-Desktop)
            raise QuellenFehler(f"dxcam kann diesen Bildschirm nicht aufnehmen ({type(exc).__name__}).") from exc
        if self._cam is None:
            raise QuellenFehler("dxcam hat keinen Bildschirm gefunden.")
        # Wo liegt dieser Bildschirm auf dem Desktop? (Fensterrechtecke -> Bildkoordinaten)
        try:
            ecke = self._cam._output.desc.DesktopCoordinates
            self.ursprung = (int(ecke.left), int(ecke.top))
        except Exception:  # noqa: BLE001
            if monitor:
                raise QuellenFehler("dxcam kennt die Lage dieses Bildschirms nicht \u2013 ich nehme mss.") from None
            self.ursprung = (0, 0)  # Hauptbildschirm liegt immer bei (0, 0)

    def bild(self):
        return self._cam.grab(new_frame_only=False)

    def schliessen(self) -> None:
        # Bewusst kein release() (dxcam-Fehler #144: Absturz beim Freigeben) - der Prozess endet ohnehin.
        self._cam = None


class MssQuelle(BildschirmQuelle):
    name = "mss"

    def __init__(self, monitor: int = 0, modul=None, np=None):
        try:
            if modul is None:
                import mss as modul  # noqa: PLC0415
            if np is None:
                import numpy as np  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            raise QuellenFehler(f"mss/numpy fehlen ({type(exc).__name__}). {PAKET_HINWEIS}") from exc
        self._np = np
        try:
            self._sct = modul.mss()
            monitore = self._sct.monitors
            self._mon = monitore[min(len(monitore) - 1, monitor + 1)] if len(monitore) > 1 else monitore[0]
        except Exception as exc:  # noqa: BLE001
            raise QuellenFehler(f"mss kann den Bildschirm nicht aufnehmen ({type(exc).__name__}).") from exc
        self.ursprung = (int(self._mon.get("left", 0)), int(self._mon.get("top", 0)))

    def bild(self):
        shot = self._sct.grab(self._mon)
        return self._np.asarray(shot)  # H x W x 4, BGRA

    def schliessen(self) -> None:
        try:
            self._sct.close()
        except Exception:  # noqa: BLE001
            pass


class FakeQuelle(BildschirmQuelle):
    """Fuer Tests: liefert die gegebenen Bilder nacheinander (das letzte bleibt stehen)."""

    name = "fake"

    def __init__(self, bilder=None, fehler_ab: int | None = None):
        self._bilder = list(bilder or [])
        self._i = 0
        self.fehler_ab = fehler_ab
        self.geschlossen = False

    def bild(self):
        if self.fehler_ab is not None and self._i >= self.fehler_ab:
            raise OSError("Testfehler")
        if not self._bilder:
            return None
        bild = self._bilder[min(self._i, len(self._bilder) - 1)]
        self._i += 1
        return bild

    def schliessen(self) -> None:
        self.geschlossen = True


def oeffne_bildschirm(wunsch: str = "auto", monitor: int = 0, dxcam_modul=None, mss_modul=None,
                      np_modul=None) -> tuple[BildschirmQuelle | None, str]:
    """dxcam -> mss -> aus. Gibt (Quelle oder None, Grund/Hinweis auf Deutsch) zurueck."""
    gruende = []
    if wunsch in ("auto", "dxcam"):
        try:
            return DxcamQuelle(monitor, modul=dxcam_modul), ""
        except QuellenFehler as exc:
            gruende.append(str(exc))
    if wunsch in ("auto", "mss", "dxcam"):
        try:
            quelle = MssQuelle(monitor, modul=mss_modul, np=np_modul)
            return quelle, (gruende[0] + " Ich nehme stattdessen mss.") if gruende else ""
        except QuellenFehler as exc:
            gruende.append(str(exc))
    return None, " ".join(gruende) or "Keine Bildschirmaufnahme m\u00f6glich."


# -- Kamera -----------------------------------------------------------------------------
class KameraQuelle:
    """Eine Kamera, deren Bilder von aussen hereinkommen (Browser, spaeter Handy)."""

    art = "kamera"
    name = "Kamera"
    MAX_ALTER = 10.0  # aelter = Kamera ist aus

    def __init__(self, uhr=time.monotonic, ruhe: float = 4.0, schwelle: float = 14.0):
        self._uhr = uhr
        self._letztes: bytes | None = None
        self._zeit = 0.0
        self._klein = None
        self._ref = None
        self._ruhig_seit: float | None = None
        self.ruhe = ruhe
        self.schwelle = schwelle
        self.vorhanden: bool | None = None  # meldet das Fenster (enumerateDevices)
        self.bilder = 0

    def aktiv(self) -> bool:
        return self._letztes is not None and self._uhr() - self._zeit <= self.MAX_ALTER

    def letztes(self) -> bytes | None:
        return self._letztes if self.aktiv() else None

    def vergessen(self) -> None:
        self._letztes = self._klein = self._ref = None
        self._ruhig_seit = None

    def nimm(self, data: bytes) -> dict | None:
        """Neues Bild (JPEG/PNG/WebP-Bytes). Gibt ein Ereignis zurueck, wenn sich nach einer
        ruhigen Phase deutlich etwas veraendert hat (jemand kommt, haelt etwas in die Kamera ...)."""
        jetzt = self._uhr()
        self._letztes, self._zeit = data, jetzt
        self.bilder += 1
        klein = _klein_grau(data)
        if klein is None:
            return None
        vorher, self._klein = self._klein, klein
        if vorher is None or len(vorher) != len(klein):
            self._ref, self._ruhig_seit = klein, jetzt
            return None
        bewegung = sum(abs(a - b) for a, b in zip(klein, vorher)) / len(klein)
        if bewegung < self.schwelle / 2:
            if self._ruhig_seit is None:
                self._ruhig_seit = jetzt
            if jetzt - self._ruhig_seit >= self.ruhe:
                ref = self._ref
                self._ref = klein
                if ref is not None and sum(abs(a - b) for a, b in zip(klein, ref)) / len(klein) >= self.schwelle:
                    return {"art": "bewegung", "quelle": self.art, "app": self.name,
                            "anteil": 1.0, "text": "Vor der Kamera hat sich etwas ver\u00e4ndert."}
            return None
        self._ruhig_seit = None
        return None


class BrowserKamera(KameraQuelle):
    """Die PC-Webcam ueber das App-Fenster (getUserMedia, Bilder per POST /api/kamera/bild)."""

    art = "webcam"
    name = "Webcam"


class HandyKameraQuelle(KameraQuelle):
    """Das Handy als Kamera (assistant/kamera): HandyQuelle.pumpe() reicht jede Sekunde ein neues
    Bild per nimm(jpeg) herein - danach wie die Webcam (nur das letzte Bild, nur im Speicher)."""

    art = "handy"
    name = "Handy-Kamera"


def _klein_grau(data: bytes) -> list[int] | None:
    """32x24 Graustufen (fuer die Bewegungserkennung) - None ohne Pillow oder bei kaputtem Bild."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None
    try:
        with Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as bild:
            if bild.size[0] * bild.size[1] > 40_000_000:
                return None
            bild.draft("L", (64, 48))
            return list(bild.convert("L").resize((32, 24)).tobytes())
    except Exception:  # noqa: BLE001
        return None


def waehle_quellen(wunsch: str, kamera_vorhanden: bool, bildschirm_moeglich: bool,
                   sieht_bilder: bool, handy_verbunden: bool = False) -> tuple[set[str], str]:
    """Welche Quellen laufen sollen -> ({"bildschirm", "webcam", "handy"} Teilmenge, Hinweis).
    auto: PC-Webcam (wenn da) -> schon gekoppeltes Handy -> Bildschirm."""
    hinweis = ""
    if wunsch == "handy":
        if not sieht_bilder:
            hinweis = ("Dein Gehirn kann keine Bilder sehen \u2013 mit der Handy-Kamera bemerke ich nur Bewegung. "
                       "Besser: ein Modell mit Augen (z.B. Claude oder deepseek-flash).")
        return {"handy"}, hinweis
    if wunsch == "bildschirm":
        return ({"bildschirm"}, "") if bildschirm_moeglich else (set(), "Den Bildschirm kann ich hier nicht sehen "
                                                                     "(nur unter Windows).")
    if wunsch == "webcam":
        if not kamera_vorhanden:
            return set(), "Ich finde keine Webcam."
        if not sieht_bilder:
            hinweis = ("Dein Gehirn kann keine Bilder sehen \u2013 mit der Webcam bemerke ich nur Bewegung. "
                       "Besser: ein Modell mit Augen (z.B. Claude oder deepseek-flash).")
        return {"webcam"}, hinweis
    if wunsch == "beides":
        quellen = set()
        if bildschirm_moeglich:
            quellen.add("bildschirm")
        if kamera_vorhanden:
            quellen.add("webcam")
        if not quellen:
            return set(), "Weder Bildschirm noch Webcam sind hier m\u00f6glich."
        if quellen != {"bildschirm", "webcam"}:
            hinweis = "Nur " + ("der Bildschirm" if "bildschirm" in quellen else "die Webcam") + " ist m\u00f6glich."
        return quellen, hinweis
    # auto: Webcam, wenn da und sinnvoll (Gehirn mit Augen), sonst Bildschirm
    if kamera_vorhanden and (sieht_bilder or not bildschirm_moeglich):
        return {"webcam"}, ""
    if handy_verbunden and (sieht_bilder or not bildschirm_moeglich):
        return {"handy"}, ""
    if bildschirm_moeglich:
        return {"bildschirm"}, ""
    return set(), ("Hier gibt es weder eine Webcam noch Bildschirm-Sehen (das geht nur unter Windows). "
                   "In der App kannst du eine Webcam nutzen.")
