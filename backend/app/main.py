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
from app.adapters.mt.ollama_mt import OllamaMtEngine
from app.adapters.mt.opus_mt import OpusMtEngine
from app.adapters.mt.prompts import PROMPT_VERSION
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.adapters.registry_file import load_default_asr, load_default_mt, load_registry
from app.api.app import create_app
from app.api.sse import JobEventBroker
from app.config import (API_HOST, API_PORT, DB_PATH, HF_HOME, LOG_DIR, MEDIA_DIR,
                        OUTPUT_DIR, OLLAMA_MODELS, ensure_dirs)
from app.pipeline.export import ExportHandler
from app.pipeline.ingest import IngestHandler
from app.pipeline.transcribe import AUTO_FORWARD_SETTING, TranscribeHandler
from app.pipeline.translate import TranslateHandler
from app.registry import (ASR_DEFAULT_SETTING, DEFAULT_MT_KEY, MT_DEFAULT_SETTING,
                          by_id, default_asr_engine, default_mt_engine,
                          ollama_available)
from app.worker import PhaseQueueWorker

#: `auto_forward` nay mặc định BẬT: từ Task 12 đã có handler `translate` thật,
#: nên bóc băng xong đẩy một job dịch là đường đi ĐÚNG, không còn là đường đẻ ra
#: job chắc chắn FAILED như Giai đoạn 1a.
_AUTO_FORWARD_ON = "1"


def _mark_availability(specs) -> None:
    """Ghi `capabilities["available"]` cho mọi engine DỊCH, dò Ollama MỘT lần.

    `EngineSpec` là dataclass `frozen` nhưng `capabilities` là dict nên sửa tại
    chỗ được — và phải sửa tại chỗ, vì chính danh sách `specs` này là thứ
    `GET /api/registry` và `mt_engines` cùng đọc.

    Fix round 1 (I-1): `available` nghĩa là "engine này phục vụ được job NGAY BÂY
    GIỜ", không phải "tiến trình Ollama có sống". Với `runtime == "ollama"` điều
    đó cần HAI thứ: tiến trình trả lời được VÀ `spec.model_ref` có trong
    `/api/tags` (đã pull). "Ollama sống" là điều kiện cần nhưng KHÔNG đủ — nó là
    tín hiệu riêng của `/api/status`. Bản cũ chỉ kiểm điều kiện cần, nên trên máy
    chỉ pull `qwen2.5:3b-instruct-q4_K_M` thì `GET /api/registry` vẫn khai
    `available: true` cho `qwen2.5-7b`/`hy-mt-1.5-7b`: người dùng chọn một engine
    mà API nói đã sẵn sàng rồi job chết ở tận worker — đúng lớp lỗi I-3 của GĐ1a.

    Phép dò trả về TÊN model đã pull (`set()` khi không dùng được), nên ở đây chỉ
    còn một phép kiểm thành viên cho mỗi engine. `runtime == "inprocess"` ⇒ `True`:
    không có tiến trình ngoài nào để hỏi, và việc dựng được engine in-process được
    ghim bằng `test_real_mt_engines_are_constructible_from_the_shipped_registry`
    (adapter THẬT, registry THẬT).
    """
    pulled: set[str] | None = None
    for spec in specs:
        if spec.kind != "mt":
            continue
        if spec.runtime == "ollama":
            if pulled is None:
                pulled = ollama_available()
            spec.capabilities["available"] = spec.model_ref in pulled
        else:
            spec.capabilities["available"] = True


def _build_mt_engines(specs) -> dict[str, object]:
    """`{spec.id: engine}` cho mọi engine dịch ĐANG sẵn sàng.

    Khoá là `spec.id` của registry, KHÔNG phải `engine.engine_id`: quy tắc suy
    `engine_id` từ tag không tái tạo được id registry cho HY-MT
    (`hy-mt1.5-7b-q4_K_M` vs `hy-mt-1.5-7b`), nên đánh khoá theo engine sẽ
    `KeyError` ngay khi có người chọn HY-MT.

    Cờ glossary là DỮ LIỆU của `spec.capabilities["glossary_prompt"]`, không
    phải hằng số của adapter: QA gắn `engine_no_glossary` theo cờ đó.

    Fix round 1 (I-2): `engine_id=spec.id` được truyền TƯỜNG MINH. `spec.id` là
    NGUỒN CHÂN LÝ, không phải quy tắc suy từ tag: tag của HY-MT cho ra
    `hy-mt1.5-7b-q4_K_M` còn id registry là `hy-mt-1.5-7b`, nên để adapter tự
    suy là ghi `prompt_version` tra theo một id không tồn tại. Truyền id vào biến
    cảnh báo "Task 12 phải đánh khoá theo `spec.id`" từ một câu trong docstring
    thành một dây nối chạy được.
    """
    engines: dict[str, object] = {}
    for spec in specs:
        if spec.kind != "mt" or not spec.capabilities.get("available"):
            continue
        if spec.runtime == "ollama":
            engines[spec.id] = OllamaMtEngine(
                spec.model_ref,
                engine_id=spec.id,
                supports_glossary=bool(spec.capabilities.get("glossary_prompt", False)),
            )
        else:
            engines[spec.id] = OpusMtEngine(spec.model_ref)
    return engines


def build_components():
    """Dựng repos, specs, worker, MỘT broker và `mt_engines` đã nối dây.

    Không chạy vòng lặp, không mở mạng (trừ một lần dò Ollama lúc dựng). Broker
    trả về ở đây là đường dây duy nhất nối worker với `/api/jobs/stream`: worker
    publish vào nó, `build_app()` truyền chính nó cho `create_app()`. Dựng hai
    broker riêng thì stream không bao giờ nhận được gì — job chạy xong mà giao
    diện đứng im.
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

    # WQ-02/F3: engine DỊCH mặc định phải được kiểm ở CÙNG chỗ sớm nhất, cùng
    # bảo đảm như ASR. Thiếu phép kiểm này thì một `default_mt` gõ sai trong
    # `registry.json` im lặng trở thành engine của MỌI job translate (GĐ1a chưa
    # có handler `translate` nên nó chỉ FAILED ở tận worker) — hai đường mặc
    # định cùng họ mà khác bảo đảm là bất nhất quán.
    declared_mt = load_default_mt()
    try:
        mt_engine_id = default_mt_engine(specs, declared=declared_mt,
                                         configured=repos.get_setting(MT_DEFAULT_SETTING))
    except KeyError as exc:
        raise RuntimeError(
            f"cấu hình engine dịch mặc định không dùng được: {exc}"
        ) from exc

    # Task 12: `available` phải có TRƯỚC khi dựng engine, vì nó quyết định engine
    # nào tồn tại. Dò ở đây (một lần) chứ không ở mỗi request.
    _mark_availability(specs)

    # Correction C của Task 13 (Important mang từ Task 12): TỒN TẠI là chưa đủ —
    # engine mặc định còn phải SẴN SÀNG. `available=False` chỉ đóng dropdown của
    # giao diện, nó KHÔNG đóng đường setting/`default_mt`: đặt
    # `MT_DEFAULT_SETTING='hy-mt-1.5-7b'` trên máy chưa pull model đó vẫn sinh
    # một hàng `translations` (`engine='hy-mt-1.5-7b'`, `status='queued'`) rồi job
    # chết `KeyError` ở tận worker — đo thật ở re-review Task 12. Cùng bài học
    # I-3: *fail ở chỗ sớm nhất*. Phép kiểm đứng SAU `_mark_availability` vì cờ
    # đó là thứ nó đọc.
    #
    # `default_mt` đã ship là `opus-mt` (`runtime == "inprocess"` ⇒ luôn
    # `available`), nên khởi động bình thường không đổi hành vi.
    if mt_engine_id is not None and not by_id(
            specs, mt_engine_id).capabilities.get("available"):
        raise RuntimeError(
            f"engine dịch mặc định {mt_engine_id!r} không sẵn sàng: nó có trong "
            f"registry nhưng model chưa được pull hoặc runtime không phục vụ "
            f"được. Sửa {DEFAULT_MT_KEY!r} trong registry.json hoặc setting "
            f"{MT_DEFAULT_SETTING!r} sang một engine đang sẵn sàng "
            f"(GET /api/registry trả `available` cho từng engine)."
        )

    # Task 13 (correction B): `prompt_version` là DỮ LIỆU DẪN XUẤT của
    # composition root, tính MỘT lần ở đây rồi đặt cạnh `available` trong
    # `spec.capabilities`. Route bản dịch KHÔNG được import `app.adapters` (đã có
    # test canh: `test_api_layer_does_not_import_adapters`), nên đây là chỗ duy
    # nhất nối `adapters/mt/prompts.py` với tầng HTTP. `TranscribeHandler` nhận
    # CÙNG dict này — hai nơi cùng ghi `translations.prompt_version` thì phải đọc
    # cùng một nguồn, không phải hai bản sao của cùng một biểu thức.
    prompt_versions = {spec.id: PROMPT_VERSION.get(spec.id, "unknown")
                       for spec in specs if spec.kind == "mt"}
    for spec in specs:
        if spec.kind == "mt":
            spec.capabilities["prompt_version"] = prompt_versions[spec.id]

    mt_engines = _build_mt_engines(specs)

    transcribe_handler = TranscribeHandler(
        repos, specs, engine_factory=_engine_factory, workdir=MEDIA_DIR,
        # R58/WQ-02: engine dịch mặc định là DỮ LIỆU của registry (`default_mt`),
        # không phải thứ tự mảng `mt`. Thiếu dây này thì mặc định âm thầm quay về
        # "phần tử đầu tiên", đúng lỗi mà khoá `default_mt` sinh ra để chặn.
        declared_default_mt=declared_mt,
        # `_forward_to_translation` phải tạo hàng `translations` kèm
        # `prompt_version`, mà giá trị đó là dữ liệu của `adapters/mt/prompts.py`
        # — composition root là chỗ duy nhất được phép biết adapter. Dùng LẠI
        # đúng dict đã đặt vào `spec.capabilities` ở trên: hai đường cùng ghi
        # `translations.prompt_version` mà tính riêng thì chúng trôi khỏi nhau.
        prompt_versions=prompt_versions,
    )
    handlers = {
        # I-3 + I-6: handler thật nhận registry và gốc media; thiếu chúng thì nó
        # không thể từ chối sớm một engine mặc định không có, hay một media_path
        # nằm ngoài gốc media.
        "ingest": IngestHandler(repos, specs=specs, media_root=MEDIA_DIR,
                                declared_default_asr=declared_asr),
        "asr": transcribe_handler,
        # Task 12: cùng lớp lỗi với `publish=` bị bỏ quên ở Giai đoạn 1a — dựng
        # `TranslateHandler` mà KHÔNG trao `mt_engines` thì mọi job dịch tự sinh
        # `KeyError` trong handler, và bóc băng xong chẳng có bản dịch nào.
        "translate": TranslateHandler(repos, mt_engines),
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

    # Cùng lý do với ASR, cho MỌI engine dịch đã dựng: engine dịch nằm trong
    # `mt_engines` chứ không trong handler, nên không đăng ký ở đây thì không ai
    # đổ model Ollama khi rời giai đoạn dịch. Khoá giai đoạn lấy từ
    # `spec.phase_key` (đi qua `phase_of`), không tự nối chuỗi từ `kind`.
    for engine_id, engine in mt_engines.items():
        spec = next(s for s in specs if s.id == engine_id)
        governor.register(spec.phase_key, engine.release)

    # `TranscribeHandler` coi `auto_forward` vắng mặt là BẬT, và từ Task 12 điều
    # đó là ĐÚNG: đã có handler `translate` thật. Chỉ ghi khi chưa ai đặt, để lựa
    # chọn của người dùng không bị ghi đè.
    if repos.get_setting(AUTO_FORWARD_SETTING) is None:
        repos.set_setting(AUTO_FORWARD_SETTING, _AUTO_FORWARD_ON)

    return repos, specs, worker, broker, mt_engines


def build_app(repos, specs, worker, broker) -> FastAPI:
    """Ráp app HTTP từ ĐÚNG những thành phần `build_components()` trả về.

    Tách khỏi `main()` để test gọi được đường dây thật, không phải bản sao của
    nó: bỏ `broker=broker` ở đây là app tự dựng broker riêng và stream câm.

    M-13: KHÔNG nhận `mt_engines`. App HTTP không có chỗ nào đọc dict engine, và
    người dùng thật của nó là `TranslateHandler` — đã nhận nó trong
    `build_components()`. Truyền thêm vào đây chỉ để gán một thuộc tính `app.state`
    không ai đọc, kèm một comment khẳng định tầng HTTP cần nó.
    """
    return create_app(repos=repos, specs=specs, media_dir=MEDIA_DIR,
                      out_dir=OUTPUT_DIR, worker=worker, log_dir=LOG_DIR,
                      broker=broker)


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

    # M-13: `mt_engines` KHÔNG đi vào app HTTP nữa (nó chỉ thuộc về
    # `TranslateHandler`, đã nhận ở `build_components()`), nhưng nó vẫn là phần
    # tử CUỐI của tuple trả về — đó là hợp đồng đã được ghim, và `main()` vẫn
    # phải giải nén đủ năm phần tử.
    repos, specs, worker, broker, _mt_engines = build_components()
    worker.recover()
    app = build_app(repos, specs, worker, broker)
    thread = threading.Thread(target=worker.run_forever, name="phase-queue", daemon=True)
    thread.start()
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


if __name__ == "__main__":
    main()
