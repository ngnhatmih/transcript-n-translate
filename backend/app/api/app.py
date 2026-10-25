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
               worker=None, log_dir=None, broker=None,
               chimera_plan=None, vram_reader=None) -> FastAPI:
    app = FastAPI(title="phu-de-lab", version="0.1.0")
    app.state.repos = repos
    app.state.specs = specs
    app.state.worker = worker
    # M-13: KHÔNG có `app.state.mt_engines`. Bản cũ ghi thuộc tính đó kèm một
    # comment khẳng định "tầng HTTP cần object đó", nhưng KHÔNG route, KHÔNG
    # dependency nào đọc nó — code chết cộng một comment nói dối. Bất biến thật
    # ("handler và composition root dùng CÙNG một dict engine") được ghim ở
    # `tests/test_mt_wiring.py` bằng `assert handler._engines is mt_engines`,
    # tức ở ĐÚNG chỗ nó có nghĩa: chỗ handler được dựng.
    # `chimera_plan` là DỮ LIỆU DẪN XUẤT của composition root (registry + cờ
    # `available` đã dò), tính MỘT lần ở `main.py`. Route Chimera KHÔNG được đọc
    # `registry.json` và cũng không được dò Ollama: nó chỉ tiêu thụ — cùng khuôn
    # với `prompt_version` ở `spec.capabilities`.
    app.state.chimera_plan = chimera_plan
    # `vram_reader` là CALLABLE do `app/main.py` dựng từ `adapters/gpu.py`; route
    # `/api/status` chỉ gọi nó. `app/api` không được import adapter (cùng lý do
    # với `chimera_plan` ở trên), nên phép đọc card đi qua state. Mặc định `None`
    # ⇒ route trả `vram: null` ("chưa đọc được"), đúng khuôn với
    # `ollama: "unknown"`; test chỉ đọc dựng app không cần GPU.
    app.state.vram_reader = vram_reader
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
    app.include_router(routes_translations.chimera_router)

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
    # Task 15: hình dạng spec §11 của route export (`GET /api/export/{translation_id}`)
    # nằm trên router RIÊNG của `routes_translations`, vì `routes_translations.router`
    # mang tiền tố `/api/translations`. Hai route cũ trong `routes_export` ở trên vẫn
    # nguyên và vẫn được phục vụ: `/{job_id}/download` và `/{translation_id}` là hai
    # khuôn đường dẫn khác nhau, nên thứ tự include không đổi hành vi của đường nào.
    app.include_router(routes_translations.export_router)
    # Task 14: tiền tố `/api/glossary` cũng TĨNH, và `GET /api/glossary/version`
    # được khai TRƯỚC route động duy nhất của router (`PATCH /{term_id}`, khác
    # method) nên không có chuyện "version" bị bắt làm id thuật ngữ.
    app.include_router(routes_glossary.router)
    app.include_router(routes_jobs.router)
    return app
