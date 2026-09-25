"""Hậu xử lý segment sau khi ASR trả về. Thuần.

Ba việc: bỏ rác, gộp đoạn quá ngắn, cắt đoạn quá dài.
Bất biến: không bao giờ mất chữ, và mốc thời gian luôn liền nhau (không hở).
"""
from __future__ import annotations

import math

from .models import Segment, Word

MIN_DUR = 0.8
MAX_DUR = 7.0
MAX_CHARS = 42 * 2          # 2 dòng × 42 ký tự

HALLUCINATION_MARKERS = (
    "[Music]", "[music]", "[Âm nhạc]", "[Applause]", "[Laughter]",
    "♪", "♪♪",
    "感谢观看", "感谢大家观看", "请不吝点赞", "订阅频道", "字幕由", "字幕组",
    "Thanks for watching", "Thank you for watching",
    "ご視聴ありがとうございました",
)


def _strip_markers(text: str) -> str:
    out = text
    for marker in HALLUCINATION_MARKERS:
        out = out.replace(marker, "")
    return " ".join(out.split()).strip()


def _seg_with(seg: Segment, **changes) -> Segment:
    """Sao chép segment với vài trường đổi. Dùng thay cho dataclasses.replace
    để giữ nguyên các trường tuỳ chọn không đụng tới."""
    data = seg.to_json()
    # `changes` có thể chứa list[Word] (khi cắt theo word boundary). to_json()
    # chỉ chuyển Word thành dict khi chính nó serialize, nên ở đây phải tự
    # chuyển — nếu không, Word.from_json sẽ nhận object và nổ TypeError.
    changes = {
        k: [w.to_json() for w in v] if isinstance(v, list) and v and isinstance(v[0], Word) else v
        for k, v in changes.items()
    }
    data.update(changes)
    return Segment.from_json(data)


def _merge(a: Segment, b: Segment) -> Segment:
    """Gộp b liền sau a. Giữ tín hiệu tin cậy XẤU NHẤT của cả hai."""
    words: list[Word] | None = None
    if a.words is not None and b.words is not None:
        words = list(a.words) + list(b.words)
    probs = [p for p in (a.no_speech_prob, b.no_speech_prob) if p is not None]
    logprobs = [p for p in (a.avg_logprob, b.avg_logprob) if p is not None]
    return _seg_with(
        a,
        text=(a.text + b.text).strip(),
        end=b.end,
        words=words,
        events=list(dict.fromkeys(a.events + b.events)),
        avg_logprob=min(logprobs) if logprobs else None,
        no_speech_prob=max(probs) if probs else None,
        suspect=a.suspect or b.suspect,
    )


def _split_once(seg: Segment, max_dur: float, max_chars: float) -> tuple[Segment, Segment]:
    """Cắt đôi một segment. Hai nhánh PHẢI chung một hợp đồng thời gian.

    Bất biến: `left.text + right.text == seg.text` (không mất chữ) và
    `left.end == right.start` (không hở, không chồng). Vì vậy cả hai nhánh
    đều cắt `seg.text` từ CHÍNH văn bản gốc tại một mốc ký tự duy nhất, và
    mốc thời gian `cut` luôn lấy từ chính tập bên trái.

    Lưu ý: chỉ `lstrip()` nửa phải, không `strip()` cả hai — khoảng trắng nằm
    đúng ranh giới cắt sẽ bị mất nếu cắt từ cả hai phía, mà mất chữ là điều
    module này cấm.
    """
    if seg.words and len(seg.words) >= 2:
        # Word timestamp là nguồn sự thật cho RANH GIỚI THỜI GIAN; văn bản vẫn
        # cắt theo ký tự để `left.text + right.text` khớp đúng văn bản gốc.
        # (Ghép `w.w` rồi lấy độ dài làm mốc cắt là sai với tiếng có khoảng
        # trắng: "hello world" ghép lại thành "helloworld", lệch 1 ký tự.)
        budget = max(1, len(seg.text) // 2)
        acc = 0
        cut_at = 0
        for idx, w in enumerate(seg.words):
            if idx > 0 and acc + len(w.w) > budget:
                break
            acc += len(w.w)
            cut_at = idx + 1
        left_words, right_words = seg.words[:cut_at], seg.words[cut_at:]
        left_text = seg.text[:acc]          # cắt theo ký tự -> không bao giờ lệch
        cut = left_words[-1].e              # mốc nối lấy từ chính tập bên trái
        return (
            _seg_with(seg, text=left_text, end=cut, words=left_words),
            _seg_with(seg, text=seg.text[acc:].lstrip(), start=cut, words=right_words),
        )

    # Không có word timestamp: cắt theo ký tự, chia thời gian theo tỉ lệ ký tự.
    half = len(seg.text) // 2
    # lùi về khoảng trắng gần nhất nếu có (tiếng Anh). Cắt SAU khoảng trắng để
    # khoảng trắng ở lại nửa trái; nếu cắt ngay tại nó thì `lstrip()` nửa phải
    # sẽ xoá mất một ký tự.
    space = seg.text.rfind(" ", 0, min(len(seg.text), half + 10))
    if space > 0:
        half = space + 1
    left_text, right_text = seg.text[:half], seg.text[half:]
    ratio = len(left_text) / max(1, len(seg.text))
    cut = seg.start + seg.duration * ratio
    return (
        _seg_with(seg, text=left_text, end=cut, words=None),
        _seg_with(seg, text=right_text.lstrip(), start=cut, words=None),
    )


def _split(seg: Segment, max_dur: float, max_chars: float) -> list[Segment]:
    if seg.duration <= max_dur and len(seg.text) <= max_chars:
        return [seg]
    if len(seg.text) < 2:
        return [seg]
    left, right = _split_once(seg, max_dur, max_chars)
    if not left.text or not right.text:
        return [seg]
    return _split(left, max_dur, max_chars) + _split(right, max_dur, max_chars)


def normalize(
    segments: list[Segment],
    *,
    min_dur: float = MIN_DUR,
    max_dur: float = MAX_DUR,
    max_chars: int = MAX_CHARS,
) -> list[Segment]:
    cleaned: list[Segment] = []
    for seg in segments:
        text = _strip_markers(seg.text)
        if not text:
            continue
        if text != seg.text:
            seg = _seg_with(seg, text=text)
        cleaned.append(seg)

    merged: list[Segment] = []
    for seg in cleaned:
        if merged and seg.duration < min_dur:
            merged[-1] = _merge(merged[-1], seg)
        elif not merged and seg.duration < min_dur:
            merged.append(seg)          # sẽ gộp xuôi ở vòng sau
        else:
            if merged and merged[-1].duration < min_dur:
                merged[-1] = _merge(merged[-1], seg)
            else:
                merged.append(seg)
    # gộp xuôi cho đoạn đầu quá ngắn
    if len(merged) >= 2 and merged[0].duration < min_dur:
        merged[1] = _merge(merged[0], merged[1])
        merged.pop(0)

    split: list[Segment] = []
    for seg in merged:
        split.extend(_split(seg, max_dur, max_chars))

    return [_seg_with(s, i=idx) for idx, s in enumerate(split)]
