from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_DIR / "scripts" / "freeze_ocr_reference.py"
V3_SHA256 = "8e1c948a8ad33a4f44bd5b2df6c26687756b78c309b5ee992d0a261035fd6e67"
HISTORICAL_V2_SHA256 = "9c8bd23a80523a1fa79745f16557744c8f1a1d6c1ae612abcc0fdbc4b9f26b8e"


def test_freeze_records_density_scan_and_model_support(tmp_path: Path) -> None:
    output = tmp_path / "reference.json"
    subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--output", str(output)],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(output.read_text(encoding="utf-8"))
    metadata = document["metadata"]
    scan = metadata["ocr_density_scan"]
    repeats = metadata["repeated_character_scan"]

    assert scan["population"] == 84
    assert scan["percentile"] == 10
    assert scan["threshold_method"] == "nearest_rank; flag values <= P10"
    assert scan["flagged_indices"] == [3, 5, 38, 43, 47, 48, 56, 68, 78]
    assert repeats["flagged_indices"] == [13, 14, 24, 25, 40, 49, 51, 57, 64, 65, 79]
    assert repeats["frame_checked_indices"] == repeats["flagged_indices"]
    rows = {row["i"]: row for row in metadata["caption_observations"]}
    for index in scan["flagged_indices"]:
        assert rows[index]["frame_audit"]["sample_positions"] == ["start", "middle", "end"]
        assert rows[index]["verification_status"] == "frame_checked_no_edit"

    assert rows[26]["source_ocr"] == "一定可以把成本"
    assert rows[26]["ocr"] == "一定可以把成本压在2,000以内"
    assert rows[26]["frame_audit"]["sample_times_s"] == [44.2, 44.8]
    assert rows[57]["source_ocr"] == "交给给我们您放心"
    assert rows[57]["ocr"] == "交给我们您放心"
    assert rows[57]["verification_status"] == "frame_checked_edit"
    assert rows[82]["source_ocr"] == "所以为什么是榕树女孩啊"
    assert rows[82]["ocr"] == "所以为什么是榕树女神啊"
    assert rows[82]["verification_status"] == "frame_checked_edit"
    original_scan = metadata["ocr_density_scan"]["row_26_original_ocr_sensitivity"]
    assert original_scan["chars_per_second"] == 4.216867
    assert original_scan["would_be_flagged_at_p10"] is False
    assert original_scan["p10_threshold_chars_per_second"] == 2.941176
    for index in (27, 69):
        assert rows[index]["ocr"] == rows[index]["source_ocr"]
        assert rows[index]["verification_status"] == "unverified"
        assert rows[index]["model_support"] == ["SenseVoice", "ElevenLabs Scribe"]


def test_freeze_v3_has_reproducible_identity_and_does_not_replace_v2(tmp_path: Path) -> None:
    """A version-only release must be byte-stable and leave the v2 artifact intact."""
    output = tmp_path / "reference-v3.json"
    second_output = tmp_path / "reference-v3-second-run.json"
    subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--output", str(output)],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--output", str(second_output)],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["dataset_id"] == "ocr-caption-reference-v2"
    assert document["version"] == 3
    assert hashlib.sha256(output.read_bytes()).hexdigest() == V3_SHA256
    assert output.read_bytes() == second_output.read_bytes()

    historical_v2 = (
        BACKEND_DIR.parent
        / "data/experiments/accuracy-pipelines/20261015-ocr-reference-v2/reference.json"
    )
    assert hashlib.sha256(historical_v2.read_bytes()).hexdigest() == HISTORICAL_V2_SHA256
