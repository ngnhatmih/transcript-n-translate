from types import SimpleNamespace

import pytest

from app.domain.models import Segment
from experiments.accuracy_pipelines.qwen3_asr import segments_from_timestamps, transcribe_with_model


def stamp(text, start, end):
    return SimpleNamespace(text=text, start_time=start, end_time=end)


def test_qwen_timestamps_group_into_timed_chinese_phrases():
    result = segments_from_timestamps([
        stamp("但", 0.1, 0.2), stamp("我", 0.2, 0.3), stamp("去", 0.3, 0.4),
        stamp("汕", 0.4, 0.5), stamp("头", 0.5, 0.7), stamp("。", 0.7, 0.8),
        stamp("好", 1.0, 1.2), stamp("。", 1.2, 1.3),
    ])

    assert result == [
        Segment(i=0, start=0.1, end=0.8, text="但我去汕头。"),
        Segment(i=1, start=1.0, end=1.3, text="好。"),
    ]


def test_qwen_timestamps_reject_non_monotonic_or_invalid_spans():
    with pytest.raises(ValueError, match="ordered"):
        segments_from_timestamps([stamp("后", 1, 2), stamp("前", 0, 0.5)])

    with pytest.raises(ValueError, match="timestamp"):
        segments_from_timestamps([stamp("坏", 1, float("nan"))])


def test_qwen_aligner_zero_duration_character_is_kept_in_phrase():
    result = segments_from_timestamps([
        stamp("我", 0.1, 0.2), stamp("已", 0.2, 0.2), stamp("到", 0.2, 0.3),
    ])

    assert result == [Segment(i=0, start=0.1, end=0.3, text="我已到")]


def test_qwen_transcriber_passes_context_and_returns_timed_segments(tmp_path):
    calls = []

    class FakeModel:
        def transcribe(self, **kwargs):
            calls.append(kwargs)
            return [SimpleNamespace(text="汕头")]

    class FakeAligner:
        def align(self, **kwargs):
            calls.append(kwargs)
            return [SimpleNamespace(items=[stamp("汕", 0, 0.2), stamp("头", 0.2, 0.4)])]

    output = transcribe_with_model(
        tmp_path / "audio.wav", "zh", "汕头; 烟台山",
        model_factory=lambda: FakeModel(), aligner_factory=lambda: FakeAligner(),
    )

    assert calls == [{
        "audio": str(tmp_path / "audio.wav"), "language": "Chinese",
        "context": ["汕头; 烟台山"], "return_time_stamps": False,
    }, {
        "audio": str(tmp_path / "audio.wav"), "text": "汕头", "language": "Chinese",
    }]
    assert output == [Segment(i=0, start=0.0, end=0.4, text="汕头")]


def test_qwen_transcriber_rejects_missing_aligner_output(tmp_path):
    class FakeModel:
        def transcribe(self, **kwargs):
            return [SimpleNamespace(text="你好")]

    class FakeAligner:
        def align(self, **kwargs):
            return [[]]

    with pytest.raises(RuntimeError, match="aligned transcript"):
        transcribe_with_model(tmp_path / "audio.wav", "zh", "",
                              model_factory=lambda: FakeModel(),
                              aligner_factory=lambda: FakeAligner())
