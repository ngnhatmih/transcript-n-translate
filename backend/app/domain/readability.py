"""Tốc độ đọc (CPS). Thuần.

Vì sao cần riêng một module: tiếng Việt dài gấp 2-3 lần tiếng Trung. Một dòng
phụ đề dịch đúng nghĩa vẫn có thể KHÔNG ĐỌC KỊP. Đây là lỗi phụ đề phổ biến
nhất và nó chỉ lộ ra khi đặt bản gốc cạnh bản dịch.
"""
from __future__ import annotations

CPS_WARN = 20.0


def reading_cps(text: str, start: float, end: float) -> float:
    """Ký tự không tính khoảng trắng trên mỗi giây."""
    duration = end - start
    if duration <= 0:
        return float("inf")
    chars = len("".join(text.split()))
    return chars / duration


def is_too_fast(text: str, start: float, end: float, threshold: float = CPS_WARN) -> bool:
    return reading_cps(text, start, end) > threshold
