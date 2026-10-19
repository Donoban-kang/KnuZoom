; KnuZoom 설치 프로그램 (Inno Setup 6)
; 빌드 순서: pyinstaller knuzoom.spec → ISCC.exe /DAppVersion=0.1.0 installer\knuzoom.iss
; 결과: dist\installer\KnuZoom-Setup-<버전>.exe
; 이 파일은 한글이 들어 있으므로 UTF-8(BOM 포함)으로 저장한다.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8E0F3B52-6C1D-4E8A-9B7F-2D4C5A1E9F30}
AppName=KnuZoom
AppVersion={#AppVersion}
AppVerName=KnuZoom {#AppVersion}
AppPublisher=KnuZoom
DefaultDirName={autopf}\KnuZoom
DefaultGroupName=KnuZoom
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=KnuZoom-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
; 실행 중인 KnuZoom이 있으면 설치·제거 전에 종료하라고 안내한다(src/knuzoom/single_instance.py와 같은 이름).
AppMutex=KnuZoomAppMutex
SetupMutex=KnuZoomSetupMutex
UninstallDisplayName=KnuZoom
UninstallDisplayIcon={app}\KnuZoom.exe
WizardStyle=modern

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\Korean.isl")
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 KnuZoom 바로가기 만들기"

[Files]
Source: "..\dist\KnuZoom\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\KnuZoomProbe.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\install.md"; DestDir: "{app}\docs"; DestName: "설치안내.txt"; Flags: ignoreversion
Source: "..\docs\rehearsal.md"; DestDir: "{app}\docs"; DestName: "리허설체크리스트.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\KnuZoom\KnuZoom"; Filename: "{app}\KnuZoom.exe"
Name: "{autoprograms}\KnuZoom\Zoom 버튼 진단"; Filename: "{app}\KnuZoomProbe.exe"
Name: "{autoprograms}\KnuZoom\설치·비상 운영 안내"; Filename: "{app}\docs\설치안내.txt"
Name: "{autoprograms}\KnuZoom\KnuZoom 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\KnuZoom"; Filename: "{app}\KnuZoom.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KnuZoom.exe"; Description: "KnuZoom 실행"; Flags: nowait postinstall skipifsilent

[Code]
const
  { OBS Studio 가상 카메라 DirectShow 필터 CLSID (추가 확인 필요: OBS 버전에 따라 다를 수 있음) }
  OBS_VCAM_CLSID = '{A3FCE0F5-3493-419F-958A-ABA1250EC20B}';

function ObsVirtualCamInstalled: Boolean;
begin
  Result := RegKeyExists(HKEY_CLASSES_ROOT, 'CLSID\' + OBS_VCAM_CLSID)
    or RegKeyExists(HKLM, 'SOFTWARE\OBS Studio')
    or RegKeyExists(HKLM32, 'SOFTWARE\OBS Studio');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ErrorCode: Integer;
begin
  if (CurStep = ssPostInstall) and (not WizardSilent) and (not ObsVirtualCamInstalled) then
  begin
    if MsgBox('KnuZoom이 Zoom에 영상을 넘기려면 OBS Studio(가상 카메라 드라이버)가 필요합니다.' + #13#10 +
              'OBS Studio 내려받기 페이지를 열까요?', mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://obsproject.com/download', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
  end;
end;
