"""Accuracy-first local ASR and translation benchmark pipelines."""

from . import (baseline, caption_ocr, dual_asr_hymt, dual_asr_glossary_whisper_hymt,
               sensevoice_opus, visual_context, whisper_vl_prompt,
               whisper_hymt, whisper_hymt_qwen3b_edit, whisper_qwen7b,
               qwen3_asr_hymt, qwen3_vl_asr_hymt, whisper_large_v3_hymt)

PIPELINES = {
    module.PIPELINE_ID: module.run
    for module in (baseline, sensevoice_opus, whisper_hymt,
                   whisper_hymt_qwen3b_edit, whisper_qwen7b,
                   dual_asr_hymt, visual_context, whisper_vl_prompt, caption_ocr,
                   qwen3_asr_hymt, qwen3_vl_asr_hymt, whisper_large_v3_hymt,
                   dual_asr_glossary_whisper_hymt)
}

__all__ = ["PIPELINES"]
