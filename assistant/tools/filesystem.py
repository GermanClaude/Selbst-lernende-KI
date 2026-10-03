"""Datei-Werkzeuge: lesen, schreiben, bearbeiten, auflisten, loeschen.

Alle Pfade laufen durch die Sandbox-Pruefung des PermissionManagers.
Loeschen verschiebt standardmaessig in einen Quarantaene-Ordner ("Papierkorb"),
damit nichts unwiederbringlich verloren geht.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from ..permissions import Risk
from .base import Tool, ToolContext

_MAX_READ_BYTES = 200_000


class ReadFileTool(Tool):
    name = "datei_lesen"
    description = "Liest den Textinhalt einer Datei im Arbeitsordner und gibt ihn zurueck."
    input_schema = {
        "type": "object",
        "properties": {"pfad": {"type": "string", "description": "Pfad zur Datei"}},
        "required": ["pfad"],
    }

    def run(self, ctx: ToolContext, pfad: str) -> str:
        path = ctx.permissions.resolve_path(pfad, must_exist=True)
        ctx.permissions.require(Risk.SAFE, f"Datei lesen: {path}")
        data = path.read_bytes()[:_MAX_READ_BYTES]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return f"(Binaerdatei, {path.stat().st_size} Bytes - kann nicht als Text angezeigt werden.)"
        suffix = "\n…(gekuerzt)" if path.stat().st_size > _MAX_READ_BYTES else ""
        return f"Inhalt von {path.name}:\n{text}{suffix}"


class WriteFileTool(Tool):
    name = "datei_schreiben"
    description = (
        "Schreibt Text in eine Datei (ueberschreibt vorhandenen Inhalt). "
        "Legt fehlende Ordner an. Nur im Arbeitsordner, ausser voller Zugriff ist erlaubt."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pfad": {"type": "string"},
            "inhalt": {"type": "string"},
        },
        "required": ["pfad", "inhalt"],
    }

    def run(self, ctx: ToolContext, pfad: str, inhalt: str) -> str:
        path = ctx.permissions.resolve_path(pfad)
        existed = path.exists()
        ctx.permissions.require(
            Risk.MODERATE,
            f"{'Ueberschreiben' if existed else 'Neu anlegen'}: {path}",
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(inhalt, encoding="utf-8")
        return f"{'Aktualisiert' if existed else 'Erstellt'}: {path} ({len(inhalt)} Zeichen)"


class EditFileTool(Tool):
    name = "datei_bearbeiten"
    description = (
        "Ersetzt in einer Datei einen exakten Textabschnitt durch einen neuen. "
        "Der zu ersetzende Text muss genau einmal vorkommen."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pfad": {"type": "string"},
            "suchen": {"type": "string", "description": "exakt vorhandener Text"},
            "ersetzen": {"type": "string", "description": "neuer Text"},
        },
        "required": ["pfad", "suchen", "ersetzen"],
    }

    def run(self, ctx: ToolContext, pfad: str, suchen: str, ersetzen: str) -> str:
        path = ctx.permissions.resolve_path(pfad, must_exist=True)
        ctx.permissions.require(Risk.MODERATE, f"Bearbeiten: {path}")
        text = path.read_text(encoding="utf-8")
        count = text.count(suchen)
        if count == 0:
            return "Der zu ersetzende Text wurde nicht gefunden - nichts geaendert."
        if count > 1:
            return f"Der Text kommt {count}-mal vor; er muss eindeutig sein. Nichts geaendert."
        path.write_text(text.replace(suchen, ersetzen, 1), encoding="utf-8")
        return f"Geaendert: {path}"


class ListDirTool(Tool):
    name = "ordner_auflisten"
    description = "Listet Dateien und Unterordner eines Verzeichnisses auf."
    input_schema = {
        "type": "object",
        "properties": {"pfad": {"type": "string", "description": "Ordnerpfad (Standard: Arbeitsordner)"}},
        "required": [],
    }

    def run(self, ctx: ToolContext, pfad: str = ".") -> str:
        path = ctx.permissions.resolve_path(pfad, must_exist=True)
        ctx.permissions.require(Risk.SAFE, f"Auflisten: {path}")
        if not path.is_dir():
            return f"{path} ist kein Ordner."
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        if not entries:
            return f"{path} ist leer."
        lines = [f"Inhalt von {path}:"]
        for e in entries:
            marker = "/" if e.is_dir() else ""
            size = f" ({e.stat().st_size} B)" if e.is_file() else ""
            lines.append(f"  {e.name}{marker}{size}")
        return "\n".join(lines)


class DeleteFileTool(Tool):
    name = "datei_loeschen"
    description = (
        "Loescht eine Datei oder einen Ordner. Standardmaessig wird in die "
        "Quarantaene verschoben (wiederherstellbar), nicht endgueltig vernichtet."
    )
    input_schema = {
        "type": "object",
        "properties": {"pfad": {"type": "string"}},
        "required": ["pfad"],
    }

    def run(self, ctx: ToolContext, pfad: str) -> str:
        path = ctx.permissions.resolve_path(pfad, must_exist=True)
        ctx.permissions.require(Risk.DANGEROUS, f"Loeschen: {path}")
        if ctx.permissions.settings.use_quarantine:
            quarantine = ctx.permissions.workspace_root / ".papierkorb"
            quarantine.mkdir(parents=True, exist_ok=True)
            target = quarantine / f"{int(time.time())}_{path.name}"
            shutil.move(str(path), str(target))
            return f"In Quarantaene verschoben (wiederherstellbar): {target}"
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return f"Endgueltig geloescht: {path}"


def register(registry) -> None:
    for tool in (ReadFileTool(), WriteFileTool(), EditFileTool(), ListDirTool(), DeleteFileTool()):
        registry.register(tool)
