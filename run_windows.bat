@echo off
REM Copyright © 2026 Tirhut LLC. All rights reserved.
setlocal
cd /d "%~dp0"
title GlowLyrics

set "PY=python"
where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"

%PY% --version >nul 2>nul
if errorlevel 1 goto nopython

if not exist ".venv\installed.ok" (
    echo First run - installing GlowLyrics. This takes a minute or two...
    %PY% -m venv .venv
    if errorlevel 1 goto fail
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto fail
    echo ok> ".venv\installed.ok"
)

start "" ".venv\Scripts\pythonw.exe" main.py %*
exit /b 0

:nopython
echo.
echo Python 3.9 or newer is required.
echo Download it from https://www.python.org/downloads/
echo During install, tick "Add python.exe to PATH". Then run this file again.
echo.
pause
exit /b 1

:fail
echo.
echo Setup failed. Check your internet connection and try again.
echo If it keeps failing, delete the .venv folder and re-run.
echo.
pause
exit /b 1
