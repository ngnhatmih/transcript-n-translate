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
