"""Chia segment thành lô cho một lần gọi engine dịch.

Ngân sách tính bằng KÝ TỰ của văn bản nguồn — đơn vị duy nhất mà mọi engine đều
có, kể cả OPUS-MT vốn không trả token count. Giá trị cụ thể đo rồi chốt ở spec §12.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Segment

#: Ngân sách mặc định. Số này là ĐIỂM KHỞI ĐẦU, không phải số đã tối ưu: spec §12
#: để ngỏ và Task 16 đo tỉ lệ lệch alignment theo kích thước lô rồi chốt lại.
DEFAULT_MAX_CHARS = 1200


def batch_segments(segments: list[Segment], *, max_chars: int) -> list[list[Segment]]:
    """Chia `segments` thành các lô liên tiếp, mỗi lô không quá `max_chars` ký tự.

    Một segment dài hơn ngân sách vẫn tạo một lô riêng chứa nó: bỏ nó đi là mất
    hẳn một dòng phụ đề.
    """
    if max_chars <= 0:
        raise ValueError(f"max_chars phải > 0, nhận {max_chars!r}")

    batches: list[list[Segment]] = []
    current: list[Segment] = []
    used = 0
    for s in segments:
        size = len(s.text)
        if current and used + size > max_chars:
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
