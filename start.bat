@echo off
REM ============================================================
REM  Startet die KI direkt (ohne .exe zu bauen).
REM  Einfach doppelklicken.
REM ============================================================
cd /d "%~dp0"
title Selbst-lernende KI

REM --- 1) Python finden -------------------------------------
REM Zuerst den Python-Launcher "py" probieren (funktioniert auch ohne PATH
REM und umgeht die Microsoft-Store-Falle), dann "python".
set "PYCMD="
py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD (
    python --version >nul 2>&1 && set "PYCMD=python"
)

if not defined PYCMD (
    echo.
    echo ============================================================
    echo [FEHLER] Python wurde nicht gefunden.
    echo ============================================================
    echo Das liegt fast immer an einem von drei Dingen:
    echo.
    echo  1) Beim Installieren war das Haekchen "Add python.exe to PATH"
    echo     NICHT gesetzt. Loesung: Python von python.org neu installieren
    echo     und dieses Haekchen UNTEN im Fenster setzen.
    echo.
    echo  2) Windows oeffnet beim Tippen von "python" den Microsoft Store.
    echo     Loesung: Windows-Einstellungen oeffnen, nach "App-
    echo     Ausfuehrungsaliase" suchen und die Schalter fuer
    echo     "python.exe" und "python3.exe" AUSschalten.
    echo.
    echo  3) Du hast dieses Fenster noch vor der Installation offen gehabt.
    echo     Loesung: dieses Fenster schliessen und start.bat erneut starten.
    echo.
    echo Tipp: Pruefe im Startmenue, ob "Python 3.14" wirklich installiert ist.
    echo.
    pause
    exit /b 1
)
echo Python gefunden: %PYCMD%

REM --- 2) Virtuelle Umgebung + Pakete (nur beim ersten Mal) --
if not exist ".venv" (
    echo Erster Start: richte die Umgebung ein. Das dauert ein paar Minuten...
    %PYCMD% -m venv .venv
    if errorlevel 1 (
        echo [FEHLER] Konnte die Umgebung nicht anlegen. Siehe ANLEITUNG.md.
        pause
        exit /b 1
    )
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [HINWEIS] Beim Installieren gab es einen Fehler. Wenn nur optionale
        echo Pakete (Sprache/PC-Steuerung) betroffen sind, laeuft die KI trotzdem.
        echo Bei einem Hauptpaket siehe ANLEITUNG.md, Abschnitt "Problemloesung".
        echo.
    )
) else (
    call ".venv\Scripts\activate.bat"
)

REM --- 3) Einstellungsdatei anlegen (falls noch nicht da) ----
if not exist "config\settings.toml" (
    copy "config\settings.example.toml" "config\settings.toml" >nul
)

REM --- 4) Schluessel-Datei .env anlegen und oeffnen ---------
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo Ich habe die Datei .env angelegt und oeffne sie jetzt im Editor.
    echo  --^> Trage deinen API-Schluessel ein, dann SPEICHERN (Strg+S)
    echo      und den Editor schliessen.
    echo.
    pause
    notepad .env
)

REM --- 5) Los geht's ----------------------------------------
echo.
echo Starte die KI...
python -m assistant
echo.
pause
