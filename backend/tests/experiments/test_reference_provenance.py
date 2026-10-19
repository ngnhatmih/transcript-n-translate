from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from app.domain.models import Segment
from experiments.accuracy_pipelines.contracts import PipelineResult
from scripts import compare_pipelines, run_asr_ocr_diagnostic, score_caption_ocr


def _reference(path):
    payload = {
        "dataset_id": "ocr-caption-reference-v2",
        "version": 3,
        "source": "x",
        "translation": "y",
        "metadata": {"caption_observations": [{"i": 0, "start": 0, "end": 1, "ocr": "你好世界"}]},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_caption_scorer_records_the_reference_bytes(tmp_path):
    reference, hypothesis, output = tmp_path / "reference.json", tmp_path / "hypothesis.json", tmp_path / "score.json"
    expected_hash = _reference(reference)
    hypothesis.write_text(json.dumps({"segments": [{"start": 0, "end": 1, "text": "你好世界"}]}), encoding="utf-8")

    assert score_caption_ocr.main([str(reference), str(hypothesis), "--output", str(output)]) == 0

    assert json.loads(output.read_text(encoding="utf-8"))["reference_provenance"] == {
        "dataset_id": "ocr-caption-reference-v2", "version": 3, "sha256": expected_hash,
    }


def test_diagnostic_records_the_reference_bytes(tmp_path, monkeypatch):
    audio, reference, output = tmp_path / "audio.wav", tmp_path / "reference.json", tmp_path / "diagnostic.json"
    audio.write_bytes(b"audio")
    expected_hash = _reference(reference)
    monkeypatch.setattr(run_asr_ocr_diagnostic, "transcribe", lambda *_args: [
        Segment(i=0, start=0, end=1, text="你好世界")
    ])

    assert run_asr_ocr_diagnostic.main([str(audio), str(reference), str(output)]) == 0

    assert json.loads(output.read_text(encoding="utf-8"))["reference_provenance"] == {
        "dataset_id": "ocr-caption-reference-v2", "version": 3, "sha256": expected_hash,
    }


def test_comparison_records_the_reference_bytes(tmp_path):
    media, reference = tmp_path / "clip.mp4", tmp_path / "reference.json"
    media.write_bytes(b"media")
    expected_hash = _reference(reference)
    context = SimpleNamespace(media_path=media, output_dir=tmp_path, source_lang="zh",
                              target_lang="vi", ollama_base_url="http://localhost:11434",
                              cleanup=lambda: None)
    module = SimpleNamespace(MODEL_TAGS=())
    args = SimpleNamespace(pipelines="good", reference=reference, output_dir=tmp_path, media=media)

    assert compare_pipelines.run_comparison(
        args, pipeline_registry={"good": lambda _ctx: PipelineResult("good", [], [], [])},
        modules={"good": module}, context_loader=lambda _args: context,
        model_checker=lambda *_args, **_kwargs: None,
    ) == 0

    assert json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8"))["reference_provenance"] == {
        "dataset_id": "ocr-caption-reference-v2", "version": 3, "sha256": expected_hash,
    }
