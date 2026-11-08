"""QR-Code fuer die Handy-Kamera: als SVG (App-Fenster) oder Text (Terminal).

segno wird erst hier geladen. Fehlt es, gibt es keinen QR-Code, aber den Link und den Kurzcode -
die Oberflaeche zeigt dann einen Hinweis (z.B. Link am Handy abtippen oder Code eingeben).
"""
from __future__ import annotations

import io
import logging

log = logging.getLogger(__name__)

OHNE_SEGNO = ("QR-Code nicht m\u00f6glich (Paket 'segno' fehlt: pip install segno). "
              "\u00d6ffne den Link am Handy oder gib dort den Code ein.")


def _segno():
    try:
        import segno  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    return segno


def qr_svg(text: str, *, skala: int = 6, rand: int = 3, dunkel: str = "#111111", hell: str = "#ffffff",
           titel: str = "QR-Code f\u00fcr die Nova-Kamera") -> str | None:
    """SVG-Text (ohne XML-Kopf, zum direkten Einbetten) oder None, wenn segno fehlt."""
    segno = _segno()
    if segno is None:
        return None
    try:
        code = segno.make(text, error="m", micro=False)
        return code.svg_inline(scale=skala, border=rand, dark=dunkel, light=hell, title=titel,
                               svgclass="nova-qr", lineclass=None)
    except Exception as exc:  # noqa: BLE001
        log.info("QR-Code nicht erzeugt (%s)", type(exc).__name__)
        return None


def qr_text(text: str) -> str | None:
    """QR-Code aus Blockzeichen fuers Terminal (halbe Zeilen) oder None, wenn segno fehlt."""
    segno = _segno()
    if segno is None:
        return None
    try:
        puffer = io.StringIO()
        segno.make(text, error="m", micro=False).terminal(out=puffer, compact=True, border=2)
        return puffer.getvalue()
    except Exception as exc:  # noqa: BLE001
        log.info("QR-Text nicht erzeugt (%s)", type(exc).__name__)
        return None


def qr_daten(link: str, code: str | None = None) -> dict:
    """Alles fuer die Anzeige: {"link", "code", "svg" (oder None), "hinweis"}."""
    svg = qr_svg(link)
    if svg is not None:
        hinweis = "Scanne den Code mit der Kamera deines Handys (Handy und PC im selben WLAN)."
    else:
        hinweis = OHNE_SEGNO
    return {"link": link, "code": code, "svg": svg, "hinweis": hinweis}
