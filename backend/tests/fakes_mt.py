"""Engine dịch giả cho test luồng: alignment, retry, hủy, checkpoint, QA.

Cố ý KHÔNG thông minh. Nó chỉ làm đúng hợp đồng, và có công tắc để hỏng đúng chỗ
cần hỏng (`drop_ids`, `fail_times`).
"""
from __future__ import annotations

from dataclasses import replace

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
        # `calls` = các lô ĐÃ THÀNH CÔNG; `attempts` = MỌI lần gọi, kể cả lần hỏng
        # (test retry cần đếm số lần THỬ, không phải số lần thành công).
        self.calls: list[list[int]] = []
        self.attempts: list[list[int]] = []
        self.last_opts: MtOpts | None = None
        self.last_glossary: list[Term] | None = None
        # `model_ref` là thứ `TranslateHandler` ghi vào `llm_calls.model_ref`, và
        # engine thật (`OpusMtEngine`/`OllamaMtEngine`) đều phơi nó ra. Fake không
        # có nó thì test `llm_calls` sẽ ghim `None` — tức là ghim luôn cả việc
        # handler không lấy được tên model từ engine.
        self.model_ref = "fake/model"

    @property
    def engine_id(self) -> str:
        return "fake-mt"

    def supports_glossary(self) -> bool:
        return True

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        self.attempts.append([s.i for s in batch])
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("fake engine: hỏng theo kịch bản test")
        self.last_opts = opts
        self.last_glossary = glossary
        self.calls.append([s.i for s in batch])
        out: list[Segment] = []
        for s in batch:
            if s.i in self._drop_ids:
                continue
            out.append(replace(s, text=self._mapping.get(s.text, f"[vi]{s.text}")))
        return out

    def release(self) -> None:
        if self.release_count == 0:
            self.release_count = 1
