from __future__ import annotations

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.worker import PhaseQueueWorker
from tests.fakes import FakeGovernor, RecordingHandler, a_job


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def _worker(repos, *handlers):
    return PhaseQueueWorker(repos, FakeGovernor(), {h.handles(): h for h in handlers})


def test_recover_marks_orphan_running_jobs_as_interrupted(repos):
    """Mô phỏng: worker bị kill giữa lúc đang chạy job. Không có bước này thì
    job treo vĩnh viễn ở `running` và giao diện hiện 'đang chạy' mãi mãi."""
    a = repos.add_job(a_job(None, job_type="asr", engine="e"))
    b = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.set_job_state(a, js.RUNNING)      # worker chết ở đây
    worker = _worker(repos, RecordingHandler(job_type="asr"))

    assert worker.recover() == 1

    assert repos.get_job(a).state == js.INTERRUPTED
    assert repos.get_job(a).finished_at is not None
    assert repos.get_job(b).state == js.QUEUED


def test_recover_is_idempotent(repos):
    a = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.set_job_state(a, js.RUNNING)
    worker = _worker(repos, RecordingHandler(job_type="asr"))
    assert worker.recover() == 1
    assert worker.recover() == 0


def test_retried_job_runs_again_after_recovery(repos):
    a = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.set_job_state(a, js.RUNNING)
    handler = RecordingHandler(job_type="asr")
    worker = _worker(repos, handler)

    worker.recover()
    repos.retry_job(a)
    while worker.tick():
        pass

    assert handler.ran == [a]
    assert repos.get_job(a).state == js.DONE
    assert repos.get_job(a).attempts == 1
