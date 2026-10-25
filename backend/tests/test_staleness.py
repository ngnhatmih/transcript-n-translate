from __future__ import annotations

from app.domain.staleness import is_stale


def test_translation_from_current_version_is_fresh():
    assert is_stale(transcript_version=5, translated_from_version=5) is False


def test_translation_from_old_version_is_stale():
    assert is_stale(transcript_version=5, translated_from_version=3) is True


def test_first_translation_is_never_stale():
    assert is_stale(transcript_version=1, translated_from_version=1) is False


def test_same_second_edits_still_detected():
    """Đây chính là lý do dùng version thay vì timestamp: hai lần sửa trong
    cùng một giây vẫn phân biệt được."""
    assert is_stale(transcript_version=8, translated_from_version=7) is True
