"""Adapter OCR dùng `rapidocr-onnxruntime` — đọc phụ đề cứng của video.

## Vì sao rapidocr

Đo được trên video 1249,237 s (1280x720): 372,8 s cho 2 fps toàn video, ~0,13 s/khung trên
CPU. `rapidocr-onnxruntime 1.4.4` đóng gói sẵn `ch_PP-OCRv4_det_infer.onnx` +
`ch_PP-OCRv4_rec_infer.onnx` — không cần tải model, không cần mạng.

## Adapter này KHÔNG lọc

Nó chỉ: trích khung → gọi rapidocr → đổi toạ độ → giao cho `domain/phu_de.py`. Bốn tầng lọc
nằm ở domain để test được bằng dữ liệu tổng hợp.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile

from app.domain.models import Segment
from app.domain.phu_de import (
    Hop, gop_thanh_dong, loc_hinh_dang, loc_on_dinh, loc_theo_asr, tim_dai_phu_de,
)


def _kich_thuoc(video_path: str) -> tuple[int, int]:
    """`(rộng, cao)` của video. Gọi `ffprobe` — không kéo thư viện video vào."""
    ra = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", video_path],
        capture_output=True, text=True, check=True).stdout.strip()
    rong, cao = ra.split("x")[:2]
    return int(rong), int(cao)


class RapidOCREngine:
    """Đọc phụ đề cứng. Tạo engine MỘT lần, dùng cho nhiều video, `release()` khi xong."""

    engine_id = "rapidocr"

    def __init__(self, *, model_dir: str | None = None) -> None:
        self._model_dir = model_dir
        self._engine = None

    def _tao_engine(self):
        """Tạo `RapidOCR` — tách ra để lỗi import thành câu rõ ràng.

        `rapidocr-onnxruntime` là tuỳ chọn của image: thiếu nó thì câu lỗi phải nêu việc cần
        cài, không phải `ImportError` trần.
        """
        if self._engine is not None:
            return self._engine
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover - image đã cài
            raise RuntimeError(
                "chưa cài OCR: cần `rapidocr-onnxruntime` trong venv của app "
                "(pip install rapidocr-onnxruntime==1.4.4)"
            ) from exc
        self._engine = RapidOCR()
        return self._engine

    def release(self) -> None:
        """Bỏ tham chiếu model. An toàn khi gọi nhiều lần (hợp đồng của cổng)."""
        self._engine = None

    def _doc_khung(self, engine, anh: str, t: float) -> list[Hop]:
        """Một khung → danh sách `Hop`. `rapidocr` trả `[[box, text, score], ...]`."""
        ra, _ = engine(anh)
        hops: list[Hop] = []
        for muc in ra or []:
            box, text, diem = muc[0], muc[1], muc[2]
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            hops.append(Hop(text=str(text).strip(), x0=min(xs), y0=min(ys),
                            x1=max(xs), y1=max(ys), t=t, diem=float(diem)))
        return hops

    def doc_phu_de(self, video_path: str, *, fps: float = 2.0,
                   khoang_asr: list[tuple[float, float]] | None = None
                   ) -> list[Segment]:
        """Xem `OCREngine.doc_phu_de`. Bốn tầng lọc chạy SAU khi đọc hết khung.

        Vì sao đọc hết rồi mới lọc: tầng 1 cần histogram `y` trên toàn video, tầng 2 cần
        biết khung TRƯỚC của cùng dòng. Lọc dòng-bởi-dòng sẽ không làm được cả hai.
        """
        if not pathlib.Path(video_path).is_file():
            raise FileNotFoundError(f"không thấy video: {video_path}")
        if fps <= 0:
            raise ValueError(f"fps phải > 0, đo được {fps}")

        rong, cao = _kich_thuoc(video_path)
        engine = self._tao_engine()

        with tempfile.TemporaryDirectory(prefix="ocr-") as tam:
            tam_p = pathlib.Path(tam)
            # ffmpeg xuar khung ở fps yêu cầu; tên tệp mang số thứ tự nên `t = k / fps`.
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", video_path, "-vf", f"fps={fps}", str(tam_p / "%06d.png")],
                check=True, capture_output=True)
            hops: list[Hop] = []
            for k, anh in enumerate(sorted(tam_p.glob("*.png"))):
                hops.extend(self._doc_khung(engine, str(anh), k / fps))

        if not hops:
            return []

        # Tầng 1: tìm dải y. Chạy trên TOÀN BỘ hộp (rẻ, và chính xác hơn mẫu 50 khung).
        y0, y1 = tim_dai_phu_de(hops, chieu_cao=cao)
        if y1 > y0:
            hops = [h for h in hops if y0 * cao <= h.y0 <= y1 * cao]

        # Tầng 2, 3, (4 tuỳ chọn).
        hops = loc_on_dinh(hops, fps=fps)
        hops = loc_hinh_dang(hops)
        if khoang_asr:
            hops = loc_theo_asr(hops, khoang_asr)

        hops.sort(key=lambda h: (h.t, h.x0))
        return gop_thanh_dong(hops, fps=fps)
