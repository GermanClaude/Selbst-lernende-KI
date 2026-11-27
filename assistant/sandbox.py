"""Sandbox-Nova ("KI-VM"): eine frische Nova zum Testen - ohne Gedaechtnis, mit vorgegaukelter Hardware/Software,
aber mit den API-Schluesseln der echten Nova (sie ist also eingerichtet, faengt aber bei null an).

Jede Sandbox laeuft in ihrem eigenen Ordner (data/simulationen/<id>/): leeres data/ (frisches Gedaechtnis),
eine Kopie der .env (Schluessel geerbt), und NOVA_SIM_HW = ein zufaelliges Hardware-Profil, das die KI ueber
system_info/Diagnose sieht. So hat sie jedes Mal einen anderen, sauberen Stand.

Wie viele gleichzeitig? Ohne Premium 1, Premium 10, Premium Max unbegrenzt. Das Limit prueft der Code (nicht
die KI selbst) - ohne gueltige Lizenz laesst es sich nicht hochsetzen.
"""
from __future__ import annotations

import json
import os
import random
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

GRENZEN = {None: 1, "premium": 10, "max": 9999, "dev": 9999}   # gleichzeitig offene Sandboxen je Stufe
_CPUS = ["AMD Ryzen 5 5600X", "AMD Ryzen 7 7800X3D", "Intel Core i5-12400F", "Intel Core i7-13700K",
         "Intel Core i9-14900K", "AMD Ryzen 9 7950X", "Apple M2", "Intel Core i3-10100"]
_GPUS = ["NVIDIA GeForce RTX 3060", "NVIDIA GeForce RTX 4070", "AMD Radeon RX 6700 XT", "Intel Arc A750",
         "NVIDIA GeForce GTX 1660", "AMD Radeon RX 7900 XT", "NVIDIA GeForce RTX 4090"]
_OS = ["Windows 10 Pro (19045)", "Windows 11 Home (22631)", "Windows 11 Pro (26100)"]
_ORTE = ["Hamburg", "Muenchen", "Berlin", "Koeln", "Wien", "Zuerich", "Leipzig", "Dresden"]


def hardware_profil(seed: str | None = None) -> dict:
    r = random.Random(seed or secrets.token_hex(8))
    ram = r.choice([8, 16, 16, 32, 32, 64])
    return {
        "prozessor": r.choice(_CPUS), "kerne": r.choice([4, 6, 8, 12, 16]),
        "grafik": r.choice(_GPUS), "arbeitsspeicher_gb": ram, "frei_gb": round(ram * r.uniform(0.2, 0.7), 1),
        "system": r.choice(_OS), "rechnername": "PC-" + secrets.token_hex(2).upper(),
        "speicherplatz_gb": r.choice([256, 512, 512, 1024, 2048]), "ort": r.choice(_ORTE),
    }


def aktiv() -> dict | None:
    """Laeuft DIESE Nova als Sandbox? Dann das Profil, sonst None."""
    roh = os.environ.get("NOVA_SIM_HW", "").strip()
    if not roh or os.environ.get("NOVA_SIM") != "1":
        return None
    try:
        return json.loads(roh)
    except ValueError:
        return None


def system_info_text(profil: dict) -> str:
    return (f"Betriebssystem: {profil.get('system', '?')}\n"
            f"Rechnername: {profil.get('rechnername', '?')}\n"
            f"Prozessor: {profil.get('prozessor', '?')} ({profil.get('kerne', '?')} Kerne)\n"
            f"Grafik: {profil.get('grafik', '?')}\n"
            f"Arbeitsspeicher: {profil.get('arbeitsspeicher_gb', '?')} GB "
            f"(frei {profil.get('frei_gb', '?')} GB)\n"
            f"Speicherplatz: {profil.get('speicherplatz_gb', '?')} GB\n"
            f"Ungefaehrer Ort: {profil.get('ort', '?')}\n"
            f"[Sandbox-Nova - Testbetrieb, frisches Gedaechtnis. Diese Angaben sind simuliert.]")


# ---------------------------------------------------------------- Verzeichnis + Zaehlung
def _basis(root) -> Path:
    return Path(root) / "data" / "simulationen"


def offene(root) -> list[dict]:
    """Laufende Sandboxen (nach ihrer sim.json, deren Prozess noch lebt)."""
    aus = []
    for ordner in sorted(_basis(root).glob("*")):
        info = ordner / "sim.json"
        try:
            d = json.loads(info.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _lebt(int(d.get("pid") or 0)):
            aus.append(d)
    return aus


def _lebt(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                                 timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            return str(pid) in out
        except (OSError, subprocess.SubprocessError):
            return True   # im Zweifel als laufend zaehlen (lieber eine zu wenig erlauben)
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def aufraeumen(root) -> None:
    """Ordner beendeter Sandboxen wegraeumen."""
    for ordner in _basis(root).glob("*"):
        info = ordner / "sim.json"
        try:
            d = json.loads(info.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        if not _lebt(int(d.get("pid") or 0)):
            shutil.rmtree(ordner, ignore_errors=True)


# ---------------------------------------------------------------- Starten
def grenze(stufe: str | None) -> int:
    return GRENZEN.get(stufe, GRENZEN[None])


def starten(config, stufe: str | None, spawn=None, env_setzen=None, auftrag: str = "") -> dict:
    """Eine neue Sandbox-Nova starten. Wirft RuntimeError, wenn das Limit erreicht ist.
    spawn(root, env): startet die App (fuer Tests ersetzbar)."""
    root = Path(config.project_root)
    aufraeumen(root)
    laufen = offene(root)
    limit = grenze(stufe)
    if len(laufen) >= limit:
        wie = {None: "Ohne Premium", "premium": "Mit Premium", "max": "Mit Premium Max"}.get(stufe, "")
        raise RuntimeError(f"{wie} darfst du {limit} Sandbox(en) gleichzeitig offen haben - es laufen schon "
                           f"{len(laufen)}. Schliess eine, oder schalte eine hoehere Stufe frei (/novaaiupdate).")
    sid = time.strftime("%H%M%S") + "-" + secrets.token_hex(2)
    ordner = _basis(root) / sid
    (ordner / "data").mkdir(parents=True, exist_ok=True)
    (ordner / "config").mkdir(parents=True, exist_ok=True)
    quelle_env = root / ".env"
    if quelle_env.is_file():
        shutil.copyfile(quelle_env, ordner / ".env")      # nur die Schluessel erben - kein Gedaechtnis, keine Persona
    for name in ("settings.toml",):
        q = root / "config" / name
        if q.is_file():
            shutil.copyfile(q, ordner / "config" / name)
    if auftrag and auftrag.strip():
        (ordner / "data" / "sim_auftrag.txt").write_text(auftrag.strip()[:8000], encoding="utf-8")
    profil = hardware_profil(sid)
    umgebung = dict(os.environ)
    umgebung.update({"NOVA_ROOT_OVERRIDE": str(ordner), "NOVA_SIM": "1", "NOVA_SIM_HW": json.dumps(profil),
                     "NOVA_CLOUD": "0", "TELEGRAM_AUTOSTART": "0"})
    umgebung.pop("NOVA_UPDATE_TOKEN", None)
    umgebung.pop("NOVA_PREMIUM_TOKEN", None)
    if env_setzen:
        env_setzen(umgebung)
    pid = (spawn or _spawn_app)(ordner, umgebung)
    (ordner / "sim.json").write_text(json.dumps({"id": sid, "pid": pid, "profil": profil,
                                                 "gestartet": time.time()}), encoding="utf-8")
    return {"id": sid, "pid": pid, "profil": profil, "ordner": str(ordner), "offen": len(laufen) + 1,
            "limit": limit, "auftrag": bool(auftrag and auftrag.strip())}


def auftrag_lesen(root) -> str:
    """Einmaliger Start-Auftrag fuer eine Sandbox-Nova (/simulate) - danach geloescht."""
    if aktiv() is None:
        return ""
    p = Path(root) / "data" / "sim_auftrag.txt"
    try:
        text = p.read_text(encoding="utf-8").strip()
        p.unlink(missing_ok=True)
        return text
    except OSError:
        return ""


def _spawn_app(ordner: Path, umgebung: dict) -> int:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        app = exe.with_name("KI-App.exe")
        cmd = [str(app if app.exists() else exe), "--app"]
        umgebung = {k: v for k, v in umgebung.items() if not k.startswith("_PYI_")}
        umgebung["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    else:
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        cmd = [str(pyw if (sys.platform == "win32" and pyw.exists()) else exe), "-m", "assistant", "--app"]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    p = subprocess.Popen(cmd, cwd=str(ordner), env=umgebung, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=flags if sys.platform == "win32" else 0,
                         start_new_session=sys.platform != "win32")
    return p.pid


def stoppen(root, sid: str = "") -> int:
    """Eine Sandbox (oder alle) beenden. Gibt zurueck, wie viele beendet wurden."""
    n = 0
    for d in offene(root):
        if sid and d.get("id") != sid:
            continue
        pid = int(d.get("pid") or 0)
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10)
            else:
                os.kill(pid, 15)
            n += 1
        except (OSError, subprocess.SubprocessError):
            pass
    aufraeumen(root)
    return n
