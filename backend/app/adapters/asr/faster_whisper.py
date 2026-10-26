"""Adapter faster-whisper (CTranslate2). KHÔNG cần torch.

`model_factory` được bơm vào để test kiểm tra hợp đồng mà không nạp model.
"""
from __future__ import annotations

import os
import time
from typing import Callable

from app.adapters.asr.cuda_runtime import ensure_cuda_runtime
from app.domain.models import Segment, Word
from app.domain.segmentation import normalize
from app.registry import EngineSpec

#: Nhịp báo tiến độ khi bóc băng. Mỗi lần `report()` là MỘT lượt ghi DB + MỘT sự kiện SSE, và
#: clip 20:49 có 446 đoạn: báo từng đoạn là 446 lượt ghi cho một thanh tiến trình. Hai giây đủ
#: để thanh nhích đều, và đủ thưa để không thành phần lớn của thời gian chạy.
_PROGRESS_EVERY_S = 2.0


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


def device_and_compute_type(spec: EngineSpec,
                            device: str | None = None) -> tuple[str, str]:
    """`(device, compute_type)` cho CTranslate2 — một cặp, không phải hai biến rời.

    `float16`/`int8_float16` chỉ có nghĩa trên GPU; CTranslate2 NÉM trên CPU. Nên
    "chạy CPU" bắt buộc phải hạ `compute_type` theo, nếu không thì đổi thiết bị là
    đổi từ một lỗi sang một lỗi khác.

    Thiết bị lấy theo thứ tự: tham số truyền vào → biến môi trường
    `PHUDE_ASR_DEVICE` → `"cuda"` (giữ nguyên hành vi cũ trên máy có GPU).

    `ponytail:` MỘT biến cho cả tiến trình, không phải `spec.opts["device"]` —
    nâng cấp khi cần hai engine ASR khác thiết bị trong cùng một tiến trình.
    """
    chosen = device or os.environ.get("PHUDE_ASR_DEVICE") or "cuda"
    compute = str(spec.opts.get("compute_type", "int8_float16"))
    if not chosen.startswith("cuda") and "float16" in compute:
        compute = "int8"
    return chosen, compute


class FasterWhisperEngine:
    def __init__(
        self,
        spec: EngineSpec,
        *,
        device: str | None = None,
        download_root: str | None = None,
        model_factory: Callable[..., object] | None = None,
    ) -> None:
        self.engine_id = spec.id
        self.spec = spec
        self.device, self.compute_type = device_and_compute_type(spec, device)
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
                compute_type=self.compute_type,
                download_root=self.download_root,
            )
        return self._model

    def model_cached(self) -> bool | None:
        """Model đã có trên ĐĨA chưa — để job NÓI RA ngay lúc phải tải lần đầu.

        Sự cố đo được: lượt `asr` đầu tiên với `fw-large-v3` đứng ở `15%` suốt **6 phút**
        trong khi `/models/models--Systran--faster-whisper-large-v3` (2,9 GB) đang được ghi —
        và job chỉ nói "nạp engine", nên không ai phân biệt được "đang tải 2,9 GB" với "treo".

        Ba giá trị, và giá trị thứ ba quan trọng ngang hai giá trị kia:
        * `True`  — có trên đĩa;
        * `False` — CHẮC CHẮN không có (`LocalEntryNotFoundError`): đây là lúc phải báo;
        * `None`  — KHÔNG BIẾT (thiếu thư viện, thiếu bảng bí danh, lỗi lạ). Trả `None` chứ
          không trả `False`: một câu "chưa có model" SAI còn tệ hơn không nói gì — đo được
          ngay ở lượt đầu của bản vá này, khi `spec.model_ref` là bí danh `large-v3-turbo` mà
          repo thật là `mobiuslabsgmbh/...` nên mọi job đều bị báo "chưa có model".

        `snapshot_download(local_files_only=True)` KHÔNG chạm mạng. Bí danh → repo thật phải
        đi qua `faster_whisper.utils._MODELS` của CHÍNH thư viện: đó là cùng một bảng mà
        `WhisperModel` dùng, nên hai bên không thể lệch.
        """
        try:
            from huggingface_hub import snapshot_download
            from huggingface_hub.errors import LocalEntryNotFoundError
        except Exception:  # noqa: BLE001 - không có thư viện thì không kết luận gì
            return None
        try:
            from faster_whisper.utils import _MODELS  # noqa: PLC0415 - bảng bí danh của chính nó
            repo = _MODELS.get(self.spec.model_ref, self.spec.model_ref)
        except Exception:  # noqa: BLE001 - API riêng, đổi giữa các bản ⇒ không đoán
            return None
        try:
            snapshot_download(repo, local_files_only=True, cache_dir=self.download_root)
            return True
        except LocalEntryNotFoundError:
            return False
        except Exception:  # noqa: BLE001 - lỗi tra cache khác ⇒ không kết luận
            return None

    def transcribe(self, audio_path: str, lang: str, *,
                   on_progress: Callable[[float, float], None] | None = None
                   ) -> list[Segment]:
        """Bóc băng; `on_progress(giây_đã_tới, tổng_giây)` là TUỲ CHỌN.

        Vì sao có callback: `faster-whisper` trả một ITERATOR đoạn, nên vị trí đọc được là
        `segment.end`. Thiếu nó, job đứng ở `0.15` cho tới khi xong — với clip 20:49 trên
        `fw-large-v3` đó là hàng phút của một thanh tiến trình không nhích.

        Gọi tối đa mỗi `_PROGRESS_EVERY_S` giây: mỗi lần `report()` là một lượt ghi DB + một
        sự kiện SSE, và clip này có 446 đoạn — báo từng đoạn là 446 lượt ghi cho một việc.
        """
        model = self._load()
        batch_size = int(self.spec.opts.get("batch_size", 0) or 0)
        lan_cuoi = 0.0
        tong_giay = 0.0

        def bao(vi_tri: float) -> None:
            nonlocal lan_cuoi
            if on_progress is None or tong_giay <= 0:
                return
            now = time.monotonic()
            if now - lan_cuoi < _PROGRESS_EVERY_S:
                return
            lan_cuoi = now
            on_progress(min(vi_tri, tong_giay), tong_giay)

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
            iterator, info = self._batched.transcribe(
                audio_path, language=lang, batch_size=batch_size,
                vad_filter=True, word_timestamps=True,
                without_timestamps=False,
                condition_on_previous_text=False,
                initial_prompt=self.spec.opts.get("initial_prompt"),
            )
        else:
            iterator, info = model.transcribe(
                audio_path, language=lang,
                vad_filter=True, word_timestamps=True,
                condition_on_previous_text=False,
                initial_prompt=self.spec.opts.get("initial_prompt"),
            )

        # Tổng thời lượng để quy tiến độ ra phần trăm: `info.duration` là thời lượng AUDIO đã
        # giải mã, không phải cửa sổ của lô đầu (hai thứ khác nhau, và dùng nhầm thì thanh
        # tiến trình vượt 100% ở lô cuối).
        tong_giay = float(getattr(info, "duration", 0.0) or 0.0)

        raw = []
        for s in iterator:
            raw.append({
                "start": s.start, "end": s.end, "text": s.text,
                "avg_logprob": getattr(s, "avg_logprob", None),
                "no_speech_prob": getattr(s, "no_speech_prob", None),
                "words": [{"word": w.word, "start": w.start, "end": w.end}
                          for w in (getattr(s, "words", None) or [])],
            })
            bao(float(s.end))
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
