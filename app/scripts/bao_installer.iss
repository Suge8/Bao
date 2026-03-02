; ──────────────────────────────────────────────────────────────
; Bao Desktop — Windows Inno Setup Installer Script
; Compile with: iscc app\scripts\bao_installer.iss
; ──────────────────────────────────────────────────────────────

#define MyAppName "Bao"
#define MyAppVersion "0.1.4"
#define MyAppPublisher "Bao Contributors"
#define MyAppURL "https://github.com/bao-project/Bao"
#define MyAppExeName "Bao.exe"

[Setup]
AppId={{B4A0-DE5K-T0P-BA0-A1}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=Bao-{#MyAppVersion}-windows-x64-setup
SetupIconFile=..\..\assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110,110
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Welcome to Bao
WelcomeLabel2=Your personal AI assistant that remembers, learns, and evolves.%n%nThis will install Bao {#MyAppVersion} on your computer.%n%nBao runs as both a desktop chat interface and a gateway for 9 messaging platforms — Telegram, Discord, WhatsApp, Slack, and more.
FinishedHeadingLabel=Bao is ready.
FinishedLabel=Your AI assistant has been installed. Launch it from the Start menu or desktop shortcut.%n%nFirst launch will create your config at ~/.bao/config.jsonc

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startmenu"; Description: "Create a Start menu entry"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "..\..\dist\build-win-x64\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenu
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenu

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Bao"; Flags: nowait postinstall skipifsilent
