"""`registry.json` phải khai engine OCR — cùng khuôn với `asr` và `mt`.

Vì sao có bài này: ghi chú đầu `registry.json` nói rõ nó là NGUỒN SỰ THẬT DUY NHẤT, và
`GET /api/registry` là đường giao diện đọc. Một engine chỉ tồn tại trong mã (không có trong
tệp) thì giao diện không biết nó, và người dùng không chọn được nó.
"""
from __future__ import annotations

import json
import pathlib

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "registry.json"


def _doc() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_registry_co_khoa_ocr():
    assert "ocr" in _doc(), "phải có khoá `ocr` — cùng khuôn `asr`/`mt`"


def test_moi_entry_ocr_co_du_bon_khoa():
    for e in _doc()["ocr"]:
        for k in ("id", "label", "runtime", "opts"):
            assert k in e, f"entry {e.get('id')!r} thiếu khoá {k!r}"


def test_id_cua_engine_rapidocr_khop_voi_adapter():
    """`id` trong registry phải TRÙNG `RapidOCREngine.engine_id`.

    Lệch nhau thì chọn engine theo id sẽ không tìm thấy adapter, và lỗi chỉ lộ ra lúc chạy.
    """
    from app.adapters.ocr_rapidocr import RapidOCREngine

    ids = [e["id"] for e in _doc()["ocr"]]
    assert RapidOCREngine.engine_id in ids, (
        f"engine_id {RapidOCREngine.engine_id!r} không có trong registry: {ids}"
    )


def test_fps_mac_dinh_nam_trong_opts_chu_khong_hard_code():
    e = next(x for x in _doc()["ocr"] if x["id"] == "rapidocr")
    assert e["opts"].get("fps") == 2.0, (
        f"fps mặc định phải là DỮ LIỆU trong registry, đo được {e['opts'].get('fps')!r}"
    )
