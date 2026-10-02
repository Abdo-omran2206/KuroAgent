; Script generated for Inno Setup Installer Generator
; KURO 2.0 Autonomous CLI AI System Assistant Setup

#define MyAppName "KURO AI Assistant"
#define MyAppVersion "2.0"
#define MyAppPublisher "Akira Omran"
#define MyAppURL "https://github.com/akiraomran/kuro"
#define MyAppExeName "KURO.exe"

[Setup]
AppId={{D37F89B2-4E21-4F25-8B9A-0A77121E90F4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=KURO_v2_Setup
SetupIconFile=..\assets\kuro_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath"; Description: "Add KURO to System PATH environment variable"; GroupDescription: "System Integration"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\kuro_icon.png"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\assets\kuro_icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\kuro_icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\assets\kuro_icon.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
