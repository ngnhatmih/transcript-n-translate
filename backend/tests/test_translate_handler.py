"""TranslateHandler: lô, alignment 3 bước, checkpoint, hủy, retry, QA.

Dùng engine GIẢ nên không cần model. Đây là chỗ ghim hành vi mà 1a đã trả giá để
học: xanh test không có nghĩa là chạy được, nên các test ở đây phải ĐỎ khi logic
đổi — mỗi test có một mutation tương ứng ở Step 5 của brief.

Ba điểm KHÁC bản code trong brief (mục hiệu chỉnh ở đầu brief thắng):

* **`report` nhận HAI tham số** (`worker.py:24`: `Callable[[float, str], None]`).
  Bản Step 1 của brief gọi `report=lambda line: None` với MỘT tham số, và bản
  Step 3 gọi `report("...")` với một tham số — cả hai đều không khớp giao thức
  thật, nên chúng bị sửa ở đây (hiệu chỉnh #1).
* **`add_translation` đòi `target_lang`** (port và adapter đều không cho default,
  `ports/repos.py:29-35`). Bản Step 1 gọi thiếu tham số này (hiệu chỉnh #5).
* `Segment` KHÔNG bao giờ được dựng tay ở đây để làm "kết quả engine": mọi test
  dùng đầu ra của chính engine (hiệu chỉnh #6). Helper `seg()` chỉ dựng dữ liệu
  ĐẦU VÀO (transcript nguồn), đúng như `test_repos_translations.py` làm.
"""
import copy
import sqlite3

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import NotFound, SqliteRepos
from app.domain.alignment import AlignmentProblem
from app.domain.models import CallStats, Job, Segment
from app.domain.mt import MtOpts
from app.domain.mt_qa import QaLimits
from app.pipeline.translate import TranslateHandler
from app.worker import PhaseQueueWorker
from tests.fakes import FakeGovernor, a_job
from tests.fakes_mt import FakeMtEngine


class _Job:
    """Job tối thiểu mà `translate()` cần: `cancel_requested` và `progress`.

    `payload` cố ý VẮNG ở mặc định: `run()` phải chịu được một job không có nó
    (attribute `Job.payload` là dataclass field nên có thật, nhưng một job đến
    từ đường khác thì phải hỏng thành thông báo rõ, không phải `AttributeError`
    trần).
    """

    def __init__(self, job_id=1, payload=None):
        self.id = job_id
        self.state = "running"
        self.progress = 0.0
        self.cancel_requested = False
        self.logs = []
        if payload is not None:
            self.payload = payload


class _NoGlossary(FakeMtEngine):
    def supports_glossary(self):
        return False


class _RecordingInputs(FakeMtEngine):
    """Nhớ chính các object `Segment` mà handler đưa vào engine.

    Dùng thay vì `monkeypatch` `engine.translate`: cách đó bắt test phải tự gọi
    lại `real_translate`, tức là chép lại thân hàm của fake vào test.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.batches_seen: list[list[Segment]] = []

    def translate(self, batch, glossary, opts):
        self.batches_seen.append(list(batch))
        return super().translate(batch, glossary, opts)


class _UpdateRaisesNotFound:
    """Bọc `SqliteRepos` và để riêng ĐƯỜNG GHI checkpoint ném `NotFound`.

    Không dùng được đường "id dịch sai" của brief: `get_translation` ném
    `NotFound` ngay ở dòng đầu nên vòng lặp không bao giờ tới checkpoint. Đây là
    mô phỏng trung thực của ca mà vòng sửa Task 6 (`ead5b4b`) nhắm tới: hàng biến
    mất (hoặc id sai) ĐÚNG lúc checkpoint, sau khi đã đọc được hàng và đã gọi
    engine xong.
    """

    def __init__(self, inner):
        self._inner = inner
        self.update_calls = 0

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def update_translation_segments(self, translation_id, segments):
        self.update_calls += 1
        raise NotFound(f"translation {translation_id} không tồn tại")


class _CancelInDbAfterFirstBatch(FakeMtEngine):
    """Huỷ theo ĐÚNG đường sản phẩm: `repos.request_cancel` ghi DB, không lật
    thuộc tính của một job giả.

    `job.cancel_requested` là ẢNH CHỤP mà worker đọc trước khi handler chạy
    (`oldest_queued()`), còn yêu cầu huỷ thật chỉ ghi `jobs.cancel_requested=1`;
    worker chỉ đọc lại cờ sau khi `run()` trả về. Nên một test chỉ lật thuộc
    tính đó là mock tự thoả mãn: nó xanh trong khi đường nối dây thật chết.
    """

    def __init__(self, repos, job_id):
        super().__init__()
        self._repos = repos
        self._job_id = job_id

    def translate(self, batch, glossary, opts):
        out = super().translate(batch, glossary, opts)
        if len(self.calls) == 1:
            self._repos.request_cancel(self._job_id)
        return out


class _StatsPerCall(FakeMtEngine):
    """Engine báo token/thời gian KHÁC NHAU ở mỗi lần gọi, và GHI ĐÈ như adapter thật.

    `OllamaMtEngine.translate` làm đúng thứ này: `self.last_stats = CallStats(...)`
    mỗi lần gọi. Nên sau một vòng lặp nhiều lô, `last_stats` chỉ còn số của lô
    CUỐI — và một handler đọc nó ở cuối sẽ báo thiếu chi phí của mọi lô trước.
    `tokens_in = 10·n` làm phép tổng (60 cho 3 lô) khác hẳn giá trị cuối (30), nên
    test phân biệt được TỔNG với "lô cuối" mà không cần đếm số lần gọi.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.stats_calls = 0

    def translate(self, batch, glossary, opts):
        out = super().translate(batch, glossary, opts)
        self.stats_calls += 1
        self.last_stats = CallStats(tokens_in=10 * self.stats_calls,
                                    tokens_out=20 * self.stats_calls,
                                    duration_ms=100 * self.stats_calls)
        return out


class _StatusSpy:
    """Bọc `SqliteRepos` để ghi lại MỌI trạng thái được ghi cho một bản dịch."""

    def __init__(self, inner, translation_id):
        self._inner = inner
        self._translation_id = translation_id
        self.writes: list[str] = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def set_translation_status(self, translation_id, status, **kw):
        if translation_id == self._translation_id:
            self.writes.append(status)
        return self._inner.set_translation_status(translation_id, status, **kw)


class _BoomOnSecondCall(FakeMtEngine):
    """Nổ `RuntimeError` trần ở lô thứ hai: engine thật sập (Ollama, OOM)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.calls_seen = 0

    def translate(self, batch, glossary, opts):
        self.calls_seen += 1
        if self.calls_seen == 2:
            raise RuntimeError("engine sập giữa đường")
        return super().translate(batch, glossary, opts)


@pytest.fixture
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def seg(i, text):
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text)


@pytest.fixture
def transcript(repos):
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    # Văn bản mỗi segment một khác: `batch_segments` chia theo KÝ TỰ, nên văn bản
    # trùng nhau sẽ làm mọi kích thước lô giống nhau và giấu mất lỗi chia lô.
    segs = [seg(i, f"câu {i}") for i in range(1, 6)]
    tid = repos.add_transcript(source_id=sid, engine="fw", lang="zh", segments=segs)
    return tid, segs


def _translation(repos, tid, *, engine="fake-mt", segments=None, status="queued"):
    return repos.add_translation(
        transcript_id=tid, transcript_version=1, engine=engine,
        target_lang="vi", segments=[] if segments is None else segments,
        prompt_version="p1", status=status)


def _handler(repos, engine, **kw):
    return TranslateHandler(repos, {"fake-mt": engine}, **kw)


def _noop(_progress, _line):
    pass


def _call(handler, repos, tr_id, tid, engine_id="fake-mt", job=None, report=_noop):
    handler.translate(translation_id=tr_id, transcript_id=tid, engine_id=engine_id,
                      source_lang="zh", target_lang="vi", job=job or _Job(),
                      report=report)


def test_handles_translate(repos):
    assert _handler(repos, FakeMtEngine()).handles() == "translate"


def test_all_segments_get_translated_in_order(repos, transcript):
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    _call(_handler(repos, FakeMtEngine()), repos, tr_id, tid)
    got = repos.get_translation(tr_id)
    assert [s.i for s in got.segments] == [1, 2, 3, 4, 5]
    assert got.status == "done"


def test_job_progress_reaches_one(repos, transcript):
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    job = _Job()
    _call(_handler(repos, FakeMtEngine(), batch_chars=1), repos, tr_id, tid, job=job)
    assert job.progress == 1.0


def test_engine_receives_the_source_and_target_languages(repos, transcript):
    """`MtOpts` phải mang ĐÚNG chiều dịch được yêu cầu, không phải default "vi"."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    engine = FakeMtEngine()
    TranslateHandler(repos, {"fake-mt": engine}).translate(
        translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
        source_lang="zh", target_lang="en", job=_Job(), report=_noop)
    assert engine.last_opts == MtOpts(source_lang="zh", target_lang="en")


def test_a_stale_payload_does_not_decide_the_recorded_glossary_version(
        repos, transcript):
    """Đây là ca THẬT của F1: payload CÓ khoá `glossary_version` nhưng đã CŨ.

    Route glossary đặt `glossary_version` vào payload lúc ENQUEUE. Nếu một lần sửa
    glossary khác landed trước khi job chạy thì payload trỏ vào version cũ, còn
    `glossary` mà handler thật sự dựng (`approved(list_terms(...))`) là glossary
    MỚI. Ghi theo payload là ghi một dấu vết SAI — đúng thứ spec §8.1 cấm.

    Kịch bản: hàng tạo ở version 1 -> job enqueue ở version 1 -> một lần upsert nữa
    đưa glossary lên version 3 -> job chạy. Kỳ vọng: ghi 3 (version ĐỌC LÚC CHẠY),
    KHÔNG phải 1 (ảnh chụp trong payload).
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with sqlite3.connect(repos.db_path) as conn:
        conn.execute("UPDATE translations SET glossary_version=1 WHERE id=?", (tr_id,))
        conn.commit()
    enqueued_version = repos.glossary_version()
    job_id = repos.add_job(Job(
        id=None, workspace=1, type="translate", engine="fake-mt", phase="translate",
        payload={"translation_id": tr_id, "transcript_id": tid, "engine_id": "fake-mt",
                 "source_lang": "zh", "target_lang": "vi",
                 "glossary_version": enqueued_version, "reason": "glossary"}))
    repos.upsert_term(lang="zh", term="câu 1", translation="cau 1",
                      note=None, approved=True)          # glossary đổi SAU enqueue
    current = repos.glossary_version()
    assert current > enqueued_version, "upsert phải bump version, nếu không test vô nghĩa"

    run_job = repos.list_jobs(states=("queued",))
    run_job = [j for j in run_job if j.id == job_id][0]
    _handler(repos, FakeMtEngine(), batch_chars=1).translate(
        translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
        source_lang="zh", target_lang="vi", job=run_job, report=_noop)

    got = repos.get_translation(tr_id)
    assert got.status == "done"
    assert got.glossary_version == current
    assert got.glossary_version != enqueued_version, "không được ghi ảnh chụp cũ"


def test_retranslation_records_the_glossary_version_it_actually_used(repos, transcript):
    """Bản tối thiểu: job KHÔNG mang payload vẫn phải ghi được version.

    Bổ trợ cho test stale-payload ở trên: nó ghim nguồn ĐỌC là repo, còn test này
    ghim rằng đường ghi không phụ thuộc payload có mặt hay không.
    """
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", target_lang="vi", segments=[],
                                  prompt_version="p1", glossary_version=0)
    repos.upsert_term(lang="zh", term="câu 1", translation="cau 1",
                      note=None, approved=True)         # bump version
    expected = repos.glossary_version()
    assert expected >= 1, "upsert_term phải bump version, nếu không test vô nghĩa"
    _call(_handler(repos, FakeMtEngine(), batch_chars=1), repos, tr_id, tid)
    got = repos.get_translation(tr_id)
    assert got.status == "done"
    assert got.glossary_version == expected


def test_finishing_a_translation_marks_the_transcript_translated(repos, transcript):
    """§8.6: `draft -> reviewed -> translated`. Đây là chỗ DUY NHẤT biết chắc xong.

    `approve` (Task 15) chỉ được ghi `reviewed`, nên nếu handler dịch không ghi
    `translated` thì giá trị cuối chuỗi không có người sản xuất và transcript mãi
    mãi nằm ở `reviewed` dù đã có bản dịch hoàn chỉnh.
    """
    tid, _ = transcript
    assert repos.get_transcript(tid).status == "draft"
    tr_id = _translation(repos, tid)
    _call(_handler(repos, FakeMtEngine()), repos, tr_id, tid)
    assert repos.get_translation(tr_id).status == "done"
    assert repos.get_transcript(tid).status == "translated"


def test_a_failed_translation_leaves_the_transcript_untranslated(repos, transcript):
    """`translated` trên một bản dịch HỎNG là cùng loại dối như version cũ.

    Transcript phải còn `draft` (không phải `translated`) khi bản dịch `failed`.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(RuntimeError):
        _call(_handler(repos, FakeMtEngine(drop_ids={3}), batch_chars=1),
              repos, tr_id, tid)
    assert repos.get_translation(tr_id).status == "failed"
    assert repos.get_transcript(tid).status == "draft"


def test_a_cancelled_translation_leaves_the_transcript_untranslated(repos, transcript):
    """Huỷ giữa đường cũng KHÔNG được ghi `translated`."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    job = _Job()
    engine = FakeMtEngine()
    real = engine.translate

    def cancel_after_first(batch, glossary, opts):
        out = real(batch, glossary, opts)
        job.cancel_requested = True
        return out

    engine.translate = cancel_after_first        # type: ignore[method-assign]
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid, job=job)
    assert repos.get_translation(tr_id).status == "cancelled"
    assert repos.get_transcript(tid).status == "draft"


def test_engine_exception_does_not_mark_the_transcript_translated(repos, transcript):
    """Lỗi engine trần cũng không được ghi `translated` (nhánh `except Exception`)."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(RuntimeError):
        _call(_handler(repos, _BoomOnSecondCall(), batch_chars=1),
              repos, tr_id, tid)
    assert repos.get_translation(tr_id).status == "failed"
    assert repos.get_transcript(tid).status == "draft"


def test_only_approved_terms_reach_the_engine(repos, transcript):
    """Glossary chưa duyệt là bản nháp: nó không được đi vào prompt."""
    tid, _ = transcript
    repos.upsert_term(lang="zh", term="câu 1", translation="cau 1",
                      note=None, approved=True)
    repos.upsert_term(lang="zh", term="câu 2", translation="cau 2",
                      note=None, approved=False)
    repos.upsert_term(lang="en", term="câu 3", translation="cau 3",
                      note=None, approved=True)
    tr_id = _translation(repos, tid)
    engine = FakeMtEngine()
    _call(_handler(repos, engine), repos, tr_id, tid)
    assert [t.term for t in engine.last_glossary] == ["câu 1"]


def test_checkpoint_happens_every_batch(repos, transcript):
    """Hủy giữa đường phải còn phần đã dịch, nên checkpoint không được dồn tới cuối."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    seen = []
    engine = FakeMtEngine()
    real_translate = engine.translate

    def spy(batch, glossary, opts):
        seen.append(len(repos.get_translation(tr_id).segments))
        return real_translate(batch, glossary, opts)

    engine.translate = spy          # type: ignore[method-assign]
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid)
    assert seen == [0, 1, 2, 3, 4], "trước mỗi lô, số segment đã ghi phải tăng dần"


def test_alignment_retry_happens_once_then_single_segment_fallback(repos, transcript):
    """Lô 5 phần tử lệch -> retry 1 lần -> hạ cấp TỪNG segment (5 lô 1 phần tử)."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    engine = FakeMtEngine(drop_ids={3})
    with pytest.raises(RuntimeError):
        _call(_handler(repos, engine, batch_chars=10_000), repos, tr_id, tid)
    # Lô lớn: gọi 1 lần (lệch) + 1 lần retry (lệch) -> hạ cấp 5 lô 1 phần tử, trong
    # đó 4 lô thành công và lô id=3 hỏng.
    assert engine.calls[0] == [1, 2, 3, 4, 5]
    assert engine.calls[1] == [1, 2, 3, 4, 5], "bước (a): retry đúng MỘT lần"
    assert engine.calls[2:] == [[1], [2], [3], [4], [5]], "bước (b): hạ cấp từng segment"
    # Cùng một lô bị gọi ĐÚNG hai lần trước khi hạ cấp: `attempts` đếm cả lần hỏng,
    # nên nó là thứ duy nhất phân biệt "retry một lần" với "retry hai lần".
    assert engine.attempts[:2] == [[1, 2, 3, 4, 5], [1, 2, 3, 4, 5]]


def test_alignment_retry_retries_the_same_batch_not_a_single_segment(repos, transcript):
    """Bước (a) phải thử lại CHÍNH lô đó, không được lén hạ cấp ngay.

    Mutant "retry bằng `engine.translate([batch[0]], ...)`" vẫn cho `calls` khớp
    ở ca trên (nó cũng gọi 1,2,3,4,5 rồi [1]..[5]), nhưng `attempts` lộ ra ngay:
    lần thử thứ hai phải là cả lô.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    engine = FakeMtEngine(drop_ids={3})
    with pytest.raises(RuntimeError):
        _call(_handler(repos, engine, batch_chars=10_000), repos, tr_id, tid)
    assert engine.attempts[1] == [1, 2, 3, 4, 5]
    assert engine.attempts[2] == [1], "sau retry mới được hạ cấp, và bắt đầu từ [1]"


def test_failure_keeps_what_was_already_translated(repos, transcript):
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(RuntimeError):
        _call(_handler(repos, FakeMtEngine(drop_ids={3}), batch_chars=1),
              repos, tr_id, tid)
    got = repos.get_translation(tr_id)
    assert got.status == "failed"
    assert [s.i for s in got.segments] == [1, 2], "phần đã dịch trước chỗ hỏng phải còn"


def test_engine_exception_outside_alignment_marks_the_translation_failed(
        repos, transcript):
    """Lỗi engine KHÔNG phải alignment cũng phải để lại `status='failed'`.

    Ràng buộc số 2 của phase nói trạng thái kết thúc là `failed`; nhánh alignment
    làm đúng, còn một `RuntimeError` trần (Ollama sập, OPUS-MT OOM) thì không —
    hàng dịch treo ở `queued` trong khi job đã `FAILED`, và API/UI hiện một bản
    dịch "đang chờ" không bao giờ chạy. Phần đã dịch vẫn phải được giữ nguyên.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(RuntimeError):
        _call(_handler(repos, _BoomOnSecondCall(), batch_chars=1),
              repos, tr_id, tid)
    got = repos.get_translation(tr_id)
    assert got.status == "failed"
    assert [s.i for s in got.segments] == [1], "phần đã dịch phải còn"


def test_a_failed_large_batch_keeps_everything_already_checkpointed(repos, transcript):
    """Hạ cấp hỏng thì KHÔNG được ghi phần hạ cấp đã dịch được.

    Lô lớn [1..5] lệch vì id=3; bước (b) dịch được [1], [2], [4] rồi chết ở [3].
    Nếu handler ghi luôn phần hạ cấp dở dang, `segments` thành [1, 2, 4] — một
    danh sách ĐÚNG id nhưng THIẾU dòng ở giữa, tức là "thiếu dòng" bị trộn với
    "đã dịch tới đâu" và lần retry sau sẽ thấy done_ids = {1,2,4} rồi bỏ qua 4.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(RuntimeError):
        _call(_handler(repos, FakeMtEngine(drop_ids={3}), batch_chars=10_000),
              repos, tr_id, tid)
    got = repos.get_translation(tr_id)
    assert got.status == "failed"
    assert got.segments == [], "lô lớn chưa checkpoint thì không có gì để giữ"


def test_failure_message_names_the_missing_segment(repos, transcript):
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(RuntimeError) as exc:
        _call(_handler(repos, FakeMtEngine(drop_ids={4}), batch_chars=1),
              repos, tr_id, tid)
    assert "4" in str(exc.value)


def test_failure_message_names_every_missing_segment_of_a_big_batch(repos, transcript):
    """Thông báo phải nói id nào CHƯA CÓ bản dịch, không chỉ id của lô đầu."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(RuntimeError) as exc:
        _call(_handler(repos, FakeMtEngine(drop_ids={2, 4}), batch_chars=10_000),
              repos, tr_id, tid)
    assert "2" in str(exc.value) and "4" in str(exc.value)


def test_cancel_between_batches_stops_and_marks_cancelled(repos, transcript):
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    job = _Job()
    engine = FakeMtEngine()
    real = engine.translate

    def cancel_after_first(batch, glossary, opts):
        out = real(batch, glossary, opts)
        job.cancel_requested = True
        return out

    engine.translate = cancel_after_first        # type: ignore[method-assign]
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid, job=job)
    got = repos.get_translation(tr_id)
    assert got.status == "cancelled"
    assert len(got.segments) == 1, "hủy sau lô đầu thì chỉ có 1 segment"


def test_cancel_on_the_last_batch_writes_nothing_more_and_leaves_status_cancelled(
        repos, transcript):
    """Huỷ ở lô cuối: phần đã checkpoint còn nguyên, không chạy QA, không `done`."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    job = _Job()
    engine = FakeMtEngine()
    real = engine.translate
    state = {"n": 0}

    def cancel_on_last(batch, glossary, opts):
        state["n"] += 1
        out = real(batch, glossary, opts)
        if state["n"] == 4:
            job.cancel_requested = True
        return out

    engine.translate = cancel_on_last        # type: ignore[method-assign]
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid, job=job)
    got = repos.get_translation(tr_id)
    assert got.status == "cancelled"
    assert [s.i for s in got.segments] == [1, 2, 3, 4]
    assert got.qa_issues == [], "huỷ thì không được ghi QA của một bản dịch chưa xong"


def test_cancel_requested_in_the_db_during_the_run_stops_at_the_next_batch(
        repos, transcript):
    """Huỷ giữa các lô phải đọc cờ từ REPO, không tin ảnh chụp trên `job`.

    Đây là đường nối dây thật: `worker._run_one` lấy job bằng `oldest_queued()`
    TRƯỚC khi chạy handler, `routes_jobs` chỉ ghi `cancel_requested=1` vào DB, và
    worker chỉ đọc lại cờ SAU khi `run()` trả về. Nếu handler chỉ nhìn
    `job.cancel_requested` thì bản dịch 5 lô chạy HẾT, ghi `status='done'` kèm QA,
    rồi job mới thành `cancelled` ở ranh giới — người dùng bấm huỷ và không thấy
    gì dừng lại.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    job = a_job(None, job_type="translate", engine="fake-mt")
    job.payload = {"translation_id": tr_id, "transcript_id": tid,
                   "engine_id": "fake-mt", "source_lang": "zh", "target_lang": "vi"}
    jid = repos.add_job(job)
    engine = _CancelInDbAfterFirstBatch(repos, jid)
    handler = TranslateHandler(repos, {"fake-mt": engine}, batch_chars=1)
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"translate": handler})

    while worker.tick():
        pass

    assert engine.calls == [[1]], "huỷ ngay sau lô 1 thì không được gọi lô nào nữa"
    assert repos.get_job(jid).state == "cancelled"
    got = repos.get_translation(tr_id)
    assert got.status == "cancelled", "job huỷ mà bản dịch vẫn `done` là hai mặt lệch nhau"
    assert [s.i for s in got.segments] == [1], "phần đã checkpoint phải được giữ"
    assert repos.get_job(jid).progress == 0.2


def test_each_segment_failure_is_logged_with_its_own_id(repos, transcript):
    """Dòng log lúc hỏng phải nói ĐÚNG id vừa hỏng, không phải id nào khác.

    Thông báo lỗi cuối cùng chỉ nói "còn thiếu id nào"; dòng log giữa đường mới
    là chỗ duy nhất nói id nào VỪA hỏng và vì sao, nên nó cũng là chỗ duy nhất
    phân biệt được "hỏng ở 3" với "hỏng ở 5".
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    seen = []
    with pytest.raises(RuntimeError):
        _call(_handler(repos, FakeMtEngine(drop_ids={3}), batch_chars=1),
              repos, tr_id, tid, report=lambda p, line: seen.append((p, line)))
    lines = [line for _, line in seen]
    assert any("segment 3" in line for line in lines), lines
    assert not any("segment 5 thất bại" in line for line in lines)
    probs = [p for p, _ in seen]
    assert probs == sorted(probs), f"tiến độ bị nhảy lùi giữa dòng chẩn đoán: {seen}"


def test_big_batch_fallback_logs_the_segment_that_failed(repos, transcript):
    """Lô lớn lệch rồi hạ cấp: dòng log phải nói ĐÚNG segment vừa hỏng.

    Test kia chỉ chạm bước (b) với `batch_chars=1`, ở đó lô hạ cấp có MỘT phần tử
    nên `batch[-1].i == s.i`; mutant dùng id của segment cuối lô vì thế vẫn xanh
    trên toàn bộ suite. Với một lô 5 phần tử thì hai id đó khác nhau, và đây là
    dòng log DUY NHẤT nói segment nào VỪA hỏng (thông báo cuối chỉ liệt kê id còn
    thiếu), nên nó cũng là chỗ duy nhất phân biệt "hỏng ở 3" với "hỏng ở 5".
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    seen = []
    with pytest.raises(RuntimeError):
        _call(_handler(repos, FakeMtEngine(drop_ids={3}), batch_chars=10_000),
              repos, tr_id, tid, report=lambda p, line: seen.append((p, line)))
    lines = [line for _, line in seen]
    assert any("segment 3 thất bại" in line for line in lines), lines
    assert not any("segment 5 thất bại" in line for line in lines), lines
    probs = [p for p, _ in seen]
    assert probs == sorted(probs), f"tiến độ bị nhảy lùi giữa dòng chẩn đoán: {seen}"


def test_retry_resumes_from_first_missing_segment(repos, transcript):
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(RuntimeError):
        _call(_handler(repos, FakeMtEngine(drop_ids={3}), batch_chars=1),
              repos, tr_id, tid)
    engine = FakeMtEngine()
    seen = []
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid,
          report=lambda p, line: seen.append(line))
    assert engine.calls[0] == [3], "đã có 1,2 thì không được dịch lại"
    assert "2/5" in seen[0], f"dòng đầu phải nói đã có 2/5 segment: {seen}"
    assert [s.i for s in repos.get_translation(tr_id).segments] == [1, 2, 3, 4, 5]


def test_retry_uses_the_gap_inside_a_partial_translation(repos, transcript):
    """Hàng đã có sẵn [1,2,4] (thiếu 3): retry bắt đầu từ 3, không dịch lại 1,2,4.

    Đây là ca mà "resume" khác "dịch lại từ đầu" rõ nhất, và cũng là ca ghim
    rằng `done` khớp theo ID chứ không theo số lượng.
    """
    tid, _ = transcript
    seeds = [seg(1, "vi 1"), seg(2, "vi 2"), seg(4, "vi 4")]
    tr_id = _translation(repos, tid, segments=seeds, status="failed")
    engine = FakeMtEngine()
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid)
    assert engine.calls == [[3], [5]]
    assert [s.i for s in repos.get_translation(tr_id).segments] == [1, 2, 3, 4, 5]


def test_success_after_a_partial_row_does_not_duplicate_the_seed(repos, transcript):
    """`done` được giữ theo id, nên hàng cũ không bị chèn lại vào giữa danh sách."""
    tid, _ = transcript
    tr_id = _translation(repos, tid, segments=[seg(2, "vi 2")], status="failed")
    _call(_handler(repos, FakeMtEngine(), batch_chars=1), repos, tr_id, tid)
    got = repos.get_translation(tr_id)
    ids = [s.i for s in got.segments]
    assert ids == sorted(set(ids)), f"id trùng hoặc sai thứ tự: {ids}"
    assert ids == [1, 2, 3, 4, 5]


def test_qa_issues_are_written(repos, transcript):
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    lim = QaLimits(max_cps=0.001, min_len_ratio=0.0, max_len_ratio=1e9)
    _call(_handler(repos, FakeMtEngine(), batch_chars=1, limits=lim),
          repos, tr_id, tid)
    assert any(i.startswith("cps:") for i in repos.get_translation(tr_id).qa_issues)


def test_engine_without_glossary_sets_the_flag(repos, transcript):
    tid, _ = transcript
    repos.upsert_term(lang="zh", term="câu 1", translation="cau 1",
                      note=None, approved=True)
    tr_id = _translation(repos, tid)
    _call(_handler(repos, _NoGlossary(), batch_chars=1), repos, tr_id, tid)
    assert "engine_no_glossary" in repos.get_translation(tr_id).qa_issues


def test_engine_without_glossary_and_without_terms_gets_no_flag(repos, transcript):
    """Cờ chỉ có nghĩa khi CÓ ràng buộc bị bỏ qua; glossary rỗng thì không cờ."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    _call(_handler(repos, _NoGlossary(), batch_chars=1), repos, tr_id, tid)
    assert repos.get_translation(tr_id).qa_issues == []


# --------------------------------------------------------------------------
# A2 ở tầng HANDLER: engine CHÉP NGUYÊN bản gốc.
#
# Đây đúng cái `qwen2.5-3b` qua `POST /api/translations` đã làm 9/9 lần ở lượt
# trước: 8/8 segment trả về nguyên chữ Trung, `qa_issues=[]`, job `done`,
# `transcript='translated'`. Bài này ghim rằng lớp QA THẬT SỰ chạy trong đường
# nối thật nhìn thấy nó — không chỉ hàm `qa_translation` gọi tay trong unit test.
# --------------------------------------------------------------------------

def test_an_echoing_engine_is_flagged_by_the_language_check(repos):
    zh = ["今天我们来聊一聊中文语音识别。", "这个项目的成本其实只有百分之十。"]
    sid = repos.add_source(kind="file", origin="zh.ogg", media_path="/m/zh.ogg",
                           lang="zh")
    tid = repos.add_transcript(
        source_id=sid, engine="fw-tiny", lang="zh",
        segments=[seg(i + 1, t) for i, t in enumerate(zh)])
    tr_id = _translation(repos, tid)
    # `FakeMtEngine` dịch theo `mapping`; ánh xạ đồng nhất = echo từng ký tự.
    _call(_handler(repos, FakeMtEngine(mapping={t: t for t in zh})),
          repos, tr_id, tid)

    issues = repos.get_translation(tr_id).qa_issues
    flagged = [i for i in issues if i.startswith("lang:")]
    assert len(flagged) == 2, (
        f"engine chép nguyên bản gốc mà QA không nói gì: {issues}"
    )
    assert all("source:" in i for i in flagged), issues


def test_a_real_vietnamese_translation_gets_no_language_flag(repos):
    """Ca XANH ở cùng tầng: bản dịch tiếng Việt thật không được gắn cờ `lang:`."""
    zh = ["今天我们来聊一聊中文语音识别。"]
    sid = repos.add_source(kind="file", origin="zh.ogg", media_path="/m/zh.ogg",
                           lang="zh")
    tid = repos.add_transcript(
        source_id=sid, engine="fw-tiny", lang="zh",
        segments=[seg(1, zh[0])])
    tr_id = _translation(repos, tid)
    _call(_handler(repos, FakeMtEngine(
        mapping={zh[0]: "Hôm nay chúng ta sẽ nói về nhận dạng tiếng nói tiếng Trung."})),
        repos, tr_id, tid)
    issues = repos.get_translation(tr_id).qa_issues
    assert not [i for i in issues if i.startswith("lang:")], issues



def test_unknown_engine_id_fails_before_touching_the_translation(repos, transcript):
    tid, _ = transcript
    tr_id = _translation(repos, tid, engine="khong-co")
    with pytest.raises(KeyError):
        _call(_handler(repos, FakeMtEngine()), repos, tr_id, tid, engine_id="khong-co")
    got = repos.get_translation(tr_id)
    assert got.status == "queued", "id engine sai không được đụng vào hàng"
    assert got.segments == []


def test_engines_are_keyed_by_the_registry_spec_id(repos, transcript):
    """Khoá là `spec.id` của registry, KHÔNG phải `engine.engine_id` (hiệu chỉnh #4).

    Với HY-MT hai giá trị này khác nhau (`hy-mt1.5-7b-q4_K_M` vs `hy-mt-1.5-7b`),
    nên handler tra bằng `engine.engine_id` sẽ `KeyError` trên chính engine mà nó
    vừa nhận. Test này ghim rằng chỉ khoá của registry được tra.
    """
    tid, _ = transcript

    class _OddEngineId(FakeMtEngine):
        @property
        def engine_id(self):
            return "hy-mt-1.5-7b"

    tr_id = _translation(repos, tid, engine="hy-mt1.5-7b-q4_K_M")
    handler = TranslateHandler(repos, {"hy-mt1.5-7b-q4_K_M": _OddEngineId()})
    _call(handler, repos, tr_id, tid, engine_id="hy-mt1.5-7b-q4_K_M")
    assert repos.get_translation(tr_id).status == "done"


def test_unknown_translation_id_fails_loudly(repos, transcript):
    """`get_translation` ném `NotFound` (kế thừa `LookupError`), không trả `None`."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(LookupError):
        _call(_handler(repos, FakeMtEngine()), repos, tr_id + 999, tid)


def test_checkpoint_not_found_is_loud_and_not_a_silent_done(repos, transcript):
    """`NotFound` từ checkpoint phải nổi lên thành lỗi, không được nuốt (hiệu chỉnh #2).

    `update_translation_segments` ném `NotFound` khi id không tồn tại (vòng sửa
    Task 6). Nuốt nó thì handler vẫn chạy tiếp, ghi `status='done'` trên một hàng
    không có segment nào, và job báo thành công trên một bản dịch rỗng — đúng thứ
    bản no-op im lặng đã che mất.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    guarded = _UpdateRaisesNotFound(repos)
    with pytest.raises(LookupError, match=str(tr_id)):
        _call(_handler(guarded, FakeMtEngine()), repos, tr_id, tid)
    assert guarded.update_calls == 1
    assert repos.get_translation(tr_id).segments == []
    assert repos.get_translation(tr_id).status == "running", (
        "hàng biến mất thì không có gì để đánh dấu `failed`; đừng ghi thêm. "
        "`running` — không phải `queued` — là trạng thái handler đã ghi lúc bắt "
        "đầu việc (I-3), và nó ở lại đó vì chính lần ghi `failed` cũng hỏng; "
        "worker đối chiếu nó ở nhánh job hỏng (`PhaseQueueWorker._settle_translation`)")


def test_run_reads_the_job_payload(repos, transcript):
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    job = _Job(payload={"translation_id": tr_id, "transcript_id": tid,
                        "engine_id": "fake-mt", "source_lang": "zh",
                        "target_lang": "vi"})
    _handler(repos, FakeMtEngine()).run(job, report=_noop)
    assert repos.get_translation(tr_id).status == "done"


def test_run_reports_progress_and_log_lines_with_two_arguments(repos, transcript):
    """`report` thật nhận HAI tham số (`worker.py:24`), không phải một (hiệu chỉnh #1).

    Bản brief gọi `report("...")`; với `worker._run_one` định nghĩa
    `def report(progress, line)` thì mọi dòng log đó là `TypeError` ngay lần đầu —
    và vì nó nằm trong `try` của worker nên job chỉ đơn giản là `failed`, không
    ai thấy lý do. Test này gọi bằng đúng chữ ký hai tham số và kiểm vài dòng
    không rỗng, nên mutant "gọi report một tham số" chết ngay tại đây.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    seen: list[tuple[float, str]] = []
    job = _Job(payload={"translation_id": tr_id, "transcript_id": tid,
                        "engine_id": "fake-mt", "source_lang": "zh",
                        "target_lang": "vi"})
    _handler(repos, FakeMtEngine(), batch_chars=1).run(
        job, report=lambda progress, line: seen.append((progress, line)))
    assert seen, "không có dòng log nào được báo"
    assert all(isinstance(p, float) and isinstance(line, str) for p, line in seen)
    assert [p for p, _ in seen] == sorted(p for p, _ in seen), "tiến độ phải không giảm"
    assert seen[-1][0] == 1.0


def test_run_without_payload_fails_loudly_without_touching_anything(repos, transcript):
    """Thiếu payload là lỗi CỦA JOB: `KeyError`, và bản dịch vẫn nguyên trạng."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(KeyError):
        _handler(repos, FakeMtEngine()).run(_Job(), report=_noop)
    assert repos.get_translation(tr_id).status == "queued"


def test_engine_returning_a_segment_object_is_stored_verbatim(repos, transcript):
    """Không dựng `Segment` bằng tay: các trường engine điền phải sống sót (hiệu chỉnh #6).

    `Segment` có 13 trường. Hai task trước đã ship lỗi dựng tay làm nuốt 7 trường;
    ở đây engine trả `Segment` với `speaker`/`emotion`/`events`/`qa`/`t` được điền
    và handler phải lưu NGUYÊN object đó. Một `Segment(i=..., start=..., end=...,
    text=...)` dựng tay sẽ xoá sạch phần còn lại.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    engine = FakeMtEngine()

    class _Rich(FakeMtEngine):
        def translate(self, batch, glossary, opts):
            out = super().translate(batch, glossary, opts)
            for s in out:
                s.speaker = "SPK1"
                s.emotion = "neutral"
                s.events = ["music"]
                s.qa = ["x"]
                s.t = "raw"
                s.words = []
                s.avg_logprob = -0.25
                s.no_speech_prob = 0.01
                s.suspect = True
            engine.calls.append([s.i for s in batch])
            return out

    _call(_handler(repos, _Rich()), repos, tr_id, tid)
    got = repos.get_translation(tr_id).segments
    assert [s.i for s in got] == [1, 2, 3, 4, 5]
    for s in got:
        assert s.speaker == "SPK1" and s.emotion == "neutral"
        assert s.events == ["music"] and s.qa == ["x"] and s.t == "raw"
        assert s.words == [] and s.avg_logprob == -0.25
        assert s.no_speech_prob == 0.01 and s.suspect is True


def test_the_engine_input_is_the_segment_object_read_from_the_repo(repos, transcript):
    """Handler không được chế bản sao segment trước khi đưa engine.

    Đối tượng engine nhận phải CHÍNH LÀ object mà `get_transcript` trả về, không
    phải một `Segment(i=..., start=..., end=..., text=...)` dựng lại: dựng tay làm
    nuốt 7/13 trường TRƯỚC cả khi engine kịp thấy chúng (hai task trước trong
    phase này đã ship đúng lỗi đó). So `id()` với một lần `get_transcript` KHÁC
    không nói lên gì — mỗi lần gọi trả một object mới — nên đối tượng đã đọc được
    ghi lại từ chính lời gọi của handler.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    engine = _RecordingInputs()
    seen = []

    class _Recording(SqliteRepos):
        def get_transcript(self, transcript_id):
            t = super().get_transcript(transcript_id)
            if transcript_id == tid:
                seen.extend(t.segments)
            return t

    recording = _Recording(repos.db_path, clock=SystemClock())
    TranslateHandler(recording, {"fake-mt": engine}, batch_chars=1).translate(
        translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
        source_lang="zh", target_lang="vi", job=_Job(), report=_noop)
    handed = [id(s) for batch in engine.batches_seen for s in batch]
    assert handed == [id(s) for s in seen], "handler đã dựng lại Segment trước khi gửi"
    assert [s.i for s in seen] == [1, 2, 3, 4, 5]


def test_whole_run_is_cancellable_before_the_first_batch(repos, transcript):
    """Huỷ trước lô đầu: không gọi engine lần nào, trạng thái `cancelled`, rỗng."""
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    job = _Job()
    job.cancel_requested = True
    engine = FakeMtEngine()
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid, job=job)
    got = repos.get_translation(tr_id)
    assert engine.attempts == []
    assert got.status == "cancelled"
    assert got.segments == []
    assert job.progress == 0.0


def test_rerunning_a_finished_translation_calls_no_engine(repos, transcript):
    """Đã đủ segment thì không còn lô nào: engine không được gọi lại lần nào."""
    tid, _ = transcript
    segs = [seg(i, f"[vi]câu {i}") for i in range(1, 6)]
    tr_id = _translation(repos, tid, segments=copy.deepcopy(segs))
    engine = FakeMtEngine()
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid)
    assert engine.attempts == []
    assert repos.get_translation(tr_id).status == "done"


# ---------------------------------------------------------------------------
# spec §4.2 — mỗi lời gọi engine để lại MỘT hàng `llm_calls`, và số của cả bản
# dịch là TỔNG của các hàng đó (I-1 + I-2 của review cuối)
# ---------------------------------------------------------------------------

def _llm_calls_for(repos, job_id):
    return repos.list_llm_calls(job_id)


def test_a_multi_batch_translation_records_one_llm_call_per_engine_call(
        repos, transcript):
    """§4.2: ba lô ⇒ ít nhất ba hàng `llm_calls`, không phải một hàng hay không hàng nào.

    Trước bản vá, `add_llm_call` KHÔNG có người gọi nào trong `app/`: bảng tồn tại
    và có test ở tầng repo, nhưng production không ghi gì vào đó, nên spec §4.2
    ("mỗi bước phải đếm được ... để biết engine nào hay hỏng alignment") và §10
    (đo tỉ lệ hỏng để chọn kích thước lô) không có kênh dữ liệu nào.

    `batch_chars=1` với text `"câu i"` (4 ký tự) ⇒ 5 lô một segment ⇒ ĐÚNG 5 hàng.
    Khẳng định `>= 2` sẽ xanh cả khi handler ghi một hàng cho cả bản dịch, nên
    phép đếm phải khớp đúng số lần chạm engine: 5.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    engine = FakeMtEngine()
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid)

    assert len(engine.attempts) == 5, "fixture phải tạo 5 lô một segment"
    rows = _llm_calls_for(repos, 1)
    assert len(rows) == len(engine.attempts) == 5, (
        f"mỗi lần chạm engine phải có ĐÚNG một hàng `llm_calls`: {rows}"
    )
    assert [r["engine"] for r in rows] == ["fake-mt"] * 5
    assert [r["prompt_version"] for r in rows] == ["p1"] * 5, (
        "`prompt_version` lấy từ hàng `translations` (dữ liệu của registry), "
        "không phải suy lại từ engine"
    )
    assert [r["model_ref"] for r in rows] == ["fake/model"] * 5
    assert all(r["ok"] == 1 for r in rows), "cả 5 lô đều thành công"


def test_a_failed_alignment_attempt_is_recorded_with_ok_false(repos, transcript):
    """Lần gọi HỎNG cũng là một hàng — đó chính là thứ §10 cần để đếm tỉ lệ hỏng.

    Lô 5 phần tử lệch vì id=3 ⇒ hai lần thử cả lô (đều `ok=0`) rồi 5 lô hạ cấp, 4
    `ok=1` và một `ok=0`. Nếu chỉ ghi các lần THÀNH CÔNG thì bảng đếm được số lần
    dịch chứ không đếm được số lần HỎNG, tức là không trả lời được câu §4.2 đặt ra.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    engine = FakeMtEngine(drop_ids={3})
    with pytest.raises(RuntimeError):
        _call(_handler(repos, engine, batch_chars=10_000), repos, tr_id, tid)

    rows = _llm_calls_for(repos, 1)
    assert len(rows) == len(engine.attempts) == 7, (
        "2 lần thử cả lô + 3 lô hạ cấp ([1], [2], [3] rồi dừng ở id hỏng) — "
        f"nhận {len(rows)} hàng: {rows}"
    )
    assert [r["ok"] for r in rows].count(0) == 3, (
        "hai lần thử lô lớn và lô hạ cấp của id=3 đều phải là `ok=0`"
    )
    failing = [r for r in rows if r["ok"] == 0]
    assert all(r["error"] for r in failing), (
        "hàng hỏng phải mang lý do, nếu không thì không biết hỏng vì lệch hay vì sập"
    )


def test_a_transport_error_is_recorded_before_it_is_reraised(repos, transcript):
    """`RuntimeError` trần (Ollama sập) cũng để lại hàng `ok=0` trước khi nổi lên.

    Ca này KHÔNG phải `AlignmentProblem` nên nó không được thử lại — nhưng nó vẫn
    là một lần chạm engine đã tiêu thời gian, và nếu bị nuốt khỏi `llm_calls` thì
    nhóm hỏng tốn kém nhất (model/runtime sập) là nhóm duy nhất không đếm được.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    with pytest.raises(RuntimeError):
        _call(_handler(repos, _BoomOnSecondCall(), batch_chars=1), repos, tr_id, tid)

    rows = _llm_calls_for(repos, 1)
    assert [r["ok"] for r in rows] == [1, 0], (
        f"lô 1 xong (ok=1), lô 2 sập (ok=0): {rows}"
    )
    assert "engine sập giữa đường" in rows[1]["error"]


def test_a_multi_batch_translation_stores_the_sum_of_every_call(repos, transcript):
    """I-2: `tokens_in`/`tokens_out`/`duration_ms` là TỔNG, không phải lô CUỐI.

    Engine ở đây ghi đè `last_stats` mỗi lần gọi như `OllamaMtEngine` thật, và báo
    `tokens_in = 10·n`. Với 3 lô: tổng là 60, còn đọc `last_stats` sau vòng lặp
    được 30 — đo trên bản cũ đúng bằng 30, tức bản dịch tự báo thiếu 2/3 chi phí.
    `duration_ms` đi cùng đường (100+200+300) để phép ghim không chỉ đúng một cột.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    engine = _StatsPerCall()
    # Độ dài các segment là 5,5,5,5,4 ("câu i"), nên `batch_chars=14` cho ra ĐÚNG
    # 3 lô: [1,2], [3,4], [5]. Không đoán: `engine.calls` được khẳng định ngay
    # dưới đây, và phép tổng chỉ khác phép "lô cuối" khi có ≥2 lô.
    _call(_handler(repos, engine, batch_chars=14), repos, tr_id, tid)

    assert engine.calls == [[1, 2], [3, 4], [5]], (
        f"fixture phải tạo 3 lô để phép tổng khác phép 'lô cuối': {engine.calls}"
    )
    got = repos.get_translation(tr_id)
    assert got.tokens_in == 60, (
        f"tổng 10+20+30 = 60; 'lô cuối' là 30 (LỖI I-2): {got.tokens_in}"
    )
    assert got.tokens_out == 120
    assert got.duration_ms == 600


def test_the_stored_totals_are_derivable_from_the_llm_calls_rows(repos, transcript):
    """Tổng trên `translations` phải bằng tổng của chính các hàng `llm_calls`.

    Đây là bất biến khiến I-2 không thể tái phát: `translations` không còn tự đọc
    một biến trong bộ nhớ của engine, nó cộng lại đúng những hàng mà người vận
    hành nhìn thấy. Một bản vá chỉ sửa một trong hai mặt sẽ đỏ ở đây.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    engine = _StatsPerCall()
    _call(_handler(repos, engine, batch_chars=14), repos, tr_id, tid)

    rows = _llm_calls_for(repos, 1)
    got = repos.get_translation(tr_id)
    assert len(rows) == 3, rows
    assert got.tokens_in == sum(r["tokens_in"] for r in rows)
    assert got.tokens_out == sum(r["tokens_out"] for r in rows)
    assert got.duration_ms == sum(r["duration_ms"] for r in rows)


def test_an_engine_without_llm_call_rows_leaves_the_totals_unset(repos, transcript):
    """Không gọi engine lần nào ⇒ `None`, KHÔNG phải `0`.

    "Chưa gọi engine" và "gọi rồi mà engine không báo token" (OPUS-MT chạy trong
    tiến trình) là hai chuyện khác nhau; ghi `0` cho cả hai là bịa ra một phép đo.
    """
    tid, _ = transcript
    segs = [seg(i, f"[vi]câu {i}") for i in range(1, 6)]
    tr_id = _translation(repos, tid, segments=copy.deepcopy(segs))
    engine = _StatsPerCall()
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid)

    assert engine.attempts == [], "không còn lô nào thì engine không được gọi"
    got = repos.get_translation(tr_id)
    assert (got.tokens_in, got.tokens_out, got.duration_ms) == (None, None, None)


def test_running_is_written_before_the_first_batch(repos, transcript):
    """I-3: `running` phải được GHI, và ghi TRƯỚC khi chạm engine.

    Vocabulary của cột đã khai `queued | running | done | failed | cancelled` từ
    Task 1, nhưng không có dòng production nào ghi `running`; Task 13 phơi cột này
    ra API nên giao diện Workspace 2 không có cách nào phân biệt "vừa xếp" với
    "đang chạy". Đo bằng chính lô đầu tiên: lúc engine được gọi, hàng đã `running`.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    engine = FakeMtEngine()
    real = engine.translate        # giữ TRƯỚC khi thay, nếu không `spy` tự gọi mình
    seen = []

    def spy(batch, glossary, opts):
        seen.append(repos.get_translation(tr_id).status)
        return real(batch, glossary, opts)

    engine.translate = spy          # type: ignore[method-assign]
    _call(_handler(repos, engine, batch_chars=1), repos, tr_id, tid)

    assert seen[0] == "running", (
        f"trước lô đầu, hàng dịch phải là `running`, nhận {seen[0]!r}: {seen}"
    )
    assert repos.get_translation(tr_id).status == "done"


def test_running_is_written_after_the_engine_lookup(repos, transcript):
    """Thứ tự này là một phần của hợp đồng: id engine sai ⇒ hàng vẫn `queued`.

    `test_unknown_engine_id_fails_before_touching_the_translation` ghim hàng còn
    nguyên `queued` khi `KeyError`; bài này ghim CƠ CHẾ (mọi trạng thái được ghi
    đều nằm sau phép tra engine), nên một bản vá đặt `running` lên trước sẽ đỏ ở
    đây kèm lý do, chứ không chỉ đỏ ở một assert ở tệp khác.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid, engine="khong-co")
    spy = _StatusSpy(repos, tr_id)
    with pytest.raises(KeyError):
        _call(_handler(spy, FakeMtEngine()), repos, tr_id, tid, engine_id="khong-co")
    assert spy.writes == [], f"không được ghi trạng thái nào: {spy.writes}"


def test_a_cancelled_run_leaves_running_behind_it(repos, transcript):
    """`running` xuất hiện TRƯỚC `cancelled` — thứ tự, không chỉ tập giá trị.

    Một mutant ghi `running` ở CUỐI hàm (sau khi đã `done`/`cancelled`) vẫn cho
    tập giá trị khác đi, nhưng mutant ghi `running` ngay trước khi trả về sẽ làm
    hàng cuối cùng là `running` trên một job đã huỷ — đúng thứ I-3 tồn tại để dẹp.
    """
    tid, _ = transcript
    tr_id = _translation(repos, tid)
    job = _Job()
    engine = FakeMtEngine()
    real = engine.translate

    def cancel_after_first(batch, glossary, opts):
        out = real(batch, glossary, opts)
        job.cancel_requested = True
        return out

    engine.translate = cancel_after_first        # type: ignore[method-assign]
    spy = _StatusSpy(repos, tr_id)
    _call(_handler(spy, engine, batch_chars=1), repos, tr_id, tid, job=job)

    assert spy.writes == ["running", "cancelled"], spy.writes
    assert repos.get_translation(tr_id).status == "cancelled"


# ---------------------------------------------------------------------------
# LÔ QUÁ TO + `AlignmentProblem` DO ADAPTER NÉM RA
#
# Hai lỗi THẬT, đo được trên bản ghi thật (`data/app.db`, transcript #1, 464 đoạn,
# engine `qwen2.5-7b`):
#
# * lô đầu là 135 mục / 1199 ký tự (`batch_segments`, ngân sách 1200 ký tự — đoạn
#   phụ đề thật rất ngắn, trung bình 8,6 ký tự), và một lời gọi 135 mục bị model
#   BỎ MỤC: đo N vào/N ra = 1→1, 4→4, 8→8, 16→16, 32→32, 64→64, **135→100/101**
#   với `done_reason="stop"` (KHÔNG phải cắt vì hết context);
# * adapter ném `AlignmentProblem` TỪ `parse_batch_response`, và bản cũ bắt nó
#   bằng `except Exception` (nó là lớp con) rồi coi là lỗi VẬN CHUYỂN ⇒ chính sách
#   ba bước không chạy. Bằng chứng từ job thật: log chỉ có một dòng `LỖI: engine
#   trả 101 mục, cần 135`, KHÔNG có dòng `lệch alignment (lần 1)` và KHÔNG có
#   dòng `hạ cấp`, và `llm_calls` có ĐÚNG MỘT hàng cho mỗi lần chạy ⇒ 0/464 đoạn.
# ---------------------------------------------------------------------------

#: Cỡ lô lớn nhất còn đo được là ĐỦ với `qwen2.5-7b` (xem `mt.DEFAULT_MAX_ITEMS`).
_MEASURED_GOOD_ITEMS = 64

#: Cỡ lô đã ĐO được là GÃY: model trả 100/101 mục rồi `done`.
_MEASURED_BROKEN_ITEMS = 135


class _RaisesAlignmentAbove(FakeMtEngine):
    """Adapter THẬT: tự ném `AlignmentProblem` khi lô vượt `limit` mục.

    `OllamaMtEngine.translate` → `parse_batch_response` ném đúng lớp lỗi này (đo
    được: `engine trả 100 mục, cần 135`), nên fake phải ném TỪ `translate` — một
    fake trả về danh sách ngắn chỉ chạm `check_alignment`, tức chạm một đường KHÁC
    với đường mà sản phẩm đi (xem ghi chú cùng loại ở `test_chimera.py`).
    """

    def __init__(self, limit: int, **kw):
        super().__init__(**kw)
        self.limit = limit
        self.raised = 0

    def translate(self, batch, glossary, opts):
        if len(batch) > self.limit:
            # Đường NÉM phải tự ghi `attempts`: `super().translate` là chỗ ghi bình
            # thường, và nó không chạy khi ta ném (ghi ở cả hai chỗ thì mỗi lần gọi
            # thành hai dòng, và phép đếm "hai lần thử mỗi lô" sẽ sai gấp đôi).
            self.attempts.append([s.i for s in batch])
            self.raised += 1
            ids = [s.i for s in batch]
            raise AlignmentProblem(
                ids, ids[: self.limit],
                f"engine trả {self.limit} mục, cần {len(batch)}")
        return super().translate(batch, glossary, opts)


def _big_transcript(repos, n=135):
    """Transcript `n` đoạn NGẮN — đúng hình dạng bản ghi thật.

    Tổng ký tự nhỏ hơn ngân sách 1200 nên KHÔNG có trần số mục thì cả bản ghi nằm
    trong MỘT lô — đó chính là cách lô 135 mục sinh ra trong sản phẩm.
    """
    sid = repos.add_source(kind="file", origin="big.mp4", media_path="/m/big.mp4")
    segs = [seg(i, f"câu {i}") for i in range(1, n + 1)]
    tid = repos.add_transcript(source_id=sid, engine="fw", lang="zh", segments=segs)
    return tid, segs


def test_a_big_transcript_is_split_by_the_item_budget(repos):
    """135 đoạn ngắn ⇒ NĂM lô ≤ `DEFAULT_MAX_ITEMS`, không phải một lô 135 mục."""
    from app.domain.mt import DEFAULT_MAX_ITEMS

    tid, _ = _big_transcript(repos)
    tr_id = _translation(repos, tid)
    engine = _RecordingInputs()
    _call(_handler(repos, engine), repos, tr_id, tid)

    sizes = [len(b) for b in engine.batches_seen]
    assert max(sizes) == DEFAULT_MAX_ITEMS, (
        f"không lô nào được vượt trần {DEFAULT_MAX_ITEMS} mục: {sizes}"
    )
    assert sizes == [DEFAULT_MAX_ITEMS] * 4 + [135 - 4 * DEFAULT_MAX_ITEMS], sizes
    got = repos.get_translation(tr_id)
    assert [s.i for s in got.segments] == list(range(1, 136)), "đủ 135 mục, đúng thứ tự"
    assert got.status == "done"


def test_the_measured_broken_batch_size_now_produces_every_item(repos):
    """Ca THẬT: engine chỉ trả đủ khi lô ≤ 64 mục ⇒ vẫn ra ĐỦ 135 mục.

    Trước bản vá, cả bản ghi là MỘT lô 135 mục > 64 nên adapter ném
    `AlignmentProblem` và (vì lỗi thứ hai) cả job `failed` ở 0 mục.
    """
    tid, _ = _big_transcript(repos)
    tr_id = _translation(repos, tid)
    engine = _RaisesAlignmentAbove(_MEASURED_GOOD_ITEMS)
    _call(_handler(repos, engine), repos, tr_id, tid)

    got = repos.get_translation(tr_id)
    assert [s.i for s in got.segments] == list(range(1, 136))
    assert got.status == "done"
    assert engine.raised == 0, (
        "trần số mục phải chặn lô 135 mục TRƯỚC khi engine kịp bỏ mục: "
        f"{engine.attempts}"
    )
    assert len(engine.attempts) == 5, engine.attempts


def test_an_alignment_problem_from_the_adapter_is_retried_then_falls_back(repos):
    """`AlignmentProblem` NÉM TỪ `translate` phải đi đúng chính sách ba bước.

    Engine ở đây lệch ở MỌI lô nhiều hơn một mục (đúng hình dạng "adapter tự
    parse rồi thấy thiếu"), nên đường đi phải là: thử cả lô (hỏng) → thử lại cả lô
    (hỏng) → hạ cấp từng segment → ĐỦ 135 mục, `done`.

    Mutant: bỏ nhánh `except AlignmentProblem` (để nó rơi vào `except Exception`)
    ⇒ `AlignmentProblem` nổi lên khỏi `translate`, hàng dịch thành `failed` với
    0 mục — ĐỎ đúng tên bài này.
    """
    tid, _ = _big_transcript(repos)
    tr_id = _translation(repos, tid)
    engine = _RaisesAlignmentAbove(1)
    _call(_handler(repos, engine), repos, tr_id, tid)

    got = repos.get_translation(tr_id)
    assert [s.i for s in got.segments] == list(range(1, 136))
    assert got.status == "done"
    assert engine.raised == 2 * 5, (
        "mỗi lô lớn phải được thử ĐÚNG hai lần trước khi hạ cấp: "
        f"raised={engine.raised}, attempts={len(engine.attempts)}"
    )
    singles = [b for b in engine.attempts if len(b) == 1]
    assert len(singles) == 135, f"hạ cấp phải chạm từng segment một: {len(singles)}"


class _RaisesMalformedAbove(FakeMtEngine):
    """Adapter trả phản hồi DỊ DẠNG khi lô vượt `limit` mục.

    `parse_batch_response` ném `ValueError` cho sáu hình dạng (khoá lạ, thiếu khoá,
    giá trị không phải chuỗi...), và ĐO ĐƯỢC trên lần chạy thật với `qwen2.5-7b`:
    model trả `{"i:": 277, "text": "…"}` — khoá `i:` thay vì `i` — làm job chết ở
    270/464 mục. Đó là hỏng CỦA MỘT LÔ, nên nó phải đi cùng đường với lệch mục.
    """

    def __init__(self, limit: int, **kw):
        super().__init__(**kw)
        self.limit = limit
        self.raised = 0

    def translate(self, batch, glossary, opts):
        if len(batch) > self.limit:
            self.attempts.append([s.i for s in batch])
            self.raised += 1
            raise ValueError(
                "mục thiếu 'i' hoặc 'text' không phải chuỗi: "
                f"{{'i:': {batch[0].i}, 'text': '...'}}")
        return super().translate(batch, glossary, opts)


def test_a_malformed_batch_response_is_retried_then_falls_back(repos):
    """`ValueError` CỦA MỘT LÔ (phản hồi dị dạng) không được giết cả bản dịch.

    Đo được: lần chạy thật `qwen2.5-7b` trên transcript #1 (464 đoạn) chết ở
    270/464 vì MỘT mục có khoá `i:` — `ValueError` nổi lên khỏi `translate` và
    không lô nào khác được thử. Sau bản vá: thử lại cả lô, rồi hạ cấp từng đoạn ⇒
    ĐỦ 135 mục.

    Mutant: bỏ `ValueError` khỏi nhánh `except` ⇒ `ValueError` nổi lên, hàng dịch
    `failed` ở 0 mục — ĐỎ đúng tên bài này.
    """
    tid, _ = _big_transcript(repos)
    tr_id = _translation(repos, tid)
    engine = _RaisesMalformedAbove(1)
    _call(_handler(repos, engine), repos, tr_id, tid)

    got = repos.get_translation(tr_id)
    assert [s.i for s in got.segments] == list(range(1, 136))
    assert got.status == "done"
    assert engine.raised == 2 * 5, (
        f"mỗi lô phải được thử ĐÚNG hai lần trước khi hạ cấp: raised={engine.raised}"
    )


def test_an_engine_that_answers_every_item_is_still_called_once_per_batch(repos):
    """ĐỐI CHỨNG ÂM: engine trả ĐỦ ⇒ không retry, không hạ cấp, không đổi gì khác.

    Chỉ có số lô là khác trước bản vá (5 lô thay vì 1), và đó là điều đã đo được
    là CẦN. Một bản vá "cứ hạ cấp cho chắc" sẽ đỏ ở đây: 135 lô một mục.
    """
    tid, _ = _big_transcript(repos)
    tr_id = _translation(repos, tid)
    engine = FakeMtEngine()
    _call(_handler(repos, engine), repos, tr_id, tid)

    assert engine.attempts == engine.calls, "không lần gọi nào được thử lại"
    assert len(engine.attempts) == 5, engine.attempts
    assert all(len(b) > 1 for b in engine.attempts), (
        f"không được hạ cấp khi engine trả đủ: {engine.attempts}"
    )
    assert [s.i for s in repos.get_translation(tr_id).segments] == list(range(1, 136))
