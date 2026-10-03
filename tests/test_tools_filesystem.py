from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import build_registry, ToolContext


def _ctx(tmp_path, **kw):
    defaults = dict(safe_mode=False, auto_confirm=True, use_quarantine=True)
    defaults.update(kw)
    pm = PermissionManager(PermissionSettings(**defaults), tmp_path, confirm_fn=lambda m, r: True)
    return ToolContext(permissions=pm, memory=None), pm


def test_write_read_roundtrip(tmp_path):
    reg = build_registry()
    ctx, _ = _ctx(tmp_path)
    out, err = reg.execute(ctx, "datei_schreiben", {"pfad": "notiz.txt", "inhalt": "Hallo Welt"})
    assert not err and "Erstellt" in out
    out, err = reg.execute(ctx, "datei_lesen", {"pfad": "notiz.txt"})
    assert not err and "Hallo Welt" in out


def test_edit_requires_unique_match(tmp_path):
    reg = build_registry()
    ctx, _ = _ctx(tmp_path)
    reg.execute(ctx, "datei_schreiben", {"pfad": "a.txt", "inhalt": "x x x"})
    out, err = reg.execute(ctx, "datei_bearbeiten", {"pfad": "a.txt", "suchen": "x", "ersetzen": "y"})
    assert "eindeutig" in out or "-mal" in out  # nicht eindeutig -> abgelehnt


def test_edit_success(tmp_path):
    reg = build_registry()
    ctx, _ = _ctx(tmp_path)
    reg.execute(ctx, "datei_schreiben", {"pfad": "b.txt", "inhalt": "Hallo NAME!"})
    out, err = reg.execute(ctx, "datei_bearbeiten", {"pfad": "b.txt", "suchen": "NAME", "ersetzen": "Welt"})
    assert not err
    out, _ = reg.execute(ctx, "datei_lesen", {"pfad": "b.txt"})
    assert "Hallo Welt!" in out


def test_delete_goes_to_quarantine(tmp_path):
    reg = build_registry()
    ctx, pm = _ctx(tmp_path, use_quarantine=True)
    reg.execute(ctx, "datei_schreiben", {"pfad": "weg.txt", "inhalt": "data"})
    out, err = reg.execute(ctx, "datei_loeschen", {"pfad": "weg.txt"})
    assert not err and "Quarantaene" in out
    assert not (tmp_path / "weg.txt").exists()
    assert (tmp_path / ".papierkorb").exists()


def test_delete_blocked_in_safe_mode(tmp_path):
    reg = build_registry()
    ctx, _ = _ctx(tmp_path, safe_mode=True, auto_confirm=False)
    reg.execute(ctx, "datei_schreiben", {"pfad": "x.txt", "inhalt": "data"})
    # Schreiben braucht MODERATE; in safe_mode ist nur DANGEROUS gesperrt,
    # aber auto_confirm=False -> confirm_fn=True erlaubt es. Loeschen ist DANGEROUS.
    out, err = reg.execute(ctx, "datei_loeschen", {"pfad": "x.txt"})
    assert "Safe Mode" in out


def test_list_dir(tmp_path):
    reg = build_registry()
    ctx, _ = _ctx(tmp_path)
    reg.execute(ctx, "datei_schreiben", {"pfad": "eins.txt", "inhalt": "1"})
    out, err = reg.execute(ctx, "ordner_auflisten", {"pfad": "."})
    assert not err and "eins.txt" in out


def test_unknown_tool(tmp_path):
    reg = build_registry()
    ctx, _ = _ctx(tmp_path)
    out, err = reg.execute(ctx, "gibt_es_nicht", {})
    assert err and "Unbekannt" in out
