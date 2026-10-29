"""Adapter OCR: dựng video tổng hợp có chữ, đọc lại, kiểm ba điều.

Không cần video thật: `ffmpeg` vẽ được chữ trắng trên nền đen, đúng hình dạng phụ đề cứng.
Bài này đi qua `rapidocr` THẬT (đã cài trong venv app), nên nó đo được cả việc model có
đọc ra chữ hay không — không phải mock.

⚠️ Chữ dùng là chữ Latin đơn giản vì `rapidocr-onnxruntime 1.4.4` đóng gói model
`ch_PP-OCRv4` (Trung) nhưng vẫn đọc được chữ Latin in rõ. Video mục tiêu là tiếng Trung;
bài này chỉ kiểm ĐƯỜNG ỐNG, không kiểm chất lượng đọc tiếng Trung.
"""
from __future__ import annotations

import pathlib
import subprocess
import pytest

from app.adapters.ocr_rapidocr import RapidOCREngine
from app.ports.ocr import OCREngine


#: Font PHẢI chỉ định tường minh: `drawtext` không có `fontfile` sẽ chết với
#: "Cannot find a valid font" trên image Debian, và trên Windows thì không có DejaVu.
#:
#: 🔴 VÌ SAO PHẢI CHỌN THEO NỀN TẢNG (đo được, không phải phòng xa):
#:   · container Debian: `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` (đã kiểm `fc-list`)
#:   · Windows: KHÔNG có DejaVu (`C:\Windows\Fonts\DejaVu*` rỗng). Trỏ vào đường Linux thì
#:     `ffmpeg` Windows chết với exit `3221225477` (access violation), không phải lỗi font
#:     lịch sự. `C:\Windows\Fonts\arial.ttf` vẽ được, nhưng phải escape dấu `:` thành `\:`.
#: Nên hàm tự dò: có DejaVu thì dùng, không thì rơi về font hệ thống của nền tảng đang chạy.
def _font_drawtext() -> str:
    r"""Đường font cho `drawtext`, hợp lệ trên nền tảng đang chạy.

    🔴 PHẢI HAI BACKSLASH trên Windows. Đo được bằng `subprocess` (đúng đường test dùng):

        fontfile=C:/Windows/Fonts/arial.ttf      -> exit 4294967274
            "No option name near '/Windows/Fonts/arial.ttf:text=Hello!..."
        fontfile=C:\:/Windows/Fonts/arial.ttf    -> exit 4294967274  (một backslash, vẫn hỏng)
        fontfile=C:\\:/Windows/Fonts/arial.ttf   -> OK, 2262 byte

    Vì sao hai: `drawtext` nhận một chuỗi `key=value` các tham số ngăn bằng `:`; dấu `:` của
    đường dẫn phải escape MỘT lần cho tầng tham số, và escape LẦN NỮA cho tầng parse
    filterchain phía ngoài. Chuỗi Python phải chứa hai ký tự backslash thật, tức viết
    `"\\\\:"` trong mã nguồn — không phải `"\\:"` (một backslash) như bản sửa đầu của tôi.

    Docstring là RAW (tiền tố `r`) vì nó chứa ví dụ có backslash: không raw thì
    Python cảnh báo `DeprecationWarning: invalid escape sequence` và docstring đọc sai.
    """
    for ung in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",   # container Debian, không cần escape
        "C:/Windows/Fonts/arial.ttf",                        # Windows, cần escape `:` hai lần
    ):
        if pathlib.Path(ung).is_file():
            return ung.replace(":", "\\\\:")
    raise RuntimeError("không tìm được font cho drawtext — cài fonts-dejavu-core")


FONT = _font_drawtext()


def _lam_video(ra: str, *, giay: float = 2.0, fps: int = 2) -> str:
    """Video 320x240, nền đen, chữ trắng ở dải dưới (y ~ 200/240 = 0,83).

    🔴 CHỮ PHẢI CÓ DẤU CÂU, không phải `hello world` trần. Đo được: `loc_hinh_dang` bỏ
    mọi hộp mà MỌI ký tự là chữ cái Latinh (`_toan_latinh`, luật của Task 2 để diệt logo
    `ebilibili`), và `rapidocr` đôi khi trả `'helloworld'` — MẤT DẤU CÁCH — nên chữ trần
    bị tầng 3 xoá sạch: `doc_phu_de` trả `[]`, test ĐỎ vì lý do không liên quan tới OCR.
    Đo lại trong container: `'Hello!'` -> `['Hello!']` 1 segment; `'hello world'` ->
    `['hello world']` 1 segment; `'helloworld'` -> 0. Dấu `!` sống sót qua OCR và phá
    luật toàn-Latinh, nên đây là dạng chữ BỀN nhất cho fixture.
    """
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={giay}:r={fps}",
         "-vf", (f"drawtext=fontfile={FONT}:text='Hello!':fontcolor=white:"
                 "fontsize=32:x=40:y=190"),
         "-pix_fmt", "yuv420p", ra],
        check=True, capture_output=True,
    )
    return ra


def test_port_khai_dung_bon_thu():
    """Cổng phải khai `engine_id`, `doc_phu_de`, `release` — cùng khuôn `ASREngine`.

    🔴 KHÔNG dùng `hasattr(OCREngine, "engine_id")`: trong một `Protocol`, `engine_id: str`
    là ANNOTATION, không phải thuộc tính lớp — `hasattr` trả False và test ĐỎ dù cổng
    khai đúng (đo được: `'engine_id' in dir(OCREngine)` = False). Kiểm qua
    `__annotations__`, đúng cách một Protocol khai hợp đồng dữ liệu.
    """
    assert "engine_id" in getattr(OCREngine, "__annotations__", {}), (
        f"cổng phải khai `engine_id: str`; đo được "
        f"{list(getattr(OCREngine, '__annotations__', {}))}"
    )
    for ten in ("doc_phu_de", "release"):
        assert callable(getattr(OCREngine, ten, None)), (
            f"cổng phải khai hàm `{ten}`; đo được {type(getattr(OCREngine, ten, None))}"
        )


def test_doc_duoc_chu_va_tra_segment(tmp_path):
    video = _lam_video(str(tmp_path / "co-chu.mp4"))
    eng = RapidOCREngine()
    try:
        segs = eng.doc_phu_de(video, fps=2.0)
    finally:
        eng.release()
    assert segs, "phải đọc được ít nhất một dòng — video có chữ trắng rõ ràng"
    assert any("hello" in s.text.lower() for s in segs), (
        f"phải đọc ra 'hello', đo được {[s.text for s in segs]}"
    )
    for s in segs:
        assert s.end > s.start, f"end phải sau start: {s}"
        assert s.text.strip()


def test_video_khong_chu_tra_danh_sach_rong(tmp_path):
    """Nền đen trơn ⇒ KHÔNG có dòng nào. Không được bịa."""
    video = str(tmp_path / "trong.mp4")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1:r=2",
         "-pix_fmt", "yuv420p", video],
        check=True, capture_output=True,
    )
    eng = RapidOCREngine()
    try:
        assert eng.doc_phu_de(video, fps=2.0) == []
    finally:
        eng.release()


def test_engine_id_la_chuoi_khong_rong():
    assert RapidOCREngine().engine_id == "rapidocr"


def test_release_an_toan_khi_goi_nhieu_lan():
    """Hợp đồng của `release`: gọi nhiều lần phải an toàn (giống `ASREngine.release`)."""
    eng = RapidOCREngine()
    eng.release()
    eng.release()


def test_khong_co_tep_thi_bao_loi_ro_rang(tmp_path):
    eng = RapidOCREngine()
    try:
        with pytest.raises((FileNotFoundError, RuntimeError)):
            eng.doc_phu_de(str(tmp_path / "khong-co.mp4"), fps=2.0)
    finally:
        eng.release()
