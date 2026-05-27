@echo off
REM uninstall_service.bat — Remove the OneSign Agent Windows service
REM Run as Administrator.

setlocal
SET "INSTALL_DIR=%~dp0"
IF "%INSTALL_DIR:~-1%"=="\" SET "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
SET NSSM=%INSTALL_DIR%\nssm.exe
SET SVC_NAME=OneSignAgent

echo [OneSign] Stopping and removing service...

sc query "%SVC_NAME%" >nul 2>&1
if errorlevel 1 (
    echo [OneSign] Service is not installed.
    exit /b 0
)

net stop %SVC_NAME% 2>nul
if exist "%NSSM%" (
    "%NSSM%" remove %SVC_NAME% confirm
) else (
    sc delete "%SVC_NAME%" >nul 2>&1
)

sc query "%SVC_NAME%" >nul 2>&1
if not errorlevel 1 (
    echo ERROR: Failed to remove service %SVC_NAME%.
    exit /b 1
)

echo [OneSign] Service removed.
exit /b 0
