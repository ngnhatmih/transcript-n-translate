"""Cổng OCR: media → danh sách dòng phụ đề có mốc thời gian.

Cùng khuôn với `ports/asr.py`: Protocol + `engine_id` + một hàm chính + `release`. Vì sao
cùng khuôn: có nhiều engine OCR (rapidocr, paddleocr, tesseract) như ASR có nhiều engine,
và tầng trên không được biết engine nào.

Trả `list[Segment]` (model có sẵn) chứ không phải kiểu riêng: OCR và ASR khác nhau ở CÁCH
LẤY chữ, không khác ở HÌNH DẠNG dữ liệu — nên mọi thứ sau đó (dịch, export, lồng tiếng)
không phải phân nhánh.
"""
from __future__ import annotations

from typing import Protocol

from app.domain.models import Segment


class OCREngine(Protocol):
    engine_id: str

    def doc_phu_de(self, video_path: str, *, fps: float = 2.0,
                   khoang_asr: list[tuple[float, float]] | None = None
                   ) -> list[Segment]:
        """Đọc phụ đề CỨNG của `video_path`.

        `fps` = số khung đọc mỗi giây. Đo được trên video 20,8 phút: 2 fps đủ (dòng phụ đề
        ngắn nhất 0,5 s), tốn 372,8 s.

        `khoang_asr` = các khoảng CÓ tiếng nói, để bật tầng lọc 4. `None`/rỗng ⇒ TẮT tầng 4,
        và đó là mặc định: pipeline phải chạy được khi không có ASR.
        """
        ...

    def release(self) -> None:
        """Giải phóng model. Phải an toàn khi gọi nhiều lần."""
        ...
