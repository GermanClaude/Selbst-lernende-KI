"""Live-Systemwerte fuer das Status-Deck der App (CPU, Arbeitsspeicher, Akku, Laufzeit).

Ohne Zusatzpakete: unter Windows ueber kernel32 (GetSystemTimes, GlobalMemoryStatusEx, GetSystemPowerStatus,
GetTickCount64), unter Linux/Android ueber /proc. Sehr billig (keine Prozesse, kein PowerShell) und hoechstens
alle 1,5 Sekunden wirklich gemessen - das Fenster fragt alle paar Sekunden, der PC merkt davon nichts.
In einer Sandbox-Nova (NOVA_SIM_HW) werden die vorgegaukelten Hardware-Namen gezeigt, die Messwerte bleiben echt.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

_lock = threading.Lock()
_letzte_cpu: tuple[float, float] | None = None     # (leerlauf, gesamt) der letzten Messung
_cache: tuple[float, dict] | None = None
CACHE_SEKUNDEN = 1.5


def _cpu_zeiten() -> tuple[float, float] | None:
    """(Leerlauf, Gesamt) seit Systemstart - Einheit egal, es zaehlen nur Differenzen."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            leer, kern, nutzer = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(leer), ctypes.byref(kern), ctypes.byref(nutzer)):
                return None

            def zahl(ft):
                return (ft.dwHighDateTime << 32) | ft.dwLowDateTime
            return float(zahl(leer)), float(zahl(kern) + zahl(nutzer))     # Kernzeit enthaelt den Leerlauf
        teile = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
        werte = [float(x) for x in teile]
        return werte[3] + (werte[4] if len(werte) > 4 else 0.0), sum(werte)
    except Exception:  # noqa: BLE001
        return None


def _cpu_prozent() -> float | None:
    global _letzte_cpu
    jetzt = _cpu_zeiten()
    if jetzt is None:
        return None
    vorher, _letzte_cpu = _letzte_cpu, jetzt
    if vorher is None:
        time.sleep(0.12)                     # erste Messung: kurz zweimal messen
        return _cpu_prozent()
    d_leer, d_ges = jetzt[0] - vorher[0], jetzt[1] - vorher[1]
    if d_ges <= 0:
        return None
    return round(max(0.0, min(100.0, 100.0 * (1.0 - d_leer / d_ges))), 1)


def _speicher() -> tuple[float, float] | None:
    """(belegt in Prozent, gesamt in GB)."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) or not m.ullTotalPhys:
                return None
            return round(100.0 * (1 - m.ullAvailPhys / m.ullTotalPhys), 1), round(m.ullTotalPhys / 2**30, 1)
        werte = dict(z.split(":", 1) for z in Path("/proc/meminfo").read_text().splitlines() if ":" in z)
        gesamt = int(werte["MemTotal"].split()[0])
        frei = int(werte.get("MemAvailable", "0 kB").split()[0])
        return round(100.0 * (1 - frei / gesamt), 1), round(gesamt / 2**20, 1)
    except Exception:  # noqa: BLE001
        return None


def _akku() -> tuple[int, bool] | None:
    """(Ladestand in Prozent, am Netz?) - None ohne Akku (Desktop-PC)."""
    try:
        if sys.platform == "win32":
            import ctypes

            class PS(ctypes.Structure):
                _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                            ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                            ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
            s = PS()
            if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
                return None
            if s.BatteryFlag & 128 or s.BatteryLifePercent > 100:       # 128 = kein Akku, 255 = unbekannt
                return None
            return int(s.BatteryLifePercent), s.ACLineStatus == 1
        basis = Path("/sys/class/power_supply")
        for d in sorted(basis.glob("BAT*")) + sorted(basis.glob("battery")):
            stand = int((d / "capacity").read_text().strip())
            status = (d / "status").read_text().strip().lower()
            return stand, status in ("charging", "full")
    except Exception:  # noqa: BLE001
        return None
    return None


def _laufzeit_stunden() -> float | None:
    try:
        if sys.platform == "win32":
            import ctypes

            f = ctypes.windll.kernel32.GetTickCount64
            f.restype = ctypes.c_ulonglong
            return round(f() / 3_600_000, 1)
        return round(float(Path("/proc/uptime").read_text().split()[0]) / 3600, 1)
    except Exception:  # noqa: BLE001
        return None


def _hardware_name() -> str:
    sim = os.environ.get("NOVA_SIM_HW", "")
    if sim:
        try:
            p = json.loads(sim)
            return str(p.get("cpu") or p.get("name") or "Sandbox")[:60]
        except ValueError:
            return "Sandbox"
    return ""


def messen(jetzt: float | None = None) -> dict:
    """Alle Werte auf einmal (zwischengespeichert). Fehlt etwas, steht None da - das Fenster zeigt dann '–'."""
    global _cache
    jetzt = jetzt or time.monotonic()
    with _lock:
        if _cache and jetzt - _cache[0] < CACHE_SEKUNDEN:
            return dict(_cache[1])
        speicher = _speicher()
        akku = _akku()
        werte = {
            "cpu": _cpu_prozent(),
            "ram": speicher[0] if speicher else None,
            "ram_gb": speicher[1] if speicher else None,
            "akku": akku[0] if akku else None,
            "am_netz": akku[1] if akku else None,
            "laufzeit_h": _laufzeit_stunden(),
            "kerne": os.cpu_count(),
            "hardware": _hardware_name(),
        }
        _cache = (jetzt, werte)
        return dict(werte)
