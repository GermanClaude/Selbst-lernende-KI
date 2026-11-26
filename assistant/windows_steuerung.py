"""Jede App bedienen - fuer JEDES KI-Modell, auch ohne Bildverstaendnis (z.B. DeepSeek).

Statt Bildschirmfotos (nur fuer Modelle, die Bilder sehen) liest Nova Fenster und Bedienelemente als TEXT:
- Windows-Bedienungshilfen (UI Automation): Fenster, Knoepfe, Felder, Menues - mit Namen; klicken, Text
  eintragen, lesen, ausklappen. Funktioniert in fast allen Programmen (Office, Browser, Explorer, Einstellungen).
- Texterkennung des Bildschirms (Windows.Media.Ocr) mit Koordinaten - fuer Apps ohne Bedienungshilfen
  (Spiele, manche Java-/Electron-Apps): "klick auf den Text 'Weiter'".
- Programme nach Namen starten (Startmenue + Store-Apps), Zwischenablage, Prozesse, Maus.

Alles ueber die Windows PowerShell 5.1, die bei jedem Windows dabei ist - keine Zusatzpakete. Die Angaben der
KI gehen als JSON in einer Umgebungsvariable hinein (nie in den Skripttext) - so kann nichts eingeschleust werden.
Das eigene Fenster von Nova (und ihr Prozess) ist tabu: Sonst koennte sie sich ueber ihre Einstellungen selbst
mehr Rechte geben.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys

TIMEOUT = 45.0


class SteuerFehler(RuntimeError):
    pass


def verfuegbar() -> bool:
    return sys.platform == "win32"


_VORSPANN = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$A = $env:NOVA_ARGS | ConvertFrom-Json
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NovaU32 {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, int d, UIntPtr e);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern void keybd_event(byte k, byte s, uint f, UIntPtr e);
}
'@
[void][NovaU32]::SetProcessDPIAware()
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
# Klassische Windows-Bedienelemente (Win32/WinForms) brauchen die Client-Proxies - sonst ist alles nur "Pane".
try {
  Add-Type -AssemblyName UIAutomationClientsideProviders
  [System.Windows.Automation.ClientSettings]::RegisterClientSideProviderAssembly([UIAutomationClientsideProviders.UIAutomationClientSideProviders].Assembly.GetName())
} catch {}
$EigenTitel = @($A.eigen_titel)
function IstEigen($w) {
  try { return ($w.Current.ProcessId -eq [int]$A.eigen_pid) -or ($EigenTitel -contains $w.Current.Name) } catch { return $false }
}
function EigeneRechtecke {
  $alle = [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
  foreach ($w in $alle) { if (IstEigen $w) { $w.Current.BoundingRectangle } }
}
function Aus($o) { $o | ConvertTo-Json -Depth 6 -Compress }
function Klick([int]$x, [int]$y, [string]$knopf = 'links', [int]$mal = 1) {
  foreach ($r in @(EigeneRechtecke)) {
    if (-not $r.IsEmpty -and $x -ge $r.Left -and $x -le $r.Right -and $y -ge $r.Top -and $y -le $r.Bottom) {
      throw 'Das ist Novas eigenes Fenster - dort klicke ich nicht (Einstellungen aendert nur dein Mensch).'
    }
  }
  [void][NovaU32]::SetCursorPos($x, $y); Start-Sleep -Milliseconds 60
  $ab = 0x2; $auf = 0x4
  if ($knopf -eq 'rechts') { $ab = 0x8; $auf = 0x10 } elseif ($knopf -eq 'mitte') { $ab = 0x20; $auf = 0x40 }
  for ($i = 0; $i -lt $mal; $i++) { [NovaU32]::mouse_event($ab,0,0,0,[UIntPtr]::Zero); [NovaU32]::mouse_event($auf,0,0,0,[UIntPtr]::Zero); Start-Sleep -Milliseconds 70 }
}
"""

_UIA = r"""
$AE = [System.Windows.Automation.AutomationElement]
$Root = $AE::RootElement
$Eigen = [int]$A.eigen_pid
function Typ($e) { ($e.Current.ControlType.ProgrammaticName -replace '^ControlType\.', '') }
function FensterListe {
  $alle = $Root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
  foreach ($w in $alle) {
    try { if ($w.Current.Name -and -not (IstEigen $w) -and -not $w.Current.IsOffscreen) { $w } } catch {}
  }
}
function ProzessName([int]$p) { try { (Get-Process -Id $p -ErrorAction Stop).ProcessName } catch { '' } }
function FindeFenster {
  $liste = @(FensterListe)
  if ($A.fenster -match '^\d+$') {
    $h = [int]$A.fenster
    foreach ($w in $liste) { if ($w.Current.NativeWindowHandle -eq $h) { return $w } }
  }
  $t = [string]$A.fenster
  if (-not $t) {
    $fg = [NovaU32]::GetForegroundWindow().ToInt64()
    foreach ($w in $liste) { if ($w.Current.NativeWindowHandle -eq $fg) { return $w } }
    throw 'Kein Fenster angegeben und das Fenster im Vordergrund gehoert Nova selbst (oder ist keins).'
  }
  foreach ($w in $liste) { if ($w.Current.Name -ieq $t) { return $w } }
  foreach ($w in $liste) { if ($w.Current.Name -like "*$t*") { return $w } }
  foreach ($w in $liste) { if ((ProzessName $w.Current.ProcessId) -like "*$t*") { return $w } }
  throw "Kein Fenster gefunden, das '$t' heisst (aktion 'liste' zeigt alle)."
}
function Elemente($fenster, [int]$max) {
  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $aus = New-Object System.Collections.ArrayList
  $warte = New-Object System.Collections.Queue
  $warte.Enqueue(@($fenster, 0))
  while ($warte.Count -gt 0 -and $aus.Count -lt $max) {
    $paar = $warte.Dequeue(); $e = $paar[0]; $tiefe = $paar[1]
    $k = $walker.GetFirstChild($e)
    while ($k -ne $null -and $aus.Count -lt $max) {
      try {
        if (-not $k.Current.IsOffscreen) { [void]$aus.Add($k) }
        if ($tiefe -lt 25) { $warte.Enqueue(@($k, $tiefe + 1)) }
      } catch {}
      $k = $walker.GetNextSibling($k)
    }
  }
  ,$aus
}
function Beschreibe($e, [int]$nr) {
  $c = $e.Current
  $d = [ordered]@{ nr = $nr; typ = (Typ $e); name = $c.Name }
  if ($c.AutomationId) { $d.id = $c.AutomationId }
  if (-not $c.IsEnabled) { $d.aus = $true }
  if ($c.IsPassword) { $d.passwort = $true }
  else {
    $vp = $null
    if ($e.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$vp)) {
      $v = $vp.Current.Value; if ($v) { $d.wert = $v.Substring(0, [Math]::Min(200, $v.Length)) }
    }
  }
  $d
}
function Passend($e) {
  $c = $e.Current
  if ($A.typ -and (Typ $e) -ne $A.typ) { return $false }
  if ($A.automation_id -and $c.AutomationId -ne $A.automation_id) { return $false }
  if ($A.element) {
    $n = [string]$c.Name; $s = [string]$A.element
    if (-not ($n -ieq $s -or $n -like "*$s*")) { return $false }
  }
  return $true
}
function FindeElement($fenster) {
  $alle = Elemente $fenster 3000
  if ($A.nr -and -not $A.element -and -not $A.automation_id) {
    $i = [int]$A.nr
    if ($i -lt 1 -or $i -gt $alle.Count) { throw "Kein Element Nr. $i (es gibt $($alle.Count))." }
    return $alle[$i - 1]
  }
  $treffer = @($alle | Where-Object { Passend $_ })
  $exakt = @($treffer | Where-Object { $_.Current.Name -ieq [string]$A.element })
  if ($exakt.Count -gt 0) { $treffer = $exakt + @($treffer | Where-Object { $exakt -notcontains $_ }) }
  if ($treffer.Count -eq 0) { throw "Kein passendes Bedienelement gefunden (aktion 'elemente' zeigt alle)." }
  $welches = if ($A.welches) { [int]$A.welches } else { 1 }
  if ($welches -gt $treffer.Count) { throw "Nur $($treffer.Count) passende Elemente." }
  $treffer[$welches - 1]
}
function Mitte($e) {
  $r = $e.Current.BoundingRectangle
  if ($r.IsEmpty) { throw 'Das Element hat keine Position auf dem Bildschirm.' }
  @([int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2))
}
function Vorne($w) {
  $h = [IntPtr]$w.Current.NativeWindowHandle
  if ([NovaU32]::IsIconic($h)) { [void][NovaU32]::ShowWindow($h, 9) }
  [NovaU32]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero); [NovaU32]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
  [void][NovaU32]::SetForegroundWindow($h)
  try { $w.SetFocus() } catch {}
  Start-Sleep -Milliseconds 150
}
"""

SKRIPTE: dict[str, str] = {}

SKRIPTE["fenster"] = _UIA + r"""
switch ($A.aktion) {
  'liste' {
    $out = foreach ($w in FensterListe) {
      $c = $w.Current
      [ordered]@{ fenster = $c.Name; handle = $c.NativeWindowHandle; programm = (ProzessName $c.ProcessId) }
    }
    Aus @($out); break
  }
  default {
    $w = FindeFenster
    $wp = $null; [void]$w.TryGetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern, [ref]$wp)
    switch ($A.aktion) {
      'fokus' { Vorne $w }
      'minimieren' { $wp.SetWindowVisualState('Minimized') }
      'maximieren' { $wp.SetWindowVisualState('Maximized') }
      'wiederherstellen' { $wp.SetWindowVisualState('Normal') }
      'schliessen' { if ($wp) { $wp.Close() } else { throw 'Dieses Fenster laesst sich nicht so schliessen.' } }
      default { throw "Unbekannte Aktion '$($A.aktion)'." }
    }
    Aus @{ ok = $true; fenster = $w.Current.Name }
  }
}
"""

SKRIPTE["bedienen"] = _UIA + r"""
$w = FindeFenster
switch ($A.aktion) {
  'elemente' {
    $alle = Elemente $w ([int]$A.max)
    $out = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt $alle.Count; $i++) {
      $e = $alle[$i]
      if (($A.element -or $A.typ) -and -not (Passend $e)) { continue }
      $d = Beschreibe $e ($i + 1)
      if (-not $d.name -and -not $d.wert -and -not $d.id -and @('Pane','Group','Custom','Separator') -contains $d.typ) { continue }
      [void]$out.Add($d)
    }
    Aus @{ fenster = $w.Current.Name; elemente = @($out); gesamt = $alle.Count }; break
  }
  'lesen' {
    $e = if ($A.element -or $A.automation_id -or $A.nr) { FindeElement $w } else { $w }
    if ($e.Current.IsPassword) { throw 'Das ist ein Passwortfeld - das lese ich nicht.' }
    $text = $null; $tp = $null; $vp = $null
    if ($e.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$tp)) { $text = $tp.DocumentRange.GetText(30000) }
    elseif ($e.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$vp)) { $text = $vp.Current.Value }
    if (-not $text) {
      $teile = foreach ($k in (Elemente $e 1500)) { $n = $k.Current.Name; if ($n -and -not $k.Current.IsPassword) { $n } }
      $text = (@($e.Current.Name) + @($teile)) -join "`n"
    }
    Aus @{ element = $e.Current.Name; text = $text }; break
  }
  default {
    $e = FindeElement $w
    $c = $e.Current
    $wie = ''
    switch ($A.aktion) {
      'klicken' {
        $p = $null
        if ($A.knopf -and $A.knopf -ne 'links' -or $A.doppelt) { Vorne $w; $m = Mitte $e; Klick $m[0] $m[1] ([string]$A.knopf) $(if ($A.doppelt) {2} else {1}); $wie = 'maus' }
        elseif ($e.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$p)) { $p.Invoke(); $wie = 'invoke' }
        elseif ($e.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$p)) { $p.Toggle(); $wie = 'umschalten' }
        elseif ($e.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$p)) { $p.Select(); $wie = 'auswaehlen' }
        elseif ($e.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$p)) { $p.Expand(); $wie = 'ausklappen' }
        else { Vorne $w; $m = Mitte $e; Klick $m[0] $m[1]; $wie = 'maus' }
      }
      'text_eingeben' {
        if ($c.IsPassword) { throw 'Das ist ein Passwortfeld - Passwoerter gibt dein Mensch selbst ein.' }
        $vp = $null
        if ($e.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$vp) -and -not $vp.Current.IsReadOnly) {
          $vp.SetValue([string]$A.text); $wie = 'wert'
        } else {
          Vorne $w; try { $e.SetFocus() } catch { $m = Mitte $e; Klick $m[0] $m[1] }
          Add-Type -AssemblyName System.Windows.Forms
          $t = ([string]$A.text) -replace '([+^%~(){}\[\]])', '{$1}'
          [System.Windows.Forms.SendKeys]::SendWait($t); $wie = 'tippen'
        }
        if ($A.enter) { Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{ENTER}') }
      }
      'fokus' { Vorne $w; $e.SetFocus(); $wie = 'fokus' }
      'ausklappen' {
        $p = $null
        if ($e.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$p)) {
          if ($p.Current.ExpandCollapseState -eq 'Expanded') { $p.Collapse(); $wie = 'eingeklappt' } else { $p.Expand(); $wie = 'ausgeklappt' }
        } else { throw 'Das laesst sich nicht ausklappen.' }
      }
      default { throw "Unbekannte Aktion '$($A.aktion)'." }
    }
    Aus @{ ok = $true; element = $c.Name; typ = (Typ $e); wie = $wie }
  }
}
"""

SKRIPTE["starten"] = r"""
$ziel = [string]$A.ziel
if ($A.aktion -eq 'liste') {
  $apps = @(Get-StartApps | Where-Object { -not $ziel -or $_.Name -like "*$ziel*" } | Select-Object -First 80 | ForEach-Object { $_.Name })
  Aus @{ apps = $apps }; return
}
if ($ziel -match '^(https?|mailto|ms-settings|steam|spotify|discord|zoommtg|tel):' -or (Test-Path -LiteralPath $ziel)) {
  Start-Process -FilePath $ziel; Aus @{ ok = $true; gestartet = $ziel; wie = 'oeffnen' }; return
}
$apps = @(Get-StartApps)
$app = $apps | Where-Object { $_.Name -ieq $ziel } | Select-Object -First 1
if (-not $app) { $app = $apps | Where-Object { $_.Name -like "$ziel*" } | Select-Object -First 1 }
if (-not $app) { $app = $apps | Where-Object { $_.Name -like "*$ziel*" } | Select-Object -First 1 }
if ($app) {
  Start-Process -FilePath ('shell:AppsFolder\' + $app.AppID)
  Aus @{ ok = $true; gestartet = $app.Name; wie = 'startmenue' }; return
}
try { Start-Process -FilePath $ziel; Aus @{ ok = $true; gestartet = $ziel; wie = 'befehl' } }
catch { throw "Kein Programm '$ziel' gefunden (aktion 'liste' zeigt die installierten Apps)." }
"""

SKRIPTE["ocr"] = r"""
Add-Type -AssemblyName System.Drawing, System.Windows.Forms, System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Warte($op, [Type]$typ) { $t = $asTask.MakeGenericMethod($typ).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$x0 = $b.X; $y0 = $b.Y
if ($A.bereich) { $x0 = [int]$A.bereich[0]; $y0 = [int]$A.bereich[1]; $bw = [int]$A.bereich[2]; $bh = [int]$A.bereich[3] } else { $bw = $b.Width; $bh = $b.Height }
$bmp = New-Object System.Drawing.Bitmap $bw, $bh
$g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($x0, $y0, 0, 0, $bmp.Size); $g.Dispose()
$ms = New-Object System.IO.MemoryStream; $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose(); $ms.Position = 0
$stream = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($ms)
$dec = Warte ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$sb = Warte ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = $null
try { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('de-DE')) } catch {}
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if (-not $engine) { throw 'Keine Sprache fuer die Windows-Texterkennung installiert.' }
$res = Warte ($engine.RecognizeAsync($sb)) ([Windows.Media.Ocr.OcrResult])
$zeilen = foreach ($z in $res.Lines) {
  $ws = @($z.Words)
  $l = ($ws | ForEach-Object { $_.BoundingRect.X } | Measure-Object -Minimum).Minimum
  $o = ($ws | ForEach-Object { $_.BoundingRect.Y } | Measure-Object -Minimum).Minimum
  $r = ($ws | ForEach-Object { $_.BoundingRect.X + $_.BoundingRect.Width } | Measure-Object -Maximum).Maximum
  $u = ($ws | ForEach-Object { $_.BoundingRect.Y + $_.BoundingRect.Height } | Measure-Object -Maximum).Maximum
  $woerter = foreach ($wd in $ws) { @{ t = $wd.Text; x = [int]($x0 + $wd.BoundingRect.X + $wd.BoundingRect.Width / 2); y = [int]($y0 + $wd.BoundingRect.Y + $wd.BoundingRect.Height / 2) } }
  [ordered]@{ text = $z.Text; x = [int]($x0 + ($l + $r) / 2); y = [int]($y0 + ($o + $u) / 2); woerter = @($woerter) }
}
$zeilen = @($zeilen)
if ($A.aktion -eq 'klicken') {
  $s = [string]$A.text
  $kand = New-Object System.Collections.ArrayList
  foreach ($z in $zeilen) {
    if ($z.text -ieq $s) { [void]$kand.Add(@($z.x, $z.y, $z.text)); continue }
    $ws = @($z.woerter)
    for ($i = 0; $i -lt $ws.Count; $i++) {
      $teil = ''
      for ($j = $i; $j -lt $ws.Count; $j++) {
        $teil = ($teil + ' ' + $ws[$j].t).Trim()
        if ($teil -ieq $s) { [void]$kand.Add(@([int](($ws[$i].x + $ws[$j].x) / 2), [int](($ws[$i].y + $ws[$j].y) / 2), $teil)); break }
      }
    }
  }
  if ($kand.Count -eq 0) { foreach ($z in $zeilen) { if ($z.text -like "*$s*") { [void]$kand.Add(@($z.x, $z.y, $z.text)) } } }
  if ($kand.Count -eq 0) { throw "Den Text '$s' sehe ich nicht auf dem Bildschirm." }
  $welches = if ($A.welches) { [int]$A.welches } else { 1 }
  if ($welches -gt $kand.Count) { throw "Nur $($kand.Count) Stellen mit '$s'." }
  $k = $kand[$welches - 1]
  Klick $k[0] $k[1] ([string]$(if ($A.knopf) { $A.knopf } else { 'links' })) $(if ($A.doppelt) { 2 } else { 1 })
  Aus @{ ok = $true; text = $k[2]; x = $k[0]; y = $k[1]; treffer = $kand.Count }; return
}
Aus @{ zeilen = @($zeilen | ForEach-Object { [ordered]@{ text = $_.text; x = $_.x; y = $_.y } }) }
"""

SKRIPTE["maus"] = r"""
$x = [int]$A.x; $y = [int]$A.y
switch ($A.aktion) {
  'bewegen' { [void][NovaU32]::SetCursorPos($x, $y) }
  'klicken' { Klick $x $y ([string]$(if ($A.knopf) { $A.knopf } else { 'links' })) $(if ($A.doppelt) { 2 } else { 1 }) }
  'ziehen' {
    [void][NovaU32]::SetCursorPos($x, $y); Start-Sleep -Milliseconds 80
    [NovaU32]::mouse_event(0x2,0,0,0,[UIntPtr]::Zero)
    $schritte = 15
    for ($i = 1; $i -le $schritte; $i++) { [void][NovaU32]::SetCursorPos([int]($x + ($A.x2 - $x) * $i / $schritte), [int]($y + ($A.y2 - $y) * $i / $schritte)); Start-Sleep -Milliseconds 25 }
    [NovaU32]::mouse_event(0x4,0,0,0,[UIntPtr]::Zero)
  }
  'scrollen' {
    if ($A.x -or $A.y) { [void][NovaU32]::SetCursorPos($x, $y) }
    $n = if ($A.menge) { [int]$A.menge } else { 3 }
    $richtung = if ($A.richtung -eq 'hoch') { 120 } else { -120 }
    for ($i = 0; $i -lt [Math]::Abs($n); $i++) { [NovaU32]::mouse_event(0x800,0,0,$richtung,[UIntPtr]::Zero); Start-Sleep -Milliseconds 30 }
  }
  default { throw "Unbekannte Aktion '$($A.aktion)'." }
}
Aus @{ ok = $true }
"""

SKRIPTE["tasten"] = r"""
$VK = @{ ctrl=0x11; strg=0x11; control=0x11; alt=0x12; shift=0x10; umschalt=0x10; win=0x5B; windows=0x5B;
  enter=0x0D; return=0x0D; tab=0x09; esc=0x1B; escape=0x1B; space=0x20; leertaste=0x20; backspace=0x08;
  delete=0x2E; entf=0x2E; insert=0x2D; home=0x24; pos1=0x24; end=0x23; ende=0x23; pageup=0x21; pagedown=0x22;
  left=0x25; links=0x25; up=0x26; hoch=0x26; right=0x27; rechts=0x27; down=0x28; runter=0x28;
  printscreen=0x2C; druck=0x2C; volumeup=0xAF; volumedown=0xAE; volumemute=0xAD; playpause=0xB3;
  nexttrack=0xB0; prevtrack=0xB1; capslock=0x14; menu=0x5D; apps=0x5D }
for ($i = 1; $i -le 12; $i++) { $VK["f$i"] = 0x6F + $i }
if ($A.aktion -eq 'tippen') {
  Add-Type -AssemblyName System.Windows.Forms
  $t = ([string]$A.text) -replace '([+^%~(){}\[\]])', '{$1}'
  $t = $t -replace "`r?`n", '{ENTER}'
  [System.Windows.Forms.SendKeys]::SendWait($t); Aus @{ ok = $true }; return
}
$codes = foreach ($k in @($A.tasten)) {
  $n = ([string]$k).ToLower()
  if ($VK.ContainsKey($n)) { $VK[$n] } elseif ($n.Length -eq 1) { [int][char]$n.ToUpper() } else { throw "Unbekannte Taste '$k'." }
}
foreach ($c in $codes) { [NovaU32]::keybd_event([byte]$c, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 30 }
[array]::Reverse($codes)
foreach ($c in $codes) { [NovaU32]::keybd_event([byte]$c, 0, 2, [UIntPtr]::Zero); Start-Sleep -Milliseconds 30 }
Aus @{ ok = $true }
"""

SKRIPTE["zwischenablage"] = r"""
if ($A.aktion -eq 'schreiben') { Set-Clipboard -Value ([string]$A.text); Aus @{ ok = $true } }
else { $t = Get-Clipboard -Raw; if ($t -eq $null) { $t = '' }; Aus @{ text = [string]$t } }
"""

SKRIPTE["prozesse"] = r"""
if ($A.aktion -eq 'beenden') {
  $p = Get-Process -Id ([int]$A.pid) -ErrorAction Stop
  $tabu = @('csrss','wininit','winlogon','lsass','services','smss','system','idle','svchost','dwm','fontdrvhost','lsaiso','registry','memory compression')
  if ($p.Id -eq [int]$A.eigen_pid -or $tabu -contains $p.ProcessName.ToLower()) { throw "'$($p.ProcessName)' beende ich nicht (Windows selbst bzw. Nova)." }
  Stop-Process -Id $p.Id -Force -ErrorAction Stop
  Aus @{ ok = $true; name = $p.ProcessName }; return
}
$f = [string]$A.filter
$liste = Get-Process | Where-Object { -not $f -or $_.ProcessName -like "*$f*" -or $_.MainWindowTitle -like "*$f*" } |
  Sort-Object WorkingSet64 -Descending | Select-Object -First 60 | ForEach-Object {
    [ordered]@{ pid = $_.Id; name = $_.ProcessName; mb = [int]($_.WorkingSet64 / 1MB); fenster = $_.MainWindowTitle }
  }
Aus @(@($liste))
"""


def eigene_titel(ki_name: str = "Nova") -> list[str]:
    """Fenstertitel von Novas eigener Oberflaeche (Programmfenster, Browser-Ersatz)."""
    name = (ki_name or "Nova").strip() or "Nova"
    return [name, f"{name} (sieht zu)", "KI"]


def _fenster_info(hwnd) -> tuple[int, str]:
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    puffer = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(hwnd, puffer, 512)
    return int(pid.value), puffer.value


def ist_eigenes_fenster(hwnd, ki_name: str = "Nova") -> bool:
    if not hwnd:
        return False
    pid, titel = _fenster_info(hwnd)
    return pid == os.getpid() or titel in eigene_titel(ki_name)


def eigenes_fenster_vorne(ki_name: str = "Nova") -> bool:
    """Ist gerade Novas eigenes Fenster vorne? Dann darf die KI nicht hineintippen (sonst koennte sie sich
    z.B. per '/stuetzraeder alles' selbst Rechte geben)."""
    if not verfuegbar():
        return False
    try:
        import ctypes

        return ist_eigenes_fenster(ctypes.windll.user32.GetForegroundWindow(), ki_name)
    except Exception:  # noqa: BLE001
        return False


def punkt_im_eigenen_fenster(x: int, y: int, ki_name: str = "Nova") -> bool:
    if not verfuegbar():
        return False
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        hwnd = u32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        wurzel = u32.GetAncestor(hwnd, 2) if hwnd else 0          # GA_ROOT
        return ist_eigenes_fenster(wurzel or hwnd, ki_name)
    except Exception:  # noqa: BLE001
        return False


def ausfuehren(skript: str, argumente: dict, timeout: float = TIMEOUT, lauf=subprocess.run,
               ki_name: str = "Nova") -> object:
    """Fuehrt ein Steuer-Skript aus. Die Angaben gehen als JSON in NOVA_ARGS - nie in den Skripttext."""
    if not verfuegbar():
        raise SteuerFehler("Das geht nur unter Windows.")
    from .geheimnisse import umgebung_ohne_geheimnisse

    text = _VORSPANN + SKRIPTE[skript]
    env = umgebung_ohne_geheimnisse()
    env["NOVA_ARGS"] = json.dumps({"eigen_pid": os.getpid(), "eigen_titel": eigene_titel(ki_name), **argumente},
                                  ensure_ascii=False)
    kodiert = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = lauf(["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass",
                  "-EncodedCommand", kodiert], capture_output=True, timeout=timeout, env=env, creationflags=flags)
    except subprocess.TimeoutExpired as exc:
        raise SteuerFehler(f"Windows hat nicht rechtzeitig geantwortet ({int(timeout)} s).") from exc
    except OSError as exc:
        raise SteuerFehler(f"PowerShell liess sich nicht starten ({exc}).") from exc
    aus = (r.stdout or b"").decode("utf-8", errors="replace").strip()
    if r.returncode != 0 or not aus:
        fehler = (r.stderr or b"").decode("utf-8", errors="replace")
        # PowerShell schreibt Fehler als CLIXML/mehrzeilig - die eigentliche Meldung herausziehen
        import re

        meldung = re.findall(r"<S S=\"Error\">(.*?)</S>", fehler)
        text = " ".join(meldung).replace("_x000D__x000A_", " ") if meldung else fehler
        text = re.split(r"\s(?:In Zeile:|At line:|Bei Zeile:)", text)[0]   # PowerShell-Fundstelle weglassen
        text = re.sub(r"\s+", " ", text).strip()
        raise SteuerFehler(text[:400] or "Das ging nicht.")
    try:
        return json.loads(aus.splitlines()[-1])
    except ValueError as exc:
        raise SteuerFehler(f"Unerwartete Antwort von Windows: {aus[:200]}") from exc
