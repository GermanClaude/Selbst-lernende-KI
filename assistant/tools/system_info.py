"""System-Info-Werkzeug: liefert harmlose Lesedaten ueber den Computer."""
from __future__ import annotations

import os
import platform
import shutil
from datetime import datetime

from ..permissions import Risk
from .base import Tool, ToolContext


class SystemInfoTool(Tool):
    name = "system_info"
    description = (
        "Gibt Basisinfos ueber den Computer zurueck: Betriebssystem, Benutzer, "
        "aktuelle Zeit, freier Speicherplatz und aktuelles Verzeichnis."
    )
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, ctx: ToolContext) -> str:
        ctx.permissions.require(Risk.SAFE, "System-Info lesen")
        usage = shutil.disk_usage(os.getcwd())
        gb = 1024 ** 3
        return (
            f"Betriebssystem: {platform.system()} {platform.release()}\n"
            f"Rechnername: {platform.node()}\n"
            f"Benutzer: {os.environ.get('USER') or os.environ.get('USERNAME', 'unbekannt')}\n"
            f"Python: {platform.python_version()}\n"
            f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Arbeitsordner der KI: {ctx.permissions.workspace_root}\n"
            f"Aktuelles Verzeichnis: {os.getcwd()}\n"
            f"Speicher frei/gesamt: {usage.free / gb:.1f} GB / {usage.total / gb:.1f} GB"
        )


def register(registry) -> None:
    registry.register(SystemInfoTool())
