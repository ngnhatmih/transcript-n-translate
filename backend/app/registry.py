"""Kiểu dữ liệu của registry và các phép tra cứu. Thuần, không đọc tệp.

Việc đọc tệp nằm ở adapters/registry_file.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class EngineSpec:
    id: str
    label: str
    kind: str            # 'asr' | 'mt'
    runtime: str         # 'inprocess' | 'ollama'
    model_ref: str
    vram_mb: int
    langs: tuple[str, ...]
    capabilities: dict = field(default_factory=dict)
    opts: dict = field(default_factory=dict)

    @property
    def phase_key(self) -> str:
        """Khoá giai đoạn của hàng đợi. Phải khớp `job_state.phase_of`."""
        return f"{self.kind}:{self.id}"


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
