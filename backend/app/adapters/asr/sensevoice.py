"""Adapter SenseVoice qua FunASR.

Khác faster-whisper ở ba điểm:
  * không có word timestamp -> chỉ timestamp cấp đoạn
  * không có avg_logprob -> dấu hiệu nghi ngờ lấy từ tag sự kiện (bgm, laughter)
  * cần torch + FunASR (faster-whisper thì không)

`funasr` được import LƯỜI trong `_load()`: nó nặng và chưa chắc đã cài, nên chỉ
việc import module này không được kéo nó vào. `model_factory` được bơm vào để
test kiểm tra hợp đồng mà không nạp model.
"""
from __future__ import annotations

import math
from typing import Callable

from app.domain.models import Segment
from app.domain.segmentation import normalize
from app.registry import EngineSpec

from .sensevoice_tags import parse_rich_tags

SUSPICIOUS_EVENTS = frozenset({"bgm", "laughter", "cry", "applause"})


class SenseVoiceEngine:
    def __init__(
        self,
        spec: EngineSpec,
        *,
        device: str = "cuda",
        model_factory: Callable[..., object] | None = None,
    ) -> None:
        self.engine_id = spec.id
        self.spec = spec
        self.device = device
        self._model_factory = model_factory
        self._model = None

    def _load(self):
        if self._model is None:
            factory = self._model_factory
            if factory is None:
                from funasr import AutoModel
                factory = AutoModel
            self._model = factory(
                model=self.spec.model_ref,
                vad_model="fsmn-vad",
                punc_model="ct-punc",
                device=self.device,
                disable_update=True,
            )
        return self._model

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        model = self._load()
        raw = model.generate(
            input=audio_path,
            language=lang,
            use_itn=bool(self.spec.opts.get("use_itn", True)),
            batch_size_s=60,
            merge_vad=True,
        )
        segments: list[Segment] = []
        for idx, item in enumerate(_flatten(raw)):
            parsed = parse_rich_tags(item.get("text", ""))
            if not parsed.text:
                continue
            start, end = _timing_seconds(item, self.engine_id)
            seg = Segment(
                i=idx, start=start, end=max(end, start + 0.01), text=parsed.text,
                emotion=parsed.emotion, events=list(parsed.events),
            )
            if SUSPICIOUS_EVENTS.intersection(parsed.events):
                seg.suspect = True
            segments.append(seg)
        if not segments:
            raise RuntimeError("SenseVoice không trả về đoạn nào")
        return normalize(segments)

    def release(self) -> None:
        # Xoá tham chiếu model TRƯỚC khối try: dù phần dọn torch có nổ thế nào
        # thì model vẫn phải được nhả.
        self._model = None
        # Best-effort, và bắt RỘNG TAY là cố ý — xin đừng "siết" lại thành
        # `except ImportError`. Task 15 trả về `FasterWhisperEngine` HOẶC
        # `SenseVoiceEngine` từ `_engine_factory` và đăng ký hàm này làm unload
        # callback của `SingleGpuGovernor`, nơi `releaser()` được gọi mà KHÔNG
        # có try/except ở cả `before_phase` lẫn `after_phase`: một exception lọt
        # ra sẽ bỏ dở cả vòng đổ model và làm hỏng chuyển giai đoạn. Bản torch
        # cài hỏng ném `OSError` (WinError 126) ngay lúc import, và
        # `torch.cuda.is_available()` có thể ném `RuntimeError` — cả hai đều
        # KHÔNG phải `ImportError`.
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 - dọn dẹp best-effort, xem chú thích trên
            pass


def _finite_number(value) -> float | None:
    """Số hữu hạn, hoặc `None`. `bool` bị loại: `True` là 1, không phải mốc."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _span_ms(timestamp) -> tuple[float | None, float | None]:
    """`timestamp` của FunASR -> (bắt đầu, kết thúc) mili giây, else (None, None).

    Hai hình dạng đã gặp: cặp phẳng `[b, k]`, và danh sách cặp
    `[[b, k], [b, k], ...]` khi VAD (`fsmn-vad`) bật.
    """
    if not isinstance(timestamp, (list, tuple)) or not timestamp:
        return None, None
    if len(timestamp) == 2:
        first, second = _finite_number(timestamp[0]), _finite_number(timestamp[1])
        if first is not None and second is not None:
            return first, second
    head, tail = timestamp[0], timestamp[-1]
    if (isinstance(head, (list, tuple)) and isinstance(tail, (list, tuple))
            and head and tail):
        start, end = _finite_number(head[0]), _finite_number(tail[-1])
        if start is not None and end is not None:
            return start, end
    return None, None


def _timing_seconds(item: dict, engine_id: str) -> tuple[float, float]:
    """Mốc thời gian của một item FunASR -> giây.

    Thứ tự ưu tiên: (1) `start`/`end` tường minh dạng số, (2) `timestamp` cặp
    phẳng, (3) `timestamp` danh sách cặp. Hết cả ba thì NỔ.

    TUYỆT ĐỐI không được lặng lẽ trả 0/0 khi thiếu mốc: khi đó mọi phụ đề nằm ở
    t=0 với thời lượng 10ms, job vẫn báo THÀNH CÔNG, và không có gì đỏ cả.
    Đầu ra rác mà báo xanh tệ hơn hẳn một lỗi ồn ào.
    """
    start_ms = _finite_number(item.get("start"))
    end_ms = _finite_number(item.get("end"))
    if start_ms is not None and end_ms is not None:
        return start_ms / 1000.0, end_ms / 1000.0

    ts_start, ts_end = _span_ms(item.get("timestamp"))
    if start_ms is None:
        start_ms = ts_start
    if end_ms is None:
        end_ms = ts_end
    if start_ms is None or end_ms is None:
        raise RuntimeError(
            f"{engine_id}: không đọc được mốc thời gian của kết quả FunASR "
            f"(khoá hiện có: {sorted(str(k) for k in item)}). Cần 'start'+'end' "
            f"dạng số mili giây, hoặc 'timestamp' dạng [bắt đầu, kết thúc] hay "
            f"[[bắt đầu, kết thúc], ...]. Không gán mốc 0 cho mọi đoạn."
        )
    return start_ms / 1000.0, end_ms / 1000.0


def _flatten(raw) -> list[dict]:
    """FunASR trả về list[dict] hoặc list[list[dict]] tuỳ cấu hình VAD."""
    if not raw:
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, list):
            out.extend(i for i in item if isinstance(i, dict))
        elif isinstance(item, dict):
            out.append(item)
    return out
