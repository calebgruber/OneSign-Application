# OneSign Windows Credential Provider

A Windows Credential Provider DLL that displays a **"Tap your badge" tile** on the Windows lock / logon screen.  When the OneSign agent authenticates a badge swipe with the backend, it sends credentials over a named pipe (`\\.\pipe\OneSignCredProvider`) and this provider submits them to Windows through the official `ICredentialProvider` → `ICredentialProviderCredential::GetSerialization` path.

## Architecture

```
[Badge tap]
    │
    ▼
[OneSign Agent] ─── HTTP ──▶ [Backend API] (auth.php)
    │                               │ credentials (username/password/domain)
    │                               ▼
    └─── Named pipe ──────▶ [Credential Provider DLL]
         (\\.\pipe\OneSignCredProvider)     │
                                            ▼
                                    [Windows LogonUI / Winlogon]
                                    → ICredentialProviderCredential::GetSerialization
                                    → KERB_INTERACTIVE_UNLOCK_LOGON
                                    → Workstation unlocked ✓
```

## Build

Requirements:
- Windows 10 / 11 (build and target machine)
- [.NET SDK 6+](https://dotnet.microsoft.com/download) **or** Visual Studio 2019/2022 with .NET desktop workload
- .NET Framework 4.8 (ships with Windows 10 1903+ and Server 2019+)

```cmd
cd credential_provider
build.bat
```

Output DLL: `bin\Release\net48\OneSignCredentialProvider.dll`

## Installation

Run **as Administrator** from the `credential_provider` folder (or the folder containing the built DLL):

```powershell
powershell -ExecutionPolicy Bypass -File Register.ps1
```

This calls `regasm.exe /codebase` (registers the COM class) and adds the GUID to the Credential Providers registry key.

## Uninstallation

```powershell
powershell -ExecutionPolicy Bypass -File Unregister.ps1
```

## Configuration

The OneSign agent automatically tries the named pipe first for every unlock.  No agent configuration is needed beyond having the DLL registered.

The pipe path is:
```
\\.\pipe\OneSignCredProvider
```

The agent sends a **4-byte little-endian length prefix** followed by a UTF-8 JSON body:
```json
{"username": "jdoe", "password": "s3cr3t", "domain": "."}
```
Use `"."` for a local account or the NETBIOS domain name for domain accounts.

## How It Works

1. **`CredProvider`** (`CredProvider.cs`) — implements `ICredentialProvider`.  On `SetUsageScenario` it starts `PipeServer` and creates a `CredentialTile`.
2. **`PipeServer`** (`PipeServer.cs`) — background thread listens on the named pipe.  Each connection delivers exactly one credential JSON blob.
3. **`CredentialTile`** (`CredentialTile.cs`) — implements `ICredentialProviderCredential`.  On `DeliverCredentials()` it stores the username/password/domain and calls `ICredentialProviderEvents::CredentialsChanged` to wake LogonUI.  LogonUI then calls `GetSerialization()` which packs a `KERB_INTERACTIVE_UNLOCK_LOGON` structure and hands it to LSA.

## Fallback Chain

The agent uses this unlock priority order:

1. **Named pipe** (this DLL) — cleanest, most reliable
2. **External credential provider command** (legacy `credential_provider.command` in `config.ini`)
3. **Winlogon SendInput** — synthesizes keystrokes on the secure desktop (least reliable, used when DLL is not installed)

## Provider GUID

```
{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
```

Registry path:
```
HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
```
