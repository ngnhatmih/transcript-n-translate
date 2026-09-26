"""Chia lô theo ký tự. Hàm thuần nên test được không cần model.

Bất biến quan trọng nhất: GHÉP các lô theo thứ tự phải bằng ĐÚNG đầu vào — không
mất segment, không nhân bản, không đổi thứ tự. Một lô rỗng hoặc một segment bị
bỏ sẽ làm bản dịch lệch phụ đề mà không ai thấy.
"""
import pytest

from app.domain.models import Segment
from app.domain.mt import DEFAULT_MAX_CHARS, batch_segments


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
    """
    segs = [seg(i, "t" * (i % 7 + 1)) for i in range(1, 40)]
    out = batch_segments(segs, max_chars=max_chars)

    flat = [s for batch in out for s in batch]
    assert [s.i for s in flat] == [s.i for s in segs]
    assert [id(s) for s in flat] == [id(s) for s in segs]
    assert len(flat) == len(segs)
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


def test_negative_budget_is_rejected():
    with pytest.raises(ValueError):
        batch_segments([seg(1, "a")], max_chars=-1)
