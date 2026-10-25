from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
from pathlib import Path
import re

import httpx

from ._common import VLM, WHISPER, chat, result, stage_call, translate
from .contracts import PipelineContext
from .postprocess import normalize_for_scoring
from .runtime import extract_frame_at, transcribe, unload_ollama_model

PIPELINE_ID = "caption_ocr"
MODEL_TAGS = (VLM,)
_MIN_CAPTION_SIMILARITY = 0.60
_NUMBER_PARTS = re.compile(r"\d+|[零〇一二两三四五六七八九十百千万亿]+")
_NEGATION = re.compile(r"不|没|无|未|别|非")


def choose_caption_text(asr_text: str, caption_text: str,
                        *, min_similarity: float = _MIN_CAPTION_SIMILARITY) -> str:
    """Use burned-in caption OCR only when it closely corroborates ASR text."""
    asr = normalize_for_scoring(asr_text)
    caption = normalize_for_scoring(caption_text)
    if not asr or len(asr) < 4 or len(caption) < 4:
        return asr_text
    if (_NUMBER_PARTS.findall(asr) != _NUMBER_PARTS.findall(caption)
            or _NEGATION.findall(asr) != _NEGATION.findall(caption)):
        return asr_text
    if min(len(asr), len(caption)) / max(len(asr), len(caption)) < 0.9:
        return asr_text
    if SequenceMatcher(None, asr, caption, autojunk=False).ratio() >= min_similarity:
        return caption_text.strip()
    return asr_text


def run(context: PipelineContext):
    stages = []
    source = stage_call(stages, "asr", WHISPER,
                        lambda: transcribe(WHISPER, context.audio_path, context.source_lang))
    corrected = []
    changes = []
    observations = []
    failures = 0
    frame_dir = context.workdir / "caption_frames"
    system = ""

    def read_and_align_captions():
        nonlocal failures
        try:
            for segment in source:
                frame = extract_frame_at(
                    context.media_path, (segment.start + segment.end) / 2,
                    frame_dir / f"segment-{segment.i:04d}.jpg")
                try:
                    payload, _stats = chat(
                        context, VLM, system,
                        "Read the visible Chinese subtitle exactly. Return JSON only: {\"text\":\"...\"}",
                        images=[frame], think=False, unload_after=False, num_predict=256)
                    caption = payload.get("text", "")
                    caption = caption.strip() if isinstance(caption, str) else ""
                    chosen = choose_caption_text(segment.text, caption)
                    observations.append({"i": segment.i, "start": segment.start,
                                         "end": segment.end, "asr": segment.text,
                                         "ocr": caption, "selected": chosen})
                    if chosen != segment.text:
                        changes.append({"i": segment.i, "before": segment.text, "after": chosen})
                    corrected.append(replace(segment, text=chosen))
                except (ValueError, httpx.HTTPError):
                    failures += 1
                    observations.append({"i": segment.i, "start": segment.start,
                                         "end": segment.end, "asr": segment.text,
                                         "ocr": "", "selected": segment.text})
                    corrected.append(segment)
        finally:
            unload_ollama_model(VLM, base_url=context.ollama_base_url)
        return corrected

    stage_call(stages, "caption_ocr_alignment", VLM, read_and_align_captions)
    mt_engine = context.models.get("baseline_mt") or "opus-mt"
    translated = stage_call(stages, "translation", mt_engine,
                             lambda: translate(mt_engine, corrected, context.glossary,
                                               context.source_lang, context.target_lang))
    return result(context, PIPELINE_ID, stages, source, translated,
                  corrected=corrected, final=translated,
                  metadata={"caption_corrections": changes,
                            "caption_observations": observations,
                            "caption_ocr_failures": failures,
                            "caption_ocr_coverage": len(source) - failures,
                            "caption_ocr_is_applicable_only_to_burned_subtitles": True})
