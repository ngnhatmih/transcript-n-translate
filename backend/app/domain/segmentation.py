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


def _words_json(value):
    """Chuẩn hoá giá trị `words` trước khi round-trip JSON.

    `Segment.to_json()` chỉ chuyển `Word` -> dict cho `self.words`, không đụng
    tới giá trị truyền qua `changes`. Không chuẩn hoá ở đây thì
    `Word.from_json` nhận object và nổ `TypeError: 'Word' object is not
    subscriptable`. Phải bắt cả tuple, list trộn, và phần tử đã là dict.
    """
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return value
    return [w.to_json() if isinstance(w, Word) else w for w in value]


def _seg_with(seg: Segment, **changes) -> Segment:
    """Sao chép segment với vài trường đổi. Dùng thay cho dataclasses.replace
    để giữ nguyên các trường tuỳ chọn không đụng tới."""
    data = seg.to_json()
    data.update({k: _words_json(v) for k, v in changes.items()})
    return Segment.from_json(data)


def _is_cjk(ch: str) -> bool:
    """Ký tự thuộc khối CJK/Hán — dùng để quyết định có chèn khoảng trắng."""
    o = ord(ch)
    return (
        0x3400 <= o <= 0x4DBF        # CJK Extension A
        or 0x4E00 <= o <= 0x9FFF     # CJK Unified Ideographs
        or 0xF900 <= o <= 0xFAFF     # CJK Compatibility Ideographs
        or 0x3040 <= o <= 0x30FF     # Hiragana + Katakana
    )


def _join_text(a: str, b: str) -> str:
    """Nối hai nửa văn bản khi GỘP, chèn một khoảng trắng nếu cần.

    Chỉ nối trực tiếp khi ký tự cuối của `a` và ký tự đầu của `b` đều là CJK
    (tiếng Trung/Nhật không ngăn cách từ bằng khoảng trắng). Mọi trường hợp
    khác — kể cả tiếng Việt, ngôn ngữ chính của pipeline — phải có khoảng
    trắng, nếu không phụ đề bị dính chữ: 'xin chào' + 'bạn' -> 'xin chàobạn'.
    """
    if not a:
        return b
    if not b:
        return a
    if _is_cjk(a[-1]) and _is_cjk(b[0]):
        return a + b
    return a + " " + b


def _merge(a: Segment, b: Segment) -> Segment:
    """Gộp b liền sau a. Giữ tín hiệu tin cậy XẤU NHẤT của cả hai."""
    words: list[Word] | None = None
    if a.words is not None and b.words is not None:
        words = list(a.words) + list(b.words)
    probs = [p for p in (a.no_speech_prob, b.no_speech_prob) if p is not None]
    logprobs = [p for p in (a.avg_logprob, b.avg_logprob) if p is not None]
    return _seg_with(
        a,
        text=_join_text(a.text, b.text).strip(),
        end=b.end,
        words=words,
        events=list(dict.fromkeys(a.events + b.events)),
        avg_logprob=min(logprobs) if logprobs else None,
        no_speech_prob=max(probs) if probs else None,
        suspect=a.suspect or b.suspect,
    )


def _word_offsets(text: str, words: list[Word]) -> list[tuple[int, int]]:
    """Với mỗi mốc cắt hợp lệ, trả về (vị trí trong `text`, số từ đứng bên trái).

    Đây là chỗ sửa lỗi "hai hệ chỉ số lệch nhau": cộng dồn `len(w.w)` rồi dùng
    nó làm offset trên `text` là sai khi văn bản có khoảng trắng
    ('hello world foo' -> tổng độ dài từ = 12, offset thật = 16), khiến phần
    bên phải bắt đầu giữa một từ.

    Mỗi từ được dò trong `text` bắt đầu từ con trỏ, nên offset luôn rơi ĐÚNG
    vào biên từ và không bao giờ nuốt khoảng trắng. Từ không khớp thì dừng
    ngay: đẩy con trỏ qua một từ không tồn tại trong văn bản sẽ sinh offset
    sai và cắt vào giữa chữ.

    Bất biến: phần tử CUỐI luôn có `count == len(words)` KHI VÀ CHỈ KHI cả danh
    sách từ được khớp trọn. Nhờ vậy bên gọi phân biệt được "khớp hết" với
    "lệch ở giữa, đừng tin offset".
    """
    out: list[tuple[int, int]] = []
    pos = 0
    for count, w in enumerate(words, start=1):
        cur = pos
        # bỏ qua rác giữa hai từ, nhưng không vượt quá độ dài văn bản
        while cur < len(text) and text[cur].isspace():
            cur += 1
        if cur >= len(text) or not text.startswith(w.w, cur):
            break
        if cur > pos:
            # khoảng trắng trước từ này cũng là một mốc cắt hợp lệ (giữ nó ở
            # bên trái). Khử trùng với mốc vừa ghi.
            if not out or out[-1] != (pos, count - 1):
                out.append((pos, count - 1))
        pos = cur + len(w.w)
        out.append((pos, count))
    return out


def _split_once(seg: Segment, max_dur: float, max_chars: float) -> tuple[Segment, Segment]:
    """Cắt đôi một segment. Hai nhánh PHẢI chung một hợp đồng thời gian.

    Bất biến: `left.text + right.text == seg.text` (không mất chữ) và
    `left.end == right.start` (không hở, không chồng). Vì vậy cả hai nhánh đều
    cắt `seg.text` từ CHÍNH văn bản gốc tại MỘT mốc ký tự duy nhất, và không
    nhánh nào `strip()`/`lstrip()` — cắt xong rồi cắt bỏ khoảng trắng ở ranh
    giới chính là xoá chữ, điều module này cấm.
    """
    if seg.words and len(seg.words) >= 2:
        # Word timestamp là nguồn sự thật cho RANH GIỚI THỜI GIAN; mốc cắt văn
        # bản lấy từ cùng một chỉ số từ, nên chữ và timestamp luôn khớp nhau.
        #
        # Điều kiện tiên quyết: danh sách từ phải dựng lại ĐÚNG văn bản (bỏ
        # khoảng trắng). Word form của engine có thể khác segment text — khi đó
        # mọi phép dò theo con trỏ đều vô nghĩa và cắt theo từ sẽ lệch chữ.
        # Thà mất word timestamp của piece còn hơn gán sai timestamp cho chữ.
        flat_words = "".join(w.w for w in seg.words)
        if flat_words != "".join(seg.text.split()):
            return _split_by_chars(seg)
        offsets = _word_offsets(seg.text, seg.words)
        if not offsets or offsets[-1][1] != len(seg.words):
            return _split_by_chars(seg)      # danh sách từ lệch văn bản
        budget = max(1, len(seg.text) // 2)
        cut_at = 0
        text_offset = 0
        for off, count in offsets:
            if count > 1 and off > budget:
                break
            cut_at, text_offset = count, off
        left_words, right_words = seg.words[:cut_at], seg.words[cut_at:]
        if not left_words or not right_words or text_offset <= 0:
            return _split_by_chars(seg)
        left_text, right_text = seg.text[:text_offset], seg.text[text_offset:]
        cut = left_words[-1].e
        # Hai nửa phải thật sự có thời lượng; nếu không thì mốc từ vô dụng.
        if cut <= seg.start or cut >= seg.end or not left_text or not right_text:
            return _split_by_chars(seg)
        return (
            _seg_with(seg, text=left_text, end=cut, words=left_words),
            _seg_with(seg, text=right_text, start=cut, words=right_words),
        )

    return _split_by_chars(seg)


def _split_by_chars(seg: Segment) -> tuple[Segment, Segment]:
    """Cắt theo ký tự, chia thời gian theo tỉ lệ ký tự. Dùng khi không có word
    timestamp, hoặc khi mốc từ không dùng được (lệch, trùng thời gian)."""
    text = seg.text
    half = len(text) // 2
    # Ưu tiên cắt SAU một khoảng trắng gần giữa để không chặt đôi từ, nhưng
    # khoảng trắng đó phải để lại chữ có nghĩa ở CẢ HAI phía — nếu không,
    # `_split` sẽ từ chối piece rỗng và bỏ luôn khả năng cắt tiếp, để lại một
    # piece dài quá MAX_DUR.
    preferred = half
    space = text.rfind(" ", 0, min(len(text), half + 10))
    if space > 0 and text[:space].strip() and text[space + 1:].strip():
        preferred = space + 1

    def usable(cut: int) -> bool:
        return 0 < cut < len(text) and bool(text[:cut].strip()) and bool(text[cut:].strip())

    if not usable(preferred):
        # mốc ưu tiên hỏng -> chọn mốc gần giữa nhất còn dùng được
        found = None
        for delta in range(1, len(text)):
            for cand in (half - delta, half + delta):
                if usable(cand):
                    found = cand
                    break
            if found is not None:
                break
        if found is None:
            preferred = half          # không có mốc nào: piece bên gọi tự xử
        else:
            preferred = found

    left_text, right_text = text[:preferred], text[preferred:]
    ratio = len(left_text) / max(1, len(text))
    cut = seg.start + seg.duration * ratio
    return (
        _seg_with(seg, text=left_text, end=cut, words=None),
        _seg_with(seg, text=right_text, start=cut, words=None),
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
