"""`requirements-docker.txt` phải khai MỌI gói mà composition root dò bằng `import`.

## Vì sao tệp này tồn tại

`main.py` quyết định có bật một tính năng hay không bằng cách `import` gói của nó và
bắt `ImportError`. Đó là thiết kế đúng — image thiếu thư viện tuỳ chọn thì tính năng
tự tắt thay vì làm chết cả app. Nhưng nó có một cái bẫy đã ĐO ĐƯỢC (2026-11-01):

  `requirements-docker.txt` không khai `rapidocr-onnxruntime` ⇒ trong container
  `import rapidocr_onnxruntime` ném `ImportError` ⇒ `ocr_engine = None` ⇒
  `TranscribeHandler._ocr is None` ⇒ `transcribe.chon_doan` bỏ hẳn nhánh OCR.

Đo được ngay trong container:

    rapidocr_onnxruntime: THIEU — No module named 'rapidocr_onnxruntime'
    handler = TranscribeHandler    _ocr = None    ocr engine id = None

Hệ quả: chính sách "OCR là CHÍNH, ASR là dự phòng" của `domain/nguon_chu.py` KHÔNG HỀ
CHẠY trên máy này. Mọi job âm thầm dùng ASR — dù ASR chỉ đúng 66,27 % ký tự và dừng ở
1186,4 s, còn OCR phủ tới 1243 s. Test xanh, tính năng có trong mã, sản phẩm chạy đường
khác. Không lỗi nào nổi lên. Đây là kiểu hỏng tệ nhất.

## Vì sao là test CHỮ, không phải test `import`

Bài test này đọc HAI TỆP và đối chiếu chuỗi. Nó KHÔNG `import rapidocr_onnxruntime`:
trên máy chạy test (host venv) gói đó CÓ, nên một bài kiểu `import` sẽ xanh trong khi
image vẫn thiếu — đúng cái bẫy nó sinh ra để bắt. Muốn bắt lỗi của IMAGE thì phải đọc
tệp khai báo của IMAGE.

## Giới hạn phải nói thẳng

Đây là phép kiểm CHUỖI, không phải trình phân giải phụ thuộc: nó biết `rapidocr_onnxruntime`
ứng với dòng `rapidocr-onnxruntime==…` nhờ bảng `_TEN_GOI_PIP` bên dưới, và bảng đó phải
được cập nhật khi thêm một phép dò `import` mới. Nó không chứng minh phiên bản cài được
trên Linux, cũng không chứng minh pip phân giải được — chỉ chứng minh TÊN có mặt.
"""
from __future__ import annotations

import re
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent
MAIN = BACKEND / "app" / "main.py"
DOCKER_REQS = BACKEND / "requirements-docker.txt"

#: Tên module Python -> tên gói trên PyPI, cho những chỗ hai tên KHÁC nhau.
#:
#: Vì sao cần bảng này thay vì đoán: `import rapidocr_onnxruntime` ứng với gói
#: `rapidocr-onnxruntime` (gạch ngang), `import faster_whisper` ứng với
#: `faster-whisper`. Một phép biến đổi `_` -> `-` sẽ đúng cho hai ca đó nhưng SAI cho
#: `rapidocr_onnxruntime` (gói thật là `rapidocr-onnxruntime`, không phải
#: `rapidocr-onnxruntime`… cùng chuỗi, nhưng `PIL` -> `pillow` thì không suy ra được).
#: Bảng tường minh, và mỗi dòng có nguồn: `pip show <gói>` trên venv đã cài.
_TEN_GOI_PIP = {
    "rapidocr_onnxruntime": "rapidocr-onnxruntime",
    "faster_whisper": "faster-whisper",
    "funasr": "funasr",
    "modelscope": "modelscope",
    "demucs": "demucs",
    "torch": "torch",
}


def _goi_duoc_do_bang_import() -> set[str]:
    """Module được dò bằng `import X` trong một khối `try/except ImportError` ở `main.py`.

    Đọc ĐÚNG hình dạng mà `main.py` dùng (xem `main.py:468-473`):

        try:
            import rapidocr_onnxruntime  # noqa: F401
        except ImportError:
            ...

    Chỉ lấy `import` nằm trong một `try:` mà `except` bắt `ImportError` — đó mới là
    phép dò "image này có gói không". Một `import` thường (không bọc) không thuộc
    phạm vi bài này: thiếu nó thì app chết ngay, không phải tắt im lặng.
    """
    dong = MAIN.read_text(encoding="utf-8").splitlines()
    ra: set[str] = set()
    for i, d in enumerate(dong):
        khop = re.match(r"^(\s*)import\s+([A-Za-z_][\w.]*)", d)
        if khop is None:
            continue
        thu_tu, module = khop.group(1), khop.group(2)
        # `import` nằm BÊN TRONG `try:`, nên nó thụt lề SÂU HƠN `try:` một mức; `except`
        # thì ngang mức `try:`. Đây chính là chỗ bản đầu của hàm này sai: nó lấy thụt lề
        # của dòng `import` rồi tìm `except` ở ĐÚNG mức đó, nên không bao giờ khớp và
        # trả về tập RỖNG — và bài `test_the_probe_actually_finds_the_known_import`
        # bắt được đúng lỗi đó ngay lần chạy đầu. Giữ bài ấy.
        if not thu_tu:
            continue
        khop_try = re.match(r"^(\s*)try:\s*$", dong[i - 1]) if i > 0 else None
        if khop_try is None:
            continue
        muc_try = khop_try.group(1)
        # Tìm xuôi xuống: `except ImportError` ngang mức `try:`.
        for j in range(i + 1, min(len(dong), i + 8)):
            if re.match(rf"^{muc_try}except\s+ImportError", dong[j]):
                ra.add(module.split(".")[0])
                break
    return ra


def _goi_trong_docker_reqs() -> set[str]:
    """Tên gói (đã hạ chữ, bỏ `==version`) khai trong `requirements-docker.txt`.

    🔴 CHỈ ĐỌC DÒNG KHAI, KHÔNG ĐỌC CHÚ THÍCH — và đây là lỗi đã đo được của bản đầu.
    Bản đầu cắt `d.split("#", 1)[0]`, tức chỉ bỏ chú thích khi `#` đứng ĐẦU dòng. Nhưng
    tệp này có những dòng chú thích chứa chính tên gói, ví dụ
    `#   rapidocr_onnxruntime: THIEU — No module named ...`. Hệ quả đo được: XOÁ HẲN dòng
    `rapidocr-onnxruntime==1.4.4` mà bài test vẫn XANH, vì tên gói còn nằm trong chú
    thích phía trên. Một bài test như vậy không bảo vệ được gì.

    Nên phép đọc ở đây chỉ nhận dòng BẮT ĐẦU bằng một tên gói hợp lệ
    (`[A-Za-z0-9]`), sau khi bỏ chú thích cuối dòng. Dòng rỗng và dòng bắt đầu bằng `#`
    bị bỏ.
    """
    ra: set[str] = set()
    for d in DOCKER_REQS.read_text(encoding="utf-8").splitlines():
        # Bỏ chú thích CUỐI dòng (`pkg==1.0  # lý do`), rồi bỏ khoảng trắng.
        d = d.split("#", 1)[0].strip()
        if not d:
            continue
        # Dòng khai phải BẮT ĐẦU bằng tên gói. Dòng chú thích đã bị cắt ở trên, nhưng
        # giữ phép kiểm này làm hàng rào thứ hai: nó chặn mọi dòng văn xuôi lọt qua.
        if not re.match(r"^[A-Za-z0-9]", d):
            continue
        ten = re.split(r"[=<>!~\[ ]", d, maxsplit=1)[0].strip().lower()
        if ten:
            ra.add(ten)
    return ra


def test_the_probe_actually_finds_the_known_import():
    """Chứng minh phép đọc không rỗng — nếu không, bài dưới xanh một cách vô nghĩa.

    Không có bài này thì một lỗi trong `_goi_duoc_do_bang_import` (ví dụ `try:` không
    khớp thụt lề) trả về tập RỖNG, và bài đối chiếu bên dưới `for … in set()` cũng
    xanh. Đó là cùng loại lỗi mà cả tệp này sinh ra để bắt.
    """
    thay = _goi_duoc_do_bang_import()
    assert "rapidocr_onnxruntime" in thay, (
        f"phép đọc không thấy phép dò OCR trong main.py — thấy {sorted(thay)}. "
        f"Nếu main.py đã đổi cách dò thì sửa phép đọc ở đây, đừng xoá bài test."
    )


def test_every_import_probed_package_is_declared_for_the_docker_image():
    """Mọi gói mà `main.py` dò bằng `import` phải có trong `requirements-docker.txt`.

    🔴 Đây là bài chặn đúng lỗi đã đo: `rapidocr-onnxruntime` có trong host venv, thiếu
    trong image, nên `_ocr = None` và nhánh OCR KHÔNG BAO GIỜ chạy trên sản phẩm — im
    lặng, không lỗi. Một tính năng chỉ tồn tại trong mã nguồn là một tính năng không có.
    """
    thay = _goi_duoc_do_bang_import()
    khai = _goi_trong_docker_reqs()
    thieu = []
    for module in sorted(thay):
        goi = _TEN_GOI_PIP.get(module)
        assert goi is not None, (
            f"`main.py` dò `import {module}` nhưng bảng `_TEN_GOI_PIP` không biết gói "
            f"PyPI tương ứng. Thêm dòng cho nó (kèm `pip show` để biết tên thật), rồi "
            f"khai gói đó vào requirements-docker.txt."
        )
        if goi.lower() not in khai:
            thieu.append(f"{module} (gói PyPI: {goi})")
    assert not thieu, (
        "requirements-docker.txt thiếu gói mà main.py dò bằng import: "
        + ", ".join(thieu)
        + ". Hệ quả KHÔNG phải một lỗi — nó là tính năng TỰ TẮT IM LẶNG trong image: "
        "`import` ném ImportError, composition root đặt engine đó thành None, và "
        "pipeline lặng lẽ đi đường dự phòng. Đo được với OCR: container thiếu "
        "rapidocr ⇒ `_ocr = None` ⇒ chính sách 'OCR là chính' không hề chạy."
    )


def test_rapidocr_is_declared_with_a_pinned_version():
    """OCR phải ghim PHIÊN BẢN, không phải tên trần.

    Vì sao riêng bài này: `rapidocr-onnxruntime` đóng gói sẵn hai model ONNX
    (`ch_PP-OCRv4_det_infer`, `ch_PP-OCRv4_rec_infer`) và hành vi đọc khung phụ thuộc
    chúng. Một bản mới đổi model hoặc đổi hình dạng `box` sẽ làm
    `ocr_rapidocr._chuan_hoa_box` trả `[]` cho mọi khung — tức OCR "chạy" mà không đọc
    được gì, rồi rơi về ASR. Ghim phiên bản để image dựng lại cho ra cùng kết quả.
    """
    noi_dung = DOCKER_REQS.read_text(encoding="utf-8")
    khop = re.search(r"^rapidocr-onnxruntime==(\d+\.\d+\.\d+)\s*$", noi_dung, re.M)
    assert khop is not None, (
        "requirements-docker.txt phải có dòng `rapidocr-onnxruntime==<x.y.z>` (ghim ba "
        "số), không phải tên trần và không phải khoảng. Đọc tệp để biết vì sao: model "
        "ONNX đi kèm gói, đổi bản là đổi hành vi đọc khung."
    )
