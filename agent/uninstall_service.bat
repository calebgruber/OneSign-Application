@echo off
REM uninstall_service.bat — Remove the OneSign Agent Windows service
REM Run as Administrator.

SET "INSTALL_DIR=%~dp0"
IF "%INSTALL_DIR:~-1%"=="\" SET "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
SET NSSM=%INSTALL_DIR%\nssm.exe
SET SVC_NAME=OneSignAgent

echo [OneSign] Stopping and removing service...

net stop %SVC_NAME% 2>nul
"%NSSM%" remove %SVC_NAME% confirm

echo [OneSign] Service removed.
pause
