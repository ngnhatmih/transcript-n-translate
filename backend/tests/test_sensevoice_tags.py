from __future__ import annotations

from app.adapters.asr.sensevoice_tags import parse_rich_tags


def test_parses_language_emotion_and_event_tags():
    raw = "<|zh|><|HAPPY|><|BGM|><|Speech|><|withitn|>大家好，欢迎来到本期节目"
    p = parse_rich_tags(raw)
    assert p.text == "大家好，欢迎来到本期节目"
    assert p.lang == "zh"
    assert p.emotion == "happy"
    assert p.events == ["bgm"]
    assert p.itn is True


def test_handles_multiple_events():
    p = parse_rich_tags("<|zh|><|NEUTRAL|><|Laughter|><|Applause|><|Speech|>哈哈")
    assert p.events == ["laughter", "applause"]
    assert p.emotion == "neutral"


def test_no_tags_is_passed_through():
    p = parse_rich_tags("纯文本")
    assert p.text == "纯文本"
    assert p.lang is None and p.emotion is None and p.events == []


def test_event_tags_are_not_leaked_into_subtitle_text():
    """Đây là lỗi dễ gặp nhất: nhét <|BGM|> vào phụ đề và người xem thấy nó."""
    raw = "<|zh|><|SAD|><|BGM|><|Speech|>这句话很难过"
    p = parse_rich_tags(raw)
    assert "<|" not in p.text and "|>" not in p.text
    assert p.text == "这句话很难过"


def test_unknown_tag_does_not_crash_and_is_dropped():
    p = parse_rich_tags("<|zh|><|SOMETHING_NEW|><|Speech|>文本")
    assert p.text == "文本"
    assert p.emotion is None


def test_whitespace_is_normalised():
    p = parse_rich_tags("<|zh|><|Speech|>  你好   世界  ")
    assert p.text == "你好 世界"
