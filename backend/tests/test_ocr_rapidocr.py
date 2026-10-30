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
    return None




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
    font = _font_drawtext()
    if font is None:
        pytest.skip("khong co font DejaVu/Arial cho drawtext — bo qua, khong giet suite")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={giay}:r={fps}",
         "-vf", (f"drawtext=fontfile={font}:text='Hello!':fontcolor=white:"
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

    🔴 VÀ PHẢI KIỂM KIỂU, KHÔNG CHỈ KIỂM TÊN (nợ review Task 3, F4). Bản đầu của bài
    này chỉ hỏi `"engine_id" in __annotations__`, nên `engine_id: int` — một hợp đồng
    SAI hẳn — vẫn XANH.

    ⚠️ `from __future__ import annotations` ở `app/ports/ocr.py` biến MỌI annotation
    thành CHUỖI, nên `khai["engine_id"]` là `'str'` chứ không phải lớp `str` — đo
    được `assert 'str' is str` ĐỎ khi tôi so trực tiếp với lớp. Phép kiểm đúng
    chấp nhận cả hai dạng: lớp thật (không future import) và chuỗi (có future import).
    """
    khai = getattr(OCREngine, "__annotations__", {})
    assert "engine_id" in khai, (
        f"cổng phải khai `engine_id: str`; đo được {list(khai)}"
    )
    kieu = khai["engine_id"]
    ten_kieu = kieu if isinstance(kieu, str) else getattr(kieu, "__name__", repr(kieu))
    assert ten_kieu == "str", (
        f"`engine_id` phải kiểu `str`, đo được {kieu!r} — một kiểu khác"
        f" (ví dụ `int`) là hợp đồng SAI dù tên đúng"
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
    font = _font_drawtext()
    if font is None:
        pytest.skip("khong co font DejaVu/Arial cho drawtext — bo qua, khong giet suite")
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
    """Hợp đồng của `release`: gọi nhiều lần phải an toàn, VÀ phải THẬT SỰ nhả model.

    🔴 Nợ review Task 3 (F8): bản đầu của bài này chỉ gọi `release()` hai lần rồi hết —
    KHÔNG một assert nào, nên `def release(self): pass` cũng XANH. Đó là pin giả: nó
    không phân biệt được `release` thật với `release` rỗng, đúng loại lỗi mà
    `test_mt_opus.py` đã ghi lại cho `OpusMtEngine` ("Test đó KHÔNG kiểm được gì về
    `release()`... Nó xanh trên một `release()` rỗng").

    Nay ghim ĐÚNG thứ `release` hứa: sau khi gọi, `_engine` phải là `None`. Đặt một
    vật giả vào `_engine` thay vì nạp model thật — cùng hợp đồng, không tốn 2 s nạp
    ONNX và không cần `rapidocr` có mặt.
    """
    eng = RapidOCREngine()
    eng._engine = object()          # gói giả: chỉ cần KHÁC None
    assert eng._engine is not None, "phép kiểm vô nghĩa nếu chưa đặt gì"
    eng.release()
    assert eng._engine is None, "release() phải THẬT SỰ nhả model, không chỉ không ném"
    eng.release()                   # lần hai: no-op, không ném
    assert eng._engine is None


def test_khong_co_tep_thi_bao_loi_ro_rang(tmp_path):
    eng = RapidOCREngine()
    try:
        with pytest.raises((FileNotFoundError, RuntimeError)):
            eng.doc_phu_de(str(tmp_path / "khong-co.mp4"), fps=2.0)
    finally:
        eng.release()

