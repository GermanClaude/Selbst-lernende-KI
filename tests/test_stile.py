"""0.53: Stile (Cockpit/Neon/Einfach/Klassisch), Status-Deck und Live-Systemwerte."""
import re
from pathlib import Path

from assistant import systemstatus as S

STATIC = Path(__file__).resolve().parent.parent / "assistant" / "app" / "static"


def test_systemwerte_sind_plausibel():
    m = S.messen()
    assert set(m) >= {"cpu", "ram", "ram_gb", "akku", "laufzeit_h", "kerne"}
    for k in ("cpu", "ram"):
        assert m[k] is None or 0 <= m[k] <= 100


def test_systemwerte_zwischengespeichert():
    a = S.messen(jetzt=1000.0)
    b = S.messen(jetzt=1000.5)
    assert a == b


def test_alle_stile_haben_css_und_eine_wahl():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    stile = re.search(r"const STILE = \[([^\]]+)\]", js).group(1)
    for stil in ("cockpit", "neon", "einfach", "klassisch"):
        assert f"'{stil}'" in stile
        assert f'data-wahl="{stil}"' in html
        if stil != "klassisch":
            assert f'[data-stil="{stil}"]' in css


def test_neon_setzt_alle_dunklen_farben():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    block = css.split(':root[data-stil="neon"] {', 1)[1].split("}", 1)[0]
    for var in ("--bg", "--surface", "--text", "--accent", "--danger-soft", "--warn-soft", "--code-bg", "--input-bg"):
        assert var + ":" in block, var
