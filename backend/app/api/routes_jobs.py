"""Route hàng đợi job: tạo, liệt kê, xem, huỷ, chạy lại, và stream SSE.

Route KHÔNG chạy job. Nó chỉ ghi một hàng `jobs` rồi để worker (luồng riêng)
bốc. Nhờ vậy `POST /api/jobs` trả về ngay cả khi engine ASR đang nạp model.

Route cũng KHÔNG phát sự kiện SSE: nguồn sự kiện duy nhất là worker, để một
client không bao giờ nhận hai sự kiện cho cùng một lần đổi trạng thái.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

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
    """`TranscribeHandler.run` đọc `payload["source_id"]` (transcribe.py).

    `vung_doc` = `[x0, y0, x1, y1]` theo TỈ LỆ khung (0..1), vùng OCR được đọc. Đây là
    tham số của LƯỢT GỌI chứ không phải của registry, vì vùng watermark phụ thuộc VIDEO:
    đo được `8f4b5304daf42569.mp4` (1080×1920) có watermark ở `y=35-102` còn
    `ac5df767b9e0c878.mp4` (1280×720) ở chỗ khác. Một con số chung trong registry đúng
    cho video này và sai cho video kia.

    `None` = dùng `opts.vung_doc` của registry (mặc định hiện tại `[0, 0.1, 1, 1]`).
    `[]` = TẮT lọc vùng, đọc cả khung — đó là cách giao diện biểu diễn nút ×.
    """

    source_id: int = Field(ge=1)
    lang: str | None = None
    vung_doc: list[float] | None = None

    @field_validator("vung_doc")
    @classmethod
    def _kiem_vung_doc(cls, v: list[float] | None) -> list[float] | None:
        """Ba trạng thái hợp lệ: `None` (mặc định), `[]` (TẮT), bốn số đúng thứ tự.

        🔴 VÌ SAO KIỂM NGỮ NGHĨA Ở ĐÂY (đo được, đây là lỗi thật đã sửa): bản đầu khai
        `min_length=0, max_length=4` — chỉ chặn SỐ PHẦN TỬ. Đo trên container:
        `POST /api/jobs` với `vung_doc: [0, 0, 1]` (BA số) trả **201**, job vào hàng đợi,
        rồi `_vung_doc_tu_payload` mới ném `ValueError` ở worker ⇒ job `failed`. Hai tầng
        không khớp nhau: cửa nhận thứ mà nhà từ chối.

        Nặng hơn là trường hợp ĐẢO: `[1, 0.1, 0, 1]` cũng trả 201. Một vùng đảo lọc sạch
        mọi hộp ⇒ OCR trả `[]` "hợp lệ" ⇒ pipeline lặng lẽ rơi về ASR mà không ai biết
        vì sao. Đó đúng là kiểu hỏng mà cả nhánh OCR vừa phải sửa ba lần, nên nó phải
        bị chặn Ở CỬA.
        """
        if v is None or len(v) == 0:
            return v
        if len(v) != 4:
            raise ValueError(
                f"vung_doc phải có đúng 4 số [x0, y0, x1, y1] theo tỉ lệ khung, "
                f"hoặc [] để tắt lọc vùng; nhận được {len(v)} số: {v!r}"
            )
        if not all(0.0 <= x <= 1.0 for x in v):
            raise ValueError(f"vung_doc phải nằm trong [0, 1] (tỉ lệ khung): {v!r}")
        x0, y0, x1, y1 = v
        if not (x0 < x1 and y0 < y1):
            raise ValueError(
                f"vung_doc phải thoả x0 < x1 và y0 < y1 (thứ tự [x0, y0, x1, y1]): {v!r}"
            )
        return v


class DubPayload(BaseModel):
    """`DubHandler.run` đọc `payload["translation_id"]` (pipeline/dub.py).

    `voice` là tên giọng dựng sẵn của engine TTS; bỏ trống = giọng mặc định của engine.
    `so_dong` là GIỚI HẠN số dòng — có mặt để đo/thử nhanh trên một bản dịch dài, không phải
    một tính năng sản phẩm (UI không gửi nó).
    """

    translation_id: int = Field(ge=1)
    voice: str | None = None
    so_dong: int | None = Field(default=None, ge=1)
    #: Kiểu chữ phụ đề BURN vào video — cùng khối với `POST /api/dubs` và
    #: `GET /api/export/{id}?style=…`. Vắng mặt = mặc định của định dạng.
    tron_nen: bool | None = None
    style: dict | None = None


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
    "dub": DubPayload,
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
    # ───────────────────────────────────────────────────────────────────────
    # JOB `asr` CẦN NGUỒN ĐÃ CÓ AUDIO — chặn Ở CỬA, không để nó chết ở worker.
    #
    # ĐO ĐƯỢC (lỗi thật, người dùng báo "mở một video khác thì hàng đợi ko thấy gì"):
    # nạp video mới -> `ingest` xếp hàng -> bấm "Phiên âm" NGAY -> giao diện gửi
    # `POST /api/jobs` luôn, không chờ `ingest` xong. Route trả **201**, job vào hàng
    # đợi, rồi `transcribe.py:212` ném:
    #
    #     FileNotFoundError: source 6 chưa có audio; job ingest phải chạy trước
    #
    # Đo trên hàng đợi thật: #94 `ingest` source 6, #95 và #96 `asr` source 6 — hai
    # job CHẮC CHẮN HỎNG đang chờ. Tệ hơn: `worker.tick()` chạy hết job của GIAI ĐOẠN
    # hiện tại trước khi đổi giai đoạn, nên hai job asr chết kia còn nằm TRƯỚC `ingest`
    # và làm nó chờ lâu hơn. Người dùng thấy hàng đợi như đứng im.
    #
    # Vì sao chặn ở ROUTE chứ không chỉ ở giao diện: bất kỳ client nào (script, curl,
    # lần sửa giao diện sau) cũng tạo được job chết. Cửa nhận thứ mà nhà từ chối là
    # đúng lớp lỗi đã sửa ba lần ở nhánh OCR.
    #
    # `duration` cũng do `ingest` đặt, nhưng điều kiện ĐÚNG là `audio_path`: chính
    # `TranscribeHandler` đọc nó để mở tệp. Kiểm `duration` sẽ chặn nhầm một nguồn có
    # audio hợp lệ mà ffprobe không đọc được độ dài.
    # ───────────────────────────────────────────────────────────────────────
    if payload.type == "asr":
        source_id = payload.payload["source_id"]
        try:
            nguon = repos.get_source(int(source_id))
        except LookupError as exc:
            raise HTTPException(404, f"source {source_id} không tồn tại") from exc
        if not nguon.audio_path:
            raise HTTPException(
                409,
                f"source {source_id} chưa có âm thanh — job `ingest` phải chạy trước. "
                "Video vừa nạp cần được bóc âm thanh xong mới bóc băng được; "
                "xem hàng đợi để biết job ingest đang ở đâu.",
            )
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
