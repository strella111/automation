; Скрипт для Inno Setup
; Создает установщик приложения Automation Tool

#define MyAppName "Automation Tool"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "PULSAR"
#define MyAppExeName "AutomationTool.exe"

[Setup]
; Основная информация
AppId={{A1B2C3D4-E5F6-4A5B-8C9D-0E1F2A3B4C5D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=Output
OutputBaseFilename=AutomationTool_Setup_{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

; Права доступа (lowest = не требуются права администратора)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Иконки (Inno Setup требует формат ICO!)
; Если файл Logo.ico не существует, закомментируйте следующую строку
SetupIconFile=icon\Logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; Языки
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Основной исполняемый файл
Source: "dist\AutomationTool\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Все остальные файлы из dist\AutomationTool (включая все подпапки)
Source: "dist\AutomationTool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Примечание: папки settings, logs, data создаются автоматически строкой выше
; Флаг uninsneveruninstall применяется ко всем пользовательским данным
[Dirs]
Name: "{app}\settings"; Flags: uninsneveruninstall
Name: "{app}\logs"; Flags: uninsneveruninstall  
Name: "{app}\data"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Удаляем логи при деинсталляции (настройки оставляем)
Type: filesandordirs; Name: "{app}\logs"

[Code]
// Проверка при установке
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

// Сообщение после установки
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Дополнительные действия после установки
  end;
end;

[CustomMessages]
russian.LaunchProgram=Запустить %1
english.LaunchProgram=Launch %1

