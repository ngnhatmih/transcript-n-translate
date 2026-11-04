"""Bẻ dòng phụ đề — MỘT nguồn cho bản burn và bản xem trước trên web.

🔴 VÌ SAO CẦN ROUTE NÀY (ERRATA #73): bản burn bẻ dòng bằng Pillow
(`subtitle_format._do_khoi_chu`), còn bản xem trước trên web bẻ bằng
`canvas.measureText` của trình duyệt. Hai bộ đo lệch nhau ~10 % bề ngang chữ ở đúng chỗ
quyết định bẻ dòng, nên cùng một câu ra SỐ DÒNG khác nhau — đo được với `co 91`:

    bản burn      : 2 dòng 919 + 345   → hộp 938 × 180
    bản xem trước : 3 dòng 872/947/122 → hộp 969 × 214

Nên giao diện HỎI route này thay vì tự đo: số dòng, bề rộng và chiều cao đều do đúng hàm
mà bản burn dùng quyết định.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.domain.subtitle_format import khoi_chu

router = APIRouter(prefix="/api/subtitles", tags=["subtitles"])


class KhoiChuIn(BaseModel):
    text: str
    #: Kích thước VIDEO thật — cùng hệ với `khung` của `to_ass`.
    khung: tuple[int, int] | None = None
    #: Cùng khối `style` mà `/api/export` và `/api/dubs` nhận.
    style: dict | None = None


class KhoiChuOut(BaseModel):
    lines: list[str]
    #: Bề rộng / chiều cao KHỐI CHỮ (chưa cộng viền), đơn vị pixel của video.
    rong: int
    cao: int
    co: int
    vien: int
    le: int
    rong_kha_dung: int


@router.post("/lines", response_model=KhoiChuOut)
def lines(body: KhoiChuIn) -> KhoiChuOut:
    """Bẻ dòng + đo khối chữ bằng ĐÚNG hàm của bản burn."""
    return KhoiChuOut(**khoi_chu(body.text, khung=body.khung, style=body.style))
