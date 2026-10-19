# PyInstaller 설정: Windows에서 `pyinstaller knuzoom.spec` 실행
#   dist/KnuZoom/KnuZoom.exe  — 본 프로그램(폴더 전체가 필요)
#   dist/KnuZoomProbe.exe     — Zoom 버튼 문구 진단 도구(단일 파일, 콘솔 창)
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ["src/knuzoom/__main__.py"],
    pathex=["src"],
    datas=collect_data_files("mediapipe") + collect_data_files("soundcard"),
    hiddenimports=["pywinauto", "keyboard", "pystray._win32", "soundcard", "pygrabber"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="KnuZoom", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="KnuZoom")

probe = Analysis(["scripts/probe_zoom.py"], hiddenimports=["pywinauto"])
probe_pyz = PYZ(probe.pure)
probe_exe = EXE(probe_pyz, probe.scripts, probe.binaries, probe.datas, name="KnuZoomProbe", console=True)
