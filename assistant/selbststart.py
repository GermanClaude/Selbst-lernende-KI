"""Wer startet die KI? - Startprotokoll, Autostart-Diagnose, nur ein Fenster.

Oeffnet sich die KI "von selbst", steckt fast immer etwas auf dem Computer
dahinter: ein Eintrag in der Windows-Aufgabenplanung, im Autostart, oder ein
Hintergrund-Skript, das sie immer wieder startet (oft von der KI selbst per
Shell eingerichtet, wenn sie "dauerhaft laufen" sollte).

  startprotokoll   - bei jedem Start: wer hat mich gestartet (Prozesskette)?
  finde_autostarts - sucht alles, was die KI automatisch startet
  entferne         - entfernt so einen Eintrag (Dateien wandern in data/entfernt/)
  Einzelinstanz    - laeuft die KI schon, oeffnet sich kein zweites Fenster
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .logging_setup import get_logger

logger = get_logger()

SILENT_EXIT_CODE = 43  # start.bat: ohne "Taste druecken" schliessen

_SCHEDULER = {"svchost.exe", "taskhostw.exe", "taskeng.exe", "taskhost.exe"}
_HOSTS = {"cmd.exe", "conhost.exe", "openconsole.exe", "windowsterminal.exe", "py.exe", "pyw.exe"}
# Nur solche Programme koennen ein "Waechter-Skript" sein, das die KI neu startet
# (ein Editor, der den KI-Ordner offen hat, gehoert nicht dazu).
_SCRIPT_HOSTS = {
    "python.exe", "pythonw.exe", "py.exe", "pyw.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "wscript.exe", "cscript.exe", "ki.exe", "python", "python3", "bash", "sh", "dash", "zsh",
}


@dataclass
class Autostart:
    kind: str          # "aufgabe", "registry", "ordner", "prozess", "cron", "datei"
    name: str          # Anzeigename
    detail: str        # was gestartet wird
    ref: dict = field(default_factory=dict)  # Daten zum Entfernen

    def describe(self) -> str:
        label = {
            "aufgabe": "Windows-Aufgabenplanung",
            "registry": "Autostart (Registrierung)",
            "ordner": "Autostart-Ordner",
            "prozess": "Laeuft gerade im Hintergrund",
            "cron": "Zeitplan (crontab)",
            "datei": "Autostart-Datei",
        }.get(self.kind, self.kind)
        return f"{label}: {self.name}\n       startet: {self.detail}"


# ---------------------------------------------------------------------------
#  Prozesskette: wer hat mich gestartet?
# ---------------------------------------------------------------------------
def _process_table() -> dict[int, tuple[int, str]]:
    """pid -> (ppid, name) fuer alle Prozesse."""
    if sys.platform == "win32":
        return _process_table_windows()
    table: dict[int, tuple[int, str]] = {}
    for entry in Path("/proc").iterdir() if Path("/proc").is_dir() else []:
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
            name = stat[stat.index("(") + 1 : stat.rindex(")")]
            ppid = int(stat[stat.rindex(")") + 2 :].split()[1])
            table[int(entry.name)] = (ppid, name)
        except (OSError, ValueError):
            continue
    return table


def _process_table_windows() -> dict[int, tuple[int, str]]:
    import ctypes

    class PROCESSENTRY32W(ctypes.Structure):  # noqa: N801 - Windows-Name
        _fields_ = [
            ("dwSize", ctypes.c_uint32),
            ("cntUsage", ctypes.c_uint32),
            ("th32ProcessID", ctypes.c_uint32),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", ctypes.c_uint32),
            ("cntThreads", ctypes.c_uint32),
            ("th32ParentProcessID", ctypes.c_uint32),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_uint32),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    k32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return {}
    table: dict[int, tuple[int, str]] = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return table


def ancestry(pid: int | None = None, table: dict[int, tuple[int, str]] | None = None) -> list[tuple[int, str]]:
    """[(pid, name), ...] vom Elternprozess aufwaerts (hoechstens 8 Stufen)."""
    table = table if table is not None else _process_table()
    chain: list[tuple[int, str]] = []
    current = pid if pid is not None else os.getpid()
    seen = {current}
    for _ in range(8):
        parent = table.get(current, (0, ""))[0]
        if not parent or parent in seen or parent not in table:
            break
        seen.add(parent)
        chain.append((parent, table[parent][1]))
        current = parent
    return chain


# Gehoeren zum eigenen Startweg: venv-Python, KI.exe-Starter, Konsole/Terminal.
_OWN_HOSTS = {"conhost.exe", "openconsole.exe", "windowsterminal.exe", "py.exe", "pyw.exe", "ki.exe"}
_SHELLS = {"cmd.exe", "bash", "sh", "dash", "zsh"}  # die Shell, die start.bat/start.sh ausfuehrt
# Programme, die ein "Waechter-Skript" sein koennen (Windows).
_WIN_SCRIPT_HOSTS = {"powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe", "cmd.exe", "mshta.exe"}
_INTERACTIVE_PARENTS = {"explorer.exe", "windowsterminal.exe", "openconsole.exe", "conhost.exe"}


def split_chain(chain: list[tuple[int, str]]) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Teilt die Prozesskette in den eigenen Startweg und den Rest (wer hat gestartet)."""
    own: list[tuple[int, str]] = []
    seen_shell = False
    for pid, name in chain:
        low = name.lower()
        if low.startswith("python") or low in _OWN_HOSTS:
            own.append((pid, name))
            continue
        if low in _SHELLS and not seen_shell:
            seen_shell = True
            own.append((pid, name))
            continue
        break
    return own, chain[len(own):]


def _is_script_host(name: str) -> bool:
    low = name.lower()
    return low in _WIN_SCRIPT_HOSTS or (low.startswith("python") and low.endswith(".exe"))


def classify(chain: list[tuple[int, str]], ki_pids: set[int] = frozenset()) -> tuple[str, bool]:
    """(Beschreibung, unerwartet?) fuer eine Prozesskette."""
    own, rest = split_chain(chain)
    for pid, _name in chain:  # die ganze Kette: auch "python -m assistant" direkt aus der Shell
        if pid in ki_pids:
            return "von einer anderen laufenden KI (z.B. per Shell-Befehl)", True
    if not rest:
        # Eltern schon beendet: typisch fuer ein Skript, das die KI startet und sich beendet.
        return "unbekannt (der startende Prozess laeuft nicht mehr)", False
    name = rest[0][1]
    low = name.lower()
    if low in _SCHEDULER:
        return "von der Windows-Aufgabenplanung (geplante Aufgabe)", True
    if low in ("cron", "crond", "anacron"):
        return "von einem Zeitplan (cron)", True
    if low == "explorer.exe":
        if _seconds_since_boot() < 180:
            return "beim Anmelden (Windows-Autostart)", True
        return "per Doppelklick bzw. aus dem Explorer", False
    if _is_script_host(name):
        parent = rest[1][1].lower() if len(rest) > 1 else ""
        if parent in _INTERACTIVE_PARENTS:
            return f"aus einem Fenster von {name}", False
        # Ein Skript ohne sichtbares Fenster dahinter: typisch fuer einen "Waechter",
        # der die KI immer wieder oeffnet.
        return f"von einem Hintergrund-Skript ({name}, PID {rest[0][0]})", True
    return f"von {name}", False


def _seconds_since_boot() -> float:
    if sys.platform == "win32":
        try:
            import ctypes

            k32 = ctypes.WinDLL("kernel32")
            k32.GetTickCount64.restype = ctypes.c_uint64
            return k32.GetTickCount64() / 1000
        except Exception:  # noqa: BLE001
            return 1e9
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 1e9


def _pid_alive(pid: int, table: dict[int, tuple[int, str]] | None = None, since: float | None = None) -> bool:
    """Laeuft unter dieser PID noch die KI? 'since' = Zeitpunkt der Sperre: ein Prozess,
    der danach gestartet ist, hat nur dieselbe (wiederverwendete) PID."""
    if pid <= 0:
        return False
    table = table if table is not None else _process_table()
    if pid not in table:
        return False
    name = table[pid][1].lower()
    own = Path(sys.executable).name.lower() if getattr(sys, "frozen", False) else ""
    if not ("python" in name or name == "assistant" or name == own
            or re.match(r"^ki(-app)?( \(\d+\))?\.exe$", name)):
        return False
    if since is not None:
        started = _process_start_time(pid)
        if started is not None and started > since + 5:
            return False
    return True


def _ki_name(name: str) -> bool:
    low = name.lower()
    own = Path(sys.executable).name.lower() if getattr(sys, "frozen", False) else ""
    return low.startswith("python") or low == own or bool(re.match(r"^ki(-app)?( \(\d+\))?\.exe$", low))


def _handed_over(chain: list[tuple[int, str]], lock_pid: int | None) -> bool:
    """Hat die laufende KI diese hier selbst gestartet (Neustart, App -> Terminal)? Nur wenn sie
    es angekuendigt hat (KI_NEUSTART_VON) und direkt startete - mit einer Shell dazwischen
    (z.B. per Shell-Befehl) zaehlt das nicht."""
    if not lock_pid or os.environ.get("KI_NEUSTART_VON") != str(lock_pid):
        return False
    for pid, name in chain:
        if pid == lock_pid:
            return True
        if not _ki_name(name):
            return False
    return False


def _process_start_time(pid: int) -> float | None:
    """Startzeit eines Prozesses (Unix-Zeit) - oder None, wenn nicht ermittelbar."""
    try:
        if sys.platform == "win32":
            import ctypes

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = ctypes.c_void_p
            k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32]
            handle = k32.OpenProcess(0x1000, 0, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return None
            try:
                times = [ctypes.c_uint64() for _ in range(4)]
                k32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_uint64)] * 4
                if not k32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                    return None
                return times[0].value / 10_000_000 - 11_644_473_600  # FILETIME -> Unix
            finally:
                k32.CloseHandle.argtypes = [ctypes.c_void_p]
                k32.CloseHandle(handle)
        stat = Path(f"/proc/{pid}/stat").read_text()
        ticks = int(stat[stat.rindex(")") + 2 :].split()[19])
        btime = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                     if line.startswith("btime"))
        return btime + ticks / os.sysconf("SC_CLK_TCK")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
#  Startprotokoll + nur ein Fenster
# ---------------------------------------------------------------------------
class StartGuard:
    """Protokolliert Starts und verhindert, dass die KI doppelt laeuft."""

    def __init__(self, root: Path, table=None):
        self.root = Path(root)
        self.lock_path = self.root / "data" / "ki.lock"
        self.log_path = self.root / "data" / "starts.json"
        self._table = table

    def _get_table(self):
        if self._table is None:
            try:
                self._table = _process_table()
            except Exception as exc:  # noqa: BLE001
                logger.info("Prozessliste nicht lesbar: %s", exc)
                self._table = {}
        return self._table

    def running_pid(self) -> int | None:
        """PID einer anderen, noch laufenden KI - sonst None."""
        try:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            pid = int(data.get("pid", 0))
            since = float(data.get("seit", 0)) or None
        except (OSError, ValueError, TypeError):
            return None
        if pid == os.getpid() or pid in {p for p, _ in ancestry(table=self._get_table())}:
            return None
        restarted_from = os.environ.get("KI_NEUSTART_VON")
        if restarted_from and str(pid) == restarted_from:
            self._wait_for_exit(pid)  # Neustart nach Update: die alte KI beendet sich gleich
            return None
        return pid if _pid_alive(pid, self._get_table(), since=since) else None

    def _wait_for_exit(self, pid: int, seconds: float = 15) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end and _pid_alive(pid, _process_table()):
            time.sleep(0.3)

    def record_start(self) -> tuple[str, bool]:
        """Merkt sich den Start; gibt (wer hat gestartet, unerwartet?) zurueck."""
        table = self._get_table()
        chain = ancestry(table=table)
        lock_pid = self._lock_pid()
        if _handed_over(chain, lock_pid):
            who, unexpected = "von der KI selbst (Neustart bzw. Wechsel App/Terminal)", False
        else:
            ki_pids = {lock_pid} if lock_pid and _pid_alive(lock_pid, table) else set()
            who, unexpected = classify(chain, ki_pids)
        entry = {
            "zeit": datetime.now().isoformat(timespec="seconds"),
            "pid": os.getpid(),
            "kette": " <- ".join(name for _pid, name in chain[:5]) or "?",
            "gestartet": who,
            "unerwartet": unexpected,
        }
        log = self.starts()
        log.append(entry)
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text(json.dumps(log[-50:], indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            logger.info("Startprotokoll nicht schreibbar: %s", exc)
        return who, unexpected

    def starts(self) -> list[dict]:
        try:
            data = json.loads(self.log_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _lock_pid(self) -> int | None:
        try:
            return int(json.loads(self.lock_path.read_text(encoding="utf-8")).get("pid", 0)) or None
        except (OSError, ValueError, TypeError):
            return None

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(json.dumps({"pid": os.getpid(), "seit": time.time()}), encoding="utf-8")

    def release(self) -> None:
        if self._lock_pid() == os.getpid():
            self.lock_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
#  Autostart-Diagnose
# ---------------------------------------------------------------------------
def _markers(root: Path, workspace: Path | None) -> list[str]:
    marks = {str(root).lower(), str(root).lower().replace("\\", "/"), "ki.exe", "run_ki.py", "-m assistant",
             "selbst-lernende-ki"}
    if workspace:
        marks |= {str(workspace).lower(), str(workspace).lower().replace("\\", "/")}
    return sorted(m for m in marks if m)


def _matches(text: str, markers: list[str]) -> bool:
    low = text.lower()
    return any(m in low for m in markers)


def _run(cmd: list[str], timeout: float = 30) -> str:
    from .tools.shell import _decode  # gleiche robuste Dekodierung wie das Shell-Werkzeug

    proc = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout)
    return _decode(proc.stdout)


def finde_autostarts(root: Path, workspace: Path | None = None) -> list[Autostart]:
    """Alles, was die KI (oder Skripte aus ihrem Arbeitsordner) automatisch startet."""
    markers = _markers(Path(root).resolve(), workspace.resolve() if workspace else None)
    found: list[Autostart] = []
    finders = (
        [_scheduled_tasks, _registry_run, _startup_folders, _processes]
        if sys.platform == "win32"
        else [_crontab, _xdg_autostart, _processes_posix]
    )
    for finder in finders:
        try:
            found.extend(finder(markers))
        except Exception as exc:  # noqa: BLE001 - eine Quelle darf die anderen nicht verhindern
            logger.info("Autostart-Suche (%s): %s", finder.__name__, exc)
    return found


def _scheduled_tasks(markers: list[str]) -> list[Autostart]:
    script = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        "Get-ScheduledTask | ForEach-Object { [pscustomobject]@{ "
        "Name = $_.TaskPath + $_.TaskName; Zustand = [string]$_.State; "
        "Aktion = (($_.Actions | ForEach-Object { $_.Execute + ' ' + $_.Arguments + ' ' + $_.WorkingDirectory }) -join ' | ') "
        "} } | ConvertTo-Json -Compress"
    )
    out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=60)
    data = json.loads(out) if out.strip() else []
    if isinstance(data, dict):
        data = [data]
    result = []
    for task in data:
        action = str(task.get("Aktion") or "")
        if _matches(action, markers):
            result.append(Autostart("aufgabe", str(task.get("Name")), action.strip(), {"name": task.get("Name")}))
    return result


_RUN_KEYS = [
    ("HKEY_CURRENT_USER", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKEY_CURRENT_USER", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
    ("HKEY_LOCAL_MACHINE", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKEY_LOCAL_MACHINE", r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
    ("HKEY_LOCAL_MACHINE", r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
]


def _registry_run(markers: list[str]) -> list[Autostart]:
    import winreg  # type: ignore

    result = []
    for hive_name, path in _RUN_KEYS:
        try:
            key = winreg.OpenKey(getattr(winreg, hive_name), path)
        except OSError:
            continue
        with key:
            index = 0
            while True:
                try:
                    name, value, _type = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if _matches(str(value), markers):
                    result.append(Autostart("registry", f"{name} ({hive_name}\\{path})", str(value),
                                            {"hive": hive_name, "path": path, "value": name}))
    return result


def _startup_dirs() -> list[Path]:
    dirs = []
    for env, sub in (("APPDATA", r"Microsoft\Windows\Start Menu\Programs\Startup"),
                     ("PROGRAMDATA", r"Microsoft\Windows\Start Menu\Programs\StartUp")):
        base = os.environ.get(env)
        if base:
            dirs.append(Path(base) / sub)
    return dirs


def _file_mentions(path: Path, markers: list[str]) -> bool:
    try:
        data = path.read_bytes()[:200_000]
    except OSError:
        return False
    # .lnk speichert Pfade als UTF-16 (an gerader oder ungerader Stelle); Skripte als Text.
    text = "\n".join((data.decode("utf-16-le", "ignore"), data[1:].decode("utf-16-le", "ignore"),
                      data.decode("latin-1", "ignore")))
    return _matches(text, markers)


def _startup_folders(markers: list[str]) -> list[Autostart]:
    result = []
    for folder in _startup_dirs():
        if not folder.is_dir():
            continue
        for item in folder.iterdir():
            if item.is_file() and _file_mentions(item, markers):
                result.append(Autostart("ordner", item.name, str(item), {"file": str(item)}))
    return result


def _processes(markers: list[str]) -> list[Autostart]:
    script = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        "Get-CimInstance Win32_Process | Select-Object ProcessId, Name, CommandLine | ConvertTo-Json -Compress"
    )
    out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=60)
    data = json.loads(out) if out.strip() else []
    return _match_processes(
        [(int(p.get("ProcessId") or 0), str(p.get("Name") or ""), str(p.get("CommandLine") or "")) for p in data],
        markers,
    )


def _match_processes(procs: list[tuple[int, str, str]], markers: list[str],
                     chain: list[tuple[int, str]] | None = None) -> list[Autostart]:
    """Laufende Skripte/Programme aus dem KI-Ordner - ausser der KI selbst.

    Nur der eigene Startweg (venv-Python, start.bat-Shell, Konsole) wird ausgelassen.
    Ein Skript WEITER OBEN in der Kette hat dieses Fenster geoeffnet - genau der
    "Waechter", der die KI immer wieder startet - und wird mit angezeigt.
    """
    chain = ancestry() if chain is None else chain
    own, rest = split_chain(chain)
    own_pids = {os.getpid(), *[pid for pid, _ in own]}
    rest_pids = {pid for pid, _ in rest}
    result = []
    for pid, name, cmdline in procs:
        if pid in own_pids or not cmdline or not _matches(cmdline, markers):
            continue
        if name.lower() not in _SCRIPT_HOSTS and not name.lower().startswith("python"):
            continue
        low = cmdline.lower()
        if pid in rest_pids:
            kind_name = f"{name} (PID {pid}) - hat DIESES Fenster geoeffnet"
        elif "-m assistant" in low or "run_ki.py" in low or low.rstrip('" ').endswith("ki.exe"):
            kind_name = f"{name} (PID {pid}) - eine weitere KI"
        else:
            kind_name = f"{name} (PID {pid})"
        result.append(Autostart("prozess", kind_name, cmdline.strip(), {"pid": pid, "vorfahr": pid in rest_pids}))
    return result


def _processes_posix(markers: list[str]) -> list[Autostart]:
    procs = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
                procs.append((int(entry.name), (entry / "comm").read_text().strip(), cmdline))
            except OSError:
                continue
    return _match_processes(procs, markers)


def _crontab(markers: list[str]) -> list[Autostart]:
    if not shutil.which("crontab"):
        return []
    proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=15)
    return [Autostart("cron", line.strip()[:60], line.strip(), {"line": line})
            for line in proc.stdout.splitlines() if line.strip() and not line.startswith("#")
            and _matches(line, markers)]


def _xdg_autostart(markers: list[str]) -> list[Autostart]:
    folder = Path.home() / ".config" / "autostart"
    if not folder.is_dir():
        return []
    return [Autostart("datei", item.name, str(item), {"file": str(item)})
            for item in folder.iterdir() if item.is_file() and _file_mentions(item, markers)]


def entferne(entry: Autostart, root: Path) -> str:
    """Entfernt einen Autostart. Dateien werden nach data/entfernt/ verschoben."""
    if entry.kind == "aufgabe":
        proc = subprocess.run(["schtasks", "/Delete", "/TN", entry.ref["name"], "/F"],
                              capture_output=True, stdin=subprocess.DEVNULL, timeout=30)
        if proc.returncode != 0:
            from .tools.shell import _decode

            raise OSError(_decode(proc.stderr or proc.stdout).strip()
                          or "Aufgabe konnte nicht entfernt werden (evtl. als Administrator noetig).")
        return f"Aufgabe {entry.ref['name']} entfernt."
    if entry.kind == "registry":
        import winreg  # type: ignore

        with winreg.OpenKey(getattr(winreg, entry.ref["hive"]), entry.ref["path"], 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, entry.ref["value"])
        return f"Autostart-Eintrag {entry.ref['value']} entfernt."
    if entry.kind in ("ordner", "datei"):
        src = Path(entry.ref["file"])
        dest_dir = Path(root) / "data" / "entfernt"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{datetime.now():%Y%m%d-%H%M%S}_{src.name}"
        shutil.move(str(src), str(dest))
        return f"{src.name} aus dem Autostart entfernt (gesichert in data/entfernt/)."
    if entry.kind == "prozess":
        pid = int(entry.ref["pid"])
        if sys.platform == "win32":
            # Ohne /T, wenn es dieses Fenster geoeffnet hat - sonst wuerde die KI mit beendet.
            tree = [] if entry.ref.get("vorfahr") else ["/T"]
            subprocess.run(["taskkill", "/F", *tree, "/PID", str(pid)], capture_output=True, timeout=30)
        else:
            import signal

            os.kill(pid, signal.SIGTERM)
        return f"Prozess {pid} beendet."
    if entry.kind == "cron":
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=15).stdout
        remaining = "".join(line for line in current.splitlines(keepends=True) if line != entry.ref["line"]
                            and line.rstrip("\n") != entry.ref["line"].rstrip("\n"))
        subprocess.run(["crontab", "-"], input=remaining, text=True, timeout=15, check=True)
        return "Zeitplan-Eintrag entfernt."
    raise ValueError(f"Unbekannte Art: {entry.kind}")


# ---------------------------------------------------------------------------
#  Shell-Befehle, die einen automatischen Start einrichten
# ---------------------------------------------------------------------------
# Nur EINRICHTEN zaehlt - Nachschauen (schtasks /query, crontab -l, dir ...) und
# Entfernen (schtasks /delete, Unregister-ScheduledTask) sind erwuenscht und frei.
_CREATE_TASK = re.compile(
    r"\bschtasks(\.exe)?\b[^|&]*\s/(create|change)\b|\b(register|set|new)-scheduledtask\b", re.I
)
_RUN_KEY = re.compile(r"\\currentversion\\run(once)?\b", re.I)
_REG_WRITE = re.compile(r"\breg(\.exe)?\s+(add|import|copy)\b|\b(set|new)-itemproperty\b|\bnew-item\b", re.I)
_STARTUP_DIR = re.compile(r"start menu\\programs\\startup|shell:(common )?startup|\\\.config\\autostart", re.I)
_WRITE = re.compile(
    r"\b(copy|xcopy|robocopy|move|mklink|new-item|set-content|add-content|out-file|copy-item|"
    r"move-item|createshortcut|cp|mv|ln|tee)\b|>", re.I
)
_OTHER_AUTOSTART = re.compile(
    r"\bcrontab\b(?!\s+-[lr]\b)|\bsystemctl\b[^|&;]*\benable\b|\bnew-service\b|\bsc(\.exe)?\s+create\b"
    r"|(^|[\s\"'&|;\\/])at(\.exe)?\s+\d|win32_startupcommand",
    re.I,
)
_KI_TARGET = r"(start\.bat|ki\.exe|run_ki\.py|-m\s+assistant\b|start\.sh)"
_RUNS_KI = re.compile(
    rf"(^|[&|;(]\s*)\"?[^\s\"&|;]*{_KI_TARGET}"                      # als Befehl selbst: C:\\KI\\start.bat
    rf"|\b(start|call|start-process|saps|invoke-item|ii)\b[^&|;]*{_KI_TARGET}"
    rf"|\b(python[w3]?|py|pythonw)(\.exe)?\b[^&|;]*{_KI_TARGET}"
    rf"|\bcmd(\.exe)?\s+/[ck]\b[^&|;]*{_KI_TARGET}|\b(bash|sh)\b[^&|;]*{_KI_TARGET}",
    re.I,
)


def sets_up_autostart(command: str) -> bool:
    """Richtet der Befehl einen automatischen Start ein (Aufgabe, Run-Schluessel, ...)?"""
    paths = command.replace("/", "\\")
    if _CREATE_TASK.search(command) or _OTHER_AUTOSTART.search(command):
        return True
    if _RUN_KEY.search(paths) and _REG_WRITE.search(command):
        return True
    return bool(_STARTUP_DIR.search(paths) and _WRITE.search(command))


_START_SCRIPT = re.compile(r"\"?([^\s\"&|;]*start\.(bat|sh))\b", re.I)


def _same_dir(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))
    except OSError:
        return False


def starts_the_ki(command: str, ki_root: Path | None = None, cwd: str | Path | None = None) -> bool:
    """Wuerde der Befehl die KI (noch einmal) starten? Lesen/Bearbeiten zaehlt nicht.

    Mit ki_root zaehlt eine start.bat/start.sh nur, wenn es die der KI ist - die
    start.bat eines Spiels oder Projekts darf ohne Rueckfrage laufen.
    """
    text = command.strip()
    if not _RUNS_KI.search(text):
        return False
    if ki_root is None:
        return True
    if re.search(r"ki\.exe|run_ki\.py|-m\s+assistant\b", text, re.I):
        return True
    base = Path(cwd) if cwd else Path.cwd()
    for match in _START_SCRIPT.finditer(text):
        raw = match.group(1).replace("\\", "/")
        script = Path(raw)
        if not script.is_absolute() and not re.match(r"^[a-zA-Z]:", raw):
            script = base / script
        if _same_dir(Path(str(script)).parent, Path(ki_root)):
            return True
    return False


def is_autostart_path(path: Path) -> bool:
    low = str(path).lower().replace("\\", "/")
    return "/start menu/programs/startup" in low or "/.config/autostart/" in low
