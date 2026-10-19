"""Zoom 회의 창과 버튼 이름을 출력하는 진단 스크립트(Windows, Zoom 회의 참가 중 실행).

음소거 상태와 해제 상태에서 각각 실행해, 마이크 버튼 이름을 settings.json의
zoom_label_when_muted / zoom_label_when_unmuted 에 반영한다.
"""
from pywinauto import Desktop


def main() -> None:
    for w in Desktop(backend="uia").windows():
        title = w.window_text()
        if "Zoom" not in title and "줌" not in title:
            continue
        print(f"[창] {title!r}")
        for b in w.descendants(control_type="Button"):
            name = b.window_text()
            if name:
                print(f"    버튼: {name!r}")


if __name__ == "__main__":
    main()
    input("\n엔터 키를 누르면 창이 닫힙니다...")  # 설치판에서 더블클릭으로 실행할 때 결과를 볼 수 있게
