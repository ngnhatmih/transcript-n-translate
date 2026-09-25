"""Serve media cho trình phát, có HTTP Range.

BẮT BUỘC hỗ trợ Range: thiếu nó trình duyệt không seek được, và tín hiệu "đoạn
nghi ngờ" thành vô dụng — người dùng biết dòng nào sai mà không nghe được để sửa.
Trình phát còn đọc `moov` của mp4 bằng dạng hậu tố `bytes=-N` ở CUỐI tệp.

Ba thứ KHÔNG được nới ở đây:

* `media_path` trong DB là DỮ LIỆU, không phải quyền. Trước khi mở tệp, đường
  dẫn phải được phân giải và CHỨNG MINH vẫn nằm trong `media_dir`
  (`domain.paths.resolve_within`): một hàng trỏ ra ngoài, một `..`, hay một
  symlink/junction nằm trong `media_dir` đều là 403 — không phải nội dung của
  máy chủ.
* Không nạp cả tệp (hay cả khoảng được yêu cầu) vào RAM: thân 206 là generator
  đọc từng khối 256 KB.
* Không chặn event loop: endpoint là hàm `def` nên FastAPI chạy nó trong
  threadpool, và `StreamingResponse` lặp generator ĐỒNG BỘ cũng trong threadpool.
"""
from __future__ import annotations

import logging
import mimetypes
import pathlib
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from app.api.deps import get_dirs, get_repos
from app.domain.paths import PathOutsideRoot, resolve_within

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media", tags=["media"])

#: Header `Range` đã hiểu nhưng KHÔNG có khoảng nào thoả mãn -> 416 (kèm tổng
#: kích thước). Khác hẳn `None`: header hỏng thì bỏ qua và trả toàn tệp.
UNSATISFIABLE = "unsatisfiable"

#: `re.IGNORECASE`: range unit là một `token`, mà token thì không phân biệt
#: hoa/thường (RFC 9110 §2.2), nên `BYTES=0-99` là cùng một yêu cầu. Khớp chữ
#: thường không thôi thì dạng đó rơi vào "header không hiểu được" và bị bỏ im
#: lặng thành 200 cả tệp.
_RANGE_RE = re.compile(r"^bytes=\s*(\d*)\s*-\s*(\d*)\s*$", re.IGNORECASE)
_CHUNK = 1024 * 256

#: Đuôi tệp của app này -> Content-Type. Tra bảng trước `mimetypes` vì
#: `mimetypes` đọc registry của Windows: cùng một tệp có thể ra kiểu khác nhau
#: giữa hai máy, và trình phát thì cần một câu trả lời cố định.
_KNOWN_TYPES = {
    ".mp4": "video/mp4", ".m4v": "video/x-m4v", ".mkv": "video/x-matroska",
    ".webm": "video/webm", ".mov": "video/quicktime", ".avi": "video/x-msvideo",
    ".flv": "video/x-flv", ".ts": "video/mp2t",
    ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".flac": "audio/flac", ".ogg": "audio/ogg", ".opus": "audio/opus",
}


def media_type_for(name: str) -> str:
    suffix = pathlib.PurePath(name).suffix.lower()
    return (_KNOWN_TYPES.get(suffix)
            or mimetypes.guess_type(name)[0]
            or "application/octet-stream")


def parse_range(header: str, size: int) -> tuple[int, int] | None | str:
    """`Range` -> (start, end) ĐÓNG, `None` (bỏ qua header), hay `UNSATISFIABLE`.

    `None` là câu trả lời cho header KHÔNG hiểu được (`banana`, `bytes=`, nhiều
    khoảng `bytes=0-9,20-29`): RFC 7233 cho phép bỏ qua, và bỏ qua thì client
    nhận 200 toàn tệp — chết người nếu ta biến nó thành 416 và trình phát đứng.

    Hậu tố dài hơn tệp (`bytes=-5000` trên tệp 1024 byte) là CẢ tệp, không phải
    start âm; tệp rỗng thì mọi khoảng đều không thoả mãn.
    """
    match = _RANGE_RE.match(header.strip())
    if match is None:
        return None
    raw_start, raw_end = match.group(1), match.group(2)
    if raw_start == "" and raw_end == "":
        return None
    if size <= 0:
        return UNSATISFIABLE
    if raw_start == "":
        length = int(raw_end)
        if length <= 0:
            return UNSATISFIABLE
        return max(0, size - length), size - 1
    start = int(raw_start)
    if start >= size:
        return UNSATISFIABLE
    end = int(raw_end) if raw_end else size - 1
    if start > end:
        return UNSATISFIABLE
    return start, min(end, size - 1)


def _iter_file(path: pathlib.Path, start: int, end: int):
    """Đọc `[start, end]` theo khối. `end < start` -> không có gì để đọc."""
    remaining = end - start + 1
    with open(path, "rb") as fh:
        fh.seek(start)
        while remaining > 0:
            chunk = fh.read(min(_CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/{source_id}")
# RFC 9110 §9.3.2: nơi phục vụ GET thì phải phục vụ HEAD (kích thước,
# `Accept-Ranges` — thứ `curl -I` và trình phát hỏi trước khi tải). FastAPI
# `APIRoute` KHÔNG tự thêm HEAD như `Route` của Starlette, nên phải khai tường
# minh; `include_in_schema=False` để OpenAPI không có hai mục cho cùng một route.
@router.head("/{source_id}", include_in_schema=False)
def get_media(source_id: int, request: Request,
              repos=Depends(get_repos), dirs=Depends(get_dirs)):
    try:
        source = repos.get_source(source_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    try:
        path = resolve_within(dirs["media"], source.media_path)
    except PathOutsideRoot as exc:
        # Câu trả lời cho client là CHUNG: endpoint này tồn tại để từ chối, nên
        # chính nó không được liệt kê gốc media hay đường dẫn đã phân giải —
        # một bước "mở API ra LAN" biến chi tiết đó thành bản đồ hệ tệp.
        # Chi tiết vẫn còn nguyên cho người vận hành, ở log của máy chủ.
        logger.warning("từ chối media ngoài gốc: source_id=%s: %s", source_id, exc)
        raise HTTPException(403, "media path is outside the media root") from exc

    # `exists()` không đủ: `media_path` trỏ vào một thư mục thì `open()` nổ 500.
    if not path.is_file():
        raise HTTPException(410, f"tệp media đã bị xoá: {path.name}")

    size = path.stat().st_size
    media_type = media_type_for(path.name)
    range_header = request.headers.get("range")
    parsed = parse_range(range_header, size) if range_header else None

    if parsed == UNSATISFIABLE:
        # 416 không có thân, nhưng PHẢI có `Content-Range: bytes */<size>` để
        # client biết tệp dài bao nhiêu mà xin lại cho đúng.
        return Response(status_code=416, headers={
            "Accept-Ranges": "bytes", "Content-Range": f"bytes */{size}",
        })

    if parsed is None:
        start, end, status = 0, size - 1, 200
    else:
        start, end, status = parsed[0], parsed[1], 206

    # `Response` và `StreamingResponse` cùng một lớp cha, nên header ở đây là
    # header cuối: không lớp nào tự thêm `Content-Length` thứ hai.
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(max(0, end - start + 1)),
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(_iter_file(path, start, end), status_code=status,
                             media_type=media_type, headers=headers)
