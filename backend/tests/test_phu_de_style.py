"""Kiểu chữ phụ đề — `to_ass(style=…)`.

Ba điều phải ghim, vì cả ba đều là chỗ dễ hỏng im lặng:

1. **Không gửi `style` thì tệp ra GIỐNG TỪNG BYTE bản cũ.** Đây là hợp đồng của mọi
   đường xuất đã có; đổi nó là đổi kết quả của những lượt xuất không ai yêu cầu sửa.
2. **`style` áp TRƯỚC khối `khung`, và khối đó nhân tỉ lệ TỪ `tham_so`.** Người dùng chọn
   cỡ chữ trong hệ 1920×1080; video có thể dọc 1080×1920. Áp sau thì cỡ chữ người dùng
   ĐÈ MẤT phần suy theo tỉ lệ và chữ tràn mép — đúng lỗi `_ASS_KHUNG_MAC_DINH` sinh ra
   để chặn.
3. **`Alpha` của ASS NGƯỢC với CSS** (`00` = đục, `FF` = trong). Map sai thì hộp đen
   thành hộp trong suốt, hoặc ngược lại.
"""
from __future__ import annotations

import pytest

from app.domain.models import Segment
from app.domain.subtitle_format import to_ass


def _doan(i=0, start=0.0, end=2.0, text="chữ"):
    return Segment(i=i, start=start, end=end, text=text)


def _dong_style(ass: str) -> str:
    """Dòng `Style:` của tệp — nơi mọi tham số hình thức nằm."""
    for line in ass.splitlines():
        if line.startswith("Style: Default,"):
            return line
    raise AssertionError("không có dòng Style trong tệp .ass")


def _truong(ass: str, ten: str) -> str:
    """Giá trị của một trường trong dòng `Style:` (theo thứ tự `Format:`).

    Dòng có dạng `Style: Default,Archivo,54,…` — tiền tố `Style: ` nằm CÙNG trường với
    `Default`, nên phải bỏ nó TRƯỚC khi tra chỉ số. Bản đầu tôi `split(",", 1)` rồi tra,
    và mọi trường lệch một cột (`Fontsize` đọc ra mã màu).
    """
    thu_tu = [
        "Name", "Fontname", "Fontsize", "PrimaryColour", "SecondaryColour",
        "OutlineColour", "BackColour", "Bold", "Italic", "Underline", "StrikeOut",
        "ScaleX", "ScaleY", "Spacing", "Angle", "BorderStyle", "Outline", "Shadow",
        "Alignment", "MarginL", "MarginR", "MarginV", "Encoding",
    ]
    gia_tri = [x.strip() for x in _dong_style(ass).split(",")]
    gia_tri[0] = gia_tri[0].removeprefix("Style: ")
    return gia_tri[thu_tu.index(ten)]


def test_khong_style_thi_GIONG_TUNG_BYTE():
    """`style=None` và không truyền `style` phải ra CÙNG một chuỗi."""
    doan = [_doan(0), _doan(1, 2.0, 4.0, "hai")]
    assert to_ass(doan) == to_ass(doan, style=None)


def test_style_doi_co_chu_va_mau():
    doan = [_doan()]
    ass = to_ass(doan, style={"co": 72, "mau_chu": "#ff0000"})
    assert _truong(ass, "Fontsize") == "72"
    # `#ff0000` -> BGR `0000FF`, alpha `00` (đục) vì CSS alpha 255.
    assert _truong(ass, "PrimaryColour") == "&H000000FF"


def test_style_hop_DO_DUC_dung_chieu_alpha_nguoc():
    """`do_duc_hop` là độ ĐỤC theo CSS (1 = đục hẳn).

    CSS `1.0` -> alpha CSS 255 -> alpha ASS `00`. CSS `0.0` -> ASS `FF`.
    """
    doan = [_doan()]
    duc = to_ass(doan, style={"mau_hop": "#000000", "do_duc_hop": 1.0})
    trong = to_ass(doan, style={"mau_hop": "#000000", "do_duc_hop": 0.0})
    assert _truong(duc, "BackColour") == "&H00000000"
    assert _truong(trong, "BackColour") == "&HFF000000"


def test_style_dam_nghieng_va_can_le():
    doan = [_doan()]
    ass = to_ass(doan, style={"dam": True, "nghieng": True, "can_le": 2})
    assert _truong(ass, "Bold") == "-1"
    assert _truong(ass, "Italic") == "-1"
    assert _truong(ass, "Alignment") == "2"


def test_style_ap_TRUOC_khung_nen_co_chu_van_duoc_suy_theo_ti_le():
    """Cỡ chữ người dùng chọn là hệ 1920×1080; khung dọc phải NHÂN TỈ LỆ.

    Khung 1080×1920: `ti_le = min(1080/1920, 1920/1080) = 0,5625`.
    `co = 60` -> `round(60 × 0,5625) = 34`.
    """
    doan = [_doan()]
    ass = to_ass(doan, khung=(1080, 1920), style={"co": 60})
    assert _truong(ass, "Fontsize") == "34", (
        "cỡ chữ phải bị nhân tỉ lệ theo khung dọc, đo được "
        + _truong(ass, "Fontsize")
    )


def test_style_khong_duoc_doi_he_toa_do():
    """`style` là danh sách TRẮNG: khoá lạ như `rx` phải bị bỏ.

    Chèn bừa `rx` sẽ đổi `PlayResX` và làm libass co giãn sai — đúng thứ cần chặn.
    """
    doan = [_doan()]
    ass = to_ass(doan, style={"rx": 640, "ry": 480, "wrap": 0})
    assert "PlayResX: 1920" in ass
    assert "PlayResY: 1080" in ass
    assert "WrapStyle: 2" in ass


def test_style_so_vo_LY_bi_KEP_chu_khong_no():
    """Cỡ chữ 5 px hay 900 px vẫn phải ra tệp đọc được — kẹp, không ném."""
    doan = [_doan()]
    assert _truong(to_ass(doan, style={"co": 5}), "Fontsize") == "8"
    assert _truong(to_ass(doan, style={"co": 900}), "Fontsize") == "400"


def test_style_mau_SAI_thi_nem():
    """Màu sai là lỗi của bên gọi — im lặng đổi màu là giấu lỗi."""
    with pytest.raises(ValueError):
        to_ass([_doan()], style={"mau_chu": "đỏ"})
