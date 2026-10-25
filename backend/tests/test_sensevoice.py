"""Test cho adapter SenseVoice (R61/R62/R63).

Mọi đường đi qua model trong unit test đều dùng `model_factory` được bơm vào.
Không bài nào tải mạng hay nạp model thật; việc đó thuộc smoke test.

Ba nhóm lý do tồn tại của file này:
  * R61 — brief chỉ test parser thuần, nên `sensevoice.py` không được bài test
    nào import: một lỗi cú pháp hay import hỏng trong đó sẽ vô hình tới Task 15.
  * R62 — mốc thời gian: bản trong brief vừa NỔ (`float([0, 1000])` khi
    `timestamp` là danh sách cặp) vừa NÓI DỐI (thiếu `timestamp` -> mọi đoạn
    thành t=0 dài 10ms, job vẫn báo thành công).
  * R63 — `release()` bắt `ImportError` trong khi bản torch cài hỏng ném
    `OSError`, và `cuda.is_available()` có thể ném `RuntimeError`.
"""
from __future__ import annotations

import ast
import builtins
import dataclasses
import pathlib
import sys
import types

import pytest

import app.adapters.asr.sensevoice as sv_module
from app.adapters.asr.sensevoice import SenseVoiceEngine, _flatten
from app.registry import EngineSpec

SOURCE = pathlib.Path(sv_module.__file__)

DEFAULT_RAW = [
    {"text": "<|zh|><|NEUTRAL|><|Speech|>你好", "start": 0, "end": 2000},
]


@pytest.fixture()
def sv_spec():
    return EngineSpec(
        id="sensevoice-small", label="SenseVoice-Small", kind="asr",
        runtime="inprocess", model_ref="iic/SenseVoiceSmall", vram_mb=1000,
        langs=("zh", "yue", "en"), capabilities={}, opts={"use_itn": True},
    )


def _with_opts(spec, **opts):
    return dataclasses.replace(spec, opts=dict(opts))


class _FakeSenseVoiceModel:
    def __init__(self, **load_kwargs) -> None:
        self.load_kwargs = load_kwargs
        self.generate_calls: list[dict] = []
        self.raw: list = []

    def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return self.raw


class _RecordingFactory:
    """`model_factory` giả: ghi lại KWARG của lần nạp rồi trả model giả.

    Chỉ nhận `**kwargs` là CỐ Ý: adapter phải gọi factory theo từ khoá
    (`factory(model=..., device=...)`). Gọi bằng đối số vị trí sẽ nổ `TypeError`
    ngay tại đây, tức là hợp đồng gọi được ghim chứ không chỉ giá trị.
    """

    def __init__(self, raw=None) -> None:
        self.calls: list[dict] = []
        self.models: list[_FakeSenseVoiceModel] = []
        self.raw = list(DEFAULT_RAW if raw is None else raw)

    def __call__(self, **kwargs):
        model = _FakeSenseVoiceModel(**kwargs)
        model.raw = list(self.raw)
        self.calls.append(kwargs)
        self.models.append(model)
        return model


def _loaded_engine(sv_spec, raw=None):
    """Engine đã nạp model giả và đã transcribe một lần (`_model` khác None)."""
    engine = SenseVoiceEngine(sv_spec, model_factory=_RecordingFactory(raw))
    engine.transcribe("a.wav", "zh")
    return engine


# --------------------------------------------------------------------------
# R61: `_flatten` — hai hình dạng tài liệu của FunASR.
# --------------------------------------------------------------------------

def test_flatten_accepts_list_of_dicts_and_drops_non_dicts():
    a, b = {"text": "a"}, {"text": "b"}
    assert _flatten([a, b]) == [a, b]
    assert _flatten([a, "rác", None, 3, b]) == [a, b], (
        "phần tử không phải dict phải bị bỏ, không được lọt vào vòng lặp"
    )


def test_flatten_accepts_list_of_lists_from_vad_and_drops_non_dicts():
    a, b, c = {"text": "a"}, {"text": "b"}, {"text": "c"}
    assert _flatten([[a], [b, c], "rác", None, []]) == [a, b, c], (
        "VAD bật thì FunASR trả list[list[dict]]: phải làm phẳng được"
    )
    assert _flatten([[a, "rác", None], [b, c]]) == [a, b, c], (
        "phần tử không phải dict NẰM TRONG một list con cũng phải bị bỏ: "
        "chỉ lọc ở cấp ngoài cùng là chưa đủ"
    )
    assert _flatten([]) == []
    assert _flatten(None) == [], "kết quả rỗng không được làm nổ adapter"


def test_flatten_treats_tuples_exactly_like_lists():
    """EX-05 (F3/Task 13): `_span_ms` nhận `(list, tuple)` ở MỌI chỗ, còn
    `_flatten` chỉ bóc `list` — nên một `tuple` nằm TRONG `raw` bị bỏ im lặng.

    Cùng một hình dạng dữ liệu mà hai hàm trong cùng tệp xử lý khác nhau là
    nguồn mất đoạn không báo: `raw` là tuple thì bản cũ vẫn chạy (vì nó lặp qua
    `raw`), nhưng phần tử tuple lồng bên trong thì biến mất.
    """
    a, b = {"text": "a"}, {"text": "b"}
    assert _flatten((a, b)) == [a, b]
    assert _flatten([(a, b)]) == [a, b], (
        "tuple NẰM TRONG raw bị bản cũ bỏ: đây là ca lỗi của EX-05"
    )
    assert _flatten(((a,), (b,))) == [a, b]
    assert _flatten([((a,), [b, ("rác",)])]) == [a, b], (
        "tuple lồng nhiều cấp vẫn phải được đệ quy, phần tử lạ thì bỏ"
    )


def test_flatten_recurses_all_the_way_down_instead_of_dropping_silently():
    """EX-06 (F4/Task 13): lồng sâu hơn hai cấp KHÔNG được trả `[]` im lặng.

    Bản cũ chỉ bóc đúng một cấp nên `[[[d]]]` -> `[]`: mất sạch đoạn mà không
    nói gì, trái tinh thần fail-loudly của R62. Hợp đồng (đã ghi trong docstring
    của `_flatten`): đệ quy tới HẾT lồng và trả về MỌI `dict`.
    """
    a, b = {"text": "a"}, {"text": "b"}
    assert _flatten([[[a]]]) == [a]
    assert _flatten([[[[a]]], [[[b]]]]) == [a, b]
    assert _flatten([[[["rác"]]]]) == [], (
        "không có dict nào thì trả rỗng — `transcribe()` mới là chỗ ném "
        "RuntimeError, không phải chỗ này nuốt lặng lẽ"
    )


# --------------------------------------------------------------------------
# R61: hợp đồng nạp model và gọi generate qua `model_factory`.
# --------------------------------------------------------------------------

def test_factory_receives_exact_load_arguments_and_loads_once(sv_spec, monkeypatch, tmp_path):
    monkeypatch.setenv("MODELSCOPE_CACHE", str(tmp_path))
    factory = _RecordingFactory()
    engine = SenseVoiceEngine(sv_spec, model_factory=factory)
    assert factory.calls == [], "chưa transcribe thì chưa được nạp model"

    engine.transcribe("a.wav", "zh")
    engine.transcribe("a.wav", "zh")

    assert factory.calls == [{
        "model": "iic/SenseVoiceSmall",
        "device": "cuda",
        "vad_model": "fsmn-vad",
        "disable_update": True,
    }], "nạp đúng một lần, dùng model local, VAD và device đã cấu hình"


def test_local_modelscope_snapshot_is_used_instead_of_downloading_alias(
    sv_spec, monkeypatch, tmp_path,
):
    snapshot = tmp_path / "models" / "iic--SenseVoiceSmall" / "snapshots" / "master"
    snapshot.mkdir(parents=True)
    (snapshot / "config.yaml").touch()
    (snapshot / "model.pt").write_bytes(b"weights")
    monkeypatch.setenv("MODELSCOPE_CACHE", str(tmp_path))
    factory = _RecordingFactory()

    SenseVoiceEngine(sv_spec, model_factory=factory).transcribe("a.wav", "zh")

    assert factory.calls[0]["model"] == str(snapshot)


def test_missing_local_snapshot_keeps_modelscope_alias_fallback(
    sv_spec, monkeypatch, tmp_path,
):
    monkeypatch.setenv("MODELSCOPE_CACHE", str(tmp_path))
    factory = _RecordingFactory()

    SenseVoiceEngine(sv_spec, model_factory=factory).transcribe("a.wav", "zh")

    assert factory.calls[0]["model"] == "iic/SenseVoiceSmall"


def test_device_argument_is_forwarded(sv_spec):
    factory = _RecordingFactory()
    SenseVoiceEngine(sv_spec, device="cpu", model_factory=factory).transcribe("a.wav", "zh")
    assert factory.calls[0]["device"] == "cpu"


def test_generate_receives_audio_path_language_and_itn_from_opts(sv_spec):
    factory = _RecordingFactory()
    engine = SenseVoiceEngine(_with_opts(sv_spec, use_itn=False), model_factory=factory)
    engine.transcribe("b.wav", "yue")

    assert factory.models[0].generate_calls == [{
        "input": "b.wav", "language": "yue", "use_itn": False,
        "batch_size_s": 60, "merge_vad": True, "output_timestamp": True,
    }], "audio_path/lang phải được chuyển tiếp, use_itn lấy từ spec.opts"


# --------------------------------------------------------------------------
# R61: tag -> Segment (chữ đã bóc tag, cảm xúc, sự kiện, cờ nghi ngờ).
# --------------------------------------------------------------------------

def test_tag_bearing_text_maps_to_segment_with_emotion_and_events(sv_spec):
    factory = _RecordingFactory([{
        "text": "<|zh|><|HAPPY|><|BGM|><|Applause|><|Speech|><|withitn|>大家好，欢迎来到本期节目",
        "start": 0, "end": 3000,
    }])
    out = SenseVoiceEngine(sv_spec, model_factory=factory).transcribe("a.wav", "zh")

    assert [s.text for s in out] == ["大家好，欢迎来到本期节目"], (
        "tag phải bị bóc khỏi phụ đề, không chỉ được phân tích"
    )
    assert out[0].emotion == "happy"
    assert out[0].events == ["bgm", "applause"]
    assert (out[0].start, out[0].end) == (0.0, 3.0)


@pytest.mark.parametrize("event,tag", [
    ("bgm", "<|BGM|>"),
    ("laughter", "<|Laughter|>"),
    ("cry", "<|Cry|>"),
    ("applause", "<|Applause|>"),
])
def test_suspicious_events_mark_segment_suspect(sv_spec, event, tag):
    factory = _RecordingFactory([{
        "text": f"<|zh|><|NEUTRAL|>{tag}<|Speech|>这句话要复查",
        "start": 0, "end": 2000,
    }])
    out = SenseVoiceEngine(sv_spec, model_factory=factory).transcribe("a.wav", "zh")

    assert out[0].events == [event]
    assert out[0].suspect is True, f"{event} nằm trong SUSPICIOUS_EVENTS"


def test_benign_event_does_not_mark_segment_suspect(sv_spec):
    factory = _RecordingFactory([{
        "text": "<|zh|><|NEUTRAL|><|Cough|><|Speech|>这句话没问题",
        "start": 0, "end": 2000,
    }])
    out = SenseVoiceEngine(sv_spec, model_factory=factory).transcribe("a.wav", "zh")

    assert out[0].events == ["cough"]
    assert out[0].suspect is False, "chỉ sự kiện trong SUSPICIOUS_EVENTS mới bị đánh dấu"


@pytest.mark.parametrize("raw", [
    [],
    [["không phải dict"]],
    [{"text": "<|zh|><|Speech|>", "start": 0, "end": 2000}],
    [{"text": "", "start": 0, "end": 2000}],
])
def test_raw_without_usable_segments_raises(sv_spec, raw):
    engine = SenseVoiceEngine(sv_spec, model_factory=_RecordingFactory(raw))
    # EX-07 (F5/Task 13): `match=` là thứ duy nhất phân biệt "nổ đúng chỗ" với
    # "nổ vì bất kỳ RuntimeError nào từ bất kỳ đâu trong khối".
    with pytest.raises(RuntimeError, match="không trả về đoạn nào"):
        engine.transcribe("a.wav", "zh")


# --------------------------------------------------------------------------
# R62: mốc thời gian. Bốn hình dạng, cả bốn đều phải được ghim.
# --------------------------------------------------------------------------

def test_explicit_start_end_are_milliseconds(sv_spec):
    factory = _RecordingFactory([
        {"text": "<|zh|><|Speech|>第一段", "start": 1500, "end": 4500},
    ])
    out = SenseVoiceEngine(sv_spec, model_factory=factory).transcribe("a.wav", "zh")
    assert (out[0].start, out[0].end) == (1.5, 4.5)


def test_explicit_start_end_win_over_timestamp(sv_spec):
    factory = _RecordingFactory([
        {"text": "<|zh|><|Speech|>第一段", "start": 2000, "end": 6000,
         "timestamp": [999000, 999999]},
    ])
    out = SenseVoiceEngine(sv_spec, model_factory=factory).transcribe("a.wav", "zh")
    assert (out[0].start, out[0].end) == (2.0, 6.0), (
        "start/end tường minh phải thắng timestamp"
    )


def test_flat_pair_timestamp_is_used(sv_spec):
    factory = _RecordingFactory([
        {"text": "<|zh|><|Speech|>第一段", "timestamp": [1000, 4000]},
    ])
    out = SenseVoiceEngine(sv_spec, model_factory=factory).transcribe("a.wav", "zh")
    assert (out[0].start, out[0].end) == (1.0, 4.0)


def test_list_of_pairs_timestamp_uses_first_start_and_last_end(sv_spec):
    factory = _RecordingFactory([
        {"text": "<|zh|><|Speech|>第一段",
         "timestamp": [[0, 1000], [1000, 2500], [2500, 5000]]},
    ])
    out = SenseVoiceEngine(sv_spec, model_factory=factory).transcribe("a.wav", "zh")
    assert (out[0].start, out[0].end) == (0.0, 5.0), (
        "danh sách cặp (fsmn-vad) lấy ts[0][0] / ts[-1][-1]; "
        "bản brief nổ TypeError ở đây vì float([0, 1000])"
    )


def test_character_timestamps_split_sensevoice_sentences_without_linear_drift(sv_spec):
    raw = [{
        "text": "<|zh|><|NEUTRAL|><|Speech|>第一句。第二句！",
        "timestamp": [
            [0, 300], [300, 600], [600, 900], [900, 1200],
            [5000, 5300], [5300, 5600], [5600, 5900], [5900, 6200],
        ],
    }]

    out = SenseVoiceEngine(sv_spec, model_factory=_RecordingFactory(raw)).transcribe(
        "a.wav", "zh"
    )

    assert [(s.text, s.start, s.end) for s in out] == [
        ("第一句。", 0.0, 1.2), ("第二句！", 5.0, 6.2),
    ], "phải dùng timestamp từng ký tự, không chia đều trên cả transcript"
    assert all(segment.words is None for segment in out), (
        "timestamp ký tự chỉ là điểm chia nội bộ, không giả là word timestamp"
    )


def test_character_timestamp_mapping_ignores_unaligned_symbol_markers(sv_spec):
    raw = [{
        "text": "<|zh|><|Speech|>第一句。😀第二句！",
        "timestamp": [
            [0, 300], [300, 600], [600, 900], [900, 1200],
            [5000, 5300], [5300, 5600], [5600, 5900], [5900, 6200],
        ],
    }]

    out = SenseVoiceEngine(sv_spec, model_factory=_RecordingFactory(raw)).transcribe(
        "a.wav", "zh"
    )

    assert [segment.text for segment in out] == ["第一句。", "第二句！"]


def test_partial_explicit_timing_is_not_silently_completed(sv_spec):
    """Chỉ có `start`, không có `end`/`timestamp`: phải ồn, không được bịa `end`."""
    engine = SenseVoiceEngine(
        sv_spec, model_factory=_RecordingFactory([{"text": "<|zh|><|Speech|>你好", "start": 0}])
    )
    # EX-07 (F5/Task 13): phải là lỗi MỐC THỜI GIAN, không phải RuntimeError nào khác.
    with pytest.raises(RuntimeError, match="mốc thời gian"):
        engine.transcribe("a.wav", "zh")


@pytest.mark.parametrize("item", [
    {"text": "<|zh|><|Speech|>你好"},                                    # thiếu hẳn
    {"text": "<|zh|><|Speech|>你好", "timestamp": None},
    {"text": "<|zh|><|Speech|>你好", "timestamp": []},
    {"text": "<|zh|><|Speech|>你好", "timestamp": [0]},                  # một số, không phải cặp
    {"text": "<|zh|><|Speech|>你好", "timestamp": [0, 1000, 2000]},
    {"text": "<|zh|><|Speech|>你好", "timestamp": [[0, 1000], "rác"]},
    {"text": "<|zh|><|Speech|>你好", "timestamp": "0,1000"},
    {"text": "<|zh|><|Speech|>你好", "start": "0", "end": "3000"},
    {"text": "<|zh|><|Speech|>你好", "start": True, "end": False},
    {"text": "<|zh|><|Speech|>你好", "start": float("nan"), "end": 3000},
])
def test_unusable_timing_raises_instead_of_emitting_zero_timings(sv_spec, item):
    """Không đọc được mốc thì phải NỔ, không được trả t=0 dài 10ms cho mọi đoạn.

    Đầu ra rác mà job báo thành công thì tệ hơn hẳn một lỗi ồn ào.
    """
    engine = SenseVoiceEngine(sv_spec, model_factory=_RecordingFactory([item]))
    with pytest.raises(RuntimeError) as excinfo:
        engine.transcribe("a.wav", "zh")

    message = str(excinfo.value)
    assert "sensevoice-small" in message, "thông báo phải nêu id engine"
    assert "timestamp" in message and "start" in message, (
        "thông báo phải nêu hình dạng mốc thời gian được chấp nhận"
    )


def test_timing_error_names_engine_id_and_present_keys(sv_spec):
    """Thông báo phải kể ra KHOÁ ĐANG CÓ, nếu không thì không gỡ được lỗi."""
    engine = SenseVoiceEngine(
        sv_spec,
        model_factory=_RecordingFactory([{"text": "<|zh|><|Speech|>你好", "seed": 7}]),
    )
    with pytest.raises(RuntimeError) as excinfo:
        engine.transcribe("a.wav", "zh")

    message = str(excinfo.value)
    assert "sensevoice-small" in message
    assert "seed" in message and "text" in message, "phải kể ra các khoá đã có"


# --------------------------------------------------------------------------
# R63: `release()` là unload callback của governor (Task 15) và governor gọi
# `releaser()` KHÔNG có try/except. Một exception lọt ra sẽ bỏ dở cả vòng đổ
# model. Bản brief bắt `ImportError`, trong khi hai đường đi THẬT dưới đây
# không phải `ImportError`.
# --------------------------------------------------------------------------

def _block_torch_import(monkeypatch, exc) -> None:
    """Làm `import torch` nổ `exc` một cách TẤT ĐỊNH, không phụ thuộc máy."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise exc
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_release_is_no_arg_idempotent_and_safe_before_load(sv_spec, monkeypatch):
    _block_torch_import(monkeypatch, ImportError("torch bị chặn trong test"))
    factory = _RecordingFactory()
    engine = SenseVoiceEngine(sv_spec, model_factory=factory)

    engine.release()          # chưa nạp gì
    engine.release()          # gọi lại: phải idempotent
    assert factory.calls == [], "release() không được nạp model"
    assert engine._model is None

    engine.transcribe("a.wav", "zh")
    engine.release()
    assert engine._model is None

    engine.transcribe("a.wav", "zh")
    assert len(factory.calls) == 2, "release() phải thật sự nhả để lần sau nạp lại"


def test_release_survives_oserror_from_broken_torch_install(sv_spec, monkeypatch):
    assert not issubclass(OSError, ImportError), (
        "đây là toàn bộ lý do phải bắt rộng: nếu OSError là ImportError thì bản cũ đã đủ"
    )
    engine = _loaded_engine(sv_spec)
    assert engine._model is not None, "bài test chỉ có nghĩa khi model ĐANG được nạp"

    _block_torch_import(monkeypatch, OSError("[WinError 126] Không tìm thấy module"))

    engine.release()          # không được ném

    assert engine._model is None, (
        "tham chiếu model phải được xoá TRƯỚC khối try, kể cả khi dọn torch nổ"
    )


def test_release_survives_runtimeerror_from_cuda_is_available(sv_spec, monkeypatch):
    engine = _loaded_engine(sv_spec)
    assert engine._model is not None

    def boom():
        raise RuntimeError("CUDA driver không khả dụng")

    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(is_available=boom, empty_cache=lambda: None)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    engine.release()          # không được ném

    assert engine._model is None, (
        "tham chiếu model phải được xoá TRƯỚC khối try, kể cả khi is_available nổ"
    )


def test_release_empties_cuda_cache_only_when_torch_reports_a_gpu(sv_spec, monkeypatch):
    calls: list[str] = []
    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(
        is_available=lambda: True, empty_cache=lambda: calls.append("empty"))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    _loaded_engine(sv_spec).release()
    assert calls == ["empty"]

    fake_torch.cuda = types.SimpleNamespace(
        is_available=lambda: False, empty_cache=lambda: calls.append("empty"))
    _loaded_engine(sv_spec).release()

    assert calls == ["empty"], "không có GPU thì không được gọi empty_cache"


# --------------------------------------------------------------------------
# R61: FunASR là phụ thuộc nặng, nên import ở cấp module sẽ kéo nó vào cả
# những lần khởi động không dùng SenseVoice. Giữ import lười và ghim bằng AST.
# --------------------------------------------------------------------------

def _funasr_refs(nodes) -> list[str]:
    out: list[str] = []
    for node in nodes:
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names if a.name.split(".")[0] == "funasr"]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "funasr":
                out.append(node.module or "")
    return out


def test_funasr_is_imported_lazily_not_at_module_level():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))

    module_level = _funasr_refs(
        n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)))
    assert module_level == [], (
        f"FunASR phải được import lười, không phải ở cấp module ({module_level})"
    )

    assert _funasr_refs(ast.walk(tree)), (
        "vẫn phải còn nhánh import lười `from funasr import AutoModel` trong _load()"
    )
