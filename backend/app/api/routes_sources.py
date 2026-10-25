"""Route nguồn vào: tải tệp lên, dán link, liệt kê, xem chi tiết, xoá.

Route KHÔNG tự chạy pipeline. Nó lưu media + một hàng `sources`, rồi xếp một job
`ingest`; worker (một luồng riêng) mới thật sự chạm ffmpeg. Nhờ vậy một tệp 2 GB
không giữ request HTTP mở suốt thời gian bóc âm thanh.

`DELETE /api/sources/{id}` là chiều NGƯỢC LẠI và cũng đi qua cùng bất biến đó:
nó không chạm worker, nó từ chối (409) khi một job còn sống đang trỏ vào nguồn —
xem `delete_source` ở cuối tệp và `app/api/delete_guard.py`.
"""
from __future__ import annotations

import pathlib
from typing import BinaryIO

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Response,
                     UploadFile)
from pydantic import BaseModel, field_validator
from starlette.concurrency import run_in_threadpool

from app.api.delete_guard import active_job_ids, mot_loi_409
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
    # API-06 (R40): spec §8.1 ghi tên tệp là `<sha256>`, ở đây cố ý rút còn 16
    # hex. Đây là QUYẾT ĐỊNH có ý thức, không phải sót: tên tệp ngắn, và 16 hex
    # (64 bit) đủ chống trùng ở quy mô GĐ1a. Đổi sang 64 hex là đổi hợp đồng
    # `media_path` (R37/StubIngest của Task 19 suy tên `.wav` từ nó) nên phải
    # làm cùng lúc, không lẻ. Hợp đồng 16 ký tự được ghim bởi
    # `test_upload_still_accepts_a_normal_filename`.
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


def _xoa_tep_media(media_dir: pathlib.Path, duong_dan: str | None) -> None:
    """Xoá MỘT tệp media của nguồn, CHỈ khi nó nằm trong `media_dir`.

    Bốn quyết định, mỗi cái là một cách hỏng đã trả giá ở chỗ khác của dự án:

    * **`resolve_within` chứ không so tiền tố chuỗi.** `media_path`/`audio_path` là
      dữ liệu trong DB, và `..` cùng symlink/junction đi vòng qua phép so chuỗi;
      đây đúng phép kiểm mà `routes_media` đã áp cho cột này lúc ĐỌC và
      `routes_sources.add_url` áp lúc GHI. Một lần `unlink()` là không hoàn tác
      được, nên nó phải đi qua cùng cửa đó.
    * **Ngoài `media_dir` ⇒ KHÔNG xoá, và KHÔNG ném.** Hàng `sources` đã bị xoá
      trong giao dịch TRƯỚC đó (xem `delete_source`), nên một `500` ở đây là nói
      dối về một việc đã xong: client sẽ tưởng bản ghi còn và bấm lại. Bất biến
      giữ được là "không bao giờ unlink ngoài thư mục media", không phải "luôn
      unlink".
    * **Tệp thiếu KHÔNG phải lỗi** (`missing_ok=True`): nguồn `url` chưa bóc âm
      thanh có `audio_path` NULL, và một tệp bị xoá tay là chuyện thường — hàng
      `sources` vẫn phải biến mất.
    * **`OSError` khác cũng bị nuốt** (tệp đang bị khoá trên Windows, quyền):
      cùng lý do với nhánh ngoài gốc — `204` đã hứa "hàng đã xoá", và một tệp
      không xoá được không làm hàng đó sống lại.
    """
    if duong_dan is None or duong_dan == "":
        return
    try:
        target = resolve_within(media_dir, duong_dan)
    except PathOutsideRoot:
        return
    try:
        target.unlink(missing_ok=True)
    except OSError:
        return


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: int, repos=Depends(get_repos), dirs=Depends(get_dirs)):
    """Xoá MỘT nguồn: bản dịch + transcript của nó, rồi hàng `sources`, rồi tệp.

    Thứ tự và giới hạn của nó, nói thẳng:

    1. **404 trước mọi thứ khác.** `get_source` đọc hàng THẬT (và trả câu
       "source N không tồn tại"), nên một id lạ không đi tiếp được vào nhánh nào.
       Route đọc hàng này chứ không chỉ dựa vào `delete_source` vì nó cần
       `media_path`/`audio_path` — thứ biến mất cùng hàng.
    2. **409 khi còn job sống.** Xem `app/api/delete_guard.py` để biết vì sao
       TỪ CHỐI là hành vi an toàn (handler đang chạy sẽ ghi checkpoint vào hàng
       vừa bị xoá) và vì sao đường nối là `payload.source_id`. Phép kiểm chạy
       TRƯỚC khi xoá bất cứ thứ gì, nên hàng còn nguyên khi route trả 409.
    3. **DB trước, đĩa sau, và không cùng một giao dịch.** Giao dịch SQLite
       (`repos.delete_source`) là một khối nguyên tử; tệp trên đĩa thì không
       rollback được cùng nó. Làm ngược lại (xoá tệp trước) sẽ để lại hàng
       `sources` trỏ vào một `media_path` không còn tồn tại nếu bước DB hỏng —
       và `GET /api/media/{id}` khi đó trả 500 thay vì 404.
    4. **Bảng `jobs` KHÔNG bị chạm.** Job là lịch sử chạy, không phải con của
       nguồn; xoá nó là xoá dấu vết của một lần chạy thật (cùng lý do
       `mark_running_as_interrupted` giữ hàng lại thay vì xoá).
    """
    try:
        source = repos.get_source(source_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    ids = active_job_ids(repos, key="source_id", value=source_id)
    if ids:
        raise HTTPException(
            409,
            mot_loi_409(doi_tuong=f"nguồn {source_id}", ids=ids,
                        cach_sua="huỷ job đó trước rồi xoá"),
        )

    try:
        repos.delete_source(source_id)
    except LookupError as exc:
        # Đua hiếm: một request khác vừa xoá xong giữa `get_source` và đây. Trả
        # CÙNG câu 404 của nhánh trên thay vì 500 — với người gọi, "hàng không
        # còn" là đúng sự thật ở cả hai thời điểm.
        raise HTTPException(404, str(exc)) from exc

    media_dir: pathlib.Path = dirs["media"]
    # `audio_path` có thể TRÙNG `media_path` (nguồn `file` đã bóc tiếng tại chỗ):
    # `unlink` lần hai với `missing_ok=True` là no-op, nên không cần khử trùng.
    for duong_dan in (source.media_path, source.audio_path):
        _xoa_tep_media(media_dir, duong_dan)

    # 204 KHÔNG có thân. Trả `Response` tường minh thay vì `None`: FastAPI sinh
    # thân JSON cho giá trị trả về, và một thân `null` trên 204 là phản hồi sai
    # chuẩn (RFC 7231) mà vài client coi là lỗi.
    return Response(status_code=204)

