@echo off
rem OneSign Credential Provider — build.bat
rem
rem Builds OneSignCredentialProvider.dll targeting .NET 4.8 x64.
rem Run from the credential_provider directory on a Windows machine with
rem the .NET SDK or MSBuild installed.
rem
rem Usage:
rem   build.bat
rem
rem After building, run Register.ps1 as Administrator to install.

setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

rem Try dotnet SDK first
where dotnet >nul 2>&1
if %errorlevel% equ 0 (
    echo Building with dotnet SDK...
    dotnet build OneSignCredentialProvider.csproj -c Release -r win-x64 --no-self-contained
    if errorlevel 1 (
        echo Build failed.
        exit /b 1
    )
    echo.
    echo Build succeeded.  DLL is in bin\Release\net48\
    goto :done
)

rem Fall back to MSBuild
set "MSBUILD="
for %%p in (
    "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe"
    "%ProgramFiles(x86)%\Microsoft Visual Studio\2019\BuildTools\MSBuild\Current\Bin\MSBuild.exe"
    "%ProgramFiles%\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe"
    "%ProgramFiles%\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\MSBuild.exe"
    "%ProgramFiles%\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\MSBuild.exe"
) do (
    if exist "%%~p" set "MSBUILD=%%~p"
)

if "%MSBUILD%"=="" (
    echo ERROR: Neither dotnet SDK nor MSBuild found.
    echo Install the .NET SDK from https://dotnet.microsoft.com/download
    echo or Visual Studio Build Tools from https://visualstudio.microsoft.com/downloads/
    exit /b 1
)

echo Building with MSBuild: %MSBUILD%
"%MSBUILD%" OneSignCredentialProvider.csproj /p:Configuration=Release /p:Platform=x64
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)
echo.
echo Build succeeded.  DLL is in bin\Release\net48\

:done
endlocal
