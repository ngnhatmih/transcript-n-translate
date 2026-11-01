"""Bốn tầng lọc phụ đề — hàm THUẦN, không model, không video.

Số đo dùng ở đây lấy từ video thật 1249,237 s (1280x720, tiếng Trung, phụ đề cứng):
  · dải y phụ đề [627, 682]/720 = 0,871..0,947
  · watermark + logo bilibili ở y <= 70
  · 696 dòng OCR thô -> 627 dòng sau lọc 3 tầng (bỏ 69 = 10 %)
  · 69 dòng bị bỏ gồm: menu giá tiền 200 ký tự, chữ chạy danh lam thắng cảnh,
    logo đọc sai thành 'ebilibili'
"""
from __future__ import annotations

import pytest

from app.domain.phu_de import (
    DUNG_SAI_X, Hop, gop_thanh_dong, loc_hinh_dang, loc_on_dinh, loc_theo_asr,
    noi_manh_cung_dong, tim_dai_phu_de,
)

CAO = 720


def _hop(text="xin chào", x0=100.0, y0=630.0, x1=400.0, y1=680.0, t=0.0, diem=0.9):
    return Hop(text=text, x0=x0, y0=y0, x1=x1, y1=y1, t=t, diem=diem)


def test_tim_dai_phu_de_tra_ti_le_khong_phai_pixel():
    """Phải trả TỈ LỆ để tự thích ứng 720p/1080p/4K — cùng video ở hai độ phân giải
    phải cho cùng dải."""
    hops = [_hop(t=float(k)) for k in range(20)]                     # dải phụ đề dày
    hops += [_hop(y0=10.0, y1=60.0, t=float(k)) for k in range(20)]  # watermark
    y0, y1 = tim_dai_phu_de(hops, chieu_cao=CAO)
    assert 0.85 <= y0 <= 0.90, f"y0 phải là tỉ lệ ~0,87, đo được {y0}"
    assert 0.93 <= y1 <= 0.97, f"y1 phải là tỉ lệ ~0,95, đo được {y1}"
    assert y0 < y1
    # cùng hops nhưng khung 1440 -> tỉ lệ KHÔNG đổi
    hops_hd = [_hop(y0=630.0 * 2, y1=680.0 * 2, t=float(k)) for k in range(20)]
    hops_hd += [_hop(y0=10.0 * 2, y1=60.0 * 2, t=float(k)) for k in range(20)]
    y0_hd, y1_hd = tim_dai_phu_de(hops_hd, chieu_cao=CAO * 2)
    assert abs(y0_hd - y0) < 0.02 and abs(y1_hd - y1) < 0.02, (
        f"tỉ lệ phải bất biến theo độ phân giải: {y0:.3f}/{y1:.3f} vs {y0_hd:.3f}/{y1_hd:.3f}"
    )


def test_tim_dai_phu_de_thich_cum_nhieu_hop_hon_la_cum_don():
    """Cụm phụ đề TRẢI trên nhiều dải phải thắng cụm logo DỒN vào một dải, khi số hộp bằng nhau.

    🔴 Vì sao có bài này (đo được, không phải phòng xa): bản sửa đầu tiên của tôi thêm khoá
    "HẸP NHẤT" để chặn cửa sổ rỗng, và khoá đó PHÁ khoá "nhiều hộp nhất" — 30 hộp phụ đề
    trải trên dải 87/88/91 thua 30 hộp logo dồn vào dải 1, hàm trả `(0.02, 0.083)` và bộ lọc
    `y0*cao <= h.y0 <= y1*cao` sau đó XOÁ SẠCH mọi phụ đề. Reviewer Task 2 bắt được.
    Bài này ghim đúng ca đó, nên không bản sửa nào lặp lại lỗi ấy mà lọt.
    """
    hops = [_hop(y0=627.0, y1=680.0, t=float(k)) for k in range(10)]
    hops += [_hop(y0=634.0, y1=680.0, t=float(k)) for k in range(10)]
    hops += [_hop(y0=655.0, y1=680.0, t=float(k)) for k in range(10)]
    hops += [_hop(y0=20.0, y1=60.0, t=float(k)) for k in range(30)]   # logo dồn một dải
    y0, y1 = tim_dai_phu_de(hops, chieu_cao=CAO)
    assert 0.85 <= y0 <= 0.90, (
        f"phải chọn cụm phụ đề ở đáy khung, không phải logo ở đỉnh; đo được {y0}"
    )
    assert 0.93 <= y1 <= 0.97, f"đáy dải phải ~0,94; đo được {y1}"


def test_tim_dai_phu_de_dem_dong_khac_nhau_khong_dem_hop():
    """Logo lặp ở MỌI khung với cùng một chuỗi KHÔNG được thắng phụ đề đổi câu.

    🔴 Vì sao có bài này (đo được, không phải phòng xa): `tim_dai_phu_de` bản đầu đếm SỐ HỘP
    mỗi dải. Logo/wartermark là HẰNG SỐ theo thời gian — nó có ở mọi khung với cùng một
    chuỗi — nên nó luôn thắng phụ đề (chỉ có ở ~40–60 % số khung). Đo được, 6 ca:

        logo 20/20 khung, phụ đề 10/20  -> đếm hộp: px(28,8) SAI | đếm dòng: px(626,4) ĐÚNG
        logo 20/20 khung, phụ đề  1/20  -> đếm hộp: px(28,8) SAI | đếm dòng: px(626,4) ĐÚNG
        watermark 30 hộp vs phụ đề 20   -> đếm hộp: px( 0,0) SAI | đếm dòng: px(626,4) ĐÚNG
        logo 10/10, phụ đề 10/10        -> ĐÚNG cả hai
        không logo                      -> ĐÚNG cả hai
        hoà 20/20 cả hai                -> ĐÚNG cả hai

    Bài này ghim ca SAI nặng nhất: logo 20 khung, phụ đề 10 câu KHÁC NHAU ở 10 khung. Đếm
    hộp cho 20 > 10 nên chọn logo; đếm dòng cho 10 > 1 (logo chỉ MỘT dòng) nên chọn phụ đề.

    Đột biến đã kiểm: trả `dem[i] += 1` (đếm hộp) thì bài này ĐỎ với "đo được 0.028".
    """
    hops = [_hop(text="bilibili", y0=28.0, y1=58.0, t=k * 0.5) for k in range(20)]
    hops += [_hop(text=f"câu phụ đề {k}", y0=627.0, y1=682.0, t=k * 1.0) for k in range(10)]
    y0, y1 = tim_dai_phu_de(hops, chieu_cao=CAO)
    assert 0.85 <= y0 <= 0.90, (
        f"phải chọn dải phụ đề ở đáy khung, không phải logo lặp 20 khung; đo được {y0}"
    )
    assert 0.93 <= y1 <= 0.97, f"đáy dải phải ~0,94; đo được {y1}"

def test_loc_on_dinh_bo_chu_chay():
    """Chữ chạy (dải danh lam thắng cảnh đo được ở giây 1056) đổi vị trí x mỗi khung
    ⇒ loại. Phụ đề đứng yên ⇒ giữ."""
    dung = [_hop(text="câu phụ đề", x0=100.0, t=0.0), _hop(text="câu phụ đề", x0=100.0, t=0.5)]
    chay = [_hop(text="桂林山水", x0=100.0, t=1.0), _hop(text="桂林山水", x0=180.0, t=1.5)]
    ra = loc_on_dinh(dung + chay, fps=2.0)
    assert [h.text for h in ra] == ["câu phụ đề", "câu phụ đề"], [h.text for h in ra]


def test_loc_hinh_dang_bo_menu_gia_tien():
    """Menu giá tiền đo được 200 ký tự và đầy cụm số — nằm ĐÚNG dải phụ đề nên tầng 1
    không bắt được. Tầng 3 phải bắt."""
    dai = _hop(text="辣炒鸡胗24元20元更没想到的是香鸡金针菇15元一份" * 4)
    gia = _hop(text="锅包肉38元 溜肉段28元 鱼香肉丝22元")
    that = _hop(text="这个酸菜里面有肉汤")
    ra = loc_hinh_dang([dai, gia, that])
    assert [h.text for h in ra] == ["这个酸菜里面有肉汤"], [h.text for h in ra]


def test_loc_hinh_dang_bo_logo_doc_sai():
    """`ebilibili` / `Cilibili` là logo bị OCR đọc sai. Quá ngắn và không có nghĩa."""
    ra = loc_hinh_dang([_hop(text="ebilibili"), _hop(text="Cilibili"),
                        _hop(text="你怎么骑")])
    assert [h.text for h in ra] == ["你怎么骑"], [h.text for h in ra]


def test_loc_hinh_dang_bo_dong_lap_lien_tiep():
    ra = loc_hinh_dang([_hop(text="好好好", t=0.0), _hop(text="好好好", t=0.5),
                        _hop(text="好好好", t=1.0), _hop(text="下一句", t=1.5)])
    texts = [h.text for h in ra]
    assert texts.count("好好好") <= 1, f"dòng lặp y nguyên phải gộp, đo được {texts}"


def test_loc_theo_asr_bo_dong_khong_co_tieng_noi():
    """Tầng 4 (TUỲ CHỌN): cửa sổ OCR có chữ mà ASR hoàn toàn im lặng ⇒ nghi vấn.

    Đo được trên video thật: lọc 3 tầng giữ 696 dòng, thêm tầng 4 còn 627 — tức tầng 4
    bắt thêm được phần lớn trong 69 dòng rác.
    """
    co_tieng = [_hop(text="có người nói", t=10.0), _hop(text="menu giá tiền", t=50.0)]
    khoang = [(9.0, 12.0)]        # ASR chỉ có tiếng nói quanh giây 10
    ra = loc_theo_asr(co_tieng, khoang)
    assert [h.text for h in ra] == ["có người nói"], [h.text for h in ra]


def test_loc_theo_asr_khong_bao_gio_lam_rong_khi_asr_rong():
    """ASR không có khoảng nào ⇒ tầng 4 KHÔNG được xoá sạch. Thà giữ rác còn hơn mất phụ đề.

    Đây là ghim chống một lỗi dễ mắc: lọc bằng một nguồn rỗng thì xoá hết.
    """
    hops = [_hop(text="câu một", t=0.0), _hop(text="câu hai", t=5.0)]
    assert loc_theo_asr(hops, []) == hops


def test_gop_thanh_dong_gop_khung_lien_tiep_cung_chu():
    """2 fps: cùng một dòng phụ đề xuất hiện ở nhiều khung ⇒ MỘT Segment, không phải 5."""
    hops = [_hop(text="这个酸菜里面有肉汤", t=0.5 * k) for k in range(5)]
    segs = gop_thanh_dong(hops, fps=2.0)
    assert len(segs) == 1, f"phải gộp thành 1 dòng, đo được {len(segs)}"
    assert segs[0].start == 0.0
    assert abs(segs[0].end - 2.5) < 1e-6, f"kết thúc phải ~2,5 s, đo được {segs[0].end}"
    assert segs[0].text == "这个酸菜里面有肉汤"


def test_gop_thanh_dong_start_lay_tu_hop_dau_khong_phai_khong():
    """`Segment.start` phải là `t` của hộp ĐẦU, không phải hằng 0.

    🔴 Vì sao có bài này (reviewer Task 2, finding 6): bài gộp phía trên dùng hộp đầu
    `t=0.0`, nên `start == 0.0` đúng một cách TÌNH CỜ — đột biến `start=0.0` cho mọi
    Segment vẫn làm bài đó XANH. Đo được: `start=0.0` (cả hai nhánh) và `start=end` đều
    cho 10/10 PASS. Bài này đẩy hộp đầu lên `t=1.0` nên hằng 0 KHÔNG thể qua.
    """
    hops = [_hop(text="câu một", t=1.0), _hop(text="câu một", t=1.5)]
    segs = gop_thanh_dong(hops, fps=2.0)
    assert len(segs) == 1, [s.text for s in segs]
    assert segs[0].start == 1.0, (
        f"start phải lấy từ hộp đầu (1,0 s), không phải 0; đo được {segs[0].start}"
    )
    assert segs[0].end > segs[0].start, (
        f"end phải sau start; đo được start={segs[0].start} end={segs[0].end}"
    )

    """2 fps: cùng một dòng phụ đề xuất hiện ở nhiều khung ⇒ MỘT Segment, không phải 5."""
    hops = [_hop(text="这个酸菜里面有肉汤", t=0.5 * k) for k in range(5)]
    segs = gop_thanh_dong(hops, fps=2.0)
    assert len(segs) == 1, f"phải gộp thành 1 dòng, đo được {len(segs)}"
    assert segs[0].start == 0.0
    assert abs(segs[0].end - 2.5) < 1e-6, f"kết thúc phải ~2,5 s, đo được {segs[0].end}"
    assert segs[0].text == "这个酸菜里面有肉汤"


def test_gop_thanh_dong_tach_khi_chu_doi():
    hops = [_hop(text="câu một", t=0.0), _hop(text="câu một", t=0.5),
            _hop(text="câu hai", t=1.0), _hop(text="câu hai", t=1.5)]
    segs = gop_thanh_dong(hops, fps=2.0)
    assert [s.text for s in segs] == ["câu một", "câu hai"]


def test_gop_thanh_dong_danh_so_tang_dan_tu_khong():
    """`Segment.i` phải là 0,1,2… liên tục — hạ tầng sau (dịch, export) dựa vào đó."""
    hops = [_hop(text=f"câu {k}", t=float(k)) for k in range(4)]
    segs = gop_thanh_dong(hops, fps=2.0)
    assert [s.i for s in segs] == list(range(len(segs))), [s.i for s in segs]


# ───────────── Số đo trên dữ liệu THẬT (video 1249,237 s, 7864 hộp thô) ─────────────
#
# Hai bài dưới ghim hai phát hiện chỉ lộ ra khi chạy OCR thật, không lộ ra bằng fixture
# tổng hợp. Số đo đầy đủ ở docstring `DUNG_SAI_X` và `tim_dai_phu_de`.


def test_tim_dai_phu_de_khong_tra_toan_khung_khi_cum_that_hep():
    """Cụm phụ đề DÀY 2 dải phải thắng cửa sổ RỘNG 15 dải rải rác.

    Đây là lỗi ĐO ĐƯỢC trên video thật, và fixture tổng hợp không bắt được. Bản trước
    chấm điểm bằng TỔNG số dòng, mà tổng ĐƠN ĐIỆU TĂNG theo bề rộng cửa sổ — nên
    `DAY_DAI_TOI_DA` không còn là ràng buộc mà thành MỤC TIÊU, và cửa sổ luôn rộng nhất.
    Đo được trên 7864 hộp thô: cửa sổ 15 dải từ dải 0 có tổng 1121, thắng cụm thật ở dải
    86-87 (tổng 698), trả `y0=0,0000 y1=0,9986` = 100 % khung.

    Fixture dưới đây dựng đúng hình dạng đó ở quy mô nhỏ: nhiều dòng RẢI RÁC ở nửa trên
    (tổng lớn) cộng một cụm DÀY ở đáy (mật độ lớn). Chấm theo mật độ thì cụm đáy thắng.
    """
    hops = []
    # Nửa trên: 60 dòng rải trên 12 dải liền nhau, mỗi dải 5 dòng.
    for i in range(60):
        dai = 10 + (i % 12)
        hops.append(Hop(text=f"tren{i}", x0=100.0, y0=dai * 7.2 + 1,
                        x1=200.0, y1=dai * 7.2 + 6, t=i * 0.5, diem=0.9))
    # Đáy: 30 dòng dồn trong 1 dải (87) -> mật độ 30/1 = 30, cao hơn 60/12 = 5.
    for i in range(30):
        hops.append(Hop(text=f"duoi{i}", x0=100.0, y0=87 * 7.2 + 1,
                        x1=200.0, y1=87 * 7.2 + 6, t=i * 0.5, diem=0.9))

    y0, y1 = tim_dai_phu_de(hops, 720)
    assert y0 >= 0.80, (
        f"phải chọn cụm ĐÁY (dải 87), đo được y0={y0:.4f} — cửa sổ rộng đã thắng lại")
    assert (y1 - y0) < 0.15, (
        f"bề dày phải dưới DAY_DAI_TOI_DA, đo được {y1 - y0:.4f} ({y1 - y0:.0%} khung)")


def test_dung_sai_x_nam_trong_khoang_trong_do_duoc():
    """Ngưỡng `DUNG_SAI_X` phải nằm trong KHOẢNG TRỐNG giữa phụ đề và chữ rời.

    ĐO ĐƯỢC trên 403 text lặp lại của video thật, sau khi lọc đúng dải: spread
    `max(x0)-min(x0)` có 398 text (98,3 %) <= 12 px, rồi KHÔNG CÓ text nào trong
    khoảng 12..31 px, rồi mới tới các mẩu menu ('12' 31 px, '驴肉' 60, '15' 63,
    '20元' 91, '16' 98, '烤' 408, '元' 755).

    Nên mọi ngưỡng trong [12, 31) cho CÙNG kết quả. Ghim CẢ HAI ĐẦU: dưới 12 sẽ bỏ oan
    phụ đề thật (ở 4 px mất 22 text, ở 8 px mất 11), từ 31 trở lên sẽ giữ lại '12' như
    một dòng đứng yên.
    """
    assert 12.0 <= DUNG_SAI_X < 31.0, (
        f"DUNG_SAI_X={DUNG_SAI_X} ra ngoài khoảng trống đo được [12, 31): "
        f"dưới 12 bỏ oan phụ đề thật, từ 31 giữ lại mẩu menu '12'")

    def _hop(text, x0):
        return Hop(text=text, x0=x0, y0=600.0, x1=x0 + 200, y1=640.0, t=0.0, diem=0.9)

    # 12 px: phụ đề thật, phải GIỮ (đây là cạnh dưới của khoảng trống).
    giu = loc_on_dinh([_hop("phu de that", 100.0), _hop("phu de that", 112.0)], fps=2.0)
    assert len(giu) == 2, f"12 px phải coi là ĐỨNG YÊN, đo được {len(giu)}/2 hộp giữ"

    # 31 px: mẩu menu '12', phải BỎ (cạnh trên của khoảng trống).
    bo = loc_on_dinh([_hop("12", 100.0), _hop("12", 131.0)], fps=2.0)
    assert bo == [], f"31 px phải coi là CHẠY, đo được {[h.text for h in bo]} còn lại"


# ---------------------------------------------------------------------------
# NỐI MẢNH CÙNG MỘT DÒNG PHỤ ĐỀ — lỗi chủ dự án báo:
#
#   "bằng 1 cách nào đấy các đoạn dùng ocr bị khá là ngắn mặc dù phụ đề trên vid đoạn phụ
#    đề đấy chưa kết thúc. Nên xem lại."
#
# 🔴 ĐO ĐƯỢC trên transcript #13 (nguồn 2, `vung_doc=[0,0.1,1,1]`, 77 dòng):
#
#     so cap CUNG CHU LIEN NHAU trong danh sach:  0
#     so cap cung chu bi dong khac chen giua:     15, khoang cach DEU = 0,0 s
#
#     '福州烟台山商业漫步街区' x6  moc=[(189.5,190.5),(190.5,191.0),(191.0,191.5),
#                                       (191.5,192.0),(192.0,192.5),(192.5,193.0)]
#
# Dòng đó hiện 3,5 giây THẬT mà thành 6 dòng 0,5 s, vì `gop_thanh_dong` chỉ nối hộp CÙNG
# CHỮ LIỀN NHAU và hai dòng phụ đề đan xen nhau trong danh sách.
#
# ⚠️ Vùng 191–195 s của cùng transcript có BA dòng phụ đề hiện ĐỒNG THỜI ở ba dải `y`, và
# `福州烟台山` xuất hiện ở ba khung liền nhau ở HAI dải khác nhau. Nên phép nối phải có điều
# kiện `y`, không chỉ `text` + thời gian.
# ---------------------------------------------------------------------------


def _hop_o(t, text, y0, y1):
    return Hop(text=text, x0=100.0, y0=y0, x1=500.0, y1=y1, t=t, diem=0.9)


def test_noi_manh_gop_cac_manh_cung_chu_cung_dai_y_bi_chen_giua():
    """Ca THẬT: một dòng hiện 4 khung, một dòng khác chen vào giữa 2 khung đầu."""
    hops = [
        _hop_o(191.0, "A", 600, 650), _hop_o(191.0, "B", 700, 750),
        _hop_o(191.5, "A", 600, 650),
        _hop_o(192.0, "A", 600, 650), _hop_o(192.0, "C", 800, 850),
        _hop_o(192.5, "A", 600, 650), _hop_o(192.5, "C", 800, 850),
    ]
    hops.sort(key=lambda h: (h.t, h.x0))
    ra = noi_manh_cung_dong(hops)
    a = [h for h in ra if h.text == "A"]
    assert len(a) == 1, f"A phải gộp thành MỘT hộp, đo được {len(a)}"
    assert a[0].t == 191.0, f"phải giữ `t` của hộp ĐẦU, đo được {a[0].t}"
    c = [h for h in ra if h.text == "C"]
    assert len(c) == 1, f"C phải gộp thành MỘT hộp, đo được {len(c)}"
    assert len(ra) == 3, f"phải còn A, B, C = 3 hộp, đo được {[h.text for h in ra]}"


def test_noi_manh_KHONG_mat_hop_nao():
    """🔴 LỖI THẬT của bản đầu: `break` nằm NGOÀI `if`, nên vòng lặp chỉ xét đúng phần tử
    cuối của `ra` rồi thoát.

    Đo được hậu quả: 5 hộp `A,B,A,B,A` vào, chỉ **2** hộp ra — `A@2.0` và `A@3.0` BIẾN MẤT
    khỏi kết quả. Đó là MẤT dòng phụ đề, không phải nối sai, nên phải có bài đếm số hộp.
    """
    hops = [
        _hop_o(1.0, "A", 600, 650), _hop_o(1.5, "B", 700, 750),
        _hop_o(2.0, "A", 600, 650), _hop_o(2.5, "B", 700, 750),
        _hop_o(3.0, "A", 600, 650),
    ]
    hops.sort(key=lambda h: (h.t, h.x0))
    ra = noi_manh_cung_dong(hops)
    assert sorted(h.text for h in ra) == ["A", "B"], (
        f"phải còn đúng A và B, đo được {[h.text for h in ra]}")


def test_noi_manh_KHONG_noi_cung_chu_khac_dai_y():
    """`福州烟台山` xuất hiện ở hai dải `y` khác nhau — đó là HAI dòng thật, không phải mảnh.

    Đo được trên #13: `193.00-193.50` ở dải này và `194.00-194.50` ở dải khác. Nối chúng
    thành một dòng 1,5 s là bịa ra một câu chưa ai nói liền mạch.
    """
    hops = [
        _hop_o(193.0, "福州烟台山", 600, 650),
        _hop_o(194.0, "福州烟台山", 800, 850),
    ]
    ra = noi_manh_cung_dong(hops)
    assert len(ra) == 2, f"khác dải y thì KHÔNG nối, đo được {len(ra)} hộp"


def test_noi_manh_KHONG_noi_watermark_lap_lai_xa_nhau():
    """Đo trên #12: 8 cặp cùng chữ nhưng cách nhau 26–134 s — watermark hiện lại.

    Nối chúng sẽ kéo một "dòng phụ đề" từ giây 51 tới giây 185.
    """
    hops = [_hop_o(51.0, "想想工作室", 600, 650),
            _hop_o(185.0, "想想工作室", 600, 650)]
    ra = noi_manh_cung_dong(hops)
    assert len(ra) == 2, f"cách 134 s thì KHÔNG nối, đo được {len(ra)} hộp"


def test_noi_manh_giu_diem_cao_nhat():
    """Mảnh đọc rõ nhất đại diện cho cả lần hiện — điểm tin cậy là max, không phải trung bình."""
    hops = [
        Hop(text="A", x0=100.0, y0=600.0, x1=500.0, y1=650.0, t=1.0, diem=0.4),
        Hop(text="A", x0=100.0, y0=600.0, x1=500.0, y1=650.0, t=1.5, diem=0.95),
    ]
    ra = noi_manh_cung_dong(hops)
    assert len(ra) == 1
    assert ra[0].diem == 0.95, f"phải giữ điểm CAO NHẤT, đo được {ra[0].diem}"


def test_noi_manh_danh_sach_rong_tra_rong():
    assert noi_manh_cung_dong([]) == []


def test_nguong_noi_manh_khop_fps_mac_dinh():
    """`_NHIP_KHUNG` là hằng số CỦA `fps = 2`, không phải hằng số thuật toán.

    `doc_phu_de` nhận `fps` làm tham số; nếu ai đổi mặc định sang `fps = 1` mà không đổi
    hằng số này thì ngưỡng nối thành hai nhịp khung và có thể nối nhầm hai lần hiện khác
    nhau. Bài này ghim sự ràng buộc đó để nó không trôi âm thầm.
    """
    from app.domain.phu_de import _NHIP_KHUNG
    import inspect
    from app.ports.ocr import OCREngine

    mac_dinh = inspect.signature(OCREngine.doc_phu_de).parameters["fps"].default
    assert _NHIP_KHUNG == 1.0 / mac_dinh, (
        f"_NHIP_KHUNG={_NHIP_KHUNG} nhưng fps mặc định là {mac_dinh} "
        f"(1/fps = {1.0 / mac_dinh}) — đổi fps thì phải đổi hằng số này")

# ---------------------------------------------------------------------------
# KÉO `end` THEO MỐC LỜI NÓI ASR — lỗi chủ dự án báo:
#
#   "các đoạn dùng ocr bị khá là ngắn mặc dù phụ đề trên vid đoạn phụ đề đấy chưa kết thúc.
#    Được thì dùng timestamp của asr cx đc nhưng nên tìm cách giải quyết cái này"
#
# 🔴 ĐO ĐƯỢC: mọi dòng OCR đều dài đúng `1/fps` = 0,50 s (76/77 dòng của transcript #13),
# vì `gop_thanh_dong` đặt `end = t_hộp_cuối + 1/fps`. ASR có mốc word-level:
#
#     OCR 193.00..193.50  '你会在山上看到'
#     ASR  你[192.53-193.13] 会[193.13-193.25] 在[193.25-193.35]
#          山[193.35-193.51] 上[193.51-193.63] 看到[193.63-193.81]
#
# Kéo đúng: `end` 193,50 -> 193,81. Đo trên cả tệp: 12/77 dòng được kéo, độ dài trung bình
# 0,506 -> 0,559 s, và số cặp chồng lấn KHÔNG đổi (14 -> 14), tức phép kéo không tạo ra
# chồng lấn mới.
# ---------------------------------------------------------------------------


def _doan(i, start, end, text, suspect=False):
    from app.domain.models import Segment
    return Segment(i=i, start=start, end=end, text=text, suspect=suspect)


def _word(w, s, e):
    from app.domain.models import Word
    return Word(w=w, s=s, e=e)


def test_keo_dai_lay_end_tu_tu_asr_cuoi_cung_khop():
    """Ca THẬT của #13: OCR `你会在山上看到` 0,50 s, lời nói thật tới 193,81."""
    from app.domain.phu_de import keo_dai_theo_asr
    doan = [_doan(0, 193.0, 193.5, "你会在山上看到")]
    tu = [_word("你", 192.53, 193.13), _word("会", 193.13, 193.25),
          _word("在", 193.25, 193.35), _word("山", 193.35, 193.51),
          _word("上", 193.51, 193.63), _word("看到", 193.63, 193.81)]
    ra = keo_dai_theo_asr(doan, tu)
    assert len(ra) == 1
    assert abs(ra[0].end - 193.81) < 0.01, f"end phải là 193,81, đo được {ra[0].end}"
    assert ra[0].start == 193.0, "start KHÔNG đổi — đó là chỗ phụ đề bắt đầu hiện"


def test_keo_dai_KHONG_keo_khi_ASR_noi_chuyen_khac():
    """OCR `胖2026见` gặp ASR `这样一个雷霆大海豹`: khớp dưới ngưỡng ⇒ GIỮ NGUYÊN.

    Đo được: tỉ lệ ký tự OCR có mặt trong ASR cùng cửa sổ là 66,7 % TÍNH TRUNG BÌNH, nhưng
    phân bố không đều — cặp đúng khớp 6/8 tới 8/9, cặp sai gần 0. Kéo theo ASR ở ca sai là
    gán mốc của một câu khác cho dòng này.
    """
    from app.domain.phu_de import keo_dai_theo_asr
    doan = [_doan(0, 193.5, 194.0, "胖2026见")]
    tu = [_word("这样", 193.81, 194.07), _word("一个", 194.07, 194.25),
          _word("雷", 194.25, 194.41), _word("霆", 194.41, 194.53),
          _word("大", 194.53, 194.63), _word("海", 194.63, 194.75),
          _word("豹", 194.75, 194.93)]
    ra = keo_dai_theo_asr(doan, tu)
    assert ra[0].end == 194.0, f"khớp dưới ngưỡng thì KHÔNG kéo, đo được end={ra[0].end}"


def test_keo_dai_dung_o_tu_dau_tien_khong_dong_gop_gi():
    """ASR hay NGHE THÊM chữ ở cuối; lấy từ cuối cả cửa sổ sẽ kéo sang câu sau.

    Đo được: OCR `会显得不太聪明` gặp ASR `价值会显得不太聪明比如` — ASR thừa `比如`.
    """
    from app.domain.phu_de import keo_dai_theo_asr
    doan = [_doan(0, 48.5, 49.0, "会显得不太聪明")]
    tu = [_word("价值", 48.20, 48.50), _word("会", 48.50, 48.70),
          _word("显得", 48.70, 48.90), _word("不太", 48.90, 49.10),
          _word("聪明", 49.10, 49.47),
          # Hai từ THỪA — không có ký tự nào OCR cần.
          _word("比如", 49.47, 49.80)]
    ra = keo_dai_theo_asr(doan, tu)
    assert abs(ra[0].end - 49.47) < 0.01, (
        f"phải dừng ở '聪明' (49,47), không lấy '比如' (49,80); đo được {ra[0].end}")


def test_keo_dai_KHONG_lay_tu_cua_dong_song_song_lam_end():
    """Ba dòng phụ đề hiện ĐỒNG THỜI ở ba dải `y` — phép chặn trên không được cắt oan.

    🔴 LỖI THẬT của bản đầu: chặn vô điều kiện bằng `min(end, doan[k+1].start)`. Đo được:
    nó CẮT SAI 14 cặp, vì dòng kế tiếp trong danh sách bắt đầu ĐÚNG LÚC dòng này bắt đầu
    (hai dòng SONG SONG, không tranh nhau chỗ nói), nên `min` kéo `end` về bằng `start`.
    """
    from app.domain.phu_de import keo_dai_theo_asr
    doan = [
        _doan(0, 193.0, 193.5, "你会在山上看到"),
        _doan(1, 193.0, 193.5, "福州烟台山"),      # SONG SONG: cùng start
    ]
    tu = [_word("你", 192.53, 193.13), _word("会", 193.13, 193.25),
          _word("在", 193.25, 193.35), _word("山", 193.35, 193.51),
          _word("上", 193.51, 193.63), _word("看到", 193.63, 193.81)]
    ra = keo_dai_theo_asr(doan, tu)
    assert abs(ra[0].end - 193.81) < 0.01, (
        f"dòng song song KHÔNG được chặn, đo được end={ra[0].end}")


def test_keo_dai_CHAN_dong_noi_tiep():
    """Vế ngược lại: dòng NỐI TIẾP thì `end` không được vượt `start` của nó."""
    from app.domain.phu_de import keo_dai_theo_asr
    doan = [
        _doan(0, 10.0, 10.5, "你会在山上看到"),
        _doan(1, 11.0, 11.5, "另一句"),
    ]
    tu = [_word("你", 10.0, 10.3), _word("会", 10.3, 10.6),
          _word("在", 10.6, 10.9), _word("山", 10.9, 11.3),
          _word("上", 11.3, 11.6), _word("看到", 11.6, 11.9)]
    ra = keo_dai_theo_asr(doan, tu)
    assert ra[0].end <= 11.0 + 0.001, (
        f"end không được vượt start của dòng nối tiếp (11,0), đo được {ra[0].end}")


def test_keo_dai_KHONG_rut_ngan_end_da_dung():
    """ASR kết thúc SỚM hơn `end` hiện tại thì giữ `end` cũ, không rút ngắn."""
    from app.domain.phu_de import keo_dai_theo_asr
    doan = [_doan(0, 10.0, 12.0, "你会在山上看到")]
    tu = [_word("你", 10.0, 10.2), _word("会", 10.2, 10.4),
          _word("在", 10.4, 10.6), _word("山", 10.6, 10.8),
          _word("上", 10.8, 11.0), _word("看到", 11.0, 11.2)]
    ra = keo_dai_theo_asr(doan, tu)
    assert ra[0].end == 12.0, f"KHÔNG được rút ngắn, đo được {ra[0].end}"


def test_keo_dai_giu_co_suspect():
    """`suspect` do `hop_nhat_theo_doan` đặt phải sống qua phép kéo."""
    from app.domain.phu_de import keo_dai_theo_asr
    doan = [_doan(0, 10.0, 10.5, "你会在山上看到", suspect=True)]
    tu = [_word("你", 10.0, 10.3), _word("会", 10.3, 10.6),
          _word("在", 10.6, 10.9), _word("山", 10.9, 11.3),
          _word("上", 11.3, 11.6), _word("看到", 11.6, 11.9)]
    ra = keo_dai_theo_asr(doan, tu)
    assert ra[0].suspect is True, "cờ nghi ngờ bị mất qua phép kéo"


def test_keo_dai_danh_sach_rong_tra_rong():
    from app.domain.phu_de import keo_dai_theo_asr
    assert keo_dai_theo_asr([], []) == []


def test_keo_dai_khong_co_tu_asr_thi_giu_nguyen():
    from app.domain.phu_de import keo_dai_theo_asr
    doan = [_doan(0, 10.0, 10.5, "你会在山上看到")]
    ra = keo_dai_theo_asr(doan, [])
    assert ra[0].end == 10.5

def test_keo_dai_KHONG_keo_khi_khop_chi_MOT_PHAN():
    """Ngưỡng khớp phải TỰ chặn, không nhờ vòng tích luỹ chặn hộ.

    🔴 PHÉP PHÁ ĐO ĐƯỢC: bỏ hẳn điều kiện ``< KHOP_TOI_THIEU`` (đổi thành ``if False``) mà
    bài ``test_keo_dai_KHONG_keo_khi_ASR_noi_chuyen_khac`` VẪN XANH — vì ở ca đó tỉ lệ khớp
    là 0,000, nên vòng tích luỹ cũng không tìm được ký tự nào đóng góp và ``end`` không đổi.
    Hai cơ chế cùng chặn thì phép phá không nói được cái nào đang giữ.

    Bài này dựng ca mà vòng tích luỹ MỘT MÌNH sẽ kéo: khớp đúng 2/6 ký tự (dưới 0,5) nhưng
    khác rỗng, và từ khớp nằm CUỐI cửa sổ. Bỏ ngưỡng thì ``end`` nhảy sang từ đó; giữ ngưỡng
    thì ``end`` đứng yên.
    """
    from app.domain.phu_de import keo_dai_theo_asr
    # OCR 6 ký tự; từ khớp ('你') nằm CUỐI cửa sổ và ĐÓNG GÓP được, nên vòng tích luỹ một
    # mình sẽ kéo `end` tới 10,9. Tỉ lệ khớp 1/6 = 0,167 < 0,5 ⇒ ngưỡng phải chặn.
    #
    # ĐO ĐƯỢC vì sao cần đúng ca này: bản đầu của bài dùng "你会天地人和" với hai từ khớp ở
    # ĐẦU, tỉ lệ 0,33, và khi bỏ hẳn ngưỡng (`if False:`) bài VẪN XANH — vì từ cuối `别的`
    # không đóng góp ký tự nào nên vòng tích luỹ tự chặn hộ, và phép phá không nói được
    # ngưỡng có đang giữ hay không.
    doan = [_doan(0, 10.0, 10.5, "天地人和你我")]
    tu = [_word("别的", 10.0, 10.3), _word("话", 10.3, 10.6),
          _word("你", 10.6, 10.9)]
    ra = keo_dai_theo_asr(doan, tu)
    assert ra[0].end == 10.5, (
        f"khớp 1/6 = 0,167 dưới ngưỡng 0,5 thì KHÔNG được kéo (bỏ ngưỡng sẽ ra 10,9), "
        f"đo được end={ra[0].end}")