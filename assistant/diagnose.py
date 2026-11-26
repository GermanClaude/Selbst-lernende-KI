"""Diagnose-Bericht: wenn etwas nicht geht, auf Wunsch an den Entwickler - wie ein Absturzbericht bei Spielen.

Was drin steht (nur mit Zustimmung, vorher anzusehen): Nova-Version, Betriebssystem, Prozessor, Arbeitsspeicher,
Grafikkarte, freier Platz, welches Gehirn/Modell (ohne Schluessel), die letzten Fehler und die letzten Zeilen
aus logs/ki.log und logs/absturz.log.
Was NIE drin steht: Schluessel und Passwoerter (geschwaerzt), dein Benutzername (Pfade werden zu ~),
der Rechnername, E-Mail-Adressen und Telefonnummern (geschwaerzt), Gespraeche und Gedaechtnis.

Versand ueber denselben Weg wie das Feedback (assistant/feedback.py -> Google-Apps-Skript): das Skript mailt
an das Postfach, dem es gehoert. Die App - und damit dieses Repo - kennt keine E-Mail-Adresse.
Klappt der Versand nicht, bleibt der Bericht im Feedback-Ausgang und geht spaeter raus; eine Kopie liegt
immer in data/diagnose/.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

MAX_LOG_ZEILEN = 160
MAX_TEXT = 19000   # das Feedback-Skript nimmt bis 20000 Zeichen

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_TELEFON = re.compile(r"(?<!\d)(?:\+|00)?\d[\d /-]{7,}\d")


def anonymisieren(text: str) -> str:
    """Geheimnisse, Benutzerpfade, E-Mail-Adressen und Telefonnummern unkenntlich machen."""
    from .geheimnisse import verschleiere, werte_schwaerzen

    t = werte_schwaerzen(verschleiere(text or ""))
    heim = str(Path.home())
    for variante in {heim, heim.replace("\\", "/"), heim.lower()}:
        if len(variante) > 3:
            t = t.replace(variante, "~")
    t = re.sub(r"(?i)([A-Z]:[\\/]Users[\\/])[^\\/\s]+", r"\1<name>", t)
    t = re.sub(r"(/home/|/Users/)[^/\s]+", r"\1<name>", t)
    t = _EMAIL.sub("<e-mail>", t)
    return _TELEFON.sub("<nummer>", t)


def _ram_gb() -> str:
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
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return f"{m.ullTotalPhys / 2**30:.1f} GB (frei {m.ullAvailPhys / 2**30:.1f} GB)"
        werte = dict(z.split(":", 1) for z in Path("/proc/meminfo").read_text().splitlines() if ":" in z)
        gesamt = int(werte["MemTotal"].split()[0]) / 2**20
        frei = int(werte.get("MemAvailable", "0 kB").split()[0]) / 2**20
        return f"{gesamt:.1f} GB (frei {frei:.1f} GB)"
    except Exception:  # noqa: BLE001
        return "?"


def _grafik(lauf=subprocess.run) -> str:
    if sys.platform != "win32":
        return "?"
    try:
        r = lauf(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                  "(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }) -join '; '"],
                 capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (r.stdout or "").strip()[:200] or "?"
    except Exception:  # noqa: BLE001
        return "?"


def _log_ende(pfad: Path, zeilen: int = MAX_LOG_ZEILEN) -> str:
    try:
        with open(pfad, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 200_000))
            text = f.read().decode("utf-8", errors="replace")
    except OSError:
        return "(keine Datei)"
    return "\n".join(text.splitlines()[-zeilen:])


def system_info(lauf=subprocess.run) -> dict:
    from . import __version__
    from . import sandbox

    profil = sandbox.aktiv()
    if profil is not None:                        # Sandbox: vorgegaukelte Hardware
        return {
            "Nova": __version__ + " (Sandbox-Test)",
            "System": profil.get("system", "?"),
            "Prozessor": f"{profil.get('prozessor', '?')}, {profil.get('kerne', '?')} Kerne",
            "Arbeitsspeicher": f"{profil.get('arbeitsspeicher_gb', '?')} GB (frei {profil.get('frei_gb', '?')} GB)",
            "Grafik": profil.get("grafik", "?"),
            "Speicherplatz": f"{profil.get('speicherplatz_gb', '?')} GB frei",
            "Hinweis": "simulierte Sandbox-Umgebung",
        }

    try:
        frei = shutil.disk_usage(Path.home()).free / 2**30
        platz = f"{frei:.0f} GB frei"
    except OSError:
        platz = "?"
    return {
        "Nova": __version__ + (" (KI.exe)" if getattr(sys, "frozen", False) else " (Quellcode)"),
        "System": f"{platform.system()} {platform.release()} ({platform.version()[:40]}) {platform.machine()}",
        "Python": platform.python_version(),
        "Prozessor": (platform.processor() or "?")[:80] + f", {os.cpu_count() or '?'} Kerne",
        "Arbeitsspeicher": _ram_gb(),
        "Grafik": _grafik(lauf),
        "Speicherplatz": platz,
        "Termux": "ja" if os.environ.get("TERMUX_VERSION") else "nein",
        "Cloud": "ja" if os.environ.get("NOVA_CLOUD") == "1" else "nein",
    }


def erstellen(root, beschreibung: str = "", fehler: list | None = None, gehirn: str = "",
              absturz: str = "", lauf=subprocess.run) -> str:
    """Den Bericht als Text bauen (schon anonymisiert)."""
    root = Path(root)
    teile = [f"Nova-Diagnose vom {datetime.now():%d.%m.%Y %H:%M}"]
    if beschreibung.strip():
        teile += ["", "Was nicht geht (Beschreibung):", beschreibung.strip()[:2000]]
    teile += ["", "System:"] + [f"  {k}: {v}" for k, v in system_info(lauf).items()]
    if gehirn:
        teile.append(f"  Gehirn: {gehirn}")
    if absturz:
        teile += ["", "Absturz:", absturz[-4000:]]
    if fehler:
        teile += ["", "Letzte Fehler in der App:"] + [f"  - {str(f)[:400]}" for f in fehler[-10:]]
    try:
        starts = json.loads((root / "data" / "starts.json").read_text(encoding="utf-8"))[-5:]
        teile += ["", "Letzte Starts:"] + [f"  {s.get('zeit')}: {s.get('gestartet')}" for s in starts]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    teile += ["", "logs/absturz.log (Ende):", _log_ende(root / "logs" / "absturz.log", 40),
              "", "logs/ki.log (Ende):", _log_ende(root / "logs" / "ki.log")]
    text = anonymisieren("\n".join(teile))
    if len(text) > MAX_TEXT:                       # vorne (System, Fehler) ist wichtiger als altes Log
        text = text[:MAX_TEXT - 40] + "\n... (gekuerzt)"
    return text


def speichern(root, text: str) -> Path:
    ordner = Path(root) / "data" / "diagnose"
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / f"diagnose-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    pfad.write_text(text, encoding="utf-8")
    alte = sorted(ordner.glob("diagnose-*.txt"))[:-10]       # nur die letzten 10 behalten
    for alt in alte:
        try:
            alt.unlink()
        except OSError:
            pass
    return pfad


def senden(config, text: str, post=None) -> str:
    """Ueber den Feedback-Weg an den Entwickler. Gibt eine Meldung fuer den Nutzer zurueck."""
    from . import feedback

    try:
        payload = feedback.baue_payload("bug", None, "[Diagnose-Bericht]\n" + text, "", [], "menue", config)
        url = feedback.ziel_url(config)
        ergebnis = feedback.senden(payload, url, post, root=config)
    except Exception as exc:  # noqa: BLE001
        return f"Senden ging nicht ({type(exc).__name__}) - der Bericht liegt in data/diagnose/."
    if ergebnis.status == "gesendet":
        return "Diagnose-Bericht gesendet - danke! Der Entwickler schaut sich das an."
    if not ergebnis.ok:
        return "Senden ging nicht - der Bericht liegt in data/diagnose/ (du kannst ihn auch selbst weitergeben)."
    return ("Gerade nicht erreichbar - der Bericht ist gespeichert und geht automatisch raus, sobald es "
            "klappt (eine Kopie liegt in data/diagnose/).")


def nach_absturz(absturz: str, fragen, melden=print) -> None:
    """Nova ist beim Start abgestuerzt: Bericht anlegen und - nur wenn der Nutzer ja sagt - senden.
    fragen(text) -> bool (Ja/Nein-Fenster oder Eingabe). Darf selbst nie abstuerzen."""
    try:
        from .config import PROJECT_ROOT

        text = erstellen(PROJECT_ROOT, "Nova ist beim Start abgestuerzt.", absturz=absturz)
        pfad = speichern(PROJECT_ROOT, text)
    except Exception:  # noqa: BLE001
        return
    try:
        if not fragen("Soll ich einen Diagnose-Bericht an den Entwickler schicken, damit er den Fehler beheben "
                      "kann?\n\nDrin: Version, System, Hardware, Fehlermeldung, letzte Protokollzeilen. Nicht "
                      "drin: Schluessel, Benutzername, E-Mail, Gespraeche, Gedaechtnis.\n\n"
                      f"Du kannst ihn vorher ansehen: {pfad}"):
            return
        from .config import load_config

        try:
            config = load_config()
        except Exception:  # noqa: BLE001 - Einstellungen kaputt: dann nur die Datei
            melden(f"Senden ging nicht (Einstellungen nicht lesbar) - der Bericht liegt hier: {pfad}")
            return
        melden(senden(config, text))
    except Exception:  # noqa: BLE001
        pass
