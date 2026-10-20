from ._common import WHISPER, HYMT, QWEN3, asr, mt, result, stage_call, chat
from .contracts import PipelineContext
from .postprocess import edit_translation

PIPELINE_ID = "whisper_hymt_qwen3b_edit"
MODEL_TAGS = ("hy-mt1.5-7b:q4_K_M", QWEN3)


def run(context: PipelineContext):
    stages = []
    source = asr(context, WHISPER, stages)
    raw = mt(context, HYMT, source, stages)
    final = stage_call(stages, "translation_edit", QWEN3, lambda: edit_translation(
        source, raw, context.glossary, model=QWEN3, source_lang=context.source_lang,
        target_lang=context.target_lang, chat=lambda *a, **k: chat(context, *a, **k),
        base_url=context.ollama_base_url))
    return result(context, PIPELINE_ID, stages, source, raw, final=final)
