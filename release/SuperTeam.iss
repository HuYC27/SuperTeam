#define MyAppName "SuperTeam"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "SuperTeam contributors"
#define MyAppExeName "SuperTeam.exe"

[Setup]
AppId={{2E245FF7-0958-45D3-B17C-D52D4A98F317}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\SuperTeam
DefaultGroupName=SuperTeam
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\publish\v1.0.0\release-assets
OutputBaseFilename=SuperTeam-Setup-1.0.0
SetupIconFile=..\ui\assets\superteam-v1.ico
UninstallDisplayIcon={app}\SuperTeam.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion=1.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=SuperTeam multi-AI collaboration workspace
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式 / Create a desktop shortcut"; GroupDescription: "附加任务 / Additional tasks:"; Flags: unchecked

[Files]
Source: "..\publish\v1.0.0\portable\SuperTeam\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SuperTeam"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\SuperTeam"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 SuperTeam / Launch SuperTeam"; Flags: nowait postinstall skipifsilent

