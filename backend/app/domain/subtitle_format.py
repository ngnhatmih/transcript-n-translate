"""Sinh SRT / VTT / ASS. Thuần, không phụ thuộc gì.

Đặt ở domain vì đây là logic nghiệp vụ và phải test được mà không cần model,
không cần đĩa, không cần mạng.

Bất biến: `translations` là danh sách SONG SONG với `segments` —
`_assert_lengths` bảo đảm `len(translations) == len(segments)`. Vì vậy CẢ BA
định dạng tra bản dịch theo VỊ TRÍ (`enumerate`), không theo `seg.i`.

Tra theo `seg.i` là sai một cách âm thầm: `normalize()` đánh số lại liên tục
nên `seg.i == vị trí` trong thực tế, và hai cách chỉ trùng nhau NHỜ MAY. Khi
`i` có khoảng trống (`i=[0,1,3]` sau khi xoá một đoạn ở giữa mà không đánh số
lại), `translations[3]` vượt biên và bản dịch biến mất — cùng một transcript
cho ra phụ đề khác nhau tuỳ định dạng.
"""
from __future__ import annotations

from .models import Segment


def format_timestamp(seconds: float, *, sep: str = ",") -> str:
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def _ass_timestamp(seconds: float) -> str:
    total_cs = int(round(max(0.0, seconds) * 100))
    hours, rem = divmod(total_cs, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, centis = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _assert_lengths(segments: list[Segment], translations: list[str] | None) -> None:
    if translations is not None and len(translations) != len(segments):
        raise ValueError(
            f"số bản dịch ({len(translations)}) khác số đoạn ({len(segments)})"
        )


def _lines(seg: Segment, translated: str | None, bilingual: bool) -> list[str]:
    if translated is None:
        return [seg.text]
    return [seg.text, translated] if bilingual else [translated]


def to_srt(segments: list[Segment], *, translations: list[str] | None = None,
           bilingual: bool = False) -> str:
    _assert_lengths(segments, translations)
    if not segments:
        return ""
    blocks: list[str] = []
    for n, seg in enumerate(segments, start=1):
        translated = translations[n - 1] if translations is not None else None
        body = "\n".join(_lines(seg, translated, bilingual))
        blocks.append(
            f"{n}\n"
            f"{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}\n"
            f"{body}"
        )
    return "\n\n".join(blocks) + "\n"


def to_vtt(segments: list[Segment], *, translations: list[str] | None = None,
           bilingual: bool = False) -> str:
    _assert_lengths(segments, translations)
    out = ["WEBVTT", ""]
    for position, seg in enumerate(segments):
        translated = translations[position] if translations is not None else None
        out.append(
            f"{format_timestamp(seg.start, sep='.')} --> {format_timestamp(seg.end, sep='.')}"
        )
        out.extend(_lines(seg, translated, bilingual))
        out.append("")
    return "\n".join(out) + "\n"


_ASS_HEADER = """[Script Info]
Title: {title}
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Archivo,54,&H00DCE4E8,&H0000B0FF,&H00201F1E,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,60,60,48,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def to_ass(segments: list[Segment], *, translations: list[str] | None = None,
           bilingual: bool = False, title: str = "phu-de-lab") -> str:
    _assert_lengths(segments, translations)
    lines = [_ASS_HEADER.format(title=title)]
    for position, seg in enumerate(segments):
        translated = translations[position] if translations is not None else None
        parts = _lines(seg, translated, bilingual)
        text = _ass_escape("\\N".join(parts))
        lines.append(
            f"Dialogue: 0,{_ass_timestamp(seg.start)},{_ass_timestamp(seg.end)},"
            f"Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"
