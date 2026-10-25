"""Hợp đồng engine dịch. Chỉ Protocol — không hiện thực gì ở đây."""
from __future__ import annotations

from typing import Protocol

from app.domain.models import Segment, Term
from app.domain.mt import MtOpts


class MtEngine(Protocol):
    @property
    def engine_id(self) -> str: ...

    def supports_glossary(self) -> bool:
        """Engine này có đường nào nhận glossary không (spec §8.7.2)."""
        ...

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        """Dịch một lô.

        BẮT BUỘC: trả về đúng bấy nhiêu `Segment`, GIỮ NGUYÊN `i`, `start`, `end`,
        `speaker` và `words` của đầu vào, CHỈ thay `text`. Không bảo đảm được thì
        ném `app.domain.alignment.AlignmentProblem` — KHÔNG trả list ngắn hơn.
        """
        ...

    def release(self) -> None:
        """Đổ model khỏi VRAM. BẮT BUỘC idempotent: gọi lúc chưa nạp là no-op."""
        ...
