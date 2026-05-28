# OneSign Credential Provider — Register.ps1
#
# Registers the OneSign Windows Credential Provider COM DLL so it appears
# on the Windows logon / lock screen.
#
# Run as Administrator from the credential_provider directory:
#   powershell -ExecutionPolicy Bypass -File Register.ps1
#
# Requirements:
#   - .NET Framework 4.8 (included in Windows 10/11 and Server 2019+)
#   - OneSignCredentialProvider.dll must be in the same folder as this script

param(
    [string]$DllPath = (Join-Path $PSScriptRoot "OneSignCredentialProvider.dll")
)

$ProviderGuid = "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}"
$RegamPath    = "${env:SystemRoot}\Microsoft.NET\Framework64\v4.0.30319\regasm.exe"

if (-not (Test-Path $DllPath)) {
    Write-Error "DLL not found: $DllPath"
    Write-Host  "Build the project first with build.bat."
    exit 1
}

if (-not (Test-Path $RegamPath)) {
    Write-Error "regasm.exe not found at: $RegamPath"
    Write-Host  ".NET Framework 4.8 may not be installed."
    exit 1
}

Write-Host "Registering COM assembly: $DllPath"
& $RegamPath /codebase $DllPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "regasm.exe failed (exit code $LASTEXITCODE)"
    exit 1
}

# Register the Credential Provider in the Windows registry
$RegPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$ProviderGuid"
New-Item -Path $RegPath -Force | Out-Null
Set-ItemProperty -Path $RegPath -Name "(Default)" -Value "OneSign Credential Provider"

Write-Host ""
Write-Host "OneSign Credential Provider registered successfully."
Write-Host "GUID: $ProviderGuid"
Write-Host ""
Write-Host "The provider will appear on the lock screen after the next lock/logon."
Write-Host "No reboot required."
