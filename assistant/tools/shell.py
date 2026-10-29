"""Shell-Werkzeug: fuehrt Systembefehle aus - streng abgesichert.

Laeuft nur, wenn Safe Mode aus ist. Jeder Befehl geht durch die Verbots- und
Erlaubnisliste des PermissionManagers und wird (ausser bei auto_confirm oder
Allowlist) bestaetigt. Mit Timeout, damit nichts haengen bleibt.

Ausgabe landet in temporaeren Dateien statt in Pipes: Programme, die der Befehl
im Hintergrund startet (z.B. 'start notepad', ein Server), erben sonst die Pipe
und das Werkzeug wuerde warten, bis sie beendet sind - also ewig. Beim Timeout
wird der ganze Prozessbaum beendet.

Die Ausgabe wird als Bytes gelesen und selbst dekodiert: Windows-Konsolenbefehle
(dir, ipconfig, ...) schreiben in der Konsolen-Codepage (z.B. cp850, dort ist 0x81
ein "ue"), manche Programme in der ANSI-Codepage cp1252, wsl.exe in UTF-16.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile

from .base import Tool, ToolContext

_TIMEOUT = 120
_MAX_OUTPUT = 20_000
_MAX_READ_BYTES = 1_000_000


def _windows_codepages() -> tuple[list[str], str | None]:
    """(Konsolen-Codepages, ANSI-Codepage), z.B. (['cp850'], 'cp1252')."""
    if sys.platform != "win32":
        return [], None
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        console = []
        for cp in (kernel32.GetConsoleOutputCP(), kernel32.GetOEMCP()):  # 0 = keine Konsole
            if cp and f"cp{cp}" not in console:
                console.append(f"cp{cp}")
        return console, f"cp{kernel32.GetACP()}"
    except Exception:  # noqa: BLE001
        return ["cp850"], "cp1252"


def _looks_like_utf16(data: bytes) -> bool:
    if data.startswith(b"\xff\xfe"):
        return True
    sample = data[:2000]
    odd = sample[1::2]
    return len(odd) >= 4 and odd.count(0) > 0.3 * len(odd)


def _letters(text: str) -> int:
    return sum(1 for c in text if ord(c) > 127 and c.isalpha())


def _has_box_drawing(text: str) -> bool:
    return any("─" <= c <= "╿" for c in text)


def _strict(data: bytes, encoding: str | None) -> str | None:
    if not encoding:
        return None
    try:
        return data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return None


def _decode(data: bytes | None) -> str:
    """Dekodiert Shell-Ausgabe robust - stuerzt nie wegen fremder Zeichen ab."""
    if not data:
        return ""
    if _looks_like_utf16(data):
        return data.decode("utf-16-le", errors="replace").lstrip("﻿")
    text = _strict(data, "utf-8")
    if text is not None:
        return text

    console, ansi = _windows_codepages()
    text = next((t for t in (_strict(data, cp) for cp in console) if t is not None), None)
    ansi_text = _strict(data, ansi)
    if text is None:
        if ansi_text is not None:
            return ansi_text
        return data.decode(console[0] if console else "utf-8", errors="replace")
    # Konsolen-Codepages wie cp850 akzeptieren jedes Byte - deshalb pruefen, ob die
    # ANSI-Lesart echte Buchstaben ergibt (z.B. "Groesse" aus einem Programm, das
    # cp1252 schreibt) statt Zeichensalat. Rahmenlinien (tree) sprechen fuer OEM.
    if ansi_text is not None and ansi_text != text and not _has_box_drawing(text):
        if _letters(ansi_text) > _letters(text):
            return ansi_text
    return text


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"  # Python-Skripte geben UTF-8 aus (eindeutig lesbar)
    env["WSL_UTF8"] = "1"  # wsl.exe ebenfalls UTF-8 statt UTF-16
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    """Beendet den Befehl samt allen Programmen, die er gestartet hat."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001 - Prozess evtl. schon weg
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass


def _read(fh) -> bytes:
    fh.seek(0)
    return fh.read(_MAX_READ_BYTES)


class ShellTool(Tool):
    name = "shell_befehl"
    description = (
        "Fuehrt einen Befehl in der System-Shell aus und gibt Ausgabe + Rueckgabecode "
        "zurueck. Nutze dies fuer Programme starten, Dinge herunterladen, installieren usw. "
        f"Befehle werden nach {_TIMEOUT} Sekunden abgebrochen; lang laufende Programme "
        "(Server, GUI-Programme) im Hintergrund starten (Windows: start \"\" programm). "
        "Es gibt keine Tastatureingabe: zum Warten unter Windows nicht 'timeout', sondern "
        "'ping -n 6 127.0.0.1 >nul' nutzen. "
        "Erfordert, dass der Nutzer gefaehrliche Aktionen freigeschaltet hat."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "befehl": {"type": "string", "description": "Der auszufuehrende Shell-Befehl"},
            "arbeitsverzeichnis": {
                "type": "string",
                "description": "Optionales Verzeichnis, in dem der Befehl laeuft",
            },
        },
        "required": ["befehl"],
    }

    def run(self, ctx: ToolContext, befehl: str, arbeitsverzeichnis: str = "") -> str:
        decision = ctx.permissions.check_shell(befehl)
        if not decision.allowed:
            return f"Nicht ausgefuehrt: {decision.reason}"

        cwd = None
        if arbeitsverzeichnis:
            cwd = str(ctx.permissions.resolve_path(arbeitsverzeichnis, must_exist=True))

        extra = {} if sys.platform == "win32" else {"start_new_session": True}
        timed_out = False
        with tempfile.TemporaryFile() as out_fh, tempfile.TemporaryFile() as err_fh:
            proc = subprocess.Popen(
                befehl,
                shell=True,
                stdin=subprocess.DEVNULL,  # Befehle, die auf Eingabe warten, haengen nicht
                stdout=out_fh,
                stderr=err_fh,
                cwd=cwd,
                env=_child_env(),
                **extra,
            )
            try:
                proc.wait(timeout=_TIMEOUT)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_tree(proc)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            out = _decode(_read(out_fh))[:_MAX_OUTPUT]
            err = _decode(_read(err_fh))[:_MAX_OUTPUT]

        if timed_out:
            parts = [f"Abgebrochen: Befehl lief laenger als {_TIMEOUT} Sekunden und wurde beendet."]
        else:
            parts = [f"Rueckgabecode: {proc.returncode}"]
        if out:
            parts.append(f"Ausgabe:\n{out}")
        if err:
            parts.append(f"Fehlerausgabe:\n{err}")
        return "\n".join(parts)


def register(registry) -> None:
    registry.register(ShellTool())
