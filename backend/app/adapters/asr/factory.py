"""Chọn adapter ASR theo `EngineSpec`. Nơi DUY NHẤT biết ánh xạ id -> adapter.

Trước đây ánh xạ này tồn tại ở hai chỗ: `app.main:_engine_factory` (đủ) và
`scripts/smoke_asr.py` (thiếu — luôn dựng `FasterWhisperEngine`). Hệ quả là
`smoke_asr.py clip.mp4 zh sensevoice-small` đưa `model_ref` của SenseVoice cho
faster-whisper và báo THẤT BẠI vì dựng sai adapter: công cụ nghiệm thu model
thật duy nhất của dự án nói dối về đúng thứ nó tồn tại để đo (I-2).

Gom về một hàm để hai chỗ gọi không thể trôi khỏi nhau lần nữa. Import adapter
nằm TRONG hàm: `torch`/`funasr`/`faster_whisper` đều nặng và có thể chưa cài.
"""
from __future__ import annotations

from app.registry import EngineSpec

#: Tiền tố id của các engine chạy bằng faster-whisper (xem `registry.json`).
FW_PREFIX = "fw-"

#: Id của engine SenseVoice — adapter KHÁC, và nó không nhận `download_root`.
SENSEVOICE_ID = "sensevoice-small"


def engine_for(spec: EngineSpec, *, download_root: str):
    """Dựng adapter ĐÚNG với `spec.id`. Id lạ bị TỪ CHỐI, không đoán.

    `download_root` là cache model đã phân giải (xem `_prepare_local_model_caches`
    / `prepare_model_cache_env`): thiếu nó thì model ~1,6 GB rơi vào cache mặc
    định ở ổ C:. `SenseVoiceEngine` không có tham số đó — nó để FunASR tự quyết
    định qua `MODELSCOPE_CACHE`, biến đã được đặt trước khi chạm adapter.
    """
    from app.adapters.asr.faster_whisper import FasterWhisperEngine
    from app.adapters.asr.sensevoice import SenseVoiceEngine

    if spec.id.startswith(FW_PREFIX):
        return FasterWhisperEngine(spec, download_root=download_root)
    if spec.id == SENSEVOICE_ID:
        return SenseVoiceEngine(spec)
    raise KeyError(f"không có adapter cho engine {spec.id!r}")
