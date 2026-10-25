"""Adapter SenseVoice qua FunASR.

Khác faster-whisper ở ba điểm:
  * không có word timestamp; FunASR alignment cấp ký tự được dùng nội bộ
  * không có avg_logprob -> dấu hiệu nghi ngờ lấy từ tag sự kiện (bgm, laughter)
  * cần torch + FunASR (faster-whisper thì không)

`funasr` được import LƯỜI trong `_load()`: nó nặng và chưa chắc đã cài, nên chỉ
việc import module này không được kéo nó vào. `model_factory` được bơm vào để
test kiểm tra hợp đồng mà không nạp model.
"""
from __future__ import annotations

import math
import os
import pathlib
import unicodedata
from typing import Callable

from app.adapters.asr.cuda_runtime import ensure_cuda_runtime
from app.domain.models import Segment, Word
from app.domain.segmentation import normalize
from app.registry import EngineSpec

from .sensevoice_tags import parse_rich_tags

SUSPICIOUS_EVENTS = frozenset({"bgm", "laughter", "cry", "applause"})


def _resolve_model_ref(model_ref: str) -> str:
    """Ưu tiên snapshot SenseVoice Small hoàn chỉnh trong cache local."""
    local_ref = pathlib.Path(model_ref)
    if local_ref.is_dir():
        return str(local_ref)
    if model_ref != "iic/SenseVoiceSmall":
        return model_ref

    cache = os.environ.get("MODELSCOPE_CACHE")
    if not cache:
        from app.config import HF_HOME
        cache = str(pathlib.Path(HF_HOME) / "modelscope")
    root = pathlib.Path(cache)
    snapshots = list((root / "models/iic--SenseVoiceSmall/snapshots").glob("*"))
    candidates = snapshots + [
        root / "hub/iic/SenseVoiceSmall",
        root / "iic/SenseVoiceSmall",
    ]
    complete = [
        path for path in candidates
        if (path / "config.yaml").is_file()
        and (path / "model.pt").is_file()
        and (path / "model.pt").stat().st_size > 0
    ]
    if complete:
        return str(max(complete, key=lambda path: path.stat().st_mtime))
    return model_ref


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
                # R72: cùng lý do như `FasterWhisperEngine._load()` — `funasr`
                # kéo `torchaudio`/CTranslate2 phụ thuộc `cublas64_12.dll`, thứ
                # chỉ vào được đường tìm DLL khi torch đã được nạp.
                ensure_cuda_runtime()
                from funasr import AutoModel
                factory = AutoModel
            self._model = factory(
                model=_resolve_model_ref(self.spec.model_ref),
                vad_model="fsmn-vad",
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
            output_timestamp=True,
        )
        segments: list[Segment] = []
        for item in _flatten(raw):
            timestamped = _character_timestamp_segments(
                item, len(segments), self.engine_id,
            )
            if timestamped is not None:
                segments.extend(timestamped)
                continue
            parsed = parse_rich_tags(item.get("text", ""))
            if not parsed.text:
                continue
            start, end = _timing_seconds(item, self.engine_id)
            seg = Segment(
                i=len(segments), start=start, end=max(end, start + 0.01), text=parsed.text,
                emotion=parsed.emotion, events=list(parsed.events),
            )
            if SUSPICIOUS_EVENTS.intersection(parsed.events):
                seg.suspect = True
            segments.append(seg)
        if not segments:
            raise RuntimeError("SenseVoice không trả về đoạn nào")
        normalized = normalize(segments)
        # Character alignments above are internal split points, not word data.
        for segment in normalized:
            segment.words = None
        return normalized

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


def _character_timestamp_segments(item: dict, first_index: int,
                                  engine_id: str) -> list[Segment] | None:
    """Split FunASR's full-text character alignment on sentence punctuation.

    Some SenseVoice/FunASR versions return one full transcript plus one
    timestamp pair per non-symbol character. If the cardinalities do not
    match, keep the existing chunk-level timing fallback rather than guessing.
    """
    raw_text = item.get("text", "")
    parsed = parse_rich_tags(raw_text)
    timestamps = item.get("timestamp")
    if not parsed.text or not isinstance(timestamps, (list, tuple)):
        return None

    # A two-number timestamp is an utterance span, not two character spans.
    if len(timestamps) == 2 and all(_finite_number(value) is not None
                                    for value in timestamps):
        return None

    aligned_chars = [
        char for char in parsed.text
        if not char.isspace()
        and not unicodedata.category(char).startswith(("S", "C"))
    ]
    if len(aligned_chars) != len(timestamps):
        return None

    words: list[Word] = []
    text_chars: list[str] = []
    sentence_segments: list[Segment] = []
    punctuation = frozenset("。！？!?；;")
    timestamp_index = 0
    previous_start = -1.0

    def append_sentence() -> None:
        if not words or not "".join(text_chars).strip():
            return
        segment = Segment(
            i=first_index + len(sentence_segments),
            start=words[0].s,
            end=max(words[-1].e, words[0].s + 0.01),
            text="".join(text_chars).strip(),
            words=list(words),
            emotion=parsed.emotion,
            events=list(parsed.events),
        )
        if SUSPICIOUS_EVENTS.intersection(parsed.events):
            segment.suspect = True
        sentence_segments.append(segment)

    for char in parsed.text:
        if char.isspace():
            if text_chars:
                text_chars.append(char)
            continue
        if unicodedata.category(char).startswith(("S", "C")):
            continue

        pair = timestamps[timestamp_index]
        timestamp_index += 1
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise RuntimeError(
                f"{engine_id}: timestamp ký tự không hợp lệ tại vị trí {timestamp_index - 1}; "
                "cần cặp timestamp ký tự hoặc start/end hợp lệ"
            )
        start_ms, end_ms = _finite_number(pair[0]), _finite_number(pair[1])
        if (start_ms is None or end_ms is None or end_ms < start_ms
                or start_ms < previous_start):
            raise RuntimeError(
                f"{engine_id}: timestamp ký tự không hữu hạn hoặc không tăng dần "
                f"tại vị trí {timestamp_index - 1}"
            )
        start, end = start_ms / 1000.0, end_ms / 1000.0
        previous_start = start_ms
        words.append(Word(w=char, s=start, e=end))
        text_chars.append(char)
        if char in punctuation:
            append_sentence()
            words = []
            text_chars = []

    append_sentence()
    return sentence_segments or None


def _flatten(raw) -> list[dict]:
    """FunASR trả về list[dict] hoặc list[list[dict]] tuỳ cấu hình VAD.

    EX-05/EX-06 (F3/F4 của review Task 13) — HỢP ĐỒNG, ghim bằng test:

    * `list` và `tuple` được đối xử NHƯ NHAU ở MỌI cấp. `_span_ms` đã nhận
      `(list, tuple)` ở mọi chỗ, nên một `tuple` lồng trong `raw` là cùng một
      hình dạng dữ liệu; bản cũ chỉ bóc `list` nên phần tử `tuple` bị BỎ.
    * Đệ quy tới HẾT lồng, không dừng ở cấp hai. Bản cũ trả `[]` cho
      `[[[d]]]` — mất sạch đoạn mà không nói gì, trái tinh thần fail-loudly
      (R62). Ở đây `[[[d]]]` -> `[d]`.
    * Phần tử không phải `dict`/`list`/`tuple` bị BỎ QUA (không ném) — "không
      có đoạn nào dùng được" vẫn là lỗi ồn ào ở tầng trên: `transcribe()` thấy
      danh sách rỗng thì ném `RuntimeError`.
    """
    if not raw:
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, (list, tuple)):
            out.extend(_flatten(item))
        elif isinstance(item, dict):
            out.append(item)
    return out
