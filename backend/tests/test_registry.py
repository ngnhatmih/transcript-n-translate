from __future__ import annotations

import json

import pytest

from app.adapters.registry_file import load_registry
from app.registry import by_id, estimate_vram_mb, of_kind


@pytest.fixture()
def specs(tmp_path):
    data = {
        "asr": [
            {"id": "fw-large-v3-turbo", "label": "Faster-Whisper large-v3-turbo",
             "runtime": "inprocess", "model_ref": "large-v3-turbo", "vram_mb": 1600,
             "langs": ["zh", "en"],
             "capabilities": {"timestamps": True, "word_timestamps": True,
                              "confidence": True, "emotion": False},
             "opts": {"batch_size": 8}},
            {"id": "sensevoice-small", "label": "SenseVoice-Small",
             "runtime": "inprocess", "model_ref": "iic/SenseVoiceSmall", "vram_mb": 1000,
             "langs": ["zh", "yue", "en", "ja", "ko"],
             "capabilities": {"timestamps": True, "word_timestamps": False,
                              "confidence": False, "emotion": True},
             "opts": {}},
        ],
        "mt": [
            {"id": "qwen2.5-7b", "label": "Qwen2.5-7B", "runtime": "ollama",
             "model_ref": "qwen2.5:7b-instruct-q4_K_M", "vram_mb": 5200,
             "langs": ["zh", "en"],
             "capabilities": {"glossary_prompt": True, "chimera": False},
             "opts": {}},
        ],
    }
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_registry(p)


def test_loads_all_kinds(specs):
    assert len(specs) == 3
    assert {s.kind for s in specs} == {"asr", "mt"}


def test_of_kind_filters(specs):
    assert [s.id for s in of_kind(specs, "asr")] == ["fw-large-v3-turbo", "sensevoice-small"]


def test_by_id_returns_spec_and_raises_on_unknown(specs):
    assert by_id(specs, "sensevoice-small").vram_mb == 1000
    with pytest.raises(KeyError):
        by_id(specs, "khong-co")


def test_capabilities_and_opts_survive_json_roundtrip(specs):
    fw = by_id(specs, "fw-large-v3-turbo")
    assert fw.capabilities["word_timestamps"] is True
    assert fw.opts["batch_size"] == 8


def test_spec_is_frozen_so_a_job_cannot_mutate_shared_config(specs):
    fw = by_id(specs, "fw-large-v3-turbo")
    with pytest.raises(Exception):
        fw.vram_mb = 1  # type: ignore[misc]


def test_estimate_vram_sums_only_requested(specs):
    assert estimate_vram_mb(specs, ["fw-large-v3-turbo"]) == 1600
    assert estimate_vram_mb(specs, ["fw-large-v3-turbo", "qwen2.5-7b"]) == 6800


def test_shipped_registry_file_is_valid():
    specs = load_registry()          # dùng đường dẫn mặc định từ config
    ids = {s.id for s in specs}
    assert "fw-large-v3-turbo" in ids
    assert "sensevoice-small" in ids
    assert all(s.phase_key.startswith(("asr:", "mt:")) for s in specs)
    # Moonshine KHÔNG được có mặt: nó không sinh timestamp (spec §6)
    assert not any("moonshine" in s.id.lower() for s in specs)
