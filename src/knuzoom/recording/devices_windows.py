"""Windows 녹화 음성 장치: 스피커 루프백(상대 기관 소리)과 기본 마이크(회의실), soundcard(WASAPI) 사용.

장치는 처음 read()를 부르는 스레드(녹화 음성 스레드)에서 연다(Windows COM은 스레드별 초기화가 필요).
한쪽 장치를 열지 못하면 그쪽은 계속 None을 돌려주고, 녹화 관리자가 경고를 띄운다.
"""
from __future__ import annotations

import numpy as np

from knuzoom.recording.audio_mix import BLOCK, CHANNELS, SAMPLE_RATE


def _co_initialize() -> None:
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED, 이미 초기화돼 있으면 무시
    except Exception:
        pass


def _open(mic):
    """2채널로 열고, 안 되면 1채널로 연다. (recorder, 채널 수) 또는 (None, 0)."""
    for ch in (CHANNELS, 1):
        try:
            rec = mic.recorder(samplerate=SAMPLE_RATE, channels=ch, blocksize=BLOCK)
            rec.__enter__()
            return rec, ch
        except Exception:
            continue
    return None, 0


def _to_stereo(block: np.ndarray, frames: int) -> np.ndarray:
    block = np.asarray(block, np.float32)
    if block.ndim == 1:
        block = block[:, None]
    if block.shape[1] == 1:
        block = np.repeat(block, 2, axis=1)
    out = np.zeros((frames, CHANNELS), np.float32)
    n = min(frames, len(block))
    out[:n] = block[:n, :CHANNELS]
    return out


class WindowsAudioSource:
    def __init__(self) -> None:
        self._opened = False
        self._loop = self._mic = None

    def _open_devices(self) -> None:
        self._opened = True
        _co_initialize()
        try:
            import soundcard as sc
        except Exception:
            return
        try:
            speaker = sc.default_speaker()
            self._loop, _ = _open(sc.get_microphone(id=str(speaker.name), include_loopback=True))
        except Exception:
            self._loop = None
        try:
            self._mic, _ = _open(sc.default_microphone())
        except Exception:
            self._mic = None

    def _read_one(self, rec, frames: int) -> np.ndarray | None:
        if rec is None:
            return None
        try:
            return _to_stereo(rec.record(numframes=frames), frames)
        except Exception:
            return None

    def read(self, frames: int) -> tuple[np.ndarray | None, np.ndarray | None]:
        if not self._opened:
            self._open_devices()
        return self._read_one(self._loop, frames), self._read_one(self._mic, frames)

    def close(self) -> None:
        for rec in (self._loop, self._mic):
            if rec is not None:
                try:
                    rec.__exit__(None, None, None)
                except Exception:
                    pass
        self._loop = self._mic = None
