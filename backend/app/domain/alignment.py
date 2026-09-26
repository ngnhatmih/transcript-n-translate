"""Bất biến alignment của một lô dịch.

Engine nhận `list[Segment]` và PHẢI trả về đúng bấy nhiêu `Segment`, cùng `i`,
cùng thứ tự. Adapter nào không bảo đảm được thì ném `AlignmentProblem` ở đây,
chứ KHÔNG trả về một list ngắn hơn: list ngắn là đúng kiểu thất bại âm thầm làm
lệch phụ đề.

`AlignmentProblem` là loại thất bại DUY NHẤT mà module này sinh ra. Bên gọi
(Task 11) bắt riêng nó để quyết định thử lại cả lô hay lùi về dịch từng segment;
một `ValueError` lọt ra từ đây sẽ rơi vào nhánh xử lý khác và mất khả năng đó.
"""
from __future__ import annotations

from .models import Segment


class AlignmentProblem(Exception):
    """Số lượng / id / thứ tự của kết quả engine không khớp đầu vào.

    `expected_ids` và `got_ids` được điền trên MỌI đường hỏng, không chỉ đường
    lệch số lượng: người đọc log cần biết engine ĐÃ NHẬN gì so với ĐÃ CẦN gì, và
    một ngoại lệ chỉ có `reason` thì không nói được điều đó.
    """

    def __init__(self, expected_ids: list[int], got_ids: list[int], reason: str) -> None:
        super().__init__(reason)
        self.expected_ids = expected_ids
        self.got_ids = got_ids
        self.reason = reason


def check_alignment(src: list[Segment], out: list[Segment]) -> None:
    """Ném `AlignmentProblem` trừ khi `[s.i for s in out] == [s.i for s in src]`."""
    expected = [s.i for s in src]
    got = [s.i for s in out]

    if len(got) != len(expected):
        missing = [i for i in expected if i not in got]
        extra = [i for i in got if i not in expected]
        detail = []
        if missing:
            detail.append(f"thiếu id {missing}")
        if extra:
            detail.append(f"thừa id {extra}")
        raise AlignmentProblem(
            expected, got,
            f"engine trả {len(got)} mục, cần {len(expected)}" + (f" ({'; '.join(detail)})" if detail else ""),
        )
    if got != expected:
        raise AlignmentProblem(expected, got, f"thứ tự/id sai: nhận {got}, cần {expected}")
