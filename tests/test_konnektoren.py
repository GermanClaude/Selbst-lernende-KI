"""0.69: Konnektoren - einfache Oberflaeche ueber das Plugin-/MCP-System (Katalog + Hinzufuegen/An-Aus)."""
import pytest

from assistant import konnektoren as K
from assistant import plugins


def test_katalog_hat_eintraege():
    schluessel = {e["schluessel"] for e in K.katalog()}
    assert {"zeit", "web", "dateien", "github"} <= schluessel
    # Eintraege mit Platzhaltern nennen ihre noetigen Eingaben
    dateien = next(e for e in K.katalog() if e["schluessel"] == "dateien")
    assert dateien["eingaben"] and dateien["eingaben"][0]["feld"] == "<ORDNER>"


def test_hinzufuegen_ohne_platzhalter(tmp_path):
    assert K.hinzufuegen(tmp_path, "zeit") == "zeit"
    alle = plugins.laden(tmp_path)
    assert alle["zeit"]["command"] == "uvx" and "mcp-server-time" in alle["zeit"]["args"]


def test_platzhalter_pflicht(tmp_path):
    with pytest.raises(plugins.PluginFehler, match="ORDNER|fehlt"):
        K.hinzufuegen(tmp_path, "dateien")                     # ohne Ordner -> Fehler
    K.hinzufuegen(tmp_path, "dateien", {"<ORDNER>": "C:/Daten"})
    assert "C:/Daten" in plugins.laden(tmp_path)["dateien"]["args"]


def test_token_landet_in_env(tmp_path):
    K.hinzufuegen(tmp_path, "github", {"<TOKEN>": "ghp_test"})
    assert plugins.laden(tmp_path)["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"] == "ghp_test"


def test_aktive_an_aus_vertrauen_entfernen(tmp_path):
    K.hinzufuegen(tmp_path, "zeit")
    assert [a["name"] for a in K.aktive(tmp_path)] == ["zeit"]
    assert K.aktive(tmp_path)[0]["an"] is True and K.aktive(tmp_path)[0]["vertrauen"] is False
    K.setzen(tmp_path, "zeit", an=False)
    assert K.aktive(tmp_path)[0]["an"] is False
    K.setzen(tmp_path, "zeit", an=True, vertrauen=True)
    a = K.aktive(tmp_path)[0]
    assert a["an"] is True and a["vertrauen"] is True
    assert K.entfernen(tmp_path, "zeit") is True and K.aktive(tmp_path) == []
    assert K.entfernen(tmp_path, "zeit") is False           # schon weg


def test_unbekannter_konnektor(tmp_path):
    with pytest.raises(plugins.PluginFehler, match="Unbekannt"):
        K.hinzufuegen(tmp_path, "gibtsnicht")
