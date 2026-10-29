import sys

from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import build_registry, ToolContext
from assistant.tools import shell


def _ctx(tmp_path):
    pm = PermissionManager(
        PermissionSettings(safe_mode=False, auto_confirm=True), tmp_path, confirm_fn=lambda m, r: True
    )
    return ToolContext(permissions=pm, memory=None)


def test_decode_oem_codepage(monkeypatch):
    # "Verzeichnis für" in cp850, wie es cmd.exe auf deutschem Windows ausgibt.
    monkeypatch.setattr(shell, "_windows_codepages", lambda: ["cp850", "cp1252"])
    assert shell._decode("Verzeichnis für".encode("cp850")) == "Verzeichnis für"


def test_decode_prefers_utf8(monkeypatch):
    monkeypatch.setattr(shell, "_windows_codepages", lambda: ["cp850", "cp1252"])
    assert shell._decode("Grüße".encode("utf-8")) == "Grüße"


def test_decode_never_raises(monkeypatch):
    monkeypatch.setattr(shell, "_windows_codepages", lambda: [])
    assert shell._decode(b"f\x81r") == "f�r"
    assert shell._decode(None) == ""


def test_shell_output_with_invalid_bytes_is_returned(tmp_path):
    # Frueher: UnicodeDecodeError im Lese-Thread und die Ausgabe ging verloren.
    befehl = f'"{sys.executable}" -c "import sys; sys.stdout.buffer.write(b\'f\\x81r OK\')"'
    out, err = build_registry().execute(_ctx(tmp_path), "shell_befehl", {"befehl": befehl})
    assert not err
    assert "Rueckgabecode: 0" in out
    assert "OK" in out
