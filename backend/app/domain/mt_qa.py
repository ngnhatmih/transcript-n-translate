"""QA tất định sau dịch: CPS, tỉ lệ độ dài, thuật ngữ bắt buộc.

Không tốn model nên chạy ở MỌI lần dịch. Đây là lớp bắt lỗi rẻ nhất; ngưỡng cụ
thể cho tiếng Việt còn để ngỏ (spec §12) và đo trên dữ liệu thật.

Issue dùng tiền tố ổn định để grep được trong `translations.qa_issues`:
`cps:` · `length:` · `missing_term:` · `empty:` · cờ trần `engine_no_glossary`.

Danh sách `glossary` truyền vào đã được lọc theo ngôn ngữ; `terms_in` KHÔNG lọc
`approved()` (Task 4 cố ý để bên gọi quyết định), nên ở đây lọc bằng `approved()`:
mục chưa duyệt là bản nháp của người dùng, không phải ràng buộc — buộc tội thiếu
một thuật ngữ chưa duyệt là báo lỗi cho một luật chưa hề được đặt ra.
"""
from __future__ import annotations

from dataclasses import dataclass

from .glossary_match import approved, terms_in
from .models import Segment, Term


@dataclass(frozen=True)
class QaLimits:
    max_cps: float = 21.0          # ký tự mỗi giây; trên ngưỡng là khó đọc
    min_len_ratio: float = 0.25    # bản dịch ngắn hơn thế này là cụt
    # ĐÚNG bằng `qa_rules.LENGTH_RATIO_MAX` (5.0), và cùng phép đo — giữ hai con
    # số này lệch nhau là tự mâu thuẫn. Số đo ghi ở `qa_rules.py:13-19`: fixture
    # 6 -> 26 ký tự = 4.33, nên 4.0 vẫn cờ nhầm một bản dịch đúng; 5.0 qua cả
    # hai fixture mà vẫn bắt được ca bịa/lặp (~159 lần).
    max_len_ratio: float = 5.0     # dài hơn thế này là lan man / lặp


def _window(src: Segment, out: Segment) -> float:
    """Thời lượng dùng để tính CPS, tính bằng giây: cửa sổ của segment NGUỒN.

    Cửa sổ NGUỒN là khoảng thời gian người xem thật sự thấy dòng dịch:
    `subtitle_format.to_srt/to_vtt/to_ass` ghi mốc `seg.start --> seg.end` của
    `segments` NGUỒN và chỉ tra bản dịch theo VỊ TRÍ (`subtitle_format.py:56-64`
    và `:71-78`; `pipeline/export.py:80` bắt `len(translations) ==
    len(transcript.segments)`). Đo CPS trên cửa sổ của chính bản dịch là đo một
    khoảng không ai thấy — cùng một dòng có thể bị tốc độ sai chỉ vì engine trả
    mốc thời gian khác.

    Cửa sổ bản dịch chỉ là DỰ PHÒNG khi cửa sổ nguồn không dương (dữ liệu nguồn
    hỏng): vẫn còn hơn là không đo được gì.

    Trả `0.0` chỉ khi CẢ HAI cửa sổ đều không dương — lúc đó CPS thật sự không
    đo được và bên gọi báo `nowindow` thay vì bịa ra một con số.
    """
    src_window = src.end - src.start
    if src_window > 0:
        return src_window
    return out.end - out.start


def qa_translation(src: list[Segment], out: list[Segment], *, glossary: list[Term],
                   supports_glossary: bool, limits: QaLimits = QaLimits()) -> list[str]:
    """Sinh danh sách issue. Rỗng nghĩa là không thấy vấn đề tất định nào.

    Giả định `check_alignment` đã chạy trước: `src` và `out` khớp id theo thứ tự.
    Segment có trong `src` mà thiếu ở `out` bị BỎ QUA chứ không báo: lúc đó là
    `check_alignment`/`TranslateHandler` phải nói, không phải QA.
    """
    issues: list[str] = []
    if not supports_glossary and glossary:
        # Thông tin, KHÔNG phải lỗi: engine này không có đường nào nhận glossary.
        # Cờ này thay cho mọi `missing_term:` — engine không nhận được ràng buộc
        # thì không thể bị buộc tội vi phạm nó. Một vấn đề, báo đúng một lần.
        issues.append("engine_no_glossary")

    required = approved(glossary)
    by_id = {s.i: s for s in out}
    for s in src:
        t = by_id.get(s.i)
        if t is None:
            continue
        text = t.text.strip()
        if not text:
            issues.append(f"empty:{s.i}")
            continue

        duration = _window(s, t)
        if duration <= 0:
            # KHÔNG có cửa sổ dương nào để đo (cả nguồn lẫn bản dịch đều <= 0):
            # đây là DỮ LIỆU HỎNG, không phải "hơi nhanh". Báo bất kể `max_cps`,
            # và báo thay vì để ZeroDivisionError giết cả job dịch. Chuỗi vẫn bắt
            # đầu bằng `cps:{id}=` như mọi issue CPS khác, nhưng ghi `nowindow`
            # kèm số ký tự: KHÔNG in một thời lượng chưa từng đo được (`0.0s` cho
            # một cửa sổ âm là con số bịa), và nói rõ đây không phải một tốc độ.
            issues.append(f"cps:{s.i}=nowindow/{len(text)}c")
        elif len(text) / duration > limits.max_cps:
            issues.append(f"cps:{s.i}={len(text) / duration:.1f}>{limits.max_cps}")

        # Mẫu số kẹp xuống 1: segment nguồn rỗng làm mọi bản dịch thành "quá dài"
        # với tỉ lệ vô hạn — đó là lỗi của dữ liệu nguồn, không phải của bản dịch.
        base = max(len(s.text.strip()), 1)
        ratio = len(text) / base
        if ratio < limits.min_len_ratio or ratio > limits.max_len_ratio:
            issues.append(f"length:{s.i}={ratio:.2f}")

        # Thuật ngữ bắt buộc phải XUẤT HIỆN trong bản dịch. So không phân biệt
        # hoa thường vì tiếng Việt viết hoa đầu câu là chuyện bình thường.
        if supports_glossary:
            lowered = text.casefold()
            for term in terms_in(s.text, required):
                if term.translation.strip().casefold() not in lowered:
                    issues.append(f"missing_term:{s.i}={term.term}->{term.translation}")
    return issues
