"""Aktivitaets-Protokoll (welche Apps/Fenster) - reine Logik, KEIN Keylogger."""
from assistant import protokoll as pr
from assistant.protokoll import Protokoll, Schnappschuss


def test_format_eintrag():
    s = Schnappschuss(zeit=0, fenster="Discord - #general", app="discord.exe")
    zeile = pr.format_eintrag(s)
    assert "Discord - #general" in zeile and "discord.exe" in zeile and zeile.startswith("[")


def test_protokoll_text_enthaelt_keylogger_hinweis():
    text = pr.protokoll_text([Schnappschuss(0, "A", "a.exe")], titel="Protokoll")
    assert "# Protokoll" in text and "Keylogger" in text and "A" in text


def test_zusammengefasst_zaehlt():
    snaps = [Schnappschuss(0, "x", "a.exe"), Schnappschuss(1, "y", "a.exe"), Schnappschuss(2, "z", "b.exe")]
    top = pr.zusammengefasst(snaps)
    assert top[0] == ("a.exe", 2) and ("b.exe", 1) in top


def test_aktives_fenster_gibt_zwei_strings():
    titel, app = pr.aktives_fenster()  # je nach OS leer - darf nie abstuerzen
    assert isinstance(titel, str) and isinstance(app, str)


def test_protokoll_baut_ohne_start(tmp_path):
    p = Protokoll(tmp_path / "prot")
    assert p.status.laeuft is False and p.status.eintraege == 0
