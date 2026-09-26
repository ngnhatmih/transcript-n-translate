"""App factory.

`create_app()` nhận hết phụ thuộc qua tham số (không đọc `app.config`) nên test
dựng được một app đầy đủ trong `tmp_path` mà không chạm `data/`, DB thật, hay
bất kỳ model nào. `app/main.py` là chỗ duy nhất ráp cấu hình thật vào đây.
"""
from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.sse import JobEventBroker
from app.registry import EngineSpec

# Frontend dev server (Next.js) chạy khác cổng với API nên trình duyệt sẽ chặn
# nếu thiếu CORS. Chỉ mở đúng hai origin của dev, không dùng "*".
FRONTEND_DEV_ORIGINS = ["http://localhost:3100", "http://127.0.0.1:3100"]


def create_app(*, repos, specs: list[EngineSpec], media_dir, out_dir,
               worker=None, log_dir=None, broker=None, mt_engines=None) -> FastAPI:
    app = FastAPI(title="phu-de-lab", version="0.1.0")
    app.state.repos = repos
    app.state.specs = specs
    app.state.worker = worker
    # `mt_engines` là dict `{spec.id: engine}` do `app/main.py` dựng và trao cho
    # CÙNG một `TranslateHandler`. Mặc định `None` để test chỉ đọc vẫn dựng được
    # app; production luôn truyền ĐÚNG object đó, không phải bản sao — một dict
    # chép lại sẽ khiến tầng HTTP nói về engine khác với engine đang chạy.
    app.state.mt_engines = mt_engines
    # `broker` là tham số tuỳ chọn để `app/main.py` truyền CÙNG một broker cho
    # worker: worker publish, route `/api/jobs/stream` đọc. Bỏ trống thì app vẫn
    # dựng được (test chỉ đọc) và route stream trả về một stream rỗng.
    app.state.broker = broker or JobEventBroker()
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

    from app.api import (routes_export, routes_glossary, routes_jobs,
                         routes_media, routes_registry, routes_sources,
                         routes_transcripts, routes_translations)

    app.include_router(routes_registry.router)
    app.include_router(routes_sources.router)
    app.include_router(routes_media.router)
    app.include_router(routes_transcripts.router)
    app.include_router(routes_export.router)
    # Task 13: `prefix="/api/translations"` là tiền tố TĨNH, không đụng route
    # `/{...}` động của các router khác, nên thứ tự ở đây không phải chuyện đúng
    # sai — nhưng vẫn đặt cạnh nhóm route tài nguyên (trước `routes_jobs`) để tệp
    # này đọc như một danh sách tài nguyên.
    app.include_router(routes_translations.router)
    # Task 14: tiền tố `/api/glossary` cũng TĨNH, và `GET /api/glossary/version`
    # được khai TRƯỚC route động duy nhất của router (`PATCH /{term_id}`, khác
    # method) nên không có chuyện "version" bị bắt làm id thuật ngữ.
    app.include_router(routes_glossary.router)
    app.include_router(routes_jobs.router)
    return app
