"""Chọn nguồn chữ: OCR là CHÍNH, ASR là dự phòng.

Ba tình huống phải phân biệt được, và chúng KHÁC NHAU về câu trả lời:
  · có OCR  -> dùng OCR (chữ đã biên tập, chính xác hơn ASR);
  · không OCR, có ASR -> dùng ASR (video không có phụ đề cứng);
  · không cả hai -> lỗi rõ ràng, KHÔNG trả danh sách rỗng im lặng.
"""
from __future__ import annotations

import pytest

from app.domain.models import Segment
from app.domain.nguon_chu import chon_nguon, khoang_co_tieng


def _seg(i=0, start=0.0, end=2.0, text="chữ"):
    return Segment(i=i, start=start, end=end, text=text)


def test_co_ocr_thi_dung_ocr():
    ocr = [_seg(0, 0.0, 2.0, "từ OCR"), _seg(1, 3.0, 5.0, "câu hai")]
    asr = [_seg(0, 0.0, 2.0, "từ ASR nghe nhầm")]
    doan, ly_do = chon_nguon(ocr, asr)
    assert [s.text for s in doan] == ["từ OCR", "câu hai"]
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


def test_doan_asr_co_ocr_de_len_thi_dung_chu_ocr():
    """Đoạn ASR nghe nhầm, OCR đọc đúng ⇒ phải lấy chữ OCR, bỏ chữ ASR."""
    asr = [_seg(0, 10.0, 12.0, "从 OCR nghe nham")]
    ocr = [_seg(0, 10.0, 10.5, "chữ đã biên tập")]
    doan, ly_do = chon_nguon(ocr, asr)
    assert [s.text for s in doan] == ["chữ đã biên tập"], [s.text for s in doan]
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
