@echo off
REM build.bat — Build the OneSign Agent EXE with PyInstaller
REM Run from the agent\ directory.
REM Requires: pip install -r requirements.txt

setlocal
set "PYTHON_CMD="
where py >nul 2>&1 && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD where python >nul 2>&1 && set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
  echo [OneSign] ERROR: Python is not available in PATH.
  exit /b 1
)

echo [OneSign] Installing dependencies...
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo [OneSign] Building EXE...
%PYTHON_CMD% -m PyInstaller ^
  --onefile ^
  --windowed ^
  --name "OneSignAgent" ^
  --icon "..\backend\assets\img\logo.ico" ^
  --add-data "config.ini;." ^
  --hidden-import=ctypes ^
  onesign_agent.py
if errorlevel 1 exit /b 1

echo.
if exist "dist\OneSignAgent.exe" (
  echo Build complete. EXE is in dist\OneSignAgent.exe
) else (
  echo [OneSign] Build finished but dist\OneSignAgent.exe was not found.
  exit /b 1
)
pause
