from knuzoom.zoom_labels import mute_state_from_labels

MUTED = ["Unmute my audio", "오디오 음소거 해제"]
UNMUTED = ["Mute my audio", "오디오 음소거"]


def test_unmute_label_means_muted():
    assert mute_state_from_labels(["Unmute my audio (Alt+A)"], MUTED, UNMUTED) is True


def test_korean_unmute_label_checked_before_mute_label():
    # "음소거 해제"는 "음소거"를 포함하므로 muted 라벨을 먼저 확인해야 한다.
    assert mute_state_from_labels(["오디오 음소거 해제"], MUTED, UNMUTED) is True


def test_mute_label_means_unmuted():
    assert mute_state_from_labels(["Start Video", "Mute my audio"], MUTED, UNMUTED) is False


def test_no_match_is_none():
    assert mute_state_from_labels(["Participants", "Chat"], MUTED, UNMUTED) is None


def test_default_labels_ignore_ask_to_unmute_button():  # Final I3
    from knuzoom.config import Settings
    s = Settings()
    names = ["Ask to Unmute", "Mute my audio (Alt+A)"]
    assert mute_state_from_labels(names, s.zoom_label_when_muted, s.zoom_label_when_unmuted) is False
