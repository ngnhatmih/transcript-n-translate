"""App factory.

`create_app()` nhận hết phụ thuộc qua tham số (không đọc `app.config`) nên test
dựng được một app đầy đủ trong `tmp_path` mà không chạm `data/`, DB thật, hay
bất kỳ model nào. `app/main.py` là chỗ duy nhất ráp cấu hình thật vào đây.
"""
from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.registry import EngineSpec

# Frontend dev server (Next.js) chạy khác cổng với API nên trình duyệt sẽ chặn
# nếu thiếu CORS. Chỉ mở đúng hai origin của dev, không dùng "*".
FRONTEND_DEV_ORIGINS = ["http://localhost:3100", "http://127.0.0.1:3100"]


def create_app(*, repos, specs: list[EngineSpec], media_dir, out_dir,
               worker=None, log_dir=None) -> FastAPI:
    app = FastAPI(title="phu-de-lab", version="0.1.0")
    app.state.repos = repos
    app.state.specs = specs
    app.state.worker = worker
    app.state.dirs = {
        "media": pathlib.Path(media_dir),
        "out": pathlib.Path(out_dir),
        "log": pathlib.Path(log_dir) if log_dir else pathlib.Path(out_dir).parent / "logs",
    }
    app.state.dirs["media"].mkdir(parents=True, exist_ok=True)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=FRONTEND_DEV_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api import routes_registry, routes_sources

    app.include_router(routes_registry.router)
    app.include_router(routes_sources.router)
    return app
