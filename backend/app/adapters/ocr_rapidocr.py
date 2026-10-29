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
    """`(rộng, cao)` của video. Gọi `ffprobe` — không kéo thư viện video vào.

    🔴 AUDIO-ONLY TRẢ `(0, 0)`, KHÔNG NÉM (đo được). `ffprobe` trên một tệp WAV không
    có stream video in ra CHUỖI RỖNG, và `"".split("x")` cho `[""]` — một phần tử, nên
    `rong, cao = ...` ném `ValueError: not enough values to unpack (expected 2, got 1)`.
    Đo được: job `asr` trên WAV 1 giây im lặng -> failed, 0 transcript.

    Audio-only là đầu vào HỢP LỆ của pipeline (video không hình), nên nó phải đi tiếp
    tới chỗ nói "không có phụ đề cứng" chứ không chết ở đây. `(0, 0)` làm
    `tim_dai_phu_de` trả `(0.0, 0.0)` (nó đã có guard `chieu_cao <= 0`), bộ lọc dải
    bị bỏ qua, và tầng 3 xoá sạch hộp — đúng ý "không có gì để đọc".
    """
    ra = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", video_path],
        capture_output=True, text=True, check=True).stdout.strip()
    phan = ra.split("x")
    if len(phan) < 2 or not phan[0] or not phan[1]:
        return 0, 0
    return int(phan[0]), int(phan[1])


def _diem_goc(box) -> list:
    """Chuan hoa `box` cua rapidocr ve `[(x, y), ...]`, hoac `[]` neu khong doc duoc.

    Hai dang da gap:
      · `[[x, y], [x, y], [x, y], [x, y]]` — dang chuan cua rapidocr
      · `[x1, y1, x2, y2, ...]` — list SO PHANG; do duoc `p[0]` tren float nem
        `TypeError: float object is not subscriptable` va giet ca video

    Dang la thi bo hop do, KHONG doan: mot hop hinh hoc sai con te hon khong co hop.
    """
    if not box:
        return []
    try:
        dau = box[0]
        if isinstance(dau, (list, tuple)):
            if len(box) < 3:
                return []
            return [(float(p[0]), float(p[1])) for p in box]
        so = [float(v) for v in box]
    except (TypeError, ValueError, IndexError):
        return []
    if len(so) < 6 or len(so) % 2:
        return []
    return [(so[i], so[i + 1]) for i in range(0, len(so), 2)]


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
        """Một khung -> danh sách `Hop`. `rapidocr` trả `[[box, text, score], ...]`.

        🔴 BA PHÒNG THỦ ĐO ĐƯỢC (review Task 3, finding 6/7/9):
          · `diem` có thể là `None` -> `float(None)` ném `TypeError` và GIẾT CẢ VIDEO,
            không chỉ một hộp. Điểm `None` nghĩa là "không chấm được", không phải 0,
            nên quy về 0.0 và để tầng lọc sau xử lý như một hộp điểm thấp.
          · `text` có thể là `None` -> `str(None)` thành CHUỖI "None" và lọt qua mọi
            tầng lọc như một dòng phụ đề thật. Bỏ hộp đó.
          · hộp có ít hơn 4 điểm -> `p[0]`/`p[1]` vẫn chạy nhưng hình chữ nhật sai;
            bỏ hộp thiếu đỉnh thay vì đoán.
        """
        ra, _ = engine(anh)
        hops: list[Hop] = []
        for muc in ra or []:
            # `muc` phai la day du ba phan tu. Kiem HINH DANG truoc khi `len`:
            # mot float/hop tho trong ket qua rapidocr lam `len(muc)` nem
            # `TypeError: object of type float has no len()` va giet ca video (do duoc).
            if not isinstance(muc, (list, tuple)) or len(muc) < 3:
                continue
            box, text, diem = muc[0], muc[1], muc[2]
            if text is None or not str(text).strip():
                continue
            # `rapidocr` tra `box` la list 4 diem `[[x,y], [x,y], ...]`. Nhung mot so
            # ban/duong goi khac tra list SO PHANG `[x1,y1,x2,y2,...]` — do duoc:
            # `p[0]` tren mot float nem `TypeError: 'float' object is not subscriptable`
            # va giet CA VIDEO. Chap nhan CA HAI dang thay vi doan mot dang.
            diem_anh = _diem_goc(box)
            if not diem_anh:
                continue
            xs = [p[0] for p in diem_anh]
            ys = [p[1] for p in diem_anh]
            hops.append(Hop(text=str(text).strip(), x0=min(xs), y0=min(ys),
                            x1=max(xs), y1=max(ys), t=t,
                            diem=float(diem) if diem is not None else 0.0))
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
        # 🔴 KHONG CO STREAM VIDEO THI KHONG CO PHU DE CUNG (do duoc). `_kich_thuoc` tra
        # `(0, 0)` cho tep audio-only, va `ffmpeg -vf fps=...` tren tep do chet ngay:
        #   exit 4294967274 (khong co stream de loc)
        # Tra `[]` la CAU TRA LOI DUNG ("khong doc duoc phu de nao"), va `chon_nguon`
        # se roi ve ASR. Nem o day bien mot dau vao hop le thanh mot job failed.
        if cao <= 0 or rong <= 0:
            return []
        engine = self._tao_engine()

        with tempfile.TemporaryDirectory(prefix="ocr-") as tam:
            tam_p = pathlib.Path(tam)
            # `ffmpeg` xuat khung o fps yeu cau, ten tep `%06d.png` mang SO THU TU KHUNG.
            #
            # 🔴 `t` LAY TU TEN TEP, KHONG TU `enumerate` (review Task 3, finding 9).
            # Ban dau dung `k / fps` voi `k` la thu tu trong danh sach da sap. Neu mot
            # khung bi thieu (ffmpeg loi mot khung, hoac tep bi xoa), `k` KHONG con bang
            # so thu tu that, va MOI moc thoi gian sau do lech di mot buoc khung — sai
            # am tham, khong bao loi. Doc so tu TEN tep thi khung thieu chi lam thieu mot
            # moc, khong keo theo ca doan sau.
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", video_path, "-vf", f"fps={fps}", str(tam_p / "%06d.png")],
                check=True, capture_output=True)
            hops: list[Hop] = []
            for anh in sorted(tam_p.glob("*.png")):
                # Ten tep `000123.png` -> khung 123 -> `t = (123 - 1) / fps`, vi ffmpeg
                # danh so tu 1. Ten hong thi bo qua khung do thay vi doan bua.
                try:
                    so_khung = int(anh.stem) - 1
                except ValueError:
                    continue
                hops.extend(self._doc_khung(engine, str(anh), so_khung / fps))

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
