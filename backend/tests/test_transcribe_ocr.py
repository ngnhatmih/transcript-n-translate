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
from app.domain.models import Job, Segment
from app.pipeline.transcribe import TranscribeHandler
from app.registry import EngineSpec


class OcrGia:
    engine_id = "ocr-gia"

    def __init__(self, doan):
        self._doan = doan
        self.duoc_goi = 0
        self.khoang_asr_nhan = "chua-goi"
        #: Đường dẫn THẬT mà handler đưa cho OCR — xem
        #: `test_run_dua_VIDEO_cho_ocr_chu_khong_phai_wav`.
        self.video_path_nhan = None
        #: `vung_doc` handler truyền — xem `test_run_truyen_vung_doc_tu_handler`.
        self.vung_doc_nhan = "chua-goi"

    def doc_phu_de(self, video_path, *, fps=2.0, khoang_asr=None, vung_doc=None):
        self.duoc_goi += 1
        self.video_path_nhan = str(video_path)
        self.khoang_asr_nhan = khoang_asr
        self.vung_doc_nhan = vung_doc
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


# ---------------------------------------------------------------------------
# Lỗi đã ĐO ĐƯỢC (2026-11-01): `run` đưa WAV cho OCR, nên nhánh OCR KHÔNG BAO GIỜ thắng.
#
# Mọi bài phía trên gọi `chon_doan` TRỰC TIẾP, nên chúng không đi qua chỗ chọn đường dẫn
# trong `run` — và vì thế cả bảy bài đều xanh trong khi sản phẩm chạy sai đường. Đó là
# giới hạn của test đơn vị trên một hàm thuần: nó kiểm hàm, không kiểm người gọi hàm.
#
# Đo được trên `8f4b5304daf42569.mp4` (video DỌC có phụ đề Trung cứng):
#   OCR tren .wav -> 0 Hop sau 0.1 s      (ffmpeg không có khung nào để trích)
#   OCR tren .mp4 -> 71 Hop sau 169.1 s   (đọc được thật)
# Log job 67 vì thế nói đúng sự thật của thời điểm đó: "dùng ASR: không đọc được phụ đề
# cứng nào" — trên một video CÓ phụ đề cứng.
# ---------------------------------------------------------------------------


def test_run_dua_VIDEO_cho_ocr_chu_khong_phai_wav(tmp_path):
    """`run` phải đưa `source.media_path` (VIDEO) cho OCR, không phải `.wav` đã tách.

    Đây là bài duy nhất đi qua `run`, nên nó là bài duy nhất bắt được lỗi này. Nó ghim
    ĐÚNG hợp đồng của `OCREngine.doc_phu_de`: tham số tên `video_path`, và một tệp âm
    thanh thì không có khung hình nào — OCR trả `[]` một cách "hợp lệ", rồi pipeline
    lặng lẽ rơi về ASR. Không lỗi nào nổi lên, chỉ có chất lượng tụt mà không ai biết.

    Cách ghim: hai tệp KHÁC TÊN trong cùng `workdir`, và khẳng định đường dẫn OCR nhận
    là tệp `.mp4`. Nếu ai đó đổi lại thành `str(audio)`, bài này đỏ ngay.
    """
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00" * 64)          # nội dung không quan trọng: OCR là engine GIẢ
    wav = tmp_path / "video.wav"
    sf.write(str(wav), np.zeros(48_000, dtype=np.float32), 48_000)

    ocr = OcrGia([Segment(i=0, start=0.0, end=1.0, text="từ OCR")])
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="từ ASR")])
    h = _handler(tmp_path, ocr=ocr, asr=asr)

    r = h._repos
    source_id = r.add_source(kind="file", origin="video.mp4",
                             media_path=str(video), audio_path=str(wav),
                             duration=1.0, lang="zh")
    job = Job(id=None, workspace=1, type="asr", engine="asr-gia",
              phase="asr:asr-gia", payload={"source_id": source_id})
    h.run(job, lambda *_: None)

    assert ocr.duoc_goi == 1, "OCR phải được gọi"
    assert ocr.video_path_nhan is not None
    assert ocr.video_path_nhan.endswith("video.mp4"), (
        f"OCR nhận {ocr.video_path_nhan!r} — phải là VIDEO. "
        f"Nếu là '.wav' thì không có khung hình nào để đọc, OCR trả [] 'hợp lệ', "
        f"và cả chính sách 'OCR là chính' lặng lẽ thành 'ASR là chính'."
    )


# ---------------------------------------------------------------------------
# `payload.vung_doc` — vùng đọc do GIAO DIỆN gửi, thắng mặc định của registry.
#
# 🔴 BA TRẠNG THÁI PHẢI PHÂN BIỆT ĐƯỢC, và đây là toàn bộ lý do nhóm test này tồn tại:
#
#   không có khoá `vung_doc`  -> dùng `opts.vung_doc` của registry (mặc định)
#   `[]`                      -> TẮT lọc vùng, đọc cả khung (nút × trên giao diện)
#   `[x0, y0, x1, y1]`        -> payload THẮNG registry
#
# Cái bẫy: `payload.get("vung_doc") or self._vung_doc` sẽ biến `[]` (falsy) thành "dùng
# mặc định" — nút × trông như đã bấm mà watermark vẫn bị lọc theo vùng cũ. Nên `run`
# kiểm bằng `"vung_doc" in job.payload`, và các bài dưới ghim đúng ba nhánh đó.
#
# Vì sao vùng phải đi theo TỪNG JOB chứ không chỉ nằm trong registry: vùng watermark
# phụ thuộc VIDEO. Đo được `8f4b5304daf42569.mp4` (1080×1920) có watermark ở
# `y=35-102`, còn `ac5df767b9e0c878.mp4` (1280×720) ở chỗ khác — một con số chung đúng
# cho video này và SAI cho video kia, và cái sai đó im lặng.
# ---------------------------------------------------------------------------


def _chay_voi_vung(tmp_path, payload_them, *, mac_dinh=(0.0, 0.1, 1.0, 1.0),
                   vung_cua_nguon="__khong_dat__"):
    """Chạy `run` với `payload_them`, trả `vung_doc` mà OCR nhận.

    `mac_dinh` đặt vào `h._vung_doc` để mô phỏng `opts.vung_doc` của registry — nếu để
    `None` thì nhánh "không khai" và nhánh "`[]`" cho CÙNG kết quả, và bài test sẽ
    xanh trong khi nút × không có tác dụng gì.

    `vung_cua_nguon` mô phỏng cột `sources.vung_doc` (giao diện lưu khi người dùng kéo
    khung). Ba giá trị có nghĩa khác nhau, nên mặc định là một sentinel chứ không phải
    `None`:

      `"__khong_dat__"` — KHÔNG gọi `set_source_vung_doc` (nguồn chưa ai chọn)
      `None`            — ghi NULL (chưa chọn, dùng mặc định registry)
      `()`              — ghi `'[]'` (đã TẮT lọc vùng, nút ×)
      `(x0,y0,x1,y1)`   — ghi vùng đã chọn
    """
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00" * 64)
    wav = tmp_path / "video.wav"
    sf.write(str(wav), np.zeros(8_000, dtype=np.float32), 8_000)

    ocr = OcrGia([Segment(i=0, start=0.0, end=1.0, text="từ OCR")])
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="từ ASR")])
    h = _handler(tmp_path, ocr=ocr, asr=asr)
    h._vung_doc = mac_dinh

    sid = h._repos.add_source(kind="file", origin="video.mp4", media_path=str(video),
                              audio_path=str(wav), duration=1.0, lang="zh")
    if vung_cua_nguon != "__khong_dat__":
        h._repos.set_source_vung_doc(sid, vung_cua_nguon)
    h.run(Job(id=None, workspace=1, type="asr", engine="asr-gia",
              phase="asr:asr-gia", payload={"source_id": sid, **payload_them}),
          lambda *_: None)
    return ocr.vung_doc_nhan


def test_khong_khai_vung_doc_thi_dung_mac_dinh_registry(tmp_path):
    """Không có khoá ⇒ handler dùng `self._vung_doc` (từ `opts.vung_doc`)."""
    assert _chay_voi_vung(tmp_path, {}) == (0.0, 0.1, 1.0, 1.0)


def test_vung_doc_rong_la_TAT_chu_khong_phai_dung_mac_dinh(tmp_path):
    """`[]` (nút ×) ⇒ OCR đọc CẢ khung, dù registry có mặc định.

    Đây là bài chặn đúng cái bẫy `or`: `[]` là falsy, nên `payload.get(...) or mac_dinh`
    biến "người dùng đã tắt" thành "dùng lại vùng cũ". Triệu chứng sẽ là watermark vẫn
    bị lọc theo vùng cũ trong khi giao diện đã hiện trạng thái tắt — không lỗi nào nổi
    lên, chỉ có kết quả sai.
    """
    assert _chay_voi_vung(tmp_path, {"vung_doc": []}) is None


def test_vung_doc_trong_payload_thang_mac_dinh_registry(tmp_path):
    """Bốn số trong payload THẮNG `opts.vung_doc` — vùng thuộc về video, không registry."""
    ra = _chay_voi_vung(tmp_path, {"vung_doc": [0.2, 0.3, 0.8, 0.9]})
    assert ra == (0.2, 0.3, 0.8, 0.9), ra


def test_vung_doc_sai_hinh_dang_thi_job_hong_ON_AO(tmp_path):
    """`x0 >= x1` phải NÉM, không lặng lẽ lọc sạch.

    Vì sao không "tự sắp lại cho đúng": người viết gửi `[1, 0.1, 0, 1]` đã hiểu sai ý
    nghĩa bốn số, và tự sửa giúp họ sẽ che mất việc đó. Nặng hơn: một vùng bị đảo có
    thể lọc sạch mọi hộp, OCR trả `[]` "hợp lệ", và pipeline lặng lẽ rơi về ASR.
    """
    import pytest

    with pytest.raises(ValueError, match="x0 < x1"):
        _chay_voi_vung(tmp_path, {"vung_doc": [1, 0.1, 0, 1]})


# ---------------------------------------------------------------------------
# TẦNG NGUỒN — vùng đã lưu của `sources.vung_doc` (giao diện ghi khi kéo khung).
#
# Thứ tự ưu tiên: payload job > vùng của NGUỒN > `opts.vung_doc` của registry.
#
# Vì sao phải có tầng nguồn: người dùng kéo khung MỘT lần cho mỗi video, rồi lưu.
# Không đọc tầng đó thì lần bóc băng sau (bấm lại bước "Phiên âm") quay về mặc định
# registry — người dùng đã chọn vùng mà sản phẩm bỏ qua.
#
# Vì sao payload vẫn THẮNG nguồn: payload là "lượt chạy này dùng vùng nào", do chính
# lần bấm đó gửi. Nó là bản ghi của hành động, còn cột nguồn là bộ nhớ dài hạn.
# ---------------------------------------------------------------------------


def test_vung_cua_NGUON_thang_mac_dinh_registry(tmp_path):
    """Nguồn đã lưu vùng ⇒ dùng vùng đó, không dùng mặc định registry."""
    ra = _chay_voi_vung(tmp_path, {}, mac_dinh=(0.0, 0.5, 1.0, 1.0),
                        vung_cua_nguon=(0.1, 0.2, 0.9, 0.8))
    assert ra == (0.1, 0.2, 0.9, 0.8), ra


def test_vung_cua_NGUON_rong_la_TAT(tmp_path):
    """`()` trong cột (JSON `'[]'`) ⇒ TẮT lọc vùng, dù registry có mặc định.

    Đây là bài ghim hành vi nút × SAU KHI TẢI LẠI TRANG: người dùng bấm ×, vùng được
    lưu thành `[]`, và lần bóc băng sau phải đọc cả khung. Nếu `run` đọc `()` thành
    `None` rồi rơi tiếp về registry thì nút × chỉ có tác dụng cho tới lần tải lại —
    đúng kiểu hỏng im lặng.
    """
    assert _chay_voi_vung(tmp_path, {}, vung_cua_nguon=()) is None


def test_vung_cua_NGUON_null_thi_van_dung_mac_dinh_registry(tmp_path):
    """Nguồn chưa chọn (`None`) KHÔNG được hiểu là "đã tắt"."""
    ra = _chay_voi_vung(tmp_path, {}, mac_dinh=(0.0, 0.1, 1.0, 1.0),
                        vung_cua_nguon=None)
    assert ra == (0.0, 0.1, 1.0, 1.0), ra


def test_PAYLOAD_thang_vung_cua_nguon(tmp_path):
    """Payload thắng cả nguồn lẫn registry — nó là vùng của CHÍNH lượt chạy này."""
    ra = _chay_voi_vung(tmp_path, {"vung_doc": [0.25, 0.3, 0.75, 0.7]},
                        mac_dinh=(0.0, 0.1, 1.0, 1.0),
                        vung_cua_nguon=(0.1, 0.2, 0.9, 0.8))
    assert ra == (0.25, 0.3, 0.75, 0.7), ra


def test_PAYLOAD_rong_thang_ca_vung_cua_nguon(tmp_path):
    """`[]` trong payload TẮT được cả vùng đã lưu của nguồn.

    Không có bài này thì một lần bấm × trên giao diện vẫn bị vùng cũ của nguồn ghi đè,
    và người dùng thấy watermark vẫn bị lọc dù đã tắt.
    """
    assert _chay_voi_vung(tmp_path, {"vung_doc": []},
                          vung_cua_nguon=(0.1, 0.2, 0.9, 0.8)) is None
