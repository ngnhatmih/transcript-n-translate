"""Kiểm alignment: engine phải trả ĐÚNG số segment, ĐÚNG id, ĐÚNG thứ tự.

Mọi engine LLM đều có lúc trả thiếu/thừa mục khi lô lớn. Nếu chỗ này không ném
lỗi thì bản dịch bị ghép lệch và phụ đề sai chỗ — hỏng âm thầm, không triệu chứng.
"""
import pytest

from app.domain.alignment import AlignmentProblem, check_alignment
from app.domain.models import Segment


def seg(i: int, text: str = "t") -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text)


def test_matching_ids_in_order_passes():
    check_alignment([seg(1), seg(2)], [seg(1, "vi1"), seg(2, "vi2")])


def test_missing_segment_raises_and_names_the_id():
    with pytest.raises(AlignmentProblem) as exc:
        check_alignment([seg(1), seg(2)], [seg(1, "vi1")])
    assert exc.value.expected_ids == [1, 2]
    assert exc.value.got_ids == [1]
    assert "2" in exc.value.reason


def test_extra_segment_raises():
    with pytest.raises(AlignmentProblem):
        check_alignment([seg(1)], [seg(1), seg(2)])


def test_wrong_order_raises():
    with pytest.raises(AlignmentProblem):
        check_alignment([seg(1), seg(2)], [seg(2), seg(1)])


def test_duplicate_id_raises():
    with pytest.raises(AlignmentProblem):
        check_alignment([seg(1), seg(2)], [seg(1), seg(1)])


def test_unknown_id_raises():
    with pytest.raises(AlignmentProblem):
        check_alignment([seg(1)], [seg(99)])


def test_empty_on_both_sides_passes():
    check_alignment([], [])


# ---------------------------------------------------------------------------
# Bài kiểm tính CHẤT: KHÔNG đường hỏng nào được rơi mất danh sách id.
#
# Task 11 bắt `AlignmentProblem` để quyết định thử lại cả lô hay dịch từng
# segment, và người đọc log phải biết nó ĐÃ NHẬN gì so với ĐÃ CẦN gì. Một
# `raise` chỉ có `reason` vẫn qua được bảy bài trên (chúng chỉ đòi đúng loại
# ngoại lệ), nên bài này ghim trường của ngoại lệ trên MỌI đường hỏng.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "src_ids, out_ids",
    [
        ([1, 2], [1]),        # thiếu ở cuối
        ([1, 2], [1, 2, 3]),  # thừa ở cuối
        ([1, 2, 3], [1, 3]),  # thiếu ở GIỮA lo
        ([1, 2], [2, 1]),     # cùng SỐ LƯỢNG, sai thứ tự
        ([1, 2], [1, 1]),     # nhân bản id
        ([1], [99]),          # id lạ
        ([], [1]),            # đầu vào rỗng mà ra vẫn có mục
        ([1], []),            # ra rỗng
    ],
)
def test_every_failure_path_reports_expected_and_got_ids(src_ids, out_ids):
    with pytest.raises(AlignmentProblem) as exc:
        check_alignment([seg(i) for i in src_ids], [seg(i) for i in out_ids])

    assert exc.value.expected_ids == src_ids
    assert exc.value.got_ids == out_ids
    assert isinstance(exc.value.reason, str) and exc.value.reason, (
        "reason rỗng thì log không nói được vì sao hỏng"
    )
