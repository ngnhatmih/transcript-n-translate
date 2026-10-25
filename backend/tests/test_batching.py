from __future__ import annotations

from app.domain.batching import (
    CONTEXT_SEGMENTS, MAX_SEGMENTS_PER_BATCH, OUTPUT_TOKEN_BUDGET,
    estimate_output_tokens, make_batches,
)
from app.domain.models import Segment


def _segs(n, chars=10):
    return [Segment(i=i, start=float(i), end=float(i + 1), text="一" * chars) for i in range(n)]


def test_estimate_is_linear_in_source_chars():
    assert estimate_output_tokens("") == 1
    assert estimate_output_tokens("一" * 100, ratio=1.0) == 100
    assert estimate_output_tokens("一" * 100, ratio=0.5) == 50


def test_splits_by_token_budget_not_by_count():
    """Đây là lỗi mà kế hoạch này sửa so với bản spec đầu: chia theo SỐ segment
    là sai đơn vị — 25 segment ngắn và 25 segment dài chênh nhau 8 lần."""
    short = [Segment(i=i, start=float(i), end=float(i + 1), text="一" * 10) for i in range(300)]
    batches = make_batches(short, budget=100, max_segments=1000, context=0)
    assert all(sum(estimate_output_tokens(s.text) for s in b.segments) <= 100 for b in batches)
    assert sum(len(b.segments) for b in batches) == 300

    long = [Segment(i=i, start=float(i), end=float(i + 1), text="一" * 60) for i in range(300)]
    long_batches = make_batches(long, budget=100, max_segments=1000, context=0)
    assert len(long_batches) > len(batches), "segment dài phải cho nhiều lô hơn"


def test_single_oversized_segment_gets_its_own_batch():
    segs = [Segment(i=0, start=0.0, end=1.0, text="一" * 5000)]
    batches = make_batches(segs, budget=100, context=0)
    assert len(batches) == 1
    assert len(batches[0].segments) == 1


def test_hard_cap_on_segment_count():
    segs = _segs(100, chars=1)
    batches = make_batches(segs, budget=10**9, max_segments=MAX_SEGMENTS_PER_BATCH, context=0)
    assert all(len(b.segments) <= MAX_SEGMENTS_PER_BATCH for b in batches)
    assert len(batches) == 4


def test_context_is_taken_from_neighbours_and_excluded_from_payload():
    segs = _segs(10)
    batches = make_batches(segs, budget=30, max_segments=3, context=CONTEXT_SEGMENTS)
    first = batches[0]
    assert first.before == (), "lô đầu không có ngữ cảnh trước"
    assert [s.i for s in first.after] == [3, 4]
    mid = batches[1]
    assert [s.i for s in mid.before] == [1, 2]
    assert all(s.i not in {x.i for x in mid.segments} for s in mid.before)


def test_no_segment_is_lost_or_duplicated():
    segs = _segs(37, chars=7)
    batches = make_batches(segs, budget=25, max_segments=4, context=2)
    flat = [s.i for b in batches for s in b.segments]
    assert flat == list(range(37))


def test_empty_input_gives_no_batches():
    assert make_batches([], budget=100, context=2) == []
