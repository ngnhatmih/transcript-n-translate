"""State machine của job. Thuần, không phụ thuộc gì.

Vì sao cần: nếu không định nghĩa transition hợp lệ thì `done -> running` sẽ
xảy ra trong thực tế (double-click, SSE gửi lại) và bảng jobs sẽ mâu thuẫn.
"""
from __future__ import annotations

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
INTERRUPTED = "interrupted"
CANCELLED = "cancelled"

ALL_STATES = frozenset({QUEUED, RUNNING, DONE, FAILED, INTERRUPTED, CANCELLED})
TERMINAL_STATES = frozenset({DONE, CANCELLED})
RETRYABLE_STATES = frozenset({FAILED, INTERRUPTED})

_TRANSITIONS: dict[str, frozenset[str]] = {
    QUEUED: frozenset({RUNNING, CANCELLED}),
    RUNNING: frozenset({DONE, FAILED, INTERRUPTED, CANCELLED}),
    FAILED: frozenset({QUEUED}),
    INTERRUPTED: frozenset({QUEUED}),
    DONE: frozenset(),
    CANCELLED: frozenset(),
}


class InvalidTransition(ValueError):
    pass


def can_transition(src: str, dst: str) -> bool:
    if src not in ALL_STATES or dst not in ALL_STATES:
        return False
    return dst in _TRANSITIONS[src]


def assert_transition(src: str, dst: str) -> None:
    if src not in ALL_STATES:
        raise InvalidTransition(f"trạng thái nguồn không tồn tại: {src!r}")
    if dst not in ALL_STATES:
        raise InvalidTransition(f"trạng thái đích không tồn tại: {dst!r}")
    if not can_transition(src, dst):
        raise InvalidTransition(f"không được chuyển {src!r} -> {dst!r}")


def phase_of(job_type: str, engine: str | None) -> str:
    """Khoá giai đoạn = CẶP (loại job, engine).

    Đây là quyết định trung tâm của hàng đợi. Gom theo `asr`/`mt` là vô dụng
    vì người dùng đổi được model cho từng job: file A dùng turbo, file B dùng
    SenseVoice thì vẫn phải nạp/đổ model như thường.
    """
    return f"{job_type}:{engine if engine else '-'}"
