"""Kế hoạch CHIA ĐÔI một lô bị chép nguyên chữ nguồn — hàm THUẦN.

Tệp này chỉ trả lời MỘT câu hỏi, không có engine, không có mạng, không có DB:
cho một lô đã biết là "bị chép" (hoặc không), phải làm gì tiếp — nhận, chia đôi,
hay hạ xuống từng mục — và các sub-batch đó theo THỨ TỰ nào. Tách khỏi driver
(`scripts/smoke_echo_halving.py`) để pin được bằng test không cần model.

Vì sao cần một kế hoạch THUẦN thay vì viết thẳng vào vòng lặp
    Phép đo này hỏi "có phải chép nguồn là CHẾ ĐỘ CỦA LÔ, nên chia lô là thoát
    được không". Câu trả lời chỉ có nghĩa nếu phép chia không làm MẤT hay NHÂN
    ĐÔI mục nào — một lô 30 mục chia 15/15 rồi 8/7 phải còn đúng 30 id, đúng thứ
    tự, để phép so "số lời gọi" và "số đoạn echo còn lại" còn so được với đối
    chứng (89 lần dịch lại, 78,85 s). Cùng lý do đó, `next_step` là hàm THUẦN:
    đầu vào chỉ là `(items, copied, depth, max_depth)` nên test đưa vào được một
    lô 30 giả và đòi đúng cây, không phải chạy model 5 GB để kiểm một phép chia.

Vì sao CHIA ĐÔI chứ không chia ba
    Lô 30 bị chép ở CẢ BA lô đủ 30 mục trong lượt đo sưởi (`29/30`, `30/30`,
    `30/30`; lô 25 mục cuối sạch) — tức ngưỡng kích thước, nếu có, nằm ĐÂU ĐÓ
    giữa 25 và 30, và chia đôi là phép chia rẻ nhất đi qua được mọi ngưỡng như
    vậy: 30 -> 15 -> 8 -> 4 -> 2 -> 1 là 5 tầng, còn chia ba cần 4 tầng nhưng mỗi
    tầng 3 lời gọi. Số đo quyết định ở `smoke_echo_halving.py`.

ĐO ĐƯỢC (lượt `20261019-echo-halving`, clip 115 đoạn, `hy-mt-1.5-7b`, prompt v0)
    Ở lô 30, **3/3** lời gọi bị chép (`29/30`, `30/30`, `30/30`). Ở 15 mục,
    **5/14** lời gọi bị chép (2/8 lô của lượt 15 thẳng + 3/6 nửa của lượt chia);
    ở 8 mục **1/2**; ở 4 mục **0/2**. Nghĩa là phép chia KHÔNG cắt ngang một
    ngưỡng: cùng kích thước 15 vừa sạch vừa chép, nên cây chia phải đi sâu tới 3
    tầng ở một lô, và tổng của cả clip là 24–25 lời gọi / 88,67–95,72 s — ÍT lời
    gọi hơn 89 singleton nhưng ĐẮT hơn về thời gian (78,91 s), vì mỗi lô bị vứt
    vẫn tốn một lời gọi 30 mục. `halves` vì thế là phép chia đúng để ĐO, không
    phải để ship.

Bất biến (test `tests/test_echo_halving.py` ghim từng cái)
    * `halves` giữ NGUYÊN thứ tự, và nửa ĐẦU nhận mục lẻ (15 -> 8/7) — cùng quy
      ước với `mt.batch_segments` (lô đầu đầy trước), nên lô 30 và lô 15 của cùng
      một clip chia ra cùng hình dạng;
    * mọi nhánh của `next_step` trả về các sub-batch mà phép nối chúng lại ĐÚNG
      bằng `items` đầu vào: không mất, không lặp;
    * chỉ có BA lý do để không chia nữa — lô sạch (`CLEAN`), lô MỘT mục (`SINGLETON`,
      không còn gì nhỏ hơn), và chạm trần `max_depth` (`DEPTH`, hạ xuống từng mục).
"""
from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")

#: Lô KHÔNG bị chép nguồn: nhận nguyên, không chia (0 lời gọi thêm).
CLEAN = "clean"
#: Lô bị chép và còn chia được: dịch lại hai nửa, theo thứ tự.
SPLIT = "split"
#: Lô MỘT mục bị chép: không còn lô nào nhỏ hơn, đây là chỗ hạ cấp cuối.
SINGLETON = "singleton"
#: Chạm trần độ sâu: hạ xuống từng mục (cùng hình dạng bước (b) của handler).
DEPTH = "depth"

#: Trần số tầng chia. Đo trên lô 30 mục: 30 -> 15 -> 8 -> 4 -> 2 -> 1 là **5**
#: tầng, nên 6 là van an toàn KHÔNG BAO GIỜ chạm trong lượt đo này — nó chỉ tồn
#: tại để một lỗi (ví dụ `halves` không thu nhỏ lô) không thành vòng lặp vô hạn.
MAX_DEPTH = 6


def halves(items: Sequence[T]) -> list[list[T]]:
    """Chia `items` thành hai nửa LIÊN TIẾP theo thứ tự, nửa đầu nhiều hơn khi lẻ.

    `30 -> 15/15`, `15 -> 8/7`, `7 -> 4/3`, `2 -> 1/1`. Không sắp xếp lại, không
    lọc: đây là phép chia theo VỊ TRÍ trong lô, nên id của mỗi nửa vẫn là một
    khoảng liên tiếp của lô gốc — đúng hình dạng `batch_segments` sinh ra.
    """
    mid = (len(items) + 1) // 2
    return [list(items[:mid]), list(items[mid:])]


def next_step(items: Sequence[T], *, copied: bool, depth: int,
              max_depth: int = MAX_DEPTH) -> tuple[str, list[list[T]]]:
    """Bước kế tiếp cho MỘT lô: `(hành động, các sub-batch theo thứ tự)`.

    `items` là danh sách id (hoặc Segment) của lô, `copied` là kết quả phép đo
    "lô này có bị chép nguyên chữ nguồn không", `depth` là số tầng đã chia TÍNH TỪ
    lô gốc (lô gốc = 0). Bốn nhánh, và chỉ bốn:

    * không chép -> `(CLEAN, [])`: không lời gọi thêm nào, đây là đường của phần
      lớn lô;
    * chép, còn một mục -> `(SINGLETON, [[mục]])`: "hạ cấp cuối" — bên gọi hoặc
      nhận bản dịch lẻ này, hoặc từ chối cả lô (`EchoProblem`);
    * chép, chạm `max_depth` -> `(DEPTH, [[mỗi mục một lô]])`: cùng đích với
      `SINGLETON` nhưng cho cả lô, dùng khi phép chia không còn được phép;
    * chép, còn chia được -> `(SPLIT, halves(items))`.

    `DEPTH` và `SINGLETON` trả về CÙNG một hình dạng (các lô một mục) chứ không
    trả `[]`: bên gọi phải dịch được từng mục đó, nếu không thì "hết đường chia"
    biến thành "bỏ lô" — đúng thứ mà cổng echo tồn tại để không xảy ra.
    """
    if not items:
        return CLEAN, []
    if not copied:
        return CLEAN, []
    if len(items) == 1:
        return SINGLETON, [list(items)]
    if depth >= max_depth:
        return DEPTH, [[item] for item in items]
    return SPLIT, halves(items)


def leaves(items: Sequence[T], *, max_depth: int = MAX_DEPTH) -> list[list[T]]:
    """Các lô LÁ của cây chia khi MỌI tầng đều bị chép — dùng cho test và cho báo cáo.

    Đây là câu trả lời cho "nếu model chép ở MỌI kích thước thì phép chia tốn bao
    nhiêu lời gọi": số lô lá = số mục, nên chi phí là 1 + 2 + 4 + ... + n/2 + n.
    Hàm THUẦN, không gọi model; `next_step` mới là thứ quyết định lúc chạy.
    """
    pending: list[tuple[list[T], int]] = [(list(items), 0)]
    found: list[list[T]] = []
    while pending:
        batch, depth = pending.pop()
        action, subs = next_step(batch, copied=True, depth=depth,
                                 max_depth=max_depth)
        if action == SPLIT:
            # Đẩy NGƯỢC để lấy ra theo đúng thứ tự trái -> phải.
            pending.extend((sub, depth + 1) for sub in reversed(subs))
        elif subs:
            found.extend(subs)
    return found
