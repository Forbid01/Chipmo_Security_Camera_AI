; Sentry Agent — Windows installer (T4-03)
;
; Compile with: iscc.exe /DSentryVersion=0.1.0 SentryAgent.iss
;
; The installer ships three components:
;   * bootstrap.ps1       — runs at the end of Install to detect Docker
;                           Desktop, pull the agent image, register the
;                           scheduled task, and kick it off.
;   * uninstall.ps1       — reverses bootstrap on Remove.
;   * service-wrapper.ps1 — the scheduled task's command — it runs the
;                           agent container in the foreground so
;                           Windows Task Scheduler can manage restart.
;
; All three are generic — per-tenant config.yaml is NOT baked in.
; The installer accepts a /CONFIGURL=<signed T4-02 url> parameter and
; has bootstrap.ps1 download config.yaml into ProgramData on first run.

#ifndef SentryVersion
  #define SentryVersion "0.0.0-dev"
#endif

#ifndef SentryImage
  #define SentryImage "ghcr.io/tuguldur0107/sentry-agent:latest"
#endif

[Setup]
AppId={{C7B4E9A2-2F1C-4A3E-9B5D-2E7F8C1A4B6D}
AppName=Sentry Agent
AppVersion={#SentryVersion}
AppVerName=Sentry Agent {#SentryVersion}
AppPublisher=Chipmo / Sentry
AppPublisherURL=https://sentry.mn
AppSupportURL=https://sentry.mn/support
AppUpdatesURL=https://sentry.mn/downloads
DefaultDirName={autopf}\Sentry\Agent
DefaultGroupName=Sentry
DisableProgramGroupPage=yes
OutputBaseFilename=SentryAgentSetup
OutputDir=dist
SolidCompression=yes
Compression=lzma2/ultra
WizardStyle=modern
; UAC — we need admin rights to install Docker Desktop (if missing),
; register a scheduled task, and write into ProgramData.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
; 64-bit only — agent image is linux/amd64, and Docker Desktop itself
; requires x64 + virtualization.
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0.17763
; Minimum Windows 10 1809 — WSL2 requirement from Docker Desktop.

UninstallDisplayIcon={app}\sentry-agent.ico
UninstallDisplayName=Sentry Agent
WizardSmallImageFile=
WizardImageFile=

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "bootstrap.ps1";        DestDir: "{app}"; Flags: ignoreversion
Source: "uninstall.ps1";        DestDir: "{app}"; Flags: ignoreversion
Source: "service-wrapper.ps1";  DestDir: "{app}"; Flags: ignoreversion
Source: "README.txt";           DestDir: "{app}"; Flags: ignoreversion isreadme

[Dirs]
; ProgramData holds config.yaml — readable only by Administrators +
; SYSTEM so a non-elevated user can't exfiltrate the embedded API key.
Name: "{commonappdata}\Sentry\Agent"; Permissions: admins-full system-full

[Run]
; bootstrap.ps1 performs the Docker Desktop check, pulls the agent
; image, and registers the scheduled task. Forwarding /CONFIGURL lets
; the installer wire a T4-02 signed URL the customer copy-pasted in
; the wizard.
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\bootstrap.ps1"" -InstallDir ""{app}"" -Image ""{#SentryImage}"" -ConfigUrl ""{code:GetConfigUrl}"""; \
  StatusMsg: "Configuring Sentry Agent (Docker Desktop + image pull)…"; \
  Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\uninstall.ps1"" -Image ""{#SentryImage}"""; \
  RunOnceId: "SentryAgentUninstall"; \
  Flags: runhidden waituntilterminated

[Code]
var
  ConfigUrlPage: TInputQueryWizardPage;

function GetConfigUrl(Param: string): string;
begin
  if Assigned(ConfigUrlPage) and (ConfigUrlPage.Values[0] <> '') then
    Result := ConfigUrlPage.Values[0]
  else
    Result := ExpandConstant('{param:CONFIGURL|}');
end;

procedure InitializeWizard();
begin
  ConfigUrlPage := CreateInputQueryPage(wpSelectDir,
    'Sentry-ийн тохиргоо',
    'Installer-ийг ажиллуулахаасаа өмнө захиалагч портлоос config.yaml-ын signed URL-ийг хуулбарлана уу.',
    'Сентри платформоос татаж авсан 24 цагийн signed URL. Хоосон орхивол bootstrap нь тохиргоог алгасаж, та дараа нь гараар нэмэх боломжтой.');
  ConfigUrlPage.Add('Config URL (https://…/api/v1/installer/config/…):', False);
end;

function DetectDockerDesktop(): Boolean;
var
  ResultCode: Integer;
  DockerExe: String;
begin
  Result := False;
  // Registry probe — Docker Desktop writes its install path here.
  if RegKeyExists(HKLM, 'SOFTWARE\Docker Inc.\Docker Desktop') then begin
    Result := True;
    Exit;
  end;
  // Filesystem fallback — covers installs that predate the registry
  // key or where the user removed the reg entry.
  DockerExe := ExpandConstant('{autopf}\Docker\Docker\Docker Desktop.exe');
  if FileExists(DockerExe) then begin
    Result := True;
  end;
end;

function InitializeSetup(): Boolean;
var
  MsgResult: Integer;
begin
  Result := True;
  if not DetectDockerDesktop() then begin
    MsgResult := MsgBox(
      'Docker Desktop илэрсэнгүй.' + #13#10 + #13#10 +
      'Sentry Agent нь Docker Desktop-ийн дээр ажилладаг. Installer нь ' +
      'bootstrap алхамд Docker Desktop-ийг албан ёсны эх үүсвэрээс татаж ' +
      'суулгах болно.' + #13#10 + #13#10 +
      'Үргэлжлүүлэх үү?',
      mbConfirmation, MB_YESNO);
    if MsgResult <> IDYES then
      Result := False;
  end;
end;
