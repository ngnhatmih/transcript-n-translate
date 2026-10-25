from __future__ import annotations

import json
import pathlib

from app.config import REGISTRY_PATH
from app.registry import DEFAULT_ASR_KEY, DEFAULT_MT_KEY, EngineSpec

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


def load_chimera(path: str | pathlib.Path | None = None) -> dict | None:
    """Khối `chimera` THÔ của registry, hoặc `None` khi registry không khai báo.

    `None` KHÔNG được coi là lỗi cấu hình: một registry không có chế độ Chimera là
    một cấu hình HỢP LỆ (chế độ này là tuỳ chọn — "Tuỳ chọn bật trong UI", §8.7.5),
    và nhiều bài test dựng app trên một registry tối thiểu. Coi nó là lỗi sẽ biến
    mọi registry tối thiểu thành một lỗi khởi động.

    Việc KIỂM TÍNH ĐÚNG của khối này nằm ở `domain.chimera.plan_from_raw` — hàm
    thuần, nên nó ghim được bằng test mà không cần đọc tệp.
    """
    p = pathlib.Path(path) if path is not None else REGISTRY_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    block = raw.get("chimera")
    return block if isinstance(block, dict) else None


def load_default_mt(path: str | pathlib.Path | None = None) -> str | None:
    """Khoá `default_mt` của registry, hoặc `None` khi registry không khai báo (R58).

    `None` KHÔNG có nghĩa là "không có mặc định": `app.registry.default_mt_engine`
    rơi về phần tử ĐẦU của danh sách `mt` — đúng hành vi cũ, chỉ còn là điểm rơi.
    """
    p = pathlib.Path(path) if path is not None else REGISTRY_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    declared = raw.get(DEFAULT_MT_KEY)
    return str(declared) if declared else None
