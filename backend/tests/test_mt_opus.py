"""OPUS-MT: Marian chạy trong tiến trình, KHÔNG có glossary, KHÔNG có token count.

Model được tiêm vào qua `model_factory` nên test này chạy được trên máy chưa tải
model. Phần chạy model thật nằm ở Task 16 (smoke), không phải ở đây.

Bất biến quan trọng nhất ở đây là `translate()` dựng segment đầu ra bằng
`dataclasses.replace` — Task 7 và Task 8 từng dựng tay `Segment(...)` và làm rơi
7 trong 13 trường (emotion/events/avg_logprob/no_speech_prob/suspect/t/qa). Test
`test_translate_keeps_every_field_it_does_not_own` ghim đúng lỗi đó.
"""
import dataclasses

import pytest

from app.adapters.mt.opus_mt import OpusMtEngine
from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term, Word
from app.domain.mt import MtOpts


class _FakeTensor:
    """`input_ids` giả: chỉ cần `.to(device)` trả về chính nó và đếm được batch.

    Tokenizer thật trả tensor; trả `list` trần thì nhánh `v.to(self.device)` của
    adapter không có gì để chạy và test lặng lẽ không kiểm được `device` nữa.
    """

    def __init__(self, rows: list[list[int]]):
        self.rows = rows
        self.to_calls: list[str] = []

    def to(self, device):
        self.to_calls.append(device)
        return self


class _FakeTokenizer:
    def __call__(self, texts, return_tensors=None, padding=None, truncation=None):
        self.seen = list(texts)
        self.last_input_ids = _FakeTensor([[1, 2, 3] for _ in texts])
        return {"input_ids": self.last_input_ids}


class _FakeModel:
    def __init__(self, outputs):
        self._outputs = outputs
        self.generate_calls = 0
        self.to_calls = []

    def to(self, device):
        self.to_calls.append(device)
        return self

    def eval(self):
        return self

    def generate(self, **kwargs):
        self.generate_calls += 1
        n = len(kwargs["input_ids"].rows)
        return [[10 + i] for i in range(n)]


class _FakeMarian:
    """Bắt chước `_MarianBundle` — ĐÚNG cái mà `model_factory` phải trả về.

    Brief Task 9 cho lớp này chỉ có `decode()`, tức là nó bắt chước
    `MarianMTModel` chứ không bắt chước bundle mà engine gọi. Giữ nguyên bản đó
    thì 10/13 test đỏ với `AttributeError: '_FakeMarian' object has no attribute
    'translate'` — seam tiêm vào (`model_factory`) là bundle, không phải model
    trần. Ở đây `translate()` chạy đúng chuỗi tokenize → to(device) → generate →
    decode y như `_MarianBundle` thật, nên test kiểm được cả `device`.
    """

    def __init__(self, translated: list[str], *, device: str = "cpu",
                 outputs: int | None = None):
        self.translated = list(translated)
        self.device = device
        #: Số chuỗi mà `generate()` trả về. Mặc định = số dòng đầu vào (hành vi
        #: bình thường). Đặt nhỏ hơn để mô phỏng decoder trả THIẾU — đúng ca mà
        #: `zip` âm thầm cắt cụt.
        self.outputs = outputs
        self.tokenizer = _FakeTokenizer()
        self.model = _FakeModel(self.translated)

    def decode(self, ids, skip_special_tokens=True):
        # Hết chuỗi thì trả "" chứ không ném: một decoder thật trả chuỗi RỖNG cho
        # dòng không dịch được, nó không sập. Ném ở đây sẽ khiến test kiểm cái
        # fake thay vì kiểm engine.
        return self.translated.pop(0) if self.translated else ""

    def translate(self, texts: list[str]) -> list[str]:
        encoded = self.tokenizer(texts, return_tensors="pt", padding=True,
                                 truncation=True)
        encoded = {k: v.to(self.device) for k, v in encoded.items()}
        generated = self.model.generate(**encoded)
        if self.outputs is not None:
            generated = generated[:self.outputs]
        return [self.decode(ids) for ids in generated]


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text, speaker="S1")


def test_supports_glossary_is_false():
    eng = OpusMtEngine(model_factory=lambda: _FakeMarian(["x"]))
    assert eng.supports_glossary() is False


def test_engine_id_is_stable():
    assert OpusMtEngine(model_factory=lambda: _FakeMarian([])).engine_id == "opus-mt"


def test_translate_preserves_identity_and_timing():
    marian = _FakeMarian(["vi1", "vi2"])
    eng = OpusMtEngine(model_factory=lambda: marian)
    out = eng.translate([seg(1, "a"), seg(2, "b")], [], MtOpts(source_lang="zh"))
    assert [s.text for s in out] == ["vi1", "vi2"]
    assert [s.i for s in out] == [1, 2]
    assert out[0].start == 1.0 and out[0].speaker == "S1"


def test_translate_returns_one_output_per_input_even_for_one_segment():
    marian = _FakeMarian(["vi"])
    eng = OpusMtEngine(model_factory=lambda: marian)
    assert len(eng.translate([seg(7, "a")], [], MtOpts(source_lang="zh"))) == 1


def test_translate_keeps_every_field_it_does_not_own():
    """Chỉ `text` được đổi. Mọi trường khác phải nguyên vẹn — kể cả `qa`.

    Dựng tay `Segment(i=..., start=..., end=..., text=t, words=..., speaker=...)`
    làm rơi emotion/events/avg_logprob/no_speech_prob/suspect/t/qa. Đây là lỗi
    ĐÃ XẢY RA HAI LẦN trong giai đoạn này, nên nó được ghim bằng test chứ không
    bằng lời hứa.
    """
    marian = _FakeMarian(["vi"])
    eng = OpusMtEngine(model_factory=lambda: marian)
    src = Segment(i=3, start=3.0, end=4.0, text="a", words=[Word("a", 3.0, 4.0)],
                  emotion="angry", events=["music"], speaker="S2", avg_logprob=-0.5,
                  no_speech_prob=0.1, suspect=True, t="orig", qa=["check"])
    out = eng.translate([src], [], MtOpts(source_lang="zh"))[0]
    assert out.text == "vi"
    assert dataclasses.replace(src, text="vi") == out, (
        "segment ra phải bằng segment vào với ĐÚNG trường text bị thay"
    )


def test_glossary_is_accepted_but_ignored_not_rejected():
    """Chữ ký phải nhận glossary; engine bỏ qua nó và QA là chỗ báo cờ."""
    marian = _FakeMarian(["vi"])
    eng = OpusMtEngine(model_factory=lambda: marian)
    terms = [Term(id=None, lang="zh", term="rồng", translation="dragon", approved=True)]
    out = eng.translate([seg(1, "rồng")], terms, MtOpts(source_lang="zh"))
    assert out[0].text == "vi"


def test_model_is_loaded_lazily_and_only_once():
    built = []

    def factory():
        built.append(1)
        return _FakeMarian(["vi", "vi"])

    eng = OpusMtEngine(model_factory=factory)
    assert built == [], "chưa gọi translate thì chưa được nạp model"
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    eng.translate([seg(2, "b")], [], MtOpts(source_lang="zh"))
    assert len(built) == 1, "nạp model hai lần là lãng phí và rò VRAM"


def test_release_is_idempotent_and_forces_reload():
    """`release()` phải THẬT SỰ nhả bundle, không chỉ không ném.

    Bản trong brief dùng MỘT `_FakeMarian` và ghim `marian.model.generate_calls
    == 2`. Test đó KHÔNG kiểm được gì về `release()`: `generate_calls` đếm số lần
    `translate()` gọi generate, mà `translate()` chạy hai lần thì luôn là 2 —
    kể cả khi `release()` là `return` trần. Nó xanh trên một `release()` rỗng.

    Ở đây factory trả bundle MỚI mỗi lần nạp, nên số lần FACTORY chạy chính là
    phép kiểm thật: 1 lần = dùng cache, 2 lần = đã nạp lại. Đồng thời ghim rằng
    lần `release()` thứ hai (no-op) không ném và bundle cũ bị bỏ hẳn.
    """
    built: list[_FakeMarian] = []

    def factory() -> _FakeMarian:
        marian = _FakeMarian(["vi", "vi"])
        built.append(marian)
        return marian

    eng = OpusMtEngine(model_factory=factory)
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    assert len(built) == 1

    eng.release()
    eng.release()          # no-op, không ném

    eng.translate([seg(2, "b")], [], MtOpts(source_lang="zh"))
    assert len(built) == 2, "sau release(), translate() phải nạp lại bundle mới"
    assert built[0].model.generate_calls == 1, "bundle CŨ không được dùng lại"
    assert built[1].model.generate_calls == 1, "bundle MỚI phải là cái chạy"


def test_empty_batch_returns_empty_without_loading_model():
    built = []
    eng = OpusMtEngine(model_factory=lambda: (built.append(1), _FakeMarian([]))[1])
    assert eng.translate([], [], MtOpts(source_lang="zh")) == []
    assert built == []


def test_injected_bundle_moves_tensors_to_its_own_device():
    """Bundle được tiêm quyết định `device` của nó — engine không ghi đè.

    `device="cpu"` của `__init__` chỉ có tác dụng trên đường `_default_factory`
    (ở đó nó thành `MarianMTModel.to(device)`). Với `model_factory` được tiêm,
    bundle là thứ đã được dựng sẵn, nên phép kiểm có nghĩa là: tensor đi qua
    `.to(...)` của CHÍNH bundle, không bị bỏ qua.
    """
    marian = _FakeMarian(["vi"], device="cpu")
    eng = OpusMtEngine(model_factory=lambda: marian)
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    assert marian.tokenizer.last_input_ids.to_calls == ["cpu"]
    assert marian.model.generate_calls == 1


def test_batch_texts_reach_the_tokenizer_in_order():
    """Một lô là MỘT lời gọi generate — thứ tự văn bản phải khớp thứ tự segment."""
    marian = _FakeMarian(["vi1", "vi2", "vi3"])
    eng = OpusMtEngine(model_factory=lambda: marian)
    out = eng.translate([seg(1, "a"), seg(2, "b"), seg(3, "c")], [],
                        MtOpts(source_lang="zh"))
    assert marian.tokenizer.seen == ["a", "b", "c"]
    assert marian.model.generate_calls == 1
    assert [s.text for s in out] == ["vi1", "vi2", "vi3"]


def test_default_factory_is_not_called_for_an_injected_model():
    """`model_factory` được tiêm thì không được chạm tới `_default_factory`.

    Nếu chạm, test sẽ cố tải 300 MB từ HuggingFace — đúng thứ `model_factory`
    tồn tại để tránh.
    """
    calls = []
    eng = OpusMtEngine(model_factory=lambda: _FakeMarian(["vi"]))
    eng._default_factory = lambda: calls.append(1)          # type: ignore[method-assign]
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    assert calls == []


@pytest.mark.parametrize("texts", [["a"], ["a", "b"]])
def test_output_length_matches_input_length(texts):
    marian = _FakeMarian([f"vi{i}" for i in range(len(texts))])
    eng = OpusMtEngine(model_factory=lambda: marian)
    batch = [seg(i, t) for i, t in enumerate(texts)]
    assert len(eng.translate(batch, [], MtOpts(source_lang="zh"))) == len(batch)


def test_short_decoder_output_is_an_alignment_problem_not_a_silent_loss():
    """Cổng `MtEngine` cấm trả list NGẮN HƠN: "KHÔNG bảo đảm được thì ném
    `AlignmentProblem`".

    Bản trong brief dùng `zip(batch, translated)`: nếu decoder trả ít hơn đầu vào
    — chuyện có thật khi một dòng bị dịch thành chuỗi rỗng và bị gộp — thì `zip`
    IM LẶNG cắt cụt và trả list ngắn hơn. Mất một dòng phụ đề mà không có tín
    hiệu nào. Test này ghim rằng trường hợp đó NÉM, không nuốt.
    """
    marian = _FakeMarian(["vi1", "vi2"], outputs=2)  # 3 segment, chỉ 2 bản dịch
    eng = OpusMtEngine(model_factory=lambda: marian)
    batch = [seg(1, "a"), seg(2, "b"), seg(3, "c")]
    with pytest.raises(AlignmentProblem):
        eng.translate(batch, [], MtOpts(source_lang="zh"))
