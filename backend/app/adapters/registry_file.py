from __future__ import annotations

import json
import pathlib

from app.config import REGISTRY_PATH
from app.registry import DEFAULT_ASR_KEY, EngineSpec

_KINDS = ("asr", "mt")


def load_registry(path: str | pathlib.Path | None = None) -> list[EngineSpec]:
    p = pathlib.Path(path) if path is not None else REGISTRY_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    specs: list[EngineSpec] = []
    for kind in _KINDS:
        for entry in raw.get(kind, []):
            specs.append(EngineSpec(
                id=entry["id"],
                label=entry.get("label", entry["id"]),
                kind=kind,
                runtime=entry["runtime"],
                model_ref=entry["model_ref"],
                vram_mb=int(entry.get("vram_mb", 0)),
                langs=tuple(entry.get("langs", ())),
                capabilities=dict(entry.get("capabilities", {})),
                opts=dict(entry.get("opts", {})),
            ))
    return specs


def load_default_asr(path: str | pathlib.Path | None = None) -> str | None:
    """Khoá `default_asr` của registry, hoặc `None` khi registry không khai báo.

    `None` KHÔNG có nghĩa là "không có mặc định": `app.registry.default_asr_engine`
    rơi về hằng số dự phòng của GĐ1a rồi vẫn phải chứng minh id đó có thật.
    """
    p = pathlib.Path(path) if path is not None else REGISTRY_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    declared = raw.get(DEFAULT_ASR_KEY)
    return str(declared) if declared else None
