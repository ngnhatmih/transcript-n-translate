"""Quy tắc 'bản dịch đã lỗi thời'. Dùng version, KHÔNG dùng timestamp.

Timestamp trùng nhau được (hai lần sửa trong cùng một giây) và không trả lời
được câu 'bản dịch này dịch từ bản transcript nào'.
"""
from __future__ import annotations


def is_stale(transcript_version: int, translated_from_version: int) -> bool:
    return translated_from_version < transcript_version
