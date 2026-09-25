from __future__ import annotations

from app.domain.models import Segment, Word
from app.domain.segmentation import MAX_CHARS, MIN_DUR, normalize


def _s(i, start, end, text, **kw):
    return Segment(i=i, start=start, end=end, text=text, **kw)


def test_renumbers_and_drops_empty():
    got = normalize([_s(5, 0.0, 3.0, "  "), _s(9, 3.0, 6.0, "你好")])
    assert [s.i for s in got] == [0]
    assert got[0].text == "你好"


def test_merges_short_segment_into_previous():
    got = normalize([
        _s(0, 0.0, 2.0, "第一句"),
        _s(1, 2.0, 2.3, "短"),          # 0.3s < MIN_DUR
        _s(2, 2.3, 5.0, "第三句"),
    ])
    assert len(got) == 2
    assert got[0].text == "第一句短"
    assert got[0].end == 2.3
    assert [s.i for s in got] == [0, 1]


def test_first_segment_too_short_merges_forward():
    got = normalize([_s(0, 0.0, 0.4, "嗯"), _s(1, 0.4, 3.0, "正文")])
    assert len(got) == 1
    assert got[0].text == "嗯正文"
    assert got[0].start == 0.0


def test_splits_long_by_duration_using_word_boundaries():
    words = [Word(w=f"词{k}", s=float(k), e=float(k + 1)) for k in range(10)]
    got = normalize([_s(0, 0.0, 10.0, "".join(w.w for w in words), words=words)])
    assert len(got) == 2, "10s > MAX_DUR phải bị cắt"
    assert got[0].end == got[1].start, "mốc nối phải liền nhau, không hở"
    assert all(s.duration <= 7.0 + 1e-6 for s in got)


def test_splits_long_by_chars_when_no_words():
    text = "一" * (MAX_CHARS + 40)
    got = normalize([_s(0, 0.0, 5.0, text)])
    assert len(got) == 2
    assert all(len(s.text) <= MAX_CHARS for s in got)
    assert got[0].start == 0.0 and got[-1].end == 5.0
    assert "".join(s.text for s in got) == text, "không được mất chữ khi cắt"


def test_removes_hallucination_markers():
    got = normalize([_s(0, 0.0, 3.0, "感谢观看"), _s(1, 3.0, 6.0, "真的一句")])
    assert [s.text for s in got] == ["真的一句"]


def test_keeps_confidence_and_suspect_flags_when_merging():
    got = normalize([
        _s(0, 0.0, 2.0, "甲", no_speech_prob=0.9, avg_logprob=-2.0, suspect=True),
        _s(1, 2.0, 2.2, "乙"),
    ])
    assert len(got) == 1
    assert got[0].suspect is True
    assert got[0].no_speech_prob == 0.9


# --- Bổ sung: đầu vào có khoảng trắng (tiếng Việt / tiếng Anh) -------------
# Bảy test gốc của brief chỉ dùng tiếng Trung không khoảng trắng — đúng lớp
# đầu vào mà mọi lỗi dưới đây không thể lộ ra. Đó là lý do ba lỗi đã ship xanh.


def test_spaced_word_split_loses_no_character():
    """'hello world' cắt theo word boundary phải giữ đủ 11 ký tự.

    (Trước khi sửa: `seg.text[acc:].lstrip()` nuốt mất dấu cách -> 10 ký tự.)
    """
    words = [Word(w="hello", s=0.0, e=5.0), Word(w="world", s=5.0, e=9.0)]
    text = "hello world"
    got = normalize([_s(0, 0.0, 9.0, text, words=words)])
    assert "".join(s.text for s in got) == text, "không được mất chữ"
    assert len(got) == 2
    assert got[0].end == got[1].start


def test_spaced_word_split_keeps_word_text_alignment():
    """Chữ và word timestamp phải cắt tại CÙNG một chỉ số.

    (Trước khi sửa: piece0 = 'hello world f' với words ['hello','world','foo'],
    piece1 = 'oo bar baz qux' — chữ lệch hẳn khỏi timestamp.)
    """
    text = "hello world foo bar baz qux"
    words = [Word(w=w, s=float(k), e=float(k + 1)) for k, w in enumerate(text.split())]
    got = normalize([_s(0, 0.0, 9.0, text, words=words)])
    assert "".join(s.text for s in got) == text
    assert len(got) == 2
    # Chữ của mỗi piece phải khớp đúng các từ được gán cho nó. Piece không có
    # word data (words=None) là hợp lệ, khi đó không kiểm tra được gì thêm.
    for seg in got:
        if seg.words is not None:
            assert seg.text.replace(" ", "") == "".join(w.w for w in seg.words), (
                f"lệch chữ/timestamp: text={seg.text!r} words={[w.w for w in seg.words]}"
            )


def test_spaced_many_words_never_emits_empty_words_or_zero_duration():
    """Không bao giờ sinh piece thời lượng 0 hay `words=[]` bịa ra.

    `models.py` cấm bịa `words: []` cho engine không có word timestamp.
    (Trước khi sửa: piece cuối start=end=8.0, words=[], 79 ký tự.)
    """
    text = ("hello world " * 40).strip()
    words = [Word(w=w, s=k * 0.1, e=(k + 1) * 0.1)
             for k, w in enumerate("hello world ".split() * 40)][:80]
    got = normalize([_s(0, 0.0, 8.0, text, words=words)])
    assert "".join(s.text for s in got) == text
    assert [s.i for s in got] == list(range(len(got)))
    for seg in got:
        assert seg.duration > 0, f"piece thời lượng 0: {seg}"
        # words=None là HỢP LỆ (không biết word data); words=[] mới là bịa.
        assert seg.words is None or len(seg.words) > 0, f"piece rỗng words: {seg}"
    assert all(len(s.text) <= MAX_CHARS for s in got)
    for a, b in zip(got, got[1:]):
        assert a.end == b.start, "không được hở/chồng mốc thời gian"


def test_merge_inserts_space_between_spaced_languages():
    """Gộp tiếng Việt phải có khoảng trắng, không dính chữ."""
    got = normalize([
        _s(0, 0.0, 2.0, "xin chào"),
        _s(1, 2.0, 2.2, "bạn"),        # 0.2s < MIN_DUR -> gộp
    ])
    assert len(got) == 1
    assert got[0].text == "xin chào bạn"


def test_merge_keeps_cjk_glued_without_space():
    """Gộp CJK thì nối trực tiếp, không chèn khoảng trắng."""
    got = normalize([_s(0, 0.0, 2.0, "第一句"), _s(1, 2.0, 2.2, "短")])
    assert len(got) == 1
    assert got[0].text == "第一句短"


def test_merge_spaced_when_short_segment_comes_first():
    got = normalize([_s(0, 0.0, 0.4, "um"), _s(1, 0.4, 3.0, "hello there")])
    assert len(got) == 1
    assert got[0].text == "um hello there"


def test_words_not_present_in_text_falls_back_without_losing_text():
    """Word list lệch văn bản thì phải cắt theo ký tự, không cắt bừa.

    Word form của engine có thể khác văn bản segment. Nếu vẫn cộng dồn độ dài
    từ để suy ra offset thì con trỏ trôi và cắt vào giữa chữ -> mất ký tự.
    """
    text = "hello world " * 20
    got = normalize([_s(0, 0.0, 10.0, text, words=[
        Word(w="zzz", s=0.0, e=1.0),
        Word(w="qqq", s=1.0, e=2.0),
    ])])
    assert "".join(s.text for s in got).rstrip() == text.rstrip()
    assert all(s.duration > 0 for s in got)
    for a, b in zip(got, got[1:]):
        assert a.end == b.start
