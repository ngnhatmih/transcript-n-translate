from __future__ import annotations

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.worker import JobCancelled, PhaseQueueWorker
from tests.fakes import FakeGovernor, RecordingHandler, a_job


class CheckpointingHandler:
    """Handler gọi checkpoint giữa các bước, giống handler thật sẽ làm."""

    def __init__(self, worker_ref: list) -> None:
        self._worker_ref = worker_ref
        self.steps_done = 0

    def handles(self) -> str:
        return "asr"

    def run(self, job, report) -> None:
        worker = self._worker_ref[0]
        for step in range(5):
            worker.checkpoint(job.id)
            self.steps_done += 1
            report(step / 5, f"bước {step}")


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def test_cancel_between_steps_stops_early_and_marks_cancelled(repos):
    ref: list = []
    handler = CheckpointingHandler(ref)
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": handler})
    ref.append(worker)

    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.request_cancel(jid)          # huỷ TRƯỚC khi chạy

    while worker.tick():
        pass

    assert handler.steps_done == 0, "checkpoint đầu tiên phải chặn ngay, không chạy bước nào"
    assert repos.get_job(jid).state == js.CANCELLED


def test_cancel_midway_only_runs_started_steps(repos):
    ref: list = []
    handler = CheckpointingHandler(ref)
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": handler})
    ref.append(worker)

    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    # huỷ sau bước đầu: dùng clock? đơn giản hơn — huỷ ngay sau checkpoint 1
    original_checkpoint = worker.checkpoint
    calls = {"n": 0}

    def counting_checkpoint(job_id: int) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            repos.request_cancel(job_id)
        original_checkpoint(job_id)

    worker.checkpoint = counting_checkpoint  # type: ignore[assignment]

    while worker.tick():
        pass

    assert handler.steps_done == 1
    assert repos.get_job(jid).state == js.CANCELLED


def test_cancelled_job_does_not_run_again(repos):
    ref: list = []
    handler = CheckpointingHandler(ref)
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": handler})
    ref.append(worker)

    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.request_cancel(jid)
    while worker.tick():
        pass

    assert worker.tick() is False
    assert repos.get_job(jid).state == js.CANCELLED


def test_cancel_requested_flag_stays_but_state_is_terminal(repos):
    ref: list = []
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": CheckpointingHandler(ref)})
    ref.append(worker)
    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.request_cancel(jid)
    while worker.tick():
        pass
    job = repos.get_job(jid)
    assert job.state == js.CANCELLED
    assert job.cancel_requested is True
    assert job.finished_at is not None


def test_cancel_requested_during_run_is_honoured_at_job_boundary(repos):
    """Huỷ giữa lúc handler đang chạy, ở handler KHÔNG gọi checkpoint.

    Đây là điểm khác biệt cốt lõi giữa hai đường huỷ: ``RecordingHandler``
    không bao giờ gọi ``checkpoint()`` nên nó không ném ``JobCancelled``; yêu
    cầu huỷ chỉ được nhận ra ở ranh giới job trong ``_run_one``. Nếu khối kiểm
    tra sau khi chạy xong bị xoá, test này đỏ vì job rơi vào ``DONE``.
    """
    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    handler = RecordingHandler(
        job_type="asr", cancel_after=1, _repos=repos, _job_id_to_cancel=jid
    )
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": handler})
    while worker.tick():
        pass
    job = repos.get_job(jid)
    assert handler.ran == [jid]
    assert job.cancel_requested is True
    assert job.state == js.CANCELLED
