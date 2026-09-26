"""Đọc/ghi bảng `translations`: checkpoint append và trạng thái.

Checkpoint ghi APPEND theo thứ tự, nên `len(segments)` chính là tiến độ. Đó là
lý do không cần bảng `translation_segments` mới (spec §3).

`Translation.status` là cột mà GĐ1a **không ghi và không đọc ở đâu** (mục I3 của
Task 1), nên default `"queued"` của nó chưa từng được ghim đầu-cuối. Các test ở
đây ghim đúng chuỗi đó: `add_translation` ghi nó xuống, `_row_to_translation`/
`get_translation` đọc nó lên, và `set_translation_status` đổi được nó — thiếu
khâu nào thì cột này mãi mãi đọc ra `"queued"`.

Hai điểm KHÁC với bản code trong brief (mục hiệu chỉnh ở đầu brief thắng):
- `add_translation` giữ `target_lang` là tham số BẮT BUỘC (không có default),
  nên mọi lời gọi ở đây truyền `target_lang="vi"` tường minh.
- Hàm thiếu bản dịch ném `NotFound` (kế thừa `LookupError`), KHÔNG phải
  `KeyError` — giống `get_transcript` và các hàm anh em.
"""
import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import NotFound, SqliteRepos
from app.domain.models import Segment


@pytest.fixture
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text)


def _transcript(repos) -> int:
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    return repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo",
                                lang="zh", segments=[seg(1, "a"), seg(2, "b")])


def _translation(repos, tid: int, segments=None) -> int:
    return repos.add_translation(
        transcript_id=tid, transcript_version=1, engine="opus-mt",
        target_lang="vi", segments=segments if segments is not None else [],
        prompt_version="opus-p1")


def test_add_then_get_round_trips_segments(repos):
    tid = _transcript(repos)
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="opus-mt", target_lang="vi",
                                  segments=[seg(1, "vi")],
                                  prompt_version="opus-p1", glossary_version=3)
    got = repos.get_translation(tr_id)
    assert got.id == tr_id and got.engine == "opus-mt"
    assert got.transcript_version == 1 and got.glossary_version == 3
    assert got.target_lang == "vi"
    assert [s.text for s in got.segments] == ["vi"]
    assert got.status == "queued"


def test_add_translation_writes_the_status_it_is_given(repos):
    """`status` là tham số THẬT, không phải hằng số ngầm định trong INSERT.

    Nếu `add_translation` bỏ qua tham số và luôn ghi `'queued'`, bản dịch được
    tạo ở trạng thái khác sẽ đọc ra sai — test này đỏ.
    """
    tid = _transcript(repos)
    tr_id = repos.add_translation(
        transcript_id=tid, transcript_version=1, engine="opus-mt",
        target_lang="vi", segments=[], prompt_version="opus-p1", status="running")
    assert repos.get_translation(tr_id).status == "running"


def test_checkpoint_appends_in_order(repos):
    tid = _transcript(repos)
    tr_id = _translation(repos, tid)
    repos.update_translation_segments(tr_id, [seg(1, "vi1")])
    repos.update_translation_segments(tr_id, [seg(1, "vi1"), seg(2, "vi2")])
    assert [s.i for s in repos.get_translation(tr_id).segments] == [1, 2]


def test_set_status_records_qa_and_tokens(repos):
    tid = _transcript(repos)
    tr_id = _translation(repos, tid)
    repos.set_translation_status(tr_id, "done", qa_issues=["cps:1=30.0"],
                                 tokens_in=10, tokens_out=20, duration_ms=1234)
    got = repos.get_translation(tr_id)
    assert got.status == "done"
    assert got.qa_issues == ["cps:1=30.0"]
    assert (got.tokens_in, got.tokens_out, got.duration_ms) == (10, 20, 1234)


def test_set_status_without_metrics_keeps_the_metrics_already_stored(repos):
    """`None` nghĩa là "không đụng tới cột đó", không phải "ghi NULL".

    Một job hỏng giữa đường đổi trạng thái sang `failed` mà không truyền token
    vẫn phải giữ token đã tiêu của các lô đã xong.
    """
    tid = _transcript(repos)
    tr_id = _translation(repos, tid)
    repos.set_translation_status(tr_id, "running", tokens_in=7, qa_issues=["a"])
    repos.set_translation_status(tr_id, "failed")
    got = repos.get_translation(tr_id)
    assert got.status == "failed"
    assert (got.tokens_in, got.qa_issues) == (7, ["a"])


def test_set_status_to_failed_keeps_segments_already_translated(repos):
    tid = _transcript(repos)
    tr_id = _translation(repos, tid, segments=[seg(1, "vi1")])
    repos.set_translation_status(tr_id, "failed")
    got = repos.get_translation(tr_id)
    assert got.status == "failed" and [s.i for s in got.segments] == [1]


def test_get_translation_missing_raises_not_found(repos):
    """`NotFound` (LookupError) — cùng loại với `get_transcript`, không `KeyError`."""
    with pytest.raises(NotFound):
        repos.get_translation(999)


def test_upsert_term_bumps_glossary_version_once_per_call(repos):
    """Ghim hành vi ĐÃ CÓ: `upsert_term` tự tăng `glossary_version` đúng 1 mỗi lần.

    Không có `bump_glossary_version` riêng (mục hiệu chỉnh #2). Nếu ai đó thêm
    một hàm như thế rồi gọi kèm ở tầng API, version sẽ tăng gấp đôi mỗi lần sửa
    glossary — test này ghim mức tăng thật của adapter.
    """
    first = repos.glossary_version()
    repos.upsert_term(lang="zh", term="剑", translation="kiếm", note=None, approved=True)
    assert repos.glossary_version() == first + 1
    repos.upsert_term(lang="zh", term="剑", translation="gươm", note="sửa", approved=True)
    assert repos.glossary_version() == first + 2
