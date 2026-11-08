"""Aenderungserkennung fuer Bildschirmbilder - billig genug fuer jedes Bild (unter 1 ms).

Verglichen wird nur jeder `schritt`-te Bildpunkt (Gruenkanal ~ Helligkeit), mit wanderndem
Versatz: so faellt auch eine 1 Pixel duenne neue Linie nach hoechstens `schritt` Bildern auf.
Verglichen wird mit einem Referenzbild (dem letzten "ruhigen" Stand). Eine Aenderung wird erst
gemeldet, wenn sich das Bild `ruhe` Sekunden lang nicht mehr bewegt (oder spaetestens nach
`max_warten` Sekunden). Bewegt sich lange ein grosser Teil (Video, Spiel), kommt einmal "video".

Kleinigkeiten (blinkender Cursor, Uhr) liegen unter `min_anteil` und werden ignoriert.
Braucht numpy (kommt mit dem Paket fuer Live-Sehen). Die Bilder werden nicht kopiert - wer
sie uebergibt, darf sie danach nicht mehr veraendern (die Quellen liefern jedes Mal ein neues).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Aenderung:
    art: str                 # "inhalt" | "video"
    anteil: float            # Anteil geaenderter Bildpunkte (0 ... 1)
    bereich: tuple[int, int, int, int]  # (x, y, breite, hoehe) im Bild
    unruhig: bool = False    # gemeldet, obwohl es sich noch bewegt (nach max_warten)


class Differenz:
    def __init__(self, schritt: int = 4, schwelle: int = 24, min_anteil: float = 0.003, kacheln=(16, 9),
                 ruhe: float = 0.4, max_warten: float = 2.0, video_anteil: float = 0.25, video_dauer: float = 2.0):
        self.schritt = max(1, int(schritt))
        self.schwelle = int(schwelle)
        self.min_anteil = float(min_anteil)
        self.kacheln = kacheln
        self.ruhe = ruhe
        self.max_warten = max_warten
        self.video_anteil = video_anteil
        self.video_dauer = video_dauer
        self._ref = None
        self._vorher = None
        self._n = 0
        self._seit: float | None = None       # seit wann weicht das Bild von der Referenz ab
        self._bewegt: float | None = None     # letzte Bewegung (zum vorigen Bild)
        self._video_seit: float | None = None
        self._video_gemeldet = False
        self._leer = 0
        self._maske = None                    # angesammelte Kacheln, die sich geaendert haben

    def zuruecksetzen(self) -> None:
        self._ref = self._vorher = None
        self._seit = self._bewegt = self._video_seit = None
        self._video_gemeldet = False
        self._maske = None

    def _probe(self, bild, versatz: int):
        s = self.schritt
        kanal = 1 if bild.ndim == 3 and bild.shape[2] >= 2 else None
        teil = bild[versatz::s, versatz::s, kanal] if kanal is not None else bild[versatz::s, versatz::s]
        return teil

    def _kachel_maske(self, geaendert):
        import numpy as np

        ky, kx = self.kacheln[1], self.kacheln[0]
        h, w = geaendert.shape
        hy, wx = max(1, h // ky), max(1, w // kx)
        teil = geaendert[:hy * ky, :wx * kx]
        if teil.size == 0:
            return np.zeros((ky, kx), dtype=bool)
        return teil.reshape(ky, hy, kx, wx).any(axis=(1, 3))

    def vergleiche(self, bild, jetzt: float) -> Aenderung | None:
        """Neues Bild (numpy-Array HxWxC, uint8). Gibt eine fertige Aenderung zurueck oder None."""
        import numpy as np

        if self._ref is None or self._ref.shape != bild.shape:
            self._ref = bild
            self._vorher = bild
            self._seit = None
            self._maske = None
            return None
        versatz = self._n % self.schritt
        self._n += 1
        jetzt_probe = self._probe(bild, versatz).astype(np.int16)
        zur_ref = np.abs(jetzt_probe - self._probe(self._ref, versatz).astype(np.int16)) > self.schwelle
        zum_vorher = np.abs(jetzt_probe - self._probe(self._vorher, versatz).astype(np.int16)) > self.schwelle
        self._vorher = bild
        anteil_ref = float(zur_ref.mean()) if zur_ref.size else 0.0
        anteil_bewegung = float(zum_vorher.mean()) if zum_vorher.size else 0.0

        # Video/Spiel: lange viel Bewegung -> einmal melden, dann Referenz nachfuehren
        if anteil_bewegung >= self.video_anteil:
            self._video_seit = self._video_seit if self._video_seit is not None else jetzt
            if not self._video_gemeldet and jetzt - self._video_seit >= self.video_dauer:
                self._video_gemeldet = True
                self._ref = bild
                self._seit = None
                self._maske = None
                h, w = bild.shape[:2]
                return Aenderung("video", anteil_bewegung, (0, 0, w, h), unruhig=True)
        elif anteil_bewegung < self.min_anteil:
            if self._video_gemeldet:
                self._video_gemeldet = False
                self._ref = bild  # Video vorbei: neuer ruhiger Stand, keine Meldung
                self._seit = None
                self._maske = None
                self._video_seit = None
                return None
            self._video_seit = None
        if self._video_gemeldet:
            self._ref = bild
            return None

        if anteil_bewegung >= self.min_anteil:
            self._bewegt = jetzt
        if anteil_ref < self.min_anteil:
            # erst nach einer ganzen Runde Versaetze ohne Abweichung gilt es als "weg"
            self._leer += 1
            if self._leer >= self.schritt:
                self._seit = None
                self._maske = None
            return None
        self._leer = 0
        maske = self._kachel_maske(zur_ref)
        self._maske = maske if self._maske is None else (self._maske | maske)
        if self._seit is None:
            self._seit = jetzt
        ruhig = self._bewegt is None or jetzt - self._bewegt >= self.ruhe
        zu_lange = jetzt - self._seit >= self.max_warten
        if not (ruhig or zu_lange):
            return None
        bereich = self._bereich(self._maske, bild.shape)
        self._ref = bild
        self._seit = None
        self._maske = None
        return Aenderung("inhalt", anteil_ref, bereich, unruhig=not ruhig)

    def _bereich(self, maske, form) -> tuple[int, int, int, int]:
        import numpy as np

        h, w = form[:2]
        ky, kx = maske.shape
        zeilen = np.where(maske.any(axis=1))[0]
        spalten = np.where(maske.any(axis=0))[0]
        if not len(zeilen) or not len(spalten):
            return (0, 0, w, h)
        kh, kw = h / ky, w / kx
        x0, x1 = int(spalten[0] * kw), int(min(w, (spalten[-1] + 1) * kw))
        y0, y1 = int(zeilen[0] * kh), int(min(h, (zeilen[-1] + 1) * kh))
        return (x0, y0, max(1, x1 - x0), max(1, y1 - y0))
