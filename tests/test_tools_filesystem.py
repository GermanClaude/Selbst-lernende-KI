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


def test_read_long_file_in_sections(tmp_path):
    reg = build_registry()
    ctx, _ = _ctx(tmp_path)
    (tmp_path / "lang.txt").write_text("\n".join(f"Zeile {i}" for i in range(1, 1001)), encoding="utf-8")
    out, err = reg.execute(ctx, "datei_lesen", {"pfad": "lang.txt"})
    assert not err and "Zeilen 1-400 von 1000" in out and "ab_zeile=401" in out
    assert "Zeile 400\n" in out and "Zeile 401" not in out
    out, err = reg.execute(ctx, "datei_lesen", {"pfad": "lang.txt", "ab_zeile": 901})
    assert "Zeilen 901-1000 von 1000" in out and "Zeile 1000" in out and "Ende der Datei" in out
    out, _ = reg.execute(ctx, "datei_lesen", {"pfad": "lang.txt", "ab_zeile": 5000})
    assert "nur 1000 Zeilen" in out


def test_write_append(tmp_path):
    reg = build_registry()
    ctx, _ = _ctx(tmp_path)
    reg.execute(ctx, "datei_schreiben", {"pfad": "teile.py", "inhalt": "teil1\n"})
    out, err = reg.execute(ctx, "datei_schreiben", {"pfad": "teile.py", "inhalt": "teil2\n", "anhaengen": True})
    assert not err and "Angehaengt" in out
    assert (tmp_path / "teile.py").read_text(encoding="utf-8") == "teil1\nteil2\n"
