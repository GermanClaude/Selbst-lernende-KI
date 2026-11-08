"""Live-Sehen im Terminal: /sehen, Zustimmung, Gesehenes in der naechsten Nachricht, Jarvis-Wortmeldung."""
import threading
from types import SimpleNamespace

import pytest

from assistant.config import load_config
from assistant.sehen.dienst import Weckpaket


@pytest.fixture
def cli(tmp_path):
    from assistant.ui.cli import CLI

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    cfg.provider.aktiv = "claude"
    c = CLI(cfg)
    c.sehen.fenster_schutz = lambda an: ""
    yield c
    c.sehen.aus()
    c.memory.close()


def test_status_und_hilfe(cli, capsys):
    from assistant.ui import cli as cli_modul

    cli._handle_command("/sehen")
    assert "Live-Sehen ist aus" in capsys.readouterr().out
    assert "/sehen" in cli_modul.__doc__ and "nur in der App" in cli_modul.__doc__
    cli._handle_command("/sehen quatsch")
    assert "So geht es" in capsys.readouterr().out


def test_ohne_ja_bleibt_es_aus(cli, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_ask_yes", lambda *a, **k: False)
    cli._handle_command("/sehen an")
    out = capsys.readouterr().out
    assert "Live-Sehen einschalten?" in out and "Passwortfelder" in out and "bleibt aus" in out
    assert not cli.sehen.aktiv and cli.sehen.braucht_zustimmung()


def test_mit_ja_wird_zugestimmt_und_eingeschaltet(cli, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_ask_yes", lambda *a, **k: True)
    cli.sehen.bildschirm_moeglich = True
    gestartet = []

    class Auge:
        def __init__(self, einst):
            gestartet.append(einst)

        def start(self):
            pass

        def senden(self, b):
            pass

        def lies(self, timeout=0.1):
            threading.Event().wait(min(timeout, 0.05))

        def lebt(self):
            return True

        def stop(self, warten=2.0):
            pass

    cli.sehen.auge_fabrik = Auge
    cli._handle_command("/sehen bildschirm")
    out = capsys.readouterr().out
    assert cli.sehen.aktiv and cli.sehen.quellen == {"bildschirm"} and gestartet
    assert "Live-Sehen ist an" in out and not cli.sehen.braucht_zustimmung()
    text = (tmp_path / "config" / "settings.toml").read_text(encoding="utf-8")
    assert 'quelle = "bildschirm"' in text and "einverstanden_am" in text
    cli._handle_command("/sehen pause")
    assert cli.sehen.pausiert
    cli._handle_command("/sehen status")
    assert "Pause" in capsys.readouterr().out
    cli._handle_command("/sehen aus")
    assert not cli.sehen.aktiv


def test_terminal_ohne_jarvis_nimmt_das_gesehene_in_die_naechste_nachricht(cli, capsys):
    cli.sehen.aktiv = True
    paket = Weckpaket(text="x", anzeige="Nova hat etwas bemerkt: Fehlerfenster", zeilen=["Fehlerfenster in Excel"])
    cli._sehen_wecken(paket)
    cli._sehen_notiz("Live-Sehen: Hinweis")
    cli._sehen_zeigen()
    out = capsys.readouterr().out
    assert "Fehlerfenster" in out and "Hinweis" in out
    vorspann = cli._sehen_kontext()
    assert "Fehlerfenster in Excel" in vorspann and "nicht vertrauenswuerdig" in vorspann
    assert cli._sehen_kontext() == ""                     # nur einmal


def test_terminal_jarvis_wortmeldung(cli, capsys):
    from assistant.ui.cli import _TerminalLiveHost
    from tests._fakes import AnthroClient, anthro_msg, text_block

    cli.brain.provider.client = AnthroClient([(anthro_msg([text_block("[still]")]), [SimpleNamespace(
        type="text", text="[still]")])])
    host = _TerminalLiveHost(cli)
    ende = []
    host.loop = SimpleNamespace(on_turn_end=lambda c=False: ende.append(c), on_text=lambda t: None,
                                on_tool=lambda: None)
    vorher = len(cli.brain.provider.messages)
    assert host.start_seen_turn(Weckpaket(text="Gerade passiert: X", anzeige="Nova hat etwas bemerkt: X"))
    host.worker.join(10)
    assert ende == [False] and len(cli.brain.provider.messages) == vorher   # [still]: zurueckgenommen
    assert "[still]" not in capsys.readouterr().out and not cli.permissions.away
