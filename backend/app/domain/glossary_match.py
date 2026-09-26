"""Thuật ngữ glossary xuất hiện ở đâu, và glossary đổi thì segment nào phải dịch lại.

Chỉ thuật ngữ ĐÃ DUYỆT mới đi vào prompt và mới tính là ảnh hưởng — spec §8.1 và
§5. Glossary chưa duyệt là bản nháp của người dùng, không phải ràng buộc.
"""
from __future__ import annotations

from .models import Segment, Term


def approved(terms: list[Term]) -> list[Term]:
    return [t for t in terms if t.approved]


def terms_in(text: str, terms: list[Term]) -> list[Term]:
    """Các thuật ngữ nguồn xuất hiện trong `text`, theo thứ tự glossary.

    So khớp không phân biệt hoa thường. Thuật ngữ rỗng bị bỏ qua: chuỗi rỗng là
    chuỗi con của MỌI văn bản, nên nhận nó là nói mọi segment đều bị ảnh hưởng.
    """
    haystack = text.casefold()
    out: list[Term] = []
    seen: set[str] = set()
    for t in terms:
        needle = t.term.strip().casefold()
        if not needle or needle in seen:
            continue
        if needle in haystack:
            out.append(t)
            seen.add(needle)
    return out


def _mapping(segments: list[Segment], terms: list[Term]) -> dict[int, dict[str, str]]:
    return {s.i: {t.term.casefold(): t.translation for t in terms_in(s.text, terms)}
            for s in segments}


def affected_segments(segments: list[Segment], old: list[Term],
                      new: list[Term]) -> list[int]:
    """Id của các segment mà ÁNH XẠ thuật ngữ -> bản dịch đã đổi.

    So ánh xạ chứ không so tập thuật ngữ: đổi bản dịch của một thuật ngữ ĐANG
    xuất hiện làm bản dịch cũ sai, nên segment đó phải dịch lại.
    """
    before, after = _mapping(segments, old), _mapping(segments, new)
    return [s.i for s in segments if before[s.i] != after[s.i]]
