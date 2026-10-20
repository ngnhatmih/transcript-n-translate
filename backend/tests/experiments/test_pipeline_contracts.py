from __future__ import annotations

from pathlib import Path

from app.domain.models import Segment
from experiments.accuracy_pipelines import PIPELINES
from experiments.accuracy_pipelines.contracts import PipelineContext


def context(tmp_path):
    return PipelineContext(
        media_path=tmp_path / "clip.mp4", audio_path=tmp_path / "clip.wav",
        source_lang="zh", target_lang="vi", workdir=tmp_path,
        output_dir=tmp_path, models={"baseline_asr": "fw-small", "baseline_mt": "opus-mt"},
    )


def test_registry_exposes_distinct_pipeline_ids():
    assert set(PIPELINES) == {
        "baseline", "sensevoice_opus", "whisper_hymt", "whisper_hymt_qwen3b_edit",
        "whisper_qwen7b", "dual_asr_hymt", "visual_context", "whisper_vl_prompt",
        "caption_ocr", "qwen3_asr_hymt", "qwen3_vl_asr_hymt",
        "whisper_large_v3_hymt",
        "dual_asr_glossary_whisper_hymt",
    }


def test_qwen3_asr_pipeline_runs_without_context(monkeypatch, tmp_path):
    from experiments.accuracy_pipelines import qwen3_asr_hymt as pipeline

    calls = []
    source = [Segment(i=0, start=0.0, end=1.0, text="但我去汕头。")]
    monkeypatch.setattr(pipeline, "transcribe_with_model",
                        lambda audio, lang, context: calls.append((lang, context)) or source)
    monkeypatch.setattr(pipeline, "translate", lambda engine, segments, *_args: [
        Segment(i=s.i, start=s.start, end=s.end, text="Nhưng tôi đi Sán Đầu.") for s in segments
    ])

    output = pipeline.run(context(tmp_path))

    assert calls == [("zh", "")]
    assert output.source_segments == source
    assert output.raw_translation[0].text == "Nhưng tôi đi Sán Đầu."


def test_qwen3_vl_asr_pipeline_injects_only_visual_entities(monkeypatch, tmp_path):
    from experiments.accuracy_pipelines import qwen3_vl_asr_hymt as pipeline

    frame = tmp_path / "frame.jpg"
    frame.touch()
    calls = []
    source = [Segment(i=0, start=0.0, end=1.0, text="但我去汕头。")]
    monkeypatch.setattr(pipeline, "extract_context_frames",
                        lambda *_args, **_kwargs: [frame])
    monkeypatch.setattr(pipeline, "visual_facts", lambda *_args, **_kwargs: ({
        "entities": ["汕头", "烟台山"], "setting": "街区", "notes": []
    }, 1))
    monkeypatch.setattr(pipeline, "transcribe_with_model",
                        lambda _audio, _lang, ctx: calls.append(ctx) or source)
    monkeypatch.setattr(pipeline, "translate", lambda _engine, segments, *_args: segments)

    output = pipeline.run(context(tmp_path))

    assert calls == ["汕头; 烟台山"]
    assert output.metadata["visual_context"]["entities"] == ["汕头", "烟台山"]
    assert output.source_segments == source


def test_dual_asr_pipeline_reconciles_only_between_supported_hypotheses(monkeypatch, tmp_path):
    from experiments.accuracy_pipelines import dual_asr_hymt as pipeline

    calls = []
    whisper = [Segment(i=0, start=0.0, end=1.2, text="我去了市里")]
    sensevoice = [Segment(i=0, start=0.0, end=1.2, text="我去了市裡")]

    def fake_transcribe(engine, *_args, **_kwargs):
        calls.append(("asr", engine))
        return whisper if engine == "fw-large-v3-turbo" else sensevoice

    def fake_chat(model, system, prompt, **kwargs):
        calls.append(("chat", model))
        return {"segments": [{"i": 0, "text": "我去了市裡"}]}, {}

    def fake_translate(engine, segments, *_args, **_kwargs):
        calls.append(("mt", engine))
        return [Segment(i=s.i, start=s.start, end=s.end, text="Tôi đã đến thành phố")
                for s in segments]

    monkeypatch.setattr(pipeline, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline, "ollama_json", fake_chat)
    monkeypatch.setattr(pipeline, "translate", fake_translate)
    monkeypatch.setattr(pipeline, "edit_translation", lambda *_args, **_kwargs: None)

    result = pipeline.run(context(tmp_path))

    assert result.corrected_segments[0].text == "我去了市裡"
    assert result.raw_translation[0].i == 0
    assert calls[:3] == [
        ("asr", "fw-large-v3-turbo"),
        ("asr", "sensevoice-small"),
        ("chat", "qwen2.5:3b-instruct-q4_K_M"),
    ]
    assert calls[3] == ("mt", "hy-mt-1.5-7b")


def test_glossary_pipeline_extracts_only_disagreements_and_reruns_whisper(monkeypatch, tmp_path):
    from experiments.accuracy_pipelines import dual_asr_glossary_whisper_hymt as pipeline

    calls = []
    first = [Segment(i=0, start=0, end=1, text="我去了汕头。")]
    sense = [Segment(i=0, start=0, end=1, text="我去了山头。")]
    second = [Segment(i=0, start=0, end=1, text="我去了汕头。")]

    def fake_transcribe(audio, lang, *, initial_prompt=None, hotwords=None):
        calls.append((initial_prompt, hotwords))
        return first if initial_prompt is None else second

    def fake_chat(model, system, prompt, **kwargs):
        calls.append(("extract", model, prompt))
        return {"topic": "地名", "terms": [{"zh": "汕头", "variants": ["山头"]}]}, {}

    monkeypatch.setattr(pipeline, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline, "transcribe_sensevoice", lambda *_: sense)
    monkeypatch.setattr(pipeline, "ollama_json", fake_chat)
    monkeypatch.setattr(pipeline, "reconcile_asr", lambda primary, _alt, **_kw:
                        (primary, _alt, {}))
    monkeypatch.setattr(pipeline, "translate", lambda _engine, segments, *_a: [
        Segment(i=s.i, start=s.start, end=s.end, text="Tôi tới Sán Đầu") for s in segments
    ])
    monkeypatch.setattr(pipeline, "edit_translation", lambda _source, raw, *_a, **_k: (raw, {}))

    output = pipeline.run(context(tmp_path))

    assert calls[0] == (None, None)
    assert calls[1][0:2] == ("extract", "qwen2.5:3b-instruct-q4_K_M")
    assert "汕头" in calls[1][2] and "山头" in calls[1][2]
    assert calls[2] == ("以下是普通话，简体中文。术语：汕头。主题：地名", "汕头")
    assert output.metadata["first_pass_segments"] == first
    assert output.metadata["auto_glossary"][0]["zh"] == "汕头"


def test_auto_glossary_rejects_terms_not_present_in_asr_evidence():
    from experiments.accuracy_pipelines.dual_asr_glossary_whisper_hymt import (
        validate_extracted_terms,
    )

    evidence = [{"whisper": "我去了汕头", "sensevoice": "我去了山头"}]
    output = validate_extracted_terms({"topic": "地名", "terms": [
        {"zh": "深圳", "variants": ["深圳市"]},
        {"zh": "汕头", "variants": ["山头"]},
    ]}, evidence)

    assert output == [{"zh": "汕头", "variants": ["山头"]}]


def test_auto_glossary_rejects_term_without_cross_asr_spelling_disagreement():
    from experiments.accuracy_pipelines.dual_asr_glossary_whisper_hymt import (
        validate_extracted_terms,
    )

    evidence = [{"whisper": "我去了汕头", "sensevoice": "我去了汕头"}]

    output = validate_extracted_terms({"terms": [
        {"zh": "汕头", "variants": ["山头"]},
    ]}, evidence)

    assert output == []


def test_auto_glossary_requires_variant_pair_in_same_time_window():
    from experiments.accuracy_pipelines.dual_asr_glossary_whisper_hymt import (
        validate_extracted_terms,
    )

    evidence = [
        {"whisper": "汕头", "sensevoice": "我去了深圳"},
        {"whisper": "我去了深圳", "sensevoice": "我去了山头"},
    ]

    output = validate_extracted_terms({"terms": [
        {"zh": "汕头", "variants": ["山头"]},
    ]}, evidence)

    assert output == []


def test_guarded_proofread_skips_ambiguous_many_to_one_timestamps():
    from experiments.accuracy_pipelines.dual_asr_glossary_whisper_hymt import (
        guarded_proofread,
    )

    primary = [Segment(i=0, start=0, end=1, text="你好"),
               Segment(i=1, start=1, end=2, text="我去汕头")]
    alternative = [Segment(i=0, start=0, end=2, text="你好我去山头")]

    def must_not_call(*_args, **_kwargs):
        raise AssertionError("ambiguous alignment reached the LLM")

    corrected, aligned, stats = guarded_proofread(
        primary, alternative, model="fake", lang="zh", chat=lambda *_a, **_k: None,
        base_url="http://localhost", reconcile=must_not_call,
    )

    assert corrected == primary
    assert [item.text for item in aligned] == ["", ""]
    assert stats["reviewed_segments"] == 0


def test_context_prompt_does_not_inject_placeholder_topic_without_grounded_terms():
    from experiments.accuracy_pipelines.dual_asr_glossary_whisper_hymt import asr_prompt

    assert asr_prompt("一句话", []) == (None, None)


def test_guarded_proofread_only_sends_disagreements_to_llm():
    from experiments.accuracy_pipelines.dual_asr_glossary_whisper_hymt import (
        guarded_proofread,
    )

    primary = [Segment(i=0, start=0, end=1, text="你好。"),
               Segment(i=1, start=1, end=2, text="我去汕头")]
    alternative = [Segment(i=0, start=0, end=1, text="你好"),
                   Segment(i=1, start=1, end=2, text="我去山头")]
    seen = []
    seen_alternative = []

    def choose_only_supported(primary_subset, alt, **_kwargs):
        seen.extend(segment.i for segment in primary_subset)
        seen_alternative.extend(segment.text for segment in alt)
        return primary_subset, alt, {}

    corrected, aligned, _stats = guarded_proofread(
        primary, alternative, model="fake", lang="zh", chat=lambda *_a, **_k: None,
        base_url="http://localhost", reconcile=choose_only_supported,
    )

    assert seen == [1]
    assert seen_alternative == ["我去山头"]
    assert [segment.text for segment in corrected] == ["你好。", "我去汕头"]
    assert len(aligned) == len(primary)


def test_translation_edit_rejection_falls_back_to_valid_raw_translation():
    from experiments.accuracy_pipelines.dual_asr_glossary_whisper_hymt import (
        safe_translation_edit,
    )
    from experiments.accuracy_pipelines.postprocess import PipelineOutputError

    source = [Segment(i=0, start=0, end=1, text="不要去")]
    raw = [Segment(i=0, start=0, end=1, text="Đừng đi")]

    def reject_edit(*_args, **_kwargs):
        raise PipelineOutputError("translation edit removed negation")

    output, status = safe_translation_edit(source, raw, [], edit=reject_edit)

    assert output == raw
    assert status == {"status": "rejected", "reason": "translation edit removed negation"}


def test_large_whisper_forwards_initial_prompt_and_hotwords(monkeypatch):
    import sys
    from types import SimpleNamespace
    from experiments.accuracy_pipelines import whisper_large_v3_hymt as pipeline

    seen = {}

    class FakeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        def transcribe(self, _audio, **kwargs):
            seen.update(kwargs)
            return ([SimpleNamespace(start=0.0, end=1.0, text="汕头")], None)

    monkeypatch.setattr(pipeline, "ensure_cuda_runtime", lambda: None)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))

    pipeline.transcribe("clip.wav", "zh", initial_prompt="主题：地名。术语：汕头", hotwords="汕头")

    assert seen["initial_prompt"] == "主题：地名。术语：汕头"
    assert seen["hotwords"] == "汕头"


def test_visual_pipeline_requests_frames_and_keeps_visual_facts_separate(monkeypatch, tmp_path):
    from experiments.accuracy_pipelines import visual_context as pipeline

    frame = tmp_path / "frame_0001.jpg"
    frame.touch()
    calls = []

    monkeypatch.setattr(pipeline, "extract_context_frames",
                        lambda *_args, **_kwargs: [frame])
    monkeypatch.setattr(pipeline, "transcribe",
                        lambda engine, *_args, **_kwargs: [Segment(
                            i=0, start=0.0, end=1.2, text="他是张三")])

    monkeypatch.setattr(pipeline, "visual_facts", lambda *_a, **_k: ({
        "entities": ["张三"], "setting": "医院", "notes": []
    }, 1))
    monkeypatch.setattr(pipeline, "translate", lambda _engine, segments, *_a, **_k: [
        Segment(i=s.i, start=s.start, end=s.end, text="Anh ấy là Trương Tam") for s in segments
    ])
    monkeypatch.setattr(pipeline, "edit_translation", lambda _source, raw, *_a, **_k: raw)

    result = pipeline.run(context(tmp_path))

    assert result.metadata["visual_context"] == {
        "entities": ["张三"], "setting": "医院", "notes": []
    }


def test_whisper_vl_prompt_injects_only_visual_entities_into_asr(monkeypatch, tmp_path):
    from experiments.accuracy_pipelines import whisper_vl_prompt as pipeline

    frame = tmp_path / "frame_0001.jpg"
    frame.touch()
    calls = []
    monkeypatch.setattr(pipeline, "extract_context_frames", lambda *_a, **_k: [frame])
    monkeypatch.setattr(pipeline, "visual_facts", lambda *_a, **_k: ({
        "entities": ["汕头", "烟台山"], "setting": "街道", "notes": []
    }, 1))

    def fake_transcribe(_engine, *_args, **kwargs):
        calls.append(kwargs["initial_prompt"])
        return [Segment(i=0, start=0, end=1, text="汕头")]

    monkeypatch.setattr(pipeline, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline, "translate", lambda _engine, segments, *_a, **_k: [
        Segment(i=s.i, start=s.start, end=s.end, text="Sán Đầu") for s in segments
    ])

    output = pipeline.run(context(tmp_path))

    assert calls == ["Context for proper nouns only (not transcript): 汕头; 烟台山"]
    assert output.source_segments[0].text == "汕头"


def test_pipeline_modules_keep_raw_and_edited_translation_separate():
    for run_pipeline in PIPELINES.values():
        assert callable(run_pipeline)


def test_whisper_qwen7b_uses_translation_adapter_not_post_editor(monkeypatch, tmp_path):
    from experiments.accuracy_pipelines import whisper_qwen7b as pipeline

    source = [Segment(i=0, start=0, end=1, text="你好")]
    translated = [Segment(i=0, start=0, end=1, text="Xin chào")]
    calls = []
    monkeypatch.setattr(pipeline, "asr", lambda *_args: source)
    monkeypatch.setattr(pipeline, "translate", lambda engine, *_args: calls.append(engine) or translated)

    output = pipeline.run(context(tmp_path))

    assert calls == ["qwen2.5-7b"]
    assert output.final_translation == translated


def test_pipeline_result_reports_source_language_echo(tmp_path):
    from experiments.accuracy_pipelines._common import result
    from experiments.accuracy_pipelines.contracts import PipelineStage

    source = [Segment(i=0, start=0, end=1, text="你好")]
    output = result(context(tmp_path), "test",
                    [PipelineStage("translation", "qwen2.5-7b", 1)],
                    source, source, final=source)

    assert output.metadata["qa_issues"] == ["lang:0=source:han2/latin0"]


def test_shared_chat_wrapper_uses_context_url_once(monkeypatch, tmp_path):
    from experiments.accuracy_pipelines import _common

    ctx = context(tmp_path)
    calls = []
    monkeypatch.setattr(_common, "ollama_json",
                        lambda *args, **kwargs: calls.append((args, kwargs)) or ({}, {}))

    _common.chat(ctx, "qwen", "system", "prompt", base_url="http://ignored")

    assert calls[0][1]["base_url"] == ctx.ollama_base_url
