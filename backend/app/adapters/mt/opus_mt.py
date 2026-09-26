"""OPUS-MT (Marian) chạy trong tiến trình, CPU.

Không có glossary và không có token count — đúng như spec §8.7.2. Vì vậy
`supports_glossary()` trả `False` để QA sinh cờ `engine_no_glossary`, thay vì để
người dùng tưởng glossary đã được áp dụng.

Segment đầu ra được dựng bằng `dataclasses.replace`: `Segment` có 13 trường và
việc dựng tay một `Segment(...)` mới làm rơi 7 trường không được kể tên
(emotion/events/avg_logprob/no_speech_prob/suspect/t/qa) — lỗi này đã xảy ra hai
lần trong giai đoạn 2. `replace` khiến "chỉ đổi `text`" là điều được bảo đảm bởi
ngôn ngữ, không phải bởi việc đọc kỹ danh sách tham số.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term
from app.domain.mt import MtOpts

DEFAULT_MODEL = "Helsinki-NLP/opus-mt-zh-vi"


class OpusMtEngine:
    def __init__(self, model_name: str = DEFAULT_MODEL, *, device: str = "cpu",
                 model_factory: Callable[[], object] | None = None) -> None:
        self._model_name = model_name
        self._device = device
        self._factory = model_factory or self._default_factory
        self._marian: object | None = None

    def _default_factory(self) -> object:
        # Import trong hàm: `transformers` nặng và không phải máy nào cũng cài, nên
        # import ở cấp module sẽ làm đỏ cả suite ở máy chưa cài.
        from transformers import MarianMTModel, MarianTokenizer
        tokenizer = MarianTokenizer.from_pretrained(self._model_name)
        model = MarianMTModel.from_pretrained(self._model_name).to(self._device).eval()
        return _MarianBundle(tokenizer, model, self._device)

    @property
    def engine_id(self) -> str:
        return "opus-mt"

    def supports_glossary(self) -> bool:
        return False

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        if not batch:
            return []
        marian = self._ensure_loaded()
        translated = marian.translate([s.text for s in batch])   # type: ignore[attr-defined]
        # `zip` một mình sẽ IM LẶNG cắt cụt khi decoder trả ít hơn đầu vào, mà
        # hợp đồng `MtEngine` cấm trả list ngắn hơn: mất một dòng phụ đề không
        # tín hiệu là đúng kiểu thất bại âm thầm mà `AlignmentProblem` tồn tại để
        # chặn. Bên gọi (Task 11) bắt riêng ngoại lệ này để thử lại cả lô hoặc
        # lùi về dịch từng segment.
        if len(translated) != len(batch):
            raise AlignmentProblem(
                expected_ids=[s.i for s in batch],
                got_ids=[s.i for s in batch[:len(translated)]],
                reason=(f"opus-mt trả {len(translated)} bản dịch cho "
                        f"{len(batch)} segment"),
            )
        return [replace(s, text=t) for s, t in zip(batch, translated)]

    def release(self) -> None:
        if self._marian is None:
            return
        self._marian = None

    def _ensure_loaded(self) -> object:
        if self._marian is None:
            self._marian = self._factory()
        return self._marian


class _MarianBundle:
    """Bọc tokenizer + model thành một lời gọi `translate(list[str]) -> list[str]`."""

    def __init__(self, tokenizer: object, model: object, device: str) -> None:
        self.tokenizer = tokenizer
        self.model = model
        self.device = device

    def translate(self, texts: list[str]) -> list[str]:
        encoded = self.tokenizer(texts, return_tensors="pt", padding=True,   # type: ignore[operator]
                                 truncation=True)
        encoded = {k: v.to(self.device) for k, v in encoded.items()}
        generated = self.model.generate(**encoded)                            # type: ignore[attr-defined]
        return [self.tokenizer.decode(ids, skip_special_tokens=True)          # type: ignore[attr-defined]
                for ids in generated]
