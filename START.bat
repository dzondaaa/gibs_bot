@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Neni nainstalovan Python: https://www.python.org/downloads/
    pause
    exit /b 1
  )
  set "PY=python"
)
echo [1/2] Instaluji potrebne knihovny vcetne opravy chyby Europe/Prague...
%PY% -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo Chyba pri instalaci knihoven. Zkontroluj pripojeni k internetu.
  pause
  exit /b 1
)
echo [2/2] Spoustim bota...
%PY% launcher.py
echo.
echo Bot se ukoncil. Pro opetovne spusteni otevri START.bat.
pause
