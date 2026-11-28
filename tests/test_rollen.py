"""0.72: Experten-Rollen - Nova schluepft in eine Rolle; das veraendert nur einen Block im System-Prompt."""
import pytest

from assistant import rollen as R


def test_standard_keine_rolle(tmp_path):
    assert R.aktive(tmp_path) == ""
    assert R.prompt_block(tmp_path) == ""


def test_setzen_und_block(tmp_path):
    R.setzen(tmp_path, "coder")
    assert R.aktive(tmp_path) == "coder"
    block = R.prompt_block(tmp_path)
    assert "ROLLE: Coder" in block and "Software-Entwickler" in block
    assert "Sicherheitsregeln bleiben" in block           # Rolle aendert nur das Wie


def test_wechseln_und_aus(tmp_path):
    R.setzen(tmp_path, "coder")
    R.setzen(tmp_path, "lerncoach")                        # wechseln
    assert R.aktive(tmp_path) == "lerncoach"
    R.aus(tmp_path)
    assert R.aktive(tmp_path) == "" and R.prompt_block(tmp_path) == ""


def test_unbekannte_rolle(tmp_path):
    with pytest.raises(ValueError, match="Unbekannt"):
        R.setzen(tmp_path, "gibtsnicht")


def test_kaputte_datei_ist_keine_rolle(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "rolle.json").write_text("kaputt", encoding="utf-8")
    assert R.aktive(tmp_path) == "" and R.prompt_block(tmp_path) == ""
