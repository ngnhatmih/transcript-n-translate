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
import math
import mimetypes
import pathlib
import re
import subprocess

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

# ─────────────────────────────────────────────────────────────────────────────
# ĐỈNH SÓNG ÂM — tính Ở SERVER, trả JSON.
#
# 🔴 VÌ SAO KHÔNG GIẢI MÃ TRONG TRÌNH DUYỆT (đo được, không đoán):
# Client từng `fetch('/api/media/1')` rồi `decodeAudioData`. Đo trên trang thật:
#
#     fetch status=206 type=video/mp4
#     blob size=238623268 sau 0.0s
#     ... rồi KHÔNG có `decodeAudioData OK` lẫn `LOI` trong 45 giây.
#
# Tải xong ngay (đo tốc độ: 318 MB/s) nhưng `decodeAudioData` TREO trên container
# MP4 238 MB. Đây là hành vi đã biết: nó chỉ giải mã CẢ tệp và giữ toàn bộ mẫu đã
# giải mã trong bộ nhớ. Tài liệu của `@humansignal/audio-file-decoder` ghi cùng
# con số: "a 10 minute audio… 4 bytes * 2 channels = ~212 MB of memory".
#
# Cách làm chuẩn (Peaks.js của BBC R&D, `waveform-data.js`) là tính peaks ở server
# rồi client chỉ vẽ. Đây là cách đó.
#
# 🔴 VÌ SAO ĐỌC `audio_path` CHỨ KHÔNG PHẢI `media_path`:
# `media_path` là MP4 238 MB có video; `audio_path` là WAV 40 MB mà ASR đã dùng.
# Đo: `ffmpeg astats` trên WAV 1249 s mất 1,56 s cho 24 986 khung 100 ms.
# Đọc MP4 thì phải giải mã video theo, chậm hơn nhiều mà không thêm thông tin gì.
#
# 🔴 VÌ SAO `astats` CHỨ KHÔNG PHẢI `showwavespic`:
# `showwavespic` trả ẢNH (7 762 B PNG cho 2400x96) — client phải nhận ảnh rồi cắt
# theo bề rộng khung, và không đổi được độ phân giải theo mức thu phóng. `astats`
# trả SỐ, client tự vẽ ở bất kỳ bề rộng nào. Số cũng nhỏ hơn: 1200 điểm ~ 10 KB.
# ─────────────────────────────────────────────────────────────────────────────

#: Đỉnh sóng thưa hơn 100 ms thì không tăng thông tin: tai người không phân biệt
#: được hai đỉnh cách nhau dưới ~50 ms, và dải thời gian ở 40 px/s chỉ rộng 4 px
#: cho 100 ms. `n=1600` mẫu ở 16 kHz = 100 ms.
_MAU_MOI_DINH = 1600

#: Số đỉnh trả về. 1200 điểm phủ 1249 s = ~1,04 s/điểm ở mức thu phóng thấp nhất;
#: client nội suy khi cần dày hơn. Nhiều hơn thì JSON to mà hình không khác.
_SO_DINH = 1200


def _doc_dinh_song(wav: pathlib.Path, so_dinh: int) -> list[float]:
    """Đỉnh sóng 0..1 cho `so_dinh` điểm, đọc từ WAV bằng `ffmpeg astats`.

    `RMS_level` là dB (âm). Đổi về biên độ tuyến tính `10**(db/20)`, rồi chia cho
    đỉnh lớn nhất để dải luôn đầy khung — đây là chuẩn hoá HIỂN THỊ, không phải
    thay đổi dữ liệu: hình dạng tỉ lệ giữa các điểm được giữ nguyên.

    Trả `[]` khi ffmpeg không chạy được hoặc không có khung nào — client sẽ vẽ
    vạch "chưa có sóng" thay vì một dải phẳng giả.
    """
    # `-t` không dùng: cần cả tệp. `-vn` để chắc chắn không giải mã video.
    lenh = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-vn",
        "-i", str(wav),
        "-af", (f"asetnsamples=n={_MAU_MOI_DINH},astats=metadata=1:reset=1,"
                "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-"),
        "-f", "null", "-",
    ]
    try:
        ket = subprocess.run(lenh, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("không đọc được đỉnh sóng của %s: %s", wav.name, exc)
        return []
    if ket.returncode != 0:
        logger.warning("ffmpeg trả %s khi đọc đỉnh sóng %s: %s",
                       ket.returncode, wav.name, ket.stderr.strip()[:200])
        return []

    # `ametadata=print` ghi ra stdout: cặp dòng "frame:N pts_time:T" và
    # "lavfi.astats.Overall.RMS_level=X". Chỉ cần các dòng RMS.
    db: list[float] = []
    for dong in ket.stdout.splitlines():
        if "RMS_level=" not in dong:
            continue
        try:
            gia_tri = float(dong.rsplit("=", 1)[1])
        except (ValueError, IndexError):
            continue
        # `-inf` (im lặng tuyệt đối) không parse được thành float hữu hạn.
        db.append(gia_tri if math.isfinite(gia_tri) else -120.0)
    if not db:
        return []

    bien_do = [10.0 ** (x / 20.0) for x in db]

    # Gộp về đúng `so_dinh` điểm bằng cách lấy MAX trong mỗi nhóm: đỉnh là đỉnh,
    # lấy trung bình sẽ làm phẳng đúng chỗ có tiếng nói.
    if len(bien_do) > so_dinh:
        buoc = len(bien_do) / so_dinh
        gon: list[float] = []
        for i in range(so_dinh):
            dau = int(i * buoc)
            cuoi = max(dau + 1, int((i + 1) * buoc))
            gon.append(max(bien_do[dau:cuoi]))
        bien_do = gon

    dinh = max(bien_do)
    if dinh <= 0:
        return []
    return [round(v / dinh, 4) for v in bien_do]


@router.get("/{source_id}/peaks")
def get_peaks(source_id: int, so_dinh: int = _SO_DINH,
              repos=Depends(get_repos), dirs=Depends(get_dirs)):
    """Đỉnh sóng âm của nguồn, dạng `{dinh: [0..1, ...], so_dinh: N, giay: D}`.

    Đọc `audio_path` (WAV 16 kHz) chứ không phải `media_path` (MP4): xem docblock
    `_doc_dinh_song` và khối chú thích đầu mục này.

    `so_dinh` bị kẹp trong `[100, 4000]`: dưới 100 thì dải quá thô để thấy nhịp
    nói; trên 4000 thì JSON to hơn hình thu được ở mọi bề rộng màn hình thực tế.
    """
    try:
        source = repos.get_source(source_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    duong_dan = source.audio_path or source.media_path
    if not duong_dan:
        raise HTTPException(404, "nguồn này không có tệp âm thanh")
    try:
        wav = resolve_within(dirs["media"], duong_dan)
    except PathOutsideRoot as exc:
        logger.warning("từ chối peaks ngoài gốc: source_id=%s: %s", source_id, exc)
        raise HTTPException(403, "media path is outside the media root") from exc
    if not wav.is_file():
        raise HTTPException(410, f"tệp âm thanh đã bị xoá: {wav.name}")

    so_dinh = max(100, min(4000, so_dinh))
    dinh = _doc_dinh_song(wav, so_dinh)
    return {"dinh": dinh, "so_dinh": len(dinh), "giay": source.duration}
