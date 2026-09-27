"""Route hàng đợi job: tạo, liệt kê, xem, huỷ, chạy lại, và stream SSE.

Route KHÔNG chạy job. Nó chỉ ghi một hàng `jobs` rồi để worker (luồng riêng)
bốc. Nhờ vậy `POST /api/jobs` trả về ngay cả khi engine ASR đang nạp model.

Route cũng KHÔNG phát sự kiện SSE: nguồn sự kiện duy nhất là worker, để một
client không bao giờ nhận hai sự kiện cho cùng một lần đổi trạng thái.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.api.deps import get_repos, get_specs
from app.api.sse import JobEventBroker, stream_events
from app.domain import job_state as js
from app.domain.models import Job, translation_id_of
from app.registry import by_id

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ENGINE_REQUIRED = {"asr"}


class IngestPayload(BaseModel):
    """`IngestHandler.run` đọc `payload["source_id"]` (ingest.py)."""

    source_id: int = Field(ge=1)


class AsrPayload(BaseModel):
    """`TranscribeHandler.run` đọc `payload["source_id"]` (transcribe.py)."""

    source_id: int = Field(ge=1)
    lang: str | None = None


class ExportPayload(BaseModel):
    """`ExportHandler.run` đọc `payload["transcript_id"]` (export.py)."""

    transcript_id: int = Field(ge=1)
    format: str | None = None
    bilingual: bool = False
    stem: str | None = None
    translations: list | None = None


#: I-5: hợp đồng payload theo từng loại job. Đây là DANH SÁCH TRẮNG: một loại
#: không có ở đây bị từ chối 422, vì không có handler nào đọc payload của nó
#: (`translate` là ca thật của GĐ1a — hàng đợi chỉ đánh dấu nó FAILED).
PAYLOAD_SCHEMA: dict[str, type[BaseModel]] = {
    "ingest": IngestPayload,
    "asr": AsrPayload,
    "export": ExportPayload,
}

JOB_TYPES = frozenset(PAYLOAD_SCHEMA)


class JobIn(BaseModel):
    workspace: int = Field(ge=1, le=2)
    type: str
    engine: str | None = None
    payload: dict = Field(default_factory=dict)


def _job_json(job: Job) -> dict:
    return {
        "id": job.id, "workspace": job.workspace, "type": job.type,
        "engine": job.engine, "phase": job.phase, "state": job.state,
        "cancel_requested": job.cancel_requested, "attempts": job.attempts,
        "progress": job.progress, "log_tail": job.log_tail, "error": job.error,
        "payload": job.payload, "created_at": job.created_at,
        "started_at": job.started_at, "finished_at": job.finished_at,
    }


def _registered_job_types(request: Request) -> set[str]:
    """Loại job có handler THẬT trong tiến trình này.

    App ráp đủ (`app/main.py`) có `worker`, nên đây là danh sách `handles()` đã
    đăng ký — thêm một handler mà quên hợp đồng payload thì nó không được nhận.
    App chỉ để đọc (test dựng `create_app()` không worker) rơi về chính danh sách
    hợp đồng, vì không có gì để hỏi.
    """
    worker = getattr(request.app.state, "worker", None)
    handlers = getattr(worker, "handlers", None) or {}
    registered = {handler.handles() for handler in handlers.values()}
    return registered & set(PAYLOAD_SCHEMA) or set(PAYLOAD_SCHEMA)


def _payload_errors(exc: ValidationError) -> str:
    """Lỗi pydantic -> câu nêu ĐÚNG tên trường, để client sửa được ngay."""
    parts: list[str] = []
    for error in exc.errors():
        field = ".".join(str(piece) for piece in error["loc"]) or "payload"
        parts.append(f"{field}: {error['msg']}")
    return "; ".join(parts)


@router.post("", status_code=201)
def create_job(payload: JobIn, request: Request, repos=Depends(get_repos),
               specs=Depends(get_specs)):
    # `workspace` đã bị `JobIn` chặn ngoài 1..2 -> 422 của FastAPI, không tới đây.
    schema = PAYLOAD_SCHEMA.get(payload.type)
    if schema is None:
        raise HTTPException(
            422, f"loại job không hợp lệ: {payload.type!r} "
                 f"(GĐ1a nhận: {sorted(PAYLOAD_SCHEMA)})")
    registered = _registered_job_types(request)
    if payload.type not in registered:
        raise HTTPException(
            422, f"chưa có handler cho loại job {payload.type!r} "
                 f"(đang có: {sorted(registered)})")
    # I-5: payload được kiểm NGAY ở đây, theo đúng trường mà handler sẽ đọc.
    # Bản cũ nhận mọi payload rồi trả 201, và client chỉ biết mình sai khi job
    # đã nằm trong hàng đợi và `KeyError` nổi lên thành FAILED ở worker.
    try:
        schema.model_validate(payload.payload)
    except ValidationError as exc:
        raise HTTPException(
            422, f"payload của job {payload.type!r} không hợp lệ: "
                 f"{_payload_errors(exc)}") from exc
    if payload.type in ENGINE_REQUIRED:
        if not payload.engine:
            raise HTTPException(422, f"job loại {payload.type} phải có engine")
        try:
            by_id(specs, payload.engine)
        except KeyError as exc:
            # M-14: cùng lỗi, cùng lớp xử lý như `routes_translations.create_translation`
            # — `exc.args[0]` là ĐỐI SỐ TRẦN của `by_id`, còn `str(exc)` repr nó
            # (`str(KeyError("x")) == "'x'"`), tức client nhận thêm một cặp nháy
            # kép và cùng một lỗi có hai hình dạng ở hai route.
            raise HTTPException(422, exc.args[0]) from exc

    job = Job(id=None, workspace=payload.workspace, type=payload.type,
              engine=payload.engine,
              phase=js.phase_of(payload.type, payload.engine),
              payload=payload.payload)
    job.id = repos.add_job(job)
    return _job_json(repos.get_job(job.id))


# PHẢI khai báo TRƯỚC "/{job_id}", nếu không FastAPI khớp "stream" vào job_id -> 422
@router.get("/stream")
def stream(request: Request):
    broker: JobEventBroker = request.app.state.broker
    repos = request.app.state.repos
    # Ảnh chụp là CALLABLE: `stream_events` chỉ gọi nó SAU khi đã subscribe, nên
    # một chuyển trạng thái rơi vào cửa sổ "chụp -> nghe" không thể mất.
    return StreamingResponse(
        stream_events(broker, snapshot=lambda: [j.to_event() for j in repos.list_jobs()]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("")
def list_jobs(repos=Depends(get_repos)):
    return [_job_json(j) for j in repos.list_jobs()]


@router.get("/{job_id}")
def get_job(job_id: int, repos=Depends(get_repos)):
    try:
        return _job_json(repos.get_job(job_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, repos=Depends(get_repos)):
    # `request_cancel` là UPDATE mù (0 hàng, không ném), nên lần đọc lại phải
    # nằm TRONG cùng khối `try`: job không tồn tại là 404 như mọi route anh em,
    # không phải 500.
    try:
        repos.request_cancel(job_id)
        job = repos.get_job(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    # Job CHƯA chạy thì huỷ là xong ngay (spec §5.4). Job đang chạy chỉ được ĐẶT
    # CỜ: worker thấy cờ ở checkpoint kế tiếp rồi mới chuyển trạng thái. Kill
    # tiến trình sẽ để DB nửa vời và model đang nạp không được đổ.
    if job.state == js.QUEUED:
        repos.set_job_state(job_id, js.CANCELLED)
        # Hàng `translations` phải theo job, không chỉ bảng `jobs`: một job dịch
        # bị huỷ lúc còn `queued` không bao giờ chạy handler, nên nếu chỉ
        # `set_job_state` thì hàng dịch đứng nguyên ở `queued` VĨNH VIỄN và
        # `GET /api/translations` (Task 13 phơi `status`) hiện một bản dịch "đang
        # chờ" không còn job nào đứng sau.
        #
        # CHỈ nhánh `queued`. Job đang `running` chỉ được đặt cờ ở đây — nó vẫn
        # có thể chạy xong trước checkpoint kế tiếp, và ghi `cancelled` ngay lúc
        # này sẽ chốt trước một kết quả chưa xảy ra (worker ghi kết luận thật ở
        # ranh giới job: `TranslateHandler` tự ghi `cancelled` khi thấy cờ, còn
        # `worker._run_one` đối chiếu hàng dịch ở nhánh huỷ sau `run()`).
        translation_id = translation_id_of(job)
        if translation_id is not None:
            repos.set_translations_status([translation_id], js.CANCELLED)
    return _job_json(repos.get_job(job_id))


@router.post("/{job_id}/retry")
def retry_job(job_id: int, repos=Depends(get_repos)):
    try:
        job = repos.get_job(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    # `REPOS.retry_job()` cũng gọi `assert_transition` và ném `InvalidTransition`
    # (một `ValueError`) — không bắt ở đây thì job ở trạng thái không chạy lại
    # được sẽ trả 500. Bảng transition không phải lỗi máy chủ.
    if job.state not in js.RETRYABLE_STATES:
        raise HTTPException(
            409, f"chỉ chạy lại được job ở trạng thái {sorted(js.RETRYABLE_STATES)}")
    repos.retry_job(job_id)
    return _job_json(repos.get_job(job_id))
