"""녹화 동의 정보: 검증, 동의 기록 문구, 채팅 안내 문구."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

METHODS = ("사전 공문", "회의 시작 시 구두 동의", "기타")
_FMT = "%Y-%m-%d %H:%M:%S"


@dataclass
class ConsentRecord:
    meeting: str
    site_name: str
    required_parties: list[str]
    agreed_parties: list[str]
    method: str
    method_other: str
    purpose: str
    retention_days: int


def validate(rec: ConsentRecord) -> list[str]:
    """녹화를 시작할 수 없는 사유 목록(비어 있으면 시작 가능)."""
    errors = []
    if not rec.meeting.strip():
        errors.append("회의명을 입력해 주세요")
    missing = [p for p in rec.required_parties if p not in rec.agreed_parties]
    if missing:
        errors.append(f"동의하지 않은 기관이 있습니다: {', '.join(missing)}")
    if rec.method not in METHODS:
        errors.append("동의 방법을 선택해 주세요")
    elif rec.method == "기타" and not rec.method_other.strip():
        errors.append("기타 동의 방법을 적어 주세요")
    if not rec.purpose.strip():
        errors.append("녹화 목적을 입력해 주세요")
    if not 1 <= rec.retention_days <= 3650:
        errors.append("보관기간은 1~3650일이어야 합니다")
    return errors


def delete_date(start: datetime, days: int) -> date:
    return (start + timedelta(days=days)).date()


def _method_text(rec: ConsentRecord) -> str:
    return f"기타({rec.method_other.strip()})" if rec.method == "기타" else rec.method


def render_text(rec: ConsentRecord, start: datetime, file_name: str,
                end: datetime | None = None, sha256: str | None = None) -> str:
    lines = [
        "KnuZoom 녹화 동의 기록",
        f"회의명: {rec.meeting.strip()}",
        f"녹화 기관: {rec.site_name}",
        f"동의 기관: {', '.join(rec.agreed_parties)}",
        f"동의 방법: {_method_text(rec)}",
        f"녹화 목적: {rec.purpose.strip()}",
        f"보관기간: {rec.retention_days}일 (삭제 예정일: {delete_date(start, rec.retention_days):%Y-%m-%d})",
        f"녹화 시작: {start:{_FMT}}",
        f"녹화 종료: {end:{_FMT}}" if end else "녹화 종료: (녹화 중)",
        f"파일: {file_name}",
        f"SHA-256: {sha256}" if sha256 else "SHA-256: (종료 시 계산)",
    ]
    return "\n".join(lines) + "\n"


def notice_text(rec: ConsentRecord) -> str:
    return (f"[안내] {rec.site_name}에서 이 회의를 녹화하고 있습니다. "
            f"(목적: {rec.purpose.strip()}, 보관: {rec.retention_days}일)")
