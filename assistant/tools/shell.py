"""Shell-Werkzeug: fuehrt Systembefehle aus - streng abgesichert.

Laeuft nur, wenn Safe Mode aus ist. Jeder Befehl geht durch die Verbots- und
Erlaubnisliste des PermissionManagers und wird (ausser bei auto_confirm oder
Allowlist) bestaetigt. Mit Timeout, damit nichts haengen bleibt.
"""
from __future__ import annotations

import subprocess

from .base import Tool, ToolContext

_TIMEOUT = 120
_MAX_OUTPUT = 20_000


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
                text=True,
                timeout=_TIMEOUT,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return f"Abgebrochen: Befehl lief laenger als {_TIMEOUT} Sekunden."

        out = (proc.stdout or "")[:_MAX_OUTPUT]
        err = (proc.stderr or "")[:_MAX_OUTPUT]
        parts = [f"Rueckgabecode: {proc.returncode}"]
        if out:
            parts.append(f"Ausgabe:\n{out}")
        if err:
            parts.append(f"Fehlerausgabe:\n{err}")
        return "\n".join(parts)


def register(registry) -> None:
    registry.register(ShellTool())
