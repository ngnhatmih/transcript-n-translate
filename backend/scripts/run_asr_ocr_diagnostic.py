from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import pathlib
import sys
import time

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from experiments.accuracy_pipelines.ocr_scoring import score_caption_observations
from experiments.accuracy_pipelines.whisper_large_v3_hymt import (
    BEAM_SIZE, COMPUTE_TYPE, MODEL_REF, transcribe,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run Whisper large-v3 and score against OCR refs")
    parser.add_argument("audio", type=pathlib.Path)
    parser.add_argument("reference", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args(argv)
    if not args.audio.is_file():
        parser.error(f"audio not found: {args.audio}")
    try:
        from opencc import OpenCC
    except ImportError:
        parser.error("install evaluation dependency: pip install opencc-python-reimplemented==0.1.7")
    reference_bytes = args.reference.read_bytes()
    reference = json.loads(reference_bytes)
    observations = reference.get("metadata", {}).get("caption_observations")
    if not isinstance(observations, list):
        parser.error("reference JSON has no metadata.caption_observations")
    started = time.perf_counter()
    segments = transcribe(args.audio, "zh")
    elapsed = time.perf_counter() - started
    serialized = [dataclasses.asdict(segment) for segment in segments]
    score = score_caption_observations(observations, serialized, opencc=OpenCC("t2s"))
    result = {
        "model": MODEL_REF, "compute_type": COMPUTE_TYPE, "beam_size": BEAM_SIZE,
        "audio": str(args.audio.resolve()), "inference_seconds": elapsed,
        "reference_provenance": {
            "dataset_id": reference.get("dataset_id"),
            "version": reference.get("version"),
            "sha256": hashlib.sha256(reference_bytes).hexdigest(),
        },
        "segments": serialized, "score": score,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"inference_seconds": elapsed, **score}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
