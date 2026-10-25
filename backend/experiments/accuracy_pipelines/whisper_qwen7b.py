from ._common import WHISPER, QWEN7, asr, result, stage_call
from .contracts import PipelineContext
from .runtime import translate

PIPELINE_ID = "whisper_qwen7b"
MODEL_TAGS = (QWEN7,)


def run(context: PipelineContext):
    stages = []
    source = asr(context, WHISPER, stages)
    translated = stage_call(stages, "translation", "qwen2.5-7b", lambda: translate(
        "qwen2.5-7b", source, context.glossary,
        context.source_lang, context.target_lang))
    return result(context, PIPELINE_ID, stages, source, translated, final=translated)
