"""Adapter faster-whisper (CTranslate2). KHÔNG cần torch.

`model_factory` được bơm vào để test kiểm tra hợp đồng mà không nạp model.
"""
from __future__ import annotations

from typing import Callable

from app.adapters.asr.cuda_runtime import ensure_cuda_runtime
from app.domain.models import Segment, Word
from app.domain.segmentation import normalize
from app.registry import EngineSpec


def to_segments(raw_segments: list[dict]) -> list[Segment]:
    """Hàm THUẦN: dict thô của faster-whisper -> list[Segment].

    Tách riêng để test được mà không cần GPU. Đây là chỗ dễ sai nhất của
    adapter: word timestamp rỗng phải thành None, không phải [].
    """
    out: list[Segment] = []
    for idx, raw in enumerate(raw_segments):
        words_raw = raw.get("words") or []
        words = [Word(w=w["word"], s=float(w["start"]), e=float(w["end"]))
                 for w in words_raw
                 if w.get("start") is not None and w.get("end") is not None]
        seg = Segment(
            i=idx,
            start=float(raw["start"]),
            end=float(raw["end"]),
            text=(raw.get("text") or "").strip(),
            words=words or None,
            avg_logprob=raw.get("avg_logprob"),
            no_speech_prob=raw.get("no_speech_prob"),
        )
        seg.mark_suspect()
        out.append(seg)
    return out


class FasterWhisperEngine:
    def __init__(
        self,
        spec: EngineSpec,
        *,
        device: str = "cuda",
        download_root: str | None = None,
        model_factory: Callable[..., object] | None = None,
    ) -> None:
        self.engine_id = spec.id
        self.spec = spec
        self.device = device
        self.download_root = download_root
        self._model_factory = model_factory
        self._model = None
        self._batched = None

    def _load(self):
        if self._model is None:
            factory = self._model_factory
            if factory is None:
                # R72: PHẢI chạy trước `from faster_whisper import ...`. Thiếu
                # bước này thì CTranslate2 tạo được model nhưng nổ ở lần
                # `encode()` đầu tiên: "Library cublas64_12.dll is not found or
                # cannot be loaded" — cublas chỉ nằm trong `torch/lib` và chỉ
                # vào được đường tìm DLL khi torch đã được nạp.
                ensure_cuda_runtime()
                from faster_whisper import WhisperModel
                factory = WhisperModel
            self._model = factory(
                self.spec.model_ref,
                device=self.device,
                compute_type=self.spec.opts.get("compute_type", "int8_float16"),
                download_root=self.download_root,
            )
        return self._model

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        model = self._load()
        batch_size = int(self.spec.opts.get("batch_size", 0) or 0)
        if batch_size > 1:
            from faster_whisper import BatchedInferencePipeline
            if self._batched is None:
                self._batched = BatchedInferencePipeline(model=model)
            # `without_timestamps` PHẢI được khai tường minh là False. Nguyên nhân
            # gốc của lỗi "mất đoạn đầu": `BatchedInferencePipeline.transcribe`
            # mặc định `without_timestamps=True` (chế độ nhanh, prompt có
            # <|notimestamps|>), còn `WhisperModel.transcribe` mặc định False.
            # Ở chế độ nhanh, `fw-large-v3-turbo` — engine ASR MẶC ĐỊNH — trả về
            # một stub cụt cho chunk đầu: đo trên clip thật 234,17 s
            # (`_realpipe`, CC BY-SA 4.0), chunk 0 có cửa sổ 0,000 -> 29,904 s
            # nhưng model chỉ sinh 4 token ("文章名", 3 chữ) rồi dừng, trong khi
            # 8 chunk còn lại sinh 114-170 token. Hệ quả: transcript mất sạch
            # ~130 chữ có tiếng nói thật trong 28,5 s đầu và mốc đầu tiên bị đẩy
            # thành 28,58 s. Bật lại timestamp (False) thì CÙNG chunk đó sinh
            # 153 token và chữ ở đầu trở lại đủ. Xem
            # tests/test_asr_first_chunk_live.py.
            iterator, _info = self._batched.transcribe(
                audio_path, language=lang, batch_size=batch_size,
                vad_filter=True, word_timestamps=True,
                without_timestamps=False,
                condition_on_previous_text=False,
                initial_prompt=self.spec.opts.get("initial_prompt"),
            )
        else:
            iterator, _info = model.transcribe(
                audio_path, language=lang,
                vad_filter=True, word_timestamps=True,
                condition_on_previous_text=False,
                initial_prompt=self.spec.opts.get("initial_prompt"),
            )

        raw = [{
            "start": s.start, "end": s.end, "text": s.text,
            "avg_logprob": getattr(s, "avg_logprob", None),
            "no_speech_prob": getattr(s, "no_speech_prob", None),
            "words": [{"word": w.word, "start": w.start, "end": w.end}
                      for w in (getattr(s, "words", None) or [])],
        } for s in iterator]
        return normalize(to_segments(raw))

    def release(self) -> None:
        # Xoá tham chiếu model TRƯỚC khối try: dù phần dọn torch có nổ thế nào
        # thì model vẫn phải được nhả.
        self._batched = None
        self._model = None
        # Best-effort, và bắt RỘNG TAY là cố ý — xin đừng "siết" lại thành
        # `except ImportError`. Đây là callback đổ model: mục đích là giải phóng
        # VRAM nếu có thể, còn không giải phóng được thì cũng KHÔNG được làm sập
        # hàng đợi. Bản torch cài hỏng ném `OSError` (WinError 126) ngay lúc
        # import, và `torch.cuda.is_available()` có thể ném `RuntimeError` —
        # cả hai đều KHÔNG phải `ImportError`. Task 15 đăng ký hàm này làm
        # unload callback của `SingleGpuGovernor`, nơi `releaser()` được gọi mà
        # không có try/except ở CẢ `before_phase` lẫn `after_phase`: một
        # exception lọt ra sẽ bỏ dở cả vòng đổ model và làm hỏng chuyển giai đoạn.
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 - dọn dẹp best-effort, xem chú thích trên
            pass
