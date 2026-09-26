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
    max_len_ratio: float = 4.0     # dài hơn thế này là lan man / lặp


def _window(src: Segment, out: Segment) -> float:
    """Thời lượng dùng để tính CPS, tính bằng giây.

    Cửa sổ của BẢN DỊCH là thứ quyết định: đó là khoảng thời gian dòng chữ thật
    sự nằm trên màn hình, nên CPS phải đo trên nó. Segment nguồn không cứu được
    một bản dịch không có cửa sổ riêng, và cũng không nên: nếu engine trả
    `start == end` thì dòng phụ đề đó không có thời lượng hiển thị nào cả.

    Chỉ khi bản dịch có cửa sổ dương mới xét tới nguồn, và khi đó nguồn chỉ dùng
    để KẸP LÊN: một cửa sổ dài hơn thực tế làm CPS trông thấp giả tạo, nên lấy
    cửa sổ NGẮN hơn (bảo thủ hơn) giữa hai vế.

    Trả `0.0` khi bản dịch không có cửa sổ dương: CPS không đo được.
    """
    out_window = out.end - out.start
    if out_window <= 0:
        return 0.0
    src_window = src.end - src.start
    return min(out_window, src_window) if src_window > 0 else out_window


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
            # 0 giây là DỮ LIỆU HỎNG, không phải "hơi nhanh": dòng phụ đề không
            # có cửa sổ hiển thị thì không ai đọc được. Báo bất kể `max_cps`, và
            # báo thay vì để ZeroDivisionError giết cả job dịch. Chuỗi vẫn bắt
            # đầu bằng `cps:{id}=` như mọi issue CPS khác, kèm `0.0s` để người
            # đọc thấy ngay đây không phải một con số đo được.
            issues.append(f"cps:{s.i}=0.0s/{len(text)}c")
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
