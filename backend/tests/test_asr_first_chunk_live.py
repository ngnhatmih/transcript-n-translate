"""Bài ghim LỖI THẬT: engine ASR MẶC ĐỊNH không được bỏ mất đoạn đầu bản ghi.

Lỗi đã đo và đã sửa (nhánh `fix-asr-mat-dau`): `fw-large-v3-turbo` — engine ASR
mặc định (`default_asr` trong `backend/registry.json`, nên chạy trên MỌI lần
nạp) — đi qua `BatchedInferencePipeline`, và pipeline đó mặc định
`without_timestamps=True` (chế độ nhanh) trong khi `WhisperModel.transcribe`
mặc định `False`. Ở chế độ nhanh, model trả về một stub CỤT cho chunk ĐẦU:

    clip thật 234,17 s (Wikimedia Commons, CC BY-SA 4.0; `_realpipe`)
    VAD (Silero, cùng tham số pipeline dùng) nói tiếng nói bắt đầu 0,000 s và
    phủ 28,50/28,50 s đầu; chunk 0 của đường batch là 0,000 -> 29,904 s
    fw-large-v3-turbo : out[0] = 4 token   (chi 3 chu "文章名")  -> MAT CHU
    fw-small          : out[0] = 147 token
    fw-medium         : 133 chu trong 28,5 s dau (do qua adapter)

Trước khi sửa, qua đúng adapter của repo: 34 đoạn, mốc đầu 28,58 s, **0 chữ**
trong 28,5 s đầu, tổng 950 chữ. Sau khi sửa: 47 đoạn, mốc đầu 0,00 s, 140 chữ
trong 28,5 s đầu, tổng 1095 chữ.

BA ĐIỀU BẮT BUỘC của bài này:

1. Dùng CLIP THẬT, KHÔNG dùng WAV tổng hợp/im lặng của `_seed`. Lý do ĐO ĐƯỢC:
   cắt 30 s đầu ra tệp riêng rồi cho chính turbo chạy qua đường batch thì KHÔNG
   mất gì (đoạn đầu vẫn đủ 130 chữ) — lỗi chỉ hiện khi đường batch có nhiều
   chunk. Một fixture ngắn vì thế KHÔNG tái hiện được lỗi, nên bài phải chạy
   trên TOÀN BỘ clip.
2. Bài cần model thật (~1,5 GB) và clip thật, nên mang dấu `live`: mặc định
   `pytest backend/` bỏ qua (`addopts = -m "not live"`), chạy bằng
   `python -B -m pytest -m live`. Thiếu clip/model thì SKIP, không đỏ vì lý do
   không liên quan tới code.
3. Máy này đang giữ VRAM cho Ollama, nên mặc định bài chạy CPU/int8 — hành vi
   sai nằm ở model + tham số, không ở thiết bị. Đổi bằng `DSH_ASR_DEVICE` /
   `DSH_ASR_COMPUTE`, đổi clip/model bằng `DSH_ASR_REAL_CLIP` /
   `DSH_ASR_MODELS_DIR`.
"""
from __future__ import annotations

import os
import pathlib

import pytest

pytestmark = pytest.mark.live

#: Clip THẬT ~234 s (tên ASCII trong `_realpipe`, giấy phép CC BY-SA 4.0).
CLIP = pathlib.Path(
    os.environ.get("DSH_ASR_REAL_CLIP")
    or r"C:\Users\Admin\Desktop\ngn\deepseek\_realpipe\data\media\64f3d8f48ed4004a.wav"
)
MODELS_DIR = pathlib.Path(os.environ.get("DSH_ASR_MODELS_DIR") or r"D:\models\hf")
#: Thư mục cache của chính model mặc định; thiếu nó thì SKIP chứ không tải mạng.
MODEL_CACHE_DIR = "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"

#: Mốc 28,5 s là ranh giới của lỗi: trước khi sửa, mọi chữ nằm SAU mốc này.
CUT = 28.5
#: Đo được 0 chữ trước khi sửa và 140 chữ sau khi sửa -> ngưỡng 100 rất rộng.
MIN_EARLY_CHARS = 100


@pytest.fixture(scope="module")
def segments():
    """Chạy ĐÚNG đường của app (adapter thật + `normalize`) trên clip thật.

    Một lần cho cả module: mỗi lượt bóc băng tốn ~45 s trên CPU.
    """
    if not CLIP.is_file():
        pytest.skip("khong co clip that: %s" % CLIP)
    if not (MODELS_DIR / MODEL_CACHE_DIR).is_dir():
        pytest.skip("khong co model trong cache: %s" % (MODELS_DIR / MODEL_CACHE_DIR))

    from app.adapters.asr.faster_whisper import FasterWhisperEngine
    from app.registry import EngineSpec

    spec = EngineSpec(
        id="fw-large-v3-turbo", label="Faster-Whisper large-v3-turbo", kind="asr",
        runtime="inprocess", model_ref="large-v3-turbo", vram_mb=1600,
        langs=("zh", "en"),
        capabilities={"timestamps": True, "word_timestamps": True, "batch_infer": True},
        opts={"batch_size": 8,
              "compute_type": os.environ.get("DSH_ASR_COMPUTE", "int8")},
    )
    engine = FasterWhisperEngine(spec, device=os.environ.get("DSH_ASR_DEVICE", "cpu"),
                                 download_root=str(MODELS_DIR))
    try:
        out = engine.transcribe(str(CLIP), "zh")
    finally:
        engine.release()
    assert out, "boc bang tra ve rong"
    return out


def _early(segments) -> list:
    return [s for s in segments if s.start < CUT]


def test_default_asr_transcript_begins_at_the_top_of_the_clip(segments):
    """Bất biến: chữ đầu tiên phải nằm ở ĐẦU clip, không phải ở giây 28,58.

    Đây là bài ĐỎ khi bỏ bản sửa: chế độ nhanh của đường batch làm chunk đầu
    thoái hoá thành stub, `normalize` đẩy mốc đầu thành 28,58 s và 28,5 s đầu
    còn ĐÚNG 0 chữ.
    """
    early = _early(segments)
    chars = sum(len(s.text) for s in early)
    assert segments[0].start < 1.0, (
        "moc dau tien phai o dau clip, dang la %.2f s (lo hong dau ban ghi)" % segments[0].start)
    assert len(early) > 0 and chars >= MIN_EARLY_CHARS, (
        "28,5 s dau phai co tieng noi that: chi %d chu trong %d doan (can >= %d)"
        % (chars, len(early), MIN_EARLY_CHARS))


def test_default_asr_keeps_the_spoken_preamble_of_the_clip(segments):
    """Chữ của 28,5 s đầu phải là LỜI ĐỌC THẬT, không phải stub.

    Người đọc mở đầu bằng phần giới thiệu bài viết: tên bài, "维基百科", địa chỉ
    "zh.wikipedia.org", ngày bản được đọc. Turbo ở chế độ nhanh chỉ giữ 3 chữ
    "文章名", nên cả hai từ khoá dưới đây biến mất.
    """
    early = "".join(s.text for s in _early(segments))
    assert "\u7ef4\u57fa\u767e\u79d1" in early, (          # 维基百科
        "thieu 'Wikipedia' (tieng Trung) trong 28,5 s dau: %r" % early[:60])
    assert "wikipedia" in early.lower(), (
        "thieu 'wikipedia.org' trong 28,5 s dau: %r" % early[:60])
