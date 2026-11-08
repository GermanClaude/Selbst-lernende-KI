import base64
import io

import pytest

from assistant import bilder
from assistant.bilder import BildFehler

PIL = pytest.importorskip("PIL.Image")


def _png(w, h, mode="RGB", color=(200, 30, 30)):
    buf = io.BytesIO()
    PIL.new(mode, (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def _jpg(w, h, orientation=None):
    img = PIL.new("RGB", (w, h), (10, 120, 200))
    buf = io.BytesIO()
    if orientation:
        exif = img.getexif()
        exif[0x0112] = orientation
        img.save(buf, "JPEG", exif=exif)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def test_type_comes_from_the_bytes_not_the_name():
    assert bilder.erkenne_typ(_png(4, 4)) == "image/png"
    assert bilder.erkenne_typ(_jpg(4, 4)) == "image/jpeg"
    assert bilder.erkenne_typ(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    with pytest.raises(BildFehler, match="kein Bild"):
        bilder.vorbereiten(b"<svg/>", "bild.png")


def test_small_images_stay_byte_identical():
    raw = _png(40, 30)
    b = bilder.vorbereiten(raw, "C:\\Users\\x\\Bildschirm foto?.png")
    assert b.data == raw and b.mime == "image/png" and (b.breite, b.hoehe) == (40, 30)
    assert b.name == "Bildschirm foto.png"  # kein Pfad, keine Sonderzeichen
    assert "\n" not in b.b64() and b.data_url().startswith("data:image/png;base64,")


def test_large_images_are_shrunk_once():
    b = bilder.vorbereiten(_jpg(4000, 3000), "foto.jpg", max_kante=1568)
    assert max(b.breite, b.hoehe) == 1568 and b.mime == "image/jpeg"
    again = bilder.vorbereiten(b.data, b.name, max_kante=1568)
    assert again.data == b.data  # zweites Mal: unveraendert (wichtig fuer Claudes Verlauf)


def test_phone_photos_are_turned_upright():
    b = bilder.vorbereiten(_jpg(60, 40, orientation=6), "handy.jpg")
    assert (b.breite, b.hoehe) == (40, 60)


def test_transparent_png_stays_png_and_gif_becomes_still_image():
    b = bilder.vorbereiten(_png(3000, 100, mode="RGBA", color=(0, 0, 0, 0)), "logo.png", 800)
    assert b.mime == "image/png" and b.breite == 800
    buf = io.BytesIO()
    frames = [PIL.new("RGB", (20, 20), c) for c in ((255, 0, 0), (0, 255, 0))]
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:])
    g = bilder.vorbereiten(buf.getvalue(), "anim.gif")
    assert g.mime in ("image/png", "image/jpeg") and g.name.endswith((".png", ".jpg"))


def test_data_urls_from_the_app():
    raw = _png(10, 10)
    url = "data:image/png;base64," + base64.b64encode(raw).decode()
    assert bilder.aus_data_url(url, "a.png").data == raw
    # Angabe "png", Inhalt aber kein Bild -> abgelehnt
    with pytest.raises(BildFehler):
        bilder.aus_data_url("data:image/png;base64," + base64.b64encode(b"hallo").decode())
    with pytest.raises(BildFehler, match="nicht richtig"):
        bilder.aus_data_url("https://example.com/x.png")


def test_broken_and_empty_images_get_friendly_errors():
    with pytest.raises(BildFehler, match="leer"):
        bilder.vorbereiten(b"")
    with pytest.raises(BildFehler, match="besch\u00e4digt"):
        bilder.vorbereiten(b"\x89PNG\r\n\x1a\n" + b"kaputt" * 10)


def test_without_pillow_only_checks(monkeypatch):
    monkeypatch.setattr(bilder, "_pillow", lambda: (None, None))
    raw = _png(5000, 10)
    assert bilder.vorbereiten(raw, "x.png").data == raw
    monkeypatch.setattr(bilder, "MAX_AUSGANG", 10)
    with pytest.raises(BildFehler, match="zu gro\u00df"):
        bilder.vorbereiten(raw, "x.png")


def test_files_and_placeholders(tmp_path):
    p = tmp_path / "foto.png"
    p.write_bytes(_png(8, 8))
    b = bilder.aus_datei(f'"{p}"')  # Windows: hineingezogener Pfad kommt in Anfuehrungszeichen
    assert b.platzhalter() == "[Bild: foto.png]"
    assert bilder.platzhalter_text([b, b]) == "[Bild: foto.png] [Bild: foto.png]"
    saved = b.speichern(tmp_path / "ablage", "abc")
    assert saved.name == "abc.png" and saved.read_bytes() == b.data
    with pytest.raises(BildFehler, match="nicht gefunden"):
        bilder.aus_datei(tmp_path / "fehlt.png")


def test_decompression_bombs_are_refused_before_unpacking(monkeypatch):
    monkeypatch.setattr(bilder, "MAX_PIXEL", 100 * 100)
    with pytest.raises(BildFehler, match="Pixel"):
        bilder.vorbereiten(_png(200, 200), "bombe.png")
    assert bilder.vorbereiten(_png(90, 90), "ok.png").breite == 90


def test_base64_size_stays_under_claudes_limit():
    import os

    rauschen = PIL.frombytes("RGBA", (1400, 1100), os.urandom(1400 * 1100 * 4))  # nicht komprimierbar
    buf = io.BytesIO()
    rauschen.save(buf, "PNG")
    assert len(buf.getvalue()) > bilder.MAX_AUSGANG
    b = bilder.vorbereiten(buf.getvalue(), "gross.png")
    assert len(b.b64()) <= 5 * 1024 * 1024
