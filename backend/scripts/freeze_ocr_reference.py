from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from experiments.accuracy_pipelines.ocr_scoring import _normalize


SOURCE = pathlib.Path(
    "data/experiments/accuracy-pipelines/20261014-caption-ocr-observations/caption_ocr.json"
)
WATERMARK_TERMS = ("想想工作室", "想法工作室", "bilibili")
FRAME_VERIFIED = {
    26: {
        "text": "一定可以把成本压在2,000以内",
        "detail": "The two successive burned-in caption states are visible in frame_44_2s.jpg (一定可以把成本) and frame_44_8s.jpg (压在2,000以内). Together they complete this speech/caption segment.",
    },
    64: {
        "text": "还会吐泡泡",
        "detail": "Subtitle read directly from frame_1335s.png (video time about 133.5s); original OCR duplicated 泡.",
    },
    57: {
        "text": "交给我们您放心",
        "detail": "Subtitle read directly from frame_row57.png (video time 116.55s); original OCR duplicated 给.",
    },
    82: {
        "text": "所以为什么是榕树女神啊",
        "detail": "Subtitle read directly from frame_row82.png (video time 220.27s); the visible character is 神, not the original OCR's 孩.",
    },
}
MODEL_SUPPORTED_CANDIDATES = {
    27: {
        "model_support": ["SenseVoice", "ElevenLabs Scribe"],
        "model_support_outputs": {
            "SenseVoice": "你直接卖字儿多少钱",
            "ElevenLabs Scribe": "字儿多少钱啊",
        },
        "model_support_note": "These ASR transcripts were reported by the user. Agreement with OCR is corroboration between automated systems, not proof from listening; retain verification status as unverified.",
    },
    69: {
        "model_support": ["SenseVoice", "ElevenLabs Scribe"],
        "model_support_outputs": {
            "SenseVoice": "没想到还是卷起来了",
            "ElevenLabs Scribe": "没想到还是卷起来了",
        },
        "model_support_note": "User reports an opening sound effect overlapping the speech. These ASR transcripts are corroboration, not proof from listening; retain verification status as unverified.",
    },
}
FRAME_DENSITY_AUDIT = {
    index: "Midpoint frame visibly matches the original OCR phrase. Start/end samples show neighboring caption states at cue boundaries; no added or missing text was evident in the reviewed caption."
    for index in (3, 5, 38, 43, 47, 48, 56, 68, 78)
}
FRAME_REPEAT_AUDIT = {
    13: "Frame at 21.39s confirms the repeated zeros are part of the displayed amount 2,000; no edit.",
    14: "Frame at 26.71s confirms the repeated sevens are part of the displayed amount 187,712; no edit.",
    24: "Frame at 41.78s confirms the repeated zeros are part of the displayed amount 2,000; no edit.",
    25: "Frame at 43.02s confirms the repeated zeros are part of the displayed amount 100; no edit.",
    40: "Frame at 70.83s visibly reads 画画; lexical repetition is intentional, no edit.",
    49: "Frame at 102.43s visibly reads 处处; lexical repetition is intentional, no edit.",
    51: "Frame at 107.24s visibly reads 指指点点; lexical repetition is intentional, no edit.",
    57: "Frame at 116.55s visibly reads 交给我们您放心; source OCR's doubled 给 is extra and is corrected.",
    64: "Frame at 133.5s visibly reads 还会吐泡泡; source OCR's third 泡 is extra and is corrected.",
    65: "Frame at 143.24s visibly reads 画画; lexical repetition is intentional, no edit.",
    79: "Frame at 212.53s visibly reads 角角落落; lexical repetition is intentional, no edit.",
}


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze the reviewed OCR caption reference v3 with its frame audit.")
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path(
            "backend/experiments/accuracy_pipelines/references/ocr-caption-reference-v3.json"
        ),
    )
    args = parser.parse_args()
    source_path = ROOT_DIR / SOURCE
    source = json.loads(source_path.read_text(encoding="utf-8"))
    observations = source["metadata"]["caption_observations"]
    included: list[dict] = []
    excluded: list[dict] = []
    for row in observations:
        raw_ocr = str(row.get("ocr", ""))
        if any(term.casefold() in raw_ocr.casefold() for term in WATERMARK_TERMS):
            excluded.append({
                **row,
                "source_ocr": raw_ocr,
                "exclusion": "persistent channel watermark, not spoken subtitle",
                "evidence": "video_frame",
                "evidence_detail": "Visible as a fixed top-right overlay in frame_250s.png; excluded from speech scoring.",
            })
            continue

        reference = FRAME_VERIFIED.get(int(row["i"]))
        reference_text = reference["text"] if reference else raw_ocr
        if len(_normalize(reference_text)) < 4:
            excluded.append({
                **row,
                "source_ocr": raw_ocr,
                "exclusion": "OCR text shorter than four normalized characters; not scoreable under the fixed retrieval protocol",
                "evidence": "original_ocr",
                "evidence_detail": "Excluded by the scorer's predeclared minimum-reference-length rule.",
            })
            continue

        entry = {
            **row,
            "source_ocr": raw_ocr,
            "ocr": reference_text,
            "evidence": "video_frame" if reference else "original_ocr",
            "evidence_detail": (
                reference["detail"] if reference else
                "Preserved from the original OCR observation; not independently confirmed against audio or frame."
            ),
        }
        entry.update(MODEL_SUPPORTED_CANDIDATES.get(int(row["i"]), {}))
        if int(row["i"]) in MODEL_SUPPORTED_CANDIDATES:
            entry["verification_status"] = "unverified"
        if int(row["i"]) in FRAME_DENSITY_AUDIT:
            start, end = float(row["start"]), float(row["end"])
            entry["evidence"] = "original_ocr_and_video_frame_scan"
            entry["evidence_detail"] = "Original OCR was unchanged; the low-density caption was checked in frames at its start, midpoint, and end. " + FRAME_DENSITY_AUDIT[int(row["i"])]
            entry["verification_status"] = "frame_checked_no_edit"
            entry["frame_audit"] = {
                "sample_positions": ["start", "middle", "end"],
                "sample_times_s": [round(start + 0.05, 3), round((start + end) / 2, 3), round(end - 0.05, 3)],
                "assessment": FRAME_DENSITY_AUDIT[int(row["i"])],
            }
        if int(row["i"]) in FRAME_VERIFIED:
            entry["verification_status"] = "frame_checked_edit"
            entry["frame_audit"] = {
                "sample_positions": (
                    ["caption_state_1", "caption_state_2"]
                    if int(row["i"]) == 26 else ["middle"]
                ),
                "sample_times_s": {
                    26: [44.2, 44.8], 57: [116.55],
                    64: [133.5], 82: [220.27],
                }[int(row["i"])],
                "assessment": FRAME_VERIFIED[int(row["i"])]["detail"],
            }
        if int(row["i"]) in FRAME_REPEAT_AUDIT and int(row["i"]) not in FRAME_VERIFIED:
            entry["evidence"] = "original_ocr_and_video_frame_repeat_scan"
            entry["evidence_detail"] = FRAME_REPEAT_AUDIT[int(row["i"])]
            entry["verification_status"] = "frame_checked_no_edit"
            entry["frame_audit"] = {
                "sample_positions": ["middle"],
                "sample_times_s": [{
                    13: 21.39, 14: 26.71, 24: 41.78, 25: 43.02,
                    40: 70.83, 49: 102.43, 51: 107.24, 65: 143.24, 79: 212.53,
                }[int(row["i"])]],
                "assessment": FRAME_REPEAT_AUDIT[int(row["i"])],
            }
        included.append(entry)

    density_rows = [
        {
            "i": int(row["i"]),
            "chars": len(_normalize(row["ocr"])),
            "duration_seconds": float(row["end"]) - float(row["start"]),
        }
        for row in included
    ]
    for row in density_rows:
        row["chars_per_second"] = row["chars"] / row["duration_seconds"]
    ordered_density = sorted(density_rows, key=lambda row: (row["chars_per_second"], row["i"]))
    cutoff = ordered_density[math.ceil(0.10 * len(ordered_density)) - 1]["chars_per_second"]
    flagged_indices = sorted(row["i"] for row in ordered_density if row["chars_per_second"] <= cutoff)
    row_26 = next(row for row in included if int(row["i"]) == 26)
    row_26_source_chars = len(_normalize(str(row_26["source_ocr"])))
    row_26_source_density = row_26_source_chars / (
        float(row_26["end"]) - float(row_26["start"])
    )
    original_density_rows = [
        row_26_source_density if int(row["i"]) == 26 else row["chars_per_second"]
        for row in density_rows
    ]
    original_cutoff = sorted(original_density_rows)[math.ceil(0.10 * len(original_density_rows)) - 1]

    result = {
        "dataset_id": "ocr-caption-reference-v2",
        "version": 3,
        "metadata": {
            "source_media": "data/media/8f4b5304daf42569.mp4",
            "source_observations": SOURCE.as_posix(),
            "source_sha256": sha256(source_path),
            "created_date": "2026-10-15",
            "normalization_for_inclusion": "NFKC; exclude Unicode punctuation and whitespace; require at least four characters",
            "scoring_normalization": "OpenCC t2s; NFKC; strip whitespace and Unicode punctuation",
            "scoring_protocol": "For each caption midpoint, concatenate ASR segments intersecting ±2.0 seconds; choose best substring within reference length ±3 characters.",
            "included_count": len(included),
            "excluded_count": len(excluded),
            "evidence_policy": "Only frame/audio-supported evidence may change reference text. Unchanged OCR rows without a frame audit remain unverified. ASR output is never used as reference-edit evidence.",
            "ocr_density_scan": {
                "population": len(density_rows),
                "character_count_normalization": "NFKC; strip Unicode punctuation and whitespace",
                "metric": "normalized OCR characters per caption duration second",
                "percentile": 10,
                "threshold_method": "nearest_rank; flag values <= P10",
                "threshold_chars_per_second": round(cutoff, 6),
                "flagged_count": len(flagged_indices),
                "flagged_indices": flagged_indices,
                "review": "The nine flagged rows were inspected at start, midpoint, and end frames; their midpoint images matched original OCR and no text edits were made. This audit only validates these nine rows and does not establish that the full reference is complete or OCR-error-free.",
                "row_26_original_ocr_sensitivity": {
                    "source_ocr": row_26["source_ocr"],
                    "chars": row_26_source_chars,
                    "chars_per_second": round(row_26_source_density, 6),
                    "p10_threshold_chars_per_second": round(original_cutoff, 6),
                    "would_be_flagged_at_p10": row_26_source_density <= original_cutoff,
                },
            },
            "repeated_character_scan": {
                "population": len(included),
                "source_text_scanned": "source_ocr",
                "normalization": "NFKC; strip Unicode punctuation and whitespace",
                "rule": "inspect every consecutive repeated-character run of length 2 or more",
                "flagged_indices": sorted(FRAME_REPEAT_AUDIT),
                "frame_checked_indices": sorted(FRAME_REPEAT_AUDIT),
                "review": "All repeated-character candidates were frame-checked. Numeric runs and lexical reduplication matched the subtitle; the duplicated OCR characters in rows 57 and 64 were corrected from frame evidence.",
            },
            "caption_observations": included,
        },
        "excluded_observations": excluded,
    }
    output_path = ROOT_DIR / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output.as_posix(), "included": len(included),
                      "excluded": len(excluded), "sha256": sha256(output_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
