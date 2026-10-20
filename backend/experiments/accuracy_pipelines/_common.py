from __future__ import annotations

import time
import math
from typing import Callable

from app.domain.models import Segment
from app.adapters.registry_file import load_registry
from app.domain.mt_qa import qa_translation

from .contracts import PipelineContext, PipelineResult, PipelineStage
from .runtime import ollama_json, transcribe, translate

WHISPER = "fw-large-v3-turbo"
SENSEVOICE = "sensevoice-small"
OPUS = "opus-mt"
HYMT = "hy-mt-1.5-7b"
QWEN3 = "qwen2.5:3b-instruct-q4_K_M"
QWEN7 = "qwen2.5:7b-instruct-q4_K_M"
VLM = "qwen3-vl:2b"


def stage_call(stages: list[PipelineStage], name: str, model: str, fn: Callable):
    started = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:
        stages.append(PipelineStage(name, model, round((time.perf_counter() - started) * 1000),
                                    status="failed", error=str(exc)))
        raise
    duration = round((time.perf_counter() - started) * 1000)
    stats = {}
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
        result, stats = result
    stages.append(PipelineStage(name, model, duration,
                                tokens_in=stats.get("tokens_in"), tokens_out=stats.get("tokens_out")))
    return result


def asr(ctx: PipelineContext, engine: str, stages: list[PipelineStage]) -> list[Segment]:
    return stage_call(stages, "asr", engine,
                      lambda: transcribe(engine, ctx.audio_path, ctx.source_lang))


def mt(ctx: PipelineContext, engine: str, source: list[Segment],
       stages: list[PipelineStage]) -> list[Segment]:
    return stage_call(stages, "translation", engine,
                      lambda: translate(engine, source, ctx.glossary,
                                        ctx.source_lang, ctx.target_lang))


def chat(ctx: PipelineContext, model: str, system: str, prompt: str, **kwargs):
    kwargs.pop("base_url", None)
    return ollama_json(model, system, prompt, base_url=ctx.ollama_base_url, **kwargs)


def visual_facts(ctx: PipelineContext, frames: list, *, ask: str) -> tuple[dict, int]:
    """Inspect a few frames individually to stay within small VLM context windows."""
    if not frames:
        return {"entities": [], "setting": "", "notes": []}, 0
    stride = max(1, math.ceil(len(frames) / 6))
    selected = frames[::stride][:6]
    entities, notes, settings = [], [], []
    system = (
        "Read visible text and identify named entities only. Do not infer dialogue. "
        "Return JSON {\"entities\":[],\"setting\":\"\",\"notes\":[]}"
    )
    failed_frames = 0
    for frame in selected:
        try:
            facts, _stats = chat(ctx, VLM, system, ask, images=[frame], think=False)
        except (ValueError, RuntimeError):
            # Qwen3-VL 2B occasionally exhausts its reasoning budget on a frame.
            # Keep usable results from other frames instead of discarding the run.
            failed_frames += 1
            continue
        for item in facts.get("entities", []) if isinstance(facts.get("entities", []), list) else []:
            value = str(item).strip()
            if value and value not in entities:
                entities.append(value)
        setting = facts.get("setting")
        if isinstance(setting, str) and setting.strip():
            settings.append(setting.strip())
        for item in facts.get("notes", []) if isinstance(facts.get("notes", []), list) else []:
            value = str(item).strip()
            if value and value not in notes:
                notes.append(value)
    if failed_frames:
        notes.append(f"VLM extraction failed for {failed_frames}/{len(selected)} sampled frames")
    if failed_frames == len(selected):
        raise RuntimeError("Qwen3-VL returned no usable visual context for sampled frames")
    return {"entities": entities, "setting": "; ".join(dict.fromkeys(settings)),
            "notes": notes}, len(selected)


def result(ctx: PipelineContext, pipeline_id: str, stages: list[PipelineStage],
           source: list[Segment], raw: list[Segment], *, corrected=None, final=None,
           metadata=None) -> PipelineResult:
    quality_source = corrected or source
    quality_translation = final or raw
    translation_stage = next((stage for stage in reversed(stages)
                              if stage.name in {"translation", "translation_edit",
                                                "contextual_translation"}), None)
    specs = load_registry()
    spec = None
    if translation_stage is not None:
        spec = next((item for item in specs
                     if item.id == translation_stage.model or
                     item.model_ref == translation_stage.model), None)
    issues = qa_translation(
        quality_source, quality_translation, glossary=ctx.glossary,
        supports_glossary=bool(spec and spec.capabilities.get("glossary_prompt")),
        target_lang=ctx.target_lang,
    )
    return PipelineResult(pipeline_id, stages, source, raw, corrected, final,
                          {"source_lang": ctx.source_lang, "target_lang": ctx.target_lang,
                           "models": [stage.model for stage in stages],
                           "qa_issues": issues, **(metadata or {})})
