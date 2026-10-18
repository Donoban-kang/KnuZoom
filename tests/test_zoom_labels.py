from knuzoom.zoom_labels import mute_state_from_labels

MUTED = ["Unmute", "음소거 해제"]
UNMUTED = ["Mute", "음소거"]


def test_unmute_label_means_muted():
    assert mute_state_from_labels(["Unmute my audio (Alt+A)"], MUTED, UNMUTED) is True


def test_korean_unmute_label_checked_before_mute_label():
    # "음소거 해제"는 "음소거"를 포함하므로 muted 라벨을 먼저 확인해야 한다.
    assert mute_state_from_labels(["오디오 음소거 해제"], MUTED, UNMUTED) is True


def test_mute_label_means_unmuted():
    assert mute_state_from_labels(["Start Video", "Mute my audio"], MUTED, UNMUTED) is False


def test_no_match_is_none():
    assert mute_state_from_labels(["Participants", "Chat"], MUTED, UNMUTED) is None
