"""Tests fuers Live-Coding-Fenster (Premium). Ohne echtes Fenster: No-Op-Sicherheit + dass die
Datei-Werkzeuge den Live-Feed speisen."""
from assistant import live_coding
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import build_registry, ToolContext


def _ctx(tmp_path):
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=True, use_quarantine=True),
                           tmp_path, confirm_fn=lambda m, r: True)
    return ToolContext(permissions=pm, memory=None)


def test_zeige_und_stoppen_ohne_fenster_sind_noop():
    # Ohne geoeffnetes Fenster darf nichts werfen und aktiv() bleibt False.
    assert live_coding.aktiv() is False
    live_coding.zeige("foo.py", "print('hi')", "schreibt")
    live_coding.stoppen()
    assert live_coding.aktiv() is False


def test_schreiben_speist_live_feed(tmp_path, monkeypatch):
    rufe = []
    monkeypatch.setattr(live_coding, "zeige", lambda pfad, inhalt, aktion="schreibt": rufe.append((str(pfad), inhalt, aktion)))
    reg = build_registry()
    ctx = _ctx(tmp_path)
    reg.execute(ctx, "datei_schreiben", {"pfad": "code.py", "inhalt": "x = 1\n"})
    assert rufe and rufe[-1][1] == "x = 1\n"
    assert rufe[-1][2] in ("erstellt", "schreibt")


def test_bearbeiten_speist_live_feed(tmp_path, monkeypatch):
    rufe = []
    monkeypatch.setattr(live_coding, "zeige", lambda pfad, inhalt, aktion="schreibt": rufe.append((str(pfad), inhalt, aktion)))
    reg = build_registry()
    ctx = _ctx(tmp_path)
    reg.execute(ctx, "datei_schreiben", {"pfad": "b.py", "inhalt": "Hallo NAME"})
    reg.execute(ctx, "datei_bearbeiten", {"pfad": "b.py", "suchen": "NAME", "ersetzen": "Welt"})
    assert rufe[-1][1] == "Hallo Welt" and rufe[-1][2] == "ändert"
