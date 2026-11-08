"""Automatische Updates aus dem GitHub-Repo - alte Versionen bleiben erhalten.

Ablauf:
  1. pruefen(): liest __version__ aus assistant/__init__.py im Repo (Branch aus
     [update]) und vergleicht sie mit der eigenen. Nur eine echte NEUERE Version
     zaehlt - ein Rueckschritt wird nie installiert.
  2. Die Neuerungen stehen in CHANGELOG.md (alle Abschnitte zwischen alter und
     neuer Version); die KI erklaert sie dann in eigenen Worten.
  3. installieren(): sichert die laufende Version nach versionen/, laedt das Repo
     als Zip, ersetzt die Programmdateien und installiert neue Pakete. Deine Daten
     und Einstellungen (.env, settings.toml, persona.md, werte.md, data/,
     workspace/ ...) werden nie angefasst.
  4. Neustart: Rueckgabecode 42 -> start.bat / start.sh starten die KI neu.

Als KI.exe kommt die neue Version aus den GitHub-Releases (Datei KI.exe).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from . import __version__
from .logging_setup import get_logger

logger = get_logger()

RESTART_EXIT_CODE = 42
BACKUP_DIR = "versionen"

# Ordner/Dateien, die ein Update NIE anfasst (deine Daten und Einstellungen).
_PROTECTED_DIRS = {
    ".env", ".git", ".venv", "venv", "data", "logs", "workspace", BACKUP_DIR,
    "dist", "build", "__pycache__",
}
_PROTECTED_FILES = {"config/settings.toml", "config/permissions.toml", "config/ueber_mich.json",
                    "config/app-anpassung.json", "config/app-anpassung.css"}
# Nur anlegen, wenn sie fehlen - hier "erziehst" du deine KI.
_CREATE_ONLY = {"config/persona.md", "config/werte.md"}
# Hier duerfen veraltete Dateien entfernt werden (sie liegen ja in der Sicherung).
_CODE_DIRS = ("assistant/", "tests/", "packaging/")

_VERSION_RE = re.compile(r"""__version__\s*=\s*["']([^"']+)["']""")


class UpdateError(Exception):
    """Ein Update konnte nicht installiert werden (mit verstaendlicher Meldung)."""


Fetch = Callable[..., bytes]


@dataclass
class UpdateInfo:
    current: str
    new: str
    notes: str           # Neuerungen (Auszug aus CHANGELOG.md bzw. Release-Text)
    download_url: str
    kind: str            # "quelle" oder "exe"


@dataclass
class Backup:
    name: str
    version: str
    path: Path


def parse_version(text: str) -> tuple[int, ...]:
    """'0.2.10' -> (0, 2, 10). Alles nach '-' oder '+' zaehlt nicht."""
    core = re.split(r"[-+ ]", text.strip().lstrip("vV"), maxsplit=1)[0]
    return tuple(int(n) for n in re.findall(r"\d+", core)) or (0,)


def exe_flavor(path) -> str:
    """'app' fuer KI-App.exe, 'terminal' fuer KI.exe - auch wenn Windows die Datei beim
    Herunterladen umbenannt hat ('KI-App (1).exe', 'KI (2).exe')."""
    stem = re.sub(r"\s*\(\d+\)$", "", Path(str(path)).stem).strip().lower()
    return "app" if stem.endswith("app") else "terminal"


def own_exe_flavor(path) -> str:
    """Art der laufenden .exe aus ihrem Programmkopf: Windows-Programm ohne Konsole = 'app'.
    (Sicherer als der Name - bei ausgeblendeten Endungen heisst sie schnell 'KI-App.exe.exe'.)"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
        pe = int.from_bytes(head[0x3C:0x40], "little")
        if head[pe:pe + 4] == b"PE\0\0":
            subsystem = int.from_bytes(head[pe + 0x5C:pe + 0x5E], "little")
            if subsystem in (2, 3):
                return "app" if subsystem == 2 else "terminal"
    except (OSError, ValueError):
        pass
    return exe_flavor(path)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def read_version(init_text: str) -> str | None:
    match = _VERSION_RE.search(init_text)
    return match.group(1) if match else None


def changelog_between(changelog: str, old: str, new: str) -> str:
    """Alle Abschnitte '## <version>' mit  old < version <= new."""
    parts = []
    for section in re.split(r"(?m)^##\s+", changelog)[1:]:
        head = section.splitlines()[0] if section.strip() else ""
        match = re.match(r"v?(\d+(?:\.\d+)*)", head.strip())
        if match and parse_version(old) < parse_version(match.group(1)) <= parse_version(new):
            parts.append("## " + section.strip())
    return "\n\n".join(parts)


def _http_get(url: str, timeout: float = 15) -> bytes:
    import requests

    headers = {"User-Agent": "Selbst-lernende-KI-Updater"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    # Ein Schluessel ist nur fuer private Repos noetig - und nur dann wird er gesendet
    # (ein fuer andere Programme gesetzter GITHUB_TOKEN wuerde sonst stoeren).
    token = os.environ.get("KI_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and resp.status_code in (401, 403, 404):
        resp = requests.get(url, headers={**headers, "Authorization": f"Bearer {token}"}, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _is_protected(rel: str) -> bool:
    parts = rel.split("/")
    return parts[0] in _PROTECTED_DIRS or "__pycache__" in parts or rel in _PROTECTED_FILES or rel.endswith(".pyc")


def program_files(folder: Path) -> set[str]:
    """Alle Programmdateien (relativ, mit '/'), ohne Daten und Einstellungen."""
    files: set[str] = set()
    if not folder.is_dir():
        return files
    for path in folder.rglob("*"):
        if path.is_file():
            rel = path.relative_to(folder).as_posix()
            if not _is_protected(rel):
                files.add(rel)
    return files


class Updater:
    def __init__(
        self,
        settings,
        root: Path,
        fetch: Fetch = _http_get,
        current_version: str = __version__,
        frozen: bool | None = None,
        exe_path: Path | None = None,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        now: Callable[[], datetime] = datetime.now,
        inplace: bool | None = None,
    ):
        self.settings = settings
        self.root = Path(root)
        self.fetch = fetch
        self.current = current_version
        self.frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        self.exe_path = Path(exe_path or sys.executable)
        # Windows: neue .exe beim Neustart IN die bestehende Datei schreiben (Verknuepfungen
        # bleiben gueltig, siehe austausch.py). Sonst (Tests, andere Systeme): gleich ersetzen.
        self.inplace = sys.platform == "win32" if inplace is None else bool(inplace)
        self.pending_exe: Path | None = None
        self.current_before_install = current_version
        self.run = run
        self.now = now
        self.state_path = self.root / "data" / "update.json"
        self.last_error: str | None = None

    # -- Zustand ------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return (self.settings.modus or "").strip().lower() in ("automatisch", "fragen")

    @property
    def automatic(self) -> bool:
        return (self.settings.modus or "").strip().lower() == "automatisch"

    def _state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self, **changes) -> None:
        state = self._state()
        state.update(changes)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    @property
    def is_git_checkout(self) -> bool:
        return not self.frozen and (self.root / ".git").exists()

    @property
    def paused(self) -> bool:
        """Nach /zurueck: keine automatischen Updates, bis du /update eingibst."""
        return bool(self._state().get("automatik_pausiert"))

    def due(self) -> bool:
        """Ist es Zeit fuer die regelmaessige Pruefung?"""
        if not self.enabled:
            return False
        last = self._state().get("letzte_pruefung")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
        except ValueError:
            return True
        hours = max(1, int(self.settings.pruefen_alle_stunden or 24))
        return self.now() - last_dt >= timedelta(hours=hours)

    # -- Pruefen ------------------------------------------------------------
    def check(self) -> UpdateInfo | None:
        """Schaut nach einer neueren Version. Netzwerkfehler -> None (still)."""
        self.last_error = None
        self.last_seen = None
        try:
            info = self._check_exe() if self.frozen else self._check_source()
        except Exception as exc:  # noqa: BLE001 - offline, Repo weg, ...
            logger.info("Update-Pruefung nicht moeglich: %s", exc)
            self.last_error = friendly_check_error(exc)
            return None
        latest = info.new if info else (self.last_seen or self.current)
        self._save_state(letzte_pruefung=self.now().isoformat(timespec="seconds"), neueste=latest)
        return info

    def status(self) -> dict:
        """Fuer die Anzeige 'auf dem neuesten Stand?' -> state: aktuell | neu | unbekannt | aus."""
        data = self._state()
        checked, latest = data.get("letzte_pruefung"), data.get("neueste")
        if latest and is_newer(str(latest), self.current):
            state = "neu"  # auch bei ausgeschalteten automatischen Updates zeigen, was es gibt
        elif not self.enabled:
            state = "aus"
        elif checked:
            state = "aktuell"  # gespeichert wird nur nach erfolgreicher Pruefung
        else:
            state = "unbekannt"
        return {"state": state, "current": self.current, "latest": latest or None, "checked": checked,
                "error": getattr(self, "last_error", None)}

    def _ref(self) -> str:
        return (self.settings.branch or "").strip()

    def _check_source(self) -> UpdateInfo | None:
        repo = self.settings.repo.strip()
        ref = self._ref() or "HEAD"  # HEAD = Standard-Branch
        base = f"https://raw.githubusercontent.com/{repo}/{quote(ref, safe='/')}/"
        remote = read_version(
            self.fetch(base + "assistant/__init__.py", timeout=8).decode("utf-8", "replace")
        )
        self.last_seen = remote
        if not remote or not is_newer(remote, self.current):
            return None
        try:
            changelog = self.fetch(base + "CHANGELOG.md", timeout=8).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            changelog = ""
        zip_ref = f"/{quote(self._ref(), safe='/')}" if self._ref() else ""
        return UpdateInfo(
            current=self.current,
            new=remote,
            notes=changelog_between(changelog, self.current, remote),
            download_url=f"https://api.github.com/repos/{repo}/zipball{zip_ref}",
            kind="quelle",
        )

    def _check_exe(self) -> UpdateInfo | None:
        repo = self.settings.repo.strip()
        release = json.loads(self.fetch(f"https://api.github.com/repos/{repo}/releases/latest", timeout=8))
        remote = str(release.get("tag_name", "")).lstrip("vV")
        self.last_seen = remote
        if not remote or not is_newer(remote, self.current):
            return None
        assets = release.get("assets", [])
        # Jedes Programm holt sich SEINE Datei (KI.exe bzw. KI-App.exe) - auch wenn es lokal
        # "KI-App (1).exe" heisst. Ersetzt wird immer die eigene Datei (Name bleibt).
        flavor = own_exe_flavor(self.exe_path)
        asset = next((a for a in assets if str(a.get("name", "")).lower().endswith(".exe")
                      and exe_flavor(a.get("name", "")) == flavor), None)
        if asset is None:
            return None
        notes = release.get("body") or ""
        try:  # alle uebersprungenen Versionen erklaeren, nicht nur die neueste
            tag = quote(str(release.get("tag_name")), safe="")
            changelog = self.fetch(f"https://raw.githubusercontent.com/{repo}/{tag}/CHANGELOG.md", timeout=8)
            notes = changelog_between(changelog.decode("utf-8", "replace"), self.current, remote) or notes
        except Exception:  # noqa: BLE001
            pass
        return UpdateInfo(
            current=self.current,
            new=remote,
            notes=notes,
            download_url=asset["browser_download_url"],
            kind="exe",
        )

    # -- Installieren -------------------------------------------------------
    def install(self, info: UpdateInfo, say: Callable[[str], None] = print) -> str:
        self.current_before_install = self.current
        if info.kind == "exe":
            message = self._install_exe(info, say)
        else:
            message = self._install_source(info, say)
        self._save_state(automatik_pausiert=False, installiert=info.new)
        self.current = info.new  # falls ohne Neustart weitergemacht wird (z.B. /zurueck)
        self._prune()
        return message

    def _install_source(self, info: UpdateInfo, say: Callable[[str], None]) -> str:
        if (self.root / ".git").exists():
            raise UpdateError(
                "Dieser Ordner ist ein Git-Checkout - bitte mit 'git pull' aktualisieren."
            )
        say(f"Lade Version {info.new} herunter …")
        data = self.fetch(info.download_url, timeout=180)
        with tempfile.TemporaryDirectory() as tmp:
            new_root = _extract_zip(data, Path(tmp))
            new_version = read_version(
                (new_root / "assistant" / "__init__.py").read_text(encoding="utf-8", errors="replace")
            )
            if not new_version or not is_newer(new_version, self.current):
                raise UpdateError("Die heruntergeladene Version ist nicht neuer - nichts geaendert.")
            backup = self._backup_source(program_files(new_root))
            say(f"Alte Version {self.current} gesichert in {backup.relative_to(self.root).as_posix()}/")
            old_requirements = _read_bytes(self.root / "requirements.txt")
            self._replace_or_rollback(new_root, backup)
            if _read_bytes(self.root / "requirements.txt") != old_requirements:
                self._pip_install(say)
        return f"Version {new_version} ist installiert."

    def _install_exe(self, info: UpdateInfo, say: Callable[[str], None]) -> str:
        exe = self.exe_path
        say(f"Lade KI.exe {info.new} herunter …")
        data = self.fetch(info.download_url, timeout=600)
        if not data.startswith(b"MZ") or len(data) < 1_000_000:
            raise UpdateError("Die heruntergeladene Datei ist keine gueltige KI.exe - nichts geaendert.")
        new_exe = exe.with_name(exe.name + ".neu")
        new_exe.write_bytes(data)
        backup = self._swap_exe(new_exe)
        say(f"Alte Version {self.current} gesichert in {backup.relative_to(self.root).as_posix()}/")
        if self.pending_exe is not None:
            return f"{exe.name} {info.new} ist bereit - sie wird beim Neustart eingesetzt."
        return f"KI.exe {info.new} ist installiert."

    def _swap_exe(self, new_exe: Path) -> Path:
        """Die laufende .exe als KOPIE sichern und die neue einsetzen.

        Windows: Eine laufende .exe darf man nicht ueberschreiben. Die neue Version wird
        deshalb erst beim Neustart von einem Helfer IN dieselbe Datei geschrieben
        (austausch.py) - so bleibt sie fuer Windows dieselbe Datei und Verknuepfungen auf dem
        Desktop oder in der Taskleiste zeigen weiter auf die richtige Version (frueher wanderten
        sie mit der alten Datei in den Sicherungsordner). Anderswo: gleich ersetzen.
        """
        exe = self.exe_path
        try:  # z.B. vom Virenscanner gleich in Quarantaene genommen?
            ok = new_exe.is_file() and new_exe.read_bytes()[:2] == b"MZ"
        except OSError:
            ok = False
        if not ok:
            raise UpdateError("Die neue Version ist nicht mehr da (Virenscanner?) - die bisherige bleibt.")
        latest = self.backups()[:1]
        if latest and latest[0].version == self.current and (latest[0].path / exe.name).is_file():
            backup = latest[0].path  # dieselbe Version ist schon gesichert (z.B. zweiter Versuch)
        else:
            backup = self._new_backup_dir(self.current)
            try:
                shutil.copy2(exe, backup / exe.name)
            except OSError as exc:
                shutil.rmtree(backup, ignore_errors=True)
                raise UpdateError(f"Die alte Version liess sich nicht sichern ({exc}) - nichts geaendert.") from exc
        if self.inplace:
            self.pending_exe = new_exe
            return backup
        try:
            _retry(lambda: os.replace(new_exe, exe))
        except OSError as exc:
            shutil.rmtree(backup, ignore_errors=True)
            raise UpdateError(f"Die neue KI.exe konnte nicht eingesetzt werden ({exc}) - alte Version bleibt.") from exc
        return backup

    def take_install_failure(self) -> str | None:
        """Hat der Update-Helfer die neue Version nicht einsetzen koennen? Meldung (einmalig)."""
        message = self._state().get("einspielen_fehlgeschlagen")
        if message:
            state = self._state()
            state.pop("einspielen_fehlgeschlagen", None)
            state.pop("letzte_pruefung", None)  # gleich wieder nachschauen duerfen
            self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        return message or None

    def _new_backup_dir(self, version: str) -> Path:
        stamp = self.now().strftime("%Y-%m-%d_%H%M%S")
        path = self.root / BACKUP_DIR / f"{_safe(version)}_{stamp}"
        suffix = 1
        while path.exists():
            suffix += 1
            path = self.root / BACKUP_DIR / f"{_safe(version)}_{stamp}-{suffix}"
        path.mkdir(parents=True)
        return path

    def _backup_source(self, incoming: set[str]) -> Path:
        """Sichert alle Programmdateien, die das Update/die Wiederherstellung beruehrt."""
        dest = self._new_backup_dir(self.current)
        for rel in sorted(program_files(self.root)):
            if not (rel.startswith(_CODE_DIRS) or rel in incoming):
                continue  # eigene Dateien im Programmordner bleiben ohnehin unangetastet
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.root / rel, target)
        return dest

    def _replace_or_rollback(self, new_root: Path, backup: Path) -> None:
        """Dateien ersetzen; bricht das mittendrin ab, wird die Sicherung zurueckgespielt."""
        try:
            self._replace_files(new_root)
        except Exception as exc:
            try:
                self._replace_files(backup)
            except Exception:  # noqa: BLE001
                logger.exception("Zuruecksetzen nach fehlgeschlagenem Update")
                raise UpdateError(
                    f"Update abgebrochen ({exc}). Die alte Version liegt in "
                    f"{backup.relative_to(self.root).as_posix()}/ - /zurueck 1 stellt sie wieder her."
                ) from exc
            shutil.rmtree(backup, ignore_errors=True)
            raise UpdateError(f"Update abgebrochen ({exc}) - die bisherige Version ist unveraendert.") from exc

    def _replace_files(self, new_root: Path) -> None:
        old_files = program_files(self.root)
        new_files = program_files(new_root)
        for rel in sorted(new_files):
            target = self.root / rel
            if rel in _CREATE_ONLY and target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(new_root / rel, target)
        for rel in sorted(old_files - new_files):
            if rel.startswith(_CODE_DIRS):
                (self.root / rel).unlink(missing_ok=True)

    def _pip_install(self, say: Callable[[str], None]) -> None:
        if self.frozen:
            return
        say("Installiere neue Pakete (requirements.txt) …")
        result = self.run(
            [sys.executable, "-m", "pip", "install", "-r", str(self.root / "requirements.txt")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            tail = "\n".join((result.stdout or "").splitlines()[-5:] + (result.stderr or "").splitlines()[-5:])
            say("Achtung: Beim Installieren der Pakete gab es einen Fehler:\n" + tail)

    def _prune(self) -> None:
        keep = max(1, int(self.settings.alte_versionen_behalten or 1))
        for old in self.backups()[keep:]:
            shutil.rmtree(old.path, ignore_errors=True)

    # -- Alte Versionen -----------------------------------------------------
    def backups(self) -> list[Backup]:
        """Gesicherte Versionen, neueste zuerst."""
        folder = self.root / BACKUP_DIR
        if not folder.is_dir():
            return []
        result = []
        for path in folder.iterdir():
            if path.is_dir():
                version = _backup_version(path) or path.name.split("_", 1)[0]
                result.append(Backup(name=path.name, version=version, path=path))
        return sorted(result, key=lambda b: b.name.split("_", 1)[-1], reverse=True)

    def restore(self, choice: str, say: Callable[[str], None] = print) -> str:
        """Stellt eine gesicherte Version wieder her (die jetzige wird vorher gesichert)."""
        backups = self.backups()
        chosen = None
        if choice.strip().isdigit() and 1 <= int(choice) <= len(backups):
            chosen = backups[int(choice) - 1]
        else:
            chosen = next((b for b in backups if b.name == choice.strip() or b.version == choice.strip()), None)
        if chosen is None:
            raise UpdateError(f"Keine gesicherte Version '{choice}' gefunden. /versionen zeigt alle.")

        self.current_before_install = self.current
        if self.frozen:
            old_exe = chosen.path / self.exe_path.name
            if not old_exe.is_file():
                raise UpdateError("In dieser Sicherung liegt keine KI.exe.")
            new_exe = self.exe_path.with_name(self.exe_path.name + ".neu")
            shutil.copy2(old_exe, new_exe)
            backup = self._swap_exe(new_exe)
        else:
            if (self.root / ".git").exists():
                raise UpdateError("Dieser Ordner ist ein Git-Checkout - bitte mit git zurueckwechseln.")
            if not (chosen.path / "assistant" / "__init__.py").is_file():
                raise UpdateError("Diese Sicherung ist unvollstaendig.")
            backup = self._backup_source(program_files(chosen.path))
            self._replace_or_rollback(chosen.path, backup)
        say(f"Version {self.current} gesichert in {backup.relative_to(self.root).as_posix()}/")
        # Sonst wuerde die automatische Pruefung gleich wieder auf die neueste wechseln.
        self._save_state(automatik_pausiert=True, installiert=chosen.version)
        self._prune()
        return (
            f"Version {chosen.version} ist wiederhergestellt. Automatische Updates sind "
            "pausiert, bis du /update eingibst."
        )

    # -- Neustart -----------------------------------------------------------
    def restart_exe(self, extra_args: list[str] | None = None) -> None:
        """Startet die (neue) KI.exe in einem neuen Fenster (z.B. mit --app). Wartet eine neue
        Version aufs Einsetzen, macht das ein Helfer, sobald diese KI beendet ist."""
        if self.pending_exe is not None:
            from .austausch import replace_by_moving, start_helper

            pending, self.pending_exe = self.pending_exe, None
            if not pending.is_file():  # z.B. Virenscanner: nicht so tun, als kaeme die neue Version
                self._save_state(installiert=self.current_before_install)
                raise UpdateError("Die neue Version ist verschwunden (Virenscanner?) - die bisherige "
                                  "laeuft weiter. Versuch es spaeter mit /update noch einmal.")
            try:
                start_helper(self.exe_path, pending, extra_args, root=self.root)
                return
            except OSError as exc:
                logger.warning("Update-Helfer startet nicht (%s) - setze die neue Version direkt ein.", exc)
                if not replace_by_moving(pending, self.exe_path):
                    raise UpdateError("Die neue Version liess sich nicht einsetzen - die bisherige "
                                      "laeuft weiter.") from exc
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        # Ohne das haelt PyInstaller (>= 6.9) den neuen Prozess fuer einen Helfer der
        # alten KI.exe und nutzt deren entpackte Dateien - die gleich geloescht werden.
        env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI_")}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        env["KI_NEUSTART_VON"] = str(os.getpid())  # die neue KI wartet, bis diese sich beendet
        subprocess.Popen([str(self.exe_path), *(extra_args or [])], cwd=str(self.exe_path.parent),
                         creationflags=flags, env=env)


def _retry(action: Callable[[], None], attempts: int = 5, delay: float = 0.5) -> None:
    """Windows: Virenscanner sperren frische Dateien oft kurz - ein paar Mal versuchen."""
    import time

    for attempt in range(attempts):
        try:
            action()
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


def _safe(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z.\-]+", "-", text).strip("-") or "unbekannt"


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _backup_version(path: Path) -> str | None:
    init = path / "assistant" / "__init__.py"
    if init.is_file():
        return read_version(init.read_text(encoding="utf-8", errors="replace"))
    return None


def _extract_zip(data: bytes, tmp: Path) -> Path:
    """Entpackt das GitHub-Zip (oberster Ordner 'owner-repo-sha/') nach tmp/neu."""
    import io

    target = tmp / "neu"
    target.mkdir()
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UpdateError("Der Download ist kein gueltiges Zip - nichts geaendert.") from exc
    with archive:
        for member in archive.infolist():
            parts = member.filename.replace("\\", "/").split("/")[1:]  # obersten Ordner weglassen
            if not parts or not parts[-1] or member.is_dir():
                continue
            if any(p in ("", "..") for p in parts) or ":" in parts[0]:
                raise UpdateError("Unsicherer Pfad im Update-Zip - abgebrochen.")
            dest = target.joinpath(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
            mode = (member.external_attr >> 16) & 0o777
            if member.create_system == 3 and mode & 0o111:  # ausfuehrbar (start.sh)
                os.chmod(dest, dest.stat().st_mode | 0o111)
    if not (target / "assistant" / "__init__.py").is_file():
        raise UpdateError("Im Download fehlt das Programm (assistant/) - nichts geaendert.")
    return target


def friendly_check_error(exc: Exception) -> str:
    """Fehler beim Nachschauen in verstaendlichen Worten (die App zeigt sie an)."""
    text = str(exc).lower()
    status = getattr(exc, "code", None) or getattr(exc, "status", None)
    if status in (403, 429) or "rate limit" in text:
        return "GitHub laesst gerade keine Abfrage zu (zu viele Anfragen) - spaeter nochmal versuchen."
    if status == 404 or "not found" in text:
        return "Die Update-Quelle wurde nicht gefunden (Repo oder Branch falsch eingestellt?)."
    if "timed out" in text or "timeout" in text:
        return "GitHub hat nicht rechtzeitig geantwortet - spaeter nochmal versuchen."
    if any(word in text for word in ("getaddrinfo", "name or service", "errno -3", "errno 11001",
                                     "network is unreachable", "connection refused", "urlopen error")):
        return "Keine Internetverbindung - bitte pruefen und nochmal versuchen."
    if "certificate" in text or "ssl" in text:
        return "Die sichere Verbindung zu GitHub ging nicht (Zertifikat/Virenscanner?)."
    return f"Nachschauen ging nicht: {str(exc)[:160]}"
