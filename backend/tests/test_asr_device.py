"""`device_and_compute_type` — cặp (thiết bị, kiểu số) của ASR.

Vì sao có bài này: image Docker không có GPU chết ở job `asr` đầu tiên với
`CUDA failed ... driver version is insufficient` — mặc định `cuda` và không có
đường đổi. Và đổi thiết bị mà không đổi `compute_type` thì chỉ đổi từ lỗi này
sang lỗi khác, nên hai vế phải được ghim CÙNG NHAU.
"""
import pytest

from app.adapters.asr.faster_whisper import device_and_compute_type
from app.registry import EngineSpec


def spec(**opts) -> EngineSpec:
    return EngineSpec(id="fw-large-v3-turbo", label="FW turbo", kind="asr",
                      runtime="inprocess", model_ref="large-v3-turbo", vram_mb=1600,
                      langs=("zh", "en"), capabilities={}, opts=dict(opts))


def test_default_is_cuda_with_float16_as_shipped(monkeypatch):
    monkeypatch.delenv("PHUDE_ASR_DEVICE", raising=False)
    assert device_and_compute_type(spec(compute_type="int8_float16")) == (
        "cuda", "int8_float16")


def test_env_switches_to_cpu_and_downgrades_float16(monkeypatch):
    """`int8_float16` trên CPU là lỗi của CTranslate2, không phải một lựa chọn."""
    monkeypatch.setenv("PHUDE_ASR_DEVICE", "cpu")
    assert device_and_compute_type(spec(compute_type="int8_float16")) == ("cpu", "int8")


def test_cpu_keeps_a_non_float16_compute_type(monkeypatch):
    monkeypatch.setenv("PHUDE_ASR_DEVICE", "cpu")
    assert device_and_compute_type(spec(compute_type="float32")) == ("cpu", "float32")


def test_explicit_argument_beats_the_environment(monkeypatch):
    monkeypatch.setenv("PHUDE_ASR_DEVICE", "cpu")
    assert device_and_compute_type(spec(), device="cuda")[0] == "cuda"


def test_engine_constructor_reads_the_same_knob(monkeypatch):
    """Không nạp model: chỉ kiểm cặp đã chọn nằm trên instance."""
    from app.adapters.asr.faster_whisper import FasterWhisperEngine

    monkeypatch.setenv("PHUDE_ASR_DEVICE", "cpu")
    engine = FasterWhisperEngine(spec(compute_type="int8_float16"))
    assert (engine.device, engine.compute_type) == ("cpu", "int8")


@pytest.mark.parametrize("value", ["", None])
def test_empty_env_falls_back_to_cuda(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("PHUDE_ASR_DEVICE", raising=False)
    else:
        monkeypatch.setenv("PHUDE_ASR_DEVICE", value)
    assert device_and_compute_type(spec())[0] == "cuda"
