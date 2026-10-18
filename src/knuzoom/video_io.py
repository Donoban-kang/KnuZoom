"""카메라 영상을 가상 카메라로 그대로 넘기고, 일정 간격으로 분석 콜백을 호출한다."""
from __future__ import annotations

import threading
import time
from typing import Callable, Protocol

import cv2
import numpy as np

from knuzoom.config import Settings
from knuzoom.detector import FaceStats

RECONNECT_INTERVAL_S = 2.0


class Capture(Protocol):
    def read(self) -> tuple[bool, np.ndarray | None]: ...
    def release(self) -> None: ...


class VCam(Protocol):
    def send(self, frame_rgb: np.ndarray) -> None: ...
    def sleep_until_next_frame(self) -> None: ...
    def close(self) -> None: ...


def open_real_capture(s: Settings) -> Capture:
    cap = cv2.VideoCapture(s.camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        raise OSError(f"카메라 {s.camera_index}번을 열 수 없습니다")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, s.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, s.height)
    cap.set(cv2.CAP_PROP_FPS, s.fps)
    return cap


def open_real_vcam(s: Settings) -> VCam:
    import pyvirtualcam
    return pyvirtualcam.Camera(width=s.width, height=s.height, fps=s.fps, device="OBS Virtual Camera")


class CameraPipeline:
    def __init__(self, s: Settings,
                 open_capture: Callable[[], Capture],
                 open_vcam: Callable[[], VCam],
                 analyze: Callable[[np.ndarray], FaceStats],
                 on_stats: Callable[[float, FaceStats], None],
                 on_lost: Callable[[float], None],
                 on_error: Callable[[Exception], None],
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.s = s
        self.open_capture = open_capture
        self.open_vcam = open_vcam
        self.analyze = analyze
        self.on_stats = on_stats
        self.on_lost = on_lost
        self.on_error = on_error
        self.clock = clock
        self._cap: Capture | None = None
        self._vcam: VCam | None = None
        self._fails = 0
        self._lost = False
        self._lost_at = 0.0
        self._last_analysis: float | None = None
        self._vcam_retry_at = -1.0

    def step(self) -> None:
        """프레임 1장을 처리한다."""
        t = self.clock()
        if self._cap is None:
            if self._lost and t - self._lost_at < RECONNECT_INTERVAL_S:
                return
            try:
                self._cap = self.open_capture()
            except Exception:
                # 열기 실패도 끊김으로 알린다(한 번만). 이후 재시도는 간격을 둔다.
                if not self._lost:
                    self._lost = True
                    self.on_lost(t)
                self._lost_at = t
                return
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._fails += 1
            if self._fails >= self.s.camera_lost_frames:
                if not self._lost:
                    self._lost = True
                    self.on_lost(t)
                self._lost_at = t
                self._fails = 0
                self._cap.release()
                self._cap = None
            return
        self._fails = 0
        self._lost = False
        self._send(t, frame)
        period = 1.0 / self.s.analysis_fps
        if self._last_analysis is None or t - self._last_analysis >= period - 1e-6:
            self._last_analysis = t
            try:
                self.on_stats(t, self.analyze(frame))
            except Exception as exc:  # 분석 오류는 알리고 다음 프레임을 계속 처리한다
                self.on_error(exc)

    def _send(self, t: float, frame: np.ndarray) -> None:
        """가상 카메라로 송출. 송출 실패는 분석과 분리하고, 열기 재시도는 간격을 둔다."""
        try:
            if self._vcam is None:
                if t < self._vcam_retry_at:
                    return
                self._vcam = self.open_vcam()
            if frame.shape[1] != self.s.width or frame.shape[0] != self.s.height:
                frame = cv2.resize(frame, (self.s.width, self.s.height))  # 가상 카메라 크기와 달라도 송출되게
            self._vcam.send(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        except Exception as exc:
            self._vcam_retry_at = t + RECONNECT_INTERVAL_S
            if self._vcam is not None:
                try:
                    self._vcam.close()
                except Exception:
                    pass
                self._vcam = None
            self.on_error(exc)

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.step()
            except Exception as exc:  # 캡처 장치 예외로 스레드가 죽지 않게 한다
                self.on_error(exc)
                if self._cap is not None:
                    try:
                        self._cap.release()
                    except Exception:
                        pass
                    self._cap = None
                time.sleep(0.1)
            if self._cap is None:
                time.sleep(0.1)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._vcam is not None:
            self._vcam.close()
            self._vcam = None
