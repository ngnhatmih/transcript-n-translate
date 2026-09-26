"""Glossary ảnh hưởng tới segment nào. Hàm thuần, test không cần model.

`affected_segments` so ÁNH XẠ thuật ngữ -> bản dịch, không chỉ so tập thuật ngữ:
đổi bản dịch của một thuật ngữ ĐANG xuất hiện cũng làm segment đó phải dịch lại.
"""
from app.domain.glossary_match import affected_segments, approved, terms_in
from app.domain.models import Segment, Term


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text)


def term(t: str, tr: str, *, ok: bool = True) -> Term:
    return Term(id=None, lang="zh", term=t, translation=tr, approved=ok)


def test_approved_filters_unapproved():
    assert [t.term for t in approved([term("a", "A"), term("b", "B", ok=False)])] == ["a"]


def test_terms_in_is_case_insensitive_substring():
    got = terms_in("Con Rồng bay", [term("rồng", "dragon"), term("phượng", "phoenix")])
    assert [t.term for t in got] == ["rồng"]


def test_terms_in_ignores_empty_term():
    assert terms_in("abc", [term("", "x")]) == []


def test_terms_in_reports_each_term_once_in_glossary_order():
    terms = [term("a", "A"), term("b", "B")]
    got = terms_in("a b a", terms)
    assert [t.term for t in got] == ["a", "b"]


def test_affected_is_empty_when_glossary_unchanged():
    segs = [seg(1, "con rồng")]
    g = [term("rồng", "dragon")]
    assert affected_segments(segs, g, g) == []


def test_affected_when_a_new_term_now_appears():
    segs = [seg(1, "con rồng"), seg(2, "con phượng")]
    old = [term("rồng", "dragon")]
    new = [term("rồng", "dragon"), term("phượng", "phoenix")]
    assert affected_segments(segs, old, new) == [2]


def test_affected_when_a_translation_changes_for_a_present_term():
    segs = [seg(1, "con rồng")]
    old = [term("rồng", "dragon")]
    new = [term("rồng", "long")]
    assert affected_segments(segs, old, new) == [1]


def test_affected_when_a_term_is_removed():
    segs = [seg(1, "con rồng")]
    old = [term("rồng", "dragon")]
    assert affected_segments(segs, old, []) == [1]


def test_a_term_not_present_anywhere_affects_nothing():
    segs = [seg(1, "con rồng")]
    assert affected_segments(segs, [], [term("phượng", "phoenix")]) == []
