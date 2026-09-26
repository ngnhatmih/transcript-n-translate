"""Điểm ráp nối của backend: dựng repos + worker + app rồi chạy.

File này là chỗ DUY NHẤT được phép biết cả adapter lẫn tầng HTTP. `create_app()`
không đọc `app.config`, còn `build_components()` thì ráp đúng một lần cho tiến
trình thật.
"""
from __future__ import annotations

import os
import pathlib
import threading

from fastapi import FastAPI

from app.adapters.clock_system import SystemClock
from app.adapters.governor.single_gpu import SingleGpuGovernor
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.adapters.registry_file import load_default_asr, load_default_mt, load_registry
from app.api.app import create_app
from app.api.sse import JobEventBroker
from app.config import (API_HOST, API_PORT, DB_PATH, HF_HOME, LOG_DIR, MEDIA_DIR,
                        OUTPUT_DIR, OLLAMA_MODELS, ensure_dirs)
from app.pipeline.export import ExportHandler
from app.pipeline.ingest import IngestHandler
from app.pipeline.transcribe import AUTO_FORWARD_SETTING, TranscribeHandler
from app.registry import ASR_DEFAULT_SETTING, default_asr_engine
from app.worker import PhaseQueueWorker

# MT là Giai đoạn 2.
_AUTO_FORWARD_OFF = "0"


def build_components():
    """Dựng repos, specs, worker và MỘT broker đã nối dây.

    Không chạy vòng lặp, không mở mạng. Broker trả về ở đây là đường dây duy
    nhất nối worker với `/api/jobs/stream`: worker publish vào nó, `build_app()`
    truyền chính nó cho `create_app()`. Dựng hai broker riêng thì stream không
    bao giờ nhận được gì — job chạy xong mà giao diện đứng im.
    """
    ensure_dirs()
    # DC-03: `log_dir` biến `log_path` + `data/logs/job-<id>.log` của spec §5.5
    # từ hợp đồng chết thành thứ chạy thật.
    repos = SqliteRepos(DB_PATH, clock=SystemClock(), log_dir=LOG_DIR)
    repos.init_schema()
    specs = load_registry()
    governor = SingleGpuGovernor(repos)

    # I-3: engine ASR mặc định là DỮ LIỆU (registry/setting), và nó phải có thật.
    # Kiểm NGAY tại đây — chỗ sớm nhất — vì một tiến trình dựng xong với cấu hình
    # này sẽ nhận upload rồi đẻ ra job asr chắc chắn `KeyError` ở tận worker.
    declared_asr = load_default_asr()
    try:
        default_asr_engine(specs, declared=declared_asr,
                           configured=repos.get_setting(ASR_DEFAULT_SETTING))
    except KeyError as exc:
        raise RuntimeError(
            f"cấu hình engine ASR mặc định không dùng được: {exc}"
        ) from exc

    transcribe_handler = TranscribeHandler(
        repos, specs, engine_factory=_engine_factory, workdir=MEDIA_DIR,
        # R58/WQ-02: engine dịch mặc định là DỮ LIỆU của registry (`default_mt`),
        # không phải thứ tự mảng `mt`. Thiếu dây này thì mặc định âm thầm quay về
        # "phần tử đầu tiên", đúng lỗi mà khoá `default_mt` sinh ra để chặn.
        declared_default_mt=load_default_mt(),
    )
    handlers = {
        # I-3 + I-6: handler thật nhận registry và gốc media; thiếu chúng thì nó
        # không thể từ chối sớm một engine mặc định không có, hay một media_path
        # nằm ngoài gốc media.
        "ingest": IngestHandler(repos, specs=specs, media_root=MEDIA_DIR,
                                declared_default_asr=declared_asr),
        "asr": transcribe_handler,
        "export": ExportHandler(repos, out_dir=OUTPUT_DIR),
    }
    broker = JobEventBroker()
    worker = PhaseQueueWorker(repos, governor, handlers, publish=broker.publish)

    # Giai đoạn = (loại job, engine). Governor chỉ đổ được model của một giai
    # đoạn nếu ai đó ĐĂNG KÝ hàm đổ cho giai đoạn đó; không có vòng lặp này thì
    # `before_phase`/`after_phase` là hàm rỗng và model ASR nằm mãi trong VRAM,
    # đúng cái mà hàng đợi theo giai đoạn sinh ra để tránh.
    for spec in specs:
        if spec.kind == "asr":
            # `release()` của TranscribeHandler không nhận tham số và idempotent
            # (worker gọi nó ở cả `before_phase` lẫn `after_phase`).
            governor.register(spec.phase_key, transcribe_handler.release)

    # `TranscribeHandler` coi `auto_forward` vắng mặt là BẬT. Trong Giai đoạn 1a
    # chưa có handler 'translate', nên bật = mỗi nguồn bóc băng xong đẩy một job
    # `translate` vào hàng đợi và worker đánh dấu nó FAILED. Chỉ ghi khi chưa ai
    # đặt, để lựa chọn của người dùng không bị ghi đè.
    if repos.get_setting(AUTO_FORWARD_SETTING) is None:
        repos.set_setting(AUTO_FORWARD_SETTING, _AUTO_FORWARD_OFF)

    return repos, specs, worker, broker


def build_app(repos, specs, worker, broker) -> FastAPI:
    """Ráp app HTTP từ ĐÚNG những thành phần `build_components()` trả về.

    Tách khỏi `main()` để test gọi được đường dây thật, không phải bản sao của
    nó: bỏ `broker=broker` ở đây là app tự dựng broker riêng và stream câm.
    """
    return create_app(repos=repos, specs=specs, media_dir=MEDIA_DIR,
                      out_dir=OUTPUT_DIR, worker=worker, log_dir=LOG_DIR, broker=broker)


def _prepare_local_model_caches() -> None:
    """Trỏ cache model về ổ D: TRƯỚC khi bất kỳ thư viện nào đọc biến môi trường.

    `huggingface_hub` đọc `HF_HOME` ngay lúc import, và nó được import gián tiếp
    khi `faster_whisper` được nạp. Nên nếu chỉ truyền `download_root=` cho
    faster-whisper thì HuggingFace vẫn có thể rơi vào cache mặc định ở ổ C: —
    chỗ chứa model ~1.6 GB mà dự án cố tình để ngoài repo.
    """
    os.environ.setdefault("HF_HOME", HF_HOME)
    os.environ.setdefault("MODELSCOPE_CACHE", str(pathlib.Path(HF_HOME) / "modelscope"))
    os.environ.setdefault("OLLAMA_MODELS", OLLAMA_MODELS)


def _engine_factory(spec):
    """EngineSpec -> adapter ASR.

    Ánh xạ id -> adapter nằm ở `app.adapters.asr.factory.engine_for`, dùng CHUNG
    với `scripts/smoke_asr.py`: hai bản sao của ánh xạ này là đúng lỗi I-2 (script
    smoke luôn dựng faster-whisper nên báo hỏng sai cho `sensevoice-small`).
    """
    from app.adapters.asr.factory import engine_for

    _prepare_local_model_caches()
    return engine_for(spec, download_root=HF_HOME)


def main() -> None:
    import uvicorn

    repos, specs, worker, broker = build_components()
    worker.recover()
    app = build_app(repos, specs, worker, broker)
    thread = threading.Thread(target=worker.run_forever, name="phase-queue", daemon=True)
    thread.start()
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


if __name__ == "__main__":
    main()
