"""Neue KI.exe / KI-App.exe einsetzen, ohne dass Verknuepfungen kaputtgehen.

Warum so umstaendlich? Windows merkt sich bei einer Verknuepfung (Desktop, Taskleiste)
nicht nur den Pfad, sondern auch, WELCHE Datei gemeint ist. Wurde die laufende .exe frueher
beim Update in den Ordner versionen/ verschoben, folgte die Verknuepfung ihr dorthin - und
startete danach die alte Version aus der Sicherung.

Deshalb jetzt:
  1. Die neue Version liegt als "<name>.neu" neben der alten, die alte ist als KOPIE gesichert.
  2. Beim Neustart startet ein kleiner Helfer (eine Kopie der laufenden .exe im Temp-Ordner).
  3. Der Helfer wartet, bis die alte KI zu ist, und schreibt den neuen Inhalt in DIESELBE
     Datei. Sie bleibt also fuer Windows dieselbe - Verknuepfungen bleiben gueltig.
  4. Dann startet er die neue Version und beendet sich.

Ausserdem repariert die neue Version beim ersten Start Verknuepfungen, die durch das alte
Verfahren schon in den Sicherungsordner zeigen.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HELPER_FLAG = "--update-einspielen"
HELPER_PREFIX = "ki-update-"
BACKUP_DIR = "versionen"


# -- Helfer starten (in der alten, noch laufenden KI) ----------------------------
def _clean_env() -> dict:
    # Sonst haelt PyInstaller (>= 6.9) den neuen Prozess fuer einen Helfer der alten .exe.
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI_")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def start_helper(exe: Path, new_file: Path, extra_args: list[str] | None = None) -> Path:
    """Kopiert die laufende .exe als Helfer in den Temp-Ordner und startet ihn (ohne Fenster)."""
    helper = Path(tempfile.gettempdir()) / f"{HELPER_PREFIX}{os.getpid()}.exe"
    shutil.copyfile(exe, helper)
    flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    cmd = [str(helper), HELPER_FLAG, str(new_file), str(exe), str(os.getpid()), *(extra_args or [])]
    subprocess.Popen(cmd, cwd=str(exe.parent), env=_clean_env(), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags if sys.platform == "win32" else 0,
                     start_new_session=sys.platform != "win32")
    return helper


# -- Im Helfer-Prozess ------------------------------------------------------------
def run_helper(argv: list[str]) -> int:
    """<neue Datei> <Ziel-.exe> <PID der alten KI> [Startargumente ...]"""
    if len(argv) < 3:
        return 2
    new_file, target, pid, extra = Path(argv[0]), Path(argv[1]), argv[2], argv[3:]
    log = _helper_log(target.parent)
    try:
        wait_for_exit(int(pid), timeout=90)
    except ValueError:
        pass
    ok = overwrite_in_place(new_file, target)
    log.info("Update eingespielt: %s" if ok else "Update NICHT eingespielt (alte Version bleibt): %s", target)
    if ok:
        try:
            new_file.unlink()
        except OSError:
            pass
    env = _clean_env()
    env["KI_NEUSTART_VON"] = str(os.getpid())
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)  # KI.exe (Terminal) bekommt ihr Fenster
    try:
        subprocess.Popen([str(target), *extra], cwd=str(target.parent), env=env,
                         creationflags=flags if sys.platform == "win32" else 0)
    except OSError as exc:
        log.warning("Neustart ging nicht: %s", exc)
        return 1
    return 0 if ok else 1


def overwrite_in_place(src: Path, dst: Path, attempts: int = 60, delay: float = 0.5) -> bool:
    """Schreibt den Inhalt von src in die BESTEHENDE Datei dst (gleiche Datei, neuer Inhalt).
    Gesperrt (Virenscanner, alte KI noch nicht ganz zu): ein paar Mal versuchen. Geht beim
    Schreiben etwas schief, kommt der alte Inhalt zurueck."""
    try:
        data = src.read_bytes()
        original = dst.read_bytes()
    except OSError:
        return False
    if not data.startswith(b"MZ") and sys.platform == "win32":
        return False
    for attempt in range(attempts):
        try:
            fh = open(dst, "r+b")  # noqa: SIM115 - Fehler beim Oeffnen = noch gesperrt
        except PermissionError:
            time.sleep(delay)
            continue
        except OSError:
            return False
        try:
            with fh:
                fh.seek(0)
                fh.write(data)
                fh.truncate()
                fh.flush()
                os.fsync(fh.fileno())
            return dst.read_bytes() == data
        except OSError:
            _restore(dst, original)
            return False
    return False


def _restore(dst: Path, original: bytes) -> None:
    try:
        with open(dst, "r+b") as fh:
            fh.seek(0)
            fh.write(original)
            fh.truncate()
    except OSError:
        pass


def wait_for_exit(pid: int, timeout: float = 60) -> None:
    """Wartet, bis der Prozess pid beendet ist (hoechstens timeout Sekunden)."""
    if pid <= 0 or pid == os.getpid():
        return
    if sys.platform == "win32":
        try:
            import ctypes

            kernel = ctypes.windll.kernel32
            handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if handle:
                kernel.WaitForSingleObject(handle, int(timeout * 1000))
                kernel.CloseHandle(handle)
            return
        except Exception:  # noqa: BLE001
            pass
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.2)


def _helper_log(folder: Path) -> logging.Logger:
    log = logging.getLogger("ki.update-helfer")
    if not log.handlers:
        try:
            (folder / "logs").mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(folder / "logs" / "update.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            log.addHandler(handler)
            log.setLevel(logging.INFO)
        except OSError:
            log.addHandler(logging.NullHandler())
    return log


# -- Nach dem Start der neuen Version -------------------------------------------------
def after_start(exe: Path, root: Path, version: str, force: bool = False, background: bool = True) -> bool:
    """Aufraeumen und - beim ersten Start einer neuen Version - Verknuepfungen reparieren
    (im Hintergrund, damit der Start nicht wartet). True = es wird repariert."""
    leftovers = list(Path(tempfile.gettempdir()).glob(f"{HELPER_PREFIX}*.exe"))
    leftovers.append(Path(exe).with_name(Path(exe).name + ".alt"))  # Notfall-Weg beim letzten Update
    for old in leftovers:
        try:
            old.unlink()  # (laufende lassen sich nicht loeschen - dann eben beim naechsten Mal)
        except OSError:
            pass
    state_path = Path(root) / "data" / "update.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if not force and state.get("gestartet") == version:
        return False
    state["gestartet"] = version
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass

    def repair() -> None:
        try:
            repair_shortcuts(Path(exe), Path(root))
        except Exception as exc:  # noqa: BLE001 - nie den Start stoeren
            logging.getLogger("ki").info("Verknuepfungen pruefen: %s", exc)

    if background:
        import threading

        threading.Thread(target=repair, name="verknuepfungen", daemon=True).start()
    else:
        repair()
    return True


def _ps_quote(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def repair_shortcuts(exe: Path, root: Path) -> int:
    """Verknuepfungen (Desktop, Startmenue, Taskleiste), die auf eine gesicherte alte Version
    in versionen/ zeigen, wieder auf die aktuelle .exe richten; solche, die schon auf die
    .exe zeigen, auffrischen. Gibt die Zahl der reparierten zurueck (nur Windows)."""
    if sys.platform != "win32":
        return 0
    backup = str(Path(root) / BACKUP_DIR) + "\\"
    script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        f"$exe = {_ps_quote(exe)}; $bak = {_ps_quote(backup)}; $name = {_ps_quote(Path(exe).name)}; "
        "$s = New-Object -ComObject WScript.Shell; "
        "$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('CommonDesktopDirectory'), "
        "[Environment]::GetFolderPath('Programs'), "
        "(Join-Path $env:APPDATA 'Microsoft\\Internet Explorer\\Quick Launch\\User Pinned\\TaskBar'), "
        "(Join-Path $env:APPDATA 'Microsoft\\Internet Explorer\\Quick Launch')); "
        "$n = 0; "
        "foreach ($d in $dirs) { if ($d -and (Test-Path -LiteralPath $d)) { "
        "Get-ChildItem -LiteralPath $d -Filter *.lnk -Recurse | ForEach-Object { "
        "$l = $s.CreateShortcut($_.FullName); $t = [string]$l.TargetPath; "
        "$old = $t.StartsWith($bak, [StringComparison]::OrdinalIgnoreCase) -and "
        "([IO.Path]::GetFileName($t) -ieq $name); "
        "if ($old -or ($t -ieq $exe)) { $l.TargetPath = $exe; "
        "$l.WorkingDirectory = [IO.Path]::GetDirectoryName($exe); $l.Save(); if ($old) { $n++ } } } } }; "
        "Write-Output $n"
    )
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        return int((proc.stdout or "0").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return 0


def running_from_backup(exe: Path) -> Path | None:
    """Laeuft gerade eine gesicherte alte Version aus versionen/<...>/? Dann: Pfad der aktuellen."""
    exe = Path(exe)
    folder = exe.parent.parent
    if folder.name.lower() != BACKUP_DIR:
        return None
    current = folder.parent / exe.name
    return current if current.is_file() and current.resolve() != exe.resolve() else None
