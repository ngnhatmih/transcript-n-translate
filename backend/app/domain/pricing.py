"""Giá của một engine dịch và chi phí ƯỚC LƯỢNG của một bản dịch.

## Vì sao giá nằm trong `registry.json`, không nằm trong mã

Giá là DỮ LIỆU của một dịch vụ, không phải một hằng số của sản phẩm: nó đổi theo bảng giá của
nhà cung cấp, và engine chạy trên máy (in-process, Ollama) thì **không có giá** — chi phí biên
của nó bằng 0 nhưng đó là kết luận từ "chạy trên GPU này", không phải một con số để nhân. Nên
hàng registry khai `opts.price_in_usd_per_mtok` / `opts.price_out_usd_per_mtok`; engine không
khai thì **không có giá**, và chi phí là `None` chứ không phải `0`.

## `None` ≠ `0`, lần nữa

Ba trường hợp đều cho `None`: engine không khai giá; hàng bản dịch chưa có token (engine in-process
không báo token); hoặc chỉ có một nửa token. Một cột `$0,00` ở đó là nói dối theo hai cách khác
nhau — "đã đo và bằng không" (sai: chưa đo), và "miễn phí" (chưa chắc: giá dịch vụ có thể đổi).

## Đây là ƯỚC LƯỢNG

Nó nhân token ĐÃ ĐO với giá ĐÃ KHAI, không phải hoá đơn. Bảng giá có thể cũ, và bản thân nhà cung
cấp có thể tính khác (giờ cao điểm, cache hit/miss). Vì vậy mọi chỗ hiển thị nó phải nói "ước
lượng" (tiền tố `~`), đúng như khối chi phí của Chimera đã làm.
"""
from __future__ import annotations

from typing import Iterable, Mapping, NamedTuple


class Price(NamedTuple):
    """Giá của MỘT engine, USD cho mỗi TRIỆU token — đơn vị mà mọi bảng giá API dùng."""

    in_usd_per_mtok: float
    out_usd_per_mtok: float


def price_of(spec) -> Price | None:
    """Giá khai trên một `EngineSpec`, hoặc `None` khi hàng đó không khai giá.

    Đọc `opts` (dữ liệu) chứ không `capabilities` (khả năng của engine): giá không phải một năng
    lực, và trộn nó vào `capabilities` sẽ khiến `available`/`glossary_prompt`/`price` cùng một
    túi — nơi giao diện đã phải lọc theo khoá.
    """
    opts = getattr(spec, "opts", None) or {}
    if not isinstance(opts, Mapping):
        return None
    vao = opts.get("price_in_usd_per_mtok")
    ra = opts.get("price_out_usd_per_mtok")
    # Cả hai phải có: một nửa bảng giá là một nửa phép nhân, tức một con số SAI chứ không phải
    # một con số thiếu.
    if not isinstance(vao, (int, float)) or not isinstance(ra, (int, float)):
        return None
    return Price(float(vao), float(ra))


def prices_from_specs(specs: Iterable) -> dict[str, Price]:
    """Bảng giá của MỌI engine có khai giá, khoá theo `spec.id`."""
    ra: dict[str, Price] = {}
    for spec in specs:
        gia = price_of(spec)
        if gia is not None:
            ra[getattr(spec, "id", "")] = gia
    return ra


def cost_usd(engine: str | None, tokens_in: int | None, tokens_out: int | None,
             prices: Mapping[str, Price] | None) -> float | None:
    """Chi phí ước lượng (USD) của MỘT bản dịch, hoặc `None` khi không tính được.

    `None` khi: không có bảng giá; engine không có giá; hoặc thiếu một trong hai số token.
    Không bao giờ trả `0.0` để thay cho "không biết" — xem docstring module.
    """
    if not prices or not engine:
        return None
    gia = prices.get(engine)
    if gia is None:
        return None
    if not isinstance(tokens_in, (int, float)) or not isinstance(tokens_out, (int, float)):
        return None
    return (tokens_in * gia.in_usd_per_mtok + tokens_out * gia.out_usd_per_mtok) / 1_000_000
