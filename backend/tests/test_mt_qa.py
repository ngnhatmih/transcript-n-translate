"""QA tất định trên bản dịch. Không tốn model, nên phải chạy ở mọi lần dịch.

Mỗi issue có tiền tố ổn định để grep được trong `translations.qa_issues`.
"""
from app.domain.models import Segment, Term
from app.domain.mt_qa import QaLimits, qa_translation


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
    src, out = [seg(1, "a")], [seg(1, "b", dur=0.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert any(i.startswith("cps:1=") for i in issues)


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
