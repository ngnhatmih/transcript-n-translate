"""Đọc/ghi bảng `translations`: checkpoint (ghi đè) và trạng thái.

Checkpoint GHI ĐÈ `segments` bằng ĐÚNG danh sách được đưa vào — adapter KHÔNG
append (review Task 6, I-2: "append là việc của người gọi"). Người gọi tự cộng
dồn (`done + new`) rồi truyền cả danh sách, nhờ vậy `len(segments)` mới là tiến
độ và không cần bảng `translation_segments` mới (spec §3). Hệ quả phải biết và
đã được ghim: một danh sách NGẮN HƠN sẽ xoá việc đã ghi trước đó
(`test_checkpoint_replaces_with_a_shorter_list`).

`Translation.status` là cột mà GĐ1a **không ghi và không đọc ở đâu** (mục I3 của
Task 1), nên default `"queued"` của nó chưa từng được ghim đầu-cuối. Các test ở
đây ghim đúng chuỗi đó: `add_translation` ghi nó xuống, `_row_to_translation`/
`get_translation` đọc nó lên, và `set_translation_status` đổi được nó — thiếu
khâu nào thì cột này mãi mãi đọc ra `"queued"`. Vì `Translation.status` CŨNG có
default `"queued"`, một khẳng định qua dataclass KHÔNG phân biệt được "cột chưa
từng được ghi" với "đã ghi rồi" (review I-3): các test dưới đây còn đọc thẳng cột
bằng SQL (`_raw_status`) để nhìn xuyên qua default đó.

Ba điểm KHÁC với bản code trong brief (mục hiệu chỉnh ở đầu brief thắng):
- `add_translation` giữ `target_lang` là tham số BẮT BUỘC (không có default),
  nên mọi lời gọi ở đây truyền `target_lang="vi"` tường minh.
- Hàm thiếu bản dịch ném `NotFound` (kế thừa `LookupError`), KHÔNG phải
  `KeyError` — giống `get_transcript` và các hàm anh em.
- Hai đường GHI (`update_translation_segments`, `set_translation_status`) cũng
  ném `NotFound` khi id không tồn tại (review I-1): một `UPDATE` không khớp hàng
  nào vẫn "thành công", nên nuốt lỗi đó biến id sai thành mất cả lô đã dịch
  trong khi job vẫn báo `done`.
"""
import sqlite3

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


def _raw_status(repos, tr_id: int) -> str:
    """Đọc thẳng cột `status`, đi vòng qua `Translation.status` default "queued"."""
    with sqlite3.connect(repos.db_path) as conn:
        return conn.execute("SELECT status FROM translations WHERE id=?",
                            (tr_id,)).fetchone()[0]


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
    # Khẳng định trên KHÔNG đủ: `Translation.status` cũng default "queued", nên
    # nó vẫn xanh khi `_row_to_translation` thôi đọc cột. SQL thô dưới đây là
    # thứ duy nhất phân biệt "INSERT đã ghi 'queued' vào cột" với "cột chưa từng
    # được ghi" (review I-3).
    assert _raw_status(repos, tr_id) == "queued"


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
    # Cột thật cũng phải mang giá trị đó, không chỉ model đọc lên đúng.
    assert _raw_status(repos, tr_id) == "running"


def test_add_translation_status_survives_the_list_read_path_too(repos):
    """Chuỗi status không được phụ thuộc vào đúng MỘT test (review I-3).

    `list_translations` là đường đọc thứ hai, cũng đi qua `_row_to_translation`,
    và là đường route danh sách dùng. Ghim thêm ở đây thì mutant "INSERT bỏ qua
    tham số `status`" chết ở hai test chứ không phải một, và mutant bỏ
    `status=row["status"]` cũng chết thêm một lần nữa.
    """
    tid = _transcript(repos)
    tr_id = repos.add_translation(
        transcript_id=tid, transcript_version=1, engine="opus-mt",
        target_lang="vi", segments=[], prompt_version="opus-p1", status="failed")
    assert [t.status for t in repos.list_translations()] == ["failed"]
    assert _raw_status(repos, tr_id) == "failed"


def test_get_translation_reads_status_from_the_column(repos):
    """Chuỗi đọc `cột -> _row_to_translation` phải được ghim ĐỘC LẬP.

    Giá trị được ghi thẳng bằng SQL (không qua `add_translation`), nên nếu
    `_row_to_translation` bỏ `status=row["status"]` thì dataclass trả default
    `"queued"` và test này đỏ — đúng thứ mà `got.status == "queued"` không thấy
    (review I-3: đường đọc ngược chỉ được ghim bởi nhiều test thì mới chắc).
    """
    tid = _transcript(repos)
    tr_id = _translation(repos, tid)
    with sqlite3.connect(repos.db_path) as conn:
        conn.execute("UPDATE translations SET status='paused' WHERE id=?", (tr_id,))
        conn.commit()
    assert repos.get_translation(tr_id).status == "paused"


def test_checkpoint_writes_the_full_list_it_is_given(repos):
    """Checkpoint ghi ĐÚNG danh sách được đưa, KHÔNG append (review I-2).

    Việc cộng dồn (`done + new`) là của người gọi; tên cũ
    `test_checkpoint_appends_in_order` gán cho adapter một trách nhiệm nó không
    có. Ở đây người gọi tự truyền cả danh sách đã dịch, nên đọc lên vẫn đủ thứ tự.
    """
    tid = _transcript(repos)
    tr_id = _translation(repos, tid)
    repos.update_translation_segments(tr_id, [seg(1, "vi1")])
    repos.update_translation_segments(tr_id, [seg(1, "vi1"), seg(2, "vi2")])
    assert [s.i for s in repos.get_translation(tr_id).segments] == [1, 2]


def test_checkpoint_replaces_with_a_shorter_list(repos):
    """Ghi danh sách NGẮN HƠN thì mất việc trước — hợp đồng thật của adapter.

    Adapter không append: lần ghi sau thắng. Đây chính là lý do Task 11 phải tự
    cộng dồn rồi truyền cả danh sách; truyền mỗi lô mới thì `len(segments)` chỉ
    còn là kích thước lô và tiến độ biến mất trong im lặng (review I-2).
    """
    tid = _transcript(repos)
    tr_id = _translation(repos, tid)
    repos.update_translation_segments(
        tr_id, [seg(1, "vi1"), seg(2, "vi2"), seg(3, "vi3")])
    repos.update_translation_segments(tr_id, [seg(3, "vi3")])
    assert [s.i for s in repos.get_translation(tr_id).segments] == [3]


def test_checkpoint_leaves_status_and_tokens_untouched(repos):
    """Checkpoint CHỈ đụng cột `segments` (review I-2; mutant `SET ..., status=`).

    `status`, `tokens_in/out` và `qa_issues` của các lô đã xong phải sống sót qua
    một checkpoint; nếu không, một job đang chạy bị đẩy về `queued` và mất token
    đã tiêu — mà trước fix round này không test nào bắt được.
    """
    tid = _transcript(repos)
    tr_id = _translation(repos, tid)
    repos.set_translation_status(tr_id, "running", qa_issues=["cps:1=30.0"],
                                 tokens_in=7, tokens_out=9)
    repos.update_translation_segments(tr_id, [seg(1, "vi1")])
    got = repos.get_translation(tr_id)
    assert got.status == "running"
    assert (got.tokens_in, got.tokens_out, got.qa_issues) == (7, 9, ["cps:1=30.0"])
    assert _raw_status(repos, tr_id) == "running"


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


def test_checkpoint_missing_id_raises_not_found(repos):
    """Checkpoint vào id không tồn tại phải NỔ, không được im lặng (review I-1).

    `UPDATE ... WHERE id=?` không khớp hàng nào vẫn trả về "thành công"; nuốt lỗi
    đó biến một id sai thành mất cả lô đã dịch, rồi lần ghi `status` sau cũng im
    lặng nốt, và job báo `done` trên `segments` rỗng — đúng hợp đồng mà
    `len(segments)` là tiến độ bị phá. Đối xứng với `get_translation` (`NotFound`)
    và với `update_transcript_segments` (cũng ném).
    """
    tid = _transcript(repos)
    tr_id = _translation(repos, tid)
    with pytest.raises(NotFound):
        repos.update_translation_segments(tr_id + 999, [seg(1, "vi1")])


def test_set_status_missing_id_raises_not_found(repos):
    """Đường ghi trạng thái cũng phải nổ trên id sai (review I-1).

    Không có lỗi này thì một job hỏng ở checkpoint vẫn "đổi trạng thái" thành
    công trên một hàng không hề tồn tại, và báo cáo cuối là `done`.
    """
    tid = _transcript(repos)
    tr_id = _translation(repos, tid)
    with pytest.raises(NotFound):
        repos.set_translation_status(tr_id + 999, "done")
    with pytest.raises(NotFound):
        repos.set_translation_status(tr_id + 999, "done", tokens_in=1,
                                     qa_issues=["cps:1=30.0"])


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
    # Không có phương thức tăng version riêng: nếu có, tầng API sẽ gọi kèm và
    # version tăng gấp đôi mỗi lần sửa glossary (mục hiệu chỉnh #2).
    assert not hasattr(repos, "bump_glossary_version")


def test_port_declares_the_translation_storage_methods():
    """M-1 của review Task 18: `add_translation` chỉ có trên ADAPTER, không có
    trên cổng — một phương thức production sắp cần lại không nằm trong giao
    diện, nên handler/route buộc phải với tay xuống `SqliteRepos` (đúng thứ R74
    cấm).

    `Repos` là `Protocol` nên Python KHÔNG kiểm lúc chạy: thiếu khai báo vẫn
    import và chạy được, chỉ lộ ra khi có người viết handler theo đúng cổng. Vì
    vậy phải ghim bằng `dir()`.
    """
    from app.ports.repos import Repos

    for name in ("add_translation", "get_translation", "update_translation_segments",
                 "set_translation_status"):
        assert name in dir(Repos), f"cổng Repos thiếu {name}"


def test_set_status_rejects_the_error_argument_that_has_no_column(repos):
    """Bảng `translations` KHÔNG có cột `error` (schema.py:30-44).

    Lỗi của job nằm ở `jobs.error`. Nhận một tham số `error` rồi lặng lẽ bỏ qua
    còn tệ hơn ném lỗi: `TranslateHandler` sẽ tưởng nó ghi được lý do hỏng.
    """
    tid = _transcript(repos)
    tr_id = _translation(repos, tid)
    with pytest.raises(TypeError):
        repos.set_translation_status(tr_id, "failed", error="nổ")

