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
import threading

from collections import OrderedDict

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
#: Số mẫu mỗi khung phân tích. `n=160` ở 16 kHz = **10 ms**.
#:
#: 🔴 ĐO ĐƯỢC, không đoán. Ba mật độ trên chính tệp này:
#:
#:     mẫu/khung   bước    điểm cho 1249 s   thời gian
#:       1600     100 ms       12 493         1,56 s
#:        400      25 ms       49 974           —
#:        160      10 ms      124 924         7,46 s
#:
#: 124 924 điểm trên `width = 1249,237 × 40 = 49 969 px` là **2,5 điểm mỗi
#: pixel** — đủ để đường bao mượt, không răng cưa. Ở 100 ms chỉ có 0,25
#: điểm/pixel, tức phải nội suy 4 pixel từ một mẫu: đó chính là chỗ "thô".
#:
#: 7,46 s cho một lần đọc cả tệp, và kết quả được tính lại mỗi lần gọi — chấp
#: nhận được vì peaks không phải đường nóng (chỉ gọi khi mở nguồn).
_MAU_MOI_KHUNG = 160

#: Số điểm trả về mặc định. Phải >= số pixel của dải thời gian rộng nhất có thể
#: (160 px/s × 1249 s = 199 878), nên lấy 4000 là quá ít — xem `_SO_DIEM_MAX`.
_SO_DINH = 200000

#: Trần cứng: 160 px/s (mức thu phóng lớn nhất của thanh `Thu phóng`) × 1249 s
#: = 199 878 px. Trên nữa thì JSON to mà không thêm chi tiết nào nhìn thấy được.
_SO_DIEM_MAX = 200000


def _doc_dinh_song(wav: pathlib.Path, so_dinh: int) -> dict[str, list[float]]:
    """Đường bao sóng âm HAI PHÍA, đọc từ WAV bằng `ffmpeg astats`.

    🔴 VÌ SAO HAI PHÍA, KHÔNG PHẢI MỘT CỘT (đo được, không đoán):

    Bản trước trả MỘT số cho mỗi khung (`Peak_level`, dB) rồi client vẽ một cột
    đối xứng quanh trục giữa. Đó là kiểu "bar waveform" của player nhạc, không
    phải kiểu Premiere Pro / Audition / DaVinci Resolve: ba chương trình đó vẽ
    ĐƯỜNG BAO LIÊN TỤC, đối xứng, tô kín, và hai phía KHÔNG nhất thiết bằng nhau
    — âm thanh thật có pha lệch, sóng dương và sóng âm khác nhau.

    `astats` trả đúng thứ đó. Khung đầu tiên của tệp này:

        lavfi.astats.1.Min_level=-10363.000000
        lavfi.astats.1.Max_level=10210.000000
        lavfi.astats.1.Peak_level=-9.999024
        lavfi.astats.1.RMS_level=-14.825099

    `Min_level`/`Max_level` là biên độ THÔ trên thang 32768 (PCM 16 bit), không
    phải dB: `-10363` xuống, `+10210` lên. Chia cho 32768 là ra `[-1, +1]`.

    🔴 VÌ SAO KHÔNG DÙNG `Peak_level` NỮA:

    `Peak_level` là dB của `max(|Min|, |Max|)` — một số DƯƠNG duy nhất. Vẽ từ nó
    thì hai phía luôn bằng nhau, và mất hẳn hình dạng pha. Đo phân bố trên 12 493
    khung cho thấy `RMS_level` dồn 84% vào 0,1..0,5 nên hầu hết cột cao bằng
    nhau; `Peak_level` khá hơn nhưng vẫn chỉ là một phía.

    Trả `{"tren": [...], "duoi": [...]}` với giá trị 0..1, đã chuẩn hoá theo
    đỉnh tuyệt đối của CẢ HAI phía để tỉ lệ giữa chúng được giữ nguyên — chuẩn
    hoá HIỂN THỊ, không phải thay đổi dữ liệu.

    Trả dict rỗng khi ffmpeg không chạy được hoặc không có khung nào — client sẽ
    vẽ vạch "chưa có sóng" thay vì một dải phẳng giả.
    """
    # `-vn`: chắc chắn không giải mã video. Không `-t`: cần cả tệp.
    # 🔴 ĐO ĐƯỢC: KHÔNG nối hai `ametadata` có `key=`. Khi nối, ffmpeg chỉ in khoá
    # của bộ lọc CUỐI — đo thật, lệnh có cả `Min_level` rồi `Max_level` chỉ ra:
    #
    #     lavfi.astats.Overall.Max_level=1.000000
    #     lavfi.astats.Overall.Max_level=9624.000000
    #
    # Không một dòng `Min_level` nào. Đó là lý do route trả `so_dinh=0` lúc đầu.
    #
    # Bỏ `key=` thì `ametadata=print` in MỌI metadata, và hai khoá nằm cạnh nhau
    # đúng thứ tự khai trong `astats`. Đo trên cả tệp: 249 848 dòng Min+Max
    # (= 124 924 × 2) trong 7,75 s.
    # 🔴 TỐI ƯU ĐO ĐƯỢC: chỉ đo HAI số cần, không đo cả 25.
    #
    # `astats` mặc định đo `all` — 25 chỉ số cho mỗi kênh VÀ mỗi overall, rồi
    # `ametadata` in hết ra. Đo trên chính tệp này:
    #
    #     astats mac dinh (in het)              5 871 428 dong   7,90 s
    #     chi decode + asetnsamples (khong astats)        0 dong   1,14 s
    #     astats do Min_level+Max_level          374 772 dong   2,68 s
    #
    # Giải mã chỉ 1,14 s; phần còn lại là `astats` tính 25 chỉ số không dùng.
    # `measure_perchannel=none` bỏ hẳn phần theo kênh (tệp mono nên nó trùng
    # `Overall`), `measure_overall=Min_level+Max_level` chỉ giữ hai số ta vẽ.
    #
    # Cùng dữ liệu, cùng khoá, cùng kết quả — chỉ không tính thứ không dùng.
    loc = (f"asetnsamples=n={_MAU_MOI_KHUNG},"
           "astats=metadata=1:reset=1:measure_perchannel=none:"
           "measure_overall=Min_level+Max_level,"
           "ametadata=print:file=-")
    lenh = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-vn",
        "-i", str(wav), "-af", loc, "-f", "null", "-",
    ]
    try:
        # 120 s: đo được 7,46 s cho cả tệp, nhưng máy chậm hoặc ổ đĩa bận thì
        # cần đệm rộng. Hết giờ thì trả rỗng, client vẽ vạch "chưa có sóng".
        ket = subprocess.run(lenh, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("không đọc được đỉnh sóng của %s: %s", wav.name, exc)
        return {}
    if ket.returncode != 0:
        logger.warning("ffmpeg trả %s khi đọc đỉnh sóng %s: %s",
                       ket.returncode, wav.name, ket.stderr.strip()[:200])
        return {}

    # `ametadata=print` ghi hai dòng cho mỗi khung, theo đúng thứ tự khoá trong
    # `loc`: Min_level trước, Max_level sau. Đọc theo CẶP thay vì hai danh sách
    # rời rồi ghép — mất một dòng là lệch toàn bộ phần còn lại.
    duoi: list[float] = []
    tren: list[float] = []
    for dong in ket.stdout.splitlines():
        if "Overall.Min_level=" in dong:
            duoi.append(_doc_thang_do(dong))
        elif "Overall.Max_level=" in dong:
            tren.append(_doc_thang_do(dong))
    if not duoi or len(duoi) != len(tren):
        logger.warning("số khung lệch nhau cho %s: min=%s max=%s",
                       wav.name, len(duoi), len(tren))
        return {}

    # 🔴 CHUẨN HOÁ HAI PHÍA RIÊNG — đo được, không đoán.
    #
    # Bản đầu chia CẢ hai phía cho một `dinh = max(max(duoi), max(tren))`. Sai:
    # `max(duoi)` là số ÂM gần 0 (`-3260` ở khung đầu), nên `dinh` luôn lấy từ
    # `tren`, và phía dưới bị chia cho số dương. Đo trên route thật:
    #
    #     tren: min=-0.3064  max=1.0000    <- "tren" có giá trị ÂM
    #     duoi: min=-1.0000  max=0.2845    <- "duoi" có giá trị DƯƠNG
    #
    # Hai phía lẫn dấu vì `Min_level` cũng có mẫu dương (nhiễu DC, `DC_offset`
    # khác 0) và `Max_level` cũng có mẫu âm.
    #
    # Đúng ra: mỗi phía chuẩn hoá theo BIÊN ĐỘ LỚN NHẤT CỦA CHÍNH NÓ, rồi kẹp
    # dấu cho đúng phía. Tỉ lệ giữa sóng dương và sóng âm KHÔNG được giữ nguyên
    # bằng cách chia chung — nó được giữ bằng cách vẽ đúng dấu, còn thang đo thì
    # mỗi phía tự no tới mép khung như Premiere/Audition vẫn làm.
    tren_max = max(tren)
    duoi_min = min(duoi)
    if tren_max <= 0 or duoi_min >= 0:
        return {}

    # Gộp về `so_dinh` điểm: mỗi điểm lấy giá trị LỚN NHẤT về phía của nó (max
    # cho phía trên, min cho phía dưới). Lấy trung bình sẽ làm phẳng đúng chỗ có
    # tiếng nói — đó là lỗi của bản cột.
    def gon(ds: list[float], lay_max: bool) -> list[float]:
        if len(ds) <= so_dinh:
            return ds
        buoc = len(ds) / so_dinh
        ra: list[float] = []
        for i in range(so_dinh):
            dau = int(i * buoc)
            cuoi = max(dau + 1, int((i + 1) * buoc))
            doan = ds[dau:cuoi]
            ra.append(max(doan) if lay_max else min(doan))
        return ra

    # `tren` -> 0..1 (dấu dương, chia cho đỉnh dương lớn nhất).
    # `duoi` -> 0..1 (độ LỚN, chia cho |đỉnh âm nhỏ nhất|), client vẽ ngược lên.
    # Kẹp `max(0, ...)`: mẫu lệch dấu do nhiễu DC thành 0, không thành một gai sai.
    return {
        "tren": [round(min(1.0, max(0.0, v / tren_max)), 4) for v in gon(tren, True)],
        "duoi": [round(min(1.0, max(0.0, v / duoi_min)), 4) for v in gon(duoi, False)],
    }


def _doc_thang_do(dong: str) -> float:
    """`lavfi.astats.Overall.Min_level=-10363.0` -> `-10363.0`, kẹp về ±32768."""
    try:
        gia_tri = float(dong.rsplit("=", 1)[1])
    except (ValueError, IndexError):
        return 0.0
    if not math.isfinite(gia_tri):
        return 0.0
    # PCM 16 bit: vượt biên là dữ liệu hỏng, kẹp lại để hình không bị xé khung.
    return max(-32768.0, min(32768.0, gia_tri))


@router.get("/{source_id}/peaks")
def get_peaks(source_id: int, so_dinh: int = _SO_DINH,
              repos=Depends(get_repos), dirs=Depends(get_dirs)):
    """Đường bao sóng âm hai phía: `{tren: [...], duoi: [...], so_dinh: N, giay: D}`.

    Đọc `audio_path` (WAV 16 kHz) chứ không phải `media_path` (MP4): xem docblock
    `_doc_dinh_song` và khối chú thích đầu mục này.

    `so_dinh` bị kẹp trong `[200, 200000]`. Dưới 200 thì ở mức thu phóng lớn nhất
    (160 px/s) mỗi điểm phải phủ gần 1000 px — thô hơn cả bản cột cũ. Trên
    200 000 thì vượt số pixel của dải rộng nhất, JSON to mà hình không khác.
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

    so_dinh = max(200, min(_SO_DIEM_MAX, so_dinh))

    # Khoá cache: đường dẫn + mtime + size + so_dinh. `st_mtime_ns` (không phải
    # `st_mtime`) vì hai lần ghi trong cùng một giây vẫn phải khác khoá.
    st = wav.stat()
    khoa = (str(wav), st.st_mtime_ns, st.st_size, so_dinh)
    co = _lay_tu_cache(khoa)
    if co is None:
        co = _doc_dinh_song(wav, so_dinh)
        if co:
            _dat_vao_cache(khoa, co)

    return {
        "tren": co.get("tren", []),
        "duoi": co.get("duoi", []),
        "so_dinh": len(co.get("tren", [])),
        "giay": source.duration,
    }
# ─────────────────────────────────────────────────────────────────────────────
# CACHE ĐỈNH SÓNG.
#
# 🔴 VÌ SAO CACHE ĐÚNG Ở ĐÂY, KHÔNG PHẢI "CHO NHANH":
#
# Peaks là hàm THUẦN của (nội dung tệp, so_dinh). Tệp media không bao giờ đổi
# sau khi ASR đã tách WAV — nó là đầu vào bất biến của cả đường ống. Nhưng route
# chạy `ffmpeg` lại từ đầu MỖI lần mở nguồn. Đo được trước khi cache:
#
#     lan 1:  9,56 s       lan 2:  9,49 s        (không có cache)
#
# Hai lần liên tiếp gần như bằng nhau — đúng như dự đoán: không cache gì cả.
#
# Khoá cache gồm `st_mtime_ns` và `st_size`: nếu tệp bị ghi đè (thay media,
# upload lại cùng id) thì khoá đổi và cache tự bỏ, không cần ai xoá tay. Đó là
# lý do dùng stat thay vì chỉ đường dẫn.
#
# Giới hạn `_CACHE_TOI_DA` mục: peaks 1,7 MB mỗi nguồn, 8 nguồn là ~14 MB RAM.
# Vượt thì xoá mục CŨ NHẤT (dict giữ thứ tự chèn) — đủ cho một phiên làm việc,
# không phải một cache vô hạn.
# ─────────────────────────────────────────────────────────────────────────────

_CACHE_TOI_DA = 8
_cache_dinh: "OrderedDict[tuple[str, int, int, int], dict[str, list[float]]]" = OrderedDict()
_cache_khoa = threading.Lock()


def _lay_tu_cache(khoa: tuple[str, int, int, int]) -> dict[str, list[float]] | None:
    """Trả bản đã tính, hoặc `None`. Chạm mục vừa dùng xuống cuối (LRU)."""
    with _cache_khoa:
        co = _cache_dinh.get(khoa)
        if co is not None:
            _cache_dinh.move_to_end(khoa)
        return co


def _dat_vao_cache(khoa: tuple[str, int, int, int],
                   gia_tri: dict[str, list[float]]) -> None:
    """Ghi vào cache, bỏ mục cũ nhất khi vượt trần."""
    with _cache_khoa:
        _cache_dinh[khoa] = gia_tri
        _cache_dinh.move_to_end(khoa)
        while len(_cache_dinh) > _CACHE_TOI_DA:
            _cache_dinh.popitem(last=False)
