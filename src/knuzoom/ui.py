"""진행자용 소형 창(항상 위), 트레이 아이콘, 긴급 정지 전역 단축키."""
from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from knuzoom.config import Settings, sanitize_settings, save_settings
from knuzoom.engine import Engine
from knuzoom.ui_calls import MainThreadCalls

GREEN, RED, AMBER, GRAY = "#1f9d55", "#d64545", "#d98e04", "#666666"
POLL_MS = 200

# 설정 창에서 편집할 항목(라벨, 필드명)
_EDITABLE = [
    ("ZOOM 기준 H", "zoom_h"),
    ("WIDE 기준 H", "wide_h"),
    ("해제 유지시간(초)", "unmute_window_s"),
    ("음소거 유지시간(초)", "mute_window_s"),
    ("음소거 상태 버튼 문구(쉼표 구분)", "zoom_label_when_muted"),
    ("해제 상태 버튼 문구(쉼표 구분)", "zoom_label_when_unmuted"),
    ("Zoom 회의 창 제목(쉼표 구분)", "zoom_window_titles"),
    ("긴급 정지 단축키(재시작 필요)", "emergency_hotkey"),
    ("우리 기관 이름(녹화 표시, 재시작 필요)", "site_name"),
    ("녹화 동의 기관(쉼표 구분)", "consent_parties"),
    ("녹화 저장 폴더(비우면 문서\\KnuZoom 녹화)", "recording_dir"),
    ("녹화할 모니터 번호(0부터)", "recording_monitor"),
    ("녹화 기본 보관기간(일)", "retention_days"),
]


class ControlWindow:
    def __init__(self, engine: Engine, settings: Settings, settings_path: Path, on_quit,
                 recorder=None, camera=None, last_frame=lambda: None) -> None:
        self.engine = engine
        self.s = settings
        self.path = settings_path
        self.on_quit = on_quit
        self._calibrating = False
        self.calls = MainThreadCalls()  # 트레이 등 다른 스레드의 화면 작업 요청
        self.tray = None
        self._tray_recording: bool | None = None
        self._closed = False

        self.root = tk.Tk()
        self.root.title("KnuZoom")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)  # 닫기 = 트레이로 숨김

        self.mic_label = tk.Label(self.root, text="음소거", font=("Malgun Gothic", 22, "bold"),
                                  fg="white", bg=RED, width=14, pady=8)
        self.mic_label.pack(fill="x", padx=8, pady=(8, 4))
        self.verdict_label = tk.Label(self.root, text="판정: -", font=("Malgun Gothic", 10))
        self.verdict_label.pack()
        self.camera = camera
        self.last_frame = last_frame
        self.camera_label = tk.Label(self.root, text="", fg=GRAY, font=("Malgun Gothic", 9))
        self.camera_label.pack()
        self.warning_label = tk.Label(self.root, text="", fg=RED, font=("Malgun Gothic", 10, "bold"),
                                      wraplength=260)
        self.warning_label.pack(pady=(2, 4))

        row1 = tk.Frame(self.root); row1.pack(pady=2)
        self.auto_btn = tk.Button(row1, text="자동 ON", width=12, command=self._toggle_auto)
        self.auto_btn.pack(side="left", padx=2)
        tk.Button(row1, text="상태 맞추기", width=12, command=self._sync_dialog).pack(side="left", padx=2)
        row2 = tk.Frame(self.root); row2.pack(pady=2)
        tk.Button(row2, text="넓은 장면 저장", width=12,
                  command=lambda: self._calibrate("wide")).pack(side="left", padx=2)
        tk.Button(row2, text="확대 장면 저장", width=12,
                  command=lambda: self._calibrate("zoom")).pack(side="left", padx=2)
        self.recording = None
        if recorder is not None:
            from knuzoom.ui_recording import RecordingPanel
            self.recording = RecordingPanel(self.root, recorder, settings)
        if camera is not None:
            tk.Button(self.root, text="📷 우리 캠퍼스 카메라 선택", width=26,
                      command=self.open_camera_dialog).pack(pady=(2, 0))
        tk.Button(self.root, text="⚙ 설정", width=26, command=self._settings_dialog).pack(pady=(2, 4))
        tk.Label(self.root, text=f"긴급 정지: {self.s.emergency_hotkey.upper()}",
                 fg=GRAY, font=("Malgun Gothic", 9)).pack(pady=(0, 8))

    # ── 주기 갱신 ─────────────────────────────────────────────
    def _poll(self) -> None:
        self.calls.drain()
        if self._closed:  # drain 중에 창이 닫혔으면 더 갱신하지 않는다
            return
        self.engine.tick()
        st = self.engine.status()
        text = "음소거" if st.muted else "발언 가능"
        if st.confirmed:
            self.mic_label.config(text=text, bg=RED if st.muted else GREEN)
        else:  # Zoom에서 실제 상태를 아직 확인하지 못함
            self.mic_label.config(text=f"{text} (미확인)", bg=AMBER)
        self.verdict_label.config(text=f"판정: {st.verdict.value} (H {st.h:.0%}, 얼굴 {st.n})")
        if self.camera is not None:
            self.camera_label.config(text=f"판정 카메라: {self.camera.label()}")
        self.warning_label.config(text=st.warning or "")
        self.auto_btn.config(text="자동 ON" if st.auto else "자동 OFF",
                             relief="raised" if st.auto else "sunken")
        if self.recording is not None:
            self.recording.poll()
            self._update_tray(self.recording.recorder.recording)
        if self._calibrating and not self.engine.calibration_running():
            self._calibrating = False
            save_settings(self.s, self.path)
        self.root.after(POLL_MS, self._poll)

    # ── 조작 ─────────────────────────────────────────────────
    def _toggle_auto(self) -> None:
        self.engine.set_auto(not self.engine.status().auto)

    def _sync_dialog(self) -> None:
        token = self.engine.sync_token()
        muted = messagebox.askyesno("상태 맞추기", "지금 Zoom 마이크가 '음소거' 상태입니까?\n"
                                    "(예 = 음소거, 아니요 = 해제)", parent=self.root)
        if not self.engine.sync_mic(muted, token):
            messagebox.showinfo("상태 맞추기", "확인하시는 동안 KnuZoom이 마이크를 조작했습니다.\n"
                                "Zoom 마이크 상태를 다시 보고 한 번 더 맞춰 주세요.", parent=self.root)

    def _update_tray(self, recording: bool) -> None:
        """녹화 중이면 트레이 아이콘을 빨간색·'● 녹화 중' 제목으로 바꾼다(바뀔 때만)."""
        if self.tray is None or recording == self._tray_recording:
            return
        self._tray_recording = recording
        try:
            from knuzoom.tray_state import tray_appearance
            color, title = tray_appearance(recording)
            self.tray.icon = tray_image(color)
            self.tray.title = title
        except Exception:
            pass

    def open_camera_dialog(self, first_run: bool = False) -> None:
        from knuzoom.ui_camera import CameraDialog
        CameraDialog(self.root, self.camera, self.last_frame, first_run=first_run)

    def _calibrate(self, kind: str) -> None:
        self.engine.start_calibration(kind, time.monotonic())
        self._calibrating = True

    def _settings_dialog(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("KnuZoom 설정")
        win.attributes("-topmost", True)
        entries = {}
        for i, (label, name) in enumerate(_EDITABLE):
            tk.Label(win, text=label).grid(row=i, column=0, sticky="w", padx=6, pady=2)
            val = getattr(self.s, name)
            e = tk.Entry(win, width=34)
            e.insert(0, ", ".join(val) if isinstance(val, list) else str(val))
            e.grid(row=i, column=1, padx=6, pady=2)
            entries[name] = e

        def save() -> None:
            new_values = {}
            try:
                for name, e in entries.items():
                    raw = e.get().strip()
                    cur = getattr(self.s, name)
                    if isinstance(cur, list):
                        new = [x.strip() for x in raw.split(",") if x.strip()]
                    elif isinstance(cur, bool):
                        new = raw.lower() in ("1", "true", "yes")
                    elif isinstance(cur, int):
                        new = int(raw)
                    elif isinstance(cur, float):
                        new = float(raw)
                    else:
                        new = raw
                    new_values[name] = new
            except ValueError:
                messagebox.showerror("설정", "숫자 항목을 확인해 주세요.", parent=win)
                return
            candidate = Settings(**{**self.s.__dict__, **new_values})
            _, problems = sanitize_settings(candidate)
            if problems:
                labels = {n: l for l, n in _EDITABLE}
                bad = ", ".join(labels.get(p, p) for p in problems)
                messagebox.showerror("설정", f"허용 범위를 벗어난 항목이 있습니다: {bad}\n"
                                     "(WIDE 기준은 ZOOM 기준보다 작아야 하고, 시간은 0보다 커야 합니다)",
                                     parent=win)
                return
            for name, value in new_values.items():
                setattr(self.s, name, value)
            save_settings(self.s, self.path)
            win.destroy()

        tk.Button(win, text="저장", command=save).grid(row=len(_EDITABLE), column=1, sticky="e",
                                                     padx=6, pady=6)

    def show(self) -> None:
        """다른 스레드에서 불러도 된다."""
        self.calls.post(self.root.deiconify)

    def quit(self) -> None:
        """다른 스레드에서 불러도 된다."""
        self.calls.post(self._close)

    def _close(self) -> None:
        self._closed = True
        self.root.destroy()

    def run(self) -> None:
        self.root.after(POLL_MS, self._poll)
        self.root.mainloop()


def tray_image(color: str):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), "white")
    ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
    return img


def start_tray(window: ControlWindow):
    """트레이 아이콘(열기/종료). pystray가 없으면 None."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    icon = pystray.Icon("KnuZoom", tray_image(GREEN), "KnuZoom", menu=pystray.Menu(
        pystray.MenuItem("열기", lambda: window.show(), default=True),
        pystray.MenuItem("종료", lambda: (icon.stop(), window.on_quit(), window.quit())),
    ))
    icon.run_detached()
    return icon


def register_emergency_hotkey(hotkey: str, engine: Engine) -> bool:
    try:
        import keyboard
        # 조합 키 중 하나를 뗄 때 실행한다(나머지 키는 아직 눌려 있을 수 있음).
        # 남은 Ctrl 등은 WindowsZoomAdapter.press_toggle이 Alt+A 전에 떼어 준다.
        keyboard.add_hotkey(hotkey, engine.emergency_stop, trigger_on_release=True)
        return True
    except Exception:
        return False
