"""Chia lô để dịch. Thuần.

Chia theo NGÂN SÁCH TOKEN, không theo số segment. Số segment chỉ là trần phụ
để chặn rủi ro hỏng JSON khi lô có quá nhiều mục.

TOKENS_PER_SOURCE_CHAR = 1.0 là GIÁ TRỊ TẠM. Giai đoạn 1b phải đo thật tỉ lệ
ký tự nguồn -> token đích rồi hiệu chỉnh; xem spec §10 bảng benchmark.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Segment

OUTPUT_TOKEN_BUDGET = 1200
MAX_SEGMENTS_PER_BATCH = 30
CONTEXT_SEGMENTS = 2
TOKENS_PER_SOURCE_CHAR = 1.0


@dataclass(frozen=True)
class Batch:
    segments: tuple[Segment, ...]
    before: tuple[Segment, ...] = ()
    after: tuple[Segment, ...] = ()

    @property
    def indices(self) -> tuple[int, ...]:
        return tuple(s.i for s in self.segments)


def estimate_output_tokens(
    source_text: str, ratio: float = TOKENS_PER_SOURCE_CHAR
) -> int:
    return max(1, math.ceil(len(source_text) * ratio))


def make_batches(
    segments: list[Segment],
    *,
    budget: int = OUTPUT_TOKEN_BUDGET,
    max_segments: int = MAX_SEGMENTS_PER_BATCH,
    context: int = CONTEXT_SEGMENTS,
    ratio: float = TOKENS_PER_SOURCE_CHAR,
) -> list[Batch]:
    if not segments:
        return []

    groups: list[list[Segment]] = []
    current: list[Segment] = []
    used = 0
    for seg in segments:
        cost = estimate_output_tokens(seg.text, ratio)
        too_big = current and (used + cost > budget or len(current) >= max_segments)
        if too_big:
            groups.append(current)
            current, used = [], 0
        current.append(seg)
        used += cost
    if current:
        groups.append(current)

    batches: list[Batch] = []
    cursor = 0
    for group in groups:
        before = tuple(segments[max(0, cursor - context):cursor])
        after = tuple(segments[cursor + len(group): cursor + len(group) + context])
        batches.append(Batch(segments=tuple(group), before=before, after=after))
        cursor += len(group)
    return batches
