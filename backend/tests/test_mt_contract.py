"""Hợp đồng `MtEngine`, ghim bằng engine giả dùng chung.

Điểm dễ sai nhất: engine GIỮ NGUYÊN i/start/end và chỉ thay text. Engine tự đặt
timestamp là làm hỏng phụ đề mà không ai thấy.
"""
import pytest

from app.domain.models import Segment, Term, Word
from app.domain.mt import MtOpts
from tests.fakes_mt import FakeMtEngine


def seg(i: int, text: str, *, start: float = 0.0) -> Segment:
    return Segment(i=i, start=start, end=start + 1.0, text=text,
                   words=None, speaker="S1")


def test_fake_preserves_identity_and_timing():
    eng = FakeMtEngine(mapping={"a": "A"})
    out = eng.translate([seg(5, "a", start=12.0)], [], MtOpts(source_lang="zh"))
    assert out[0].i == 5 and out[0].start == 12.0 and out[0].end == 13.0
    assert out[0].text == "A"


def test_fake_preserves_words_and_speaker():
    src = seg(1, "a", start=3.0)
    out = FakeMtEngine().translate([src], [], MtOpts(source_lang="zh"))
    assert out[0].speaker == "S1"


def test_fake_preserves_word_timestamps_identity_not_just_the_key():
    """`words` phải được GIỮ NGUYÊN, không chỉ giữ khoá.

    `seg()` ở trên luôn dựng `words=None`, nên một engine đổi `words=<có dữ liệu>`
    thành `None` vẫn lọt qua `test_fake_preserves_words_and_speaker` (đã đo: mutant
    `words=s.words` -> `words=None` sống sót, 7 passed). Word timestamp là thứ tầng
    giao diện dùng để tô từ đang đọc; mất nó là hỏng âm thầm. Bài này ghim bằng
    dữ liệu THẬT, và ghim cả `is not` để engine không được tráo sang list khác.
    """
    words = [Word(w="a", s=3.0, e=3.4), Word(w="b", s=3.4, e=4.0)]
    src = Segment(i=1, start=3.0, end=4.0, text="ab", words=words, speaker="S1")
    out = FakeMtEngine().translate([src], [], MtOpts(source_lang="zh"))
    assert out[0].words is words
    assert [(w.w, w.s, w.e) for w in out[0].words] == [("a", 3.0, 3.4), ("b", 3.4, 4.0)]
    assert out[0].text == "[vi]ab"
    assert out[0].to_json() == {**src.to_json(), "text": "[vi]ab"}


def test_fake_changes_only_text_across_all_thirteen_segment_fields():
    """I-1 của review Task 7: bản cũ dựng lại `Segment` bằng tay nên nuốt 7/13 field
    (`emotion`, `events`, `avg_logprob`, `no_speech_prob`, `qa`, `suspect`, `t`).

    Dựng ĐỦ 13 field rồi so `to_json()` đầy đủ của đầu vào với đầu ra: chỉ được
    khác `text`. Một fake *bịa* `qa`/`emotion` cũng chết ở đây, không chỉ fake làm mất.
    """
    words = [Word(w="a", s=3.0, e=3.4)]
    src = Segment(i=7, start=3.0, end=4.0, text="ab", words=words, emotion="neutral",
                  events=["music"], speaker="S1", avg_logprob=-0.31,
                  no_speech_prob=0.02, suspect=True, t="2026-09-26T00:00:00",
                  qa=["length:1=4.25"])
    out = FakeMtEngine().translate([src], [], MtOpts(source_lang="zh"))
    assert out[0].to_json() == {**src.to_json(), "text": "[vi]ab"}
    assert out[0].words is words


def test_fake_returns_exactly_one_output_per_input():
    eng = FakeMtEngine()
    batch = [seg(i, f"t{i}") for i in range(1, 6)]
    assert [s.i for s in eng.translate(batch, [], MtOpts(source_lang="zh"))] == [1, 2, 3, 4, 5]


def test_release_is_idempotent():
    eng = FakeMtEngine()
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    eng.release()
    eng.release()          # lần hai phải là no-op, không ném
    assert eng.release_count == 1


def test_fake_can_be_asked_to_break_alignment():
    eng = FakeMtEngine(drop_ids={2})
    out = eng.translate([seg(1, "a"), seg(2, "b")], [], MtOpts(source_lang="zh"))
    assert [s.i for s in out] == [1]


def test_fail_times_raises_exactly_n_times_then_succeeds():
    """I-3 của review Task 7: `fail_times` là công tắc DUY NHẤT để dựng lỗi theo
    kịch bản, mà không test nào chạm tới (mutant bỏ `self._fail_times -= 1` vẫn
    xanh). Ghim: hỏng ĐÚNG n lần rồi thành công.
    """
    eng = FakeMtEngine(fail_times=2)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    out = eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    assert [s.i for s in out] == [1]


def test_calls_counts_successes_while_attempts_counts_every_try():
    """I-3: `calls` chỉ ghi lô THÀNH CÔNG — sau 1 lần hỏng và 1 lần thành công nó
    chỉ có một phần tử, nên không đếm được số lần THỬ. `attempts` ghi MỌI lần gọi,
    kể cả lần hỏng: đó là thứ test retry của Task 11 cần.
    """
    eng = FakeMtEngine(fail_times=1)
    with pytest.raises(RuntimeError):
        eng.translate([seg(9, "a")], [], MtOpts(source_lang="zh"))
    eng.translate([seg(9, "a")], [], MtOpts(source_lang="zh"))
    assert eng.calls == [[9]]
    assert eng.attempts == [[9], [9]]


def test_engine_id_is_stable():
    assert FakeMtEngine().engine_id == "fake-mt"


def test_source_and_target_lang_reach_the_engine():
    eng = FakeMtEngine()
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh", target_lang="vi"))
    assert eng.last_opts == MtOpts(source_lang="zh", target_lang="vi")


def test_glossary_reaches_the_engine():
    """I-2 của review Task 7: fake nhận `glossary` rồi ném đi, trong khi
    `supports_glossary()` trả `True` — nên mọi test glossary viết trên nó không
    chứng minh được gì. Ghim danh sách đã duyệt có tới được engine không.
    """
    terms = [Term(id=1, lang="zh", term="源", translation="nguồn")]
    eng = FakeMtEngine()
    eng.translate([seg(1, "源")], terms, MtOpts(source_lang="zh"))
    assert eng.last_glossary == terms


def test_supports_glossary_is_reported():
    assert FakeMtEngine().supports_glossary() is True


def test_port_and_fake_declare_the_same_interface():
    """I-4 của review Task 7: KHÔNG tệp nào trong repo import `app.ports.mt`;
    `test_layer_boundary.py` chỉ `ast.parse` nên một thành viên bị đổi tên trong
    cổng vẫn xanh. `MtEngine` là `Protocol` nên Python KHÔNG kiểm lúc chạy.

    Cố tình KHÔNG thêm `@runtime_checkable`: nó chỉ kiểm sự HIỆN DIỆN (đúng thứ
    `dir()` đã cho) và lệch quy ước của `ports/asr.py`/`ports/governor.py`. Ghim
    bằng `dir()` như `test_repos_translations.py:269` và `test_repos.py:52`.
    """
    from app.ports.mt import MtEngine

    for name in ("engine_id", "supports_glossary", "translate", "release"):
        assert name in dir(MtEngine), f"cổng MtEngine thiếu {name}"
        assert hasattr(FakeMtEngine, name), f"fake thiếu {name}"
