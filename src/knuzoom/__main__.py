"""KnuZoom 실행: 설정 → Zoom 어댑터·제어기·엔진 → 카메라 스레드 → 진행자 창."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from knuzoom.config import default_settings_path, load_settings_with_problems
from knuzoom.engine import Engine
from knuzoom.faces import FaceAnalyzer
from knuzoom.mic import MicController
from knuzoom.ui import ControlWindow, register_emergency_hotkey, start_tray
from knuzoom.video_io import CameraPipeline, open_real_capture, open_real_vcam
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


def main() -> None:
    settings_path = default_settings_path()
    s, problems = load_settings_with_problems(settings_path)
    log = make_file_log(settings_path.parent)
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

    analyzer = FaceAnalyzer(s.min_face_confidence)
    pipeline = CameraPipeline(
        s,
        open_capture=lambda: open_real_capture(s),
        open_vcam=lambda: open_real_vcam(s),
        analyze=analyzer.analyze,
        on_stats=engine.on_stats,
        on_lost=engine.on_camera_lost,
        on_error=engine.on_error,
        clock=time.monotonic,
    )
    stop = threading.Event()
    cam_thread = threading.Thread(target=pipeline.run, args=(stop,), daemon=True, name="knuzoom-cam")

    window = ControlWindow(engine, s, settings_path, on_quit=stop.set)
    if not register_emergency_hotkey(s.emergency_hotkey, engine):
        log(f"{datetime.now():%H:%M:%S} 긴급 정지 단축키 등록 실패: {s.emergency_hotkey}")
    tray = start_tray(window)

    cam_thread.start()
    try:
        window.run()
    finally:
        stop.set()
        cam_thread.join(timeout=3)
        worker.shutdown(wait=True, cancel_futures=True)  # 진행 중인 제어만 끝내고 대기 요청은 버림
        engine.shutdown()                                # 종료 시 항상 음소거
        pipeline.close()
        analyzer.close()
        if tray is not None:
            tray.stop()


if __name__ == "__main__":
    main()
