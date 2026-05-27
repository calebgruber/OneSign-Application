@echo off
REM install_service.bat — Install OneSign Agent as a Windows service using NSSM
REM Run as Administrator.

SET "INSTALL_DIR=%~dp0"
IF "%INSTALL_DIR:~-1%"=="\" SET "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
SET NSSM=%INSTALL_DIR%\nssm.exe
SET EXE=%INSTALL_DIR%\OneSignAgent.exe
SET SVC_NAME=OneSignAgent

echo [OneSign] Installing service...

if not exist "%EXE%" (
    echo ERROR: %EXE% not found. Run the installer first.
    pause
    exit /b 1
)

if not exist "%NSSM%" (
    echo ERROR: %NSSM% not found. NSSM must be included in the installer.
    pause
    exit /b 1
)

REM Install the service
"%NSSM%" install %SVC_NAME% "%EXE%"
"%NSSM%" set %SVC_NAME% AppDirectory "%INSTALL_DIR%"
"%NSSM%" set %SVC_NAME% AppParameters "%INSTALL_DIR%\config.ini"
"%NSSM%" set %SVC_NAME% DisplayName "OneSign Authentication Agent"
"%NSSM%" set %SVC_NAME% Description "OneSign tap-and-go RFID authentication agent"
"%NSSM%" set %SVC_NAME% Start SERVICE_AUTO_START
"%NSSM%" set %SVC_NAME% ObjectName LocalSystem ""
"%NSSM%" set %SVC_NAME% AppStdout "%PROGRAMDATA%\OneSign\service_out.log"
"%NSSM%" set %SVC_NAME% AppStderr "%PROGRAMDATA%\OneSign\service_err.log"

REM Start the service
net start %SVC_NAME%

echo.
echo [OneSign] Service installed and started successfully.
echo Log files: %%PROGRAMDATA%%\OneSign\
pause
