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


# ---------------------------------------------------------------------------
# recover() phải đối chiếu CẢ bảng `translations`, không chỉ `jobs` (I-3)
# ---------------------------------------------------------------------------

def _translate_job(repos, translation_id: int) -> int:
    """Một job `translate` THẬT, mang ĐÚNG khoá payload mà handler đọc.

    Dùng `Job` của domain chứ không tự bịa dict: dấu nối duy nhất giữa job và
    hàng dịch là `payload["translation_id"]` (`domain.models.translation_id_of`),
    và một fixture dựng payload sai khoá sẽ khiến bài này xanh vì lý do sai.
    """
    from app.domain.models import Job

    job = Job(id=None, workspace=2, type="translate", engine="fake-mt",
              phase=js.phase_of("translate", "fake-mt"),
              payload={"translation_id": translation_id, "transcript_id": 1,
                       "engine_id": "fake-mt", "source_lang": "zh",
                       "target_lang": "vi"})
    return repos.add_job(job)


def _running_translation(repos, *, status="running") -> int:
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = repos.add_transcript(source_id=sid, engine="fw", lang="zh", segments=[])
    return repos.add_translation(transcript_id=tid, transcript_version=1,
                                 engine="fake-mt", target_lang="vi", segments=[],
                                 prompt_version="p1", status=status)


def test_recover_settles_a_translation_whose_job_was_interrupted(repos):
    """Worker chết giữa lúc dịch: hàng `translations` không được ở `running` mãi.

    `mark_running_as_interrupted` chỉ sửa bảng `jobs`. Hàng dịch đã được handler
    ghi `running` (I-3a) nên không có bước đối chiếu này thì nó đứng nguyên ở
    `running` VĨNH VIỄN — `GET /api/translations` hiện một bản dịch "đang chạy"
    mà không còn tiến trình nào chạy nó.
    """
    tr_id = _running_translation(repos)
    job_id = _translate_job(repos, tr_id)
    repos.set_job_state(job_id, js.RUNNING)         # worker chết ở đây

    worker = _worker(repos, RecordingHandler(job_type="asr"))

    assert worker.recover() == 1, "vẫn phải trả SỐ JOB đã đổi trạng thái"
    assert repos.get_job(job_id).state == js.INTERRUPTED
    assert repos.get_translation(tr_id).status == "failed", (
        "job bị ngắt ⇒ bản dịch không hoàn chỉnh; `running` mãi mãi là trạng thái treo"
    )


def test_recover_does_not_touch_a_queued_translation_of_an_untouched_job(repos):
    """Vế đối chứng: job còn `queued` thì hàng dịch của nó cũng phải còn nguyên.

    Phép đối chiếu phải bám vào SỐ PHẬN của job, không phải vào "mọi hàng dịch
    đang dở": một lần `recover()` không được giết những bản dịch còn nằm trong
    hàng đợi chờ chạy.
    """
    tr_id = _running_translation(repos, status="queued")
    job_id = _translate_job(repos, tr_id)           # vẫn `queued`

    worker = _worker(repos, RecordingHandler(job_type="asr"))

    assert worker.recover() == 0, "không có job `running` nào để ngắt"
    assert repos.get_translation(tr_id).status == "queued"
    assert repos.get_job(job_id).state == js.QUEUED


def test_recover_never_overwrites_a_finished_translation(repos):
    """Một hàng đã `done` là kết quả của một lần chạy THẬT: đừng xoá nó.

    `set_translations_status` chỉ được chạm `queued`/`running`
    (`UNSETTLED_TRANSLATION_STATUSES`), và bài này ghim bất biến đó qua đường
    `recover()` thật: một hàng `done` sót lại bên cạnh một job `running` (kịch bản
    không bình thường, nhưng đúng loại dữ liệu mà một lần quét muộn gặp phải)
    phải sống sót.
    """
    tr_id = _running_translation(repos, status="done")
    job_id = _translate_job(repos, tr_id)
    repos.set_job_state(job_id, js.RUNNING)

    worker = _worker(repos, RecordingHandler(job_type="asr"))
    worker.recover()

    assert repos.get_job(job_id).state == js.INTERRUPTED
    assert repos.get_translation(tr_id).status == "done"
