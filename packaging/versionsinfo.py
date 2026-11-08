"""Versionsangaben fuer die .exe (Rechtsklick -> Eigenschaften -> Details zeigt dann die
Dateiversion, z.B. 0.6.1). Wird von ki.spec beim Bauen benutzt."""
from __future__ import annotations

import re
from pathlib import Path


def read_version(project_root: Path) -> str:
    text = (Path(project_root) / "assistant" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def version_tuple(version: str) -> tuple[int, int, int, int]:
    numbers = [int(n) for n in re.findall(r"\d+", version)[:4]]
    return tuple((numbers + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def version_info(project_root: Path, exe_name: str, description: str):
    """VSVersionInfo fuer PyInstaller (EXE(version=...))."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    version = read_version(project_root)
    numbers = version_tuple(version)
    strings = [
        StringStruct("CompanyName", "Selbst-lernende KI"),
        StringStruct("FileDescription", f"{description} {version}"),
        StringStruct("FileVersion", version),
        StringStruct("InternalName", exe_name),
        StringStruct("OriginalFilename", f"{exe_name}.exe"),
        StringStruct("ProductName", "Selbst-lernende KI (Nova)"),
        StringStruct("ProductVersion", version),
    ]
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([StringTable("040704B0", strings)]),  # Deutsch, Unicode
            VarFileInfo([VarStruct("Translation", [0x0407, 1200])]),
        ],
    )
