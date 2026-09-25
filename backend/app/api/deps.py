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
