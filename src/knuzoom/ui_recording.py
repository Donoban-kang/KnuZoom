"""진행자 창의 녹화 부분: [● 녹화]/[■ 녹화 종료], 녹화 상태 줄, 동의 확인 창, 보관기간 경과 파일 확인."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import messagebox

from knuzoom.config import Settings
from knuzoom.recording.consent import METHODS, ConsentRecord, notice_text, validate
from knuzoom.recording.recorder import Recorder
from knuzoom.recording.storage import delete_recording, expired_recordings, recording_dir

RED, GRAY = "#d64545", "#666666"
FONT = "Malgun Gothic"


def _hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


class RecordingPanel:
    def __init__(self, root: tk.Misc, recorder: Recorder, s: Settings) -> None:
        self.root = root
        self.recorder = recorder
        self.s = s
        frame = tk.Frame(root)
        frame.pack(fill="x", padx=8, pady=(2, 2))
        self.button = tk.Button(frame, text="● 녹화", width=26, command=self._toggle)
        self.button.pack()
        self.status = tk.Label(frame, text="", fg=RED, font=(FONT, 10, "bold"))
        self.status.pack()
        self.warning = tk.Label(frame, text="", fg=RED, font=(FONT, 9), wraplength=260)
        self.warning.pack()

    def poll(self) -> None:
        try:
            self.recorder.tick()
        except Exception as exc:  # 녹화 오류는 녹화 줄에만 표시(음소거 제어와 분리)
            self.warning.config(text=f"녹화 오류: {exc}")
        if self.recorder.recording:
            self.button.config(text="■ 녹화 종료")
            self.status.config(text=f"● 녹화 중 {_hms(self.recorder.elapsed_s)}")
        elif self.recorder.finalizing:
            self.button.config(text="● 녹화")
            self.status.config(text="녹화 파일 마무리 중…")
        else:
            self.button.config(text="● 녹화")
            self.status.config(text="")
        self.warning.config(text=self.recorder.warning or "")

    def _toggle(self) -> None:
        if self.recorder.recording:
            if messagebox.askyesno("녹화 종료", "녹화를 종료할까요?", parent=self.root):
                self.recorder.stop("사용자 종료")
        else:
            ConsentDialog(self.root, self.recorder, self.s)


class ConsentDialog:
    """녹화 시작의 유일한 경로. 모든 기관 동의·회의명·방법·목적·보관기간이 맞아야 [녹화 시작]이 켜진다."""

    def __init__(self, root: tk.Misc, recorder: Recorder, s: Settings) -> None:
        self.recorder = recorder
        self.s = s
        self.win = win = tk.Toplevel(root)
        win.title("녹화 동의 확인")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.transient(root)

        def row(label: str, r: int) -> None:
            tk.Label(win, text=label, anchor="w").grid(row=r, column=0, sticky="nw", padx=8, pady=3)

        self.meeting = tk.StringVar()
        row("회의명", 0)
        tk.Entry(win, textvariable=self.meeting, width=32).grid(row=0, column=1, sticky="w", padx=8)

        row("동의 받은 기관", 1)
        box = tk.Frame(win)
        box.grid(row=1, column=1, sticky="w", padx=8)
        self.party_box = box
        self.parties: dict[str, tk.BooleanVar] = {}
        for p in s.consent_parties:
            self._add_party_checkbox(p)
        addrow = tk.Frame(win)
        addrow.grid(row=1, column=2, sticky="w", padx=(0, 8))
        self.new_party = tk.StringVar()
        tk.Entry(addrow, textvariable=self.new_party, width=10).pack(side="left")
        tk.Button(addrow, text="기관 추가", command=self._add_party).pack(side="left", padx=2)

        row("동의 방법", 2)
        mbox = tk.Frame(win)
        mbox.grid(row=2, column=1, sticky="w", padx=8)
        self.method = tk.StringVar(value="")
        for m in METHODS:
            tk.Radiobutton(mbox, text=m, value=m, variable=self.method, command=self._refresh).pack(anchor="w")
        self.method_other = tk.StringVar()
        tk.Entry(mbox, textvariable=self.method_other, width=28).pack(anchor="w")

        self.purpose = tk.StringVar(value="회의록 작성")
        row("녹화 목적", 3)
        tk.Entry(win, textvariable=self.purpose, width=32).grid(row=3, column=1, sticky="w", padx=8)

        self.retention = tk.StringVar(value=str(s.retention_days))
        row("보관기간(일)", 4)
        tk.Entry(win, textvariable=self.retention, width=8).grid(row=4, column=1, sticky="w", padx=8)

        self.error = tk.Label(win, text="", fg=RED, wraplength=360, justify="left")
        self.error.grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 0))
        tk.Label(win, text=f"녹화 중에는 {s.site_name} 영상에 '녹화 중' 표시가 나가며 끌 수 없습니다.",
                 fg=GRAY, wraplength=360, justify="left").grid(row=6, column=0, columnspan=2, sticky="w", padx=8)
        self.start_btn = tk.Button(win, text="녹화 시작", width=12, command=self._start, state="disabled")
        self.start_btn.grid(row=7, column=1, sticky="e", padx=8, pady=8)
        for var in (self.meeting, self.method_other, self.purpose, self.retention):
            var.trace_add("write", lambda *_: self._refresh())
        self._refresh()

    def _add_party_checkbox(self, name: str) -> None:
        var = tk.BooleanVar(value=False)
        self.parties[name] = var
        tk.Checkbutton(self.party_box, text=name, variable=var, command=self._refresh).pack(side="left")

    def _add_party(self) -> None:
        """회의에 늦게 들어온 기관: 이번 녹화의 동의 대상에 추가(체크해야 시작 가능)."""
        name = self.new_party.get().strip()
        if name and name not in self.parties:
            self._add_party_checkbox(name)
        self.new_party.set("")
        self._refresh()

    def record(self) -> ConsentRecord:
        try:
            days = int(self.retention.get())
        except ValueError:
            days = 0
        return ConsentRecord(
            meeting=self.meeting.get(), site_name=self.s.site_name,
            required_parties=list(self.parties),
            agreed_parties=[p for p, v in self.parties.items() if v.get()],
            method=self.method.get(), method_other=self.method_other.get(),
            purpose=self.purpose.get(), retention_days=days)

    def _refresh(self) -> None:
        errors = validate(self.record())
        self.error.config(text=errors[0] if errors else "")
        self.start_btn.config(state="disabled" if errors else "normal")

    def _start(self) -> None:
        rec = self.record()
        result = self.recorder.start(rec)
        if not result.ok:
            self.error.config(text=result.message)
            return
        text = notice_text(rec)
        self.win.clipboard_clear()
        self.win.clipboard_append(text)
        self.win.destroy()
        messagebox.showinfo("녹화 시작", "안내 문구를 복사했습니다. Zoom 채팅에 붙여넣어 주세요.\n\n" + text)


def ask_delete_expired(root: tk.Misc, s: Settings, today: date | None = None) -> None:
    """보관기간이 지난 녹화를 보여 주고, 확인을 받은 경우에만 지운다."""
    expired = expired_recordings(recording_dir(s), today or date.today())
    if not expired:
        return
    names = "\n".join(f"· {p.name}" for p in expired[:15]) + ("\n…" if len(expired) > 15 else "")
    if messagebox.askyesno("보관기간 경과 녹화",
                           f"보관기간이 지난 녹화가 {len(expired)}개 있습니다.\n\n{names}\n\n"
                           "녹화 파일과 동의 기록을 삭제할까요? ('아니요'를 고르면 다음에 다시 묻습니다)",
                           parent=root):
        failed = []
        for p in expired:
            try:
                delete_recording(Path(p))
            except OSError:
                failed.append(p.name)
        if failed:
            messagebox.showerror("삭제 실패", "삭제하지 못한 파일:\n" + "\n".join(failed), parent=root)
