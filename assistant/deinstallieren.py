"""/deinstallieren: Nova sauber entfernen - auf Wunsch mit Sicherung der Erinnerungen auf dem Desktop.

Ablauf (der Nutzer bestaetigt jeden Schritt, die KI selbst kann das nicht ausloesen - nur der Befehl):
  1. Sicherung? -> Nova-Sicherung-<Datum>.zip auf den Desktop: Gedaechtnis (JSON), Ueber mich, Persoenlichkeit,
     Skills, Zeitplan, Telefon-Persona und der Arbeitsordner (wenn er im Nova-Ordner liegt). Ohne Schluessel.
  2. Hintergrund weg: Wachwort-Lauscher + Autostart-Eintraege von Nova, Desktop-Verknuepfung.
  3. Dateien weg: nur, was Nova gehoert (Liste NOVA_TEILE) - nie fremde Dateien im selben Ordner. Weil die
     laufende KI.exe sich nicht selbst loeschen kann, macht das ein kleines Skript, nachdem Nova beendet ist.
     Aus dem Quellcode (git-Ordner) werden nur Daten und Einstellungen geloescht, der Code bleibt.
Liegt der Arbeitsordner ausserhalb des Nova-Ordners, bleibt er immer (das sind deine Dateien).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

GETEILT = ("config/ueber_mich.json", "config/persona.md", "config/skills.json", "config/anruf_persona.txt",
           "data/zeitplan.json", "config/werte.md")
# Was zu Nova gehoert (neben der KI.exe bzw. im Projektordner). Alles andere im Ordner bleibt liegen.
NOVA_TEILE = ("KI.exe", "KI-App.exe", "KI.exe.alt", "KI-App.exe.alt", "data", "config", "logs", "workspace",
              "versionen", ".env", "tools", "start.bat", "start-app.bat")
DATEN_TEILE = ("data", "config", "logs", "workspace", ".env", "versionen")


def desktop() -> Path:
    """Der echte Desktop (unter Windows evtl. in OneDrive umgeleitet); Termux: Download-Ordner."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            puffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, puffer) == 0 and puffer.value:
                return Path(puffer.value)
        except Exception:  # noqa: BLE001
            pass
    for kandidat in (Path.home() / "storage" / "downloads", Path.home() / "Desktop", Path.home() / "Schreibtisch"):
        if kandidat.is_dir():
            return kandidat
    return Path.home()


def sicherung(root, memory, workspace: Path | None = None, ziel: Path | None = None) -> Path:
    """Erinnerungen und Einstellungen als ZIP (ohne Schluessel). Gibt den Pfad zurueck."""
    root = Path(root)
    ziel = Path(ziel or desktop())
    ziel.mkdir(parents=True, exist_ok=True)
    pfad = ziel / f"Nova-Sicherung-{time.strftime('%Y-%m-%d_%H-%M')}.zip"
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        if memory is not None:
            z.writestr("gedaechtnis.json", json.dumps(memory.exportieren(max_episoden=100000), ensure_ascii=False,
                                                      indent=1))
        for rel in GETEILT:
            datei = root / rel
            if datei.is_file():
                z.write(datei, rel)
        if workspace is not None and Path(workspace).is_dir():
            ws = Path(workspace).resolve()
            for datei in ws.rglob("*"):
                if datei.is_file() and datei.stat().st_size < 200 * 2**20:
                    z.write(datei, "arbeitsordner/" + datei.relative_to(ws).as_posix())
        z.writestr("LIESMICH.txt", "Sicherung deiner Nova. Wieder einspielen: Nova neu installieren und diese Datei "
                                   "im Chat mit /sicherung einspielen <Pfad> laden - oder die Dateien von Hand in "
                                   "die Ordner config/ und data/ legen. Deine API-Schluessel sind NICHT dabei.")
    return pfad


def hintergrund_entfernen(root) -> list[str]:
    """Wachwort-Lauscher, Autostarts und Desktop-Verknuepfungen von Nova entfernen."""
    erledigt = []
    try:
        from . import wachwort

        wachwort.ausschalten(root)
        erledigt.append("Wachwort-Lauscher aus")
    except Exception:  # noqa: BLE001
        pass
    try:
        from .selbststart import entferne, finde_autostarts

        for eintrag in finde_autostarts(Path(root)):
            if eintrag.kind == "prozess" and ("nova_wachwort" not in eintrag.detail
                                             or int(eintrag.ref.get("pid") or 0) == os.getpid()):
                continue                       # laufende Prozesse: nur den Lauscher, nie Nova selbst
            try:
                entferne(eintrag, Path(root))
                erledigt.append(f"Autostart entfernt: {getattr(eintrag, 'name', eintrag)}")
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    for lnk in desktop().glob("*.lnk") if sys.platform == "win32" else []:
        try:
            if _verknuepfung_zeigt_auf(lnk, Path(root)):
                lnk.unlink()
                erledigt.append(f"Verknuepfung entfernt: {lnk.name}")
        except OSError:
            continue
    return erledigt


def _verknuepfung_zeigt_auf(lnk: Path, root: Path) -> bool:
    try:
        roh = lnk.read_bytes()
    except OSError:
        return False
    text = roh.decode("utf-16-le", errors="ignore") + roh.decode("latin-1", errors="ignore")
    return str(root.resolve()).lower() in text.lower()


def zu_loeschen(root, workspace: Path | None = None) -> list[Path]:
    """Was geloescht wird - nur Novas eigene Teile. Quellcode-Ordner (git): nur Daten/Einstellungen."""
    root = Path(root).resolve()
    namen = DATEN_TEILE if (root / ".git").exists() else NOVA_TEILE
    teile = [root / n for n in namen if (root / n).exists()]
    if workspace is not None:
        ws = Path(workspace).resolve()
        if root not in ws.parents and ws != root:   # eigener Arbeitsordner woanders: bleibt
            teile = [t for t in teile if t.resolve() != ws]
    return teile


def loesch_skript(root, teile: list[Path], warte_pid: int) -> str:
    """PowerShell (Windows) bzw. sh: wartet, bis Nova beendet ist, loescht die Teile, dann den leeren Ordner."""
    root = Path(root).resolve()
    if sys.platform == "win32":
        liste = ",".join("'" + str(t).replace("'", "''") + "'" for t in teile)
        return (f"$p={int(warte_pid)}; while (Get-Process -Id $p -ErrorAction SilentlyContinue) {{ Start-Sleep 1 }}; "
                "Start-Sleep 2; "
                f"foreach ($t in @({liste})) {{ for ($i=0; $i -lt 15; $i++) {{ try {{ Remove-Item -LiteralPath $t "
                "-Recurse -Force -ErrorAction Stop; break } catch { Start-Sleep 2 } } }; "
                f"$r='{str(root).replace(chr(39), chr(39) * 2)}'; "
                "if ((Test-Path $r) -and -not (Get-ChildItem -LiteralPath $r -Force | Select-Object -First 1)) "
                "{ Remove-Item -LiteralPath $r -Force }")
    import shlex

    teile_sh = " ".join(shlex.quote(str(t)) for t in teile)
    return (f"while kill -0 {int(warte_pid)} 2>/dev/null; do sleep 1; done; sleep 1; rm -rf -- {teile_sh}; "
            f"rmdir {shlex.quote(str(root))} 2>/dev/null; "
            "[ -n \"$PREFIX\" ] && rm -f \"$PREFIX/bin/nova\"; true")


def loeschen_starten(root, teile: list[Path], popen=subprocess.Popen) -> None:
    skript = loesch_skript(root, teile, os.getpid())
    if sys.platform == "win32":
        popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", skript],
              cwd=str(Path.home()), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0))
    else:
        popen(["sh", "-c", skript], cwd=str(Path.home()), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, start_new_session=True)


def einspielen(root, memory, zip_pfad) -> str:
    """Eine Sicherung wieder laden: Gedaechtnis zusammenfuehren, bekannte Einstellungs-Dateien zurueck."""
    root = Path(root)
    pfad = Path(str(zip_pfad).strip().strip('"'))
    if not zipfile.is_zipfile(pfad):
        return "Das ist keine Nova-Sicherung (ZIP)."
    teile = []
    with zipfile.ZipFile(pfad) as z:
        namen = set(z.namelist())
        if "gedaechtnis.json" in namen and memory is not None:
            zahlen = memory.importieren(json.loads(z.read("gedaechtnis.json").decode("utf-8")))
            teile.append(f"Gedaechtnis: {zahlen.get('neu', 0)} neu, {zahlen.get('geaendert', 0)} aktualisiert")
        for rel in GETEILT:                      # nur bekannte Dateien - nie ein fremder Pfad aus dem ZIP
            if rel in namen:
                ziel = root / rel
                ziel.parent.mkdir(parents=True, exist_ok=True)
                ziel.write_bytes(z.read(rel))
                teile.append(rel)
    return "Eingespielt: " + (", ".join(teile) if teile else "nichts gefunden")
