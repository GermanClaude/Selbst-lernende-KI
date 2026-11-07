"""Updater: neue Version erkennen, sicher installieren, alte Versionen behalten."""
import io
import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from assistant.config import UpdateSettings
from assistant.updater import (
    UpdateError,
    Updater,
    changelog_between,
    is_newer,
    parse_version,
)

REPO = "GermanClaude/Selbst-lernende-KI"
RAW = f"https://raw.githubusercontent.com/{REPO}/HEAD/"
ZIP = f"https://api.github.com/repos/{REPO}/zipball"
CHANGELOG = """# Neuigkeiten

## 0.3.0 – 2026-12-01
- Noch neuer

## 0.2.0 – 2026-11-07
- F2 zum Sprechen

## 0.1.0 – 2026-10-03
- Erste Version
"""


def _init(version):
    return f'"""KI"""\n\n__version__ = "{version}"\n'


def make_zip(files, top="GermanClaude-Selbst-lernende-KI-abc1234"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(top + "/", "")
        for rel, content in files.items():
            z.writestr(f"{top}/{rel}", content)
    return buf.getvalue()


REMOTE_FILES = {
    "assistant/__init__.py": _init("0.2.0"),
    "assistant/neu.py": "NEU = True\n",
    "run_ki.py": "print('v2')\n",
    "requirements.txt": "requests\nneues-paket\n",
    "config/persona.md": "Standard-Persona\n",
    "config/settings.example.toml": "[ki]\nname = 'Aria'\n",
    "CHANGELOG.md": CHANGELOG,
}


class FakeFetch:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, timeout=15):
        self.calls.append(url)
        value = self.routes.get(url)
        if value is None:
            raise RuntimeError(f"404 {url}")
        return value if isinstance(value, bytes) else value.encode("utf-8")


def _install_dir(tmp_path):
    root = tmp_path / "KI"
    files = {
        "assistant/__init__.py": _init("0.1.0"),
        "assistant/alt.py": "ALT = True\n",
        "run_ki.py": "print('v1')\n",
        "requirements.txt": "requests\n",
        ".env": "DEEPSEEK_API_KEY=sk-geheim\n",
        "config/settings.toml": "[provider]\naktiv = 'deepseek'\n",
        "config/persona.md": "Meine eigene Persona\n",
        "data/memory.sqlite3": "GEDAECHTNIS",
        "workspace/projekt.txt": "meine Arbeit",
        "meine_notizen.txt": "privat",
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _updater(root, routes, current="0.1.0", runs=None, **settings):
    runs = runs if runs is not None else []

    def run(cmd, **kw):
        runs.append(cmd)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    return Updater(UpdateSettings(**settings), root, fetch=FakeFetch(routes), current_version=current,
                   frozen=False, run=run)


def _routes(remote=REMOTE_FILES, version="0.2.0"):
    return {
        RAW + "assistant/__init__.py": _init(version),
        RAW + "CHANGELOG.md": CHANGELOG,
        ZIP: make_zip(remote),
    }


def test_versions():
    assert parse_version("v0.10.2") == (0, 10, 2)
    assert is_newer("0.10.0", "0.9.9") and not is_newer("0.2.0", "0.2.0")
    notes = changelog_between(CHANGELOG, "0.1.0", "0.2.0")
    assert "F2 zum Sprechen" in notes and "Noch neuer" not in notes and "Erste Version" not in notes


def test_check_finds_newer_version_with_notes(tmp_path):
    up = _updater(_install_dir(tmp_path), _routes())
    info = up.check()
    assert info.new == "0.2.0" and info.current == "0.1.0" and info.kind == "quelle"
    assert "F2 zum Sprechen" in info.notes
    assert info.download_url == ZIP


def test_never_downgrades(tmp_path):
    # Der Standard-Branch hat eine AELTERE Version als die installierte.
    up = _updater(_install_dir(tmp_path), _routes(version="0.1.0"), current="0.2.0")
    assert up.check() is None


def test_branch_setting_is_used(tmp_path):
    routes = {
        f"https://raw.githubusercontent.com/{REPO}/test-zweig/assistant/__init__.py": _init("0.2.0"),
        f"https://api.github.com/repos/{REPO}/zipball/test-zweig": make_zip(REMOTE_FILES),
    }
    up = _updater(_install_dir(tmp_path), routes, branch="test-zweig")
    info = up.check()
    assert info.new == "0.2.0" and info.download_url.endswith("/zipball/test-zweig")


def test_offline_check_is_quiet(tmp_path):
    up = _updater(_install_dir(tmp_path), {})
    assert up.check() is None and up.last_error


def test_install_replaces_program_but_keeps_user_data(tmp_path):
    root = _install_dir(tmp_path)
    runs = []
    up = _updater(root, _routes(), runs=runs)
    message = up.install(up.check(), say=lambda m: None)
    assert "0.2.0" in message
    read = lambda rel: (root / rel).read_text(encoding="utf-8")  # noqa: E731
    # neue Programmdateien
    assert "0.2.0" in read("assistant/__init__.py") and read("run_ki.py") == "print('v2')\n"
    assert (root / "assistant/neu.py").exists()
    assert not (root / "assistant/alt.py").exists()  # veraltetes Modul entfernt
    # deine Daten bleiben unangetastet
    assert read(".env") == "DEEPSEEK_API_KEY=sk-geheim\n"
    assert read("config/settings.toml") == "[provider]\naktiv = 'deepseek'\n"
    assert read("config/persona.md") == "Meine eigene Persona\n"
    assert read("data/memory.sqlite3") == "GEDAECHTNIS"
    assert read("workspace/projekt.txt") == "meine Arbeit"
    assert read("meine_notizen.txt") == "privat"
    # alte Version gesichert
    backups = up.backups()
    assert len(backups) == 1 and backups[0].version == "0.1.0"
    saved = backups[0].path
    assert (saved / "run_ki.py").read_text(encoding="utf-8") == "print('v1')\n"
    assert (saved / "assistant/alt.py").exists()
    assert not (saved / ".env").exists() and not (saved / "data").exists()
    # neue Pakete installiert, weil requirements.txt sich geaendert hat
    assert len(runs) == 1 and runs[0][-2:] == ["-r", str(root / "requirements.txt")]
    assert json.loads((root / "data/update.json").read_text(encoding="utf-8"))["installiert"] == "0.2.0"


def test_missing_persona_is_created(tmp_path):
    root = _install_dir(tmp_path)
    (root / "config/persona.md").unlink()
    up = _updater(root, _routes())
    up.install(up.check(), say=lambda m: None)
    assert (root / "config/persona.md").read_text(encoding="utf-8") == "Standard-Persona\n"


def test_git_checkout_is_not_overwritten(tmp_path):
    root = _install_dir(tmp_path)
    (root / ".git").mkdir()
    up = _updater(root, _routes())
    with pytest.raises(UpdateError, match="git pull"):
        up.install(up.check(), say=lambda m: None)
    assert "0.1.0" in (root / "assistant/__init__.py").read_text(encoding="utf-8")


def test_unsafe_zip_is_rejected(tmp_path):
    root = _install_dir(tmp_path)
    routes = _routes()
    routes[ZIP] = make_zip({**REMOTE_FILES, "../../boese.txt": "x"})
    up = _updater(root, routes)
    with pytest.raises(UpdateError, match="Unsicher"):
        up.install(up.check(), say=lambda m: None)
    assert not (tmp_path / "boese.txt").exists()
    assert "0.1.0" in (root / "assistant/__init__.py").read_text(encoding="utf-8")
    assert up.backups() == []


def test_download_not_newer_changes_nothing(tmp_path):
    root = _install_dir(tmp_path)
    routes = _routes()
    routes[ZIP] = make_zip({**REMOTE_FILES, "assistant/__init__.py": _init("0.1.0")})
    up = _updater(root, routes)
    with pytest.raises(UpdateError, match="nicht neuer"):
        up.install(up.check(), say=lambda m: None)
    assert (root / "assistant/alt.py").exists() and up.backups() == []


def test_old_versions_are_pruned(tmp_path):
    root = _install_dir(tmp_path)
    up = _updater(root, _routes(), alte_versionen_behalten=2)
    for i in range(4):
        (root / "versionen" / f"0.0.{i}_2026-01-0{i + 1}_120000").mkdir(parents=True)
    up._prune()
    assert [b.name for b in up.backups()] == ["0.0.3_2026-01-04_120000", "0.0.2_2026-01-03_120000"]


def test_restore_brings_back_old_version_and_pauses(tmp_path):
    root = _install_dir(tmp_path)
    up = _updater(root, _routes())
    up.install(up.check(), say=lambda m: None)
    up.current = "0.2.0"
    message = up.restore("1", say=lambda m: None)
    assert "0.1.0" in message
    assert "0.1.0" in (root / "assistant/__init__.py").read_text(encoding="utf-8")
    assert (root / "assistant/alt.py").exists() and not (root / "assistant/neu.py").exists()
    assert (root / ".env").read_text(encoding="utf-8") == "DEEPSEEK_API_KEY=sk-geheim\n"
    assert up.paused  # sonst wuerde sofort wieder aktualisiert
    assert {b.version for b in up.backups()} == {"0.1.0", "0.2.0"}  # 0.2.0 ist jetzt gesichert


def test_restore_unknown_version(tmp_path):
    up = _updater(_install_dir(tmp_path), {})
    with pytest.raises(UpdateError, match="Keine gesicherte Version"):
        up.restore("7")


def test_due_once_per_day(tmp_path):
    root = _install_dir(tmp_path)
    now = datetime(2026, 11, 7, 12, 0, 0)
    up = _updater(root, _routes())
    up.now = lambda: now
    assert up.due()
    up.check()
    assert not up.due()
    up.now = lambda: now + timedelta(hours=25)
    assert up.due()
    off = _updater(root, _routes(), modus="aus")
    assert not off.due() and not off.enabled


def test_exe_update_from_release(tmp_path):
    root = tmp_path / "KI"
    root.mkdir()
    exe = root / "KI.exe"
    exe.write_bytes(b"MZ-alt")
    release = {
        "tag_name": "v0.3.0",
        "body": "## 0.3.0\n- Neue KI.exe",
        "assets": [{"name": "KI.exe", "browser_download_url": "https://example/KI.exe"}],
    }
    new_exe = b"MZ" + b"\0" * 1_200_000
    routes = {
        f"https://api.github.com/repos/{REPO}/releases/latest": json.dumps(release),
        "https://example/KI.exe": new_exe,
    }
    up = Updater(UpdateSettings(), root, fetch=FakeFetch(routes), current_version="0.2.0",
                 frozen=True, exe_path=exe)
    info = up.check()
    assert info.kind == "exe" and info.new == "0.3.0" and "Neue KI.exe" in info.notes
    up.install(info, say=lambda m: None)
    assert exe.read_bytes() == new_exe
    backups = up.backups()
    assert len(backups) == 1 and (backups[0].path / "KI.exe").read_bytes() == b"MZ-alt"


def test_exe_rejects_invalid_download(tmp_path):
    root = tmp_path / "KI"
    root.mkdir()
    exe = root / "KI.exe"
    exe.write_bytes(b"MZ-alt")
    release = {"tag_name": "v0.3.0", "assets": [{"name": "KI.exe", "browser_download_url": "u"}]}
    routes = {f"https://api.github.com/repos/{REPO}/releases/latest": json.dumps(release), "u": b"<html>"}
    up = Updater(UpdateSettings(), root, fetch=FakeFetch(routes), current_version="0.2.0",
                 frozen=True, exe_path=exe)
    with pytest.raises(UpdateError):
        up.install(up.check(), say=lambda m: None)
    assert exe.read_bytes() == b"MZ-alt"


def test_release_notes_script():
    import subprocess
    import sys

    root = Path(__file__).resolve().parent.parent
    ver = subprocess.run([sys.executable, str(root / "packaging/release_notes.py"), "--version"],
                         capture_output=True, text=True, check=True).stdout.strip()
    from assistant import __version__

    assert ver == __version__
    notes = subprocess.run([sys.executable, str(root / "packaging/release_notes.py")],
                           capture_output=True, text=True, check=True, encoding="utf-8").stdout
    assert notes.startswith(f"## {ver}")


def test_failed_replace_rolls_back(tmp_path, monkeypatch):
    import shutil as shutil_mod

    root = _install_dir(tmp_path)
    up = _updater(root, _routes())
    real_copy = shutil_mod.copy2
    state = {"n": 0}

    def flaky_copy(src, dst, *a, **kw):
        # Beim Einspielen der NEUEN Dateien bricht es nach zwei Dateien ab (z.B. Virenscanner).
        if "versionen" not in str(dst) and "neu" in str(src):
            state["n"] += 1
            if state["n"] == 3:
                raise PermissionError("Datei gesperrt")
        return real_copy(src, dst, *a, **kw)

    monkeypatch.setattr("assistant.updater.shutil.copy2", flaky_copy)
    with pytest.raises(UpdateError, match="unveraendert"):
        up.install(up.check(), say=lambda m: None)
    assert "0.1.0" in (root / "assistant/__init__.py").read_text(encoding="utf-8")
    assert (root / "run_ki.py").read_text(encoding="utf-8") == "print('v1')\n"
    assert (root / "assistant/alt.py").exists() and not (root / "assistant/neu.py").exists()
    assert up.backups() == []


def test_exe_swap_rolls_back_when_new_exe_is_locked(tmp_path, monkeypatch):
    import os as os_mod

    root = tmp_path / "KI"
    root.mkdir()
    exe = root / "KI.exe"
    exe.write_bytes(b"MZ-alt")
    release = {"tag_name": "v0.3.0", "assets": [{"name": "KI.exe", "browser_download_url": "u"}]}
    routes = {f"https://api.github.com/repos/{REPO}/releases/latest": json.dumps(release),
              "u": b"MZ" + b"\0" * 1_200_000}
    up = Updater(UpdateSettings(), root, fetch=FakeFetch(routes), current_version="0.2.0",
                 frozen=True, exe_path=exe)
    real_replace = os_mod.replace

    def locked(src, dst):
        if str(src).endswith(".neu"):
            raise PermissionError("Virenscanner prueft noch")
        return real_replace(src, dst)

    monkeypatch.setattr("assistant.updater.os.replace", locked)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(UpdateError, match="alte Version bleibt"):
        up.install(up.check(), say=lambda m: None)
    assert exe.read_bytes() == b"MZ-alt"  # die laufende KI.exe ist noch da


def test_exe_notes_cover_skipped_versions(tmp_path):
    root = tmp_path / "KI"
    root.mkdir()
    exe = root / "KI.exe"
    exe.write_bytes(b"MZ")
    release = {"tag_name": "v0.3.0", "body": "nur 0.3.0",
               "assets": [{"name": "KI.exe", "browser_download_url": "u"}]}
    routes = {f"https://api.github.com/repos/{REPO}/releases/latest": json.dumps(release),
              f"https://raw.githubusercontent.com/{REPO}/v0.3.0/CHANGELOG.md": CHANGELOG}
    up = Updater(UpdateSettings(), root, fetch=FakeFetch(routes), current_version="0.1.0",
                 frozen=True, exe_path=exe)
    notes = up.check().notes
    assert "Noch neuer" in notes and "F2 zum Sprechen" in notes


def test_restart_exe_resets_pyinstaller_environment(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "C:/Temp/_MEI123")
    monkeypatch.setattr("assistant.updater.subprocess.Popen", lambda cmd, **kw: seen.update(kw))
    Updater(UpdateSettings(), tmp_path, frozen=True, exe_path=tmp_path / "KI.exe").restart_exe()
    assert seen["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert "_PYI_APPLICATION_HOME_DIR" not in seen["env"]


def test_git_checkout_offer_is_only_a_hint(tmp_path, capsys):
    from assistant.ui.cli import CLI
    from assistant.updater import UpdateInfo

    root = _install_dir(tmp_path)
    (root / ".git").mkdir()
    cli = CLI.__new__(CLI)
    cli.updater = _updater(root, _routes())
    cli.brain = None  # wuerde bei einem KI-Aufruf sofort scheitern
    info = UpdateInfo("0.1.0", "0.2.0", "neu", ZIP, "quelle")
    assert cli._offer_update(info, ask=False) is False
    assert "git pull" in capsys.readouterr().out


def test_executable_bit_survives_update(tmp_path):
    import os
    import stat

    root = _install_dir(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for rel, content in REMOTE_FILES.items():
            z.writestr(f"top/{rel}", content)
        info = zipfile.ZipInfo("top/start.sh")
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o755) << 16
        z.writestr(info, "#!/bin/bash\n")
    routes = _routes()
    routes[ZIP] = buf.getvalue()
    up = _updater(root, routes)
    up.install(up.check(), say=lambda m: None)
    assert os.stat(root / "start.sh").st_mode & 0o111
