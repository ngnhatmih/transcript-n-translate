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

import re
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


# ─────────────────────── hộp vector: chia mảnh theo HAI trục ───────────────────────
#
# libass THU NHỎ một hình vẽ vector khi nó vượt `PlayResX / 2` (đo được 600→540,
# 800→540, 2400→540 trên khung 1080) và cả khi nó quá cao (`cao = 960` → **864**, tức
# còn 0,9). Nên hộp được chia thành nhiều mảnh ≤ `rx/2` × `ry/4`.
#
# 🔴 VỊ TRÍ: đo được trên ảnh burn, một mảnh cao `h` neo `\pos(x, p)` (hệ `\an2`, toạ độ
# dương) hiện ra ở `[p − 2h, p − h]` — ĐÁY THẬT là `p − h`, KHÔNG phải `p`. Hai công
# thức dưới đây là hệ quả của phép đo đó; nếu libass đổi thì các test này phải đổi theo
# ảnh burn mới, không phải sửa cho vừa code.
#
# Vì sao các test dưới truyền `rong_hop = 600`: máy chạy test KHÔNG có
# `/usr/share/fonts/truetype/archivo/Archivo.ttf`, nên `_do_khoi_chu` trả `(0, 0, 0)` và
# `ngang = 0` ("bám chữ") không đo được ⇒ `ve_hop` False ⇒ không có mảnh nào để kiểm.
# Chiều cao thì không cần đo, nên đặt sẵn bề rộng là đủ để kiểm hình học dọc.


def _manh_hop(ass: str) -> list[tuple[int, int, int, int]]:
    """`(x, y, rộng, cao)` của TỪNG mảnh hộp vector trong tệp."""
    ra = []
    for line in ass.splitlines():
        if "\\p1" not in line:
            continue
        x, y = (int(v) for v in line.split("\\pos(")[1].split(")")[0].split(","))
        # `m 0 0 l {rong} 0 {rong} -{cao} 0 -{cao}`: lấy hai số ĐẦU của cạnh thứ nhất.
        rong, cao = re.search(r"m 0 0 l (\d+) 0 \d+ (-?\d+)", line).groups()
        ra.append((x, y, int(rong), -int(cao)))
    return ra


def _khung_hop(ass: str) -> tuple[int, int]:
    """`(đỉnh, đáy)` của hộp trên khung, theo hình học ĐÃ ĐO của libass."""
    manh = _manh_hop(ass)
    assert manh, "không có mảnh hộp nào trong tệp"
    return (min(y - 2 * h for _, y, _, h in manh), max(y - h for _, y, _, h in manh))


def _dong_chu(ass: str) -> str:
    for line in ass.splitlines():
        if line.startswith("Dialogue:") and "\\p1" not in line:
            return line
    raise AssertionError("không có sự kiện chữ trong tệp")


_THU = "Chi phi hien tai cua ban la bao nhieu, khong tinh phi nhap la 2000"


def test_hop_CAO_chia_thanh_nhieu_hang_nho():
    """`cao = 960` phải ra 2 hàng ≤ `ry/4`, KHÔNG phải một hình vẽ bị thu còn 864."""
    ass = to_ass([_doan(text=_THU)], khung=(1080, 1920), offset_doc=0.05,
                 style={"rong_hop": 600, "cao_hop": 960, "kieu_vien": 3, "co": 41})
    manh = _manh_hop(ass)
    assert len(manh) >= 2, "hộp cao 960 phải chia thành nhiều hàng, đo được %d" % len(manh)
    assert max(h for _, _, _, h in manh) <= 1920 // 4, "mỗi hàng phải ≤ ry/4"
    dinh, day = _khung_hop(ass)
    assert (day - dinh) == 960, "hộp phải CAO ĐÚNG 960, đo được %d" % (day - dinh)


def test_hop_RAT_cao_van_chia_duoc_vao_trong_khung():
    """`cao = 1300` (> `ry/2`) trước đây bị KẸP; nay chia 3 hàng và vẫn trong khung."""
    ass = to_ass([_doan(text=_THU)], khung=(1080, 1920), offset_doc=0.05,
                 style={"rong_hop": 600, "cao_hop": 1300, "kieu_vien": 3, "co": 41})
    dinh, day = _khung_hop(ass)
    assert (day - dinh) == 1300, "hộp phải cao đúng 1300, đo được %d" % (day - dinh)
    assert dinh >= 0, "hộp không được tràn lên trên khung, đỉnh đo được %d" % dinh


def test_hop_MOT_hang_thi_day_hong_dung_bang_y():
    """Một hàng: `\\pos.y = y + cao` để ĐÁY hộp rơi đúng `y` — mốc cũ, không được lệch."""
    ass = to_ass([_doan(text=_THU)], khung=(1080, 1920), offset_doc=0.05,
                 style={"rong_hop": 600, "cao_hop": 400, "kieu_vien": 3, "co": 41})
    dinh, day = _khung_hop(ass)
    assert day == 1824, "đáy hộp phải là `pos_y` của khung (1824), đo được %d" % day
    assert (day - dinh) == 400


def test_chu_NAM_TRONG_hop_khi_hop_cao():
    """Neo chữ phải rơi vào KHOẢNG của hộp, dù hộp 1 hàng hay 3 hàng.

    Đây chính là lỗi đã xảy ra: đổi `\\pos` của mảnh làm hộp trôi khỏi chữ, và trên nền
    xám thì không thấy vì cả hai đều trắng.
    """
    for cao_hop in (400, 960, 1300):
        ass = to_ass([_doan(text=_THU)], khung=(1080, 1920), offset_doc=0.05,
                     style={"rong_hop": 600, "cao_hop": cao_hop,
                            "kieu_vien": 3, "co": 41})
        dinh, day = _khung_hop(ass)
        y_chu = int(_dong_chu(ass).split("\\pos(")[1].split(")")[0].split(",")[1])
        assert dinh <= y_chu <= day, (
            "cao %d: chữ ở %d nằm ngoài hộp [%d, %d]" % (cao_hop, y_chu, dinh, day)
        )


def test_KHONG_DO_DUOC_chu_thi_khong_ve_hop(monkeypatch):
    """`ngang = 0` là "bám chữ" — không đo được chữ thì KHÔNG vẽ hộp, chứ không vẽ hộp rỗng.

    Đây là đường dự phòng đã ghi trong `_do_khoi_chu`; ghim lại vì chính máy chạy test là
    ca "không có font", và nếu nó đổi thì các test hình học ở trên sẽ im lặng bỏ qua.
    """
    from app.domain import subtitle_format as sf

    monkeypatch.setattr(sf, "_FONT_CHO_DUONG", {})
    ass = to_ass([_doan(text=_THU)], khung=(1080, 1920),
                 style={"cao_hop": 960, "kieu_vien": 3, "co": 41})
    assert _manh_hop(ass) == []
