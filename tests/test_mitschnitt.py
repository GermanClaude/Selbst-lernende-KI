"""Mitschnitt/Transkription - die reine Logik (ohne echtes Audio/Whisper)."""
from assistant import mitschnitt as mit
from assistant.mitschnitt import Mitschnitt, Segment
from assistant.tools import ToolContext, build_registry
from assistant.permissions import PermissionManager
from assistant.config import PermissionSettings


def test_geschlecht_aus_tonhoehe():
    assert mit.geschlecht_aus_tonhoehe(120) == "m"
    assert mit.geschlecht_aus_tonhoehe(210) == "w"
    assert mit.geschlecht_aus_tonhoehe(165) == ""   # Graubereich -> nichts behaupten
    assert mit.geschlecht_aus_tonhoehe(0) == ""


def test_sprecher_name_und_zeile():
    seg = Segment(start=83, ende=85, text="Hallo zusammen", sprecher="Sprecher 1", geschlecht="w")
    assert mit.sprecher_name("Sprecher 1", {"Sprecher 1": "Aria"}) == "Aria"
    zeile = mit.transkript_zeile(seg, {"Sprecher 1": "Aria"})
    assert zeile == "[00:01:23] Aria (weiblich?): Hallo zusammen"


def test_transkript_text_mit_mehreren_sprechern():
    segs = [Segment(0, 1, "Hi", "Sprecher 1"), Segment(2, 3, "Na du", "Sprecher 2")]
    text = mit.transkript_text(segs, {"Sprecher 1": "Aria", "Sprecher 2": "Tim"}, titel="Test")
    assert "# Test" in text and "Aria: Hi" in text and "Tim: Na du" in text
    assert "Sprecher: Aria, Tim" in text  # Fussnote listet die Sprecher


def test_zusammenfassung_prompt_kuerzt():
    kurz = mit.zusammenfassung_prompt("A: hallo\nB: hi")
    assert "hallo" in kurz and "zusammen" in kurz.lower()
    lang = mit.zusammenfassung_prompt("x" * 100_000, grenze=1000)
    assert "(gekuerzt)" in lang and len(lang) < 3000


def test_f0_ohne_numpy_oder_leer():
    assert mit._f0_schaetzen(b"") == 0.0  # zu kurz/kein numpy -> 0


def test_mische_system_und_mikrofon():
    from array import array
    a = array("h", [100, -100, 32767, 0]).tobytes()
    b = array("h", [50, -50, 100, -32768]).tobytes()
    out = array("h")
    out.frombytes(mit._mische(a, b))
    assert list(out) == [150, -150, 32767, -32768]  # addiert, auf int16 begrenzt


def test_mische_ungleiche_laenge_haengt_rest_an():
    from array import array
    a = array("h", [10, 20, 30]).tobytes()
    b = array("h", [1, 2]).tobytes()
    out = array("h")
    out.frombytes(mit._mische(a, b))
    assert list(out) == [11, 22, 30]  # erste zwei gemischt, Rest (30) angehaengt


def test_mitschnitt_ohne_pakete_meldet_setup(tmp_path):
    m = Mitschnitt(tmp_path / "mit")
    # In der Testumgebung sind sounddevice/faster-whisper nicht da -> freundlicher Hinweis.
    assert m.problem() is not None
    r = m.start("system")
    assert r["ok"] is False and r.get("setup") is True


def test_benennen_und_neu_schreiben(tmp_path):
    m = Mitschnitt(tmp_path / "mit")
    m.segmente = [Segment(0, 1, "Hallo", "Sprecher 1")]
    m.status.datei = str(tmp_path / "t.md")
    m.status.quelle = "system"
    m.benenne("1", "Aria")   # "1" -> "Sprecher 1"
    assert m.namen["Sprecher 1"] == "Aria"
    assert "Aria: Hallo" in (tmp_path / "t.md").read_text(encoding="utf-8")


def test_werkzeug_transkription_registriert_und_status(tmp_path):
    reg = build_registry()
    assert any(getattr(t, "name", "") == "transkription" for t in reg._tools.values())
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=True), tmp_path,
                           confirm_fn=lambda m, r: True)
    zustand = {"laeuft": True, "quelle": "system", "minuten": 3, "segmente": 5, "datei": "x.md"}
    ctx = ToolContext(permissions=pm, extra={"mitschnitt_start": lambda q: {"ok": True, "quelle": q, "datei": "x.md"},
                                             "mitschnitt_stop": lambda: {"ok": True, "segmente": 5, "minuten": 3, "datei": "x.md"},
                                             "mitschnitt_status": lambda: zustand})
    out, err = reg.execute(ctx, "transkription", {"aktion": "status"})
    assert not err and "laeuft" in out.lower()
    out2, _ = reg.execute(ctx, "transkription", {"aktion": "start", "quelle": "system"})
    assert "system" in out2
