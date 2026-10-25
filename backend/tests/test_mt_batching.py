"""Chia lô theo ký tự. Hàm thuần nên test được không cần model.

Bất biến quan trọng nhất: GHÉP các lô theo thứ tự phải bằng ĐÚNG đầu vào — không
mất segment, không nhân bản, không đổi thứ tự. Một lô rỗng hoặc một segment bị
bỏ sẽ làm bản dịch lệch phụ đề mà không ai thấy.
"""
import pytest

from app.domain.batching import MAX_SEGMENTS_PER_BATCH
from app.domain.models import Segment
from app.domain.mt import DEFAULT_MAX_CHARS, DEFAULT_MAX_ITEMS, batch_segments


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1.0, text=text)


def test_empty_input_gives_no_batches():
    assert batch_segments([], max_chars=10) == []


def test_single_segment_is_its_own_batch():
    s = seg(1, "xin chào")
    assert batch_segments([s], max_chars=100) == [[s]]


def test_segments_pack_until_the_budget_would_be_exceeded():
    a, b, c = seg(1, "a" * 5), seg(2, "b" * 5), seg(3, "c" * 5)
    assert batch_segments([a, b, c], max_chars=10) == [[a, b], [c]]


def test_a_segment_longer_than_the_budget_is_not_dropped():
    big = seg(1, "x" * 50)
    small = seg(2, "y")
    assert batch_segments([big, small], max_chars=10) == [[big], [small]]


def test_no_segment_is_lost_or_duplicated_or_reordered():
    segs = [seg(i, "t" * (i % 7 + 1)) for i in range(1, 40)]
    out = batch_segments(segs, max_chars=13)
    assert [s.i for batch in out for s in batch] == [s.i for s in segs]
    assert all(batch for batch in out), "không được có lô rỗng"


def test_non_positive_budget_is_rejected():
    with pytest.raises(ValueError):
        batch_segments([seg(1, "a")], max_chars=0)


def test_default_budget_is_a_positive_int():
    assert isinstance(DEFAULT_MAX_CHARS, int) and DEFAULT_MAX_CHARS > 0


# ---------------------------------------------------------------------------
# Bài kiểm tính CHẤT, không phải ví dụ: đúng một bất biến, quét nhiều ngân sách.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("max_chars", [1, 3, 7, 13, 50, 1200])
def test_concatenating_batches_reproduces_the_input_exactly(max_chars):
    """Ghép lô theo thứ tự == đầu vào, y hệt từng ĐỐI TƯỢNG segment.

    So `id()` chứ không chỉ so `i`: một hiện thực nhân bản segment rồi sửa bản
    sao vẫn giữ nguyên dãy `i` và sẽ lọt qua phép so khoá.

    Và so `text` với ảnh chụp TRƯỚC lời gọi: một hiện thực cắt `s.text` tại chỗ
    vẫn qua được mọi phép so đối tượng ở trên, nhưng làm hỏng chính segment của
    người gọi (segment trả về là cùng đối tượng, không phải bản sao).
    """
    segs = [seg(i, "t" * (i % 7 + 1)) for i in range(1, 40)]
    texts = [s.text for s in segs]
    out = batch_segments(segs, max_chars=max_chars)

    flat = [s for batch in out for s in batch]
    assert [s.i for s in flat] == [s.i for s in segs]
    assert [id(s) for s in flat] == [id(s) for s in segs]
    assert len(flat) == len(segs)
    assert [s.text for s in flat] == texts
    assert all(batch for batch in out), "không được có lô rỗng"

    for batch in out:
        # Chỉ một segment dài hơn ngân sách mới được phép vượt ngân sách, và khi
        # đó nó phải nằm một mình (không kéo segment nào khác vượt theo).
        if len(batch) > 1:
            assert sum(len(s.text) for s in batch) <= max_chars
        elif len(batch[0].text) <= max_chars:
            assert sum(len(s.text) for s in batch) <= max_chars


def test_every_segment_longer_than_the_budget_gets_its_own_batch():
    """Nhiều segment quá khổ liên tiếp: không cái nào bị bỏ, không cái nào bị gộp."""
    segs = [seg(i, "x" * 20) for i in range(1, 6)]
    out = batch_segments(segs, max_chars=10)
    assert out == [[s] for s in segs]


def test_empty_text_segment_is_not_dropped():
    """Segment văn bản RỖNG là đầu vào có thật: `models.py` gán mặc định `""` cho
    thiếu khoá `text`, `faster_whisper.py` trả `(raw.get("text") or "").strip()`.

    Nó vẫn phải có mặt, đúng thứ tự, đúng một lần, trong đúng một lô — bỏ nó là
    mất hẳn một dòng phụ đề mà không phép so nào khác nhìn thấy.
    """
    a, b, c = seg(1, ""), seg(2, "x"), seg(3, "")
    out = batch_segments([a, b, c], max_chars=10)

    flat = [s for batch in out for s in batch]
    assert [id(s) for s in flat] == [id(a), id(b), id(c)]
    assert len(out) == 1, "ba segment này phải nằm gọn trong đúng một lô"
    assert all(batch for batch in out), "không được có lô rỗng"


def test_negative_budget_is_rejected():
    with pytest.raises(ValueError):
        batch_segments([seg(1, "a")], max_chars=-1)


def test_packing_restarts_after_a_flush():
    """Sau mỗi lần xả lô, bộ đếm `used` phải reset về 0 rồi gói tiếp.

    Quên reset thì mọi segment sau lô đầu thành lô riêng: bản ghi 1000 segment
    × 40 ký tự gói đúng thành 34 lô nhưng thành 971 lô (28,6× số lần gọi engine)
    nếu không reset — nội dung vẫn ghép đúng nên không phép so "ghép lại == đầu
    vào" nào bắt được, chỉ có ví dụ vượt qua một lần xả lô này bắt được.
    """
    a, b, c, d, e = seg(1, "a" * 6), seg(2, "b" * 6), seg(3, "c"), seg(4, "d"), seg(5, "e")
    assert batch_segments([a, b, c, d, e], max_chars=6) == [[a], [b], [c, d, e]]


# ---------------------------------------------------------------------------
# Ngân sách SỐ MỤC — trần thứ hai, độc lập với ký tự (xem `mt.DEFAULT_MAX_ITEMS`).
# ---------------------------------------------------------------------------

def test_max_items_caps_the_number_of_items_per_batch():
    """Trần số mục: lô đầu tiên ĐẦY thì xả, dù còn thừa ngân sách ký tự."""
    segs = [seg(i, "x") for i in range(1, 8)]
    out = batch_segments(segs, max_chars=10_000, max_items=3)
    assert [len(b) for b in out] == [3, 3, 1]
    assert [s for batch in out for s in batch] == segs, "không mục nào bị mất/đổi thứ tự"


def test_max_items_never_drops_a_segment():
    """Trần số mục chỉ chặn việc GHÉP THÊM — không bao giờ bỏ mục, kể cả khi lô
    chỉ còn một chỗ và segment kế tiếp dài hơn ngân sách ký tự."""
    segs = [seg(1, "a" * 50), seg(2, "b"), seg(3, "c")]
    out = batch_segments(segs, max_chars=2, max_items=2)
    assert [s for batch in out for s in batch] == segs
    assert all(batch for batch in out)


def test_max_items_none_keeps_the_character_budget_alone():
    """`None` = hành vi CŨ (chỉ ký tự). Người gọi không quan tâm số mục không bị
    đổi hành vi âm thầm."""
    segs = [seg(i, "x") for i in range(1, 40)]
    assert batch_segments(segs, max_chars=10_000, max_items=None) == [segs]
    assert batch_segments(segs, max_chars=10_000) == [segs]


def test_non_positive_max_items_is_rejected():
    with pytest.raises(ValueError):
        batch_segments([seg(1, "a")], max_chars=10, max_items=0)
    with pytest.raises(ValueError):
        batch_segments([seg(1, "a")], max_chars=10, max_items=-3)


def test_default_item_budget_is_the_number_the_project_already_declared():
    """HAI con số cho CÙNG một khái niệm ("bao nhiêu mục thì lô quá to") phải là
    MỘT con số.

    `domain/batching.MAX_SEGMENTS_PER_BATCH` là chỗ dự án đã khai trần đó (kèm
    test riêng) nhưng cơ chế ấy CHƯA được nối vào đường dịch; trần thật của đường
    dịch nằm ở `mt.DEFAULT_MAX_ITEMS`. Bài này ghim ĐẲNG THỨC giữa hai chỗ, không
    ghim một literal: đổi một bên mà không đổi bên kia là ĐỎ.
    """
    assert DEFAULT_MAX_ITEMS == MAX_SEGMENTS_PER_BATCH
    assert isinstance(DEFAULT_MAX_ITEMS, int) and DEFAULT_MAX_ITEMS > 0


def test_default_item_budget_stays_under_the_measured_breaking_threshold():
    """Biên an toàn ĐO ĐƯỢC, ghim bằng QUAN HỆ: cỡ lô lớn nhất còn đo được là ĐỦ
    với `qwen2.5-7b` là 64 mục; trần phải ≤ một nửa của nó (xem
    `mt.DEFAULT_MAX_ITEMS`). 135 mục ⇒ model bỏ mục (`engine trả 100/101 mục,
    cần 135`)."""
    assert DEFAULT_MAX_ITEMS <= 64 // 2
