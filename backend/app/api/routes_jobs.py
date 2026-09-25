"""Route hàng đợi job: tạo, liệt kê, xem, huỷ, chạy lại, và stream SSE.

Route KHÔNG chạy job. Nó chỉ ghi một hàng `jobs` rồi để worker (luồng riêng)
bốc. Nhờ vậy `POST /api/jobs` trả về ngay cả khi engine ASR đang nạp model.

Route cũng KHÔNG phát sự kiện SSE: nguồn sự kiện duy nhất là worker, để một
client không bao giờ nhận hai sự kiện cho cùng một lần đổi trạng thái.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_repos, get_specs
from app.api.sse import JobEventBroker, stream_events
from app.domain import job_state as js
from app.domain.models import Job
from app.registry import by_id

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

JOB_TYPES = {"ingest", "asr", "translate", "export"}
ENGINE_REQUIRED = {"asr", "translate"}


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


@router.post("", status_code=201)
def create_job(payload: JobIn, repos=Depends(get_repos), specs=Depends(get_specs)):
    # `workspace` đã bị `JobIn` chặn ngoài 1..2 -> 422 của FastAPI, không tới đây.
    if payload.type not in JOB_TYPES:
        raise HTTPException(422, f"loại job không hợp lệ: {payload.type!r}")
    if payload.type in ENGINE_REQUIRED:
        if not payload.engine:
            raise HTTPException(422, f"job loại {payload.type} phải có engine")
        try:
            by_id(specs, payload.engine)
        except KeyError as exc:
            raise HTTPException(422, str(exc)) from exc

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
    return StreamingResponse(
        stream_events(broker),
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
    try:
        repos.request_cancel(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    job = repos.get_job(job_id)
    # Job CHƯA chạy thì huỷ là xong ngay (spec §5.4). Job đang chạy chỉ được ĐẶT
    # CỜ: worker thấy cờ ở checkpoint kế tiếp rồi mới chuyển trạng thái. Kill
    # tiến trình sẽ để DB nửa vời và model đang nạp không được đổ.
    if job.state == js.QUEUED:
        repos.set_job_state(job_id, js.CANCELLED)
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
