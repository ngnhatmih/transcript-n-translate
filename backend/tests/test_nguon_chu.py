"""Chọn nguồn chữ: OCR là CHÍNH, ASR là dự phòng.

Ba tình huống phải phân biệt được, và chúng KHÁC NHAU về câu trả lời:
  · có OCR  -> dùng OCR (chữ đã biên tập, chính xác hơn ASR);
  · không OCR, có ASR -> dùng ASR (video không có phụ đề cứng);
  · không cả hai -> lỗi rõ ràng, KHÔNG trả danh sách rỗng im lặng.
"""
from __future__ import annotations

import pytest

from app.domain.models import Segment
from app.domain.nguon_chu import (
    LOP_HAI_NGUON,
    LOP_MOT_NGUON,
    chon_nguon,
    hop_nhat_theo_doan,
    khoang_co_tieng,
)


def _seg(i=0, start=0.0, end=2.0, text="chữ"):
    return Segment(i=i, start=start, end=end, text=text)


def test_co_ocr_thi_giu_CA_HAI_dong_mot_dong_moi_lop():
    """HOP DONG MOI (nguoi dung chot 2026-11-02).

    Ban cu bo han chu ASR khi OCR de len. Do duoc tren #36: **51/56 doan
    `hai_nguon` khong con dong ASR nao song song** — chung mang nhan "2 nguon"
    nhung thuc chat chi con chu OCR.

    Nay giu CA HAI, moi dong mot lop, va nguoi dung tu soat tren timeline.
    Ban long loc theo `layer` de khong doc cung mot cau hai lan.
    """
    ocr = [_seg(0, 0.0, 2.0, "từ OCR"), _seg(1, 3.0, 5.0, "câu hai")]
    asr = [_seg(0, 0.0, 2.0, "từ ASR nghe nhầm")]
    doan, ly_do = chon_nguon(ocr, asr)

    chu = [s.text for s in doan]
    assert "từ OCR" in chu, chu
    assert "câu hai" in chu, chu
    assert "từ ASR nghe nhầm" in chu, "phai GIU ca dong ASR: " + repr(chu)
    assert "OCR" in ly_do, ly_do


def test_khong_co_ocr_thi_dung_asr():
    asr = [_seg(0, 0.0, 2.0, "từ ASR")]
    doan, ly_do = chon_nguon([], asr)
    assert [s.text for s in doan] == ["từ ASR"]
    assert "ASR" in ly_do, ly_do


def test_khong_co_gi_ca_thi_bao_loi():
    """Danh sách rỗng im lặng là bẫy: job sẽ 'thành công' với bản lồng tiếng rỗng."""
    with pytest.raises(RuntimeError, match="không có chữ"):
        chon_nguon([], None)
    with pytest.raises(RuntimeError, match="không có chữ"):
        chon_nguon([], [])


def test_ocr_rong_vi_video_khong_phu_de_thi_roi_ve_asr():
    """Video không có phụ đề cứng ⇒ OCR trả [] một cách HỢP LỆ, không phải lỗi."""
    asr = [_seg(0, 0.0, 2.0, "lời nói thật")]
    doan, ly_do = chon_nguon([], asr)
    assert len(doan) == 1
    assert "ASR" in ly_do


def test_khoang_co_tieng_gop_khoang_sat_nhau():
    """Hai đoạn cách nhau 0,2 s là MỘT khoảng (nhiễu cắt dòng), không phải hai."""
    doan = [_seg(0, 0.0, 2.0), _seg(1, 2.2, 4.0), _seg(2, 10.0, 12.0)]
    ra = khoang_co_tieng(doan)
    assert ra == [(0.0, 4.0), (10.0, 12.0)], ra


def test_khoang_co_tieng_rong_khi_khong_co_doan_nao():
    assert khoang_co_tieng([]) == []


# ---------------------------------------------------------------------------
# HỢP NHẤT THEO TỪNG ĐOẠN — chính sách chủ dự án đặt ra:
#
#   "kết hợp asr nghe trước để biết đoạn nào nói. Sau đó duyệt qua ocr. Nếu đoạn nào tách
#    từ asr mà có cả ocr rồi thì đè ocr lên dùng. Kể cả 1 đoạn asr có 2 đoạn ocr thì ưu tiên
#    dùng 2 đoạn ocr đó mà bỏ đoạn 1 đoạn asr kia. Còn nếu đoạn nào mà có asr nhưng ko có ocr
#    thì đoạn đấy có thể thuộc diện nghi ngờ (Nhưng đó là chỉ nếu đang bật ocr)"
#
# ⚠️ MỐC THỜI GIAN: mọi dòng OCR đều dài đúng 0,50 s (đo được trên 77 dòng của transcript
# #13) vì `gop_thanh_dong` đặt `end = t_hộp_cuối + 1/fps`, fps = 2. Đó là độ phân giải
# THẬT của OCR, nên test dưới đây dùng mốc lệch nhau dưới `DUNG_SAI_OCR` — không so khít.
# ---------------------------------------------------------------------------


def test_doan_asr_co_ocr_de_len_thi_giu_CA_HAI():
    """HOP DONG MOI: ASR nghe nham + OCR doc dung ⇒ giu ca hai, de nguoi dung thay.

    Do duoc tren #36 ca that:

        ASR "你见过人类做海豹吗"   <- nghe SAI (hai cau)
        OCR "你见过人类做海报吗"   <- doc DUNG (poster)

    Bo dong ASR la giau di rang may da nghe sai cho nay.
    """
    asr = [_seg(0, 10.0, 12.0, "从 OCR nghe nham")]
    ocr = [_seg(0, 10.0, 10.5, "chữ đã biên tập")]
    doan, ly_do = chon_nguon(ocr, asr)

    chu = [s.text for s in doan]
    assert "chữ đã biên tập" in chu, chu
    assert "从 OCR nghe nham" in chu, "phai giu ca dong ASR: " + repr(chu)
    assert "hợp nhất" in ly_do, ly_do


def test_mot_doan_asr_chua_hai_dong_ocr_thi_giu_ca_hai():
    """Yêu cầu nguyên văn: "1 đoạn asr có 2 đoạn ocr thì ưu tiên dùng 2 đoạn ocr đó"."""
    asr = [_seg(0, 20.0, 23.0, "hai câu gộp làm một")]
    ocr = [_seg(0, 20.0, 20.5, "câu thứ nhất"), _seg(1, 21.0, 21.5, "câu thứ hai")]
    doan, _ = chon_nguon(ocr, asr)
    assert [s.text for s in doan] == ["câu thứ nhất", "câu thứ hai"], [s.text for s in doan]


def test_doan_asr_khong_co_ocr_thi_giu_va_danh_dau_nghi_ngo():
    """Có tiếng nói mà OCR không đọc ra ⇒ nghi ngờ, NHƯNG vẫn giữ (không xoá lời nói)."""
    asr = [_seg(0, 30.0, 32.0, "lời nói không có phụ đề")]
    ocr = [_seg(0, 10.0, 10.5, "một dòng khác")]
    doan, ly_do = chon_nguon(ocr, asr)
    nghi = [s for s in doan if s.suspect]
    assert len(nghi) == 1, [(s.text, s.suspect) for s in doan]
    assert nghi[0].text == "lời nói không có phụ đề"
    assert "nghi ngờ" in ly_do, ly_do


def test_dong_ocr_khong_de_len_asr_nao_van_duoc_giu():
    """ASR dừng sớm (đo được: 1186,4 s) còn OCR phủ tới 1243 s — phần đó KHÔNG được mất."""
    asr = [_seg(0, 10.0, 12.0, "lời nói")]
    ocr = [_seg(0, 10.0, 10.5, "lời nói"), _seg(1, 1200.0, 1200.5, "phần ASR không nghe ra")]
    doan, _ = chon_nguon(ocr, asr)
    assert "phần ASR không nghe ra" in [s.text for s in doan], [s.text for s in doan]


def test_khong_dung_mot_dong_ocr_hai_lan():
    """Hai đoạn ASR cùng đè một dòng OCR ⇒ dòng đó chỉ xuất hiện MỘT lần (không chép đôi)."""
    asr = [_seg(0, 10.0, 11.0, "a"), _seg(1, 10.0, 11.5, "b")]
    ocr = [_seg(0, 10.0, 10.5, "chữ duy nhất")]
    doan, _ = chon_nguon(ocr, asr)
    assert [s.text for s in doan].count("chữ duy nhất") == 1, [s.text for s in doan]


def test_i_duoc_danh_lai_lien_mach_theo_thu_tu_start():
    """`i` là SỐ THỨ TỰ, không phải danh tính — lỗ hổng ở đây làm PATCH /segments/{i} trỏ sai."""
    asr = [_seg(0, 30.0, 32.0, "sau"), _seg(1, 10.0, 12.0, "trước")]
    ocr = [_seg(0, 10.0, 10.5, "trước")]
    doan, _ = chon_nguon(ocr, asr)
    assert [s.i for s in doan] == list(range(len(doan))), [s.i for s in doan]
    assert [s.start for s in doan] == sorted(s.start for s in doan), [s.start for s in doan]


def test_chi_co_asr_thi_KHONG_danh_dau_nghi_ngo():
    """🔴 Điểm dễ sai: "OCR bật mà đọc ra rỗng" KHÁC "không có OCR".

    Video không có phụ đề cứng ⇒ OCR trả `[]` hợp lệ ⇒ đánh dấu nghi ngờ TẤT CẢ sẽ biến
    một video sạch thành 451 việc giả.
    """
    asr = [_seg(0, 0.0, 2.0, "lời nói"), _seg(1, 3.0, 5.0, "câu hai")]
    doan, ly_do = chon_nguon([], asr)
    assert [s.suspect for s in doan] == [False, False], [s.suspect for s in doan]
    assert "ASR" in ly_do, ly_do


def test_chi_co_ocr_thi_KHONG_danh_dau_nghi_ngo():
    """Không có ASR ⇒ không có bằng chứng nào nói dòng OCR sai."""
    ocr = [_seg(0, 0.0, 0.5, "một"), _seg(1, 1.0, 1.5, "hai")]
    doan, ly_do = chon_nguon(ocr, None)
    assert [s.suspect for s in doan] == [False, False]
    assert "OCR" in ly_do, ly_do

def test_doan_asr_KHONG_khop_thoi_gian_nhung_TRUNG_CHU_dong_ocr_da_dung_thi_bo():

    """ASR va OCR lech nhau vai phan tram giay => van la CUNG mot cau, khong duoc giu hai.

    🔴 DO DUOC tren transcript #30 (nguon 6, 131 doan): **19/130 cap chong thoi gian**,
    gan nhu toan bo la cung mot cau hien hai lan — mot ban `suspect=True` (ASR) va mot ban
    `suspect=False` (OCR):

        i=1 [1.14-2.42] S "最苦恼的事就是"
        i=2 [1.50-2.42]   "最苦恼的事就是"

    Nguyen nhan: `ung_vien` doi hoi GIAO THOI GIAN > 0. Khi ASR bat dau TRUOC OCR (1.14 so
    voi 1.50) thi giao van duong, nhung khi lech han thi khong — va doan ASR van duoc giu
    nguyen, ke ca khi chu cua no TRUNG KHIT mot dong OCR da dung.

    Hau qua: ban long doc cung mot cau HAI LAN.
    """

    asr = [_seg(0, 1.14, 2.42, "câu này nói một lần")]

    ocr = [_seg(0, 3.50, 4.20, "câu này nói một lần")]

    doan, _ = chon_nguon(ocr, asr)

    assert len(doan) == 1, [(s.start, s.end, s.text, s.suspect) for s in doan]

    assert doan[0].text == "câu này nói một lần"

    assert not doan[0].suspect, "ban OCR la ban dung, khong duoc danh nghi ngo"



def test_doan_asr_CHUA_chu_cua_dong_ocr_da_dung_thi_bo():

    """Chieu nguoc lai: ASR gop nhieu dong OCR thanh mot cau dai.

    🔴 DO DUOC tren #30:

        i=5 [7.02-9.66] S "要经常证明自己的作品是有价值的长"
        i=6 [7.50-8.00]   "经常要证明"
        i=7 [8.00-9.10]   "自己的作品是有价值的"

    Doan ASR chua TOAN BO chu cua hai dong OCR, va hai dong OCR da duoc dung. Giu ca ba
    la lap.
    """

    asr = [_seg(0, 7.02, 9.66, "nói một câu dài gồm hai vế")]

    ocr = [

        _seg(0, 20.00, 20.50, "nói một câu"),

        _seg(1, 20.50, 21.60, "dài gồm hai vế"),

    ]

    doan, _ = chon_nguon(ocr, asr)

    assert len(doan) == 2, [(s.start, s.end, s.text, s.suspect) for s in doan]

    assert all(not s.suspect for s in doan), [(s.text, s.suspect) for s in doan]



def test_doan_asr_khac_chu_han_thi_VAN_giu_du_thoi_gian_lech():

    """Veh nguoc lai: chi bo khi CHU trung. Lech thoi gian ma chu KHAC thi van phai giu.

    Day la ve chong lai ban sua: neu chi so THOI GIAN (hoac bo qua buoc kiem chu) thi mot
    doan ASR that su khac bi se bi xoa — mat loi noi.
    """

    asr = [_seg(0, 1.14, 2.42, "lời nói thật sự khác")]

    ocr = [_seg(0, 3.50, 4.20, "dòng phụ đề hoàn toàn khác")]

    doan, _ = chon_nguon(ocr, asr)

    assert len(doan) == 2, [(s.text, s.suspect) for s in doan]

    nghi = [s for s in doan if s.suspect]

    assert len(nghi) == 1 and nghi[0].text == "lời nói thật sự khác"

def test_doan_asr_SAI_MOT_CHU_so_voi_ocr_van_la_ban_sao():

    """OCR doc `集` con ASR nghe `街` trong CUNG mot cau — van phai coi la ban sao.

    🔴 DO DUOC tren transcript #31:

        [228.99-230.71]S "在整个集区藏了很多个福"
        [229.00-229.97]  "在整个街区藏了很多个“福"

    Phep so `in` KHONG bat duoc cap nay (sai mot chu), nen phai them ti le ky tu.
    Do 11 cap biet truoc:

        cung cau:  0,90   0,91   0,87
        khac cau:  0,00   0,00   0,00   0,32

    Khoang trong 0,32 -> 0,87 rong, nen nguong 0,85 an toan.
    """

    asr = [_seg(0, 228.99, 230.71, "在整个集区藏了很多个福")]

    ocr = [_seg(0, 229.00, 229.97, "在整个街区藏了很多个“福")]

    doan, _ = chon_nguon(ocr, asr)

    # LUAT MOI (nguoi dung chot): lop 1 = OCR mac dinh + ASR nhung cho OCR KHONG co;
    # lop 2 = ASR o doan OCR CO. Nen dong OCR LUON lop 1, va bang chung "cung mot
    # cau" la su co mat cua mot dong ASR o LOP 2.
    assert len(doan) == 2, [(s.start, s.text, s.layer) for s in doan]

    # LUAT MOI (nguoi dung chot): lop 1 = OCR mac dinh + ASR nhung cho OCR KHONG co;
    # lop 2 = ASR o doan OCR CO. Nen dong OCR LUON lop 1, va bang chung "cung mot
    # cau" la su co mat cua mot dong ASR o LOP 2.
    assert all(s.layer == LOP_MOT_NGUON for s in doan if not s.suspect), (
        "dong OCR luon lop 1: " + repr([(s.text, s.layer) for s in doan if not s.suspect])
    )
    assert any(s.layer == LOP_HAI_NGUON for s in doan if s.suspect), (
        "sai mot chu van la BAN SAO => co dong ASR o lop 2: "
        + repr([(s.text, s.layer) for s in doan])
    )

    chu = [s.text for s in doan]
    assert "在整个街区藏了很多个“福" in chu, "phai giu ban OCR: " + repr(chu)



# DA THU VA DA BO — ghi lai de khong ai lam lai lan nua.
#
# Y dinh tung la: chi coi OCR la ban sua cua ASR khi CHU tuong ung, de giu duoc ca nhu
# transcript #31 cap 6 (OCR "ΛNI" chong len ASR "所以为什么是榕树女神" — hai thu khac han,
# ca hai deu that).
#
# DO DUOC no KHONG LAM DUOC, vi hai nhom khong tach ra duoc:
#
#                          giaoTho  tiLeASR  lenOCR  lenASR  cungCau
#   fixture cu (OCR thang)   0.50     0.250     5      13     False
#   #31 cap 6  (ASR giu)     0.50     0.258     3      10     False
#   fixture cu (OCR thang)   0.50     0.167    10      15     False
#   #31 cap 8  (ASR giu)     0.50     0.294     5      11     False
#
# Thoi gian chenh 0,008; do dai chenh 2 ky tu; `cungCau` deu False. Khong mot dac trung
# nao tach duoc. Va ap quy tac do lam DO ba bai test cua chinh sach cu
# (`test_co_ocr_thi_dung_ocr`, `..._de_len_thi_dung_chu_ocr`, `..._chua_hai_dong_ocr_thi_giu_ca_hai`)
# — tuc no DOI HOP DONG chu khong sua loi.
#
# Hop dong dang dung: OCR doc CHU DA BIEN TAP nen khi no de len mot doan ASR thi OCR
# thang, ke ca khi ASR nghe ra chu khac. Giu nguyen.



def test_dong_OCR_cach_doan_ASR_nua_giay_KHONG_bi_coi_la_de_nhau():
    """🔴 BUG THAT, do duoc tren transcript #35.

    `ung_vien` tung loc bang `_giao(..., DUNG_SAI_OCR)` — tuc giao DA NOI 0,5 s moi ben.
    Hau qua: mot dong OCR cach doan ASR 0,4 s van duoc coi la "ung vien", chiem mat no,
    roi doan ASR that moi khong con gi de khop va roi vao nhanh "khong co OCR".

    Do duoc truoc khi sua:

        ASR [218.50-219.60]   <- doan truoc
        OCR [220.00-220.50]   giaoTho=0.000 nhung giaoNoi=0.10 -> bi chiem
        ASR [219.17-221.11]   <- doan that, ung_vien RONG
        => "LAMDA" bi gan hai_nguon (SAI: no chi co MOT nguon doc ra) va mat chua_trong dung

    Sau khi loc bang giao THO, dong do khong duoc chon va "LAMDA" thuoc ve dung doan ASR.
    """
    asr = [_seg(0, 218.50, 219.60, "cau truoc"), _seg(1, 219.17, 221.11, "ASR chinh")]
    ocr = [_seg(0, 220.00, 220.50, "NI")]

    ra, _, _ = hop_nhat_theo_doan(ocr, asr)
    the = {x.text: x for x in ra}

    assert the["NI"].layer == LOP_MOT_NGUON, "chi OCR doc ra => MOT nguon"
    assert the["NI"].chua_trong >= 0, "phai tro toi doan ASR bao no"
    assert ra[the["NI"].chua_trong].text == "ASR chinh", "phai tro DUNG doan bao"


def test_hai_doan_cach_nhau_0_3_giay_la_HAI_vat_the_khac_nhau():
    """Truoc day `DUNG_SAI_OCR = 0.5` khien chung bi gop lam mot.

    0,3 s la khoang cach that giua hai vat the tren man hinh, khong phai sai so lam tron.
    Gop chung lam mot se xoa mat mot trong hai.
    """
    asr = [_seg(0, 10.0, 11.0, "loi noi")]
    ocr = [_seg(0, 11.30, 11.80, "phu de")]

    ra, _, _ = hop_nhat_theo_doan(ocr, asr)
    assert [x.text for x in ra] == ["loi noi", "phu de"]
    assert all(x.layer == LOP_MOT_NGUON for x in ra)

def test_dong_OCR_chi_CHAM_MEP_khong_duoc_gan_hai_nguon():
    """🔴 BUG THAT, do duoc tren transcript #38 bang phep do chen trong ham.

    `ung_vien` duoc loc bang giao DA NOI, nen mot dong OCR chi cham mep cung lot vao.
    Ban truoc gan `hai_nguon` cho MOI dong trong do, nen 33/56 dong OCR mang nhan
    "2 nguon" trong khi chung chi co MOT nguon doc ra.

    Do duoc:

        ASR [48.27-50.05] "有时又会显得很荒诞"
          OCR [48.50-49.47] giaoTho=0.970  "有时又会显得很荒诞"  <- CUNG CAU, lop 2
          OCR [50.00-51.09] giaoTho=0.050  "比如这个搞雕塑的"    <- CHAM MEP, lop 1
    """
    asr = [_seg(0, 48.27, 50.05, "有时又会显得很荒诞")]
    ocr = [_seg(0, 48.50, 49.47, "有时又会显得很荒诞"),
           _seg(1, 50.00, 51.09, "比如这个搞雕塑的")]

    ra, _, _ = hop_nhat_theo_doan(ocr, asr)
    the = {x.text: x for x in ra}

    # LUAT MOI: dong OCR LUON lop 1 — ke ca khi cung cau voi ASR.
    #
    # 🔴 DO DUOC (khong phai gia thiet): o ca nay KHONG co dong ASR nao duoc giu.
    # `giu_asr` doi `len(ung_vien) == 1`, ma o day `ung_vien` co HAI dong OCR (mot
    # cau that + mot dong chi cham mep), nen ASR bi bo. Do truc tiep:
    #
    #     so dong ra: 2   so_de: 1   so_nghi: 0
    #     i=0 [48.50-49.47] OCR lop 1  "有时又会显得很荒诞"
    #     i=1 [50.00-51.09] OCR lop 1  "比如这个搞雕塑的"
    #
    # Do la hanh vi CO TU TRUOC, khong phai do doi luat lop. Bai nay chi kiem mot
    # dieu: KHONG dong OCR nao bi gan lop 2 chi vi no nam canh mot doan ASR.
    assert the["有时又会显得很荒诞"].layer == LOP_MOT_NGUON, \
        "dong OCR luon lop 1, du cung cau voi ASR"
    assert the["比如这个搞雕塑的"].layer == LOP_MOT_NGUON, \
        "chi cham mep => cung lop 1 (ASR khong doc ra no)"
    assert all(x.layer == LOP_MOT_NGUON for x in ra), (
        "khong dong OCR nao duoc gan lop 2: " + repr([(x.text, x.layer) for x in ra])
    )
