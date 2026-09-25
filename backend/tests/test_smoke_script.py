"""Hợp đồng của `scripts/smoke_asr.py` (R17, R60).

Script này tải model ~1,6 GB và cần GPU nên KHÔNG thuộc bộ pytest ⇒ nó không có
RED kiểu "chạy script rồi đỏ". Hai thứ nó PHẢI làm thì vẫn kiểm được mà không
cần model:

* R17 · ép UTF-8 cho stdout trước khi in bất cứ thứ gì (console Windows cp1252
  + chuỗi tiếng Việt/Trung = `UnicodeEncodeError` ngay lần chạy thật đầu tiên).
* R60 · đây là chỗ gọi `FasterWhisperEngine` **thứ hai** (cùng họ với
  `main.py:_engine_factory`) và nó từng thiếu `download_root` ⇒ model rơi vào
  cache mặc định trên ổ C:.
"""
from __future__ import annotations

import importlib.util
import io
import os
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "smoke_asr.py"


def _load_smoke():
    assert SCRIPT.exists(), "brief Task 20 yêu cầu backend/scripts/smoke_asr.py"
    spec = importlib.util.spec_from_file_location("smoke_asr_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cp1252_console() -> io.TextIOWrapper:
    """Bắt chước console Windows: TextIOWrapper ghi ra buffer, mã hoá cp1252."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


# ---------------------------------------------------------------------------
# R17 — UTF-8 cho stdout
# ---------------------------------------------------------------------------

def test_console_without_the_fix_is_the_real_trap():
    """Chứng minh cái bẫy là THẬT, không phải lo xa: cp1252 không có `→`."""
    stream = _cp1252_console()
    with pytest.raises(UnicodeEncodeError):
        stream.write("→ nạp xong sau 12.3s")


def test_force_utf8_stdout_makes_vietnamese_printable():
    smoke = _load_smoke()
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")

    assert smoke.force_utf8_stdout(stream) is True
    stream.write("→ nạp xong sau 12.3s")
    stream.flush()

    assert "nạp xong" in raw.getvalue().decode("utf-8")


def test_force_utf8_stdout_replaces_unencodable_characters_instead_of_dying():
    """`errors="replace"`: ký tự không mã hoá được không được làm chết script."""
    smoke = _load_smoke()
    stream = _cp1252_console()
    with pytest.raises(UnicodeEncodeError):
        stream.write("\ud800")  # surrogate trần: utf-8 strict cũng từ chối

    smoke.force_utf8_stdout(stream)
    stream.write("\ud800")  # phải thành '?' thay vì ném


def test_main_forces_utf8_before_printing_the_usage_text(monkeypatch, capsys):
    """Thứ tự mới là điều quan trọng: ép TRƯỚC dòng `print` đầu tiên."""
    smoke = _load_smoke()
    calls: list[str] = []

    def spy(stream=None):
        calls.append("forced")
        return True

    monkeypatch.setattr(smoke, "force_utf8_stdout", spy)
    monkeypatch.setattr(smoke.sys, "argv", ["smoke_asr.py"])
    assert smoke.main() == 2
    assert calls == ["forced"], "main() phải ép UTF-8 trước khi in hướng dẫn"


# ---------------------------------------------------------------------------
# R60 — chỗ gọi thứ hai của FasterWhisperEngine
# ---------------------------------------------------------------------------

def test_prepare_model_cache_env_defaults_to_the_project_cache(monkeypatch):
    smoke = _load_smoke()
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("MODELSCOPE_CACHE", raising=False)

    from app.config import HF_HOME
    root = smoke.prepare_model_cache_env()

    assert root == HF_HOME, "mặc định phải lấy từ app.config, không bịa đường dẫn"
    assert os.environ["HF_HOME"] == HF_HOME
    assert os.environ["MODELSCOPE_CACHE"] == str(pathlib.Path(HF_HOME) / "modelscope")


def test_prepare_model_cache_env_respects_a_choice_made_by_the_user(monkeypatch, tmp_path):
    smoke = _load_smoke()
    # Đọc hằng số TRƯỚC khi đổi biến môi trường. Nếu để `app.config` được import
    # lần đầu SAU `monkeypatch.setenv`, thì `config.HF_HOME` sẽ chính là lựa chọn
    # của test và phép kiểm "không ghi đè" sẽ XANH vì lý do sai — đúng loại test
    # tự thoả mãn mà mutation M14 đã phát hiện.
    from app.config import HF_HOME as CONFIG_HF_HOME

    chosen = tmp_path / "my-models"
    assert str(chosen) != CONFIG_HF_HOME, (
        "phải chọn đường dẫn KHÁC mặc định, nếu không phép kiểm không nói lên gì"
    )
    monkeypatch.setenv("HF_HOME", str(chosen))
    monkeypatch.delenv("MODELSCOPE_CACHE", raising=False)

    assert smoke.prepare_model_cache_env() == str(chosen)
    assert os.environ["HF_HOME"] == str(chosen), "setdefault, không ghi đè"


def test_build_engine_passes_the_cache_as_download_root(monkeypatch, tmp_path):
    """Thiếu `download_root` thì model ~1,6 GB rơi vào cache mặc định ổ C:."""
    smoke = _load_smoke()
    chosen = tmp_path / "my-models"
    monkeypatch.setenv("HF_HOME", str(chosen))
    monkeypatch.delenv("MODELSCOPE_CACHE", raising=False)

    from app.registry import EngineSpec
    spec = EngineSpec(id="fw-large-v3-turbo", label="FW", kind="asr",
                      runtime="inprocess", model_ref="large-v3-turbo",
                      vram_mb=1600, langs=("zh", "en"), capabilities={}, opts={})

    engine = smoke.build_engine(spec)

    assert engine.download_root == str(chosen), (
        "smoke_asr.py là chỗ gọi THỨ HAI và cũng phải truyền download_root"
    )
