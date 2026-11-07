"""Wer startet die KI? Autostart-Diagnose, Sperren, nur ein Fenster."""
import json
import os
from pathlib import Path

from assistant import selbststart as s
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry


def test_classify_scheduler_and_double_click(monkeypatch):
    monkeypatch.setattr(s, "_seconds_since_boot", lambda: 10_000)
    who, unexpected = s.classify([(10, "cmd.exe"), (5, "svchost.exe"), (1, "services.exe")])
    assert "Aufgabenplanung" in who and unexpected
    who, unexpected = s.classify([(10, "cmd.exe"), (7, "explorer.exe")])
    assert "Doppelklick" in who and not unexpected
    monkeypatch.setattr(s, "_seconds_since_boot", lambda: 30)
    assert s.classify([(10, "cmd.exe"), (7, "explorer.exe")])[1]  # direkt nach dem Anmelden


def test_classify_started_by_running_ki():
    who, unexpected = s.classify([(20, "cmd.exe"), (15, "python.exe")], ki_pids={15})
    assert "anderen laufenden KI" in who and unexpected


def test_ancestry_from_process_table():
    table = {100: (50, "python.exe"), 50: (40, "cmd.exe"), 40: (4, "svchost.exe"), 4: (0, "System")}
    assert s.ancestry(100, table) == [(50, "cmd.exe"), (40, "svchost.exe"), (4, "System")]


def test_start_guard_single_instance(tmp_path, monkeypatch):
    other_pid = 99999
    table = {other_pid: (1, "python.exe"), os.getpid(): (other_pid, "python.exe")}
    guard = s.StartGuard(tmp_path, table=table)
    assert guard.running_pid() is None
    (tmp_path / "data").mkdir()
    (tmp_path / "data/ki.lock").write_text(json.dumps({"pid": other_pid}))
    assert guard.running_pid() == other_pid           # andere KI laeuft noch
    guard = s.StartGuard(tmp_path, table={os.getpid(): (1, "python.exe")})
    assert guard.running_pid() is None                # Sperre einer beendeten KI zaehlt nicht
    guard.acquire()
    assert json.loads((tmp_path / "data/ki.lock").read_text())["pid"] == os.getpid()
    guard.release()
    assert not (tmp_path / "data/ki.lock").exists()


def test_restart_after_update_waits_instead_of_refusing(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/ki.lock").write_text(json.dumps({"pid": 4242}))
    monkeypatch.setenv("KI_NEUSTART_VON", "4242")
    monkeypatch.setattr(s, "_process_table", lambda: {})  # alte KI hat sich beendet
    guard = s.StartGuard(tmp_path, table={4242: (1, "KI.exe")})
    assert guard.running_pid() is None


def test_start_log_marks_unexpected_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "_seconds_since_boot", lambda: 10_000)
    table = {os.getpid(): (50, "python.exe"), 50: (40, "cmd.exe"), 40: (4, "taskhostw.exe")}
    guard = s.StartGuard(tmp_path, table=table)
    who, unexpected = guard.record_start()
    assert unexpected and "Aufgabenplanung" in who
    assert guard.starts()[-1]["unerwartet"] is True


def test_only_script_processes_count_as_watchdogs(tmp_path):
    markers = s._markers(Path("C:/KI"), Path("C:/KI/workspace"))
    procs = [
        (11, "python.exe", "python C:/KI/workspace/waechter.py"),
        (12, "Code.exe", "Code.exe C:/KI"),          # Editor mit offenem Ordner: kein Waechter
        (13, "cmd.exe", 'cmd /c "C:/KI/start.bat"'),
        (14, "python.exe", "python other.py"),
    ]
    found = s._match_processes(procs, markers)
    assert [e.ref["pid"] for e in found] == [11, 13]


def test_remove_startup_file_keeps_a_copy(tmp_path):
    startup = tmp_path / "Startup"
    startup.mkdir()
    link = startup / "KI.bat"
    link.write_text("call C:\\KI\\start.bat")
    entry = s.Autostart("ordner", link.name, str(link), {"file": str(link)})
    msg = s.entferne(entry, tmp_path)
    assert "entfernt" in msg and not link.exists()
    assert list((tmp_path / "data/entfernt").iterdir())


def test_persistence_detection():
    assert s.sets_up_autostart('schtasks /create /sc minute /mo 2 /tn "KI" /tr "C:\\KI\\start.bat"')
    assert s.sets_up_autostart("reg add HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run /v KI /d x")
    assert s.sets_up_autostart('powershell Register-ScheduledTask -TaskName KI')
    assert not s.sets_up_autostart("dir C:\\Users")
    assert s.starts_the_ki('start "" "C:\\KI\\start.bat"') and s.starts_the_ki("python -m assistant")
    assert s.is_autostart_path(Path("C:/Users/x/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/a.lnk"))


def _pm(tmp_path, answers, **kw):
    asked = []

    def confirm(message, risk):
        asked.append(message)
        return answers.pop(0) if answers else False

    settings = dict(safe_mode=False, auto_confirm=True, allow_full_filesystem=True)
    settings.update(kw)
    return PermissionManager(PermissionSettings(**settings), tmp_path, confirm_fn=confirm), asked


def test_autostart_command_always_asks_even_with_auto_confirm(tmp_path):
    pm, asked = _pm(tmp_path, [False])
    decision = pm.check_shell("schtasks /create /sc minute /tn KI /tr start.bat")
    assert not decision.allowed and "AUTOMATISCHEN START" in asked[0]
    pm, asked = _pm(tmp_path, [True])
    assert pm.check_shell("schtasks /create /sc minute /tn KI /tr start.bat").allowed
    pm, asked = _pm(tmp_path, [])
    assert pm.check_shell("echo hallo").allowed and asked == []  # normales bleibt ohne Rueckfrage


def test_ki_does_not_restart_itself_without_asking(tmp_path):
    pm, asked = _pm(tmp_path, [False])
    assert not pm.check_shell('start "" C:\\KI\\start.bat').allowed
    assert "weiteres Mal starten" in asked[0]


def test_writing_into_startup_folder_asks(tmp_path):
    startup = tmp_path / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
    pm, asked = _pm(tmp_path, [False])
    ctx = ToolContext(permissions=pm, memory=None)
    out, _ = build_registry().execute(ctx, "datei_schreiben", {"pfad": str(startup / "ki.bat"), "inhalt": "x"})
    assert "Nicht ausgefuehrt" in out and not (startup / "ki.bat").exists()
