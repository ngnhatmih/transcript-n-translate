from __future__ import annotations

from ._common import WHISPER, VLM, result, stage_call, translate, visual_facts
from .contracts import PipelineContext
from .runtime import extract_context_frames, transcribe

PIPELINE_ID = "whisper_vl_prompt"
MODEL_TAGS = (VLM,)


def build_asr_prompt(facts: dict) -> str:
    """Keep only concise visual entities; never feed scene guesses as speech."""
    entities = facts.get("entities", [])
    if not isinstance(entities, list):
        entities = []
    names = [str(item).strip() for item in entities if str(item).strip()]
    return "Context for proper nouns only (not transcript): " + "; ".join(names[:30])


def run(context: PipelineContext):
    stages = []
    frames = stage_call(stages, "frame_sampling", "ffmpeg",
        lambda: extract_context_frames(context.media_path, context.workdir / "frames",
                                      context.frame_interval_seconds))
    facts, sampled_frames = stage_call(stages, "visual_context", VLM, lambda: visual_facts(
        context, frames, ask="List visible names or specific place names useful for speech recognition."))
    prompt = build_asr_prompt(facts)
    source = stage_call(stages, "asr_with_visual_prompt", WHISPER,
                        lambda: transcribe(WHISPER, context.audio_path, context.source_lang,
                                           initial_prompt=prompt))
    mt_engine = context.models.get("baseline_mt") or "opus-mt"
    raw = stage_call(stages, "translation", mt_engine,
                     lambda: translate(mt_engine, source, context.glossary,
                                       context.source_lang, context.target_lang))
    return result(context, PIPELINE_ID, stages, source, raw, final=raw,
                  metadata={"visual_context": facts, "asr_initial_prompt": prompt,
                            "sampled_frames": sampled_frames})
