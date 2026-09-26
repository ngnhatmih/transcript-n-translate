"""Engine dịch giả cho test luồng: alignment, retry, hủy, checkpoint, QA.

Cố ý KHÔNG thông minh. Nó chỉ làm đúng hợp đồng, và có công tắc để hỏng đúng chỗ
cần hỏng (`drop_ids`, `fail_times`).
"""
from __future__ import annotations

from app.domain.models import Segment, Term
from app.domain.mt import MtOpts


class FakeMtEngine:
    def __init__(self, *, mapping: dict[str, str] | None = None,
                 drop_ids: set[int] | None = None,
                 fail_times: int = 0) -> None:
        self._mapping = mapping or {}
        self._drop_ids = drop_ids or set()
        self._fail_times = fail_times
        self.release_count = 0
        self.calls: list[list[int]] = []
        self.last_opts: MtOpts | None = None

    @property
    def engine_id(self) -> str:
        return "fake-mt"

    def supports_glossary(self) -> bool:
        return True

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("fake engine: hỏng theo kịch bản test")
        self.last_opts = opts
        self.calls.append([s.i for s in batch])
        out: list[Segment] = []
        for s in batch:
            if s.i in self._drop_ids:
                continue
            out.append(Segment(i=s.i, start=s.start, end=s.end,
                               text=self._mapping.get(s.text, f"[vi]{s.text}"),
                               words=s.words, speaker=s.speaker))
        return out

    def release(self) -> None:
        if self.release_count == 0:
            self.release_count = 1
