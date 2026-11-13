"""Bewertungen: oeffentliche Rezensionen, Sterne-Durchschnitt (App) und README-Abschnitt (Repo)."""
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

from assistant import feedback
from assistant.config import load_config

URL = "https://script.google.com/macros/s/AKfycbTestTestTest123/exec"
WURZEL = Path(__file__).resolve().parent.parent


def _cfg(tmp_path):
    cfg = load_config(tmp_path)
    cfg.feedback.adresse = URL
    return cfg


def _repo_skript():
    spec = importlib.util.spec_from_file_location("bewertungen_skript", WURZEL / "packaging" / "bewertungen.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


ANTWORT = {"ok": True, "anzahl": 3, "schnitt": 4.333, "verteilung": {"5": 2, "3": 1},
           "oeffentlich": [{"sterne": 5, "name": "Alex", "text": "Super KI!", "datum": "2026-11-12", "version": "0.14.0"},
                           {"sterne": 9, "name": "Kaputt", "text": "x"},
                           {"sterne": 3, "name": "", "text": "  ", "datum": "gestern"},
                           {"sterne": 3, "name": "N" * 99, "text": "T" * 900, "datum": "<b>"}]}


def test_payload_oeffentlich_nur_mit_sternen(tmp_path):
    cfg = _cfg(tmp_path)
    p = feedback.baue_payload("bewertung", 5, "Toll", None, None, "menue", cfg, oeffentlich=True, name="  Alex  B. ")
    assert p["public"] is True and p["name"] == "Alex B." and p["v"] == 2
    assert len(p["install"]) >= 16 and p["install"] == feedback.kennung(cfg)  # bleibt gleich
    p = feedback.baue_payload("idee", None, "Idee ohne Sterne", None, None, "menue", cfg, oeffentlich=True, name="X")
    assert p["public"] is False and p["name"] == ""
    p = feedback.baue_payload("bewertung", 4, "privat", None, None, "menue", cfg, name="Geheim")
    assert p["public"] is False and p["name"] == ""


def test_antwort_wird_gesaeubert():
    d = feedback.bewertungen_saeubern(ANTWORT)
    assert d["anzahl"] == 3 and d["schnitt"] == 4.3
    assert d["verteilung"] == {"1": 0, "2": 0, "3": 1, "4": 0, "5": 2}
    assert [r["name"] for r in d["oeffentlich"]] == ["Alex", "N" * 40]
    assert len(d["oeffentlich"][1]["text"]) == 600 and d["oeffentlich"][1]["datum"] == ""
    assert feedback.bewertungen_saeubern({"ok": False}) is None
    assert feedback.bewertungen_saeubern("kaputt") is None
    assert feedback.bewertungen_saeubern({"ok": True, "anzahl": 0, "schnitt": 9})["schnitt"] == 0.0
    assert feedback.sterne_text(4.3) == "★★★★☆"


def test_bewertungen_werden_eine_stunde_gemerkt(tmp_path):
    cfg = _cfg(tmp_path)
    aufrufe = []

    def holen(url):
        aufrufe.append(url)
        return json.dumps(ANTWORT).encode()

    jetzt = datetime(2026, 11, 13, 12, 0)
    d = feedback.bewertungen(cfg, holen=holen, jetzt=jetzt)
    assert d["schnitt"] == 4.3 and aufrufe == [URL + "?aktion=bewertungen"]
    feedback.bewertungen(cfg, holen=holen, jetzt=jetzt + timedelta(minutes=30))
    assert len(aufrufe) == 1  # aus dem Speicher
    # nach einer Stunde neu - klappt das nicht, bleibt der alte Stand
    def kaputt(url):
        aufrufe.append(url)
        raise OSError("offline")

    d = feedback.bewertungen(cfg, holen=kaputt, jetzt=jetzt + timedelta(minutes=61))
    assert len(aufrufe) == 2 and d["anzahl"] == 3


def test_ohne_postfach_keine_bewertungen(tmp_path):
    cfg = load_config(tmp_path)
    cfg.feedback.adresse = ""
    assert feedback.bewertungen(cfg, fetch=lambda url, timeout=0: b"", holen=lambda u: b"{}") is None


def test_neue_bewertung_leert_den_speicher(tmp_path):
    cfg = _cfg(tmp_path)
    feedback.bewertungen(cfg, holen=lambda u: json.dumps(ANTWORT).encode())
    assert "bewertungen" in json.loads((tmp_path / "data" / "feedback_state.json").read_text())

    class Antwort:
        status_code = 200
        text = '{"ok": true}'

    erg = feedback.abschicken(cfg, "bewertung", 5, "Top", oeffentlich=True, name="Kim",
                              post=lambda url, **kw: Antwort())
    assert erg.status == "gesendet"
    assert "bewertungen" not in json.loads((tmp_path / "data" / "feedback_state.json").read_text())


def test_readme_abschnitt_und_einsetzen():
    skript = _repo_skript()
    daten = feedback.bewertungen_saeubern({**ANTWORT, "oeffentlich": [
        {"sterne": 5, "name": "Alex [Klick](http://boese.de)", "text": "Super <script>x</script> *KI*",
         "datum": "2026-11-12"}]})
    text = skript.abschnitt(daten)
    assert "★★★★☆ 4,3 von 5 · 3 Bewertungen" in text
    assert "| ★★★★★ | ██████████ | 2 |" in text and "| ★★★ | █████ | 1 |" in text
    assert "<script>" not in text and "](http" not in text and "\\*KI\\*" in text
    assert "12.11.2026" in text
    assert "Noch keine Bewertungen" in skript.abschnitt(None)
    readme = "A\n<!-- BEWERTUNGEN:START -->\nalt\n<!-- BEWERTUNGEN:ENDE -->\nB"
    assert skript.readme_einsetzen(readme, "neu") == "A\n<!-- BEWERTUNGEN:START -->\nneu\n<!-- BEWERTUNGEN:ENDE -->\nB"
    # die echte README hat die Markierungen
    assert skript.START in (WURZEL / "README.md").read_text(encoding="utf-8")
