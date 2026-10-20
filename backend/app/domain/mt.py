"""Chia segment thành lô cho một lần gọi engine dịch.

Ngân sách tính bằng KÝ TỰ của văn bản nguồn — đơn vị duy nhất mà mọi engine đều
có, kể cả OPUS-MT vốn không trả token count. Giá trị cụ thể đo rồi chốt ở spec §12.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Segment

#: Ngân sách ký tự mặc định. Số này là ĐIỂM KHỞI ĐẦU, không phải số đã tối ưu:
#: spec §12 để ngỏ và Task 16 đo tỉ lệ lệch alignment theo kích thước lô rồi chốt lại.
DEFAULT_MAX_CHARS = 1200

#: Số MỤC tối đa cho MỘT lời gọi engine — ngân sách thứ hai, độc lập với ký tự.
#:
#: Vì sao cần (đo trên bản ghi THẬT `data/app.db`, engine `qwen2.5-7b`, 464 đoạn,
#: lô đầu 135 mục / 1199 ký tự): ngân sách KÝ TỰ không chặn được lô 135 mục, vì
#: đoạn phụ đề thật rất ngắn (trung bình 8,6 ký tự). Đo N mục vào / N mục ra của
#: một lời gọi thật: 1→1, 4→4, 8→8, 16→16, 32→32, 64→64, **135→100** (model trả
#: 100/101 mục ở ba lần chạy khác nhau) — model BỎ MỤC khi danh sách quá dài, và
#: `prompts.py` ném `AlignmentProblem: engine trả 101 mục, cần 135`. Ngưỡng gãy đo
#: được nằm giữa 64 và 135, nên trần phải ≤ một nửa cỡ lớn nhất còn đo được là ĐỦ
#: (64/2 = 32) để chừa biên cho prompt dài hơn (glossary, chỉ dẫn thêm) và cho
#: engine khác. **30** là giá trị đã được dự án khai cho ĐÚNG rủi ro này ở
#: `domain/batching.MAX_SEGMENTS_PER_BATCH` — cơ chế đó có test nhưng CHƯA được nối
#: vào đường dịch, nên nếu ở đây đặt một con số thứ hai thì hai chỗ khai cùng một
#: khái niệm sẽ trôi khỏi nhau. `tests/test_mt_batching.py` ghim ĐẲNG THỨC đó.
#:
#: Trần này KHÔNG thay phép kiểm alignment: nó chỉ làm lô nhỏ hơn. Một lô vẫn có
#: thể lệch (engine khác, prompt khác), và khi đó chính sách ba bước của
#: `TranslateHandler` vẫn là thứ bảo đảm đầu ra đủ mục — hoặc hỏng RÕ RÀNG.
DEFAULT_MAX_ITEMS = 30


def batch_segments(segments: list[Segment], *, max_chars: int,
                   max_items: int | None = None) -> list[list[Segment]]:
    """Chia `segments` thành các lô liên tiếp theo HAI ngân sách.

    `max_chars` là ngân sách KÝ TỰ và `max_items` là ngân sách SỐ MỤC; lô đầu
    tiên chạm ngân sách nào cũng bị xả. `max_items=None` = chỉ dùng ký tự (giữ
    nguyên hành vi cũ cho người gọi không quan tâm số mục — trần số mục là
    chính sách của `TranslateHandler`, xem `DEFAULT_MAX_ITEMS`).

    Một segment dài hơn ngân sách ký tự vẫn tạo một lô riêng chứa nó: bỏ nó đi là
    mất hẳn một dòng phụ đề. `max_items` chỉ chặn việc GHÉP THÊM, không bao giờ
    bỏ mục — nên ghép các lô theo thứ tự vẫn bằng ĐÚNG đầu vào.
    """
    if max_chars <= 0:
        raise ValueError(f"max_chars phải > 0, nhận {max_chars!r}")
    if max_items is not None and max_items <= 0:
        raise ValueError(f"max_items phải > 0 hoặc None, nhận {max_items!r}")

    batches: list[list[Segment]] = []
    current: list[Segment] = []
    used = 0
    for s in segments:
        size = len(s.text)
        full_items = max_items is not None and len(current) >= max_items
        if current and (used + size > max_chars or full_items):
            batches.append(current)
            current, used = [], 0
        current.append(s)
        used += size
    if current:
        batches.append(current)
    return batches


@dataclass(frozen=True)
class MtOpts:
    """Tham số của một lần gọi engine. Bất biến, nên so sánh được trong test.

    `temperature` là tham số THẬT của lượt gọi, không phải một cờ trang trí:
    `OllamaMtEngine` gửi nó trong `options` của `/api/chat`. Nó tồn tại vì chế độ
    Chimera (§8.7.5) cần N ứng viên KHÁC NHAU từ cùng một model — ở một nhiệt độ
    cố định thì sáu lời gọi cho ra sáu bản gần như giống hệt nhau, và lượt "pha"
    không còn gì để pha. `None` = dùng mặc định của adapter (`_TEMPERATURE`).

    Hai trường `merge_*` CHỈ có nghĩa với adapter của lượt PHA
    (`adapters/mt/chimera_merge.py`); mọi adapter khác bỏ qua chúng. Chúng nằm ở
    ĐÂY — chứ không thành một tham số riêng của `translate` — vì như vậy lượt pha
    đi qua ĐÚNG `TranslateHandler._translate_batch`: cùng chính sách alignment,
    cùng đường retry, và cùng MỘT hàng `llm_calls` cho mỗi lần chạm engine
    (spec §4.2). Một đường gọi thứ hai cho lượt pha là đường thứ hai để những thứ
    đó trôi khỏi nhau.
    """
    source_lang: str
    target_lang: str = "vi"
    temperature: float | None = None
    #: `((id_ứng_viên, (Segment, ...)), ...)` — CHỈ lượt pha đọc.
    merge_candidates: tuple = ()
    #: `id` của ứng viên MỎ NEO — CHỈ lượt pha đọc.
    merge_anchor: str | None = None
