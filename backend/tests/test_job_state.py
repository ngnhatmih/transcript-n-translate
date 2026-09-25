from __future__ import annotations

import pytest

from app.domain.job_state import (
    CANCELLED, DONE, FAILED, INTERRUPTED, QUEUED, RUNNING,
    InvalidTransition, assert_transition, can_transition, phase_of,
)


def test_phase_includes_engine_not_just_job_type():
    """Đây là điểm dễ sai nhất của cả hàng đợi: gom theo `asr` là VÔ DỤNG
    vì người dùng đổi được model từng job."""
    assert phase_of("asr", "fw-large-v3-turbo") == "asr:fw-large-v3-turbo"
    assert phase_of("asr", "sensevoice-small") == "asr:sensevoice-small"
    assert phase_of("asr", "fw-large-v3-turbo") != phase_of("asr", "sensevoice-small")
    assert phase_of("ingest", None) == "ingest:-"


@pytest.mark.parametrize("src,dst", [
    (QUEUED, RUNNING), (QUEUED, CANCELLED),
    (RUNNING, DONE), (RUNNING, FAILED), (RUNNING, INTERRUPTED), (RUNNING, CANCELLED),
    (FAILED, QUEUED), (INTERRUPTED, QUEUED),
])
def test_allowed_transitions(src, dst):
    assert can_transition(src, dst) is True
    assert_transition(src, dst)


@pytest.mark.parametrize("src,dst", [
    (DONE, RUNNING), (DONE, QUEUED), (CANCELLED, RUNNING),
    (QUEUED, DONE), (QUEUED, FAILED), (RUNNING, QUEUED),
])
def test_forbidden_transitions(src, dst):
    assert can_transition(src, dst) is False
    with pytest.raises(InvalidTransition):
        assert_transition(src, dst)


def test_unknown_state_is_rejected():
    with pytest.raises(InvalidTransition):
        assert_transition("khong_ton_tai", RUNNING)
