"""우리 캠퍼스 판정 카메라 선택 창(첫 실행 시 기관 이름도 함께 받음)."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from typing import Callable

import numpy as np

from knuzoom.camera_select import CameraControl
from knuzoom.config import save_settings

PREVIEW_W, PREVIEW_H = 320, 180
FONT = "Malgun Gothic"


def grab_preview(index: int) -> np.ndarray | None:
    """사용 중이 아닌 카메라에서 한 장만 읽는다(Windows DirectShow). 실패하면 None."""
    try:
        import cv2
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        try:
            if not cap.isOpened():
                return None
            ok, frame = cap.read()
            return frame if ok else None
        finally:
            cap.release()
    except Exception:
        return None


class CameraDialog:
    def __init__(self, root: tk.Misc, ctl: CameraControl, last_frame: Callable[[], np.ndarray | None],
                 on_done: Callable[[], None] = lambda: None, first_run: bool = False) -> None:
        self.ctl = ctl
        self.last_frame = last_frame
        self.on_done = on_done
        self.first_run = first_run
        self.win = win = tk.Toplevel(root)
        win.title("처음 설정" if first_run else "우리 캠퍼스 카메라 선택")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        r = 0
        if first_run:
            tk.Label(win, text="KnuZoom 처음 설정", font=(FONT, 12, "bold")).grid(row=r, column=0, columnspan=2,
                                                                           sticky="w", padx=8, pady=(8, 2))
            r += 1
            tk.Label(win, text="우리 기관 이름").grid(row=r, column=0, sticky="w", padx=8)
            self.site = tk.StringVar(value=ctl.s.site_name)
            tk.Entry(win, textvariable=self.site, width=20).grid(row=r, column=1, sticky="w", padx=8)
            r += 1
        tk.Label(win, text="음소거 판정에 쓸 '우리 캠퍼스' 추적 카메라를 고르세요.\n"
                           "(Zoom으로 내보내는 가상 카메라는 목록에 나오지 않습니다)",
                 justify="left").grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 2))
        r += 1
        self.listbox = tk.Listbox(win, height=6, width=40, exportselection=False)
        self.listbox.grid(row=r, column=0, sticky="n", padx=8)
        self.preview = tk.Label(win, text="미리보기", width=40, height=10, bg="#222", fg="#aaa")
        self.preview.grid(row=r, column=1, padx=8)
        r += 1
        btns = tk.Frame(win)
        btns.grid(row=r, column=0, columnspan=2, sticky="e", padx=8, pady=8)
        tk.Button(btns, text="목록 새로고침", command=self._load).pack(side="left", padx=2)
        tk.Button(btns, text="미리보기", command=self._preview).pack(side="left", padx=2)
        tk.Button(btns, text="이 카메라 사용", command=self._use).pack(side="left", padx=2)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._preview())
        if first_run:  # 처음 설정은 끝내야 한다(기관 이름이 녹화 표시·동의 기록에 쓰임)
            win.protocol("WM_DELETE_WINDOW", self._refuse_close)
        self._photo = None
        self._preview_seq = 0
        self.choices: list[tuple[int, str]] = []
        self._load()

    def _load(self) -> None:
        self.choices = self.ctl.refresh()
        self.listbox.delete(0, "end")
        current = self.ctl.current_index()
        for pos, (idx, name) in enumerate(self.choices):
            self.listbox.insert("end", f"{name}  (번호 {idx})" + ("  ← 사용 중" if idx == current else ""))
            if idx == current:
                self.listbox.selection_set(pos)
        if not self.choices:
            self.listbox.insert("end", "카메라를 찾지 못했습니다")

    def _selected(self) -> tuple[int, str] | None:
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.choices):
            return None
        return self.choices[sel[0]]

    def _preview(self) -> None:
        choice = self._selected()
        if choice is None:
            return
        idx, _ = choice
        if idx == self.ctl.current_index():
            self._show_frame(self.last_frame())
            return
        # 사용 중이 아닌 카메라는 여는 데 몇 초 걸릴 수 있어 백그라운드에서 읽는다(진행자 창이 멈추지 않게)
        self._preview_seq += 1
        seq = self._preview_seq
        self.preview.config(image="", text="미리보기 불러오는 중…")
        result: dict = {}

        def work():
            result["frame"] = grab_preview(idx)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        self._wait_preview(t, result, seq)

    def _wait_preview(self, t: threading.Thread, result: dict, seq: int) -> None:
        if not self.win.winfo_exists() or seq != self._preview_seq:
            return  # 창이 닫혔거나 다른 카메라를 다시 고름
        if t.is_alive():
            self.win.after(100, lambda: self._wait_preview(t, result, seq))
            return
        self._show_frame(result.get("frame"))

    def _show_frame(self, frame) -> None:
        if frame is None:
            self.preview.config(image="", text="미리보기를 가져올 수 없습니다")
            return
        from PIL import Image, ImageTk
        rgb = frame[..., ::-1]
        img = Image.fromarray(np.ascontiguousarray(rgb)).resize((PREVIEW_W, PREVIEW_H))
        self._photo = ImageTk.PhotoImage(img)
        self.preview.config(image=self._photo, text="", width=PREVIEW_W, height=PREVIEW_H)

    def _refuse_close(self) -> None:
        messagebox.showinfo("처음 설정", "우리 기관 이름을 입력하고 [이 카메라 사용]을 눌러 처음 설정을 마쳐 주세요.\n"
                            "(카메라가 아직 없으면 목록에서 고르지 않고 눌러도 됩니다)", parent=self.win)

    def _use(self) -> None:
        choice = self._selected()
        if self.first_run:
            name = self.site.get().strip()
            if not name:
                messagebox.showerror("처음 설정", "우리 기관 이름을 입력해 주세요.", parent=self.win)
                return
            self.ctl.s.site_name = name
            save_settings(self.ctl.s, self.ctl.path)
        if choice is not None and not self.ctl.choose(choice[0]):
            messagebox.showerror("카메라 선택", "이 카메라는 사용할 수 없습니다.", parent=self.win)
            return
        self.win.destroy()
        self.on_done()
