# PyInstaller 설정: Windows에서 `pyinstaller knuzoom.spec` 실행 → dist/KnuZoom/KnuZoom.exe
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ["src/knuzoom/__main__.py"],
    pathex=["src"],
    datas=collect_data_files("mediapipe"),
    hiddenimports=["pywinauto", "keyboard", "pystray._win32"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="KnuZoom", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="KnuZoom")
