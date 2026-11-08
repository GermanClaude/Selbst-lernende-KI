"""Bilder fuer den Chat, das Feedback und den Bildgenerator.

Ein gemeinsamer Weg fuer alle Bilder, die Nova bekommt (eingefuegt, hineingezogen, als Datei
oder als Bildschirmfoto): Typ an den Bytes erkennen, auf eine vernuenftige Groesse verkleinern
und als `Bild` weitergeben. Ohne Pillow geht es auch - dann wird nur geprueft, nicht verkleinert.

Wichtig fuer Claude: ein Bild wird EINMAL beim Ankommen verkleinert und danach nie mehr
veraendert (sonst gilt der Verlauf als "bearbeitet" und Claude lehnt ab).
"""
from __future__ import annotations

import base64
import binascii
import io
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

ERLAUBT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
MAX_EINGANG = 25 * 1024 * 1024      # so gross darf ein Bild hoechstens ankommen
MAX_AUSGANG = 5 * 1024 * 1024       # so gross darf es nach dem Verkleinern hoechstens sein
MAX_PIXEL = 40_000_000            # mehr Pixel = Verdacht auf "Bild-Bombe"
MAX_SEITE = 3000                    # keine Seite laenger (Claude: strengere Grenze ab 20 Bildern)
STANDARD_KANTE = 1568
_NAME_OK = re.compile(r"[^A-Za-z0-9._ \-]+")


class BildFehler(ValueError):
    """Bild ist kaputt, zu gross oder kein unterstuetztes Format (Text fuer den Nutzer)."""


@dataclass(frozen=True)
class Bild:
    name: str
    mime: str
    data: bytes
    breite: int | None = None
    hoehe: int | None = None

    @property
    def endung(self) -> str:
        return ERLAUBT.get(self.mime, "bin")

    def b64(self) -> str:
        """Base64 ohne Zeilenumbrueche (so wollen es die APIs)."""
        return base64.b64encode(self.data).decode("ascii")

    def data_url(self) -> str:
        return f"data:{self.mime};base64,{self.b64()}"

    def platzhalter(self) -> str:
        """Kurzer Text statt des Bildes (Zusammenfassungen, Modelle ohne Augen, Verlauf)."""
        return f"[Bild: {self.name}]" if self.name else "[Bild]"

    def speichern(self, ordner: Path, stamm: str | None = None) -> Path:
        """Legt das Bild als Datei ab (Name: zufaellig oder `stamm`); gibt den Pfad zurueck."""
        ordner = Path(ordner)
        ordner.mkdir(parents=True, exist_ok=True)
        stamm = stamm or f"{time.strftime('%Y%m%d-%H%M%S')}_{secrets.token_hex(4)}"
        ziel = ordner / f"{stamm}.{self.endung}"
        ziel.write_bytes(self.data)
        return ziel


def erkenne_typ(data: bytes) -> str | None:
    """MIME-Typ an den ersten Bytes erkennen (nicht an Dateiname oder Angabe des Absenders)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def sauberer_name(name: str | None, mime: str) -> str:
    """Dateiname ohne Pfad und Sonderzeichen, mit passender Endung."""
    roh = re.split(r"[\\/]", str(name or ""))[-1]  # Windows- und Linux-Pfade
    stamm = _NAME_OK.sub("_", roh.rsplit(".", 1)[0] if "." in roh else roh).strip(" ._")[:60]
    return f"{stamm or 'bild'}.{ERLAUBT.get(mime, 'bin')}"


def _pillow():
    try:
        from PIL import Image, ImageOps  # noqa: F401
        return Image, ImageOps
    except Exception:  # noqa: BLE001 - Pillow ist fuer Quellcode-Nutzer optional
        return None, None


def vorbereiten(data: bytes, name: str | None = None, max_kante: int = STANDARD_KANTE) -> Bild:
    """Pruefen und (mit Pillow) verkleinern: laengste Seite <= max_kante, GIF -> erstes Bild,
    Fotos als JPEG, Bildschirmfotos/Grafiken als PNG (wenn das kleiner ist). Wirft BildFehler."""
    if not data:
        raise BildFehler("Das Bild ist leer.")
    if len(data) > MAX_EINGANG:
        raise BildFehler("Das Bild ist zu gro\u00df (h\u00f6chstens 25 MB).")
    mime = erkenne_typ(data)
    if mime is None:
        raise BildFehler("Das ist kein Bild, das ich lesen kann (erlaubt: PNG, JPEG, GIF, WebP).")
    max_kante = max(64, min(int(max_kante or STANDARD_KANTE), MAX_SEITE))
    Image, ImageOps = _pillow()
    if Image is None:
        if len(data) > MAX_AUSGANG:
            raise BildFehler("Das Bild ist zu gro\u00df (h\u00f6chstens 5 MB). Tipp: kleiner speichern "
                             "oder einen Ausschnitt nehmen.")
        return Bild(sauberer_name(name, mime), mime, data)
    try:
        bild = Image.open(io.BytesIO(data), formats=["PNG", "JPEG", "GIF", "WEBP"])
    except Exception as exc:  # noqa: BLE001 - kaputte Datei
        raise BildFehler("Das Bild ist besch\u00e4digt und l\u00e4sst sich nicht \u00f6ffnen.") from exc
    # Vor dem Entpacken: winzige Datei, riesiges Bild ("Bild-Bombe") sonst Gigabytes im Speicher.
    if bild.size[0] * bild.size[1] > MAX_PIXEL:
        raise BildFehler("Das Bild hat zu viele Pixel (h\u00f6chstens 40 Megapixel).")
    try:
        bild.seek(0)  # GIF: nur das erste Bild
        bild.load()
    except Exception as exc:  # noqa: BLE001 - kaputte Datei
        raise BildFehler("Das Bild ist besch\u00e4digt und l\u00e4sst sich nicht \u00f6ffnen.") from exc
    gedreht = False
    try:
        gedreht = bild.getexif().get(0x0112, 1) not in (0, 1)
        if gedreht:
            bild = ImageOps.exif_transpose(bild)  # Handyfotos richtig herum (KI liest kein EXIF)
    except Exception:  # noqa: BLE001
        gedreht = False
    breite, hoehe = bild.size
    if breite < 1 or hoehe < 1:
        raise BildFehler("Das Bild ist leer.")
    faktor = min(1.0, max_kante / max(breite, hoehe))
    veraendert = (faktor < 1.0 or gedreht or mime in ("image/gif", "image/webp")
                  or len(data) > MAX_AUSGANG)
    if not veraendert and mime in ("image/png", "image/jpeg"):
        return Bild(sauberer_name(name, mime), mime, data, breite, hoehe)
    if faktor < 1.0:
        bild = bild.resize((max(1, round(breite * faktor)), max(1, round(hoehe * faktor))), Image.LANCZOS)
    neu_mime, neu = _kodieren(bild, Image, bevorzugt=mime)
    if len(neu) > MAX_AUSGANG:
        raise BildFehler("Das Bild ist auch verkleinert noch zu gro\u00df.")
    return Bild(sauberer_name(name, neu_mime), neu_mime, neu, bild.size[0], bild.size[1])


def _kodieren(bild, Image, bevorzugt: str) -> tuple[str, bytes]:
    hat_alpha = bild.mode in ("RGBA", "LA") or (bild.mode == "P" and "transparency" in bild.info)
    png = io.BytesIO()
    (bild if bild.mode in ("RGB", "RGBA", "L", "LA", "P") else bild.convert("RGBA")).save(png, "PNG", optimize=True)
    if hat_alpha:
        return "image/png", png.getvalue()
    jpg = io.BytesIO()
    bild.convert("RGB").save(jpg, "JPEG", quality=85, optimize=True)
    # Bildschirmfotos (wenige Farben, scharfe Kanten) bleiben als PNG oft kleiner und lesbarer.
    if bevorzugt == "image/png" and len(png.getvalue()) <= len(jpg.getvalue()) * 1.5:
        return "image/png", png.getvalue()
    return "image/jpeg", jpg.getvalue()


_DATA_URL = re.compile(r"^data:(image/[a-z0-9.+-]+)?(;[a-z0-9=.+-]+)*;base64,", re.I)


def aus_data_url(url: str, name: str | None = None, max_kante: int = STANDARD_KANTE) -> Bild:
    """'data:image/...;base64,...' (aus der App) -> Bild. Der Typ wird an den Bytes geprueft."""
    text = str(url or "").strip()
    treffer = _DATA_URL.match(text)
    if not treffer:
        raise BildFehler("Das Bild kam nicht richtig an (kein Bildinhalt).")
    if len(text) > MAX_EINGANG * 4 // 3 + 200:
        raise BildFehler("Das Bild ist zu gro\u00df (h\u00f6chstens 25 MB).")
    try:
        data = base64.b64decode(text[treffer.end():], validate=False)
    except (binascii.Error, ValueError) as exc:
        raise BildFehler("Das Bild kam nicht richtig an (fehlerhafte Daten).") from exc
    return vorbereiten(data, name, max_kante)


def aus_datei(pfad: Path | str, max_kante: int = STANDARD_KANTE) -> Bild:
    """Bilddatei (z.B. /bild C:\\Bilder\\foto.jpg im Terminal) -> Bild."""
    pfad = Path(str(pfad).strip().strip('"').strip("'")).expanduser()
    if not pfad.is_file():
        raise BildFehler(f"Datei nicht gefunden: {pfad}")
    if pfad.stat().st_size > MAX_EINGANG:
        raise BildFehler("Das Bild ist zu gro\u00df (h\u00f6chstens 25 MB).")
    return vorbereiten(pfad.read_bytes(), pfad.name, max_kante)


def platzhalter_text(bilder: list[Bild] | tuple[Bild, ...] | None) -> str:
    """'[Bild: a.png] [Bild: b.jpg]' - fuer Zusammenfassungen und Modelle ohne Augen."""
    return " ".join(b.platzhalter() for b in (bilder or []))
