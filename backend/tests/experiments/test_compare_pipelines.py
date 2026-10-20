import json

import pytest
from types import SimpleNamespace
from app.domain.models import Segment
from experiments.accuracy_pipelines.contracts import PipelineResult

from scripts.compare_pipelines import parse_reference, parse_pipeline_ids, run_comparison
from experiments.accuracy_pipelines import PIPELINES


def test_pipeline_ids_reject_unknown_names():
    with pytest.raises(ValueError, match="unknown pipeline"):
        parse_pipeline_ids("baseline,not-real")


def test_full_whisper_large_v3_is_an_explicit_comparison_pipeline():
    assert "whisper_large_v3_hymt" in PIPELINES
    assert "whisper_large_v3_hymt" in parse_pipeline_ids(
        "whisper_large_v3_hymt", PIPELINES
    )


def test_reference_accepts_string_or_segment_lists(tmp_path):
    path = tmp_path / "ref.json"
    path.write_text(json.dumps({"source": ["你", "好"], "translation": "Xin chào"}),
                    encoding="utf-8")

    assert parse_reference(path) == {"source": "你好", "translation": "Xin chào"}


def test_reference_rejects_missing_fields(tmp_path):
    path = tmp_path / "ref.json"
    path.write_text('{"source":"你好"}', encoding="utf-8")

    with pytest.raises(ValueError, match="translation"):
        parse_reference(path)


def test_comparison_continues_after_pipeline_failure_and_writes_artifacts(tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"sample")
    context = SimpleNamespace(media_path=media, output_dir=tmp_path, source_lang="zh",
                              target_lang="vi", ollama_base_url="http://localhost:11434",
                              cleanup=lambda: None)
    module = SimpleNamespace(MODEL_TAGS=())

    def fail(_context):
        raise RuntimeError("fixture error")

    def succeed(_context):
        segment = Segment(i=0, start=0, end=1, text="x")
        return PipelineResult("good", [], [segment], [segment], final_translation=[segment])

    args = SimpleNamespace(pipelines="bad,good", reference=None, output_dir=tmp_path,
                           media=media)
    status = run_comparison(args, pipeline_registry={"bad": fail, "good": succeed},
                            modules={"bad": module, "good": module},
                            context_loader=lambda _args: context,
                            model_checker=lambda *_args, **_kwargs: None)

    assert status == 1
    assert (tmp_path / "bad.error.json").exists()
    assert (tmp_path / "good.json").exists()
    assert json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8"))["complete"] is False
