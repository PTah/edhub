; Inno Setup 6 — установщик EDHUD
; Сборка: build_windows.bat (нужен ISCC) или вручную:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.2.4 installer\edhud.iss

#ifndef MyAppVersion
  #define MyAppVersion "1.2.4"
#endif

#define MyAppName "EDHUD"
#define MyAppPublisher "EDHUD"
#define MyAppURL "https://github.com/PTah/edhub"
#define MyAppExeName "EDHUD.exe"

[Setup]
AppId={{A7C3E8F1-4B2D-4E9A-9C1F-8D6E5A2B0F33}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=EDHUD-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\data\edhud.ico
InfoBeforeFile=
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Запускать EDHUD при входе в Windows"; GroupDescription: "Автозапуск:"; Flags: unchecked

[Files]
; Содержимое PyInstaller --onedir (Python, tkinter, data/* внутри)
Source: "..\dist\EDHUD\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Кэш и настройки пользователя не трогаем (%LOCALAPPDATA%\EliteDangerousHUD)
Type: filesandordirs; Name: "{app}"
