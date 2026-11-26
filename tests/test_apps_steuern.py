"""Apps bedienen fuer jedes Modell - ohne echte Fenster (Attrappe statt PowerShell)."""
import base64
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from assistant import windows_steuerung as W
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry
from assistant.tools import apps

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-Werkzeuge")


def _ctx(tmp_path, gefragt=None, safe=False):
    def confirm(m, r):
        if gefragt is not None:
            gefragt.append(m)
        return True
    pm = PermissionManager(PermissionSettings(safe_mode=safe, auto_confirm=False), tmp_path, confirm_fn=confirm)
    return ToolContext(permissions=pm, memory=None, extra={"app_root": tmp_path, "ki_name": lambda: "Nova"})


class Liste(list):
    pass


@pytest.fixture
def aufrufe2(monkeypatch):
    liste = Liste()
    liste.antworten = {}

    def fake(skript, argumente, timeout=W.TIMEOUT, ki_name="Nova"):
        liste.append((skript, argumente))
        a = liste.antworten.get(skript)
        if isinstance(a, Exception):
            raise a
        return a if a is not None else {"ok": True}
    monkeypatch.setattr(W, "ausfuehren", fake)
    return liste


def test_alle_werkzeuge_fuer_jedes_modell():
    reg = build_registry()
    namen = {"fenster", "app_bedienen", "programm_starten", "bildschirm_text", "maus", "tasten", "zwischenablage",
             "prozesse"}
    assert namen <= set(reg.names())
    openai = {s["function"]["name"] for s in reg.specs_openai()}          # DeepSeek, Gemini, Ollama ...
    assert namen <= openai


def test_angaben_gehen_nie_in_den_skripttext(monkeypatch):
    gesehen = {}

    def lauf(befehl, **kw):
        gesehen["befehl"], gesehen["env"] = befehl, kw["env"]
        return SimpleNamespace(returncode=0, stdout=b'{"ok": true}', stderr=b"")
    boese = "'; Remove-Item C:\\ -Recurse; '"
    W.ausfuehren("bedienen", {"aktion": "klicken", "element": boese}, lauf=lauf, ki_name="Nova")
    skript = base64.b64decode(gesehen["befehl"][-1]).decode("utf-16-le")
    assert boese not in skript and "Remove-Item" not in skript
    args = json.loads(gesehen["env"]["NOVA_ARGS"])
    assert args["element"] == boese and "Nova" in args["eigen_titel"]
    assert not any(k.endswith("_API_KEY") for k in gesehen["env"])


def test_fehlermeldung_wird_lesbar():
    clixml = ('#< CLIXML\n<Objs><S S="Error">Kein Fenster gefunden, das \'x\' heisst._x000D__x000A_</S>'
              '<S S="Error">In Zeile:12 Zeichen:5 + throw ...</S></Objs>').encode()

    def lauf(befehl, **kw):
        return SimpleNamespace(returncode=1, stdout=b"", stderr=clixml)
    with pytest.raises(W.SteuerFehler) as fehler:
        W.ausfuehren("fenster", {"aktion": "fokus"}, lauf=lauf)
    assert str(fehler.value) == "Kein Fenster gefunden, das 'x' heisst."


def test_elemente_als_text(tmp_path, aufrufe2):
    aufrufe2.antworten["bedienen"] = {"fenster": "Rechner", "gesamt": 3, "elemente": [
        {"nr": 1, "typ": "Button", "name": "Sieben", "id": "num7Button"},
        {"nr": 2, "typ": "Edit", "name": "Suche", "wert": "hallo"},
        {"nr": 3, "typ": "Edit", "name": "Kennwort", "passwort": True}]}
    out, _ = build_registry().execute(_ctx(tmp_path), "app_bedienen", {"aktion": "elemente", "fenster": "Rechner"})
    assert "[1] Button 'Sieben' id=num7Button" in out and "= 'hallo'" in out and "(Passwortfeld)" in out


def test_klicken_fragt_mit_klarem_text(tmp_path, aufrufe2):
    aufrufe2.antworten["bedienen"] = {"ok": True, "element": "Speichern", "typ": "Button", "wie": "invoke"}
    gefragt = []
    out, _ = build_registry().execute(_ctx(tmp_path, gefragt), "app_bedienen",
                                      {"aktion": "klicken", "fenster": "Editor", "element": "Speichern"})
    assert "Erledigt" in out and gefragt and "Editor" in gefragt[0] and "Speichern" in gefragt[0]
    assert aufrufe2[-1][1]["element"] == "Speichern" and "nr" not in aufrufe2[-1][1]


def test_tippen_nie_ins_eigene_fenster(tmp_path, aufrufe2, monkeypatch):
    monkeypatch.setattr(W, "eigenes_fenster_vorne", lambda name="Nova": True)
    out, _ = build_registry().execute(_ctx(tmp_path), "tasten", {"aktion": "tippen", "text": "/stuetzraeder alles\n"})
    assert "eigenes Fenster" in out and aufrufe2 == []


def test_maus_nie_ins_eigene_fenster(tmp_path, aufrufe2, monkeypatch):
    monkeypatch.setattr(W, "punkt_im_eigenen_fenster", lambda x, y, name="Nova": True)
    out, _ = build_registry().execute(_ctx(tmp_path), "maus", {"aktion": "klicken", "x": 10, "y": 10})
    assert "eigenes Fenster" in out and aufrufe2 == []


def test_alte_werkzeuge_auch_geschuetzt(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "eigenes_fenster_vorne", lambda name="Nova": True)
    out, _ = build_registry().execute(_ctx(tmp_path), "tastatur_tippen", {"text": "/stuetzraeder alles"})
    assert "eigenes Fenster" in out


def test_gefaehrliches_nur_ohne_stuetzraeder(tmp_path, aufrufe2):
    out, _ = build_registry().execute(_ctx(tmp_path, safe=True), "prozesse", {"aktion": "beenden", "pid": 1234})
    assert aufrufe2 == [] and "safe_mode" in out


def test_bildschirm_text_und_zwischenablage_schwaerzen(tmp_path, aufrufe2):
    aufrufe2.antworten["ocr"] = {"zeilen": [{"text": "Passwort: hunter2geheim", "x": 5, "y": 6}]}
    out, _ = build_registry().execute(_ctx(tmp_path), "bildschirm_text", {"aktion": "lesen"})
    assert "hunter2geheim" not in out and "(5, 6)" in out
    aufrufe2.antworten["zwischenablage"] = {"text": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456"}
    out, _ = build_registry().execute(_ctx(tmp_path), "zwischenablage", {"aktion": "lesen"})
    assert "abcdefghijklmnop" not in out


def test_fehler_wird_freundlich(tmp_path, aufrufe2):
    aufrufe2.antworten["fenster"] = W.SteuerFehler("Kein Fenster gefunden, das 'Spotify' heisst.")
    out, _ = build_registry().execute(_ctx(tmp_path), "fenster", {"aktion": "fokus", "fenster": "Spotify"})
    assert out.startswith("Ging nicht: Kein Fenster")


@pytest.mark.parametrize("skript", sorted(W.SKRIPTE))
def test_powershell_skripte_ohne_syntaxfehler(skript, tmp_path):
    """Nur pruefen (Parser), nichts ausfuehren - es oeffnet sich kein Fenster."""
    datei = tmp_path / "s.ps1"
    datei.write_text(W._VORSPANN + W.SKRIPTE[skript], encoding="utf-8-sig")
    pruefung = ("$f=$null; [void][System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$null,[ref]$f);"
                " $f | ForEach-Object { $_.Message + ' @' + $_.Extent.StartLineNumber }")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", pruefung, str(datei)],
                       capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "", r.stdout
