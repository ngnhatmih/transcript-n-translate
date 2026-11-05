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


def _manh_hop(ass: str) -> list[tuple[float, int, int, int]]:
    """`(pos.x, pos.y, rộng, cao)` của TỪNG mảnh hộp vector trong tệp.

    `pos.x` đọc bằng `float`, KHÔNG `int`: hộp rộng lẻ bị chia mảnh thì tâm mảnh là `.5`
    và chính con số đó là thứ giữ mép trên toạ độ nguyên (xem ERRATA #78).
    """
    ra = []
    for line in ass.splitlines():
        if "\\p1" not in line:
            continue
        x_ra, y_ra = line.split("\\pos(")[1].split(")")[0].split(",")
        # `m 0 0 l {rong} 0 {rong} -{cao} 0 -{cao}`: lấy hai số ĐẦU của cạnh thứ nhất.
        rong, cao = re.search(r"m 0 0 l (\d+) 0 \d+ (-?\d+)", line).groups()
        ra.append((float(x_ra), int(y_ra), int(rong), -int(cao)))
    return ra


def _mep_ngang(ass: str) -> list[tuple[float, float]]:
    """`(mép trái, mép phải)` của từng mảnh hộp — `pos.x` là TÂM mảnh (neo `\\an2`)."""
    return [(x - rong / 2, x + rong / 2) for x, _, rong, _ in _manh_hop(ass)]


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


# ---------------------------------------------------------------------------
# VẠCH HỞ GIỮA HAI MẢNH HỘP — ERRATA #78
#
# 🔴 ĐO ĐƯỢC trên ảnh burn thật (bản dịch #63, câu "Là một người làm nghề thuật",
# `cao_hop 180`, hộp rộng 806 trên khung 1080): HAI CỘT x=539 và x=540 không đen suốt cả
# chiều cao hộp, mỗi cột chỉ phủ ~45 % — nền video lọt qua thành một vạch dọc giữa hộp,
# trong khi bản xem trước trên web (CSS) không có vạch đó.
#
# Nguyên nhân: hộp 806 > `PlayResX/2 = 540` nên bị chia HAI mảnh, mỗi mảnh rộng **403 (số
# LẺ)** ⇒ tâm mảnh là `.5`. Bản cũ ghi `\pos` bằng `int(round(cx))`, mà `round` của Python làm
# tròn CHẴN (338,5 → 338 và 741,5 → 742), nên hai mép kề nhau hở đúng 1 px. Đọc thẳng tệp
# `.ass` của bản cũ:
#
#     mảnh 1: \pos(338) rộng 403 → mép 136,5 … 539,5
#     mảnh 2: \pos(742) rộng 403 → mép 540,5 … 943,5     ← hở 1 px
#
# Bài 1 ghim HÌNH HỌC (nhanh, không cần ffmpeg). Bài 2 BURN THẬT rồi đếm cột — vì lỗi này
# thuần thị giác, một test chỉ so số trong tệp `.ass` sẽ không bắt được nó.
# ---------------------------------------------------------------------------


def _he_hop_rong_le() -> dict:
    """Style của ĐÚNG ca gây lỗi (đo trên ảnh burn thật): hộp rộng **806** trên khung 1080.

    `mau_hop`/`do_duc_hop` khai tường minh: mặc định của hộp là `&HA0000000` (alpha `A0`,
    tức ĐỤC 62 %) — trên nền sáng nó ra màu xám và bài đo pixel bên dưới sẽ không nhận ra
    hộp. Hộp trong ca thật của chủ dự án là ĐEN ĐẶC (`do_duc_hop = 1`).
    """
    return {"rong_hop": 806, "cao_hop": 180, "kieu_vien": 3, "co": 41,
            "mau_hop": "#000000", "mau_chu": "#ffffff", "do_duc_hop": 1}


def test_mep_ngang_cua_manh_hop_la_SO_NGUYEN_va_KHOP_NHAU():
    """Mọi mép của mọi mảnh là số nguyên, và hai mảnh kề CHUNG đúng một mép.

    Đây là điều kiện để libass (rasteriser subpixel) phủ trọn cột ở đường nối: mép nằm trên
    toạ độ nguyên thì không cột nào bị phủ nửa. Lệch `.5` ⇒ vạch hở đúng hai cột.
    """
    ass = to_ass([_doan(text="A")], khung=(1080, 1920), offset_doc=0.21,
                 style=_he_hop_rong_le())
    mep = _mep_ngang(ass)
    assert len(mep) >= 2, "hộp 806 px phải chia mảnh (trần rx/2 = 540), đo được %d" % len(mep)

    for trai, phai in mep:
        assert abs(trai - round(trai)) < 1e-9, f"mép trái {trai} KHÔNG nguyên — sẽ hở vạch"
        assert abs(phai - round(phai)) < 1e-9, f"mép phải {phai} KHÔNG nguyên — sẽ hở vạch"

    mep.sort()
    for (_, phai_truoc), (trai_sau, _) in zip(mep, mep[1:]):
        assert trai_sau == phai_truoc, (
            f"hai mảnh kề lệch nhau: mảnh trước hết ở {phai_truoc}, mảnh sau bắt đầu ở "
            f"{trai_sau} — hở {trai_sau - phai_truoc} px")


def _co_ffmpeg() -> bool:
    import subprocess

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def test_BURN_THAT_khong_co_cot_nao_ho_giua_hai_manh_hop(tmp_path):
    """Burn một khung thật rồi đếm: KHÔNG cột nào bên trong hộp bị nền lọt qua.

    Bài này là bài DUY NHẤT bắt được lỗi thật, vì lỗi nằm ở pixel chứ không ở chuỗi `.ass`.
    Đo trên bản CŨ: cột x=539 và x=540 có màu `(103,101,97)` trên nền `(216,208,192)` — tức
    chỉ phủ ~45 %. Nay cả hai phải là `(0,0,0)`.
    """
    import subprocess

    if not _co_ffmpeg():
        pytest.skip("cần ffmpeg có libass")

    from PIL import Image

    nen = (216, 208, 192)
    ass = to_ass([_doan(text="A", start=0.0, end=1.0)], khung=(1080, 1920),
                 offset_doc=0.21, style=_he_hop_rong_le())
    tep_ass = tmp_path / "box.ass"
    tep_ass.write_text(ass, encoding="utf-8")
    tep_png = tmp_path / "box.png"

    # Thoát đường dẫn y như `tach_nen.remux` (dấu `:` và `\\` có nghĩa trong chuỗi filter).
    duong = str(tep_ass.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"color=c=0x{nen[0]:02X}{nen[1]:02X}{nen[2]:02X}:s=1080x1920:d=1:r=10",
         "-vf", f"ass='{duong}'", "-frames:v", "1", str(tep_png)],
        check=True, capture_output=True)

    px = Image.open(tep_png).convert("RGB").load()
    W, H = 1080, 1920

    def den(c: tuple[int, int, int]) -> bool:
        return max(c) < 40

    hang = [y for y in range(H) if sum(1 for x in range(0, W, 4) if den(px[x, y])) > 60]
    assert hang, "không thấy hộp đen nào trên khung — hộp không được vẽ?"
    y0, y1 = min(hang), max(hang)
    cot = [x for x in range(W) if den(px[x, (y0 + y1) // 2])]
    x0, x1 = min(cot), max(cot)

    # Mười hai hàng sát ĐỈNH hộp: vùng này không có chữ, nên phải đen tuyệt đối.
    ho = [
        (x, px[x, y0 + 5])
        for x in range(x0, x1 + 1)
        for y in range(y0, y0 + 12)
        if not den(px[x, y0 + 5])
    ]
    assert not ho, (
        f"hộp {x1 - x0 + 1} px có {len(set(x for x, _ in ho))} cột bị nền lọt qua, "
        f"ví dụ {ho[:4]} — đó là vạch hở giữa hai mảnh (mép không nguyên)")


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


def test_chu_DAM_phai_di_vao_phep_DO_be_rong(monkeypatch):
    """`dam = True` phải được CHUYỀN vào phép đo, và hộp phải rộng bằng `chữ + 2·viền`.

    🔴 VÌ SAO PHẢI GHIM: đo trên video thật (đoạn 0:40.05, `co 30`, `dam true`, `vien 20`)
    bản cũ vẽ hộp **424** trong khi libass vẽ chữ **428** — đệm mỗi bên còn **1 px** thay vì
    11, tức chữ chạm mép và thò ra ngoài hộp. Nguyên nhân: `_TI_LE_CHU = 0,637` đo trên chữ
    THƯỜNG, còn libass in đậm rộng thêm ~6,5 % (`_TI_LE_CHU_DAM`).

    Máy chạy test không có file font nên không đo được chữ thật; bài này ghim ĐƯỜNG ĐI
    (`dam` tới được `_do_khoi_chu`) và phép cộng `2·vien`, còn con số 1,065 được đo bằng
    burn thật (xem `ERRATA #67`).
    """
    from app.domain import subtitle_format as sf

    da_goi = []

    def gia(chu, font, co, rong_kha_dung, dam=False):
        da_goi.append(bool(dam))
        return (300, 20, 1, ["một dòng"])

    monkeypatch.setattr(sf, "_do_khoi_chu", gia)

    ass = to_ass([_doan(text=_THU)], khung=(1080, 1920),
                 style={"cao_hop": 180, "kieu_vien": 3, "co": 30, "dam": True, "vien": 20})
    assert da_goi == [True], "`dam` không được chuyền vào phép đo: %r" % (da_goi,)
    # `vien = 20` trên khung 1080×1920 -> 20 × 0,5625 = 11 (làm tròn).
    assert _manh_hop(ass)[0][2] == 300 + 2 * 11, (
        "hộp phải rộng `chữ + 2·viền`, đo được %d" % _manh_hop(ass)[0][2]
    )

    da_goi.clear()
    to_ass([_doan(text=_THU)], khung=(1080, 1920),
           style={"cao_hop": 180, "kieu_vien": 3, "co": 30, "dam": False, "vien": 20})
    assert da_goi == [False]



def test_cao_khoi_chu_dung_BUOC_DONG_chu_khong_phai_net_chu(monkeypatch):
    """Chiều cao khối = `nét_một_dòng + (n−1) × bước_dòng`.

    🔴 ĐO ĐƯỢC (ERRATA #72, style `co 91`, 3 dòng, `cao_hop 60`): bản burn vẽ đỉnh ba dòng
    ở **1366 / 1417 / 1468** — bước dòng **51 px = 1,0 × cỡ chữ** — trong khi nét chữ đo qua
    Pillow chỉ **29 px**. Công thức cũ `nét × n = 87` cho hộp cao 109 trong khi khối chữ cao
    132, nên **DÒNG ĐẦU NẰM NGOÀI HỘP** (đúng ảnh chủ dự án gửi).

    Máy chạy test không có file font, nên bài này TIÊM một font giả: nét cao 20 px, mỗi ký tự
    rộng 12 px. Nhờ vậy phép đo chạy được ở mọi máy và con số kiểm là số học thuần.
    """
    from PIL import ImageFont

    from app.domain import subtitle_format as sf

    class FontGia:
        def getbbox(self, s: str):
            #: Nét cao 20 px cho MỌI chuỗi (kể cả "Ạ"), bề rộng 12 px mỗi ký tự.
            return (0, 0, 12 * len(s), 20)

        def getmetrics(self):
            return (45, 11)

    monkeypatch.setitem(sf._FONT_CHO_DUONG, "Archivo", "gia.ttf")
    monkeypatch.setattr(ImageFont, "truetype", lambda *a, **k: FontGia())

    #: `co = 51`, bề ngang cho phép 30 px ⇒ mỗi từ (12 px/ký tự) đứng riêng một dòng.
    dai, cao, so_dong, dong = sf._do_khoi_chu("aa bb cc", "Archivo", 51, 30)

    assert so_dong == 3, f"phải bẻ thành 3 dòng, đo được {so_dong}: {dong}"
    net = int(20 * sf._TI_LE_CHU)          # 12
    dung = net + (so_dong - 1) * 51        # 12 + 2×51 = 114
    assert cao == dung, (
        f"chiều cao khối phải là nét + (n−1)×bước_dòng = {dung}, đo được {cao}. "
        f"Công thức SAI (nét × n) sẽ cho {net * so_dong}."
    )
    assert cao != net * so_dong, "không được quay lại công thức `nét × số_dòng`"



def test_CACH_DAY_di_qua_STYLE_khong_bi_bo_im_lang():
    """`offset_doc` trong `style` phải đổi `\pos` của chữ — nếu không, burn lệch bản web.

    🔴 ĐO ĐƯỢC (chủ dự án: *"bản xuất ra trông vẫn khác xa với bản web"*, ảnh khung 3,03 s):
    bản xem trước đặt hộp đáy ở 79 % chiều cao (`viTriDoc = 0,21`), còn bản BURN đặt hộp sát
    đáy. Nguyên nhân: `offset_doc` là tham số riêng của `to_ass`, và `_style_ass` lọc theo
    danh sách trắng `_ASS_STYLE_CHO_PHEP` — danh sách đó KHÔNG có `offset_doc` (đúng: nó
    không phải trường của dòng `Style:`), nên khoá này bị bỏ IM LẶNG và mọi đường đi qua
    `style` rơi về mặc định 6 %.

    Khung 1080×1920: `pos_y = round(1920 × (1 − offset))` ⇒ 0,06 → 1805; 0,21 → 1517.
    """
    import re

    def pos_y(style: dict) -> int:
        ass = to_ass([_doan(text="Nay toi noi")], khung=(1080, 1920), style=style)
        for line in ass.splitlines():
            if line.startswith("Dialogue:") and "\\p1" not in line:
                return int(re.findall(r"pos\((\d+),(\d+)\)", line)[0][1])
        raise AssertionError("không có sự kiện chữ")

    goc = {"co": 91, "vien": 20, "cao_hop": 180, "kieu_vien": 3, "dam": True}
    assert pos_y(dict(goc)) == 1805, "không khai `offset_doc` thì giữ mặc định 6 %"
    assert pos_y({**goc, "offset_doc": 0.21}) == 1517, (
        "`offset_doc` trong style PHẢI được đọc — nếu không, bản burn nằm sát đáy trong khi "
        "bản xem trước đặt ở 79 % chiều cao"
    )
    #: Tham số truyền TAY thắng style (đường job cũ truyền thẳng, không qua style).
    ass = to_ass([_doan(text="Nay toi noi")], khung=(1080, 1920),
                 offset_doc=0.30, style={**goc, "offset_doc": 0.21})
    for line in ass.splitlines():
        if line.startswith("Dialogue:") and "\\p1" not in line:
            assert re.findall(r"pos\((\d+),(\d+)\)", line)[0][1] == "1344", (
                "offset_doc truyền tay (0,30 → 1344) phải thắng style (0,21 → 1517)"
            )
            break
