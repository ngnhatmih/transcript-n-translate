from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from experiments.accuracy_pipelines.ocr_scoring import score_caption_observations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Score an ASR JSON against the saved OCR caption observations")
    parser.add_argument("reference", type=pathlib.Path,
                        help="pipeline JSON containing metadata.caption_observations")
    parser.add_argument("hypothesis", type=pathlib.Path,
                        help="ASR JSON containing segments or source_segments")
    parser.add_argument("--output", type=pathlib.Path,
                        help="optional path to save the score JSON")
    args = parser.parse_args(argv)
    try:
        from opencc import OpenCC
    except ImportError:
        parser.error("install evaluation dependency: pip install opencc-python-reimplemented==0.1.7")
    reference_bytes = args.reference.read_bytes()
    reference = json.loads(reference_bytes)
    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    observations = reference.get("metadata", {}).get("caption_observations")
    segments = hypothesis.get("segments", hypothesis.get("source_segments"))
    if not isinstance(observations, list) or not isinstance(segments, list):
        parser.error("reference/hypothesis JSON has no caption_observations/segments list")
    score = score_caption_observations(observations, segments, opencc=OpenCC("t2s"))
    score["reference_provenance"] = {
        "dataset_id": reference.get("dataset_id"),
        "version": reference.get("version"),
        "sha256": hashlib.sha256(reference_bytes).hexdigest(),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(score, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
