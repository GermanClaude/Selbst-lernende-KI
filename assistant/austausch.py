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


def start_helper(exe: Path, new_file: Path, extra_args: list[str] | None = None,
                 root: Path | None = None) -> Path:
    """Kopiert die laufende .exe als Helfer in den Temp-Ordner und startet ihn (ohne Fenster)."""
    helper = Path(tempfile.gettempdir()) / f"{HELPER_PREFIX}{os.getpid()}.exe"
    shutil.copyfile(exe, helper)
    flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    cmd = [str(helper), HELPER_FLAG, str(new_file), str(exe), str(os.getpid()), *(extra_args or [])]
    env = _clean_env()
    env["KI_UPDATE_ORDNER"] = str(root or exe.parent)  # dort steht data/update.json
    subprocess.Popen(cmd, cwd=str(exe.parent), env=env, stdin=subprocess.DEVNULL,
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
    root = Path(os.environ.get("KI_UPDATE_ORDNER") or target.parent)
    log = _helper_log(root)
    old_pid = int(pid) if pid.isdigit() else 0
    # Die alte KI schreibt beim Beenden noch eine Zusammenfassung (kann dauern) - geduldig warten.
    wait_for_exit(old_pid, timeout=600)
    how = "in dieselbe Datei" if overwrite_in_place(new_file, target) else ""
    if not how and replace_by_moving(new_file, target):
        how = "per Umbenennen (Ausweichweg)"  # z.B. Datei gesperrt oder schreibgeschuetzt
    if how:
        log.info("Update eingespielt (%s): %s", how, target)
        try:
            new_file.unlink()
        except OSError:
            pass
    else:
        log.warning("Update NICHT eingespielt - die bisherige Version bleibt: %s", target)
        record_failure(root, "Die neue Version konnte nicht eingesetzt werden (Datei gesperrt?). "
                             "Die bisherige laeuft weiter - versuch es spaeter mit /update noch einmal.")
        if _alive(old_pid):
            return 1  # die alte KI laeuft noch - kein zweites Fenster derselben Version
    env = _clean_env()
    env["KI_NEUSTART_VON"] = str(old_pid or os.getpid())
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)  # KI.exe (Terminal) bekommt ihr Fenster
    try:
        subprocess.Popen([str(target), *extra], cwd=str(target.parent), env=env,
                         creationflags=flags if sys.platform == "win32" else 0)
    except OSError as exc:
        log.warning("Neustart ging nicht: %s", exc)
        return 1
    return 0 if how else 1


def overwrite_in_place(src: Path, dst: Path, attempts: int = 60, delay: float = 0.5) -> bool:
    """Schreibt den Inhalt von src in die BESTEHENDE Datei dst (gleiche Datei, neuer Inhalt).
    Gesperrt (Virenscanner, alte KI noch nicht ganz zu): ein paar Mal versuchen. Geht beim
    Schreiben etwas schief, kommt der alte Inhalt zurueck."""
    import stat

    for attempt in range(attempts):
        try:
            data = src.read_bytes()
            original = dst.read_bytes()
            if not data.startswith(b"MZ") and sys.platform == "win32":
                return False
            if not os.access(dst, os.W_OK):
                os.chmod(dst, stat.S_IREAD | stat.S_IWRITE)  # Schreibschutz-Haken entfernen
            fh = open(dst, "r+b")  # noqa: SIM115 - Fehler beim Oeffnen = noch gesperrt
        except FileNotFoundError:
            return False
        except OSError:
            time.sleep(delay)
            continue
        try:
            with fh:
                fh.seek(0)
                fh.write(data)
                fh.truncate()
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            _restore(dst, original)
            time.sleep(delay)
            continue
        if dst.read_bytes() == data:
            return True
        _restore(dst, original)
    return False


def replace_by_moving(src: Path, dst: Path, attempts: int = 10, delay: float = 0.5) -> bool:
    """Ausweichweg: die (evtl. noch laufende) .exe beiseite schieben - das erlaubt Windows auch
    bei gesperrten Dateien - und die neue an ihren Platz setzen. Beim naechsten Start raeumt
    after_start die .alt weg und richtet Verknuepfungen wieder auf die .exe."""
    aside = dst.with_name(dst.name + ".alt")
    for attempt in range(attempts):
        try:
            if aside.exists():
                aside.unlink()
            os.replace(dst, aside)
        except FileNotFoundError:
            return False
        except OSError:
            time.sleep(delay)
            continue
        try:
            os.replace(src, dst)
            return True
        except OSError:
            try:
                os.replace(aside, dst)
            except OSError:
                pass
            time.sleep(delay)
    return False


def record_failure(root: Path, message: str) -> None:
    """Merkt sich fuer die naechste KI, dass das Einspielen nicht geklappt hat (sie sagt es dir)."""
    path = Path(root) / "data" / "update.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    state["einspielen_fehlgeschlagen"] = message
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel = ctypes.windll.kernel32
            handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if not handle:
                return False
            running = kernel.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT
            kernel.CloseHandle(handle)
            return running
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


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
    """Protokoll des Helfers in <Programmordner>/logs/update.log."""
    log = logging.getLogger("ki.update-helfer")
    target = Path(folder) / "logs" / "update.log"
    if getattr(log, "_ki_file", None) == target:
        return log
    for handler in list(log.handlers):
        log.removeHandler(handler)
        handler.close()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(target, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        log.addHandler(handler)
    except OSError:
        log.addHandler(logging.NullHandler())
    log.setLevel(logging.INFO)
    log._ki_file = target  # type: ignore[attr-defined]
    return log


# -- Nach dem Start der neuen Version -------------------------------------------------
def _read_state(root: Path) -> dict:
    try:
        return json.loads((Path(root) / "data" / "update.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(root: Path, **changes) -> None:
    path = Path(root) / "data" / "update.json"
    state = _read_state(root)  # frisch lesen: der Updater schreibt dieselbe Datei
    state.update(changes)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def after_start(exe: Path, root: Path, version: str, force: bool = False, background: bool = True) -> bool:
    """Aufraeumen und - beim ersten Start dieser .exe in dieser Version (auch nach /zurueck) -
    Verknuepfungen reparieren (im Hintergrund, damit der Start nicht wartet).
    True = es wird repariert."""
    exe = Path(exe)
    leftovers = list(Path(tempfile.gettempdir()).glob(f"{HELPER_PREFIX}*.exe"))
    leftovers.append(exe.with_name(exe.name + ".alt"))  # Ausweichweg beim letzten Update
    for old in leftovers:
        try:
            old.unlink()  # (laufende lassen sich nicht loeschen - dann eben beim naechsten Mal)
        except OSError:
            pass
    seen = _read_state(root).get("gestartet")
    seen = seen if isinstance(seen, dict) else {}
    if not force and seen.get(exe.name) == version:
        return False

    def repair() -> None:
        try:
            repair_shortcuts(exe, Path(root))
        except Exception as exc:  # noqa: BLE001 - nie den Start stoeren; beim naechsten Start nochmal
            logging.getLogger("ki").info("Verknuepfungen pruefen: %s", exc)
            return
        current = _read_state(root).get("gestartet")
        current = current if isinstance(current, dict) else {}
        current[exe.name] = version
        _write_state(root, gestartet=current)

    if background:
        import threading

        threading.Thread(target=repair, name="verknuepfungen", daemon=True).start()
    else:
        repair()
    return True


def repair_shortcuts(exe: Path, root: Path) -> int:
    """Verknuepfungen (Desktop, Startmenue, Taskleiste), die auf eine gesicherte alte Version
    in versionen/ (oder die beiseite geschobene .alt) zeigen, wieder auf die aktuelle .exe
    richten; solche, die schon auf die .exe zeigen, auffrischen (Windows merkt sich dann die
    richtige Datei). Gibt die Zahl der reparierten zurueck (nur Windows)."""
    if sys.platform != "win32":
        return 0
    exe = Path(exe)
    env = dict(os.environ)
    # Pfade als Umgebungsvariablen - nie in den Skripttext (Apostrophe, Sonderzeichen).
    env["KI_EXE"] = str(exe)
    env["KI_NAME"] = exe.name
    env["KI_BAK1"] = str(exe.parent / BACKUP_DIR) + "\\"
    env["KI_BAK2"] = str(Path(root) / BACKUP_DIR) + "\\"
    script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        "$exe = $env:KI_EXE; $name = $env:KI_NAME; $alt = $exe + '.alt'; "
        "$baks = @($env:KI_BAK1, $env:KI_BAK2); "
        "$s = New-Object -ComObject WScript.Shell; "
        "$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('CommonDesktopDirectory'), "
        "[Environment]::GetFolderPath('Programs'), "
        "(Join-Path $env:APPDATA 'Microsoft\\Internet Explorer\\Quick Launch\\User Pinned\\TaskBar'), "
        "(Join-Path $env:APPDATA 'Microsoft\\Internet Explorer\\Quick Launch')); "
        "$n = 0; "
        "foreach ($d in $dirs) { if ($d -and (Test-Path -LiteralPath $d)) { "
        "Get-ChildItem -LiteralPath $d -Filter *.lnk -Recurse | ForEach-Object { "
        "$l = $s.CreateShortcut($_.FullName); $t = [string]$l.TargetPath; $old = $false; "
        "foreach ($b in $baks) { if ($t.StartsWith($b, [StringComparison]::OrdinalIgnoreCase) -and "
        "([IO.Path]::GetFileName($t) -ieq $name)) { $old = $true } }; "
        "if ($t -ieq $alt) { $old = $true }; "
        "if ($old -or ($t -ieq $exe)) { $l.TargetPath = $exe; "
        "$l.WorkingDirectory = [IO.Path]::GetDirectoryName($exe); $l.Save(); if ($old) { $n++ } } } } }; "
        "Write-Output $n"
    )
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=90, stdin=subprocess.DEVNULL, env=env,
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
