"""Bilder vom Spielfenster: aufnehmen, Raster einzeichnen, vergleichen.

Aufgenommen wird nur der Innenbereich des Spielfensters (nie der ganze Bildschirm) - mit mss,
sonst Pillow (ImageGrab). Das Bild fuer die KI wird EINMAL vorbereitet (assistant.bilder) und
danach nie mehr veraendert. Optional kommt vorher ein duennes Koordinaten-Raster hinein (0,1-Schritte
mit Beschriftung), damit die KI Positionen (0..1) besser treffen kann.
"""
from __future__ import annotations

import io

from ..bilder import Bild, BildFehler, vorbereiten


class AufnahmeFehler(RuntimeError):
    """Kein Bild vom Spielfenster (Text fuer den Menschen)."""


def aufnehmen(rechteck: tuple[int, int, int, int]) -> bytes:  # pragma: no cover - echter Bildschirm
    """PNG des Bereichs (x, y, b, h) in Bildschirm-Pixeln."""
    x, y, b, h = (int(v) for v in rechteck)
    if b <= 0 or h <= 0:
        raise AufnahmeFehler("Das Spielfenster hat keine Größe (minimiert?).")
    fehler = ""
    try:
        import mss
        import mss.tools

        with mss.mss() as m:
            shot = m.grab({"left": x, "top": y, "width": b, "height": h})
            return mss.tools.to_png(shot.rgb, shot.size)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        fehler = f"{type(exc).__name__}"
    try:
        from PIL import ImageGrab

        bild = ImageGrab.grab(bbox=(x, y, x + b, y + h), all_screens=True)
        puffer = io.BytesIO()
        bild.save(puffer, "PNG")
        return puffer.getvalue()
    except Exception as exc:  # noqa: BLE001
        fehler = fehler or type(exc).__name__
    raise AufnahmeFehler("Ich konnte kein Bild vom Spielfenster machen"
                         + (f" ({fehler})" if fehler else "") + ". Ist der Bildschirm gesperrt? Tipp: im Spiel "
                         "„Randloses Vollbild“ (Borderless) einstellen.")


def _pillow():
    try:
        from PIL import Image, ImageDraw

        return Image, ImageDraw
    except Exception:  # noqa: BLE001
        return None, None


def mit_raster(png: bytes) -> bytes:
    """Duennes Raster in 0,1-Schritten mit Beschriftung am Rand (gibt bei Problemen das Original zurueck)."""
    Image, ImageDraw = _pillow()
    if Image is None:
        return png
    try:
        bild = Image.open(io.BytesIO(png)).convert("RGBA")
        breite, hoehe = bild.size
        ebene = Image.new("RGBA", bild.size, (0, 0, 0, 0))
        stift = ImageDraw.Draw(ebene)
        dicke = max(1, round(min(breite, hoehe) / 900))
        for i in range(1, 10):
            x, y = round(breite * i / 10), round(hoehe * i / 10)
            stift.line([(x, 0), (x, hoehe)], fill=(255, 255, 0, 70), width=dicke)
            stift.line([(0, y), (breite, y)], fill=(255, 255, 0, 70), width=dicke)
            beschriftung = f"0.{i}"
            for px, py in ((x + 3, 2), (2, y + 2)):
                stift.rectangle([px - 1, py - 1, px + 22, py + 11], fill=(0, 0, 0, 120))
                stift.text((px, py), beschriftung, fill=(255, 255, 0, 220))
        bild = Image.alpha_composite(bild, ebene).convert("RGB")
        puffer = io.BytesIO()
        bild.save(puffer, "PNG")
        return puffer.getvalue()
    except Exception:  # noqa: BLE001
        return png


def fuer_ki(png: bytes, name: str, max_kante: int, raster: bool = True) -> Bild:
    """Einmal vorbereitet (verkleinert) - so geht es an die KI. Wirft BildFehler."""
    return vorbereiten(mit_raster(png) if raster else png, name, max_kante=max(256, min(int(max_kante or 1280), 2000)))


def fingerabdruck(png: bytes) -> tuple[int, ...] | None:
    """Winziges Graustufenbild (32x18) zum Vergleichen - None ohne Pillow."""
    Image, _ = _pillow()
    if Image is None:
        return None
    try:
        klein = Image.open(io.BytesIO(png)).convert("L").resize((32, 18))
        return tuple(klein.tobytes())
    except Exception:  # noqa: BLE001
        return None


def unterschied(a, b) -> float:
    """Mittlere Helligkeits-Abweichung 0..255 (ohne Fingerabdruck: 0 bei gleichen Bytes, sonst 255)."""
    if a is None or b is None:
        return 255.0
    if isinstance(a, (bytes, bytearray)) or isinstance(b, (bytes, bytearray)):
        return 0.0 if a == b else 255.0
    if len(a) != len(b) or not a:
        return 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def fast_schwarz(fingerabdruck_: tuple[int, ...] | None) -> bool:
    """Ganz schwarzes Bild = Aufnahme klappt nicht (exklusives Vollbild, gesperrter Bildschirm)."""
    return bool(fingerabdruck_) and max(fingerabdruck_) < 8


def groesse(png: bytes) -> tuple[int, int] | None:
    Image, _ = _pillow()
    if Image is not None:
        try:
            return Image.open(io.BytesIO(png)).size
        except Exception:  # noqa: BLE001
            return None
    if png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) >= 24:
        return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    return None


def als_bericht_bild(png: bytes, name: str) -> Bild | None:
    """Kleiner fuer den Bericht (ohne Raster)."""
    try:
        return vorbereiten(png, name, max_kante=1280)
    except BildFehler:
        return None
