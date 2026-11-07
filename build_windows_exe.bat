@echo off
REM Copyright © 2026 Tirhut LLC. All rights reserved.
REM Builds a standalone GlowLyrics.exe (no Python needed on the target PC).
REM Run run_windows.bat once first so the .venv exists.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run run_windows.bat once first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\python.exe" tools\gen_licenses.py THIRD-PARTY-LICENSES.txt
set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" tools\make_icns.py build\GlowLyrics.ico
set "QT_QPA_PLATFORM="
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --windowed --name GlowLyrics --icon build\GlowLyrics.ico ^
    --collect-all winrt --collect-data soundcard ^
    --add-data "LICENSE.txt;." --add-data "THIRD-PARTY-NOTICES.txt;." ^
    --add-data "THIRD-PARTY-LICENSES.txt;." main.py
copy /y LICENSE.txt dist\GlowLyrics\ >nul
copy /y THIRD-PARTY-NOTICES.txt dist\GlowLyrics\ >nul
copy /y THIRD-PARTY-LICENSES.txt dist\GlowLyrics\ >nul
echo.
echo Done. Share the folder dist\GlowLyrics (zip it) - users run GlowLyrics.exe inside it.
pause
