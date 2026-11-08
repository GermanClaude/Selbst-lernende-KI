"""Neue .exe einsetzen, ohne dass Verknuepfungen kaputtgehen (assistant/austausch.py)."""
import json
import os
import sys
from types import SimpleNamespace

from assistant import austausch
from assistant.config import UpdateSettings
from assistant.updater import Updater

from tests.test_updater import REPO, FakeFetch


def test_overwrite_keeps_the_same_file(tmp_path):
    target = tmp_path / "KI-App.exe"
    target.write_bytes(b"MZ-alt" * 100)
    new = tmp_path / "KI-App.exe.neu"
    new.write_bytes(b"MZ-neu")
    before = os.stat(target)
    assert austausch.overwrite_in_place(new, target)
    after = os.stat(target)
    assert target.read_bytes() == b"MZ-neu"
    assert (before.st_ino, before.st_dev) == (after.st_ino, after.st_dev)  # dieselbe Datei


def test_helper_waits_writes_and_restarts(tmp_path, monkeypatch):
    target = tmp_path / "KI-App.exe"
    target.write_bytes(b"MZ-alt")
    new = tmp_path / "KI-App.exe.neu"
    new.write_bytes(b"MZ-neu")
    started = {}
    monkeypatch.setattr(austausch.subprocess, "Popen", lambda cmd, **kw: started.update(cmd=cmd, env=kw["env"]))
    monkeypatch.setattr(austausch, "wait_for_exit", lambda pid, timeout=0: started.update(waited=pid))
    code = austausch.run_helper([str(new), str(target), "4242", "--app"])
    assert code == 0 and started["waited"] == 4242
    assert target.read_bytes() == b"MZ-neu" and not new.exists()
    assert started["cmd"] == [str(target), "--app"]
    assert started["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert (tmp_path / "logs" / "update.log").read_text(encoding="utf-8").strip()


def _exe_update(tmp_path, inplace=True):
    root = tmp_path / "KI"
    root.mkdir()
    exe = root / "KI-App.exe"
    exe.write_bytes(b"MZ-alt")
    release = {"tag_name": "v0.7.0", "assets": [{"name": "KI-App.exe", "browser_download_url": "u"}]}
    routes = {f"https://api.github.com/repos/{REPO}/releases/latest": json.dumps(release),
              "u": b"MZ" + b"\0" * 1_200_000}
    up = Updater(UpdateSettings(), root, fetch=FakeFetch(routes), current_version="0.6.0",
                 frozen=True, exe_path=exe, inplace=inplace)
    return up, exe


def test_update_waits_for_the_restart_and_keeps_a_copy(tmp_path, monkeypatch):
    up, exe = _exe_update(tmp_path)
    message = up.install(up.check(), say=lambda m: None)
    assert "beim Neustart" in message
    assert exe.read_bytes() == b"MZ-alt"  # die laufende Datei bleibt, wo und was sie ist
    assert up.pending_exe == exe.with_name("KI-App.exe.neu") and up.pending_exe.is_file()
    backup = up.backups()[0].path / "KI-App.exe"
    assert backup.read_bytes() == b"MZ-alt"  # Sicherung ist eine Kopie
    calls = []
    monkeypatch.setattr("assistant.austausch.start_helper", lambda *a, **kw: calls.append((a, kw)))
    up.restart_exe(["--app"])
    assert calls == [((exe, exe.with_name("KI-App.exe.neu"), ["--app"]), {"root": up.root})]
    assert up.pending_exe is None


def test_update_falls_back_when_the_helper_cannot_start(tmp_path, monkeypatch):
    up, exe = _exe_update(tmp_path)
    up.install(up.check(), say=lambda m: None)

    def broken(*a, **kw):
        raise OSError("Virenscanner")

    monkeypatch.setattr("assistant.austausch.start_helper", broken)
    monkeypatch.setattr("assistant.updater.subprocess.Popen", lambda *a, **k: None)
    up.restart_exe(["--app"])
    assert exe.read_bytes().startswith(b"MZ\0")  # neue Version ist trotzdem drin
    assert exe.with_name("KI-App.exe.alt").read_bytes() == b"MZ-alt"


def test_start_helper_copies_itself_to_temp(tmp_path, monkeypatch):
    exe = tmp_path / "KI-App.exe"
    exe.write_bytes(b"MZ-alt")
    seen = {}
    monkeypatch.setattr(austausch.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(austausch.subprocess, "Popen", lambda cmd, **kw: seen.update(cmd=cmd))
    helper = austausch.start_helper(exe, exe.with_name("KI-App.exe.neu"), ["--app"])
    assert helper.read_bytes() == b"MZ-alt" and helper.name.startswith("ki-update-")
    assert seen["cmd"][:3] == [str(helper), "--update-einspielen", str(exe.with_name("KI-App.exe.neu"))]
    assert seen["cmd"][-1] == "--app"


def test_after_start_repairs_once_per_version_and_per_exe(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(austausch, "repair_shortcuts", lambda exe, root: calls.append(exe) or 1)
    monkeypatch.setattr(austausch.tempfile, "gettempdir", lambda: str(tmp_path))
    (tmp_path / "ki-update-99.exe").write_bytes(b"x")
    exe = tmp_path / "KI-App.exe"
    exe.with_name("KI-App.exe.alt").write_bytes(b"alt")
    assert austausch.after_start(exe, tmp_path, "0.7.0", background=False)
    assert calls == [exe] and not (tmp_path / "ki-update-99.exe").exists()
    assert not exe.with_name("KI-App.exe.alt").exists()
    assert not austausch.after_start(exe, tmp_path, "0.7.0", background=False)  # schon erledigt
    assert austausch.after_start(exe, tmp_path, "0.7.0", force=True, background=False)
    assert len(calls) == 2
    terminal = tmp_path / "KI.exe"  # die zweite .exe im selben Ordner hat ihren eigenen Merker
    assert austausch.after_start(terminal, tmp_path, "0.7.0", background=False)
    assert austausch.after_start(exe, tmp_path, "0.6.1", background=False)  # nach /zurueck wieder

    def failing(exe, root):
        raise OSError("PowerShell fehlt")

    monkeypatch.setattr(austausch, "repair_shortcuts", failing)
    assert austausch.after_start(exe, tmp_path, "0.8.0", background=False)
    assert austausch.after_start(exe, tmp_path, "0.8.0", background=False)  # nicht als erledigt gemerkt


def test_an_old_copy_from_the_backup_folder_points_to_the_current_one(tmp_path):
    root = tmp_path / "NovaAI"
    old = root / "versionen" / "0.6.0_2026-11-08_060000" / "KI-App.exe"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"MZ-alt")
    assert austausch.running_from_backup(old) is None  # aktuelle fehlt -> nichts tun
    (root / "KI-App.exe").write_bytes(b"MZ-neu")
    assert austausch.running_from_backup(old) == root / "KI-App.exe"
    assert austausch.running_from_backup(root / "KI-App.exe") is None


def test_shortcut_repair_is_windows_only():
    if sys.platform != "win32":
        assert austausch.repair_shortcuts(SimpleNamespace(), SimpleNamespace()) == 0



def test_helper_falls_back_to_renaming_when_the_file_is_locked(tmp_path, monkeypatch):
    target = tmp_path / "KI-App.exe"
    target.write_bytes(b"MZ-alt")
    new = tmp_path / "KI-App.exe.neu"
    new.write_bytes(b"MZ-neu")
    started = []
    monkeypatch.setattr(austausch, "overwrite_in_place", lambda src, dst: False)  # gesperrt
    monkeypatch.setattr(austausch, "wait_for_exit", lambda pid, timeout=0: None)
    monkeypatch.setattr(austausch.subprocess, "Popen", lambda cmd, **kw: started.append(kw["env"]))
    monkeypatch.setenv("KI_UPDATE_ORDNER", str(tmp_path))
    assert austausch.run_helper([str(new), str(target), "4242", "--app"]) == 0
    assert target.read_bytes() == b"MZ-neu" and target.with_name("KI-App.exe.alt").read_bytes() == b"MZ-alt"
    assert started[0]["KI_NEUSTART_VON"] == "4242"  # wartet auf die alte KI, nicht auf den Helfer
    assert "Ausweichweg" in (tmp_path / "logs" / "update.log").read_text(encoding="utf-8")


def test_helper_gives_up_honestly_and_never_opens_the_old_version_twice(tmp_path, monkeypatch):
    target = tmp_path / "KI-App.exe"
    target.write_bytes(b"MZ-alt")
    new = tmp_path / "KI-App.exe.neu"
    new.write_bytes(b"MZ-neu")
    started = []
    monkeypatch.setattr(austausch, "overwrite_in_place", lambda src, dst: False)
    monkeypatch.setattr(austausch, "replace_by_moving", lambda src, dst: False)
    monkeypatch.setattr(austausch, "wait_for_exit", lambda pid, timeout=0: None)
    monkeypatch.setattr(austausch, "_alive", lambda pid: True)  # die alte KI laeuft noch
    monkeypatch.setattr(austausch.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    monkeypatch.setenv("KI_UPDATE_ORDNER", str(tmp_path))
    assert austausch.run_helper([str(new), str(target), "4242", "--app"]) == 1
    assert started == [] and target.read_bytes() == b"MZ-alt"
    up = Updater(UpdateSettings(), tmp_path, frozen=True, exe_path=target, inplace=True)
    message = up.take_install_failure()
    assert message and "/update" in message and up.take_install_failure() is None


def test_read_only_exe_is_still_updated_in_place(tmp_path):
    import stat

    target = tmp_path / "KI-App.exe"
    target.write_bytes(b"MZ-alt")
    os.chmod(target, stat.S_IREAD)
    new = tmp_path / "neu.bin"
    new.write_bytes(b"MZ-neu")
    try:
        assert austausch.overwrite_in_place(new, target, attempts=2, delay=0)
        assert target.read_bytes() == b"MZ-neu"
    finally:
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE)


def test_vanished_new_version_is_reported_not_pretended(tmp_path):
    import pytest

    from assistant.updater import UpdateError

    up, exe = _exe_update(tmp_path)
    up.install(up.check(), say=lambda m: None)
    up.pending_exe.unlink()  # Virenscanner hat sie weggenommen
    with pytest.raises(UpdateError, match="verschwunden"):
        up.restart_exe(["--app"])
    assert json.loads(up.state_path.read_text(encoding="utf-8"))["installiert"] == "0.6.0"


def test_second_attempt_reuses_the_backup_of_the_same_version(tmp_path):
    up, exe = _exe_update(tmp_path)
    up.install(up.check(), say=lambda m: None)
    up.pending_exe = None
    up.current = "0.6.0"  # Einspielen hat nicht geklappt, gleiche Version nochmal
    up.install(up.check(), say=lambda m: None)
    assert len(up.backups()) == 1


def test_running_app_exe_is_recognized_as_the_ki(monkeypatch):
    from assistant.selbststart import _pid_alive

    for name in ("KI-App.exe", "KI-App (1).exe", "KI.exe"):
        assert _pid_alive(100, {100: (1, name)}), name
    assert not _pid_alive(100, {100: (1, "notepad.exe")})
