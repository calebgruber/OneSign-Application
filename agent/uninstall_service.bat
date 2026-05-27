@echo off
REM uninstall_service.bat — Remove the OneSign Agent Windows service
REM Run as Administrator.

SET INSTALL_DIR=C:\Program Files\OneSign Agent
SET NSSM=%INSTALL_DIR%\nssm.exe
SET SVC_NAME=OneSignAgent

echo [OneSign] Stopping and removing service...

net stop %SVC_NAME% 2>nul
"%NSSM%" remove %SVC_NAME% confirm

echo [OneSign] Service removed.
pause
