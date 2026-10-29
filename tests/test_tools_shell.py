import sys
import time

from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import build_registry, ToolContext
from assistant.tools import shell

GERMAN_WINDOWS = (["cp850"], "cp1252")


def _ctx(tmp_path):
    pm = PermissionManager(
        PermissionSettings(safe_mode=False, auto_confirm=True), tmp_path, confirm_fn=lambda m, r: True
    )
    return ToolContext(permissions=pm, memory=None)


def _py(code):
    return f'"{sys.executable}" -c "{code}"'


def test_decode_oem_codepage(monkeypatch):
    # "Verzeichnis für" in cp850, wie es cmd.exe auf deutschem Windows ausgibt.
    monkeypatch.setattr(shell, "_windows_codepages", lambda: GERMAN_WINDOWS)
    assert shell._decode("Verzeichnis für".encode("cp850")) == "Verzeichnis für"
    assert shell._decode("Datenträger in Laufwerk C:".encode("cp850")) == "Datenträger in Laufwerk C:"
    assert shell._decode("Größe Übung".encode("cp850")) == "Größe Übung"


def test_decode_ansi_output(monkeypatch):
    # Programme, die cp1252 in die Pipe schreiben (z.B. Python ohne UTF-8, Excel-CSV).
    monkeypatch.setattr(shell, "_windows_codepages", lambda: GERMAN_WINDOWS)
    assert shell._decode("Größe für Übung".encode("cp1252")) == "Größe für Übung"


def test_decode_tree_box_drawing_stays_oem(monkeypatch):
    monkeypatch.setattr(shell, "_windows_codepages", lambda: GERMAN_WINDOWS)
    tree = "C:.\r\n├───Bilder\r\n│   └───Urlaub\r\n"
    assert shell._decode(tree.encode("cp850")) == tree


def test_decode_utf16(monkeypatch):
    monkeypatch.setattr(shell, "_windows_codepages", lambda: GERMAN_WINDOWS)
    assert shell._decode("NAME  STATE\r\nUbuntu Prüfung\r\n".encode("utf-16-le")) == "NAME  STATE\r\nUbuntu Prüfung\r\n"
    assert shell._decode("﻿Hallo".encode("utf-16-le")) == "Hallo"


def test_decode_prefers_utf8(monkeypatch):
    monkeypatch.setattr(shell, "_windows_codepages", lambda: GERMAN_WINDOWS)
    assert shell._decode("Grüße".encode("utf-8")) == "Grüße"


def test_decode_never_raises(monkeypatch):
    monkeypatch.setattr(shell, "_windows_codepages", lambda: ([], None))
    assert shell._decode(b"f\x81r") == "f�r"
    assert shell._decode(None) == ""


def test_shell_output_with_invalid_bytes_is_returned(tmp_path):
    # Frueher: UnicodeDecodeError im Lese-Thread und die Ausgabe ging verloren.
    befehl = _py("import sys; sys.stdout.buffer.write(b'f\\x81r OK')")
    out, err = build_registry().execute(_ctx(tmp_path), "shell_befehl", {"befehl": befehl})
    assert not err
    assert "Rueckgabecode: 0" in out
    assert "OK" in out


def test_python_children_print_utf8(tmp_path):
    befehl = _py("print('Grüße aus München')")
    out, _ = build_registry().execute(_ctx(tmp_path), "shell_befehl", {"befehl": befehl})
    assert "Grüße aus München" in out


def test_background_program_does_not_block(tmp_path):
    # Frueher: ein im Hintergrund gestartetes Programm hielt die Pipe offen -> Haenger.
    befehl = _py("import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)']); print('gestartet')")
    start = time.monotonic()
    out, _ = build_registry().execute(_ctx(tmp_path), "shell_befehl", {"befehl": befehl})
    assert time.monotonic() - start < 10
    assert "gestartet" in out and "Rueckgabecode: 0" in out


def test_timeout_kills_tree_and_keeps_partial_output(tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "_TIMEOUT", 1)
    befehl = _py("import time; print('teil-ausgabe', flush=True); time.sleep(30)")
    start = time.monotonic()
    out, _ = build_registry().execute(_ctx(tmp_path), "shell_befehl", {"befehl": befehl})
    assert time.monotonic() - start < 15
    assert "Abgebrochen" in out and "teil-ausgabe" in out
