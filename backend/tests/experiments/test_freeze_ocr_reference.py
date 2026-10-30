from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_DIR / "scripts" / "freeze_ocr_reference.py"
V4_SHA256 = "cc5c8aaa3cc2d886d141e75d917b2d64d211d99443b05c8a555c83e45a917818"
HISTORICAL_V2_SHA256 = "b95621e28f9708bcd89b9a6879979d370961eb119eeb7f53394bd73f08f8ee67"


def _sha256_chuan_hoa(path: Path) -> str:
    """sha256 cua NOI DUNG, sau khi dua xuong dong ve LF.

    🔴 VI SAO KHONG BAM THANG `path.read_bytes()` (do duoc, khong doan):

        $ git config --get core.autocrlf
        true
        $ git ls-files --eol .../ocr-caption-reference-v4.json
        i/lf    w/crlf  attr/
        $ git cat-file -s HEAD:backend/.../ocr-caption-reference-v4.json
        64241                       <- blob trong git, LF
        $ (Get-Item .../ocr-caption-reference-v4.json).Length
        65865                       <- working tree, CRLF

        $ diff /tmp/that.json /tmp/ref-z.json | grep -cE "^[<>]"
        3248                        <- "khac het 1624 dong"
        $ python -c "a=...replace(b'\r\n',b'\n'); b=...; print(a==b)"
        giong het sau khi chuan hoa: True
        sha256 that (LF): cc5c8aaa...
        sha256 sinh (LF): cc5c8aaa...

    NOI DUNG GIONG HET TUNG BYTE. Khac biet duy nhat la xuong dong: git luu LF
    (`i/lf`), `core.autocrlf=true` doi thanh CRLF khi checkout (`w/crlf`), nen
    file TREN DIA tren may Windows co 65 865 B con trong container Linux co
    64 241 B. `V4_SHA256` duoc tinh tren ban CRLF.

    Nghia la bai test cu ghim mot hash PHU THUOC CAU HINH GIT cua may checkout:
    no xanh tren Windows co `autocrlf=true` va do trong container Linux — cung
    mot noi dung, hai ket qua. Do la loi cua TEST, khong phai cua script: script
    tai lap dung tuyet doi, va chinh bai nay khang dinh dieu do o dong
    `output.read_bytes() == second_output.read_bytes()`.

    Chuan hoa ve LF truoc khi bam: hash ghim NOI DUNG, khong ghim cach checkout.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


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


def test_freeze_v4_has_reproducible_identity_and_does_not_replace_v2(tmp_path: Path) -> None:
    """A split-bearing release must be byte-stable and leave old artifacts intact."""
    output = tmp_path / "reference-v4.json"
    second_output = tmp_path / "reference-v4-second-run.json"
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
    assert document["version"] == 4
    assert _sha256_chuan_hoa(output) == V4_SHA256
    assert output.read_bytes() == second_output.read_bytes()

    historical_v2 = (
        BACKEND_DIR.parent
        / "data/experiments/accuracy-pipelines/20261015-ocr-reference-v2/reference.json"
    )
    assert _sha256_chuan_hoa(historical_v2) == HISTORICAL_V2_SHA256


def test_freeze_assigns_the_chronological_dev_test_split(tmp_path: Path) -> None:
    output = tmp_path / "reference-v4.json"
    subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--output", str(output)],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )

    document = json.loads(output.read_text(encoding="utf-8"))
    rows = document["metadata"]["caption_observations"]
    split = document["metadata"]["evaluation_split"]
    assert split == {
        "method": "chronological half split; first 42 scoreable captions are dev, last 42 are test",
        "dev_count": 42,
        "test_count": 42,
    }
    assert [row["evaluation_split"] for row in rows] == ["dev"] * 42 + ["test"] * 42
