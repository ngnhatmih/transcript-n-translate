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


@dataclass(frozen=True)
class CpsRow:
    """CPS của MỘT đoạn dịch, dạng SỐ — không phải một chuỗi hiển thị.

    Vì sao tách khỏi `qa_translation`: chuỗi `cps:` trong `translations.qa_issues`
    VÀ con số mà `GET /api/translations/{id}` trả cho màn Đối chiếu phải là CÙNG một
    đại lượng. Hai chỗ tính CPS là hai chỗ trôi khỏi nhau — đúng lớp lỗi mà spec
    frontend §2 dựng ra để chặn. Cả hai đi qua `cps_row` dưới đây.

    `cps is None` nghĩa là KHÔNG ĐO ĐƯỢC (cả cửa sổ nguồn lẫn cửa sổ bản dịch đều
    không dương). Khác hẳn `0.0` (một tốc độ thật bằng không), và khác `inf`: đó là
    DỮ LIỆU HỎNG, không phải "hơi nhanh". `chars` vẫn có để nói được đã đếm bao
    nhiêu ký tự — theo đúng cách nhánh `nowindow` của `qa_translation` đã làm.
    """

    i: int
    #: `len(text.strip())` — CÙNG định nghĩa với con số trong chuỗi `cps:`.
    chars: int
    #: Cửa sổ NGUỒN (dự phòng: cửa sổ bản dịch), giây.
    window: float
    #: `None` = không đo được.
    cps: float | None
    max_cps: float
    over: bool


def cps_row(src: Segment, out: Segment, *,
            limits: QaLimits = QaLimits()) -> CpsRow:
    """CHỖ DUY NHẤT tính CPS.

    `out` là đoạn DỊCH (bên được đo), `src` là đoạn nguồn cùng `i` (bên cho cửa sổ
    thời gian). Gọi `cps_row(t, t)` khi không có đoạn nguồn tương ứng: cửa sổ nguồn
    bằng 0 nên `_window` tự rơi về cửa sổ bản dịch — đúng quy tắc dự phòng đã có,
    không phải một quy tắc mới.

    `over` so trên giá trị CHƯA làm tròn. Đó là lý do nó phải đi kèm con số ra
    ngoài: một client tự so `cps` (đã làm tròn để hiển thị) với `max_cps` sẽ nói
    SAI ở đúng biên (21,04 CPS hiển thị là 21,0).
    """
    text = out.text.strip()
    window = _window(src, out)
    if window <= 0:
        return CpsRow(i=out.i, chars=len(text), window=window, cps=None,
                      max_cps=limits.max_cps, over=False)
    cps = len(text) / window
    return CpsRow(i=out.i, chars=len(text), window=window, cps=cps,
                  max_cps=limits.max_cps, over=cps > limits.max_cps)


def cps_issue(row: CpsRow) -> str | None:
    """Chuỗi `cps:` cho `qa_issues`, sinh TỪ CÙNG dữ liệu với con số của route.

    Trả `None` khi đoạn đó không có gì để báo (đo được và không vượt ngưỡng).
    Định dạng giữ nguyên y như trước khi tách hàm — nó là hợp đồng grep được.

    Nhánh `nowindow` ghi SỐ KÝ TỰ chứ không ghi một thời lượng: `0.0s` cho một cửa
    sổ âm là con số bịa, và in `inf` thì `json.dumps` ném `ValueError: Out of range
    float values are not JSON compliant`. Báo như thế này thay vì để phép chia giết
    cả job dịch.
    """
    if row.cps is None:
        return f"cps:{row.i}=nowindow/{row.chars}c"
    if row.over:
        return f"cps:{row.i}={row.cps:.1f}>{row.max_cps}"
    return None


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

        # CPS: hình dạng chuỗi do `cps_issue` quyết, con số do `cps_row` tính —
        # CÙNG một chỗ với con số mà `GET /api/translations/{id}` trả ra.
        issue = cps_issue(cps_row(s, t, limits=limits))
        if issue is not None:
            issues.append(issue)

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
