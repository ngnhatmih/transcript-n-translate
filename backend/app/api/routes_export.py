"""Route export: xếp một job `export`, rồi phục vụ tệp mà handler đã ghi.

Hai quyết định ở đây, cả hai đều là ranh giới an ninh:

* **`stem` là dữ liệu BÊN NGOÀI.** Nó đi vào payload job (và job có thể được
  tạo từ bất kỳ client nào), nên nó bị cắt về TÊN TRẦN (`safe_basename`) ngay
  lúc tạo job — cùng phép cắt mà route upload dùng cho `filename`. Handler cắt
  lại một lần nữa; hai lớp vì payload job là dữ liệu đọc từ DB, không phải giá
  trị ta vừa kiểm.
* **Đường dẫn tải về được CHỨNG MINH nằm trong `out_dir`** (`resolve_within`)
  trước khi mở. Tên tệp đã là tên trần, nhưng `out_dir` có thể chứa symlink và
  so chuỗi tiền tố không bắt được `..` lẫn junction.
* **Tên tệp do `pipeline/export.py:artifact_name()` sinh ra**, không tự ghép ở
  đây: handler là bên thật sự ghi tệp, và hai chỗ tự ghép tên thì trôi khỏi
  nhau (`.vi` khi có bản dịch).
"""
from __future__ import annotations

import logging
import pathlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.api.deps import get_dirs, get_repos
from app.domain import job_state as js
from app.domain.models import Job
from app.domain.paths import InvalidBasename, PathOutsideRoot, resolve_within, safe_basename
from app.pipeline.export import FORMATS, MEDIA_TYPES, artifact_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["export"])


class ExportIn(BaseModel):
    transcript_id: int
    format: str = "srt"
    bilingual: bool = False
    stem: str | None = None


def _safe_stem(raw: str | None, transcript_id: int) -> str:
    """`stem` của client -> tên trần, hoặc tên mặc định theo id.

    Tên KHÔNG phải tên tệp (`""`, `"."`, `".."`) là lỗi ĐẦU VÀO (422), không
    được âm thầm đổi thành tên mặc định: người dùng gõ `..` thì phải biết là
    mình gõ sai.
    """
    if not raw:
        return f"transcript-{transcript_id}"
    try:
        return safe_basename(raw, fallback=f"transcript-{transcript_id}")
    except InvalidBasename as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("", status_code=201)
def create_export(payload: ExportIn, repos=Depends(get_repos)):
    fmt = payload.format.lower()
    if fmt not in FORMATS:
        raise HTTPException(
            422, f"định dạng không hỗ trợ: {payload.format!r}"
                 f" (có: {sorted(FORMATS)})")

    try:
        repos.get_transcript(payload.transcript_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    stem = _safe_stem(payload.stem, payload.transcript_id)
    job = Job(id=None, workspace=1, type="export", engine=None,
              phase=js.phase_of("export", None),
              payload={"transcript_id": payload.transcript_id, "format": fmt,
                       "bilingual": payload.bilingual, "stem": stem})
    job.id = repos.add_job(job)
    stored = repos.get_job(job.id)
    return {"id": stored.id, "type": stored.type, "phase": stored.phase,
            "state": stored.state, "payload": stored.payload}


@router.get("/{job_id}/download", response_class=PlainTextResponse)
def download(job_id: int, repos=Depends(get_repos), dirs=Depends(get_dirs)):
    try:
        job = repos.get_job(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    if job.type != "export":
        raise HTTPException(422, "job này không phải job xuất tệp")
    if job.state != js.DONE:
        # 409 chứ không 404: tệp CHƯA có vì job chưa xong, không phải vì không
        # có gì để tải. Client phải chờ, không phải đi tìm chỗ khác.
        raise HTTPException(409, f"job chưa xong (đang ở {job.state})")

    raw_stem = job.payload.get("stem")
    stem = _safe_stem(str(raw_stem) if raw_stem else None,
                      int(job.payload.get("transcript_id", 0)))
    fmt = str(job.payload.get("format", "srt")).lower()
    if fmt not in FORMATS:
        raise HTTPException(422, f"định dạng không hỗ trợ: {fmt!r}")
    translated = job.payload.get("translations") is not None
    out_dir = pathlib.Path(dirs["out"])
    name = artifact_name(stem, fmt, translated=translated)

    # NEO vào `out_dir` TRƯỚC khi phân giải: `resolve_within` phân giải ứng viên
    # theo thư mục làm việc của tiến trình, nên một tên trần như
    # `transcript-1.srt` sẽ được phân giải thành `<cwd>/transcript-1.srt` — nằm
    # ngoài `out_dir` — và mọi lần tải về đều 403 dù tệp có thật. Phép kiểm chỉ
    # có nghĩa khi ứng viên đã đi qua `out_dir`.
    try:
        path = resolve_within(out_dir, out_dir / name)
    except PathOutsideRoot as exc:
        # Câu trả lời cho client là CHUNG: chi tiết đường dẫn đã phân giải là
        # bản đồ hệ tệp. Chi tiết còn nguyên cho người vận hành, ở log.
        logger.warning("từ chối tệp xuất ngoài gốc: job_id=%s: %s", job_id, exc)
        raise HTTPException(403, "đường dẫn xuất nằm ngoài thư mục output") from exc

    if not path.is_file():
        raise HTTPException(410, f"tệp xuất không còn: {path.name}")

    return PlainTextResponse(path.read_text(encoding="utf-8"),
                             media_type=MEDIA_TYPES.get(fmt, "text/plain"))
