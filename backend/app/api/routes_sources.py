"""Route nguồn vào: tải tệp lên, dán link, liệt kê, xem chi tiết.

Route KHÔNG tự chạy pipeline. Nó lưu media + một hàng `sources`, rồi xếp một job
`ingest`; worker (một luồng riêng) mới thật sự chạm ffmpeg. Nhờ vậy một tệp 2 GB
không giữ request HTTP mở suốt thời gian bóc âm thanh.
"""
from __future__ import annotations

import pathlib
from typing import BinaryIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, field_validator
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_dirs, get_repos
from app.domain import job_state as js
from app.domain.models import Job, Source
from app.domain.paths import InvalidBasename, PathOutsideRoot, resolve_within, safe_basename
from app.pipeline import ingest

router = APIRouter(prefix="/api/sources", tags=["sources"])

ALLOWED_LANGS = {"zh", "en"}
DEFAULT_LANG = "zh"
_CHUNK = 1024 * 1024


class UrlIn(BaseModel):
    url: str
    lang: str = DEFAULT_LANG

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("chỉ nhận http/https")
        return v

    @field_validator("lang")
    @classmethod
    def _known_lang(cls, v: str) -> str:
        if v not in ALLOWED_LANGS:
            raise ValueError(f"ngôn ngữ không hỗ trợ: {v!r}")
        return v


def _source_json(source: Source) -> dict:
    return {
        "id": source.id, "kind": source.kind, "origin": source.origin,
        "media_path": source.media_path, "audio_path": source.audio_path,
        "duration": source.duration, "lang": source.lang,
        "created_at": source.created_at,
    }


def _job_json(job: Job) -> dict:
    return {"id": job.id, "workspace": job.workspace, "type": job.type,
            "engine": job.engine, "phase": job.phase, "state": job.state}


def _enqueue_ingest(repos, source_id: int, lang: str) -> Job:
    job = Job(id=None, workspace=1, type="ingest", engine=None,
              phase=js.phase_of("ingest", None),
              payload={"source_id": source_id, "lang": lang})
    job.id = repos.add_job(job)
    return job


def _require_lang(lang: str) -> str:
    if lang not in ALLOWED_LANGS:
        raise HTTPException(422, f"ngôn ngữ không hỗ trợ: {lang!r}")
    return lang


def _safe_name(name: str | None, fallback: str = "upload.bin") -> str:
    """Tên tệp do client gửi -> tên trần, không có thành phần đường dẫn.

    Không có bước này thì `../` trong `filename` ghi được ra ngoài `media_dir`.

    Tên KHÔNG phải tên tệp (`""`, `"."`, `".."`) là lỗi ĐẦU VÀO, không phải lỗi
    máy chủ: `pathlib.Path("..").name` vẫn là `".."`, nên `media_dir / ".."` là
    thư mục CHA và `open(target, "wb")` nổ 500.
    """
    try:
        return safe_basename(name, fallback)
    except InvalidBasename as exc:
        raise HTTPException(422, str(exc)) from exc


def _copy_upload(src: BinaryIO, target: pathlib.Path) -> int:
    """Chép tệp tải lên xuống đĩa, trả về số byte. Hàm ĐỒNG BỘ (chạy threadpool).

    Cả vòng lặp nằm trong MỘT hàm đồng bộ, không phải `await file.read()` từng
    khối: `open()` và từng `write()` đều là lệnh chặn, nên nếu chúng chạy trong
    thân route `async def` thì mỗi khối 1 MiB lại treo event loop một nhịp.
    `UploadFile.file` là tệp tạm mà Starlette đã ghi xong TRƯỚC khi route chạy,
    nên đọc nó chỉ là đọc tệp thường — không cần `await`.
    """
    size = 0
    with open(target, "wb") as fh:
        while chunk := src.read(_CHUNK):
            size += len(chunk)
            fh.write(chunk)
    return size


@router.post("/upload", status_code=201)
async def upload(file: UploadFile = File(...), lang: str = Form(DEFAULT_LANG),
                 repos=Depends(get_repos), dirs=Depends(get_dirs)):
    lang = _require_lang(lang)

    media_dir: pathlib.Path = dirs["media"]
    target = media_dir / _safe_name(file.filename)
    # Mọi thứ chạm đĩa đi qua threadpool. Route này là `async def`, nên `open()`,
    # vòng `write`, `sha256_file` và `replace` chạy thẳng ở đây sẽ chặn event
    # loop: một tệp 2 GB giữ server đứng suốt lượt băm, `/api/jobs/stream` không
    # gửi được gì. `run_in_threadpool` cũng là chốt chặn cuối: kể cả một tên tệp
    # lọt qua `_safe_name` mà chặn đĩa thì chỉ một worker đứng, không phải server.
    size = await run_in_threadpool(_copy_upload, file.file, target)
    if size == 0:
        # Xoá tệp rỗng vừa tạo: để lại thì `media_dir` đầy rác 0 byte và lần tải
        # sau trùng tên sẽ gặp một tệp cũ vô nghĩa.
        await run_in_threadpool(target.unlink, True)
        raise HTTPException(422, "tệp rỗng")

    digest = await run_in_threadpool(ingest.sha256_file, target)
    stem = digest[:16]
    final = media_dir / f"{stem}{target.suffix}"
    # Tên theo nội dung: hai lần tải cùng một video dùng chung một tệp, và lần
    # tải lại không đẻ ra bản sao thứ hai.
    await run_in_threadpool(target.replace, final)

    source_id = repos.add_source(kind="file", origin=file.filename or final.name,
                                 media_path=str(final), lang=lang)
    job = _enqueue_ingest(repos, source_id, lang)
    return {"source": _source_json(repos.get_source(source_id)), "job": _job_json(job)}


@router.post("/url", status_code=201)
def add_url(payload: UrlIn, repos=Depends(get_repos), dirs=Depends(get_dirs)):
    media_dir: pathlib.Path = dirs["media"]
    try:
        path = ingest.download_url(payload.url, media_dir)
    except ingest.IngestError as exc:
        # Mất mạng / video bị chặn là lỗi ĐẦU VÀO, không phải lỗi máy chủ.
        raise HTTPException(422, str(exc)) from exc

    # I-6: tên tệp do yt-dlp sinh ra từ `%(id)s`, tức do SITE TỪ XA chọn, nên nó
    # là DỮ LIỆU chứ không phải quyền. Đây là CÙNG một luật mà `routes_media` đã
    # áp cho chính cột này khi ĐỌC (`resolve_within`): không chứng minh được nó
    # nằm trong `media_dir` thì không lưu — nếu không, ffprobe/ffmpeg ở worker sẽ
    # mở một đường dẫn ngoài gốc media.
    try:
        path = resolve_within(media_dir, path)
    except PathOutsideRoot as exc:
        raise HTTPException(
            422, f"tệp tải về nằm ngoài thư mục media: {exc}") from exc

    source_id = repos.add_source(kind="url", origin=payload.url,
                                 media_path=str(path), lang=payload.lang)
    job = _enqueue_ingest(repos, source_id, payload.lang)
    return {"source": _source_json(repos.get_source(source_id)), "job": _job_json(job)}


@router.get("")
def list_sources(repos=Depends(get_repos)):
    # Đi qua CỔNG: thứ tự mới-nhất-trước là việc của `SqliteRepos.list_sources()`
    # (R74 — route từng mở thẳng tệp SQLite vì cổng còn thiếu phương thức này).
    return [_source_json(s) for s in repos.list_sources()]


@router.get("/{source_id}")
def get_source(source_id: int, repos=Depends(get_repos)):
    try:
        return _source_json(repos.get_source(source_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
