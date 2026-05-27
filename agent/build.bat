@echo off
REM build.bat — Build the OneSign Agent EXE with PyInstaller
REM Run from the agent\ directory.
REM Requires: pip install -r requirements.txt

echo [OneSign] Installing dependencies...
pip install -r requirements.txt

echo [OneSign] Building EXE...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "OneSignAgent" ^
  --icon "..\backend\assets\img\logo.ico" ^
  --add-data "config.ini;." ^
  onesign_agent.py

echo.
echo Build complete. EXE is in dist\OneSignAgent.exe
pause
