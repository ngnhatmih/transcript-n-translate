"""Thuật ngữ glossary xuất hiện ở đâu, và glossary đổi thì segment nào phải dịch lại.

Chỉ thuật ngữ ĐÃ DUYỆT mới đi vào prompt và mới tính là ảnh hưởng — spec §8.1 và
§5. Glossary chưa duyệt là bản nháp của người dùng, không phải ràng buộc.

`affected_segments` tự gọi `approved()` trên CẢ HAI vế: đổi một mục từ nháp thành
duyệt là thêm một ràng buộc, còn bỏ duyệt là gỡ một ràng buộc — cả hai đều làm
bản dịch cũ sai. `terms_in` thì KHÔNG lọc, vì Task 14 cần danh sách thô để so
`old` với `new`; lọc là việc của bên gọi.

Danh sách truyền vào phải đã lọc theo ngôn ngữ (`list_terms(lang=…)`): mặc định
của port là MỌI ngôn ngữ, và cùng một chữ ở hai ngôn ngữ là hai danh tính.
"""
from __future__ import annotations

from .models import Segment, Term


def approved(terms: list[Term]) -> list[Term]:
    return [t for t in terms if t.approved]


def key(t: Term) -> str:
    """Danh tính của một thuật ngữ nguồn: `strip().casefold()`.

    MỘT nguồn duy nhất cho cả `terms_in` lẫn `_mapping`. Hai bên dùng hai cách
    chuẩn hoá khác nhau thì module này tự mâu thuẫn: `terms_in` nói "cùng một
    thuật ngữ" còn `_mapping` nói "đã đổi".
    """
    return t.term.strip().casefold()


def terms_in(text: str, terms: list[Term]) -> list[Term]:
    """Các thuật ngữ nguồn xuất hiện trong `text`, theo thứ tự glossary.

    So khớp không phân biệt hoa thường. Thuật ngữ rỗng bị bỏ qua: chuỗi rỗng là
    chuỗi con của MỌI văn bản, nên nhận nó là nói mọi segment đều bị ảnh hưởng.

    Khi glossary có hai mục cùng danh tính (`key`), mục ĐẦU TIÊN thắng và mục sau
    bị che — đúng một mục cho mỗi thuật ngữ, đúng thứ tự glossary. Hàm này KHÔNG
    lọc `approved()` và không lọc theo ngôn ngữ; bên gọi phải làm.
    """
    haystack = text.casefold()
    out: list[Term] = []
    seen: set[str] = set()
    for t in terms:
        needle = key(t)
        if not needle or needle in seen:
            continue
        if needle in haystack:
            out.append(t)
            seen.add(needle)
    return out


def _mapping(segments: list[Segment], terms: list[Term]) -> dict[int, dict[str, set[str]]]:
    """segment id -> {danh tính thuật ngữ: TẬP bản dịch của thuật ngữ đó}.

    Tập chứ không phải một chuỗi: hai hàng glossary cùng danh tính (`rồng` và
    `Rồng`) đều là thuật ngữ đang xuất hiện, nên đổi bản dịch của hàng thứ hai
    vẫn phải làm segment đó dịch lại. Giữ một chuỗi thì hàng bị che mất thay đổi
    — đúng lỗi mà Task 14 không bao giờ được trả về.
    """
    out: dict[int, dict[str, set[str]]] = {}
    for s in segments:
        haystack = s.text.casefold()
        m: dict[str, set[str]] = {}
        for t in terms:
            needle = key(t)
            if needle and needle in haystack:
                m.setdefault(needle, set()).add(t.translation)
        out[s.i] = m
    return out


def affected_segments(segments: list[Segment], old: list[Term],
                      new: list[Term]) -> list[int]:
    """Id của các segment mà ÁNH XẠ thuật ngữ -> bản dịch đã đổi.

    So ánh xạ chứ không so tập thuật ngữ: đổi bản dịch của một thuật ngữ ĐANG
    xuất hiện làm bản dịch cũ sai, nên segment đó phải dịch lại.

    Cả hai vế đi qua `approved()`: mục chưa duyệt là bản nháp, sửa nó không ràng
    buộc gì; duyệt nó lên hoặc bỏ duyệt nó đi đều đổi ràng buộc nên phải báo.
    """
    before = _mapping(segments, approved(old))
    after = _mapping(segments, approved(new))
    return [s.i for s in segments if before[s.i] != after[s.i]]
