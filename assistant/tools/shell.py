"""Shell-Werkzeug: fuehrt Systembefehle aus - streng abgesichert.

Laeuft nur, wenn Safe Mode aus ist. Jeder Befehl geht durch die Verbots- und
Erlaubnisliste des PermissionManagers und wird (ausser bei auto_confirm oder
Allowlist) bestaetigt. Mit Timeout, damit nichts haengen bleibt.

Die Ausgabe wird als Bytes gelesen und selbst dekodiert: Windows-Konsolenbefehle
(dir, ipconfig, ...) schreiben in der OEM-Codepage (z.B. cp850, dort ist 0x81 ein
"ue"), nicht in der ANSI-Codepage cp1252, die Python sonst annehmen wuerde.
"""
from __future__ import annotations

import subprocess
import sys

from .base import Tool, ToolContext

_TIMEOUT = 120
_MAX_OUTPUT = 20_000


def _windows_codepages() -> list[str]:
    """OEM- und ANSI-Codepage des Systems (z.B. ['cp850', 'cp1252'])."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        return [f"cp{kernel32.GetOEMCP()}", f"cp{kernel32.GetACP()}"]
    except Exception:  # noqa: BLE001
        return ["cp850", "cp1252"]


def _decode(data: bytes | None) -> str:
    """Dekodiert Shell-Ausgabe robust - stuerzt nie wegen fremder Zeichen ab."""
    if not data:
        return ""
    for encoding in ("utf-8", *_windows_codepages()):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


class ShellTool(Tool):
    name = "shell_befehl"
    description = (
        "Fuehrt einen Befehl in der System-Shell aus und gibt Ausgabe + Rueckgabecode "
        "zurueck. Nutze dies fuer Programme starten, Dinge herunterladen, installieren usw. "
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

        try:
            proc = subprocess.run(
                befehl,
                shell=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,  # Befehle, die auf Eingabe warten, haengen nicht
                timeout=_TIMEOUT,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return f"Abgebrochen: Befehl lief laenger als {_TIMEOUT} Sekunden."

        out = _decode(proc.stdout)[:_MAX_OUTPUT]
        err = _decode(proc.stderr)[:_MAX_OUTPUT]
        parts = [f"Rueckgabecode: {proc.returncode}"]
        if out:
            parts.append(f"Ausgabe:\n{out}")
        if err:
            parts.append(f"Fehlerausgabe:\n{err}")
        return "\n".join(parts)


def register(registry) -> None:
    registry.register(ShellTool())
