from pathlib import Path

from knuzoom.recording.ffmpeg_cmd import build_command, find_ffmpeg


def test_screen_command():
    cmd = build_command("ffmpeg", Path("out.mp4"), monitor=1, fps=30)
    assert "ddagrab=output_idx=1:framerate=30:draw_mouse=0" in cmd
    assert "hwdownload,format=bgra,format=nv12" in cmd
    for arg in ("h264_mf", "aac", "pipe:0", "-shortest", "+frag_keyframe+empty_moov+default_base_moof",
                "aresample=async=1"):
        assert arg in cmd
    assert cmd[0] == "ffmpeg" and cmd[-1] == "out.mp4"


def test_test_source_command():
    cmd = build_command("ffmpeg", Path("o.mp4"), monitor=0, fps=30, source="test")
    assert "testsrc2=size=1280x720:rate=30" in cmd
    assert not any("ddagrab" in a for a in cmd)


def test_find_ffmpeg_prefers_bundled(tmp_path):
    exe = tmp_path / "ffmpeg" / "ffmpeg.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    assert find_ffmpeg(tmp_path) == str(exe)


def test_screen_audio_uses_wallclock_timestamps():  # 경미 4
    cmd = build_command("ffmpeg", Path("o.mp4"), monitor=0, fps=30)
    i = cmd.index("pipe:0")
    assert "-use_wallclock_as_timestamps" in cmd[:i] and cmd.index("-use_wallclock_as_timestamps") > cmd.index("ddagrab=output_idx=0:framerate=30:draw_mouse=0")


def test_test_source_does_not_use_wallclock():
    assert "-use_wallclock_as_timestamps" not in build_command("ffmpeg", Path("o.mp4"), 0, 30, source="test")


def test_spawn_writes_stderr_to_log_and_closes_handle(tmp_path):  # 경미 1
    import sys
    from knuzoom.recording.ffmpeg_cmd import make_spawn
    spawn = make_spawn(tmp_path / "logs")
    proc = spawn([sys.executable, "-c", "import sys; sys.stdin.read(); sys.stderr.write('warn')"])
    proc.stdin.close()
    proc.wait(10)
    assert (tmp_path / "logs" / "ffmpeg.log").read_text() == "warn"
    assert spawn.open_handles() == 0
