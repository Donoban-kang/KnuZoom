from knuzoom.camera_select import camera_choices, resolve_camera_index
from knuzoom.config import Settings

NAMES = ["Integrated Webcam", "OBS Virtual Camera", "AVer CAM520 Pro"]


def test_virtual_camera_excluded_from_choices():
    assert camera_choices(NAMES) == [(0, "Integrated Webcam"), (2, "AVer CAM520 Pro")]


def test_resolve_by_saved_name_even_if_index_moved():
    s = Settings(camera_name="AVer CAM520 Pro", camera_index=0)
    assert resolve_camera_index(s, NAMES) == 2


def test_resolve_falls_back_to_index_when_name_missing():
    s = Settings(camera_name="없는 카메라", camera_index=0)
    assert resolve_camera_index(s, NAMES) == 0


def test_resolve_never_picks_virtual_camera():
    s = Settings(camera_name="", camera_index=1)       # 1번이 가상 카메라
    assert resolve_camera_index(s, NAMES) == 0         # 가상이 아닌 첫 카메라


def test_resolve_without_names_uses_index():
    assert resolve_camera_index(Settings(camera_index=3), []) == 3


def test_camera_control_choose_saves_reopens_and_notifies(tmp_path):
    from knuzoom.camera_select import CameraControl
    from knuzoom.config import load_settings
    calls = []
    s = Settings()
    ctl = CameraControl(s, tmp_path / "s.json", reopen=lambda: calls.append("reopen"),
                        camera_changed=lambda: calls.append("changed"), list_names=lambda: NAMES)
    ctl.choose(2)
    assert (s.camera_index, s.camera_name) == (2, "AVer CAM520 Pro")
    assert load_settings(tmp_path / "s.json").camera_name == "AVer CAM520 Pro"
    assert calls == ["reopen", "changed"]
    assert ctl.label() == "AVer CAM520 Pro"


def test_camera_control_refuses_virtual_camera(tmp_path):
    from knuzoom.camera_select import CameraControl
    s = Settings()
    ctl = CameraControl(s, tmp_path / "s.json", reopen=lambda: None, camera_changed=lambda: None,
                        list_names=lambda: NAMES)
    assert ctl.choose(1) is False and s.camera_index == 0
