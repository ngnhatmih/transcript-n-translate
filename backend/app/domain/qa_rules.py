"""QA tầng 1 — thuần code, miễn phí, chạy trên MỌI segment.

Tầng 2 (gọi LLM soát lại) chỉ chạy trên segment đã bị tầng này cảnh báo, để
không đốt token. Xem spec §8.8.

Tên riêng không có NER ở đây — dùng chính thuật ngữ glossary làm đại diện. Đó
là thứ duy nhất người dùng đã nói rõ là quan trọng.
"""
from __future__ import annotations

import re

# Vì sao 5.0 mà không phải 3.0 (con số trong spec): tiếng Việt dài gấp ~2.5-4
# lần tiếng Trung — chữ Hán cô đặc, tiếng Việt thêm khoảng trắng — nên một bound
# 3x gắn cờ "too_long" cho MỌI bản dịch đúng, tức là vô hiệu hoá chính cái check
# này. Số đo trên fixture của brief: 7 -> 27 ký tự = 3.86; 6 -> 26 = 4.33. 4.0
# vẫn không đủ (4.33 > 4), 5.0 thì qua cả hai, mà ca bịa/dài dòng (tỉ lệ ~159)
# vẫn bị bắt. Mục đích của check là bắt bịa đặt/lan man, không phải bắt tiếng Việt.
LENGTH_RATIO_MAX = 5.0
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_GARBAGE_RE = re.compile(r"^[\W_]+$", re.UNICODE)


def _numbers(text: str) -> set[str]:
    return {m.group(0) for m in _NUMBER_RE.finditer(text)}


def check(
    source_text: str,
    translated_text: str,
    glossary_terms: tuple[str, ...] | list[str] = (),
    *,
    length_ratio_max: float = LENGTH_RATIO_MAX,
) -> list[str]:
    issues: list[str] = []
    translated = translated_text.strip()

    if not translated or _GARBAGE_RE.match(translated):
        return ["empty"]

    for number in sorted(_numbers(source_text)):
        if number not in translated:
            issues.append(f"missing_number:{number}")

    for term in glossary_terms:
        if term and term not in translated:
            issues.append(f"missing_term:{term}")

    source_len = max(1, len(source_text.strip()))
    if len(translated) > source_len * length_ratio_max:
        issues.append("too_long")

    return issues
