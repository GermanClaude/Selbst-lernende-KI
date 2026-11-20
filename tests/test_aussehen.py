"""Design-Vorlagen, Hintergrundbild und dass Updates das Design nie anfassen."""
import json

import pytest

from assistant import aussehen, updater

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)  # reicht als "Bilddatei" fuer den Test


def _cfg(tmp_path):
    (tmp_path / "config").mkdir()
    return tmp_path


def test_vorlage_setzen_und_entfernen(tmp_path):
    root = _cfg(tmp_path)
    data = aussehen.set_thema(root, "Hacker")  # Gross-/Kleinschreibung egal
    assert data["thema"] == "hacker"
    assert data["akzentfarbe"] == aussehen.THEMES["hacker"]["akzent"]
    assert data["sphaere_farbe"] == aussehen.THEMES["hacker"]["sphaere"]
    gespeichert = json.loads((root / "config" / "app-anpassung.json").read_text(encoding="utf-8"))
    assert gespeichert["thema"] == "hacker"
    css = aussehen.generated_css(root)
    assert "--bg:#000700" in css and "monospace" in css and "prefers-color-scheme: dark" in css
    # "aus" entfernt Vorlage und die mitgesetzten Farben
    data = aussehen.set_thema(root, "aus")
    assert "thema" not in data and "akzentfarbe" not in data
    assert aussehen.generated_css(root) == ""


def test_unbekannte_vorlage():
    with pytest.raises(ValueError):
        aussehen.set_thema(".", "gibtsnicht")


def test_hintergrundbild(tmp_path):
    root = _cfg(tmp_path)
    data = aussehen.set_hintergrund(root, PNG, ".png", deckkraft=0.5)
    assert data["hintergrund"]["datei"] == "app-hintergrund.png"
    assert (root / "config" / "app-hintergrund.png").read_bytes() == PNG
    css = aussehen.generated_css(root)
    assert "data:image/png;base64," in css and "background-attachment:fixed" in css
    assert "rgba(0,0,0,0.5)" in css
    # entfernen loescht Datei und Eintrag
    aussehen.clear_hintergrund(root)
    assert not (root / "config" / "app-hintergrund.png").exists()
    assert aussehen.generated_css(root) == ""


def test_hintergrund_grenzen(tmp_path):
    root = _cfg(tmp_path)
    with pytest.raises(ValueError):
        aussehen.set_hintergrund(root, PNG, ".txt")  # falsche Endung
    with pytest.raises(ValueError):
        aussehen.set_hintergrund(root, b"x" * (7 * 1024 * 1024), ".jpg")  # zu gross


def test_vorlage_und_bild_zusammen_mit_eigenem_css(tmp_path):
    root = _cfg(tmp_path)
    aussehen.set_thema(root, "dracula")
    aussehen.set_hintergrund(root, PNG, "png")
    aussehen.set_css(root, "body{letter-spacing:1px}")
    gen = aussehen.generated_css(root)
    assert "--bg:#1a1b26" in gen and "data:image/png" in gen
    assert aussehen.css(root) == "body{letter-spacing:1px}"  # eigenes CSS getrennt erhalten


def test_zuruecksetzen_loescht_auch_hintergrund(tmp_path):
    root = _cfg(tmp_path)
    aussehen.set_thema(root, "retro")
    aussehen.set_hintergrund(root, PNG, "jpg")
    aussehen.set_css(root, "x{}")
    aussehen.reset(root)
    assert not (root / "config" / "app-anpassung.json").exists()
    assert not (root / "config" / "app-anpassung.css").exists()
    assert not any((root / "config").glob("app-hintergrund.*"))


def test_updates_fassen_das_design_nie_an():
    # Der Updater behandelt alle Design-Dateien als geschuetzt (werden nie ueberschrieben/geloescht).
    for rel in ("config/app-anpassung.json", "config/app-anpassung.css",
                "config/app-hintergrund.png", "config/app-hintergrund.jpg"):
        assert updater._is_protected(rel) is True
    # Normale Programmdateien sind NICHT geschuetzt (werden aktualisiert).
    assert updater._is_protected("assistant/app/static/app.css") is False


def test_werkzeug_vorlage_und_hintergrund(tmp_path):
    from assistant.permissions import PermissionManager
    from assistant.config import load_config
    from assistant.tools import build_registry, ToolContext

    root = _cfg(tmp_path)
    (root / "bild.png").write_bytes(PNG)
    reg = build_registry()
    pm = PermissionManager(load_config().permissions, root, confirm_fn=lambda m, r: True)
    pm.app_root = root
    ctx = ToolContext(permissions=pm)
    out, err = reg.execute(ctx, "app_anpassen", {"aktion": "vorlage", "vorlage": "hacker"})
    assert not err and "hacker" in out.lower()
    out, err = reg.execute(ctx, "app_anpassen", {"aktion": "hintergrund", "datei": str(root / "bild.png")})
    assert not err and "Hintergrundbild" in out
    assert (root / "config" / "app-hintergrund.png").exists()
    out, _ = reg.execute(ctx, "app_anpassen", {"aktion": "hintergrund", "datei": ""})
    assert "brauche ich" in out
