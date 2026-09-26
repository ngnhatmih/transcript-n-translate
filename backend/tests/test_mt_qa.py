"""QA tất định trên bản dịch. Không tốn model, nên phải chạy ở mọi lần dịch.

Mỗi issue có tiền tố ổn định để grep được trong `translations.qa_issues`.
"""
from app.domain.models import Segment, Term
from app.domain.mt_qa import QaLimits, qa_translation
from app.domain.qa_rules import LENGTH_RATIO_MAX


def seg(i: int, text: str, *, dur: float = 1.0) -> Segment:
    return Segment(i=i, start=0.0, end=dur, text=text)


def term(t: str, tr: str) -> Term:
    return Term(id=None, lang="zh", term=t, translation=tr, approved=True)


LIMITS = QaLimits(max_cps=10.0, min_len_ratio=0.5, max_len_ratio=2.0)


def test_clean_translation_reports_nothing():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con rồng")]
    assert qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS) == []


def test_cps_over_limit_is_reported_with_the_id():
    src, out = [seg(1, "a")], [seg(1, "x" * 30, dur=1.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert any(i.startswith("cps:1=") for i in issues), issues


def test_zero_duration_does_not_divide_by_zero():
    """F2: cửa sổ NGUỒN là cửa sổ `subtitle_format` thật sự ghi ra, nên nguồn
    1.0s + bản dịch 0.0s vẫn là một dòng đọc được — không phải vấn đề. Chỉ khi
    CẢ HAI vế không dương mới không đo được CPS, và lúc đó báo `nowindow`."""
    # nguồn 1.0s, bản dịch 0.0s -> đo trên nguồn -> dòng "b" trong 1.0s là ổn
    src, out = [seg(1, "a")], [seg(1, "b", dur=0.0)]
    assert qa_translation(src, out, glossary=[], supports_glossary=True,
                          limits=LIMITS) == []
    # cả hai vế 0.0s -> không có cửa sổ dương nào -> báo, và KHÔNG chia 0
    src0, out0 = [seg(1, "a", dur=0.0)], [seg(1, "b", dur=0.0)]
    issues = qa_translation(src0, out0, glossary=[], supports_glossary=True,
                            limits=LIMITS)
    assert issues == ["cps:1=nowindow/1c"]


def test_too_short_and_too_long_translations_are_reported():
    src = [seg(1, "x" * 10)]
    short = [seg(1, "y")]
    long_ = [seg(1, "z" * 40)]
    assert any(i.startswith("length:1=") for i in
               qa_translation(src, short, glossary=[], supports_glossary=True, limits=LIMITS))
    assert any(i.startswith("length:1=") for i in
               qa_translation(src, long_, glossary=[], supports_glossary=True, limits=LIMITS))


def test_missing_required_term_is_reported():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con rong")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=True, limits=LIMITS)
    assert any(i.startswith("missing_term:1=") for i in issues), issues


def test_present_required_term_is_not_reported():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con rồng lớn")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=True, limits=LIMITS)
    assert not any(i.startswith("missing_term:") for i in issues)


def test_engine_without_glossary_support_gets_a_flag_not_a_missing_term():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con dragon")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=False, limits=LIMITS)
    assert "engine_no_glossary" in issues
    assert not any(i.startswith("missing_term:") for i in issues), \
        "engine không hỗ trợ glossary thì không được buộc tội thiếu thuật ngữ"


def test_empty_translated_text_is_reported():
    src, out = [seg(1, "con rồng")], [seg(1, "   ")]
    assert any(i.startswith("empty:1") for i in
               qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS))


# --- Fix round 1 -----------------------------------------------------------
# F1: ngưỡng độ dài ship ra phải là số repo đã ĐO, không phải 4.0 đã đo là sai.


def test_default_max_len_ratio_is_the_measured_qa_rules_value():
    """F1: `qa_rules` đo cùng phép đo và ship 5.0 (fixture 6 -> 26 = 4.33, nên
    4.0 cờ nhầm bản dịch đúng). Ghim ngưỡng từ CẢ HAI phía: 4.99 phải qua,
    5.01 phải bị bắt."""
    assert QaLimits().max_len_ratio == LENGTH_RATIO_MAX == 5.0

    src = [seg(1, "x" * 100, dur=1000.0)]
    under = [seg(1, "y" * 499, dur=1000.0)]     # 4.99 -> qua
    over = [seg(1, "y" * 501, dur=1000.0)]      # 5.01 -> bắt
    assert qa_translation(src, under, glossary=[], supports_glossary=True,
                          limits=QaLimits()) == []
    assert qa_translation(src, over, glossary=[], supports_glossary=True,
                          limits=QaLimits()) == ["length:1=5.01"]


# F2: CPS đo trên cửa sổ được HIỂN THỊ — cửa sổ nguồn.


def test_cps_uses_the_source_window_not_the_translation_window():
    """F2: `subtitle_format` ghi mốc thời gian NGUỒN và tra bản dịch theo vị trí,
    nên cửa sổ người xem thấy là cửa sổ nguồn. Nguồn 1.0s / bản dịch 3.0s: đo
    trên cửa sổ bản dịch thì 20 ký tự = 6.7 cps (im lặng), đo trên cửa sổ nguồn
    mới là 20.0 cps > 10.0 -> phải báo."""
    src = [seg(1, "x" * 20, dur=1.0)]
    out = [Segment(i=1, start=0.0, end=3.0, text="y" * 20)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert issues == ["cps:1=20.0>10.0"]


def test_cps_falls_back_to_the_translation_window_when_the_source_has_none():
    """F2: cửa sổ nguồn không dương là dữ liệu nguồn hỏng — vẫn còn cửa sổ bản
    dịch để đo thật, nên KHÔNG được báo `nowindow`."""
    src = [seg(1, "x" * 30, dur=0.0)]
    out = [Segment(i=1, start=0.0, end=1.0, text="y" * 30)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert issues == ["cps:1=30.0>10.0"]


# F3 + các survivor M6/M1b/M14/M16/M7/M8.


def test_only_approved_terms_are_required():
    """F3/M6: chỉ glossary ĐÃ DUYỆT mới là ràng buộc (design §8). Mục CHƯA DUYỆT
    là bản nháp của người dùng, thiếu nó không phải lỗi; mục đã duyệt thì phải
    báo."""
    src, out = [seg(1, "con rồng")], [seg(1, "con rong")]
    draft = Term(id=None, lang="zh", term="rồng", translation="rồng", approved=False)
    ok = Term(id=None, lang="zh", term="rồng", translation="rồng", approved=True)
    assert qa_translation(src, out, glossary=[draft], supports_glossary=True,
                          limits=LIMITS) == []
    assert qa_translation(src, out, glossary=[ok], supports_glossary=True,
                          limits=LIMITS) == ["missing_term:1=rồng->rồng"]


def test_no_glossary_flag_when_there_is_no_glossary_to_miss():
    """F3/M1b: cờ `engine_no_glossary` thay cho việc buộc tội thiếu thuật ngữ.
    Glossary rỗng thì engine không bỏ lỡ gì cả, nên không có cờ."""
    src, out = [seg(1, "con rồng")], [seg(1, "con rồng")]
    assert qa_translation(src, out, glossary=[], supports_glossary=False,
                          limits=LIMITS) == []


def test_empty_translation_reports_exactly_one_issue():
    """F3/M14: "một vấn đề, báo đúng một lần" — dòng ra rỗng chỉ được báo
    `empty:`, không kèm `length:1=0.00` và `missing_term:` cho cùng một lỗi."""
    src, out = [seg(1, "con rồng")], [seg(1, "   ")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=True, limits=LIMITS)
    assert issues == ["empty:1"]


def test_empty_source_text_does_not_divide_by_zero():
    """F3/M16: segment nguồn rỗng là dữ liệu nguồn hỏng. Mẫu số kẹp xuống 1 để
    tỉ lệ không thành vô hạn và không ZeroDivisionError."""
    src, out = [seg(1, "")], [seg(1, "con rồng")]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert issues == ["length:1=8.00"]
