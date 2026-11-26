"""0.43: gemeinsamer Speicher (Einstellungen im Abgleich), Deinstallieren mit Sicherung, Diagnose-Bericht.
Nichts wird wirklich geloescht, gesendet oder gestartet."""
import json
import os
import sys
import zipfile
from types import SimpleNamespace

import pytest

from assistant import abgleich as A
from assistant import deinstallieren as D
from assistant import diagnose as G
from assistant.memory import Memory


@pytest.fixture
def mem(tmp_path):
    m = Memory(tmp_path / "data" / "memory.sqlite3")
    yield m
    m.close()


# ---------------------------------------------------------------- Abgleich mit Einstellungen
def test_einstellungen_wandern_mit(tmp_path, mem):
    pc, handy = tmp_path / "pc", tmp_path / "handy"
    (pc / "config").mkdir(parents=True)
    (pc / "config" / "ueber_mich.json").write_text('{"name": "Max"}', encoding="utf-8")
    os.utime(pc / "config" / "ueber_mich.json", (2_000_000_000, 2_000_000_000))
    daten = A.MitDateien(mem, pc).exportieren()
    assert daten["dateien"]["config/ueber_mich.json"]["text"] == '{"name": "Max"}'

    m2 = Memory(tmp_path / "m2.sqlite3")
    try:
        ziel = A.MitDateien(m2, handy)
        zahlen = ziel.importieren(daten)
        assert zahlen["dateien"] == 1 and json.loads((handy / "config" / "ueber_mich.json").read_text())["name"] == "Max"
        assert ziel.importieren(daten)["dateien"] == 0                      # schon aktuell: nicht hin und her
        boese = {"dateien": {"../../boese.txt": {"text": "x", "zeit": 9e9}, ".env": {"text": "K=1", "zeit": 9e9}}}
        ziel.importieren(boese)
        assert not (tmp_path / "boese.txt").exists() and not (handy / ".env").exists()   # nur bekannte Dateien
        assert not A._gleich(daten, ziel.exportieren() | {"dateien": {}})  # Dateiunterschied zaehlt
    finally:
        m2.close()


def test_schluessel_und_rechte_werden_nie_geteilt():
    assert not any(n in A.GETEILTE_DATEIEN for n in (".env", "config/permissions.toml", "config/plugins.json",
                                                    "config/settings.toml", "data/server_token"))


# ---------------------------------------------------------------- Deinstallieren
def test_nur_novas_eigene_teile(tmp_path):
    for n in ("KI.exe", "data", "config", "logs", "workspace"):
        (tmp_path / n).mkdir() if "." not in n else (tmp_path / n).write_text("x")
    (tmp_path / "Urlaubsfotos").mkdir()
    (tmp_path / "Steuer.pdf").write_text("x")
    teile = {t.name for t in D.zu_loeschen(tmp_path)}
    assert teile == {"KI.exe", "data", "config", "logs", "workspace"}
    (tmp_path / ".git").mkdir()                                             # Quellcode: Code bleibt
    assert "KI.exe" not in {t.name for t in D.zu_loeschen(tmp_path)}


def test_eigener_arbeitsordner_bleibt(tmp_path):
    root = tmp_path / "nova"
    (root / "data").mkdir(parents=True)
    draussen = tmp_path / "meine-projekte"
    draussen.mkdir()
    teile = D.zu_loeschen(root, draussen)
    assert all(draussen not in [t, *t.parents] for t in teile) and [t.name for t in teile] == ["data"]


def test_sicherung_und_einspielen(tmp_path, mem):
    root = tmp_path / "nova"
    (root / "config").mkdir(parents=True)
    (root / "config" / "persona.md").write_text("Ich bin Nova.", encoding="utf-8")
    (root / ".env").write_text("ANTHROPIC_API_KEY=geheim", encoding="utf-8")
    ws = root / "workspace"
    (ws / "projekt").mkdir(parents=True)
    (ws / "projekt" / "notiz.txt").write_text("hallo", encoding="utf-8")
    pfad = D.sicherung(root, mem, ws, ziel=tmp_path / "desktop")
    with zipfile.ZipFile(pfad) as z:
        namen = set(z.namelist())
    assert {"gedaechtnis.json", "config/persona.md", "arbeitsordner/projekt/notiz.txt", "LIESMICH.txt"} <= namen
    assert not any(".env" in n for n in namen)                              # nie Schluessel
    neu = tmp_path / "neu"
    m2 = Memory(tmp_path / "neu.sqlite3")
    try:
        meldung = D.einspielen(neu, m2, pfad)
        assert "config/persona.md" in meldung and (neu / "config" / "persona.md").read_text() == "Ich bin Nova."
    finally:
        m2.close()


def test_loesch_skript_wartet_und_loescht_nur_die_liste(tmp_path):
    teile = [tmp_path / "data", tmp_path / "KI.exe"]
    s = D.loesch_skript(tmp_path, teile, 4242)
    assert "4242" in s and str(tmp_path / "data") in s and "Steuer" not in s
    if sys.platform == "win32":
        assert "Get-ChildItem" in s     # den Ordner selbst nur, wenn er danach leer ist


def test_deinstallieren_ist_kein_werkzeug():
    from assistant.tools import build_registry
    assert not any("deinstall" in n for n in build_registry().names())


# ---------------------------------------------------------------- Diagnose
def test_diagnose_ohne_persoenliches(tmp_path, monkeypatch):
    (tmp_path / "logs").mkdir()
    heim = str(tmp_path / "Users" / "maxmuster")
    monkeypatch.setattr(G.Path, "home", staticmethod(lambda: G.Path(heim)))
    (tmp_path / "logs" / "ki.log").write_text(
        f"Fehler in {heim}\\x.py\nmail max@example.org tel +49 171 2345678\nsk-ant-api03-{'a' * 40}\n", encoding="utf-8")
    lauf = lambda *a, **k: SimpleNamespace(stdout="Grafik X", returncode=0)   # noqa: E731
    text = G.erstellen(tmp_path, "geht nicht", ["App: kaputt"], "deepseek / x", lauf=lauf)
    for verboten in ("maxmuster", "max@example.org", "2345678", "a" * 30):
        assert verboten not in text
    assert "geht nicht" in text and "App: kaputt" in text and "Arbeitsspeicher" in text
    assert len(text) <= G.MAX_TEXT


def test_diagnose_senden_ueber_feedback(tmp_path, monkeypatch):
    from assistant import feedback
    gesendet = {}
    monkeypatch.setattr(feedback, "ziel_url", lambda config: "https://script.google.com/macros/s/x/exec")
    monkeypatch.setattr(feedback, "baue_payload", lambda *a, **k: {"kind": a[0], "text": a[2]})

    def senden(payload, url, post, root=None):
        gesendet.update(payload)
        return SimpleNamespace(status="gesendet", ok=True)
    monkeypatch.setattr(feedback, "senden", senden)
    meldung = G.senden(SimpleNamespace(project_root=tmp_path), "Bericht")
    assert "gesendet" in meldung and gesendet["kind"] == "bug" and "Diagnose" in gesendet["text"]


def test_keine_mailadresse_im_code():
    """Die Adresse des Entwicklers steht nirgends im Programm - nur im Postfach hinter dem Google-Skript."""
    from pathlib import Path
    wurzel = Path(__file__).resolve().parent.parent / "assistant"
    for datei in wurzel.rglob("*.py"):
        text = datei.read_text(encoding="utf-8", errors="ignore")
        assert "@gmail.com" not in text, datei


def test_nach_absturz_fragt_vorher(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "senden", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ohne Ja gesendet")))
    gefragt = []
    G.nach_absturz("Traceback ...", lambda t: gefragt.append(t) or False, melden=lambda t: None)
    assert gefragt and "Diagnose-Bericht" in gefragt[0]
