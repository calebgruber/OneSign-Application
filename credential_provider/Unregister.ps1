# OneSign Credential Provider — Unregister.ps1
#
# Removes the OneSign Windows Credential Provider from the lock screen.
#
# Run as Administrator from the credential_provider directory:
#   powershell -ExecutionPolicy Bypass -File Unregister.ps1

param(
    [string]$DllPath = (Join-Path $PSScriptRoot "OneSignCredentialProvider.dll")
)

$ProviderGuid = "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}"
$RegamPath    = "${env:SystemRoot}\Microsoft.NET\Framework64\v4.0.30319\regasm.exe"

# Remove Credential Provider registry key
$RegPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$ProviderGuid"
if (Test-Path $RegPath) {
    Remove-Item -Path $RegPath -Recurse -Force
    Write-Host "Credential Provider registry key removed."
} else {
    Write-Host "Credential Provider registry key not found (already removed?)"
}

# Unregister COM class if DLL is available
if (Test-Path $DllPath) {
    Write-Host "Unregistering COM assembly: $DllPath"
    & $RegamPath /unregister $DllPath
} else {
    Write-Warning "DLL not found; COM registration may need manual cleanup with regasm /unregister."
}

Write-Host ""
Write-Host "OneSign Credential Provider unregistered."
Write-Host "The provider will no longer appear on the lock screen after the next lock."
