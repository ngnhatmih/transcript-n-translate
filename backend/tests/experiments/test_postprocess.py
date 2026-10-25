from __future__ import annotations

import json

import pytest

from app.domain.models import Segment, Term
from experiments.accuracy_pipelines.postprocess import (
    PipelineOutputError,
    normalize_for_scoring,
    align_hypothesis,
    validate_asr_correction,
    validate_translation_edit,
    edit_translation,
    reconcile_asr,
)


def segment(i: int, text: str, *, start: float = 1.0, end: float = 2.0) -> Segment:
    return Segment(i=i, start=start, end=end, text=text)


def test_asr_correction_can_select_a_text_present_in_an_independent_hypothesis():
    source = [segment(0, "他在市里")]
    chosen = [segment(0, "他在市裡")]

    result = validate_asr_correction(source, chosen, alternatives=[[segment(0, "他在市裡")]])

    assert result[0].text == "他在市裡"
    assert source[0].text == "他在市里"


def test_asr_correction_rejects_text_not_supported_by_any_hypothesis():
    source = [segment(0, "他在市里")]

    with pytest.raises(PipelineOutputError, match="unsupported"):
        validate_asr_correction(source, [segment(0, "他在北京")], alternatives=[])


@pytest.mark.parametrize("bad", [
    [segment(1, "他在市里")],
    [segment(0, "")],
    [segment(0, "他在市裡", start=1.1)],
])
def test_asr_correction_rejects_invalid_alignment_or_empty_text(bad):
    source = [segment(0, "他在市里")]

    with pytest.raises(PipelineOutputError):
        validate_asr_correction(source, bad, alternatives=[[segment(0, "他在市裡")]])


def test_translation_edit_preserves_timing_numbers_and_approved_glossary():
    source = [segment(0, "第3号龙来了")]
    raw = [segment(0, "Số 3, rồng đã tới")]
    edited = [segment(0, "Số 3, Rồng đã tới")]
    glossary = [Term(id=1, lang="zh", term="龙", translation="Rồng", approved=True)]

    assert validate_translation_edit(source, raw, edited, glossary) == edited


@pytest.mark.parametrize("edited_text", ["Số 4, Rồng đã tới", "Số 3, sinh vật đã tới", ""])
def test_translation_edit_rejects_number_glossary_or_empty_regressions(edited_text):
    source = [segment(0, "第3号龙来了")]
    raw = [segment(0, "Số 3, rồng đã tới")]
    glossary = [Term(id=1, lang="zh", term="龙", translation="Rồng", approved=True)]

    with pytest.raises(PipelineOutputError):
        validate_translation_edit(source, raw, [segment(0, edited_text)], glossary)


def test_scoring_normalization_keeps_lexical_content_and_folds_punctuation():
    assert normalize_for_scoring("  你好，  Xin chào! ") == "你好 Xin chào"


def test_sensevoice_hypothesis_is_aligned_by_time_to_whisper_skeleton():
    whisper = [segment(0, "第一句", start=0.0, end=1.0),
               segment(1, "第二句", start=1.0, end=2.0)]
    sensevoice = [segment(0, "甲", start=0.2, end=0.8),
                  segment(1, "乙", start=1.1, end=1.9)]

    aligned = align_hypothesis(whisper, sensevoice, lang="zh")

    assert [(s.i, s.start, s.end, s.text) for s in aligned] == [
        (0, 0.0, 1.0, "甲"), (1, 1.0, 2.0, "乙")]


def test_translation_editor_retries_malformed_multi_segment_batch_individually():
    source = [segment(0, "你好"), segment(1, "再见", start=2.0, end=3.0)]
    raw = [segment(0, "Xin chào"), segment(1, "Tạm biệt", start=2.0, end=3.0)]
    calls = []

    def fake_chat(_model, _system, prompt, **_kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            return {"segments": []}, {}
        pairs = json.loads(prompt.split("Chỉnh đúng các mục sau: ", 1)[1])
        return {"segments": [{"i": pair["i"], "text": pair["draft"]} for pair in pairs]}, {}

    edited, _stats = edit_translation(source, raw, [], model="fake", source_lang="zh",
                                      target_lang="vi", chat=fake_chat, base_url="", batch_size=2)

    assert [item.text for item in edited] == ["Xin chào", "Tạm biệt"]
    assert len(calls) == 3


def test_translation_editor_merges_by_id_and_keeps_raw_for_missing_or_invalid_items():
    source = [segment(0, "你好"), segment(1, "第3号龙来了", start=2, end=3)]
    raw = [segment(0, "Xin chào"), segment(1, "Số 3, rồng đã tới", start=2, end=3)]
    glossary = [Term(id=1, lang="zh", term="龙", translation="Rồng", approved=True)]

    edited, _stats = edit_translation(
        source, raw, glossary, model="fake", source_lang="zh", target_lang="vi",
        chat=lambda *_a, **_k: ({"segments": [
            {"i": 1, "text": "Số 4, Rồng đã tới"},
            {"i": 0, "text": "Chào bạn"},
        ]}, {}), base_url="", batch_size=2)

    assert [item.text for item in edited] == ["Chào bạn", "Số 3, rồng đã tới"]


def test_translation_editor_keeps_only_the_missing_items_from_raw_translation():
    source = [segment(0, "你好"), segment(1, "再见", start=2, end=3)]
    raw = [segment(0, "Xin chào"), segment(1, "Tạm biệt", start=2, end=3)]

    edited, stats = edit_translation(
        source, raw, [], model="fake", source_lang="zh", target_lang="vi",
        chat=lambda *_a, **_k: ({"segments": [{"i": 1, "text": "Hẹn gặp lại"}]}, {}),
        base_url="", batch_size=2)

    assert [item.text for item in edited] == ["Xin chào", "Hẹn gặp lại"]
    assert stats["fallback_segments"] == 1


def test_asr_reconciler_retries_malformed_multi_segment_batch_individually():
    primary = [segment(0, "那赶紧赔我了"), segment(1, "但我直接去扇头", start=2, end=3)]
    alternative = [segment(0, "那赶紧赔我了"), segment(1, "但我直接去汕头", start=2, end=3)]
    calls = []

    def fake_chat(_model, _system, prompt, **_kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            return {"segments": []}, {}
        item = json.loads(prompt.split("Dữ liệu: ", 1)[1])[0]
        selected = item["sensevoice"] if "汕头" in item["sensevoice"] else item["whisper"]
        return {"segments": [{"i": 0, "text": selected}]}, {}

    corrected, _aligned, _stats = reconcile_asr(
        primary, alternative, model="fake", lang="zh", chat=fake_chat,
        base_url="", visual_facts={"entities": ["汕头"]}, batch_size=2)

    assert [item.text for item in corrected] == ["那赶紧赔我了", "但我直接去汕头"]
    assert len(calls) == 3


def test_asr_reconciler_falls_back_to_whisper_if_single_item_is_invalid():
    primary = [segment(0, "那赶紧赔我了"), segment(1, "但我直接去扇头", start=2, end=3)]
    alternative = [segment(0, "那赶紧赔我了"), segment(1, "但我直接去汕头", start=2, end=3)]
    calls = 0

    def fake_chat(_model, _system, _prompt, **_kwargs):
        nonlocal calls
        calls += 1
        return {"segments": []}, {}

    corrected, _aligned, stats = reconcile_asr(
        primary, alternative, model="fake", lang="zh", chat=fake_chat,
        base_url="", batch_size=2)

    assert [item.text for item in corrected] == [item.text for item in primary]
    assert stats["fallback_segments"] == 2
    assert calls == 3


def test_asr_reconciler_rejects_llm_speech_not_in_either_asr_hypothesis():
    primary = [segment(0, "那赶紧赔我了")]
    alternative = [segment(0, "那该你赔我了")]

    corrected, _aligned, stats = reconcile_asr(
        primary, alternative, model="fake", lang="zh",
        chat=lambda *_a, **_k: ({"segments": [{"i": 0, "text": "那应该赔钱"}]}, {}),
        base_url="", visual_facts={"entities": ["汕头"]}, batch_size=1)

    assert corrected[0].text == primary[0].text
    assert stats["fallback_segments"] == 1
