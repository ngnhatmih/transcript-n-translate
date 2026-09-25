"""Parser cho đầu ra 'rich text' của SenseVoice.

SenseVoice trả về chuỗi có tag, ví dụ:
    <|zh|><|HAPPY|><|BGM|><|Speech|><|withitn|>大家好

Parser này là hàm THUẦN nên test được mà không cần nạp model. Nó cũng là chỗ
chặn lỗi khó chịu nhất: để lọt <|BGM|> vào phụ đề.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TAG_RE = re.compile(r"<\|([^|]+)\|>")

EMOTION_TAGS = frozenset({
    "happy", "sad", "angry", "neutral", "fearful", "disgusted", "surprised",
    "unknown",
})
EVENT_TAGS = frozenset({
    "bgm", "speech", "applause", "laughter", "cry", "cough", "sneeze",
    "breath", "noise",
})
LANG_TAGS = frozenset({"zh", "en", "yue", "ja", "ko", "nospeech"})


@dataclass
class ParsedUtterance:
    text: str
    lang: str | None = None
    emotion: str | None = None
    events: list[str] = field(default_factory=list)
    itn: bool = False


def parse_rich_tags(raw: str) -> ParsedUtterance:
    out = ParsedUtterance(text="")
    for match in _TAG_RE.finditer(raw):
        token = match.group(1).strip().lower()
        if token in LANG_TAGS:
            out.lang = token
        elif token in EMOTION_TAGS:
            out.emotion = token
        elif token in EVENT_TAGS:
            if token != "speech" and token not in out.events:
                out.events.append(token)
        elif token == "withitn":
            out.itn = True
        # tag lạ: bỏ qua, không làm hỏng gì

    out.text = " ".join(_TAG_RE.sub("", raw).split())
    return out
