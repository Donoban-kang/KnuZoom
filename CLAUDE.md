# KnuZoom

추적 카메라가 발언자 쪽으로 확대되면 Zoom Workplace 마이크를 자동으로 음소거 해제하고, 넓게 비추면 다시 음소거하는 Windows 보조 프로그램. 회의 녹화 기능도 포함한다.

## 구조

- `src/knuzoom/`: 앱 본체. 진입점은 `__main__.py`
  - 영상 입출력 `video_io.py`(카메라 → 가상 카메라 "KnuZoom Camera" → Zoom)
  - 확대 판단 `faces.py`·`detector.py`(MediaPipe 얼굴 검출) → 상태 확정 `stabilizer.py` → `engine.py`
  - Zoom 제어 `mic.py`·`zoom_windows.py`(UI Automation으로 상태 확인 후 Alt+A)
  - 진행자 화면 `ui*.py`, 트레이 `tray_state.py`, 보정 `calibration.py`, 설정 `config.py`
  - 녹화 `recording/`(FFmpeg 명령 생성, 오디오 믹스, 오버레이, 동의, 저장)
- `tests/`: pytest. Windows·Zoom 의존부는 `tests/fakes.py`의 가짜 구현(`FakeZoom` 등)으로 대체한다
- `scripts/`: 실기 점검용(`probe_zoom.py`, `record_smoke.py`)
- `knuzoom.spec`(PyInstaller), `installer/knuzoom.iss`(Inno Setup)
- `docs/superpowers/specs/`·`plans/`: 설계서와 구현 계획. 동작 규칙(판정 기준·오작동 대응·개인정보)은 설계서가 기준이다

## 개발 명령

```bash
pip install -e ".[dev]"            # Windows 실기: ".[windows,dev]"
pytest -q
```

- Python 3.11 전용(`>=3.11,<3.12`). `mediapipe==0.10.14` 고정
- Windows 전용 패키지(`pywinauto`, `keyboard`, `pystray`, `soundcard`, `pygrabber`)는 함수 안에서 지연 import한다. 모듈 최상단에서 import하지 말 것
- 플랫폼 분기는 `sys.platform == "win32"`로 한다

## CI

`.github/workflows/build-windows.yml`이 `main`과 `claude/**` 브랜치 push, PR에서 Windows 러너로 돈다: pytest → FFmpeg(LGPL) 녹화 시험 → PyInstaller 빌드 → `KnuZoom.exe` 실행 확인(로그에 "KnuZoom 시작" 기록) → Inno Setup 설치 파일. Windows 실기 동작은 로컬(Linux) 시험만으로 확인되지 않으므로 CI 결과로 확인한다.

## 규칙

- 코드 주석·로그·UI 문구·커밋 메시지는 한국어. 커밋은 `feat:`·`fix:`·`test:`·`docs:`·`build:`·`chore:` 접두어
- 버전은 `pyproject.toml`의 `version` 한 곳에서 관리한다(CI가 읽어 설치 파일 이름에 쓴다)
- 얼굴 검출·녹화는 개인정보와 연관된다. 영상·얼굴 데이터를 저장하거나 외부로 보내는 변경은 설계서 「8. 개인정보」와 `recording/consent.py`의 동의 흐름을 먼저 확인한다
