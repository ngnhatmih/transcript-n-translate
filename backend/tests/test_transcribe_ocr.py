"""`TranscribeHandler.chon_doan`: OCR là chính, ASR là dự phòng, không có OCR thì như cũ.

Dùng engine GIẢ cho cả hai — bài này kiểm ĐƯỜNG NỐI, không kiểm chất lượng model (đã có
`test_ocr_rapidocr.py` và các bài ASR riêng).
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest
import soundfile as sf

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.models import Segment
from app.pipeline.transcribe import TranscribeHandler
from app.registry import EngineSpec


class OcrGia:
    engine_id = "ocr-gia"

    def __init__(self, doan):
        self._doan = doan
        self.duoc_goi = 0
        self.khoang_asr_nhan = "chua-goi"

    def doc_phu_de(self, video_path, *, fps=2.0, khoang_asr=None):
        self.duoc_goi += 1
        self.khoang_asr_nhan = khoang_asr
        return list(self._doan)

    def release(self):
        pass


class AsrGia:
    engine_id = "asr-gia"

    def __init__(self, doan):
        self._doan = doan
        self.duoc_goi = 0

    def transcribe(self, audio_path, lang):
        self.duoc_goi += 1
        return list(self._doan)

    def release(self):
        pass


def _media(tmp_path: pathlib.Path) -> pathlib.Path:
    """Một tệp .wav 1 s — handler chỉ cần đường dẫn TỒN TẠI và nằm trong `workdir`."""
    p = tmp_path / "m.wav"
    sf.write(str(p), np.zeros(48_000, dtype=np.float32), 48_000)
    return p


def _spec_asr() -> EngineSpec:
    """`EngineSpec` giả cho `asr-gia`.

    🔴 VÌ SAO CẦN (lỗi của plan, đo được): `TranscribeHandler._engine_for` gọi
    `by_id(self._specs, engine_id)`; với `specs=[]` nó ném
    `KeyError: "engine 'asr-gia' không có trong registry"`. Brief đầu dựng handler bằng
    `TranscribeHandler(r, [], ...)` nên ASR KHÔNG BAO GIỜ chạy, và năm bài đỏ với
    `RuntimeError: không có chữ để lồng tiếng` — đỏ vì lý do không liên quan tới thứ chúng
    định kiểm. Đo được: 5 failed / 2 passed trước khi sửa.
    """
    return EngineSpec(id="asr-gia", label="ASR giả", kind="asr", runtime="inprocess",
                      model_ref="gia", vram_mb=0, langs=("zh",), capabilities={}, opts={})


def _handler(tmp_path, *, ocr=None, asr=None):
    """Handler có `_engine_id` đặt sẵn, để `chon_doan` dùng được NGOÀI `run`.

    `_engine_id` chỉ được `run` gán, nên gọi `chon_doan` trần sẽ thấy `None` và bỏ qua ASR
    một cách CÂM LẶNG (không ném lỗi — nguy hiểm hơn). Bài
    `test_chon_doan_nhan_asr_engine_id_de_dung_duoc_ngoai_run` kiểm đường thay thế.
    """
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    h = TranscribeHandler(r, [_spec_asr()], lambda spec: asr, workdir=tmp_path,
                          ocr_engine=ocr)
    h._engine_id = "asr-gia"
    return h


def test_chon_doan_nhan_asr_engine_id_de_dung_duoc_ngoai_run(tmp_path):
    """`asr_engine_id` cho phép gọi `chon_doan` khi `run` CHƯA chạy (chưa có `_engine_id`).

    Không có tham số này thì `chon_doan` câm lặng bỏ qua ASR — nó không ném lỗi, chỉ trả
    về đường OCR, và người gọi tưởng mọi thứ ổn.
    """
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="từ ASR")])
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    h = TranscribeHandler(r, [_spec_asr()], lambda spec: asr, workdir=tmp_path)
    assert h._engine_id is None, "tiền đề: handler mới chưa có _engine_id"
    doan, ly_do = h.chon_doan(str(_media(tmp_path)), "zh", asr_engine_id="asr-gia")
    assert [s.text for s in doan] == ["từ ASR"], [s.text for s in doan]
    assert "ASR" in ly_do, ly_do
    assert asr.duoc_goi == 1

def test_khong_co_ocr_engine_thi_hanh_vi_y_ban_cu(tmp_path):
    """`ocr_engine=None` ⇒ KHÔNG gọi OCR, dùng ASR.

    Ghim chống hồi quy: mọi bài `transcribe` cũ dựng handler KHÔNG có OCR, nên đường đó phải
    nguyên vẹn — nếu không, 8 bài cũ sẽ đỏ vì một lý do không liên quan tới chúng.
    """
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="từ ASR")])
    h = _handler(tmp_path, ocr=None, asr=asr)
    doan, ly_do = h.chon_doan(str(_media(tmp_path)), "zh")
    assert [s.text for s in doan] == ["từ ASR"]
    assert "ASR" in ly_do, ly_do
    assert asr.duoc_goi == 1


def test_co_ocr_engine_va_ocr_co_chu_thi_dung_ocr(tmp_path):
    ocr = OcrGia([Segment(i=0, start=0.0, end=1.0, text="từ OCR")])
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="từ ASR")])
    h = _handler(tmp_path, ocr=ocr, asr=asr)
    doan, ly_do = h.chon_doan(str(_media(tmp_path)), "zh")
    assert [s.text for s in doan] == ["từ OCR"]
    assert "OCR" in ly_do, ly_do
    assert ocr.duoc_goi == 1


def test_ocr_rong_thi_roi_ve_asr_va_khong_no(tmp_path):
    """Video không có phụ đề cứng ⇒ OCR trả [] HỢP LỆ ⇒ rơi về ASR, không ném lỗi."""
    ocr = OcrGia([])
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="lời nói thật")])
    h = _handler(tmp_path, ocr=ocr, asr=asr)
    doan, ly_do = h.chon_doan(str(_media(tmp_path)), "zh")
    assert [s.text for s in doan] == ["lời nói thật"]
    assert "ASR" in ly_do, ly_do


def test_ca_hai_deu_rong_thi_nem_loi(tmp_path):
    """Trả `[]` im lặng là bẫy: job sẽ 'thành công' với bản lồng tiếng RỖNG."""
    h = _handler(tmp_path, ocr=OcrGia([]), asr=AsrGia([]))
    with pytest.raises(RuntimeError, match="không có chữ"):
        h.chon_doan(str(_media(tmp_path)), "zh")


def test_ocr_nhan_khoang_asr_tu_doan_asr(tmp_path):
    """Tầng lọc 4 cần `khoang_asr`; handler phải TRUYỀN nó, không bỏ quên.

    Hai đoạn cách 0,2 s phải gộp thành MỘT khoảng (0,0 - 4,0) — việc của `khoang_co_tieng`
    (Task 5), nhưng nếu handler không gọi nó thì tầng 4 sẽ nhận `None`.
    """
    ocr = OcrGia([Segment(i=0, start=0.0, end=1.0, text="từ OCR")])
    asr = AsrGia([Segment(i=0, start=0.0, end=2.0, text="x"),
                  Segment(i=1, start=2.2, end=4.0, text="y")])
    h = _handler(tmp_path, ocr=ocr, asr=asr)
    h.chon_doan(str(_media(tmp_path)), "zh")
    assert ocr.khoang_asr_nhan == [(0.0, 4.0)], ocr.khoang_asr_nhan


def test_dung_ocr_lam_goc_false_thi_bo_qua_ocr(tmp_path):
    """Cờ để tắt OCR cho một lượt (video không có phụ đề: khỏi tốn 6 phút đọc khung)."""
    ocr = OcrGia([Segment(i=0, start=0.0, end=1.0, text="từ OCR")])
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="từ ASR")])
    h = _handler(tmp_path, ocr=ocr, asr=asr)
    doan, _ = h.chon_doan(str(_media(tmp_path)), "zh", dung_ocr_lam_goc=False)
    assert [s.text for s in doan] == ["từ ASR"]
    assert ocr.duoc_goi == 0, "cờ TẮT thì KHÔNG được đọc khung"
