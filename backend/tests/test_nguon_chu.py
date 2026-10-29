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
