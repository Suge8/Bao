; ──────────────────────────────────────────────────────────────
; Bao Desktop — Windows Inno Setup Installer Script
; Compile with: app\scripts\package_win_installer.bat
; ──────────────────────────────────────────────────────────────

#define MyAppName "Bao"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppPublisher "Bao Contributors"
#define MyAppURL "https://github.com/bao-project/Bao"
#define MyAppExeName "Bao.exe"
#ifndef BuildSource
  #define BuildSource "..\..\dist\build-win-x64\main.dist"
#endif

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
SetupIconFile=..\resources\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern windows11 dynamic
WizardSizePercent=106,108
WizardImageFile=..\resources\installer\wizard-image-light.png
WizardImageFileDynamicDark=..\resources\installer\wizard-image-dark.png
WizardSmallImageFile=..\resources\installer\wizard-small-light.png
WizardSmallImageFileDynamicDark=..\resources\installer\wizard-small-dark.png
WizardBackImageFile=..\resources\installer\wizard-back-light.png
WizardBackImageFileDynamicDark=..\resources\installer\wizard-back-dark.png
WizardBackImageOpacity=148
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage
UsePreviousLanguage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "..\resources\installer\ChineseSimplified.isl"

[Messages]
english.WelcomeLabel1=Welcome to Bao
english.WelcomeLabel2=Install Bao {#MyAppVersion} and start with one calm desktop workspace for chat, memory, tools, and gateway controls.%n%nAfter first launch, you can connect Telegram, Discord, WhatsApp, Slack, and more from inside the app.
english.FinishedHeadingLabel=Bao is ready.
english.FinishedLabel=Bao has been installed successfully.%n%nLaunch it from the Start menu or your desktop shortcut. Bao will create its config at ~/.bao/config.jsonc on first launch.
english.BeveledLabel=Bao Desktop Setup
chinesesimplified.WelcomeLabel1=欢迎使用 Bao
chinesesimplified.WelcomeLabel2=安装 Bao {#MyAppVersion}，先把聊天、记忆、工具和网关控制收进一个更安静的桌面工作区。%n%n首次启动后，你可以再在应用内接入 Telegram、Discord、WhatsApp、Slack 等渠道。
chinesesimplified.FinishedHeadingLabel=Bao 已准备就绪。
chinesesimplified.FinishedLabel=Bao 已成功安装。%n%n你可以从开始菜单或桌面快捷方式启动它。首次启动时，Bao 会在 ~/.bao/config.jsonc 创建配置文件。
chinesesimplified.BeveledLabel=Bao 桌面端安装程序

[CustomMessages]
english.ShortcutsGroup=Shortcuts:
english.CreateDesktopShortcut=Create a desktop shortcut
english.CreateStartMenuShortcut=Create a Start menu entry
english.LaunchBao=Launch Bao
chinesesimplified.ShortcutsGroup=快捷方式：
chinesesimplified.CreateDesktopShortcut=创建桌面快捷方式
chinesesimplified.CreateStartMenuShortcut=创建开始菜单项
chinesesimplified.LaunchBao=启动 Bao

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopShortcut}"; GroupDescription: "{cm:ShortcutsGroup}"
Name: "startmenu"; Description: "{cm:CreateStartMenuShortcut}"; GroupDescription: "{cm:ShortcutsGroup}"; Flags: checkedonce

[Files]
Source: "{#BuildSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenu
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenu

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchBao}"; Flags: nowait postinstall skipifsilent
