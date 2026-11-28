"""0.71: Proaktive Nova - darf sie sich JETZT von selbst melden? Nur die Regeln (gut testbar);
die eigentliche Wortmeldung macht der Controller ueber brain.wortmeldung (hier nicht getestet)."""
from datetime import datetime

from assistant import proaktiv as PV


def _ts(h, m=0):
    return datetime(2026, 11, 28, h, m).timestamp()


def test_standard_aus(tmp_path):
    assert PV.einstellungen(tmp_path)["an"] is False
    assert PV.faellig(tmp_path, now=_ts(12)) is False          # aus = nie


def test_an_mittag_idle(tmp_path):
    PV.setzen(tmp_path, an=True)
    assert PV.faellig(tmp_path, now=_ts(12)) is True
    assert PV.faellig(tmp_path, now=_ts(12), idle=False) is False   # nicht stoeren


def test_ruhezeit(tmp_path):
    PV.setzen(tmp_path, an=True)
    assert PV.faellig(tmp_path, now=_ts(3)) is False           # 3 Uhr nachts
    assert PV.faellig(tmp_path, now=_ts(23)) is False          # nach 21:00


def test_mindestabstand_und_tageslimit(tmp_path):
    PV.setzen(tmp_path, an=True, min_abstand_min=180, max_pro_tag=2)
    PV.notieren(tmp_path, now=_ts(9))
    assert PV.faellig(tmp_path, now=_ts(9, 30)) is False        # zu kurz nach der letzten
    assert PV.faellig(tmp_path, now=_ts(12)) is True            # 3h spaeter ok
    PV.notieren(tmp_path, now=_ts(12))
    assert PV.faellig(tmp_path, now=_ts(16)) is False           # Tageslimit 2 erreicht


def test_limit_neuer_tag(tmp_path):
    PV.setzen(tmp_path, an=True, max_pro_tag=1)
    PV.notieren(tmp_path, now=_ts(12))
    naechster_tag = datetime(2026, 11, 29, 12, 0).timestamp()
    assert PV.faellig(tmp_path, now=naechster_tag) is True      # Zaehler startet neu


def test_fenster_ueber_nacht(tmp_path):
    PV.setzen(tmp_path, an=True, von="20:00", bis="06:00")      # Nachtfenster
    assert PV.faellig(tmp_path, now=_ts(23)) is True
    assert PV.faellig(tmp_path, now=_ts(12)) is False
