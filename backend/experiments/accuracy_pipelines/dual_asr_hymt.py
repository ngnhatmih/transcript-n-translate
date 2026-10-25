from ._common import WHISPER, SENSEVOICE, HYMT, QWEN3, result, stage_call
from .contracts import PipelineContext
from .postprocess import reconcile_asr, edit_translation
from .runtime import transcribe, translate, ollama_json


def chat(context, model, system, prompt, **kwargs):
    kwargs.pop("base_url", None)
    return ollama_json(model, system, prompt, base_url=context.ollama_base_url, **kwargs)

PIPELINE_ID = "dual_asr_hymt"
MODEL_TAGS = ("hy-mt1.5-7b:q4_K_M", QWEN3)


def run(context: PipelineContext):
    stages = []
    whisper = stage_call(stages, "asr", WHISPER,
                         lambda: transcribe(WHISPER, context.audio_path, context.source_lang))
    sensevoice = stage_call(stages, "asr", SENSEVOICE,
                            lambda: transcribe(SENSEVOICE, context.audio_path, context.source_lang))
    corrected, alternative, _stats = stage_call(stages, "asr_reconciliation", QWEN3,
        lambda: reconcile_asr(whisper, sensevoice, model=QWEN3, lang=context.source_lang,
                              chat=lambda *a, **k: chat(context, *a, **k),
                              base_url=context.ollama_base_url))
    raw = stage_call(stages, "translation", HYMT,
                     lambda: translate(HYMT, corrected, context.glossary,
                                       context.source_lang, context.target_lang))
    final = stage_call(stages, "translation_edit", QWEN3, lambda: edit_translation(
        corrected, raw, context.glossary, model=QWEN3, source_lang=context.source_lang,
        target_lang=context.target_lang, chat=lambda *a, **k: chat(context, *a, **k),
        base_url=context.ollama_base_url))
    return result(context, PIPELINE_ID, stages, whisper, raw, corrected=corrected,
                  final=final, metadata={"alternative_asr": alternative})
