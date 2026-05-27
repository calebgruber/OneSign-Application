; OneSign Agent Installer — InnoSetup 6 script
; Build: iscc setup.iss
; Requires: iscc.exe in PATH or run via Inno Setup Compiler

#define AppName    "OneSign Agent"
#define AppVersion "1.0.0"
#define AppPublisher "OneSign"
#define AppURL     "https://github.com/calebgruber/OneSign-Application"
#define AppExeName "OneSignAgent.exe"
#define InstallDir "{autopf}\OneSign Agent"

[Setup]
AppId={{B2A1C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={#InstallDir}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=.
OutputBaseFilename=OneSignAgentSetup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
; Show a wizard page asking for server URL and API key
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.ServerURLLabel=Backend Server URL (e.g. http://192.168.1.100):
english.ApiKeyLabel=API Key (from Admin Panel → Workstations → API Keys):

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "installservice"; Description: "Install and start Windows service (recommended)"; GroupDescription: "Service:"; Flags: checkedonce

[Files]
; Main EXE (built by PyInstaller)
Source: "..\agent\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; pcProx DLLs — place both files in installer\ before building (one is selected at install time)
Source: "pcProxAPI64.dll"; DestDir: "{app}"; Flags: ignoreversion; Check: Is64BitInstallMode
Source: "pcProxAPI.dll";   DestDir: "{app}"; Flags: ignoreversion; Check: not Is64BitInstallMode

; NSSM service manager
Source: "nssm.exe"; DestDir: "{app}"; Flags: ignoreversion

; Service scripts
Source: "..\agent\install_service.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\agent\uninstall_service.bat"; DestDir: "{app}"; Flags: ignoreversion

; Default config (will be filled from the wizard)
Source: "..\agent\config.ini"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist

; Logo / icon
Source: "..\backend\assets\img\logo.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\OneSign Agent (Admin Panel)"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\OneSign Agent"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Install and start the Windows service after installation
Filename: "{app}\install_service.bat"; Flags: runhidden waituntilterminated; Tasks: installservice; Description: "Install OneSign Windows service"
Filename: "{app}\{#AppExeName}"; Description: "Launch OneSign Agent"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\uninstall_service.bat"; Flags: runhidden waituntilterminated

[Code]
var
  ServerURLPage: TInputQueryWizardPage;

procedure InitializeWizard();
begin
  ServerURLPage := CreateInputQueryPage(
    wpSelectTasks,
    'Server Configuration',
    'Enter your OneSign backend server details.',
    ''
  );
  ServerURLPage.Add(CustomMessage('ServerURLLabel'), False);
  ServerURLPage.Add(CustomMessage('ApiKeyLabel'),    False);
  ServerURLPage.Values[0] := 'http://YOUR_SERVER';
  ServerURLPage.Values[1] := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigFile: string;
  ServerURL, ApiKey, ReaderDllPath: string;
begin
  if CurStep = ssPostInstall then
  begin
    ServerURL  := ServerURLPage.Values[0];
    ApiKey     := ServerURLPage.Values[1];
    ConfigFile := ExpandConstant('{app}\config.ini');

    if FileExists(ConfigFile) then
    begin
      SetIniString('server', 'url', ServerURL, ConfigFile);
      SetIniString('server', 'api_key', ApiKey, ConfigFile);

      if Is64BitInstallMode then
        ReaderDllPath := ExpandConstant('{app}\pcProxAPI64.dll')
      else
        ReaderDllPath := ExpandConstant('{app}\pcProxAPI.dll');
      SetIniString('reader', 'dll_path', ReaderDllPath, ConfigFile);
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ServerURLPage.ID then
  begin
    if Trim(ServerURLPage.Values[0]) = '' then
    begin
      MsgBox('Please enter the backend server URL.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;
