from __future__ import annotations

from ._common import HYMT, VLM, result, stage_call, translate, visual_facts
from .contracts import PipelineContext
from .qwen3_asr import transcribe_with_model
from .runtime import extract_context_frames

PIPELINE_ID = "qwen3_vl_asr_hymt"
MODEL_TAGS = (VLM, "hy-mt1.5-7b:q4_K_M")
ASR_MODEL = "Qwen3-ASR-0.6B + Qwen3-ForcedAligner-0.6B"


def build_asr_context(facts: dict) -> str:
    entities = facts.get("entities", [])
    if not isinstance(entities, list):
        return ""
    names = dict.fromkeys(str(item).strip() for item in entities if str(item).strip())
    return "; ".join(list(names)[:30])


def run(context: PipelineContext):
    stages = []
    frames = stage_call(stages, "frame_sampling", "ffmpeg", lambda: extract_context_frames(
        context.media_path, context.workdir / "qwen_asr_frames",
        context.frame_interval_seconds, crop_subtitles=True))
    facts, sampled_frames = stage_call(stages, "visual_context", VLM, lambda: visual_facts(
        context, frames, ask="List only visible named entities and place names, not subtitles."))
    asr_context = build_asr_context(facts)
    source = stage_call(stages, "asr_with_visual_context", ASR_MODEL, lambda: transcribe_with_model(
        context.audio_path, context.source_lang, asr_context))
    raw = stage_call(stages, "translation", HYMT, lambda: translate(
        HYMT, source, context.glossary, context.source_lang, context.target_lang))
    return result(context, PIPELINE_ID, stages, source, raw, final=raw,
                  metadata={"visual_context": facts, "asr_context": asr_context,
                            "sampled_frames": sampled_frames,
                            "subtitle_band_cropped": True})
