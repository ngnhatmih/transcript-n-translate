"""Kiểu dữ liệu của registry và các phép tra cứu. Thuần, không đọc tệp.

Việc đọc tệp nằm ở adapters/registry_file.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.domain.job_state import phase_of

# `kind` là loại ENGINE trong registry; `phase_of` nhận loại JOB. Hai từ vựng
# này KHÁC nhau: engine dịch có kind "mt" nhưng job của nó là "translate"
# (plan §JOB_TYPES: ingest | asr | translate | export). Ánh xạ tường minh ở đây
# để `phase_key` không bao giờ tự bịa ra một tiền tố thứ ba.
_JOB_TYPE_OF_KIND = {"asr": "asr", "mt": "translate"}


@dataclass(frozen=True)
class EngineSpec:
    """Mô tả một engine. `frozen=True` chỉ chặn GÁN thuộc tính.

    `capabilities` và `opts` vẫn là dict nên `spec.capabilities[...] = ...` và
    `spec.opts[...] = ...` VẪN sửa được tại chỗ, và sửa thì hỏng cấu hình dùng
    chung cho mọi nơi giữ danh sách spec đã nạp. Hãy coi hai trường này là chỉ
    đọc. Việc cưỡng chế bằng kiểu bất biến thuộc task VRAM arbitration.
    """

    id: str
    label: str
    kind: str            # 'asr' | 'mt'  — loại ENGINE, không phải loại job
    runtime: str         # 'inprocess' | 'ollama'
    model_ref: str
    vram_mb: int
    langs: tuple[str, ...]
    capabilities: dict = field(default_factory=dict)
    opts: dict = field(default_factory=dict)

    @property
    def phase_key(self) -> str:
        """Khoá giai đoạn của hàng đợi. Bằng ĐÚNG chuỗi `Job.phase` lưu.

        `next_queued_for_phase` tra bằng equality, nên lệch một chữ cái là hàng
        đợi đứng im mà không ném exception. Vì vậy khoá được dựng qua chính
        `phase_of` với loại job thật, không tự nối chuỗi từ `kind`.
        """
        return phase_of(_JOB_TYPE_OF_KIND[self.kind], self.id)


def of_kind(specs: Iterable[EngineSpec], kind: str) -> list[EngineSpec]:
    return [s for s in specs if s.kind == kind]


def by_id(specs: Iterable[EngineSpec], engine_id: str) -> EngineSpec:
    for spec in specs:
        if spec.id == engine_id:
            return spec
    raise KeyError(f"engine {engine_id!r} không có trong registry")


def estimate_vram_mb(specs: Iterable[EngineSpec], engine_ids: Iterable[str]) -> int:
    specs = list(specs)
    return sum(by_id(specs, eid).vram_mb for eid in engine_ids)
