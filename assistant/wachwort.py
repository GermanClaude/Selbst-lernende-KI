"""Wachwort am PC: "Hey Nova" (oder ein eigenes Wort) - Nova startet bzw. kommt nach vorne, auf einem freien
Bildschirm (nicht dem mit dem Spiel), und die Spracheingabe geht gleich an (abschaltbar).

Der Lauscher ist ein kleines PowerShell-Skript mit der Spracherkennung von Windows (System.Speech, offline,
nichts geht ins Internet). Es laeuft im Hintergrund - auch wenn Nova zu ist - und startet beim Anmelden mit
(Eintrag "Nova-Wachwort" in HKCU\\...\\Run). Es hoert NUR auf das Wachwort; was du sonst sagst, wird sofort
verworfen. Hat es das Wachwort gehoert:
  * laeuft Nova schon: POST /api/aufwachen an die laufende App (Schluessel aus data/app.json)
  * sonst: Nova starten (KI-App.exe --app --aufwachen)
Die App sucht sich dann den Bildschirm aus (waehle_bildschirm) und oeffnet die Spracheingabe.

Einstellungen in data/wachwort.json: an, wort, sprechen (Spracheingabe beim Aufwachen), empfindlich.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

STANDARD = {"an": False, "wort": "Hey Nova", "sprechen": True, "empfindlich": 0.55}
RUN_SCHLUESSEL = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Nova-Wachwort"


class WachwortFehler(RuntimeError):
    pass


# ---------------------------------------------------------------- Einstellungen
def _pfad(root) -> Path:
    return Path(root) / "data" / "wachwort.json"


def laden(root) -> dict:
    try:
        daten = json.loads(_pfad(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        daten = {}
    e = dict(STANDARD)
    if isinstance(daten, dict):
        e.update({k: daten[k] for k in STANDARD if k in daten})
    return e


def speichern(root, **neu) -> dict:
    e = laden(root)
    for k, v in neu.items():
        if k in STANDARD and v is not None:
            e[k] = v
    e["wort"] = wort_pruefen(e["wort"])
    try:
        e["empfindlich"] = max(0.3, min(float(e["empfindlich"]), 0.95))
    except (TypeError, ValueError):
        e["empfindlich"] = STANDARD["empfindlich"]
    pfad = _pfad(root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    return e


def wort_pruefen(wort: str) -> str:
    """Zwei bis fuenf Woerter, nur Buchstaben - ein einzelnes kurzes Wort loest zu oft aus Versehen aus."""
    w = " ".join(re.sub(r"[^\w\s'-]", " ", str(wort or "")).split())
    if not w or any(ch.isdigit() for ch in w):
        raise WachwortFehler("Das Wachwort braucht Buchstaben, z.B. 'Hey Nova' oder 'Nova, bist du da'.")
    if len(w) < 6 or not 1 <= len(w.split()) <= 5:
        raise WachwortFehler("Nimm zwei bis fuenf Woerter (mindestens 6 Buchstaben), z.B. 'Hey Nova' - "
                             "ein kurzes Wort loest sonst dauernd aus Versehen aus.")
    return w[:60]


# ---------------------------------------------------------------- Bildschirm aussuchen
def _deckt(fenster: tuple, monitor: tuple, rand: int = 2) -> bool:
    fx1, fy1, fx2, fy2 = fenster
    mx1, my1, mx2, my2 = monitor
    return fx1 <= mx1 + rand and fy1 <= my1 + rand and fx2 >= mx2 - rand and fy2 >= my2 - rand


def waehle_bildschirm(monitore: list[dict], vollbilder: list[tuple], maus: tuple | None = None) -> int:
    """Index des Bildschirms fuer Nova. monitore: [{"rechteck": (l, o, r, u), "primaer": bool}],
    vollbilder: Rechtecke von Fenstern im Vollbild (Spiele, Videos). Vorrang: ein FREIER Bildschirm - der mit
    der Maus, sonst der Hauptbildschirm, sonst irgendeiner. Ist keiner frei: der mit der Maus."""
    if not monitore:
        return 0
    frei = [i for i, m in enumerate(monitore) if not any(_deckt(v, m["rechteck"]) for v in vollbilder)]

    def maus_index() -> int | None:
        if maus is None:
            return None
        for i, m in enumerate(monitore):
            l, o, r, u = m["rechteck"]
            if l <= maus[0] < r and o <= maus[1] < u:
                return i
        return None

    mi = maus_index()
    if mi is not None and mi in frei:
        return mi
    primaer = next((i for i, m in enumerate(monitore) if m.get("primaer")), 0)
    if primaer in frei:
        return primaer
    if frei:
        return frei[0]
    return mi if mi is not None else primaer


def fenster_position(monitor: dict, breite: int = 1200, hoehe: int = 860) -> tuple[int, int, int, int]:
    """Mitte des Arbeitsbereichs (ohne Taskleiste); passt die Groesse an kleine Bildschirme an."""
    l, o, r, u = monitor.get("arbeit") or monitor["rechteck"]
    b = min(breite, max(480, r - l - 40))
    h = min(hoehe, max(560, u - o - 40))
    return l + max(0, (r - l - b) // 2), o + max(0, (u - o - h) // 2), b, h


def bildschirme_lesen(eigene_titel: tuple[str, ...] = ()) -> tuple[list[dict], list[tuple], tuple | None]:
    """Windows: alle Bildschirme, Vollbild-Fenster und die Mausposition (ctypes, oeffnet nichts)."""
    if sys.platform != "win32":
        return [], [], None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    monitore: list[dict] = []
    MonitorEnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                         ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def je_monitor(hmon, _hdc, _rect, _lp):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            m, w = info.rcMonitor, info.rcWork
            monitore.append({"rechteck": (m.left, m.top, m.right, m.bottom),
                             "arbeit": (w.left, w.top, w.right, w.bottom), "primaer": bool(info.dwFlags & 1)})
        return True

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(je_monitor), 0)

    vollbilder: list[tuple] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def je_fenster(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        klasse = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, klasse, 64)
        if klasse.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return True
        # Einblendungen (z.B. NVIDIA-Overlay): durchsichtig, Werkzeugfenster oder nie aktiv - kein Spiel
        if user32.GetWindowLongW(hwnd, -20) & (0x20 | 0x80 | 0x08000000):
            return True
        versteckt = ctypes.c_int(0)
        try:
            ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(versteckt), 4)  # DWMWA_CLOAKED
        except Exception:  # noqa: BLE001
            pass
        if versteckt.value:
            return True
        titel = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, titel, 256)
        if not titel.value or any(titel.value.startswith(t) for t in eigene_titel if t):
            return True
        r = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(r)):
            vollbilder.append((r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumWindows(EnumWindowsProc(je_fenster), 0)
    # nur echte Vollbilder behalten (deckt einen ganzen Bildschirm inkl. Taskleiste)
    vollbilder = [v for v in vollbilder if any(_deckt(v, m["rechteck"]) for m in monitore)]
    punkt = wintypes.POINT()
    maus = (punkt.x, punkt.y) if user32.GetCursorPos(ctypes.byref(punkt)) else None
    return monitore, vollbilder, maus


def ziel_rechteck(eigene_titel: tuple[str, ...] = ()) -> tuple[int, int, int, int] | None:
    """(x, y, breite, hoehe) fuer Novas Fenster - oder None (nicht Windows / nicht lesbar)."""
    try:
        monitore, vollbilder, maus = bildschirme_lesen(eigene_titel)
    except Exception:  # noqa: BLE001
        return None
    if not monitore:
        return None
    return fenster_position(monitore[waehle_bildschirm(monitore, vollbilder, maus)])


# ---------------------------------------------------------------- Lauscher (PowerShell)
LAUSCHER = r"""
$ErrorActionPreference = 'Stop'
$root = $env:NOVA_ROOT
if (-not $root) { $root = '__ROOT__' }
$cfgPfad = Join-Path $root 'data\wachwort.json'
$status = Join-Path $root 'data\wachwort_status.json'
function Lade { try { return (Get-Content $cfgPfad -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null } }
function Melde([string]$text) {
  try { (@{ pid = $PID; status = $text; zeit = (Get-Date).ToString('s') } | ConvertTo-Json -Compress) |
        Set-Content -Path $status -Encoding UTF8 } catch { }
}
function Normal([string]$t) { return (($t.ToLowerInvariant() -replace '[^\p{L}\p{N} ]', ' ') -replace '\s+', ' ').Trim() }
$cfg = Lade
if (-not $cfg -or -not $cfg.an) { exit 0 }
$mutex = New-Object System.Threading.Mutex($false, 'Local\NovaWachwort')
if (-not $mutex.WaitOne(0)) { exit 0 }
Add-Type -AssemblyName System.Speech
$alle = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
$info = $alle | Where-Object { $_.Culture.Name -eq 'de-DE' } | Select-Object -First 1
if (-not $info) { $info = $alle | Where-Object { $_.Culture.TwoLetterISOLanguageName -eq 'de' } | Select-Object -First 1 }
if (-not $info) { $info = $alle | Select-Object -First 1 }
if (-not $info) { Melde 'kein Spracherkenner'; exit 2 }
$e = New-Object System.Speech.Recognition.SpeechRecognitionEngine($info)
function Grammatik([string]$wort) {
  $e.UnloadAllGrammars()
  $gb = New-Object System.Speech.Recognition.GrammarBuilder
  $gb.Culture = $info.Culture
  $gb.Append($wort)
  $g = New-Object System.Speech.Recognition.Grammar($gb)
  $g.Name = 'wach'
  $e.LoadGrammar($g)
  try { $d = New-Object System.Speech.Recognition.DictationGrammar; $d.Name = 'frei'; $e.LoadGrammar($d) } catch { }
}
function Wecke {
  $app = $null
  try { $app = Get-Content (Join-Path $root 'data\app.json') -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
  if ($app -and $app.pid -and $app.url -and (Get-Process -Id ([int]$app.pid) -ErrorAction SilentlyContinue)) {
    try {
      $u = [Uri][string]$app.url
      $t = ''
      if ([string]$app.url -match '[?&]t=([^&]+)') { $t = [Uri]::UnescapeDataString($Matches[1]) }
      $basis = $u.GetLeftPart([UriPartial]::Authority)
      Invoke-RestMethod -Method Post -Uri ($basis + '/api/aufwachen') -Headers @{ 'X-KI-Token' = $t } `
        -ContentType 'application/json' -Body '{}' -TimeoutSec 10 | Out-Null
      return
    } catch { }
  }
  Start-Process -FilePath '__EXE__' -ArgumentList '__ARGS__' -WorkingDirectory $root
}
$wort = [string]$cfg.wort
Grammatik $wort
$e.SetInputToDefaultAudioDevice()
Melde ('bereit ' + $info.Culture.Name)
$zuletzt = [datetime]::MinValue
while ($true) {
  $r = $null
  try { $r = $e.Recognize([TimeSpan]::FromSeconds(15)) } catch { Start-Sleep -Seconds 5 }
  $neu = Lade
  if (-not $neu -or -not $neu.an) { Melde 'aus'; break }
  if ([string]$neu.wort -ne $wort) { $wort = [string]$neu.wort; Grammatik $wort }
  if (-not $r) { continue }
  $min = 0.55
  try { $min = [double]$neu.empfindlich } catch { }
  $treffer = ($r.Grammar.Name -eq 'wach' -and $r.Confidence -ge $min) -or
             ((Normal $r.Text) -like ('*' + (Normal $wort) + '*'))
  if ($treffer -and ((Get-Date) - $zuletzt).TotalSeconds -gt 5) {
    $zuletzt = Get-Date
    Melde 'gehoert'
    Wecke
    Melde ('bereit ' + $info.Culture.Name)
  }
}
"""

PRUEFEN = r"""
Add-Type -AssemblyName System.Speech
$alle = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
($alle | ForEach-Object { $_.Culture.Name }) -join ','
"""


def _ps_text(wert: str) -> str:
    return str(wert).replace("'", "''")


def start_befehl(root) -> tuple[str, list[str]]:
    """Womit der Lauscher Nova startet: KI-App.exe (fertige App) oder pythonw -m assistant (Quellcode)."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        app = exe.with_name("KI-App.exe")
        return str(app if app.exists() else exe), ["--app", "--aufwachen"]
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    return str(pyw if pyw.exists() else py), ["-m", "assistant", "--app", "--aufwachen"]


def skript_pfad(root) -> Path:
    return Path(root) / "data" / "nova_wachwort.ps1"


def skript_schreiben(root) -> Path:
    exe, argumente = start_befehl(root)
    text = (LAUSCHER.replace("__ROOT__", _ps_text(Path(root).resolve()))
            .replace("__EXE__", _ps_text(exe)).replace("__ARGS__", _ps_text(" ".join(argumente))))
    pfad = skript_pfad(root)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(text, encoding="utf-8-sig")    # mit BOM: PowerShell 5.1 liest sonst Umlaute falsch
    return pfad


def ps_befehl(root) -> list[str]:
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-ExecutionPolicy",
            "Bypass", "-File", str(skript_pfad(root))]


def erkenner(lauf=subprocess.run) -> list[str]:
    """Installierte Windows-Spracherkenner (z.B. ['de-DE', 'en-US']). Nimmt nichts auf."""
    if sys.platform != "win32":
        return []
    try:
        r = lauf(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PRUEFEN], capture_output=True,
                 text=True, timeout=40, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [k for k in (r.stdout or "").strip().split(",") if k]


def autostart(an: bool, root=None) -> None:
    """Lauscher beim Anmelden starten (HKCU Run) - oder den Eintrag entfernen."""
    if sys.platform != "win32":
        raise WachwortFehler("Das Wachwort gibt es nur unter Windows.")
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_SCHLUESSEL, 0, winreg.KEY_SET_VALUE) as k:
        if an:
            befehl = " ".join(f'"{t}"' if " " in t else t for t in ps_befehl(root))
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, befehl)
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


def lauscher_starten(root, popen=subprocess.Popen) -> None:
    """Jetzt gleich im Hintergrund starten (ohne Fenster). Ein zweiter Start beendet sich selbst (Mutex)."""
    from .geheimnisse import umgebung_ohne_geheimnisse

    env = dict(umgebung_ohne_geheimnisse(), NOVA_ROOT=str(Path(root).resolve()))
    popen(ps_befehl(root), cwd=str(root), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
          | getattr(subprocess, "DETACHED_PROCESS", 0))


def einschalten(root, popen=subprocess.Popen) -> None:
    speichern(root, an=True)
    skript_schreiben(root)
    autostart(True, root)
    lauscher_starten(root, popen)


def ausschalten(root) -> None:
    speichern(root, an=False)          # der laufende Lauscher sieht das und beendet sich
    try:
        autostart(False)
    except (WachwortFehler, OSError):
        pass


def status_text(root) -> str:
    e = laden(root)
    try:
        st = json.loads((Path(root) / "data" / "wachwort_status.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        st = {}
    lauscht = str(st.get("status") or "")
    teile = [f"Wachwort: {'an' if e['an'] else 'aus'} ('{e['wort']}')",
             f"Spracheingabe beim Aufwachen: {'an' if e['sprechen'] else 'aus'}"]
    if e["an"]:
        teile.append("Lauscher: " + ({"kein Spracherkenner": "kein Windows-Spracherkenner installiert"}
                                    .get(lauscht, lauscht or "startet ...")))
    return " | ".join(teile)


def gestartet_vom_lauscher(root, kette_pids: set[int]) -> bool:
    """Kommt dieser Start vom eigenen Lauscher? (dann ist er erwartet - kein 'unerwarteter Start')"""
    try:
        st = json.loads((Path(root) / "data" / "wachwort_status.json").read_text(encoding="utf-8-sig"))
        return int(st.get("pid") or 0) in kette_pids
    except (OSError, ValueError, TypeError):
        return False
