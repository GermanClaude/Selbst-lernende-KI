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

_MAX_READ_BYTES = 5_000_000
_LINES_PER_READ = 400       # so viele Zeilen liefert datei_lesen hoechstens auf einmal
_CHARS_PER_READ = 40_000    # ... und hoechstens so viele Zeichen


class ReadFileTool(Tool):
    name = "datei_lesen"
    description = (
        "Liest den Textinhalt einer Datei. Lange Dateien kommen abschnittsweise "
        f"(hoechstens {_LINES_PER_READ} Zeilen); den Rest liest du mit 'ab_zeile'. "
        "Lies eine Datei nur einmal - du behaeltst den Inhalt."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pfad": {"type": "string", "description": "Pfad zur Datei"},
            "ab_zeile": {
                "type": "integer",
                "description": "Erste zu lesende Zeile (ab 1). Nur fuer lange Dateien noetig.",
            },
        },
        "required": ["pfad"],
    }
    # Liefert selbst passende Abschnitte -> der Sparmodus soll nicht zusaetzlich kuerzen.
    sparmodus_kuerzen = False

    def run(self, ctx: ToolContext, pfad: str, ab_zeile: int = 1) -> str:
        path = ctx.permissions.resolve_path(pfad, must_exist=True)
        ctx.permissions.require(Risk.SAFE, f"Datei lesen: {path}")
        data = path.read_bytes()[:_MAX_READ_BYTES]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return f"(Binaerdatei, {path.stat().st_size} Bytes - kann nicht als Text angezeigt werden.)"

        lines = text.splitlines(keepends=True)
        total = len(lines)
        start = max(1, int(ab_zeile or 1))
        if total and start > total:
            return f"{path.name} hat nur {total} Zeilen - ab Zeile {start} gibt es nichts mehr."

        chunk: list[str] = []
        size = 0
        cut_lines: list[str] = []
        for number, line in enumerate(lines[start - 1 : start - 1 + _LINES_PER_READ], start=start):
            if chunk and size + len(line) > _CHARS_PER_READ:
                break
            if len(line) > _CHARS_PER_READ:
                cut_lines.append(f"Zeile {number} hat {len(line)} Zeichen, gezeigt: {_CHARS_PER_READ}")
                line = line[:_CHARS_PER_READ] + "…\n"
            chunk.append(line)
            size += len(line)
        end = start - 1 + len(chunk)
        cut_note = f"\n…(Zeile gekuerzt: {'; '.join(cut_lines)})" if cut_lines else ""

        if start == 1 and end >= total and path.stat().st_size <= _MAX_READ_BYTES and not cut_lines:
            return f"Inhalt von {path.name}:\n{''.join(chunk)}"
        header = f"Inhalt von {path.name} (Zeilen {start}-{end} von {total}):\n"
        if end < total:
            footer = f"\n…(noch {total - end} Zeilen - weiterlesen mit ab_zeile={end + 1})"
        elif path.stat().st_size > _MAX_READ_BYTES:
            footer = "\n…(Datei ist zu gross, der Rest wird nicht angezeigt)"
        else:
            footer = "\n(Ende der Datei)"
        return header + "".join(chunk) + cut_note + footer


class WriteFileTool(Tool):
    name = "datei_schreiben"
    description = (
        "Schreibt Text in eine Datei (ueberschreibt vorhandenen Inhalt). "
        "Legt fehlende Ordner an. Nur im Arbeitsordner, ausser voller Zugriff ist erlaubt. "
        "Grosse Dateien in mehreren Teilen schreiben: erster Teil normal, weitere Teile "
        "mit anhaengen=true."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pfad": {"type": "string"},
            "inhalt": {"type": "string"},
            "anhaengen": {
                "type": "boolean",
                "description": "true = Text ans Dateiende anhaengen statt zu ueberschreiben",
            },
        },
        "required": ["pfad", "inhalt"],
    }

    def run(self, ctx: ToolContext, pfad: str, inhalt: str, anhaengen: bool = False) -> str:
        path = ctx.permissions.resolve_path(pfad)
        existed = path.exists()
        if anhaengen and existed:
            action = "Anhaengen an"
        else:
            action = "Ueberschreiben" if existed else "Neu anlegen"
        ctx.permissions.require(Risk.MODERATE, f"{action}: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if anhaengen:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(inhalt)
            return f"Angehaengt an {path} ({len(inhalt)} Zeichen, jetzt {path.stat().st_size} Bytes)"
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
