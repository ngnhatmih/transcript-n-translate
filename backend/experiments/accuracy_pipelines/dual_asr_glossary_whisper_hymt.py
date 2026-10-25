"""Dual-ASR disagreement glossary, a prompted second full Whisper pass, and HY-MT."""
from __future__ import annotations

import json
import unicodedata
from dataclasses import replace

from ._common import HYMT, QWEN3, result, stage_call
from .contracts import PipelineContext
from .postprocess import (align_hypothesis, edit_translation, normalize_for_scoring,
                          PipelineOutputError, reconcile_asr, validate_asr_correction)
from .runtime import transcribe as transcribe_sensevoice, translate, ollama_json
from .whisper_large_v3_hymt import transcribe

PIPELINE_ID = "dual_asr_glossary_whisper_hymt"
MODEL_TAGS = ("hy-mt1.5-7b:q4_K_M", QWEN3)
MAX_EVIDENCE = 40
MAX_TERMS = 20
MIN_ALIGNMENT_OVERLAP = 0.65


def disagreement_evidence(whisper, sensevoice, lang: str) -> list[dict]:
    aligned = align_hypothesis(whisper, sensevoice, lang=lang)
    return [
        {"i": source.i, "start": source.start, "end": source.end,
         "whisper": source.text.strip(), "sensevoice": other.text.strip()}
        for source, other in zip(whisper, aligned)
        if normalize_for_scoring(source.text) != normalize_for_scoring(other.text)
    ][:MAX_EVIDENCE]


def validate_extracted_terms(payload: dict, evidence: list[dict]) -> list[dict]:
    """Keep only terms with two observed spellings, one from each ASR."""
    terms = payload.get("terms") if isinstance(payload, dict) else None
    if not isinstance(terms, list):
        return []
    out, seen = [], set()
    for item in terms:
        if not isinstance(item, dict):
            continue
        zh = item.get("zh")
        variants = item.get("variants", [])
        if not isinstance(zh, str) or not isinstance(variants, list):
            continue
        zh = zh.strip()
        variants = list(dict.fromkeys(
            value.strip() for value in variants
            if isinstance(value, str) and value.strip()
        ))
        candidates = [zh, *variants]
        forms = {unicodedata.normalize("NFKC", value).casefold() for value in candidates
                 if value}
        disagrees = False
        for row in evidence:
            left = unicodedata.normalize("NFKC", str(row.get("whisper", ""))).casefold()
            right = unicodedata.normalize("NFKC", str(row.get("sensevoice", ""))).casefold()
            left_forms = {form for form in forms if form in left}
            right_forms = {form for form in forms if form in right}
            if any(a != b for a in left_forms for b in right_forms):
                disagrees = True
                break
        if not zh or zh in seen or not disagrees:
            continue
        seen.add(zh)
        out.append({"zh": zh, "variants": variants[:5]})
        if len(out) == MAX_TERMS:
            break
    return out


def asr_prompt(topic: str, terms: list[dict]) -> tuple[str | None, str | None]:
    names = list(dict.fromkeys(item["zh"] for item in terms if item.get("zh")))
    if not names:
        return None, None
    prompt = f"以下是普通话，简体中文。术语：{'、'.join(names)}"
    if topic.strip():
        prompt += f"。主题：{topic.strip()}"
    return prompt, " ".join(names) or None


def guarded_proofread(primary, alternative, *, model: str, lang: str, chat,
                      base_url: str, reconcile=None):
    """Spend LLM calls only on differing time windows; preserve every other segment."""
    aligned = []
    for source in primary:
        best_overlap, best_candidate = 0.0, None
        for candidate in alternative:
            overlap = max(0.0, min(source.end, candidate.end) - max(source.start, candidate.start))
            if overlap > best_overlap:
                best_overlap, best_candidate = overlap, candidate
        denominator = max(source.duration, best_candidate.duration) if best_candidate else 0.0
        confidence = best_overlap / denominator if denominator > 0 else 0.0
        text = best_candidate.text if confidence >= MIN_ALIGNMENT_OVERLAP else ""
        aligned.append(replace(source, text=text))
    candidates = [source for source, other in zip(primary, aligned)
                  if other.text.strip() and
                  normalize_for_scoring(source.text) != normalize_for_scoring(other.text)]
    if not candidates:
        return validate_asr_correction(primary, primary, alternatives=[aligned]), aligned, {
            "reviewed_segments": 0, "skipped_agreements": len(primary),
        }
    aligned_by_id = {segment.i: segment for segment in aligned}
    candidate_alternative = [replace(segment, text=aligned_by_id[segment.i].text)
                             for segment in candidates]
    edited, _candidate_alternative, stats = (reconcile or reconcile_asr)(
        candidates, candidate_alternative, model=model, lang=lang, chat=chat,
        base_url=base_url,
    )
    by_id = {segment.i: segment for segment in edited}
    corrected = [by_id.get(segment.i, segment) for segment in primary]
    stats["reviewed_segments"] = len(candidates)
    stats["skipped_agreements"] = len(primary) - len(candidates)
    return validate_asr_correction(primary, corrected, alternatives=[aligned]), aligned, stats


def safe_translation_edit(source, raw, glossary, *, edit=None, **kwargs):
    """Fall back to the complete raw translation when a guarded edit is rejected."""
    try:
        output, stats = (edit or edit_translation)(source, raw, glossary, **kwargs)
        return output, {"status": "accepted", "stats": stats}
    except PipelineOutputError as exc:
        return raw, {"status": "rejected", "reason": str(exc)}


def _chat(context: PipelineContext, model: str, system: str, prompt: str, **kwargs):
    kwargs.pop("base_url", None)
    return ollama_json(model, system, prompt, base_url=context.ollama_base_url, **kwargs)


def _extract(context: PipelineContext, evidence: list[dict]) -> tuple[str, list[dict]]:
    if not evidence:
        return "", []
    system = (
        "你是中文语音识别术语整理器。A/B 是同一段音频的 ASR 结果。"
        "只根据给出的不同片段判断主题，并提取其中实际出现的人名、品牌、地名、"
        "专业词。若 A/B 写法不同，合并为一个条目并将观察到的其他写法放入 variants。"
        "不得补充片段中没有出现的词。topic 必须是具体主题，不要照抄字段说明；"
        "无法判断时填空字符串。只返回 JSON："
        "{\"topic\":\"城市历史街区艺术\",\"terms\":[{\"zh\":\"汕头\",\"variants\":[\"山头\"]}]}"
    )
    payload, _stats = _chat(
        context, QWEN3, system,
        "只分析以下 ASR 不同片段；不要推测视频画面或未给出的上下文。\n"
        + json.dumps(evidence, ensure_ascii=False), think=False, num_predict=700,
    )
    topic = payload.get("topic", "") if isinstance(payload, dict) else ""
    if not isinstance(topic, str):
        topic = ""
    if topic.strip() in {"一句话", "主题", "领域", "内容主题", "未知", "无法判断"}:
        topic = ""
    return topic.strip(), validate_extracted_terms(payload, evidence)


def run(context: PipelineContext):
    stages = []
    whisper_1 = stage_call(stages, "asr_pass_1", "large-v3 beam=5",
                           lambda: transcribe(context.audio_path, context.source_lang))
    sensevoice = stage_call(stages, "asr_second_opinion", "sensevoice-small",
                            lambda: transcribe_sensevoice(
                                "sensevoice-small", context.audio_path, context.source_lang))
    evidence = disagreement_evidence(whisper_1, sensevoice, context.source_lang)
    topic, terms = stage_call(
        stages, "glossary_extraction", QWEN3,
        lambda: _extract(context, evidence),
    )
    prompt, hotwords = asr_prompt(topic, terms)
    whisper_2 = (stage_call(
        stages, "asr_pass_2_contextual", "large-v3 beam=5 + glossary",
        lambda: transcribe(context.audio_path, context.source_lang,
                           initial_prompt=prompt, hotwords=hotwords),
    ) if prompt else whisper_1)
    corrected, alternative, reconciliation = stage_call(
        stages, "asr_guarded_proofread", QWEN3,
        lambda: guarded_proofread(
            whisper_2, sensevoice,
            model=QWEN3, lang=context.source_lang,
            chat=lambda *args, **kwargs: _chat(context, *args, **kwargs),
            base_url=context.ollama_base_url,
        ),
    )
    raw = stage_call(stages, "translation", HYMT, lambda: translate(
        HYMT, corrected, context.glossary, context.source_lang, context.target_lang))
    edit_status = {}

    def guarded_translation_edit():
        output, status = safe_translation_edit(
            corrected, raw, context.glossary,
            model=QWEN3, source_lang=context.source_lang,
            target_lang=context.target_lang,
            chat=lambda *args, **kwargs: _chat(context, *args, **kwargs),
            base_url=context.ollama_base_url,
        )
        edit_status.update(status)
        return output, status.get("stats", {})

    final = stage_call(stages, "translation_edit", QWEN3, guarded_translation_edit)
    return result(
        context, PIPELINE_ID, stages, whisper_2, raw, corrected=corrected, final=final,
        metadata={
            "first_pass_segments": whisper_1,
            "sensevoice_segments": sensevoice,
            "second_pass_segments": whisper_2,
            "disagreement_count": len(evidence),
            "disagreement_evidence": evidence,
            "glossary_topic": topic,
            "auto_glossary": terms,
            "asr_initial_prompt": prompt,
            "asr_hotwords": hotwords,
            "asr_reconciliation": reconciliation,
            "alternative_asr": alternative,
            "vocal_separation": "not_run; input is ffmpeg-extracted audio",
            "second_pass_skipped_reason": "no grounded glossary terms" if not prompt else None,
            "translation_edit": edit_status,
        },
    )
