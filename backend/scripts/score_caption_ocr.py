from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from experiments.accuracy_pipelines.metrics import paired_bootstrap_ci  # noqa: E402
from experiments.accuracy_pipelines.ocr_scoring import (  # noqa: E402
    per_caption_rows, score_caption_observations)


def _candidate_name(path: pathlib.Path) -> str:
    """Tên cấu hình đọc từ TÊN TỆP, bỏ hậu tố `.json`.

    Vì sao không lấy từ trường trong tệp: bảng điểm của sweep là tệp phẳng
    (`{...}` không có `name`), còn `baseline`/`candidate` trong CI phải trỏ được
    về đúng tệp đã chấm — tên tệp là danh tính duy nhất luôn có mặt.
    """
    return path.stem


def _segments(document: dict) -> list[dict]:
    segments = document.get("segments", document.get("source_segments"))
    if not isinstance(segments, list):
        raise SystemExit("hypothesis JSON has no segments/source_segments list")
    return segments


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Score an ASR JSON against the saved OCR caption observations")
    parser.add_argument("reference", type=pathlib.Path,
                        help="pipeline JSON containing metadata.caption_observations")
    parser.add_argument("hypothesis", type=pathlib.Path,
                        help="ASR JSON containing segments or source_segments")
    parser.add_argument("--split", choices=("dev", "test"),
                        help="score only the frozen evaluation split")
    parser.add_argument("--output", type=pathlib.Path,
                        help="optional path to save the score JSON")
    #: So THEO CẶP với một baseline. Vì sao cần cờ riêng: một bảng điểm đơn lẻ
    #: không trả lời được "cấu hình này có HƠN không", và trên dev mọi biến thể
    #: decode nằm sát nhau (prevtrue -0,004) — không có CI thì không phân biệt
    #: được cải thiện thật với nhiễu.
    parser.add_argument("--paired-baseline", type=pathlib.Path,
                        help="score a paired CI of timed mean CER against this baseline JSON")
    parser.add_argument("--ci-output", type=pathlib.Path,
                        help="optional path to save the paired CI JSON")
    parser.add_argument("--resamples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261019)
    args = parser.parse_args(argv)
    try:
        from opencc import OpenCC
    except ImportError:
        parser.error("install evaluation dependency: pip install opencc-python-reimplemented==0.1.7")
    reference_bytes = args.reference.read_bytes()
    reference = json.loads(reference_bytes)
    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    observations = reference.get("metadata", {}).get("caption_observations")
    segments = _segments(hypothesis)
    if not isinstance(observations, list):
        parser.error("reference JSON has no metadata.caption_observations list")
    if args.split:
        observations = [row for row in observations
                        if row.get("evaluation_split") == args.split]
        if not observations:
            parser.error(f"reference has no {args.split!r} evaluation split")
    converter = OpenCC("t2s")
    score = score_caption_observations(observations, segments, opencc=converter)
    score["evaluation_split"] = args.split or "all"
    score["reference_provenance"] = {
        "dataset_id": reference.get("dataset_id"),
        "version": reference.get("version"),
        "sha256": hashlib.sha256(reference_bytes).hexdigest(),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(score, ensure_ascii=False, indent=2))

    if args.paired_baseline:
        baseline = json.loads(args.paired_baseline.read_text(encoding="utf-8"))
        # CÙNG danh sách `observations` cho cả hai vế: đó là điều kiện của phép so
        # theo cặp (cùng caption, cùng cửa sổ ±2 s, cùng dung sai).
        baseline_rows = per_caption_rows(observations, _segments(baseline),
                                         opencc=converter)
        candidate_rows = per_caption_rows(observations, segments, opencc=converter)
        if len(baseline_rows) != len(candidate_rows):
            raise SystemExit("paired CI needs the same scored captions for both sides")
        deltas = [candidate["timed"]["cer"] - base["timed"]["cer"]
                  for candidate, base in zip(candidate_rows, baseline_rows)]
        delta_mean, ci95 = paired_bootstrap_ci(deltas, resamples=args.resamples,
                                               seed=args.seed)
        paired = {
            "baseline": _candidate_name(args.paired_baseline),
            "candidate": _candidate_name(args.hypothesis),
            "split": args.split or "all",
            "metric": ("paired timed mean per-caption CER; negative delta is better "
                       "than the baseline"),
            "delta_mean_cer": delta_mean,
            "ci95": list(ci95),
            "resamples": args.resamples,
            "seed": args.seed,
            "identical_per_caption": all(delta == 0.0 for delta in deltas),
            "reference_provenance": score["reference_provenance"],
        }
        if args.ci_output:
            args.ci_output.parent.mkdir(parents=True, exist_ok=True)
            args.ci_output.write_text(json.dumps(paired, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
        print(json.dumps(paired, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
