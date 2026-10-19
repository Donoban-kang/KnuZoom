# KnuZoom 녹화 기능 구현 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 참석 기관 동의를 확인한 뒤 B대학 PC의 회의 화면·소리를 mp4로 녹화하고, 녹화 중임을 모든 참석 기관 화면에 표시하는 기능을 추가한다.

**Architecture:** 판단 로직(동의 검증·파일 관리·표시 합성·음성 혼합·명령 생성·녹화 수명 관리)은 `src/knuzoom/recording/` 아래 순수 Python으로 두고 장치·프로세스는 주입해 Linux에서 시험한다. FFmpeg가 화면(ddagrab)을 캡처·인코딩하고, KnuZoom이 섞은 음성을 표준입력으로 넘긴다. "녹화 중" 표시는 기존 카메라 파이프라인의 송출 직전 단계에 프레임 필터로 끼운다.

**Tech Stack:** Python 3.11, numpy, Pillow(표시 그리기), soundcard(WASAPI 루프백·마이크, Windows), FFmpeg LGPL 빌드(`ddagrab`, `h264_mf`, `aac`), 기존 tkinter UI, GitHub Actions(windows-latest)

**Spec:** `docs/superpowers/specs/2026-10-19-knuzoom-recording-design.md`

## Global Constraints

- 녹화 시작 경로는 동의 확인 창 하나뿐이며, `consent_parties`를 **모두** 체크해야 시작 가능.
- 녹화 중에는 가상 카메라 프레임 우상단에 `녹화 중 ({site_name})` 표시. 끌 수 없음.
- 마이크 게이트 열림 = 엔진 `muted=False` 이고 (`confirmed` 또는 경고가 `상태 추정 중(Zoom 상태를 읽을 수 없음)`). 그 외 닫힘. 전환 페이드 20ms(48kHz에서 960샘플).
- 음성: 48000Hz, 2채널, s16le, 20ms 블록(960프레임). 클리핑은 -1~1 제한 후 변환.
- 영상: `ddagrab=output_idx={monitor}:framerate={fps}:draw_mouse=0` → `hwdownload,format=bgra,format=nv12` → `h264_mf` 4Mbps, 음성 `aac` 160k, `-af aresample=async=1`, `-shortest`, `-movflags +frag_keyframe+empty_moov+default_base_moof`.
- 디스크: 시작 시 여유 < `min_free_gb_start`(5) 이면 거부, 녹화 중 < `min_free_gb_stop`(2) 이면 자동 종료.
- Zoom 회의 창이 10초 이상 없으면 자동 종료. 긴급 정지는 녹화를 멈추지 않음.
- 파일 이름 `YYYYMMDD_HHMM_{회의명}.mp4`: `\/:*?"<>|` 제거, 회의명 30자 제한, 비면 `회의`, 중복 시 `_2`, `_3`…
- 동의 기록 `.txt`(UTF-8, mp4와 같은 이름) 문구는 설계서 5.2 그대로. 종료 시 `녹화 종료:`·`SHA-256:` 줄 채움.
- 채팅 안내 문구: `[안내] {site_name}에서 이 회의를 녹화하고 있습니다. (목적: {purpose}, 보관: {retention_days}일)`
- 보관기간 경과 파일은 **확인 후에만** mp4·txt 함께 삭제. 자동 삭제 없음.
- 녹화 기능 예외는 엔진·음소거 제어로 전파하지 않는다(녹화 경고는 별도 필드).
- 화면 문구(한국어 고정): "● 녹화", "■ 녹화 종료", "● 녹화 중 {HH:MM:SS}", "녹화: 스피커 소리 녹음 실패", "녹화: 마이크 녹음 실패", "녹화: 디스크 공간 부족으로 종료", "녹화: Zoom 회의가 끝나 종료", "녹화: FFmpeg 오류로 중단", "녹화를 시작할 수 없습니다: 디스크 여유 공간 부족(5GB 미만)", "녹화를 시작할 수 없습니다: FFmpeg를 찾을 수 없습니다".

## Review Focus

1. 회의명이 금지 문자뿐이거나 공백 → 파일 이름이 `..._회의.mp4`로 만들어져야 함 → Task 3 `test_filename_fallback_when_name_empty`.
2. 같은 분에 두 번 녹화 → 앞 파일을 덮어쓰지 않고 `_2` → Task 3 `test_unique_path_adds_suffix`.
3. 녹화 중 음성 장치가 읽기 오류 → 녹화는 무음으로 계속되고 경고 표시 → Task 7 `test_audio_read_error_continues_with_silence_and_warns`.
4. KnuZoom 종료 시 녹화 중 → 종료 전에 정상 종료되고 동의 기록에 SHA-256이 남아야 함, 두 번 호출해도 안전 → Task 7 `test_stop_is_idempotent_and_finalizes_record`.
5. Zoom 상태를 읽을 수 없는(추정 모드) 회의실 → 해제 상태면 마이크가 녹음돼야 함(아니면 B대학 발언이 녹화에서 빠짐) → Task 6 `test_gate_open_in_estimated_mode_when_unmuted`.

---

## 파일 구조
```
src/knuzoom/recording/__init__.py
src/knuzoom/recording/consent.py      # ConsentRecord, validate, render_text, notice_text
src/knuzoom/recording/storage.py      # 파일 이름·경로·디스크·보관기간·해시·삭제
src/knuzoom/recording/overlay.py      # RecordingOverlay
src/knuzoom/recording/audio_mix.py    # MicGate, mix, to_s16le
src/knuzoom/recording/ffmpeg_cmd.py   # build_command, find_ffmpeg
src/knuzoom/recording/recorder.py     # Recorder (수명 관리)
src/knuzoom/recording/devices_windows.py  # WindowsAudioSource (Windows 전용)
scripts/record_smoke.py               # CI 녹화 시험
tests/test_rec_*.py
```

---

### Task 1: 설정 항목 추가

**Files:** Modify `src/knuzoom/config.py`, `pyproject.toml`; Test `tests/test_config.py`

**Interfaces:**
- Produces: `Settings` 새 필드 `site_name: str = "B대학"`, `consent_parties: list[str] = ["A대학","C대학","D대학"]`, `recording_dir: str = ""`(빈 값 = 기본 폴더), `recording_monitor: int = 0`, `recording_fps: int = 30`, `retention_days: int = 30`, `min_free_gb_start: float = 5.0`, `min_free_gb_stop: float = 2.0`
- `_RANGES` 추가: `recording_monitor (0,15,True)`, `recording_fps (1,60,True)`, `retention_days (1,3650,True)`, `min_free_gb_start (0,1000,False)`, `min_free_gb_stop (0,1000,False)`. `recording_dir`은 빈 문자열 허용(문자열 검증 예외).
- 의존성: 공통에 `pillow`, `windows` 추가 묶음에 `soundcard`.

- [ ] **Step 1: 실패 테스트** — `test_recording_defaults`(위 기본값 그대로), `test_recording_dir_may_be_empty`(`sanitize_settings(Settings(recording_dir=""))` 문제 없음), `test_retention_days_out_of_range`(`retention_days=0` → 30 복원, problems에 포함)
- [ ] **Step 2: 실패 확인** — `pytest tests/test_config.py -q` → FAIL
- [ ] **Step 3: 구현** — `_valid`에서 `recording_dir`은 `isinstance(value, str)`만 확인.
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `feat: 녹화 설정 항목 추가`

---

### Task 2: 동의 정보(consent)

**Files:** Create `src/knuzoom/recording/__init__.py`, `src/knuzoom/recording/consent.py`; Test `tests/test_rec_consent.py`

**Interfaces:**
- Produces: `@dataclass ConsentRecord(meeting: str, site_name: str, required_parties: list[str], agreed_parties: list[str], method: str, method_other: str, purpose: str, retention_days: int)`; `METHODS = ("사전 공문", "회의 시작 시 구두 동의", "기타")`
- `validate(rec) -> list[str]` (오류 문구 목록, 비면 통과): `"회의명을 입력해 주세요"`, `"동의하지 않은 기관이 있습니다: {이름들}"`, `"동의 방법을 선택해 주세요"`, `"기타 동의 방법을 적어 주세요"`, `"녹화 목적을 입력해 주세요"`, `"보관기간은 1~3650일이어야 합니다"`
- `delete_date(start: datetime, days: int) -> date`
- `render_text(rec, start: datetime, file_name: str, end: datetime | None = None, sha256: str | None = None) -> str` — 설계서 5.2 형식. 동의 방법이 "기타"면 `기타({method_other})`. 미종료 시 `녹화 종료: (녹화 중)`, `SHA-256: (종료 시 계산)`.
- `notice_text(rec) -> str` — Global Constraints 문구.

- [ ] **Step 1: 실패 테스트**
```python
def rec(**kw):
    base = dict(meeting="○○협의회", site_name="B대학", required_parties=["A대학","C대학","D대학"],
                agreed_parties=["A대학","C대학","D대학"], method="사전 공문", method_other="",
                purpose="회의록 작성", retention_days=30)
    return ConsentRecord(**{**base, **kw})

def test_valid_record(): assert validate(rec()) == []
def test_missing_party_blocks():
    assert validate(rec(agreed_parties=["A대학"])) == ["동의하지 않은 기관이 있습니다: C대학, D대학"]
def test_blank_meeting_and_purpose():
    assert "회의명을 입력해 주세요" in validate(rec(meeting="  "))
    assert "녹화 목적을 입력해 주세요" in validate(rec(purpose=""))
def test_other_method_needs_text():
    assert validate(rec(method="기타")) == ["기타 동의 방법을 적어 주세요"]
def test_retention_range(): assert validate(rec(retention_days=0)) == ["보관기간은 1~3650일이어야 합니다"]
def test_render_text_while_recording():
    t = render_text(rec(), datetime(2026,10,19,14,0,5), "20261019_1400_○○협의회.mp4")
    assert "동의 기관: A대학, C대학, D대학" in t
    assert "보관기간: 30일 (삭제 예정일: 2026-11-18)" in t
    assert "녹화 종료: (녹화 중)" in t and "SHA-256: (종료 시 계산)" in t
def test_render_text_finished():
    t = render_text(rec(), datetime(2026,10,19,14,0,5), "f.mp4", datetime(2026,10,19,15,12,40), "ab12")
    assert "녹화 종료: 2026-10-19 15:12:40" in t and "SHA-256: ab12" in t
def test_notice_text():
    assert notice_text(rec()) == "[안내] B대학에서 이 회의를 녹화하고 있습니다. (목적: 회의록 작성, 보관: 30일)"
```
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `feat: 녹화 동의 정보 검증과 동의 기록 문구`

---

### Task 3: 저장 관리(storage)

**Files:** Create `src/knuzoom/recording/storage.py`; Test `tests/test_rec_storage.py`

**Interfaces:**
- Produces: `safe_filename(meeting: str, start: datetime) -> str`, `unique_path(directory: Path, filename: str) -> Path`, `recording_dir(s: Settings) -> Path`(빈 값이면 `Path.home()/"Documents"/"KnuZoom 녹화"`), `free_gb(path: Path) -> float`(`shutil.disk_usage`, 폴더가 없으면 가장 가까운 상위 폴더 기준), `sha256_file(path: Path) -> str`, `record_path(mp4: Path) -> Path`(`.txt`), `expired_recordings(directory: Path, today: date) -> list[Path]`(txt의 `삭제 예정일: YYYY-MM-DD` < today 인 mp4 경로, 파싱 불가 txt는 무시), `delete_recording(mp4: Path) -> None`(mp4·txt 존재하는 것만 삭제)

- [ ] **Step 1: 실패 테스트**
```python
T = datetime(2026,10,19,14,0)
def test_filename(): assert safe_filename("○○ 협의회", T) == "20261019_1400_○○ 협의회.mp4"
def test_filename_strips_forbidden(): assert safe_filename('a/b:c*?"<>|', T) == "20261019_1400_abc.mp4"
def test_filename_truncates(): assert safe_filename("가"*40, T) == "20261019_1400_" + "가"*30 + ".mp4"
def test_filename_fallback_when_name_empty(): assert safe_filename(' /:* ', T) == "20261019_1400_회의.mp4"  # RF1
def test_unique_path_adds_suffix(tmp_path):  # RF2
    (tmp_path/"x.mp4").write_bytes(b"1"); (tmp_path/"x_2.mp4").write_bytes(b"1")
    assert unique_path(tmp_path, "x.mp4") == tmp_path/"x_3.mp4"
def test_expired_recordings(tmp_path):
    for name, d in [("old", "2026-10-01"), ("new", "2026-12-01")]:
        (tmp_path/f"{name}.mp4").write_bytes(b"v")
        (tmp_path/f"{name}.txt").write_text(f"보관기간: 30일 (삭제 예정일: {d})", encoding="utf-8")
    (tmp_path/"bad.txt").write_text("엉망", encoding="utf-8")
    assert expired_recordings(tmp_path, date(2026,10,19)) == [tmp_path/"old.mp4"]
def test_delete_recording(tmp_path):
    (tmp_path/"a.mp4").write_bytes(b"v"); (tmp_path/"a.txt").write_text("t", encoding="utf-8")
    delete_recording(tmp_path/"a.mp4"); assert list(tmp_path.iterdir()) == []
def test_sha256(tmp_path):
    p = tmp_path/"f"; p.write_bytes(b"abc")
    assert sha256_file(p) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
def test_free_gb_for_missing_dir(tmp_path): assert free_gb(tmp_path/"없음"/"더없음") > 0
```
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현** — 해시는 1MB 단위로 읽기.
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `feat: 녹화 파일 이름·보관기간·해시 관리`

---

### Task 4: "녹화 중" 표시(overlay)

**Files:** Create `src/knuzoom/recording/overlay.py`; Test `tests/test_rec_overlay.py`

**Interfaces:**
- Produces: `class RecordingOverlay(site_name: str, font_path: str | None = None)` — 생성 시 RGBA 이미지 1회 작성(반투명 검정 배경 alpha 160, 빨간 원 RGB(220,40,40), 흰 글자 `녹화 중 ({site_name})`, 글자 크기 = 프레임 높이 기준이 아니라 고정 28px, 여백 12px). `apply(frame_bgr: np.ndarray) -> np.ndarray`(복사본에 우상단 여백 16px 위치로 알파 합성, 프레임보다 크면 잘라 합성). 글꼴: `font_path` → `C:\Windows\Fonts\malgun.ttf` → `PIL.ImageFont.load_default()`.

- [ ] **Step 1: 실패 테스트** — `test_overlay_marks_top_right_only`: 720x1280 검정 프레임에 apply → 우상단 영역(행 16~60, 열 끝-300~끝-16) 평균 밝기 > 0, 좌하단 1/4 영역은 전부 0; 원본 프레임은 변경 없음. `test_overlay_has_red_dot`: 합성 영역에 B<80, G<80, R>150 픽셀 존재(BGR). `test_overlay_on_tiny_frame_does_not_crash`: 40x60 프레임 → 같은 크기 반환.
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `feat: 가상 카메라용 녹화 중 표시`

---

### Task 5: 음성 혼합(audio_mix)

**Files:** Create `src/knuzoom/recording/audio_mix.py`; Test `tests/test_rec_audio.py`

**Interfaces:**
- Produces: `SAMPLE_RATE = 48000`, `CHANNELS = 2`, `BLOCK = 960`; `class MicGate(fade: int = 960)`: `process(block: np.ndarray, open_: bool) -> np.ndarray` — 내부 이득 0~1을 블록 내 샘플 단위로 목표값(1 또는 0)까지 `1/fade`씩 선형 이동(첫 상태 닫힘); `mix(loop: np.ndarray | None, mic: np.ndarray | None, frames: int = BLOCK) -> np.ndarray`(None은 0으로, 합산 후 -1~1 clip, float32 (frames,2)); `to_s16le(block) -> bytes`(×32767 반올림, int16 little-endian)

- [ ] **Step 1: 실패 테스트**
```python
def ones(): return np.ones((960, 2), np.float32)
def test_gate_starts_closed(): assert np.all(MicGate().process(ones(), False) == 0)
def test_gate_fades_in_over_20ms():
    out = MicGate().process(ones(), True)
    assert out[0,0] < 0.01 and abs(out[-1,0] - 1.0) < 0.01 and np.all(np.diff(out[:,0]) >= 0)
def test_gate_fully_open_next_block():
    g = MicGate(); g.process(ones(), True); assert np.allclose(g.process(ones(), True), 1.0)
def test_mix_clips(): assert np.max(mix(ones(), ones())) == 1.0
def test_mix_none_is_silence(): assert np.all(mix(None, None) == 0) and mix(None, None).shape == (960, 2)
def test_to_s16le(): assert to_s16le(np.array([[1.0, -1.0]], np.float32)) == b"\xff\x7f\x01\x80"
```
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `feat: 녹화 음성 혼합과 마이크 게이트`

---

### Task 6: 엔진·카메라 파이프라인 연결점

**Files:** Modify `src/knuzoom/engine.py`, `src/knuzoom/video_io.py`; Test `tests/test_engine.py`, `tests/test_video_io.py`

**Interfaces:**
- Produces: `Engine.mic_gate_open() -> bool` — Global Constraints의 게이트 조건. `CameraPipeline.frame_filter: Callable[[np.ndarray], np.ndarray] | None = None` — `_send`에서 크기 맞춤 후, BGR→RGB 변환 전에 적용. 필터 예외는 필터 없이 송출하고 `on_error`로 알림(영상은 끊지 않음).

- [ ] **Step 1: 실패 테스트**
  - `test_gate_closed_while_muted`: 시작 직후 → False
  - `test_gate_open_when_unmuted_and_confirmed`: `zoom_for(e,1.2,0)` 후 True
  - `test_gate_open_in_estimated_mode_when_unmuted`(RF5): `FakeZoom(readable=False)`, `e.tick()`, `zoom_for(e,1.2,0)` → True
  - `test_gate_closed_after_emergency`: 해제 후 `e.emergency_stop()` → False
  - `test_frame_filter_applied_before_send`: 필터가 프레임을 255로 채움 → FakeVCam이 받은 프레임 전부 255
  - `test_frame_filter_error_still_sends`: 필터가 예외 → `vcam.sent == 1`, errors 1건
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현** — FakeVCam이 마지막 프레임을 보관하도록 테스트 쪽 가짜 확장.
- [ ] **Step 4: 통과 확인** — `pytest -q` → PASS
- [ ] **Step 5: 커밋** — `feat: 녹화용 마이크 게이트 상태와 프레임 필터 연결점`

---

### Task 7: FFmpeg 명령과 녹화 관리자(recorder)

**Files:** Create `src/knuzoom/recording/ffmpeg_cmd.py`, `src/knuzoom/recording/recorder.py`; Test `tests/test_rec_ffmpeg.py`, `tests/test_rec_recorder.py`

**Interfaces:**
- Consumes: Task 2~6 전부.
- Produces (`ffmpeg_cmd.py`):
  - `build_command(ffmpeg: str, out: Path, monitor: int, fps: int, source: Literal["screen","test"] = "screen") -> list[str]` — Global Constraints 값 그대로. `test`는 영상 입력을 `testsrc2=size=1280x720:rate={fps}`, 필터를 `format=nv12`로.
  - `find_ffmpeg(app_dir: Path | None = None) -> str | None` — `app_dir/"ffmpeg"/"ffmpeg.exe"` → `shutil.which("ffmpeg")` 순.
- Produces (`recorder.py`):
  - `class AudioSource(Protocol)`: `read(frames: int) -> tuple[np.ndarray | None, np.ndarray | None]`(루프백, 마이크; 각 (frames,2) float32, 장치 없으면 None), `close() -> None`
  - `class Proc(Protocol)`: `stdin`(write/close), `poll() -> int | None`, `wait(timeout: float) -> int`, `kill() -> None`
  - `@dataclass StartResult(ok: bool, message: str, path: Path | None = None)`
  - `class Recorder(s: Settings, *, ffmpeg: str | None, spawn: Callable[[list[str]], Proc], open_audio: Callable[[], AudioSource], gate_open: Callable[[], bool], meeting_active: Callable[[], bool], set_filter: Callable[[Callable | None], None], log: Callable[[str], None], now: Callable[[], datetime] = datetime.now, monotonic: Callable[[], float] = time.monotonic, free_gb: Callable[[Path], float] = storage.free_gb, source: str = "screen", threaded: bool = True)`
    - `start(rec: ConsentRecord) -> StartResult` — 순서: 동의 검증 → FFmpeg 존재 → 디스크(<시작 기준 거부) → 경로 결정·폴더 생성 → 동의 기록 작성 → `spawn` → 음성 열기 → 표시 필터 설정 → 음성 스레드 시작. 이미 녹화 중이면 `StartResult(False, "이미 녹화 중입니다")`.
    - `pump_once() -> None` — 음성 1블록: `read(BLOCK)` → 마이크는 `MicGate.process(mic, gate_open())` → `mix` → `to_s16le` → `stdin.write`. `read` 예외는 무음 블록 + 해당 경고(루프백·마이크 구분이 안 되면 "녹화: 스피커 소리 녹음 실패"), 루프백 None이면 최초 1회 "녹화: 스피커 소리 녹음 실패", 마이크 None이면 최초 1회 "녹화: 마이크 녹음 실패"(녹화는 계속). `threaded=False`면 시험에서 직접 호출.
    - `tick() -> None` — UI 주기 호출: 프로세스 종료 감지("녹화: FFmpeg 오류로 중단"), 회의 창 10초 부재("녹화: Zoom 회의가 끝나 종료"), 디스크 < 종료 기준("녹화: 디스크 공간 부족으로 종료") → `stop(사유)`.
    - `stop(reason: str = "사용자 종료") -> Path | None` — 멱등. 음성 스레드 정지 → stdin 닫기 → `wait(10)`, 시간 초과 시 `kill()` → 필터 해제 → 음성 닫기 → SHA-256 계산 → 동의 기록 다시 쓰기(종료 시각·해시) → 로그 `HH:MM:SS 녹화 종료({reason}) {파일명}`.
    - 속성: `recording: bool`, `elapsed_s: float`, `warning: str | None`, `path: Path | None`

- [ ] **Step 1: 실패 테스트 (`test_rec_ffmpeg.py`)**
  - `test_screen_command`: 결과에 `"ddagrab=output_idx=1:framerate=30:draw_mouse=0"`, `"hwdownload,format=bgra,format=nv12"`, `"h264_mf"`, `"aac"`, `"pipe:0"`, `"-shortest"`, `"+frag_keyframe+empty_moov+default_base_moof"`, 마지막 인자 = 출력 경로
  - `test_test_source_command`: `"testsrc2=size=1280x720:rate=30"` 포함, `ddagrab` 미포함
  - `test_find_ffmpeg_prefers_bundled(tmp_path)`: `tmp_path/"ffmpeg"/"ffmpeg.exe"` 생성 → 그 경로 반환
- [ ] **Step 2: 실패 테스트 (`test_rec_recorder.py`)** — 가짜: `FakeProc`(stdin=BytesIO 유사, `poll` 값 조절), `FakeAudio`(블록 반환·예외 주입), `free_gb` 람다, 시계 가짜, `threaded=False`, `tmp_path`를 `recording_dir`로.
  - `test_start_requires_valid_consent` → ok False, spawn 미호출
  - `test_start_refuses_low_disk`(free 4.9) → `"녹화를 시작할 수 없습니다: 디스크 여유 공간 부족(5GB 미만)"`
  - `test_start_refuses_missing_ffmpeg`(ffmpeg=None) → 해당 문구
  - `test_start_writes_record_and_sets_filter` → txt 존재·"녹화 종료: (녹화 중)", set_filter가 콜러블 받음
  - `test_pump_writes_one_block` → stdin 길이 960*2*2
  - `test_mic_excluded_when_gate_closed` → 루프백 0, 마이크 1, gate False → 쓴 바이트 전부 0
  - `test_audio_read_error_continues_with_silence_and_warns`(RF3) → 예외 주입 후 무음 3840바이트, warning == "녹화: 스피커 소리 녹음 실패"
  - `test_missing_mic_warns_once_and_records_loopback` → 마이크 None, 루프백 0.5 → 쓴 값이 0.5 기준(16384±1), warning == "녹화: 마이크 녹음 실패"
  - `test_auto_stop_when_meeting_gone_10s` → monotonic 0→10.5, meeting False 유지, tick → recording False, warning "녹화: Zoom 회의가 끝나 종료"
  - `test_auto_stop_on_low_disk` → free 1.9 → 종료, 해당 문구
  - `test_ffmpeg_exit_detected` → poll 1 → "녹화: FFmpeg 오류로 중단"
  - `test_stop_is_idempotent_and_finalizes_record`(RF4) → stop 2회, 두 번째 None, txt에 SHA-256 실제 값(출력 파일을 테스트가 미리 만들어 둠), set_filter(None) 호출
  - `test_kill_when_ffmpeg_does_not_exit` → wait가 TimeoutExpired → kill 호출
- [ ] **Step 3: 실패 확인** — `pytest tests/test_rec_ffmpeg.py tests/test_rec_recorder.py -q` → FAIL
- [ ] **Step 4: 구현** — 설계서 5.6의 "표준입력 닫기 + `q`"는 표준입력이 음성 통로라 `q`를 보낼 수 없으므로, `-shortest`로 음성 입력이 끝나면 FFmpeg가 스스로 마무리하게 한다(설계서와 같은 효과). `spawn` 실제 구현(Task 9에서 연결)은 `subprocess.Popen(cmd, stdin=PIPE, stdout=DEVNULL, stderr=로그파일, creationflags=CREATE_NO_WINDOW on Windows)`.
- [ ] **Step 5: 통과 확인** — `pytest -q` → PASS
- [ ] **Step 6: 커밋** — `feat: FFmpeg 녹화 명령과 녹화 관리자`

---

### Task 8: Windows 음성 장치

**Files:** Create `src/knuzoom/recording/devices_windows.py`

**Interfaces:**
- Produces: `class WindowsAudioSource(AudioSource)` — `soundcard`: 루프백 `sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)`, 마이크 `sc.default_microphone()`; 각각 `.recorder(samplerate=48000, channels=2, blocksize=960)`를 열어 둠. 한쪽 열기 실패 시 그쪽은 항상 None. 모노 장치는 2채널로 복제.

- [ ] **Step 1: 구현** (장치 의존 — 단위 시험 없음, Task 10 CI에서 import 확인, 실기는 리허설)
- [ ] **Step 2: 확인** — `python -m py_compile src/knuzoom/recording/devices_windows.py`
- [ ] **Step 3: 커밋** — `feat: Windows 스피커 루프백·마이크 입력`

---

### Task 9: 진행자 화면·조립

**Files:** Modify `src/knuzoom/ui.py`, `src/knuzoom/__main__.py`

**Interfaces:**
- Consumes: `Recorder`, `ConsentRecord`, `METHODS`, `validate`, `notice_text`, `RecordingOverlay`, `expired_recordings`, `delete_recording`, `recording_dir`, `Engine.mic_gate_open`, `CameraPipeline.frame_filter`
- 화면:
  - 버튼 행 추가: [● 녹화] / 녹화 중에는 [■ 녹화 종료]. 상태 줄: `● 녹화 중 {HH:MM:SS}`(빨강), 녹화 경고는 그 아래 별도 줄.
  - 동의 확인 창: 회의명, 기관 체크박스(`consent_parties`), 동의 방법 라디오(METHODS)+기타 입력, 목적(기본 "회의록 작성"), 보관기간(기본 `retention_days`). 매 입력 변경마다 `validate` → 오류 첫 줄 표시, 오류 있으면 [녹화 시작] 비활성.
  - 시작 성공 시 `notice_text`를 클립보드에 복사하고 안내 상자 "안내 문구를 복사했습니다. Zoom 채팅에 붙여넣어 주세요."
  - 시작 시 `expired_recordings` 결과가 있으면 목록 확인 창 → [삭제] 시 `delete_recording`, [나중에] 시 아무것도 안 함.
  - `_poll`에서 `recorder.tick()` 호출(예외는 녹화 경고로만 표시).
- `__main__`: Recorder 생성(`set_filter`는 `lambda f: setattr(pipeline, "frame_filter", f)`, 필터는 시작 시 `RecordingOverlay(s.site_name).apply`), 종료 시 **`recorder.stop("프로그램 종료")`를 `engine.shutdown()`보다 먼저**.

- [ ] **Step 1: 구현**
- [ ] **Step 2: Xvfb 확인(uv 관리 Python 3.11)** — 가짜 Recorder로: 동의 미체크 시 시작 버튼 비활성, 모두 체크 후 시작 → 버튼이 [■ 녹화 종료], 상태 줄 표시, 종료 → 원래대로.
- [ ] **Step 3: 커밋** — `feat: 녹화 버튼·동의 확인 창·보관기간 확인`

---

### Task 10: 배포·CI 녹화 시험·문서

**Files:** Create `scripts/record_smoke.py`; Modify `.github/workflows/build-windows.yml`, `installer/knuzoom.iss`, `knuzoom.spec`, `docs/install.md`, `docs/rehearsal.md`

- [ ] **Step 1: `scripts/record_smoke.py`** — `Recorder(source="test", spawn=Popen 래퍼, open_audio=사인파 440Hz 가짜, gate_open=lambda: True, meeting_active=lambda: True, threaded=True)`로 5초 녹화 후 `stop` → `ffprobe -show_entries format=duration`이 4.0 이상이면 종료 코드 0. 결과 mp4 크기·길이 출력.
- [ ] **Step 2: 워크플로** — PyInstaller 전에 LGPL FFmpeg 내려받기(`https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip`, 실패 시 빌드 실패) → `third_party/ffmpeg/`에 `ffmpeg.exe`, `ffprobe.exe`, `LICENSE.txt` 배치(저장소에는 커밋하지 않음, `.gitignore` 추가). `pytest` 다음에 `python scripts/record_smoke.py third_party/ffmpeg/ffmpeg.exe` 실행. `ddagrab` 3초 시험은 `continue-on-error: true`로 별도 단계(결과만 기록).
- [ ] **Step 3: 설치 파일** — `[Files]`에 `..\third_party\ffmpeg\ffmpeg.exe`, `LICENSE.txt`를 `{app}\ffmpeg\`로. `knuzoom.spec`의 `hiddenimports`에 `soundcard`, Pillow 데이터 확인.
- [ ] **Step 4: 문서** — `docs/install.md`에 "회의 녹화" 절(동의 절차, 전용 모니터 권장, 저장 위치, 보관·삭제, 기관 확인사항 표)과 비상 표에 "녹화 중 KnuZoom이 멈춤 → 작업 관리자 종료, 이미 녹화된 부분은 재생 가능". `docs/rehearsal.md`에 설계서 7.1의 12~17번 항목 추가.
- [ ] **Step 5: 확인** — 브랜치 푸시 → Windows 워크플로 전 단계 성공, 녹화 시험 로그에 길이 ≥ 4초. `ddagrab` 단계 결과 기록.
- [ ] **Step 6: 커밋** — `build: FFmpeg 포함 배포와 Windows 녹화 시험`
