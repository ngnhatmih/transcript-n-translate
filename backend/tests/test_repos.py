from __future__ import annotations

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.domain.models import Job, Segment


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def test_source_and_transcript_roundtrip(repos):
    sid = repos.add_source(kind="file", origin="a.mp4", media_path="m/a.mp4",
                           lang="zh", audio_path="m/a.wav", duration=12.5)
    segs = [Segment(i=0, start=0.0, end=2.0, text="你好")]
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang="zh", segments=segs)

    t = repos.get_transcript(tid)
    assert t.version == 1 and t.status == "draft"
    assert t.segments[0].text == "你好"
    assert repos.get_source(sid).duration == 12.5


def test_update_segments_bumps_version(repos):
    sid = repos.add_source(kind="file", origin="a", media_path="m", lang="zh")
    tid = repos.add_transcript(source_id=sid, engine="e", lang="zh",
                               segments=[Segment(i=0, start=0.0, end=1.0, text="a")])
    assert repos.update_transcript_segments(tid, [Segment(i=0, start=0.0, end=1.0, text="b")]) == 2
    assert repos.update_transcript_segments(tid, [Segment(i=0, start=0.0, end=1.0, text="c")]) == 3
    assert repos.get_transcript(tid).version == 3


def test_queue_picks_oldest_of_a_given_phase(repos):
    for engine in ("fw-large-v3-turbo", "sensevoice-small", "fw-large-v3-turbo"):
        repos.add_job(Job(id=None, workspace=1, type="asr", engine=engine,
                          phase=js.phase_of("asr", engine), payload={"source_id": 1}))
    first = repos.next_queued_for_phase("asr:fw-large-v3-turbo")
    assert first.engine == "fw-large-v3-turbo"
    oldest = repos.oldest_queued()
    assert oldest.id == 1, "job cũ nhất phải là cái đầu tiên được thêm"


def test_queue_ignores_cancelled_and_done(repos):
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e",
                            phase="asr:e", payload={}))
    repos.set_job_state(jid, js.RUNNING)
    repos.set_job_state(jid, js.DONE)
    assert repos.oldest_queued() is None
    assert repos.next_queued_for_phase("asr:e") is None


def test_mark_running_as_interrupted_at_startup(repos):
    a = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    b = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.set_job_state(a, js.RUNNING)
    repos.set_job_state(b, js.QUEUED)
    assert repos.mark_running_as_interrupted() == 1
    assert repos.get_job(a).state == js.INTERRUPTED
    assert repos.get_job(b).state == js.QUEUED
    assert repos.get_job(a).finished_at is not None


def test_illegal_transition_raises(repos):
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.set_job_state(jid, js.RUNNING)
    repos.set_job_state(jid, js.DONE)
    with pytest.raises(js.InvalidTransition):
        repos.set_job_state(jid, js.RUNNING)


def test_cancel_request_and_progress_and_log_tail(repos):
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.request_cancel(jid)
    assert repos.get_job(jid).cancel_requested is True
    repos.set_job_progress(jid, 0.42)
    assert repos.get_job(jid).progress == pytest.approx(0.42)
    for n in range(150):
        repos.append_job_log(jid, f"line {n}")
    tail = repos.get_job(jid).log_tail.splitlines()
    assert len(tail) == 100, "log_tail phải giữ đúng 100 dòng cuối"
    assert tail[-1] == "line 149"


def test_retry_after_failure_resets_to_queued_and_bumps_attempts(repos):
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.set_job_state(jid, js.RUNNING)
    repos.set_job_state(jid, js.FAILED, error="boom")
    repos.retry_job(jid)
    j = repos.get_job(jid)
    assert j.state == js.QUEUED and j.attempts == 1 and j.error is None


def test_llm_calls_are_recorded(repos):
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.add_llm_call(job_id=jid, engine="e", model_ref="m", prompt_version=None,
                       tokens_in=None, tokens_out=None, duration_ms=123, ok=True, error=None)
    rows = repos.list_llm_calls(jid)
    assert len(rows) == 1 and rows[0]["duration_ms"] == 123


def test_glossary_upsert_and_list(repos):
    repos.upsert_term(lang="zh", term="大模型", translation="mô hình lớn", note=None, approved=False)
    repos.upsert_term(lang="zh", term="大模型", translation="mô hình lớn", note="sửa", approved=True)
    terms = repos.list_terms(lang="zh")
    assert len(terms) == 1
    assert terms[0].approved is True
    assert repos.glossary_version() == 2, "mỗi lần ghi glossary phải tăng version"


def test_settings_roundtrip(repos):
    assert repos.get_setting("auto_forward", default="1") == "1"
    repos.set_setting("auto_forward", "0")
    assert repos.get_setting("auto_forward") == "0"
