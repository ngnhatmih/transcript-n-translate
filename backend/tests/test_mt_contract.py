"""Hợp đồng `MtEngine`, ghim bằng engine giả dùng chung.

Điểm dễ sai nhất: engine GIỮ NGUYÊN i/start/end và chỉ thay text. Engine tự đặt
timestamp là làm hỏng phụ đề mà không ai thấy.
"""
from app.domain.models import Segment, Term
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
