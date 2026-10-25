from __future__ import annotations

from ._common import HYMT, result, stage_call, translate
from .contracts import PipelineContext
from .qwen3_asr import transcribe_with_model

PIPELINE_ID = "qwen3_asr_hymt"
MODEL_TAGS = ("hy-mt1.5-7b:q4_K_M",)
ASR_MODEL = "Qwen3-ASR-0.6B + Qwen3-ForcedAligner-0.6B"


def run(context: PipelineContext):
    stages = []
    source = stage_call(stages, "asr", ASR_MODEL, lambda: transcribe_with_model(
        context.audio_path, context.source_lang, ""))
    raw = stage_call(stages, "translation", HYMT, lambda: translate(
        HYMT, source, context.glossary, context.source_lang, context.target_lang))
    return result(context, PIPELINE_ID, stages, source, raw, final=raw)
