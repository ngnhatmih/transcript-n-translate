"""R72 · đường nạp model phải nạp runtime CUDA trước khi chạm CTranslate2.

Lỗi thật đã đo được trên đúng máy này (`scripts/smoke_asr.py`, model `tiny`,
torch 2.5.1+cu121, RTX 3070):

    RuntimeError: Library cublas64_12.dll is not found or cannot be loaded

Nguyên nhân: `ctranslate2` không kèm `cublas64_12.dll`; bản duy nhất trong venv
nằm ở `torch\\lib\\`, và thư mục đó chỉ vào được đường tìm DLL **khi torch được
nạp**. Đo A/B trong ba tiến trình mới (xem report Task 20, mục R72):

    from faster_whisper import WhisperModel           -> RuntimeError
    import torch; from faster_whisper import ...      -> OK

Nên phép kiểm ở đây chạy trong TIẾN TRÌNH MỚI và bắt đầu bằng việc xoá `torch`
khỏi `sys.modules`: nếu ai đó bỏ `ensure_cuda_runtime()` khỏi `_load()`, biến
`TORCH_WAS_LOADED_BEFORE_FW` quay về `False` và test ĐỎ — đúng cái đã xảy ra
ngoài đời thật.

Không import `faster_whisper` trong tiến trình pytest: cả file này chạy qua
`subprocess` (xem `test_asr_runtime_deps.py` để biết lý do).
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import textwrap

BACKEND = pathlib.Path(__file__).resolve().parents[1]
VENV_PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"

# Chạy trong tiến trình con. Cố ý KHÔNG import torch ở đầu.
_PROBE = textwrap.dedent(
    """
    import json, sys, types
    sys.modules.pop("torch", None)
    assert "torch" not in sys.modules, "tien trinh con phai bat dau KHONG co torch"

    # Bom mot module `faster_whisper` GIA vao sys.modules. Nho vay `_load()` di
    # dung nhanh THAT (`model_factory is None`) — nhanh duy nhat goi
    # `ensure_cuda_runtime()` — ma khong phai tai model.
    captured = {}


    def WhisperModel(model_ref, **kwargs):
        captured["torch_loaded_at_construction"] = "torch" in sys.modules
        captured["model_ref"] = model_ref
        captured["kwargs"] = {k: v for k, v in kwargs.items()}
        return object()


    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = WhisperModel
    sys.modules["faster_whisper"] = fake

    from app.adapters.asr.faster_whisper import FasterWhisperEngine
    from app.registry import EngineSpec

    spec = EngineSpec(id="fw-tiny", label="tiny", kind="asr", runtime="inprocess",
                      model_ref="tiny", vram_mb=200, langs=("zh", "en"),
                      capabilities={}, opts={"compute_type": "int8_float16"})

    engine = FasterWhisperEngine(spec)
    engine._load()
    captured["torch_loaded_after_load"] = "torch" in sys.modules
    print("PROBE" + json.dumps(captured))
    """
)


def _run_probe() -> dict:
    if not VENV_PYTHON.exists():
        import pytest
        pytest.skip(f"chưa có venv tại {VENV_PYTHON}")
    env = {"PYTHONPATH": str(BACKEND), "PYTHONIOENCODING": "utf-8",
           "SYSTEMROOT": "C:\\Windows", "PATH": ""}
    proc = subprocess.run(  # noqa: S603 - đường dẫn cố định, không có shell
        [str(VENV_PYTHON), "-B", "-c", _PROBE],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"probe nổ:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    line = next(line for line in proc.stdout.splitlines()
                if line.startswith("PROBE"))
    return json.loads(line[len("PROBE"):]), proc.stdout


def test_load_preloads_torch_before_constructing_the_model():
    """R72 · trên nhánh THẬT của `_load()`, torch phải đã được nạp.

    Phép kiểm này ĐỎ nếu `ensure_cuda_runtime()` bị bỏ khỏi `_load()`: tiến trình
    con đã xoá torch khỏi `sys.modules` và không có gì khác nạp lại nó, nên
    `torch_loaded_at_construction` quay về `False` — đúng trạng thái đã sinh ra
    RuntimeError ngoài đời thật.
    """
    captured, stdout = _run_probe()
    assert captured["torch_loaded_at_construction"] is True, (
        "FasterWhisperEngine._load() phải nạp torch TRƯỚC khi CTranslate2 chạm "
        "GPU — thiếu bước đó thì lần `encode()` đầu tiên nổ "
        "'Library cublas64_12.dll is not found or cannot be loaded'\n"
        f"stdout con: {stdout}"
    )


def test_load_still_builds_the_model_with_the_registry_settings():
    """Chống hồi quy ngược: thêm bước nạp DLL không được đổi tham số dựng model."""
    captured, _ = _run_probe()
    assert captured["model_ref"] == "tiny"
    assert captured["kwargs"]["device"] == "cuda"
    assert captured["kwargs"]["compute_type"] == "int8_float16"
