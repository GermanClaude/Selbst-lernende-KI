"""Arbeitsordner (Workspace) auswaehlen: Befehl setzt ihn, legt ihn an, speichert ihn, wirkt sofort."""
from pathlib import Path

import pytest

from assistant.app.controller import AppController
from assistant.config import load_config


@pytest.fixture
def ctl(tmp_path):
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    c = AppController(cfg, lambda e: None)
    yield c
    c.shutdown()


def test_setzen_legt_ordner_an_und_wirkt_sofort(ctl, tmp_path):
    ziel = tmp_path / "mein projekt"            # mit Leerzeichen
    ok, msg = ctl._arbeitsordner_setzen(str(ziel))
    assert ok and ziel.is_dir()
    assert ctl.permissions.workspace_root == ziel.resolve()      # Sandbox/relative Pfade sofort hier
    assert ctl.config.permissions.workspace_root == str(ziel.resolve())
    assert ctl.config.workspace_path == ziel                     # expanduser, nicht zwingend resolved


def test_setzen_wird_dauerhaft_gespeichert(ctl, tmp_path):
    ziel = tmp_path / "dauerhaft"
    ok, _ = ctl._arbeitsordner_setzen(str(ziel))
    assert ok
    text = (tmp_path / "config" / "settings.toml").read_text(encoding="utf-8")
    assert "workspace_root" in text and "dauerhaft" in text


def test_befehl_mit_pfad_setzt(ctl, tmp_path):
    ziel = tmp_path / "per_befehl"
    ctl._arbeitsordner_command([str(ziel)])
    assert ctl.permissions.workspace_root == ziel.resolve()


def test_zuruecksetzen_geht_auf_standard(ctl, tmp_path):
    ctl._arbeitsordner_setzen(str(tmp_path / "woanders"))
    ctl._arbeitsordner_command(["zuruecksetzen"])
    assert ctl.permissions.workspace_root == (tmp_path / "workspace").resolve()


def test_picker_ohne_fenster_bricht_sauber_ab(ctl):
    # Ohne gesetztes _window gibt es keinen Dialog - darf nicht abstuerzen, nichts aendern.
    vorher = ctl.permissions.workspace_root
    assert ctl._arbeitsordner_picker() == ""
    assert ctl.permissions.workspace_root == vorher
