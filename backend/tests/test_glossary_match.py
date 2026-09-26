"""Glossary ảnh hưởng tới segment nào. Hàm thuần, test không cần model.

`affected_segments` so ÁNH XẠ thuật ngữ -> bản dịch, không chỉ so tập thuật ngữ:
đổi bản dịch của một thuật ngữ ĐANG xuất hiện cũng làm segment đó phải dịch lại.

Danh tính thuật ngữ là `term.strip().casefold()`, không phải `(lang, term)`.
Hai hàng khác nhau trong DB vẫn có thể cùng danh tính: khác hoa thường, khác
khoảng trắng đầu/cuối, hoặc cùng chữ ở hai ngôn ngữ. Và `affected_segments` chỉ
tính thuật ngữ ĐÃ DUYỆT: nháp không phải ràng buộc.
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


# --- F1: hai hàng glossary cùng danh tính `strip().casefold()` ----------------
# `UNIQUE(lang, term)` của schema KHÔNG chặn được: 'rồng' vs 'Rồng', 'rồng' vs
# ' rồng ', hoặc cùng chữ ở hai `lang` là những hàng khác nhau nhưng cùng danh
# tính với module này. Bản dịch của hàng bị che đổi thì segment vẫn phải dịch lại.

def test_affected_when_a_shadowed_duplicate_needle_translation_changes():
    segs = [seg(1, "con rồng bay")]
    old = [term("rồng", "long"), term("Rồng", "CASE-VARIANT")]
    new = [term("rồng", "long"), term("Rồng", "CASE-VARIANT-CHANGED")]
    assert affected_segments(segs, old, new) == [1]


def test_affected_when_a_shadowed_whitespace_variant_translation_changes():
    segs = [seg(1, "con rồng bay")]
    old = [term("rồng", "long"), term(" rồng ", "WS-VARIANT")]
    new = [term("rồng", "long"), term(" rồng ", "WS-VARIANT-CHANGED")]
    assert affected_segments(segs, old, new) == [1]


def test_affected_when_the_first_of_two_colliding_rows_translation_changes():
    """Hàng ĐẦU của cặp trùng danh tính đổi bản dịch.

    Đây là vế còn lại của F1: `terms_in` cho hàng đầu thắng, nên nếu ánh xạ giữ
    một giá trị duy nhất (last-wins) thì hàng sau che mất hàng đầu và sửa hàng
    đầu trả về `[]` — đúng false negative mà tập bản dịch tồn tại để chặn.
    """
    segs = [seg(1, "con rồng bay")]
    old = [term("rồng", "FIRST-ROW"), term("Rồng", "case-variant")]
    new = [term("rồng", "FIRST-ROW-CHANGED"), term("Rồng", "case-variant")]
    assert affected_segments(segs, old, new) == [1]


def test_terms_in_still_reports_one_term_for_duplicate_needles_first_wins():
    got = terms_in("con rồng bay", [term("rồng", "long"), term("Rồng", "CASE-VARIANT")])
    assert [t.term for t in got] == ["rồng"]


# --- F2: chỉ thuật ngữ ĐÃ DUYỆT mới là ràng buộc ------------------------------
# Header §8.1: glossary chưa duyệt là bản nháp. `terms_in` vẫn không lọc (Task 14
# cần danh sách thô), `affected_segments` lọc cả hai vế.

def test_affected_when_a_term_is_approved():
    segs = [seg(1, "con rồng")]
    old = [term("rồng", "long", ok=False)]
    new = [term("rồng", "long", ok=True)]
    assert affected_segments(segs, old, new) == [1]


def test_affected_when_a_term_is_unapproved():
    segs = [seg(1, "con rồng")]
    old = [term("rồng", "long", ok=True)]
    new = [term("rồng", "long", ok=False)]
    assert affected_segments(segs, old, new) == [1]


def test_unapproved_draft_edit_affects_nothing():
    segs = [seg(1, "con rồng"), seg(2, "con phượng")]
    old = [term("rồng", "long", ok=False)]
    new = [term("rồng", "CASE-DRAFT-EDIT", ok=False), term("phượng", "phoenix", ok=False)]
    assert affected_segments(segs, old, new) == []
