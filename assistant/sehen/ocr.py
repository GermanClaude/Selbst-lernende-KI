"""Texterkennung mit der eingebauten Windows-Texterkennung (Windows.Media.Ocr ueber winrt).

Nur fuer Bereiche, die sich geaendert haben und zur Ruhe gekommen sind - nie fuer Passwortfelder
oder ausgeschlossene Fenster. Fehlt die deutsche Texterkennung, nimmt Nova die Sprachen deines
Windows-Profils und sagt dir, wie du Deutsch nachinstallierst.
"""
from __future__ import annotations

import asyncio

DEUTSCH_FEHLT = ("Die deutsche Texterkennung von Windows fehlt. Nachinstallieren: Einstellungen \u2192 Zeit und "
                 "Sprache \u2192 Sprache \u2192 Deutsch \u2192 Sprachoptionen \u2192 "
                 "\u201eOptische Zeichenerkennung\u201c "
                 "(oder als Administrator: Add-WindowsCapability -Online -Name Language.OCR~~~de-DE~0.0.1.0).")


class WindowsOcr:
    def __init__(self):
        self._engine = None
        self._max = 2000
        self.hinweis = ""
        self.fehler = ""

    def start(self, sprache: str = "de-DE") -> bool:
        try:
            from winrt.windows.globalization import Language  # noqa: PLC0415
            from winrt.windows.media.ocr import OcrEngine  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            self.fehler = f"Windows-Texterkennung nicht verf\u00fcgbar ({type(exc).__name__})."
            return False
        try:
            engine = None
            try:
                sprache_obj = Language(sprache)
                if OcrEngine.is_language_supported(sprache_obj):
                    engine = OcrEngine.try_create_from_language(sprache_obj)
            except Exception:  # noqa: BLE001
                engine = None
            if engine is None:
                engine = OcrEngine.try_create_from_user_profile_languages()
                if sprache.lower().startswith("de"):
                    self.hinweis = DEUTSCH_FEHLT
            if engine is None:
                self.fehler = "Keine Sprache f\u00fcr die Windows-Texterkennung installiert."
                return False
            try:
                self._max = int(OcrEngine.max_image_dimension) or 2000
            except Exception:  # noqa: BLE001
                self._max = 2000
            self._engine = engine
            return True
        except Exception as exc:  # noqa: BLE001
            self.fehler = f"Windows-Texterkennung ging nicht ({type(exc).__name__})."
            return False

    @property
    def bereit(self) -> bool:
        return self._engine is not None

    def erkenne(self, bgra) -> str:
        """Ausschnitt (numpy H x W x 4, BGRA) -> erkannter Text ('' bei Problemen)."""
        if self._engine is None:
            return ""
        try:
            import numpy as np  # noqa: PLC0415
            from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap  # noqa: PLC0415

            h, w = bgra.shape[:2]
            schritt = 1
            while max(h, w) // schritt > self._max:
                schritt += 1
            if schritt > 1:
                bgra = bgra[::schritt, ::schritt]
            if min(bgra.shape[:2]) < 8:
                return ""
            daten = np.ascontiguousarray(bgra[..., :4], dtype=np.uint8)
            h, w = daten.shape[:2]
            try:
                bitmap = SoftwareBitmap.create_copy_from_buffer(memoryview(daten).cast("B"),
                                                                BitmapPixelFormat.BGRA8, w, h)
            except TypeError:
                from winrt.windows.storage.streams import DataWriter  # noqa: PLC0415

                schreiber = DataWriter()
                schreiber.write_bytes(daten.tobytes())
                bitmap = SoftwareBitmap.create_copy_from_buffer(schreiber.detach_buffer(),
                                                                BitmapPixelFormat.BGRA8, w, h)

            async def lesen():
                return await self._engine.recognize_async(bitmap)

            ergebnis = asyncio.run(lesen())
            zeilen = [str(z.text) for z in ergebnis.lines]
            return "\n".join(z for z in zeilen if z.strip())
        except Exception as exc:  # noqa: BLE001 - lieber kein Text als ein Absturz
            self.fehler = f"Texterkennung: {type(exc).__name__}"
            return ""


class FakeOcr:
    """Fuer Tests: liefert festen Text und merkt sich, wie oft gelesen wurde."""

    def __init__(self, text: str = ""):
        self.text = text
        self.aufrufe = 0
        self.hinweis = ""
        self.fehler = ""

    def start(self, sprache: str = "de-DE") -> bool:
        return True

    bereit = True

    def erkenne(self, bgra) -> str:
        self.aufrufe += 1
        return self.text
