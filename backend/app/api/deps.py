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


def get_worker(request: Request):
    return getattr(request.app.state, "worker", None)


def get_dirs(request: Request) -> dict[str, Any]:
    return request.app.state.dirs


def get_chimera_plan(request: Request):
    """Kế hoạch Chimera của tiến trình, hoặc `None`.

    `getattr` có mặc định: `create_app()` dựng được mà không có kế hoạch (mọi bài
    test chỉ đọc), và một route Chimera gọi trên app đó phải trả 503 kèm lý do —
    không phải ném `AttributeError` thành 500.
    """
    return getattr(request.app.state, "chimera_plan", None)
