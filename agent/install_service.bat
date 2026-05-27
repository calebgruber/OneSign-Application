@echo off
REM install_service.bat — Install OneSign Agent as a Windows service using NSSM
REM Run as Administrator.

setlocal
SET "INSTALL_DIR=%~dp0"
IF "%INSTALL_DIR:~-1%"=="\" SET "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
SET NSSM=%INSTALL_DIR%\nssm.exe
SET EXE=%INSTALL_DIR%\OneSignAgent.exe
SET SVC_NAME=OneSignAgent

echo [OneSign] Installing service...

if not exist "%EXE%" (
    echo ERROR: %EXE% not found. Run the installer first.
    exit /b 1
)

if not exist "%NSSM%" (
    echo ERROR: %NSSM% not found. NSSM must be included in the installer.
    exit /b 1
)

SET "LOG_DIR=%PROGRAMDATA%\OneSign"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if exist "%LOG_DIR%" (
    icacls "%LOG_DIR%" /grant "Users:(OI)(CI)M" >nul 2>&1
)

REM Install the service
"%NSSM%" install %SVC_NAME% "%EXE%"
if errorlevel 1 (
    echo ERROR: Failed to install service %SVC_NAME% with NSSM.
    exit /b 1
)
"%NSSM%" set %SVC_NAME% AppDirectory "%INSTALL_DIR%"
if errorlevel 1 exit /b 1
"%NSSM%" set %SVC_NAME% AppParameters "%INSTALL_DIR%\config.ini"
if errorlevel 1 exit /b 1
"%NSSM%" set %SVC_NAME% DisplayName "OneSign Authentication Agent"
if errorlevel 1 exit /b 1
"%NSSM%" set %SVC_NAME% Description "OneSign tap-and-go RFID authentication agent"
if errorlevel 1 exit /b 1
"%NSSM%" set %SVC_NAME% Start SERVICE_AUTO_START
if errorlevel 1 exit /b 1
"%NSSM%" set %SVC_NAME% ObjectName LocalSystem ""
if errorlevel 1 exit /b 1
"%NSSM%" set %SVC_NAME% AppStdout "%LOG_DIR%\service_out.log"
if errorlevel 1 exit /b 1
"%NSSM%" set %SVC_NAME% AppStderr "%LOG_DIR%\service_err.log"
if errorlevel 1 exit /b 1

REM Start the service
net start %SVC_NAME%
if errorlevel 1 (
    echo ERROR: Service %SVC_NAME% was installed but could not be started.
    exit /b 1
)

echo.
echo [OneSign] Service installed and started successfully.
echo Log files: %%PROGRAMDATA%%\OneSign\
exit /b 0
