from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import traceback
import uuid

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import DATA_DIR
from experiments.accuracy_pipelines import PIPELINES
from experiments.accuracy_pipelines import (baseline, dual_asr_hymt,
    sensevoice_opus,
    visual_context, whisper_hymt, whisper_hymt_qwen3b_edit, whisper_qwen7b,
    whisper_vl_prompt, caption_ocr, qwen3_asr_hymt, qwen3_vl_asr_hymt,
    whisper_large_v3_hymt, dual_asr_glossary_whisper_hymt)
from experiments.accuracy_pipelines.contracts import PipelineResult
from experiments.accuracy_pipelines.reporting import build_report, markdown_report
from experiments.accuracy_pipelines.runtime import (load_runtime_context,
    require_ollama_models, ModelUnavailableError)

_MODULES = {module.PIPELINE_ID: module for module in (baseline, sensevoice_opus,
    whisper_hymt, whisper_hymt_qwen3b_edit, whisper_qwen7b, dual_asr_hymt, visual_context,
    whisper_vl_prompt, caption_ocr, qwen3_asr_hymt, qwen3_vl_asr_hymt,
    whisper_large_v3_hymt, dual_asr_glossary_whisper_hymt)}


def parse_pipeline_ids(value: str, registry=None) -> list[str]:
    registry = registry or PIPELINES
    ids = list(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))
    unknown = [pipeline_id for pipeline_id in ids if pipeline_id not in registry]
    if unknown:
        raise ValueError(f"unknown pipeline id(s): {', '.join(unknown)}")
    if not ids:
        raise ValueError("select at least one pipeline")
    return ids


def parse_reference(path: pathlib.Path | None) -> dict | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("reference JSON must be an object")
    normalized = {}
    for key in ("source", "translation"):
        value = payload.get(key)
        if isinstance(value, str):
            normalized[key] = value
        elif isinstance(value, list) and all(isinstance(part, str) for part in value):
            normalized[key] = "".join(value)
        else:
            raise ValueError(f"reference field {key!r} must be a string or list of strings")
    return normalized


def reference_provenance(path: pathlib.Path | None) -> dict | None:
    if path is None:
        return None
    reference_bytes = path.read_bytes()
    payload = json.loads(reference_bytes)
    return {"dataset_id": payload.get("dataset_id"), "version": payload.get("version"),
            "sha256": hashlib.sha256(reference_bytes).hexdigest()}


def _serialize(value):
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, pathlib.Path):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare local ASR/translation pipelines")
    parser.add_argument("media", type=pathlib.Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--pipelines", default=",".join(PIPELINES))
    parser.add_argument("--reference", type=pathlib.Path)
    parser.add_argument("--glossary", type=pathlib.Path)
    parser.add_argument("--output-dir", type=pathlib.Path)
    parser.add_argument("--frame-interval", type=int, default=15)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--baseline-asr")
    parser.add_argument("--baseline-mt")
    return parser


def run_comparison(args, *, pipeline_registry=None, modules=None,
                   context_loader=load_runtime_context, model_checker=require_ollama_models):
    registry = pipeline_registry or PIPELINES
    selected = parse_pipeline_ids(args.pipelines, registry)
    reference = parse_reference(args.reference)
    provenance = reference_provenance(args.reference)
    run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    args.output_dir = args.output_dir or DATA_DIR / "experiments" / "accuracy-pipelines" / run_id
    args.output_dir.mkdir(parents=True, exist_ok=True)
    context = context_loader(args)
    module_map = modules or _MODULES
    results, failures = [], []
    try:
        for pipeline_id in selected:
            try:
                model_checker(module_map[pipeline_id].MODEL_TAGS,
                              base_url=context.ollama_base_url)
                item = registry[pipeline_id](context)
                if not isinstance(item, PipelineResult):
                    raise TypeError(f"{pipeline_id} returned {type(item).__name__}, expected PipelineResult")
                results.append(item)
                (args.output_dir / f"{pipeline_id}.json").write_text(
                    json.dumps(item, ensure_ascii=False, default=_serialize, indent=2), encoding="utf-8")
            except Exception as exc:
                failures.append({"pipeline_id": pipeline_id, "error": str(exc),
                                 "traceback": traceback.format_exc(limit=8)})
                (args.output_dir / f"{pipeline_id}.error.json").write_text(
                    json.dumps(failures[-1], ensure_ascii=False, indent=2), encoding="utf-8")
        rows = build_report(results, reference)
        complete = not failures and len(results) == len(selected)
        report = {"run_id": run_id, "complete": complete, "media": str(context.media_path),
                  "media_sha256": hashlib.sha256(context.media_path.read_bytes()).hexdigest(),
                  "source_lang": context.source_lang, "target_lang": context.target_lang,
                  "reference": reference, "reference_provenance": provenance,
                  "rows": rows, "failures": failures}
        (args.output_dir / "comparison.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output_dir / "comparison.md").write_text(
            markdown_report(rows, complete=complete), encoding="utf-8")
        return 0 if complete else 1
    finally:
        context.cleanup()


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.pipelines = ",".join(parse_pipeline_ids(args.pipelines))
        args.reference = args.reference.resolve() if args.reference else None
        args.glossary = args.glossary.resolve() if args.glossary else None
        return run_comparison(args)
    except (ValueError, ModelUnavailableError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
