from __future__ import annotations

import json
import sqlite3

import pytest

from app.adapters.clock_system import FrozenClock, SystemClock
from app.adapters.persist import sqlite_repos as sqlite_repos_mod
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.domain.models import Job, Segment, segments_to_json


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


class InjectedFailure(RuntimeError):
    """Lỗi do test cố tình tiêm vào giữa hai câu lệnh."""


def repos_that_fails_on(tmp_path, monkeypatch, predicate):
    """Repos mà `execute` ném lỗi khi `predicate(sql)` đúng.

    `SqliteRepos._connect` tự gọi `sqlite3.connect` nên không có khe nào để
    truyền `factory=` từ ngoài; cách duy nhất là chặn `sqlite3.connect` trong
    lúc test chạy (monkeypatch tự khôi phục sau test). Dùng `factory=` với lớp
    con của `sqlite3.Connection` để câu lệnh chỉ nổ ở đúng chỗ đã chọn.
    """
    class FailingConn(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if predicate(sql):
                raise InjectedFailure(f"nổ có chủ đích: {sql.strip()[:48]}")
            return super().execute(sql, *args, **kwargs)

    real_connect = sqlite3.connect

    def connect(path, **kwargs):
        kwargs["factory"] = FailingConn
        return real_connect(path, **kwargs)

    monkeypatch.setattr(sqlite_repos_mod.sqlite3, "connect", connect)
    r = SqliteRepos(tmp_path / "boom.db", clock=SystemClock())
    r.init_schema()
    return r


def test_repos_port_declares_sources_and_translations_listing():
    """I2: cổng `Repos` phải đối xứng — `list_transcripts` đã có sẵn từ trước.

    Thiếu hai phương thức này chính là lý do `routes_sources.py` từng phải mở
    thẳng tệp SQLite (R74).
    """
    from app.ports.repos import Repos

    assert "list_sources" in dir(Repos)
    assert "list_translations" in dir(Repos)


def test_list_sources_is_newest_first(repos):
    first = repos.add_source(kind="file", origin="a.mp4", media_path="m/a.mp4",
                             lang="zh", audio_path="m/a.wav", duration=12.5)
    second = repos.add_source(kind="url", origin="https://x/v", media_path="m/b.mp4",
                              lang="en")

    got = repos.list_sources()
    assert [s.id for s in got] == [second, first]
    assert got[0].kind == "url" and got[0].lang == "en"
    assert got[0].media_path == "m/b.mp4"
    # Cùng phép ánh xạ hàng -> `Source` như `get_source`, không phải bản sao thứ hai.
    assert got[1] == repos.get_source(first)


def test_list_translations_is_empty_before_any_translation(repos):
    assert repos.list_translations() == []


def test_list_translations_maps_stored_rows(repos):
    """Task 18 chưa có `add_translation`; hàng được ghi thẳng để khoá phần ĐỌC.

    Cột `segments`/`qa_issues` là JSON trong schema nên phép ánh xạ hàng ->
    `Translation` phải giải mã, không trả chuỗi thô.
    """
    sid = repos.add_source(kind="file", origin="a", media_path="m", lang="zh")
    tid = repos.add_transcript(source_id=sid, engine="e", lang="zh",
                               segments=[Segment(i=0, start=0.0, end=1.0, text="你好")])
    with sqlite3.connect(repos.db_path) as conn:
        conn.execute(
            "INSERT INTO translations(transcript_id, transcript_version, engine,"
            " target_lang, segments, prompt_version, glossary_version, qa_issues,"
            " tokens_in, tokens_out, duration_ms, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, 1, "qwen2.5-7b", "vi",
             segments_to_json([Segment(i=0, start=0.0, end=1.0, text="Xin chào")]),
             "v1", 3, json.dumps(["lệch thuật ngữ"], ensure_ascii=False),
             10, 20, 30, "2026-01-01T00:00:00Z"),
        )

    got = repos.list_translations()
    assert len(got) == 1
    tr = got[0]
    assert tr.transcript_id == tid and tr.transcript_version == 1
    assert tr.engine == "qwen2.5-7b" and tr.target_lang == "vi"
    assert tr.segments[0].text == "Xin chào"
    assert tr.prompt_version == "v1" and tr.glossary_version == 3
    assert tr.qa_issues == ["lệch thuật ngữ"]
    assert (tr.tokens_in, tr.tokens_out, tr.duration_ms) == (10, 20, 30)
    assert tr.created_at == "2026-01-01T00:00:00Z"


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
    # Job cũ NHẤT phải thuộc phase KHÁC. Nếu hiện thực bỏ mệnh đề `phase` khỏi
    # SQL thì `next_queued_for_phase` sẽ trả về job này (engine sensevoice-small)
    # và test đỏ — trước đây job cũ nhất tình cờ cũng đúng phase cần tìm nên một
    # hiện thực hỏng vẫn qua.
    repos.add_job(Job(id=None, workspace=1, type="asr", engine="sensevoice-small",
                      phase=js.phase_of("asr", "sensevoice-small"), payload={"source_id": 0}))
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
    # Gọi lần hai phải là no-op: không còn job `running` nào để quét. Task 9 gọi
    # hàm này lúc khởi động và báo cáo số hàng đã đổi, nên `rowcount` phải đúng.
    assert repos.mark_running_as_interrupted() == 0


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


def test_job_log_file_gets_the_whole_log_while_log_tail_keeps_the_tail(tmp_path):
    """DC-03 · spec §5.5: log ĐẦY ĐỦ nằm ở tệp `job-<id>.log`, DB giữ 100 dòng cuối.

    Trước bản vá, `log_path` là trường chết: cột `jobs.log_path` không bao giờ
    được gán và `data/logs/job-<id>.log` không bao giờ tồn tại.
    """
    import pathlib

    log_dir = tmp_path / "logs"
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock(), log_dir=log_dir)
    r.init_schema()
    jid = r.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    for n in range(150):
        r.append_job_log(jid, f"line {n}")

    job = r.get_job(jid)
    assert job.log_path is not None, "ghi log ra tệp thì `log_path` phải được gán"
    path = pathlib.Path(job.log_path)
    assert path == log_dir / f"job-{jid}.log", (
        f"`log_path` phải trỏ đúng tệp theo spec §5.5, thấy {path}"
    )
    assert path.read_text(encoding="utf-8").splitlines() == [
        f"line {n}" for n in range(150)
    ], "tệp log phải giữ TOÀN BỘ dòng, không bị cắt ở 100"
    tail = job.log_tail.splitlines()
    assert len(tail) == 100, "DB chỉ giữ 100 dòng cuối cho UI"
    assert tail[-1] == "line 149"


def test_job_log_file_is_absent_when_the_adapter_has_no_log_dir(repos):
    """Chống hồi quy: repos không có `log_dir` (test dựng trần) giữ nguyên hành vi cũ."""
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.append_job_log(jid, "một dòng")
    assert repos.get_job(jid).log_path is None
    assert repos.get_job(jid).log_tail.splitlines()[-1] == "một dòng"


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


def test_upsert_term_returns_real_id_on_both_paths(repos):
    # Nhánh INSERT rồi nhánh ON CONFLICT ... DO UPDATE. Trước đây nhánh update trả
    # `lastrowid` = 0 dù hàng có id thật, nên API glossary trả về id 0.
    first = repos.upsert_term(lang="zh", term="大模型", translation="a",
                              note=None, approved=False)
    second = repos.upsert_term(lang="zh", term="大模型", translation="b",
                               note=None, approved=True)
    assert first == 1
    assert second == 1, "nhánh update phải trả id thật của hàng, không phải 0"
    assert len(repos.list_terms(lang="zh")) == 1
    assert repos.glossary_version() == 2


def test_list_jobs_with_empty_states_returns_nothing(repos):
    for _ in range(3):
        repos.add_job(Job(id=None, workspace=1, type="asr", engine="e",
                          phase="asr:e", payload={}))
    assert len(repos.list_jobs()) == 3
    assert repos.list_jobs(states=()) == [], (
        "tập trạng thái rỗng nghĩa là 'không khớp gì', không phải 'tất cả'"
    )
    assert len(repos.list_jobs(states=(js.QUEUED,))) == 3


def test_list_terms_with_empty_lang_filters_instead_of_returning_all(repos):
    repos.upsert_term(lang="zh", term="t1", translation="a", note=None, approved=False)
    repos.upsert_term(lang="en", term="t2", translation="b", note=None, approved=False)
    assert len(repos.list_terms()) == 2
    assert repos.list_terms(lang="") == [], "chuỗi rỗng là bộ lọc thật, không phải 'bỏ lọc'"
    assert len(repos.list_terms(lang="zh")) == 1


def test_timestamps_come_from_the_injected_clock(tmp_path):
    """Đồng hồ phải được TIÊM vào, không gọi `datetime.now()` trực tiếp.

    Nếu adapter tự lấy giờ hệ thống thì mốc lưu xuống sẽ không khớp đồng hồ đóng
    băng và test này đỏ.
    """
    clock = FrozenClock("2026-09-25T00:00:00Z")
    r = SqliteRepos(tmp_path / "c.db", clock=clock)
    r.init_schema()
    jid = r.add_job(Job(id=None, workspace=1, type="asr", engine="e",
                        phase="asr:e", payload={}))
    assert r.get_job(jid).created_at == "2026-09-25T00:00:00Z"
    r.set_job_state(jid, js.RUNNING)
    assert r.get_job(jid).started_at == "2026-09-25T00:00:00Z"
    clock.advance(90)
    r.set_job_state(jid, js.DONE)
    assert r.get_job(jid).finished_at == "2026-09-25T00:01:30Z"
    sid = r.add_source(kind="file", origin="a", media_path="m", lang="zh")
    assert r.get_source(sid).created_at == "2026-09-25T00:01:30Z"


def test_upsert_term_is_atomic(tmp_path, monkeypatch):
    """Tiêm lỗi vào câu lệnh THỨ HAI; câu thứ nhất đã chạy thật nên phải bị cuốn theo.

    Không có giao dịch tường minh thì hàng glossary đã autocommit và ở lại, còn
    `glossary_version` không tăng — đúng cái lệch khiến bản dịch không bị coi là
    lỗi thời.
    """
    r = repos_that_fails_on(
        tmp_path, monkeypatch,
        lambda sql: sql.lstrip().upper().startswith("INSERT INTO SETTINGS"),
    )
    with pytest.raises(InjectedFailure):
        r.upsert_term(lang="zh", term="大模型", translation="mô hình lớn",
                      note=None, approved=True)
    assert r.list_terms(lang="zh") == [], "hàng glossary đã landed phải bị rollback"
    assert r.glossary_version() == 0, "version không được tăng khi hàng không landed"


def test_update_transcript_segments_is_atomic(tmp_path, monkeypatch):
    """Nổ ở COMMIT; cả lần đọc version lẫn lần ghi version+1 phải bị cuốn theo.

    Không có giao dịch tường minh thì UPDATE đã autocommit trước khi COMMIT chạy,
    nên version tăng dù lần ghi đó thất bại.
    """
    r = repos_that_fails_on(
        tmp_path, monkeypatch,
        lambda sql: sql.strip().upper().startswith("COMMIT"),
    )
    sid = r.add_source(kind="file", origin="a", media_path="m", lang="zh")
    tid = r.add_transcript(source_id=sid, engine="e", lang="zh",
                           segments=[Segment(i=0, start=0.0, end=1.0, text="a")])
    with pytest.raises(InjectedFailure):
        r.update_transcript_segments(tid, [Segment(i=0, start=0.0, end=1.0, text="b")])
    t = r.get_transcript(tid)
    assert t.version == 1, "version không được tăng khi COMMIT nổ"
    assert t.segments[0].text == "a", "segments không được đổi khi COMMIT nổ"
