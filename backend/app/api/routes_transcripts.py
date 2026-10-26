"""Route transcript: xem, sửa (tăng version), duyệt, và đo tốc độ đọc.

Hai bất biến của tầng này:

* **Sửa nội dung là TĂNG VERSION, và version là thứ duy nhất khiến bản dịch cũ
  thành 'lỗi thời'.** `stale` KHÔNG được lưu ở đâu cả — nó được TÍNH mỗi lần
  đọc bằng `is_stale(version_hiện_tại, version_đã_dịch)`. Lưu sẵn một cột
  `stale` thì mọi đường ghi khác (sửa, chạy lại ASR, hồi phục job) đều phải nhớ
  cập nhật nó, và quên một đường là giao diện nói sai.
* **Duyệt (`approve`) KHÔNG tăng version.** Nó chỉ đổi `status`. Nếu nó tăng
  version thì mọi bản dịch thành lỗi thời chỉ vì người dùng bấm "duyệt" — một
  nút không sửa một ký tự nào.

Route đi qua cổng `Repos` cho cả bản dịch (`list_translations_for_transcript`):
`app/api` không được mở tệp SQLite, kể cả để đọc.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_prices, get_repos
from app.domain.models import Segment
from app.domain.readability import CPS_WARN, reading_cps
from app.domain.staleness import translation_summary_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])

VALID_STATUS = {"draft", "reviewed", "translated"}


class PatchIn(BaseModel):
    # `min_length=1`: một transcript không đoạn nào là dữ liệu hỏng, không phải
    # "xoá sạch nội dung" — và nó cũng làm mọi bước sau chia cho rỗng.
    segments: list[dict] = Field(min_length=1)
    status: str | None = None


def _translation_json(row, current_version: int, *, prices=None) -> dict:
    """Hình dạng JSON của một bản dịch — UỶ QUYỀN cho builder dùng chung.

    Trước bản này route ở đây tự ghép khoá và phát `translated_from_version`
    (không `status`), nên cùng một hàng đọc ở `/api/translations` và ở đây cho
    hai hình dạng khác nhau. Một builder trong `domain/staleness.py` — chỗ đã sở
    hữu `is_stale` — là nguồn duy nhất; hai endpoint được ghim bằng nhau ở
    `tests/test_api_translations.py::test_the_two_endpoints_describe_a_translation_identically`
    (và bài kế tiếp đo lại sau khi transcript đổi version).
    """
    return translation_summary_json(row, current_version, prices=prices)


def _transcript_json(repos, transcript, *, prices=None, include_segments: bool = True) -> dict:
    out = {
        "id": transcript.id,
        "source_id": transcript.source_id,
        "engine": transcript.engine,
        "lang": transcript.lang,
        "version": transcript.version,
        "status": transcript.status,
        "created_at": transcript.created_at,
        "translations": [
            _translation_json(r, transcript.version)
            for r in repos.list_translations_for_transcript(transcript.id)
        ],
    }
    if include_segments:
        out["segments"] = [s.to_json() for s in transcript.segments]
    return out


def _require_transcript(repos, transcript_id: int):
    """Đọc một transcript, đổi `LookupError` của cổng thành 404.

    `LookupError` chứ không `NotFound`: route chỉ được biết cổng, và một hiện
    thực khác của cổng không phải kéo theo lớp `NotFound` của adapter SQLite.
    """
    try:
        return repos.get_transcript(transcript_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("")
def list_transcripts(repos=Depends(get_repos), prices=Depends(get_prices)):
    # KHÔNG kèm segments: một transcript vài nghìn đoạn sẽ làm phình response
    # của trang danh sách, mà trang đó không vẽ đoạn nào.
    return [_transcript_json(repos, t, prices=prices, include_segments=False)
            for t in repos.list_transcripts()]


@router.get("/{transcript_id}")
def get_transcript(transcript_id: int, repos=Depends(get_repos),
                   prices=Depends(get_prices)):
    return _transcript_json(repos, _require_transcript(repos, transcript_id),
                            prices=prices)


@router.patch("/{transcript_id}")
def patch_transcript(transcript_id: int, payload: PatchIn, repos=Depends(get_repos),
                     prices=Depends(get_prices)):
    _require_transcript(repos, transcript_id)

    if payload.status is not None and payload.status not in VALID_STATUS:
        raise HTTPException(422, f"trạng thái không hợp lệ: {payload.status!r}")

    try:
        segments = [Segment.from_json(d) for d in payload.segments]
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        # Đoạn thiếu khoá (`{"start": 0.0}`) là lỗi ĐẦU VÀO -> 422. Để `KeyError`
        # nổi lên thành 500 là nói với client rằng máy chủ hỏng.
        raise HTTPException(422, f"segment không hợp lệ: {exc}") from exc

    repos.update_transcript_segments(transcript_id, segments)
    if payload.status is not None:
        repos.set_transcript_status(transcript_id, payload.status)

    return _transcript_json(repos, _require_transcript(repos, transcript_id),
                           prices=prices)


@router.get("/{transcript_id}/readability")
def readability(transcript_id: int, threshold: float = CPS_WARN,
                repos=Depends(get_repos)):
    """Những đoạn đọc NHANH HƠN ngưỡng CPS.

    Ngưỡng mặc định là `CPS_WARN`; client hạ nó xuống để soi trước khi bản dịch
    dài ra (tiếng Việt dài gấp 2-3 lần tiếng Trung, nên dòng dịch đúng nghĩa
    vẫn có thể không đọc kịp).

    Một đoạn có thời lượng `<= 0` KHÔNG được đi qua `reading_cps`: hàm đó trả
    `float("inf")` (đúng về toán), và để `inf` tới được response thì
    `ValueError: Out of range float values are not JSON compliant` ⇒ cả route 500 và
    người dùng mất TOÀN BỘ danh sách vì MỘT dòng dữ liệu hỏng.

    ⚠️ CƠ CHẾ, nói cho đúng (ERRATA #15 mục 2 — một lời giải thích cơ chế cũng là một
    lời khai, và bản đầu của khối này đã kể SAI): `json.dumps({"cps": inf})` **KHÔNG**
    ném — nó trả `{"cps": Infinity}` (đã đo). `ValueError` đến từ
    `starlette.responses.JSONResponse.render`, nơi gọi `json.dumps(..., allow_nan=False)`.
    Đây là ràng buộc của TẦNG HTTP, không phải của `json.dumps` nói chung.

    Cách xử ở đây theo ĐÚNG nhánh `nowindow` mà `mt_qa.qa_translation` đã dùng: báo là
    KHÔNG ĐO ĐƯỢC kèm số ký tự, KHÔNG in một tốc độ chưa từng đo được, và báo BẤT KỂ
    ngưỡng — đây là dữ liệu hỏng, không phải "hơi nhanh".

    Khoá đếm ký tự tên là `chars_no_space` vì định nghĩa ở đây là của `reading_cps`
    (BỎ khoảng trắng). ⚠️ `mt_qa` cũng phát một khoá tên `chars` nhưng nghĩa **KHÁC**
    (`len(text.strip())` — CÓ đếm khoảng trắng), nên cùng một dòng có thể ra hai con số
    khác nhau. Hai khoá cùng tên mà khác nghĩa là đúng thứ khiến người sau đọc sai số;
    tên ở đây nói rõ nghĩa của nó.
    """
    transcript = _require_transcript(repos, transcript_id)
    too_fast = []
    for seg in transcript.segments:
        chars_no_space = len("".join(seg.text.split()))
        if seg.end - seg.start <= 0:
            too_fast.append({"i": seg.i, "cps": None, "chars_no_space": chars_no_space,
                             "start": seg.start, "end": seg.end})
            continue
        cps = reading_cps(seg.text, seg.start, seg.end)
        if cps > threshold:
            too_fast.append({"i": seg.i, "cps": round(cps, 1),
                             "chars_no_space": chars_no_space,
                             "start": seg.start, "end": seg.end})
    return {"threshold": threshold, "too_fast": too_fast}


@router.post("/{transcript_id}/approve")
def approve(transcript_id: int, repos=Depends(get_repos), prices=Depends(get_prices)):
    # Cố ý KHÔNG đụng tới segments/version: xem docstring đầu tệp.
    _require_transcript(repos, transcript_id)
    repos.set_transcript_status(transcript_id, "reviewed")
    return _transcript_json(repos, _require_transcript(repos, transcript_id),
                            prices=prices, include_segments=False)
