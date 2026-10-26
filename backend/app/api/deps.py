"""Dependency của FastAPI: chỉ là lớp mỏng đọc `app.state`.

Để riêng một chỗ thì `create_app()` không phải truyền tham số qua từng route, và
test vẫn thay được bằng `app.dependency_overrides`.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request


def get_repos(request: Request):
    return request.app.state.repos


def get_specs(request: Request):
    return request.app.state.specs


def get_prices(request: Request):
    """Bảng giá của mọi engine có khai giá, suy từ `specs` — MỘT chỗ duy nhất.

    Route nào đọc một hàng bản dịch cũng cần nó để trả `cost_usd`; tự gọi
    `prices_from_specs(app.state.specs)` ở từng route là ba bản sao của cùng một phép suy, và
    bản sao thứ ba sẽ quên `opts` (giá nằm ở `opts`, không ở `capabilities`).
    """
    from app.domain.pricing import prices_from_specs

    return prices_from_specs(request.app.state.specs)


def get_worker(request: Request):
    return getattr(request.app.state, "worker", None)


def get_vram_reader(request: Request):
    """Callable đọc VRAM, do composition root đặt vào `app.state`.

    Mặc định `None`: app dựng để test chỉ đọc (hoặc để đọc dữ liệu cũ) không có
    đường đo, và khi đó route trả `vram: null` — đúng nghĩa "chưa đọc được",
    không phải 0. `app/api` KHÔNG tự import adapter GPU
    (`tests/test_api_sources.py::test_api_layer_does_not_import_adapters`).
    """
    return getattr(request.app.state, "vram_reader", None)


def get_dirs(request: Request) -> dict[str, Any]:
    return request.app.state.dirs


def get_chimera_plan(request: Request):
    """Kế hoạch Chimera của tiến trình, hoặc `None`.

    `getattr` có mặc định: `create_app()` dựng được mà không có kế hoạch (mọi bài
    test chỉ đọc), và một route Chimera gọi trên app đó phải trả 503 kèm lý do —
    không phải ném `AttributeError` thành 500.
    """
    return getattr(request.app.state, "chimera_plan", None)
