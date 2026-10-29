@echo off
REM ============================================================
REM  Baut KI.exe unter Windows.
REM  Doppelklick genuegt (oder in der Eingabeaufforderung starten).
REM ============================================================
cd /d "%~dp0\.."

echo [1/3] Virtuelle Umgebung vorbereiten...
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/3] Abhaengigkeiten installieren...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
pip install pyinstaller

echo [3/3] KI.exe bauen...
pyinstaller packaging\ki.spec --noconfirm

echo.
echo Fertig! Die Datei liegt hier: dist\KI.exe
echo Sie nutzt .env und config\ aus diesem Projektordner. Kopierst du KI.exe
echo woandershin, legt sie dort beim ersten Start eigene Dateien an (.env, config\).
pause
