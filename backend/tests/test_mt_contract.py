"""Hợp đồng `MtEngine`, ghim bằng engine giả dùng chung.

Điểm dễ sai nhất: engine GIỮ NGUYÊN i/start/end và chỉ thay text. Engine tự đặt
timestamp là làm hỏng phụ đề mà không ai thấy.
"""
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


def test_source_and_target_lang_reach_the_engine():
    eng = FakeMtEngine()
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh", target_lang="vi"))
    assert eng.last_opts == MtOpts(source_lang="zh", target_lang="vi")


def test_supports_glossary_is_reported():
    assert FakeMtEngine().supports_glossary() is True
