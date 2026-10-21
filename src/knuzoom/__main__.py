"""KnuZoom 실행: 설정 → Zoom 어댑터·제어기·엔진 → 카메라 스레드 → 진행자 창."""
from __future__ import annotations
import os as _os, sys as _sys
_TRACE = []
def _apt(tag):
    if _sys.platform != "win32":
        return
    import ctypes
    t = ctypes.c_int(-1); q = ctypes.c_int(-1)
    hr = ctypes.windll.ole32.CoGetApartmentType(ctypes.byref(t), ctypes.byref(q))
    _TRACE.append(f"{tag}: hr={hr & 0xFFFFFFFF:#x} type={t.value} qual={q.value}")
    with open(_os.path.join(_os.environ.get("TEMP", "."), "knuzoom_com_trace.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(_TRACE))
_apt("start")

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from knuzoom.config import default_settings_path, load_settings_with_problems
_apt("after knuzoom.config")
from knuzoom.engine import Engine
_apt("after knuzoom.engine")
from knuzoom.faces import FaceAnalyzer
_apt("after knuzoom.faces")
from knuzoom.mic import MicController
_apt("after knuzoom.mic")
from knuzoom.recording.ffmpeg_cmd import find_ffmpeg, make_spawn
_apt("after knuzoom.recording.ffmpeg_cmd")
from knuzoom.recording.recorder import Recorder
_apt("after knuzoom.recording.recorder")
from knuzoom.single_instance import acquire, show_already_running
_apt("after knuzoom.single_instance")
from knuzoom.ui import ControlWindow, register_emergency_hotkey, start_tray
_apt("after knuzoom.ui")
from knuzoom.video_io import CameraPipeline, open_real_capture, open_real_vcam
_apt("after knuzoom.video_io")
from knuzoom.zoom_windows import WindowsZoomAdapter


def make_file_log(base_dir):
    lock = threading.Lock()

    def log(line: str) -> None:
        path = base_dir / "logs" / f"knuzoom-{datetime.now():%Y%m%d}.log"
        with lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    return log


def make_recorder(s, engine, pipeline, log, log_dir: Path) -> Recorder:
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else None

    def overlay_factory(site_name):  # 녹화 시작 때 '지금' 기관 이름으로 그린다. 실패하면 녹화 시작 거부
        from knuzoom.recording.overlay import RecordingOverlay
        return RecordingOverlay(site_name).apply

    def overlay_alive():  # 최근 5초 안에 가상 카메라로 영상을 보냈는지(= 다른 기관이 표시를 볼 수 있는지)
        sent = pipeline.last_sent_at
        return sent is not None and time.monotonic() - sent < 5.0

    def open_audio():
        from knuzoom.recording.devices_windows import WindowsAudioSource
        return WindowsAudioSource()

    recorder = Recorder(
        s, ffmpeg=find_ffmpeg(app_dir), spawn=make_spawn(log_dir), open_audio=open_audio,
        gate_open=engine.mic_gate_open,
        meeting_active=lambda: engine.meeting_present() is not False,
        set_filter=lambda f: setattr(pipeline, "frame_filter", f),
        log=log, overlay_factory=overlay_factory, overlay_alive=overlay_alive)
    pipeline.on_filter_error = recorder.on_overlay_error
    return recorder


def main() -> None:
    if not acquire():  # 두 개가 실행되면 같은 마이크를 서로 반대로 조작할 수 있다
        show_already_running()
        return
    settings_path = default_settings_path()
    first_run = not settings_path.exists()
    s, problems = load_settings_with_problems(settings_path)
    log = make_file_log(settings_path.parent)
    log(f"{datetime.now():%H:%M:%S} KnuZoom 시작")
    if problems:
        log(f"{datetime.now():%H:%M:%S} 설정 기본값 복원: {', '.join(problems)}")

    worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="knuzoom-mic")

    def run(job):
        def safe():
            try:
                job()
            except Exception as exc:  # 마이크 제어 실패는 기록만 하고 앱은 계속
                log(f"{datetime.now():%H:%M:%S} 마이크 제어 오류: {exc!r}")
        worker.submit(safe)

    mic = MicController(WindowsZoomAdapter(s), s.verify_delay_s)
    engine = Engine(s, mic, log, clock_hms=lambda: f"{datetime.now():%H:%M:%S}", run=run)

    from knuzoom.camera_select import CameraControl
    camera = CameraControl(s, settings_path, reopen=lambda: None, camera_changed=engine.camera_changed)

    def open_capture():  # 다시 연결할 때마다 장치 목록을 새로 보고, 저장된 '우리 카메라 이름'으로 번호를 찾는다
        camera.refresh()
        return open_real_capture(s, camera.current_index())

    analyzer = FaceAnalyzer(s.min_face_confidence)
    pipeline = CameraPipeline(
        s,
        open_capture=open_capture,
        open_vcam=lambda: open_real_vcam(s),
        analyze=analyzer.analyze,
        on_stats=engine.on_stats,
        on_lost=engine.on_camera_lost,
        on_error=engine.on_error,
        clock=time.monotonic,
    )
    stop = threading.Event()
    cam_thread = threading.Thread(target=pipeline.run, args=(stop,), daemon=True, name="knuzoom-cam")

    recorder = make_recorder(s, engine, pipeline, log, settings_path.parent / "logs")
    camera.reopen = pipeline.reopen
    window = ControlWindow(engine, s, settings_path, on_quit=stop.set, recorder=recorder,
                           camera=camera, last_frame=lambda: pipeline.last_frame)
    if not register_emergency_hotkey(s.emergency_hotkey, engine):
        log(f"{datetime.now():%H:%M:%S} 긴급 정지 단축키 등록 실패: {s.emergency_hotkey}")
    tray = start_tray(window)
    window.tray = tray

    cam_thread.start()
    from knuzoom.ui_recording import ask_delete_expired
    from knuzoom.recording.storage import finalize_orphans, recording_dir
    for orphan in finalize_orphans(recording_dir(s), datetime.now()):  # 지난번 강제 종료로 마무리 못 한 녹화
        log(f"{datetime.now():%H:%M:%S} 마무리되지 않은 녹화 기록 보완: {orphan.name}")
    window.root.after(1000, lambda: ask_delete_expired(window.root, s))
    if first_run:  # 처음 실행: 우리 기관 이름과 우리 캠퍼스 카메라를 고른다
        window.root.after(500, lambda: window.open_camera_dialog(first_run=True))
    try:
        window.run()
    finally:
        try:
            recorder.stop("프로그램 종료")  # 표시를 끄고 마무리는 백그라운드로(오래 걸려도 아래 음소거를 막지 않음)
        except Exception as exc:
            log(f"{datetime.now():%H:%M:%S} 녹화 종료 오류: {exc!r}")
        stop.set()
        cam_thread.join(timeout=3)
        worker.shutdown(wait=True, cancel_futures=True)  # 진행 중인 제어만 끝내고 대기 요청은 버림
        engine.shutdown()                                # 종료 시 항상 음소거
        recorder.wait_finalized(30)                      # 녹화 파일·동의 기록(해시) 마무리 대기
        pipeline.close()
        analyzer.close()
        if tray is not None:
            tray.stop()


if __name__ == "__main__":
    main()
