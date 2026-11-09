"""Sicherheits-Check: sucht Spuren von Malware, Spyware, Trojanern und Infostealern.

Nur lesen - hier wird nie etwas geloescht, verschoben oder veraendert. Ablauf:

  1. sammeln()   - ein PowerShell-Skript sammelt Rohdaten (Windows-Defender-Status und -Funde,
                   Autostarts, geplante Aufgaben, laufende Programme, neue Programmdateien,
                   Netzwerkverbindungen, hosts-Datei)
  2. signaturen()- prueft bei verdaechtigen Kandidaten die digitale Signatur
  3. bewerten()  - Faustregeln machen daraus nummerierte Funde (hoch / mittel / niedrig)
  4. bericht()   - Text fuer Nova und fuer dich; Nova bewertet die Funde danach fachlich

datei_pruefen() prueft eine einzelne Datei (Signatur, SHA256, Windows Defender ohne Bereinigen).
Die Faustregeln sind bewusst vorsichtig: Sie liefern Hinweise, keine Urteile.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .logging_setup import get_logger

logger = get_logger()

STUFEN = ("hoch", "mittel", "niedrig")
STUFE_TEXT = {"hoch": "HOCH", "mittel": "MITTEL", "niedrig": "niedrig"}

# Programmdateien und Skripte, die bei neuen Dateien interessant sind.
ENDUNGEN = (".exe", ".dll", ".scr", ".com", ".pif", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse",
            ".wsf", ".hta", ".lnk", ".msi", ".jar")
_PROGRAMM_ENDUNGEN = (".exe", ".dll", ".scr", ".com", ".pif", ".msi")

# Echte Windows-Programme - liegen sie woanders, ist das eine bekannte Tarnung.
_SYSTEM_NAMEN = {"svchost.exe", "lsass.exe", "csrss.exe", "winlogon.exe", "services.exe", "smss.exe",
                 "wininit.exe", "explorer.exe", "rundll32.exe", "dllhost.exe", "conhost.exe", "taskhostw.exe",
                 "spoolsv.exe", "lsm.exe", "dwm.exe", "sihost.exe", "ctfmon.exe", "runtimebroker.exe",
                 "searchindexer.exe", "wuauclt.exe", "msmpeng.exe"}
_SKRIPT_HOSTS = {"wscript.exe", "cscript.exe", "mshta.exe", "powershell.exe", "pwsh.exe", "cmd.exe",
                 "regsvr32.exe", "rundll32.exe"}

# Typische Muster in Autostarts von Schadsoftware (versteckte/verschluesselte Befehle, Nachladen aus dem Netz).
_GEFAEHRLICHE_BEFEHLE = [
    (re.compile(r"-e(nc(odedcommand)?)?\s+[A-Za-z0-9+/=]{20,}", re.I), "verschluesselter PowerShell-Befehl"),
    (re.compile(r"\b(iex|invoke-expression)\b", re.I), "fuehrt nachgeladenen Code aus (Invoke-Expression)"),
    (re.compile(r"downloadstring|downloadfile|invoke-webrequest|\biwr\b|net\.webclient|start-bitstransfer",
                re.I), "laedt etwas aus dem Internet nach"),
    (re.compile(r"frombase64string", re.I), "entschluesselt versteckten Inhalt (Base64)"),
    (re.compile(r"-w(indowstyle)?\s+h(idden)?\b", re.I), "startet unsichtbar (verstecktes Fenster)"),
    (re.compile(r"-ex(ecutionpolicy)?\s+bypass", re.I), "umgeht die Skript-Sperre (ExecutionPolicy Bypass)"),
    (re.compile(r"mshta(\.exe)?\s+\S*(https?:|javascript:|vbscript:)", re.I), "mshta mit Internet-/Skript-Code"),
    (re.compile(r"regsvr32(\.exe)?.*(/i:\s*https?:|scrobj)", re.I), "regsvr32-Trick (laedt Code aus dem Netz)"),
    (re.compile(r"rundll32(\.exe)?.*javascript:", re.I), "rundll32 mit Skript-Code"),
    (re.compile(r"certutil(\.exe)?.*-(urlcache|decode)", re.I), "certutil zum Herunterladen/Entschluesseln"),
    (re.compile(r"bitsadmin(\.exe)?.*/transfer", re.I), "bitsadmin zum Herunterladen"),
    (re.compile(r"\b(curl|wget)(\.exe)?\b.*https?://", re.I), "laedt mit curl/wget aus dem Internet"),
]
# Namen, hinter denen sich oft Schadsoftware versteckt (Cheats, Cracks, "kostenlose" Extras).
_TARN_NAMEN = re.compile(
    r"crack|keygen|cheat|inject|loader|activat|kmspico|\bkms\b|hack|executor|spoofer|bypass|unlocker|"
    r"free[-_ .]?(robux|vbucks|nitro)|nitro[-_ .]?gen|generator|aimbot|wallhack|trainer|mod[-_ .]?menu", re.I)
_DOPPELTE_ENDUNG = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|jpe?g|png|gif|txt|mp3|mp4|avi|mkv|zip|rar|7z)"
                              r"\s*\.(exe|scr|com|pif|bat|cmd|js|jse|vbs|vbe|hta|lnk)$", re.I)
_ZUFALLS_NAME = re.compile(r"^(?=.*\d)(?=.*[a-z])[a-z0-9]{10,}$|^[a-f0-9]{8,}$", re.I)
# Geheimnisse in Befehlszeilen (Tokens, Passwoerter) nie an die KI.
_GEHEIM = [
    (re.compile(r"(?i)((?:pass(?:word|wort)?|pwd|token|secret|api[-_]?key|key)\s*[=:]\s*)\S+"), r"\1…"),
    (re.compile(r"(?<![A-Za-z0-9+/_\-])[A-Za-z0-9+/_\-]{40,}={0,2}"), "…"),
]
_SPEICHER_ORDNER = "sicherheit"


@dataclass
class Fund:
    stufe: str                 # "hoch" | "mittel" | "niedrig"
    bereich: str               # "Virenschutz", "Autostart", "Aufgabe", "Programm", "Datei", "Netzwerk", "hosts"
    titel: str
    pfad: str = ""
    gruende: list[str] = field(default_factory=list)

    def zeilen(self, nummer: int) -> list[str]:
        kopf = f"[{nummer}] {STUFE_TEXT.get(self.stufe, self.stufe)} - {self.bereich}: {self.titel}"
        aus = [kopf]
        if self.pfad and self.pfad not in self.titel:
            aus.append(f"     Ort: {self.pfad}")
        aus += [f"     - {g}" for g in self.gruende]
        return aus


# ---------------------------------------------------------------------------
#  Hilfen
# ---------------------------------------------------------------------------
def geheimnisse_entfernen(text: str) -> str:
    text = text or ""
    for muster, ersatz in _GEHEIM:
        text = muster.sub(ersatz, text)
    return text


def _kurz(text: str, laenge: int = 220) -> str:
    text = geheimnisse_entfernen(" ".join((text or "").split()))
    return text if len(text) <= laenge else text[: laenge - 1] + "…"


def programm_aus_befehl(befehl: str) -> str:
    """'"C:\\x\\a.exe" --flag' -> 'C:\\x\\a.exe'; auch ohne Anfuehrungszeichen und mit Leerzeichen im Pfad."""
    befehl = (befehl or "").strip()
    if not befehl:
        return ""
    if befehl.startswith('"'):
        ende = befehl.find('"', 1)
        return befehl[1:ende] if ende > 0 else befehl[1:]
    treffer = re.match(r"(.+?\.(exe|com|bat|cmd|vbs|js|ps1|scr|lnk))(\s|$)", befehl, re.I)
    if treffer:
        return treffer.group(1)
    return befehl.split()[0]


def _env_pfad(pfad: str) -> str:
    pfad = os.path.expandvars(pfad or "").strip().strip('"')
    return pfad[4:] if pfad.startswith(("\\\\?\\", "\\??\\")) else pfad  # \\?\C:\... -> C:\...


def _norm(pfad: str) -> str:
    return _env_pfad(pfad).replace("/", "\\").lower().rstrip("\\")


@dataclass
class Orte:
    """Wichtige Ordner (klein geschrieben, ohne \\ am Ende). Im Test frei vorgebbar."""

    windows: str = "c:\\windows"
    benutzer: str = ""
    temp: list[str] = field(default_factory=list)
    beschreibbar: list[str] = field(default_factory=list)  # Ordner, in die jedes Programm schreiben kann
    downloads: str = ""

    @classmethod
    def aus_umgebung(cls) -> Orte:
        profil = _norm(os.environ.get("USERPROFILE", ""))
        temp = [_norm(p) for p in (os.environ.get("TEMP", ""), os.environ.get("TMP", ""), "C:\\Windows\\Temp") if p]
        beschreibbar = [p for p in (profil, _norm(os.environ.get("ProgramData", "C:\\ProgramData")),
                                    _norm(os.environ.get("PUBLIC", "C:\\Users\\Public")), *temp) if p]
        return cls(windows=_norm(os.environ.get("SystemRoot", "C:\\Windows")), benutzer=profil,
                   temp=sorted(set(temp)), beschreibbar=sorted(set(beschreibbar)),
                   downloads=profil + "\\downloads" if profil else "")

    def unter(self, pfad: str, ordner: str) -> bool:
        p = _norm(pfad)
        return bool(ordner) and (p == ordner or p.startswith(ordner + "\\"))

    def in_temp(self, pfad: str) -> bool:
        return any(self.unter(pfad, t) for t in self.temp)

    def im_benutzerordner(self, pfad: str) -> bool:
        return any(self.unter(pfad, b) for b in self.beschreibbar)


def _signiert(sig: dict | None) -> bool | None:
    """True = gueltig signiert, False = nicht/ungueltig signiert, None = unbekannt."""
    if not sig:
        return None
    status = str(sig.get("status", ""))
    if status == "Valid":
        return True
    if status in ("NotSigned", "HashMismatch", "NotTrusted", "Incompatible", "UnknownError"):
        return False
    return None


def _signatur_text(sig: dict | None) -> str:
    if not sig:
        return ""
    status = str(sig.get("status", ""))
    if status == "Valid":
        return f"digital signiert von {sig.get('signer') or 'unbekannt'}"
    return {"NotSigned": "nicht digital signiert", "HashMismatch": "Signatur passt nicht zur Datei (veraendert!)",
            "NotTrusted": "Signatur nicht vertrauenswuerdig"}.get(status, f"Signatur: {status}")


# ---------------------------------------------------------------------------
#  1) Sammeln (PowerShell, nur lesen)
# ---------------------------------------------------------------------------
_SAMMEL_SKRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$tage = [int]$env:NOVA_TAGE; $tiefe = [int]$env:NOVA_TIEFE; $budget = [int]$env:NOVA_SEKUNDEN
$seit = (Get-Date).AddDays(-$tage)
$r = [ordered]@{}

# Virenschutz
try {
  $s = Get-MpComputerStatus -ErrorAction Stop
  $r.defender = [ordered]@{ aktiv = [bool]$s.AntivirusEnabled; echtzeit = [bool]$s.RealTimeProtectionEnabled;
    manipulationsschutz = [bool]$s.IsTamperProtected; signaturen = [string]$s.AntivirusSignatureLastUpdated.ToString('s');
    schnellscan = $(if ($s.QuickScanEndTime) { $s.QuickScanEndTime.ToString('s') } else { '' });
    vollscan = $(if ($s.FullScanEndTime) { $s.FullScanEndTime.ToString('s') } else { '' }) }
} catch { $r.defender = $null }
$namen = @{}; Get-MpThreat | ForEach-Object { $namen[[string]$_.ThreatID] = @{ n = [string]$_.ThreatName; a = [bool]$_.IsActive; x = [bool]$_.DidThreatExecute } }
$r.defender_funde = @(Get-MpThreatDetection | Where-Object { $_.InitialDetectionTime -gt (Get-Date).AddDays(-30) } |
  Sort-Object InitialDetectionTime -Descending | Select-Object -First 40 | ForEach-Object {
    $t = $namen[[string]$_.ThreatID]
    $dateien = @($_.Resources | Where-Object { $_ -like 'file:_*' } | ForEach-Object { $_.Substring(6) })
    [ordered]@{ zeit = $_.InitialDetectionTime.ToString('s'); name = $(if ($t) { $t.n } else { [string]$_.ThreatID });
      aktiv = $(if ($t) { $t.a } else { $false }); ausgefuehrt = $(if ($t) { $t.x } else { $false });
      erfolg = [bool]$_.ActionSuccess; dateien = $dateien;
      noch_da = @($dateien | Where-Object { Test-Path -LiteralPath $_ }) } })

# Autostarts
$auto = New-Object System.Collections.ArrayList
foreach ($k in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run','HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce',
               'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run','HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce',
               'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run') {
  $p = Get-ItemProperty -LiteralPath $k
  if ($p) { $p.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object {
    [void]$auto.Add([ordered]@{ art = 'registry'; name = $_.Name; befehl = [string]$_.Value; ort = $k }) } }
}
$wl = Get-ItemProperty -LiteralPath 'HKLM:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon'
if ($wl) { [void]$auto.Add([ordered]@{ art = 'winlogon'; name = 'Shell'; befehl = [string]$wl.Shell; ort = 'Winlogon' })
           [void]$auto.Add([ordered]@{ art = 'winlogon'; name = 'Userinit'; befehl = [string]$wl.Userinit; ort = 'Winlogon' }) }
$sh = New-Object -ComObject WScript.Shell
foreach ($d in [Environment]::GetFolderPath('Startup'), [Environment]::GetFolderPath('CommonStartup')) {
  if ($d -and (Test-Path -LiteralPath $d)) { Get-ChildItem -LiteralPath $d -File -Force | Where-Object { $_.Name -ne 'desktop.ini' } | ForEach-Object {
    $b = $_.FullName
    if ($_.Extension -ieq '.lnk') { $l = $sh.CreateShortcut($_.FullName); $b = ('"' + $l.TargetPath + '" ' + $l.Arguments).Trim() }
    [void]$auto.Add([ordered]@{ art = 'ordner'; name = $_.Name; befehl = $b; ort = $d }) } }
}
Get-ScheduledTask | Where-Object { $_.TaskPath -notlike '\Microsoft\*' } | ForEach-Object {
  $t = $_
  foreach ($a in $t.Actions) { if ($a.Execute) {
    [void]$auto.Add([ordered]@{ art = 'aufgabe'; name = ($t.TaskPath + $t.TaskName); befehl = ([string]$a.Execute + ' ' + [string]$a.Arguments).Trim();
      ort = [string]$t.State }) } }
}
$r.autostart = @($auto)

# Laufende Programme
$r.prozesse = @(Get-CimInstance Win32_Process | ForEach-Object {
  $c = [string]$_.CommandLine; if ($c.Length -gt 500) { $c = $c.Substring(0, 500) }
  [ordered]@{ pid = [int]$_.ProcessId; eltern = [int]$_.ParentProcessId; name = [string]$_.Name; pfad = [string]$_.ExecutablePath; befehl = $c } })

# Netzwerk
$r.netz = @(Get-NetTCPConnection -State Listen, Established | Select-Object -First 600 | ForEach-Object {
  [ordered]@{ pid = [int]$_.OwningProcess; lokal = [string]$_.LocalAddress; port = [int]$_.LocalPort;
    gegen = [string]$_.RemoteAddress; gport = [int]$_.RemotePort; zustand = [string]$_.State } })

# hosts-Datei
$h = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
$r.hosts = @(Get-Content -LiteralPath $h | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') } | Select-Object -First 200)

# Neue Programmdateien (mit Zeitbudget)
$endungen = @('__ENDUNGEN__')
$ueberspringen = @('node_modules','.git','.venv','venv','site-packages','__pycache__','cache','code cache','gpucache',
  'packages','windowsapps','steamapps','shadercache','dxcache','nvidia','crashpad','ebwebview','service worker','indexeddb')
$uhr = [Diagnostics.Stopwatch]::StartNew()
$funde = New-Object System.Collections.ArrayList
$gesehen = @{}
function Lauf([string]$d, [int]$t) {
  if ($uhr.Elapsed.TotalSeconds -gt $budget -or $funde.Count -ge 800) { return }
  if ($gesehen.ContainsKey($d.ToLower())) { return }; $gesehen[$d.ToLower()] = 1
  try { foreach ($f in [IO.Directory]::EnumerateFiles($d)) {
    $e = [IO.Path]::GetExtension($f).ToLower()
    if ($endungen -contains $e) { $i = New-Object IO.FileInfo $f
      if ($i.CreationTime -gt $seit -or $i.LastWriteTime -gt $seit) {
        [void]$funde.Add([ordered]@{ pfad = $f; groesse = [int64]$i.Length; erstellt = $i.CreationTime.ToString('s');
          versteckt = [bool]($i.Attributes -band [IO.FileAttributes]::Hidden) }) } } } } catch {}
  if ($t -le 0) { return }
  try { foreach ($s in [IO.Directory]::EnumerateDirectories($d)) {
    if ($ueberspringen -contains ([IO.Path]::GetFileName($s)).ToLower()) { continue }
    if (([IO.File]::GetAttributes($s)) -band [IO.FileAttributes]::ReparsePoint) { continue }
    Lauf $s ($t - 1) } } catch {}
}
$profil = $env:USERPROFILE
foreach ($z in @(@((Join-Path $profil 'Downloads'), ($tiefe + 1)), @([Environment]::GetFolderPath('Desktop'), $tiefe),
                 @($env:TEMP, $tiefe), @($env:APPDATA, $tiefe), @($env:LOCALAPPDATA, $tiefe),
                 @($env:ProgramData, ($tiefe - 1)), @($env:PUBLIC, $tiefe))) {
  if ($z[0] -and (Test-Path -LiteralPath $z[0])) { Lauf $z[0] $z[1] }
}
$r.dateien = @($funde)
$r.dateien_abgebrochen = ($uhr.Elapsed.TotalSeconds -gt $budget)
$r | ConvertTo-Json -Depth 6 -Compress
"""

_SIGNATUR_SKRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$aus = @{}
foreach ($p in (Get-Content -LiteralPath $env:NOVA_LISTE -Encoding UTF8 | ConvertFrom-Json)) {
  if (Test-Path -LiteralPath $p) { $s = Get-AuthenticodeSignature -LiteralPath $p
    $n = ''; if ($s.SignerCertificate) { $n = ($s.SignerCertificate.Subject -replace '^CN=("?)([^,"]+)\1.*', '$2') }
    $aus[$p] = @{ status = [string]$s.Status; signer = $n } } else { $aus[$p] = @{ status = 'Fehlt'; signer = '' } }
}
$aus | ConvertTo-Json -Depth 3 -Compress
"""


def _powershell(skript: str, env: dict[str, str], timeout: int) -> str:
    kodiert = base64.b64encode(skript.encode("utf-16-le")).decode("ascii")
    umgebung = {**os.environ, **env}
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-EncodedCommand", kodiert],
                          capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, env=umgebung,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    text = proc.stdout.decode("utf-8", errors="replace").strip().lstrip("\ufeff")
    # Nur die letzte Zeile ist das JSON (falls doch etwas anderes ausgegeben wurde).
    zeilen = [z for z in text.splitlines() if z.strip()]
    return zeilen[-1] if zeilen else ""


def sammeln(gruendlich: bool = False) -> dict:
    if sys.platform != "win32":
        raise RuntimeError("Der Sicherheits-Check geht (vorerst) nur unter Windows.")
    skript = _SAMMEL_SKRIPT.replace("'__ENDUNGEN__'", ",".join(f"'{e}'" for e in ENDUNGEN))
    env = {"NOVA_TAGE": "30" if gruendlich else "7", "NOVA_TIEFE": "5" if gruendlich else "3",
           "NOVA_SEKUNDEN": "150" if gruendlich else "45"}
    roh = _powershell(skript, env, timeout=300 if gruendlich else 150)
    try:
        daten = json.loads(roh)
    except json.JSONDecodeError as exc:
        logger.warning("Sicherheits-Check: Ausgabe nicht lesbar: %r", roh[:300])
        raise RuntimeError("Die Daten vom PC liessen sich nicht lesen.") from exc
    return daten if isinstance(daten, dict) else {}


def signaturen(pfade: list[str]) -> dict[str, dict]:
    pfade = sorted({p for p in pfade if p})[:250]
    if not pfade or sys.platform != "win32":
        return {}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as datei:
        json.dump(pfade, datei)
        liste = datei.name
    try:
        roh = _powershell(_SIGNATUR_SKRIPT, {"NOVA_LISTE": liste}, timeout=180)
        daten = json.loads(roh) if roh else {}
        return {k.lower(): v for k, v in daten.items()} if isinstance(daten, dict) else {}
    except (json.JSONDecodeError, subprocess.TimeoutExpired):
        return {}
    finally:
        try:
            os.unlink(liste)
        except OSError:
            pass


# ---------------------------------------------------------------------------
#  2) Bewerten (Faustregeln - reine Funktionen, gut testbar)
# ---------------------------------------------------------------------------
def kandidaten(daten: dict, orte: Orte) -> list[str]:
    """Welche Dateien brauchen eine Signatur-Pruefung?"""
    pfade: list[str] = []
    for p in daten.get("prozesse") or []:
        if p.get("pfad") and orte.im_benutzerordner(p["pfad"]):
            pfade.append(p["pfad"])
    for a in daten.get("autostart") or []:
        ziel = _env_pfad(programm_aus_befehl(a.get("befehl", "")))
        if ziel and orte.im_benutzerordner(ziel):
            pfade.append(ziel)
    for d in daten.get("dateien") or []:
        if str(d.get("pfad", "")).lower().endswith(_PROGRAMM_ENDUNGEN):
            pfade.append(d["pfad"])
    return pfade


def _ist_lokal(ip: str) -> bool:
    ip = (ip or "").strip()
    return (ip in ("", "0.0.0.0", "::", "::1", "*") or ip.startswith(("127.", "10.", "192.168.", "169.254.", "fe80", "fd"))
            or bool(re.match(r"172\.(1[6-9]|2\d|3[01])\.", ip)))


def _defender_funde(daten: dict) -> list[Fund]:
    funde: list[Fund] = []
    d = daten.get("defender")
    if d is None and "defender" in daten:
        funde.append(Fund("mittel", "Virenschutz", "Windows-Defender-Status nicht lesbar",
                          gruende=["Entweder ist ein anderer Virenscanner installiert oder Defender ist abgeschaltet."]))
    elif isinstance(d, dict):
        if not d.get("aktiv"):
            funde.append(Fund("hoch", "Virenschutz", "Windows-Virenschutz ist aus",
                              gruende=["Schadsoftware schaltet den Virenschutz oft als Erstes ab."]))
        elif not d.get("echtzeit"):
            funde.append(Fund("hoch", "Virenschutz", "Echtzeitschutz ist aus",
                              gruende=["Neue Dateien werden so nicht mehr automatisch geprueft."]))
        try:
            alt = datetime.now() - datetime.fromisoformat(str(d.get("signaturen")))
            if alt > timedelta(days=7):
                funde.append(Fund("mittel", "Virenschutz", f"Virendefinitionen sind {alt.days} Tage alt",
                                  gruende=["Windows Update / Defender-Update pruefen."]))
        except ValueError:
            pass
    # Dieselbe Bedrohung in derselben Datei wird oft mehrfach erkannt -> ein Fund mit Anzahl.
    gruppen: dict[tuple[str, str], list[dict]] = {}
    for f in daten.get("defender_funde") or []:
        dateien = [p for p in (f.get("dateien") or []) if p]
        gruppen.setdefault((str(f.get("name") or "unbekannt"), (dateien or [""])[0].lower()), []).append(f)
    for (name, _datei), liste in gruppen.items():
        liste.sort(key=lambda f: str(f.get("zeit", "")))
        neueste = liste[-1]
        dateien = [p for p in (neueste.get("dateien") or []) if p]
        noch_da = [p for p in (neueste.get("noch_da") or []) if p]
        zeiten = [str(f.get("zeit", ""))[:16].replace("T", " ") for f in liste]
        gruende = ([f"erkannt am {zeiten[0]}"] if len(liste) == 1
                   else [f"{len(liste)}-mal erkannt, zuerst {zeiten[0]}, zuletzt {zeiten[-1]}"])
        if any(f.get("aktiv") for f in liste):
            stufe = "hoch"
            gruende.append("Defender meldet die Bedrohung als AKTIV (nicht bereinigt).")
        elif noch_da:
            stufe = "hoch"
            gruende.append("Die erkannte Datei liegt noch auf dem PC (vielleicht von Hand zugelassen).")
        elif any(f.get("ausgefuehrt") for f in liste):
            stufe = "mittel"
            gruende.append("Die Datei wurde ausgefuehrt, bevor Defender sie entfernt hat - sie koennte "
                           "etwas hinterlassen oder Daten abgegriffen haben.")
        else:
            stufe = "niedrig"
            gruende.append("Defender hat sie entfernt, bevor sie lief.")
        funde.append(Fund(stufe, "Virenschutz", f"Defender-Fund: {name}",
                          pfad=(noch_da or dateien or [""])[0], gruende=gruende))
    return funde


def _datei_regeln(pfad: str, orte: Orte, sig: dict | None) -> tuple[str | None, list[str]]:
    """Regeln, die fuer jede Datei gelten (Name/Ort/Signatur). -> (stufe oder None, gruende)."""
    name = Path(pfad.replace("\\", "/")).name
    low = name.lower()
    gruende: list[str] = []
    stufe: str | None = None

    def hoeher(neu: str) -> None:
        nonlocal stufe
        if stufe is None or STUFEN.index(neu) < STUFEN.index(stufe):
            stufe = neu

    if _DOPPELTE_ENDUNG.search(name):
        hoeher("hoch")
        gruende.append("doppelte Dateiendung (tarnt ein Programm als Dokument/Bild)")
    if low in _SYSTEM_NAMEN and not orte.unter(pfad, orte.windows):
        hoeher("hoch")
        gruende.append(f"traegt den Namen eines Windows-Programms ({name}), liegt aber nicht im Windows-Ordner")
    signiert = _signiert(sig)
    if orte.in_temp(pfad) and low.endswith(_PROGRAMM_ENDUNGEN) and signiert is not True:
        hoeher("mittel")
        gruende.append("Programmdatei im Temp-Ordner (beliebter Ort fuer Schadsoftware)")
    if _TARN_NAMEN.search(name):
        hoeher("mittel")
        gruende.append("Name wie Cheat/Crack/Injector/Generator - eine sehr haeufige Tarnung fuer Infostealer")
    if _ZUFALLS_NAME.match(Path(low).stem) and orte.im_benutzerordner(pfad) and low.endswith(_PROGRAMM_ENDUNGEN):
        hoeher("niedrig")
        gruende.append("zufaellig wirkender Name")
    if signiert is False and low.endswith(_PROGRAMM_ENDUNGEN):
        text = _signatur_text(sig)
        if sig and sig.get("status") == "HashMismatch":
            hoeher("hoch")
        gruende.append(text)
    return stufe, gruende


def _autostart_funde(daten: dict, orte: Orte, sigs: dict[str, dict]) -> list[Fund]:
    funde: list[Fund] = []
    for a in daten.get("autostart") or []:
        befehl = str(a.get("befehl", ""))
        art = a.get("art", "")
        bereich = "Aufgabe" if art == "aufgabe" else "Autostart"
        if art == "winlogon":
            soll = "explorer.exe" if a.get("name") == "Shell" else "userinit.exe"
            teile = [t.strip().strip('"').lower() for t in befehl.split(",") if t.strip()]
            fremd = [t for t in teile if not t.endswith(soll)]
            if fremd:
                funde.append(Fund("hoch", "Autostart", f"Windows-Anmeldung startet zusaetzlich: {_kurz(befehl)}",
                                  gruende=[f"Winlogon/{a.get('name')} sollte nur {soll} enthalten - ein klassischer "
                                           "Trick von Trojanern."]))
            continue
        ziel = _env_pfad(programm_aus_befehl(befehl))
        ziel_name = Path(ziel.replace("\\", "/")).name.lower()
        sig = sigs.get(ziel.lower())
        gruende: list[str] = []
        stufe: str | None = None
        for muster, grund in _GEFAEHRLICHE_BEFEHLE:
            if muster.search(befehl):
                stufe = "hoch"
                gruende.append(grund)
        if sig and sig.get("status") == "Fehlt" or (ziel and ":" in ziel and not sig and not os.path.exists(ziel)
                                                      and orte.im_benutzerordner(ziel)):
            stufe = stufe or "niedrig"
            gruende.append("das gestartete Programm gibt es nicht mehr (verwaister Eintrag)")
        elif ziel:
            d_stufe, d_gruende = _datei_regeln(ziel, orte, sig)
            if d_stufe:
                stufe = d_stufe if stufe is None or STUFEN.index(d_stufe) < STUFEN.index(stufe) else stufe
                gruende += d_gruende
            elif _signiert(sig) is False and orte.im_benutzerordner(ziel):
                stufe = stufe or "niedrig"
                gruende.append("startet ein nicht signiertes Programm aus einem Benutzerordner")
        if ziel_name in _SKRIPT_HOSTS and not gruende:
            skript = re.search(r"[A-Za-z]:\\[^\"']+?\.(vbs|vbe|js|jse|ps1|bat|cmd|hta|wsf)", befehl, re.I)
            if skript and orte.im_benutzerordner(skript.group(0)):
                stufe = "mittel" if orte.in_temp(skript.group(0)) else "niedrig"
                gruende.append(f"startet ein Skript aus einem Benutzerordner ({Path(skript.group(0)).name})")
        if stufe:
            ort = {"registry": "Registrierung", "ordner": "Autostart-Ordner", "aufgabe": "Aufgabenplanung"}.get(art, art)
            funde.append(Fund(stufe, bereich, f"{a.get('name')} ({ort})", pfad=_kurz(befehl), gruende=gruende))
    return funde


def _prozess_funde(daten: dict, orte: Orte, sigs: dict[str, dict], eigene: set[str]) -> list[Fund]:
    funde: list[Fund] = []
    netz: dict[int, list[dict]] = {}
    for n in daten.get("netz") or []:
        netz.setdefault(int(n.get("pid", 0)), []).append(n)
    gesehen: set[str] = set()
    for p in daten.get("prozesse") or []:
        pfad = _env_pfad(str(p.get("pfad") or ""))
        name = str(p.get("name") or "")
        if int(p.get("eltern") or 0) == os.getpid():
            continue  # unsere eigene PowerShell (dieser Check)
        if not pfad or pfad.lower() in eigene:
            # Ohne Pfad (Systemprozess / keine Rechte) - nur die Namens-Tarnung pruefen wir nicht blind.
            continue
        sig = sigs.get(pfad.lower())
        stufe, gruende = _datei_regeln(pfad, orte, sig)
        verbindungen = netz.get(int(p.get("pid", 0)), [])
        fremd = [v for v in verbindungen if v.get("zustand") == "Established" and not _ist_lokal(v.get("gegen", ""))]
        lauscht = [v for v in verbindungen if v.get("zustand") == "Listen" and v.get("lokal") in ("0.0.0.0", "::")]
        if _signiert(sig) is False and orte.im_benutzerordner(pfad):
            if fremd:
                ziele = ", ".join(sorted({f"{v['gegen']}:{v['gport']}" for v in fremd})[:4])
                stufe = stufe if stufe == "hoch" else "mittel"
                gruende.append(f"nicht signiert und hat Verbindungen ins Internet ({ziele})")
            elif lauscht:
                stufe = stufe or "niedrig"
                ports = ", ".join(sorted({str(v["port"]) for v in lauscht}))
                gruende.append(f"nicht signiert und wartet auf Verbindungen aus dem Netz (Port {ports})")
        if "-enc" in (p.get("befehl") or "").lower() or re.search(r"-w(indowstyle)?\s+h", p.get("befehl") or "", re.I):
            if name.lower() in ("powershell.exe", "pwsh.exe"):
                # Machen auch viele normale Programme (Entwickler-Tools) - darum "mittel".
                stufe = stufe if stufe == "hoch" else "mittel"
                gruende.append("PowerShell laeuft versteckt/verschluesselt: " + _kurz(p.get("befehl", ""), 160))
        if stufe and pfad.lower() not in gesehen:
            gesehen.add(pfad.lower())
            funde.append(Fund(stufe, "Programm", f"laeuft gerade: {name} (PID {p.get('pid')})", pfad=pfad,
                              gruende=gruende))
    return funde


def _datei_funde(daten: dict, orte: Orte, sigs: dict[str, dict], schon: set[str]) -> list[Fund]:
    funde: list[Fund] = []
    temp_skripte: list[str] = []
    for d in daten.get("dateien") or []:
        pfad = str(d.get("pfad", ""))
        if not pfad or pfad.lower() in schon:
            continue
        low = pfad.lower()
        stufe, gruende = _datei_regeln(pfad, orte, sigs.get(low))
        if not stufe and orte.in_temp(pfad) and low.endswith((".ps1", ".bat", ".cmd", ".vbs", ".vbe", ".js", ".jse",
                                                                 ".hta", ".wsf")):
            temp_skripte.append(pfad)  # meist Hilfsskripte von Programmen -> ein Sammel-Eintrag
            continue
        if low.endswith(".scr"):
            stufe = stufe or "mittel"
            gruende.append("Bildschirmschoner-Datei (.scr) - ist in Wahrheit ein Programm")
        if low.endswith((".hta", ".vbs", ".vbe", ".js", ".jse", ".wsf")) and orte.unter(pfad, orte.downloads):
            stufe = stufe or "mittel"
            gruende.append("Skript-Datei aus den Downloads - ein haeufiger Weg fuer Trojaner")
        if d.get("versteckt") and low.endswith(_PROGRAMM_ENDUNGEN):
            stufe = stufe or "niedrig"
            gruende.append("versteckte Programmdatei")
        if stufe:
            zeit = str(d.get("erstellt", ""))[:16].replace("T", " ")
            groesse = int(d.get("groesse") or 0)
            gruende.insert(0, f"neu seit {zeit}, {groesse / 1024 / 1024:.1f} MB")
            funde.append(Fund(stufe, "Datei", Path(pfad.replace("\\", "/")).name, pfad=pfad, gruende=gruende))
    if temp_skripte:
        namen = [Path(p.replace("\\", "/")).name for p in temp_skripte]
        funde.append(Fund("niedrig", "Datei", f"{len(temp_skripte)} neue Skripte im Temp-Ordner",
                          pfad=str(Path(temp_skripte[0]).parent),
                          gruende=["Meist Hilfsskripte von Programmen (z.B. Entwickler-Tools, Installer) - "
                                   "auffaellig nur, wenn sie auch im Autostart auftauchen.",
                                   "z.B. " + ", ".join(namen[:8]) + (" …" if len(namen) > 8 else "")]))
    return funde


def _hosts_funde(daten: dict) -> list[Fund]:
    umgeleitet = []
    for zeile in daten.get("hosts") or []:
        teile = str(zeile).split()
        if len(teile) >= 2 and teile[0] not in ("127.0.0.1", "0.0.0.0", "::1", "::") and not teile[0].startswith("127."):
            umgeleitet.append(" ".join(teile[:3]))
    if not umgeleitet:
        return []
    return [Fund("mittel", "hosts", f"{len(umgeleitet)} Umleitung(en) in der hosts-Datei",
                 pfad="C:\\Windows\\System32\\drivers\\etc\\hosts",
                 gruende=["Leitet Webseiten auf andere Server um - manchmal fuer Spiele/Tools gewollt, "
                          "manchmal von Schadsoftware (z.B. gefaelschte Login-Seiten)."]
                 + [f"Eintrag: {u}" for u in umgeleitet[:8]])]


def bewerten(daten: dict, sigs: dict[str, dict] | None = None, orte: Orte | None = None,
             eigene: set[str] | None = None) -> list[Fund]:
    """Alle Faustregeln. Ergebnis: hoch zuerst, dann mittel, dann niedrig."""
    orte = orte or Orte.aus_umgebung()
    sigs = {k.lower(): v for k, v in (sigs or {}).items()}
    eigene = {e.lower() for e in (eigene or set())}
    funde = _defender_funde(daten)
    funde += _autostart_funde(daten, orte, sigs)
    prozesse = _prozess_funde(daten, orte, sigs, eigene)
    funde += prozesse
    funde += _datei_funde(daten, orte, sigs, {f.pfad.lower() for f in prozesse} | eigene)
    funde += _hosts_funde(daten)
    return sorted(funde, key=lambda f: STUFEN.index(f.stufe) if f.stufe in STUFEN else 9)


def _eigene_dateien() -> set[str]:
    """Nova selbst (KI-App.exe / Python) - nicht als verdaechtig melden."""
    eigene = {sys.executable.lower()}
    if getattr(sys, "frozen", False):
        eigene.add(str(Path(sys.executable).resolve()).lower())
    return eigene


# ---------------------------------------------------------------------------
#  3) Bericht
# ---------------------------------------------------------------------------
def bericht(daten: dict, funde: list[Fund], gruendlich: bool) -> str:
    zahl = {s: sum(1 for f in funde if f.stufe == s) for s in STUFEN}
    jetzt = datetime.now().strftime("%d.%m.%Y %H:%M")
    zeilen = [f"Sicherheits-Check vom {jetzt} ({'gruendlich, 30 Tage' if gruendlich else 'schnell, 7 Tage'})",
              f"Geprueft: {len(daten.get('autostart') or [])} Autostarts/Aufgaben, "
              f"{len(daten.get('prozesse') or [])} laufende Programme, "
              f"{len(daten.get('netz') or [])} Netzwerkverbindungen, "
              f"{len(daten.get('dateien') or [])} neue Programmdateien/Skripte"
              + (" (Zeitlimit erreicht - nicht alle Ordner durchsucht)" if daten.get("dateien_abgebrochen") else "")]
    d = daten.get("defender")
    if isinstance(d, dict):
        zeilen.append(f"Windows Defender: {'an' if d.get('aktiv') else 'AUS'}, Echtzeitschutz "
                      f"{'an' if d.get('echtzeit') else 'AUS'}, Definitionen vom {str(d.get('signaturen'))[:10]}, "
                      f"letzter Vollscan: {str(d.get('vollscan') or 'nie')[:10]}")
    zeilen.append(f"Ergebnis: {zahl['hoch']} hoch, {zahl['mittel']} mittel, {zahl['niedrig']} niedrig")
    zeilen.append("")
    if not funde:
        zeilen.append("Keine Auffaelligkeiten nach den Faustregeln.")
    for i, fund in enumerate(funde, start=1):
        zeilen += fund.zeilen(i)
    zeilen += ["", "Hinweis: Das sind Faustregeln, keine Urteile. Viele Funde sind harmlos (z.B. eigene oder "
                   "unsignierte Hobby-Programme). Nichts wurde geloescht oder veraendert."]
    return "\n".join(zeilen)


def _schluessel(fund: Fund) -> str:
    """Woran ein Fund beim naechsten Scan wiedererkannt wird (fuer 'ignorieren')."""
    return (fund.pfad or f"{fund.bereich}: {fund.titel}").strip().lower()


def speichern(text: str, ordner: Path, funde: list[Fund] | None = None) -> Path | None:
    try:
        ziel = Path(ordner) / _SPEICHER_ORDNER
        ziel.mkdir(parents=True, exist_ok=True)
        datei = ziel / f"scan-{datetime.now().strftime('%Y-%m-%d_%H%M')}.txt"
        datei.write_text(text, encoding="utf-8")
        if funde is not None:  # damit "ignorieren 3" weiss, was Nr. 3 war
            liste = [{"nr": i, "titel": f.titel, "schluessel": _schluessel(f)} for i, f in enumerate(funde, start=1)]
            (ziel / _LETZTE_FUNDE).write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
        return datei
    except OSError:
        logger.exception("Sicherheits-Bericht nicht gespeichert")
        return None


_IGNORIERT = "ignoriert.json"
_LETZTE_FUNDE = "letzte-funde.json"


def ignoriert_laden(ordner: Path) -> dict[str, str]:
    """{schluessel: titel} - Funde, die du als harmlos markiert hast."""
    try:
        daten = json.loads((Path(ordner) / _SPEICHER_ORDNER / _IGNORIERT).read_text(encoding="utf-8"))
        return {str(k).lower(): str(v) for k, v in daten.items()} if isinstance(daten, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def ignorieren(ordner: Path, auswahl: str) -> str:
    """auswahl: Nummern aus dem letzten Bericht ("1 3" / "1, 3") oder ein Pfad. -> Meldung."""
    ziel = Path(ordner) / _SPEICHER_ORDNER
    liste = ignoriert_laden(ordner)
    auswahl = (auswahl or "").strip().strip('"')
    if not auswahl:
        return "Was soll ich ignorieren? Nummern aus dem letzten Bericht (z.B. 1 3) oder einen Pfad."
    neu: dict[str, str] = {}
    if re.fullmatch(r"[\d,;\s]+", auswahl):
        try:
            letzte = json.loads((ziel / _LETZTE_FUNDE).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "Ich finde keinen letzten Bericht mit Nummern - bitte erst einen Scan machen."
        nach_nr = {int(e["nr"]): e for e in letzte if isinstance(e, dict) and "nr" in e}
        for nr in (int(n) for n in re.findall(r"\d+", auswahl)):
            if nr not in nach_nr:
                return f"Nr. {nr} gibt es im letzten Bericht nicht."
            neu[nach_nr[nr]["schluessel"]] = nach_nr[nr]["titel"]
    else:
        neu[_norm(auswahl)] = auswahl
    liste.update(neu)
    try:
        ziel.mkdir(parents=True, exist_ok=True)
        (ziel / _IGNORIERT).write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as exc:
        return f"Konnte die Liste nicht speichern: {exc}"
    return ("Wird ab jetzt nicht mehr als Fund gemeldet: " + "; ".join(neu.values())
            + f" (Liste: {ziel / _IGNORIERT})")


def ignorierte_entfernen(funde: list[Fund], ignoriert: dict[str, str]) -> tuple[list[Fund], int]:
    rest = [f for f in funde if _schluessel(f) not in ignoriert and _norm(f.pfad) not in ignoriert]
    return rest, len(funde) - len(rest)


def letzter_bericht(ordner: Path) -> str | None:
    ziel = Path(ordner) / _SPEICHER_ORDNER
    berichte = sorted(ziel.glob("scan-*.txt")) if ziel.is_dir() else []
    return berichte[-1].read_text(encoding="utf-8") if berichte else None


def pc_scannen(gruendlich: bool = False, ordner: Path | None = None) -> tuple[str, list[Fund]]:
    """Kompletter Check. -> (Bericht, Funde). Speichert den Bericht in <ordner>/sicherheit/."""
    daten = sammeln(gruendlich)
    orte = Orte.aus_umgebung()
    sigs = signaturen(kandidaten(daten, orte))
    funde = bewerten(daten, sigs, orte, _eigene_dateien())
    weg = 0
    if ordner is not None:
        funde, weg = ignorierte_entfernen(funde, ignoriert_laden(ordner))
    text = bericht(daten, funde, gruendlich)
    if weg:
        text += f"\n{weg} Fund(e) auf deinen Wunsch ignoriert (Liste: sicherheit/{_IGNORIERT} im Arbeitsordner)."
    if ordner is not None:
        gespeichert = speichern(text, ordner, funde)
        if gespeichert:
            text += f"\nGespeichert: {gespeichert}"
    return text, funde


# ---------------------------------------------------------------------------
#  Einzelne Datei pruefen
# ---------------------------------------------------------------------------
def _mpcmdrun() -> Path | None:
    plattform = Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "Microsoft" / "Windows Defender" / "Platform"
    kandidaten_ = sorted(plattform.glob("*/MpCmdRun.exe")) if plattform.is_dir() else []
    if kandidaten_:
        return kandidaten_[-1]
    alt = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Windows Defender" / "MpCmdRun.exe"
    return alt if alt.is_file() else None


def datei_pruefen(pfad: str) -> str:
    datei = Path(_env_pfad(pfad))
    if not datei.exists():
        return f"Die Datei gibt es nicht: {datei}"
    if datei.is_dir():
        return "Das ist ein Ordner - bitte eine einzelne Datei angeben (oder den ganzen PC scannen)."
    info = datei.stat()
    sha = hashlib.sha256()
    with datei.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(block)
    hash_ = sha.hexdigest()
    zeilen = [f"Datei: {datei}", f"Groesse: {info.st_size / 1024 / 1024:.2f} MB",
              f"Erstellt: {datetime.fromtimestamp(info.st_ctime):%d.%m.%Y %H:%M}, "
              f"geaendert: {datetime.fromtimestamp(info.st_mtime):%d.%m.%Y %H:%M}",
              f"SHA256: {hash_}",
              f"Bei VirusTotal nachschlagen (von Hand im Browser): https://www.virustotal.com/gui/file/{hash_}"]
    sig = signaturen([str(datei)]).get(str(datei).lower()) if sys.platform == "win32" else None
    if sig:
        zeilen.append(_signatur_text(sig).capitalize())
    stufe, gruende = _datei_regeln(str(datei), Orte.aus_umgebung(), sig)
    if gruende:
        zeilen.append(f"Faustregeln ({stufe or 'info'}): " + "; ".join(gruende))
    mp = _mpcmdrun() if sys.platform == "win32" else None
    if mp is None:
        zeilen.append("Windows Defender: nicht verfuegbar.")
    else:
        try:
            proc = subprocess.run([str(mp), "-Scan", "-ScanType", "3", "-File", str(datei), "-DisableRemediation"],
                                  capture_output=True, timeout=300, stdin=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            ausgabe = proc.stdout.decode("utf-8", errors="replace")
            treffer = [z.strip() for z in ausgabe.splitlines() if "Threat" in z or "Bedrohung" in z]
            if proc.returncode == 0:
                zeilen.append("Windows Defender: nichts gefunden.")
            elif proc.returncode == 2:
                zeilen.append("Windows Defender: BEDROHUNG GEFUNDEN. " + " | ".join(treffer[:4]))
            else:
                zeilen.append(f"Windows Defender: Pruefung nicht moeglich (Code {proc.returncode}).")
        except subprocess.TimeoutExpired:
            zeilen.append("Windows Defender: Pruefung hat zu lange gedauert.")
    return "\n".join(zeilen)
