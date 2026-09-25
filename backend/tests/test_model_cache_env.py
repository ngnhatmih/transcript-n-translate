"""R64 — CHỈ kiểm chứng: Task 15 đã ghim cache model bằng biến môi trường.

`app/config.py:HF_HOME` là một **hằng số Python**. Thứ `huggingface_hub` đọc là
**biến môi trường**, và nó đọc **ngay lúc import** — mà `huggingface_hub` được
nạp gián tiếp khi `faster_whisper` được import trong `_load()`. Nên
"đã truyền `download_root=`" **một mình chưa đủ**: biến phải được đặt TRƯỚC.

Ba mệnh đề được ghim ở đây:
1. `_prepare_local_model_caches()` đặt **cả** `HF_HOME` lẫn `MODELSCOPE_CACHE`,
   và `MODELSCOPE_CACHE` nằm TRONG `HF_HOME`.
2. `setdefault` — không ghi đè lựa chọn của người dùng.
3. Cơ chế "đọc lúc import" là THẬT: một tiến trình mới, chỉ có `HF_HOME`, thấy
   `huggingface_hub.constants.HF_HUB_CACHE` trỏ vào đó.

(3) là bài duy nhất ở đây cần tiến trình con; `tests/test_ingest.py` đã làm đúng
việc đó nên không có gì mới về hạ tầng.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from app.config import HF_HOME as CONFIG_HF_HOME


def _clean(monkeypatch):
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("MODELSCOPE_CACHE", raising=False)


def test_prepare_local_model_caches_sets_both_variables(monkeypatch):
    from app.main import _prepare_local_model_caches

    _clean(monkeypatch)
    _prepare_local_model_caches()

    assert os.environ["HF_HOME"] == CONFIG_HF_HOME
    assert os.environ["MODELSCOPE_CACHE"] == str(pathlib.Path(CONFIG_HF_HOME) / "modelscope")


def test_prepare_local_model_caches_does_not_override_the_user(monkeypatch, tmp_path):
    from app.main import _prepare_local_model_caches

    chosen = tmp_path / "chosen"
    assert str(chosen) != CONFIG_HF_HOME, (
        "phải chọn đường dẫn KHÁC mặc định: nếu trùng thì phép kiểm 'không ghi "
        "đè' xanh vì lý do sai (config.HF_HOME được đọc sau setenv)"
    )
    _clean(monkeypatch)
    monkeypatch.setenv("HF_HOME", str(chosen))
    monkeypatch.setenv("MODELSCOPE_CACHE", str(chosen / "ms"))

    _prepare_local_model_caches()

    assert os.environ["HF_HOME"] == str(chosen)
    assert os.environ["MODELSCOPE_CACHE"] == str(chosen / "ms")


def test_both_call_sites_agree_on_the_cache_root(monkeypatch):
    """Hai chỗ gọi (`main.py` và `scripts/smoke_asr.py`) phải cho CÙNG kết quả.

    Đây là bài học R28: "hai bên dùng cùng quy ước" là khẳng định phải kiểm bằng
    test LIÊN MODULE, không phải bằng cách đọc hai đoạn code cạnh nhau. R60 sinh
    ra đúng vì một chỗ được sửa còn chỗ kia thì không.
    """
    import importlib.util

    from app.main import _prepare_local_model_caches

    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "smoke_asr.py"
    assert path.exists(), "brief Task 20 yêu cầu backend/scripts/smoke_asr.py"
    spec = importlib.util.spec_from_file_location("smoke_asr_cross_check", path)
    assert spec is not None and spec.loader is not None
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)

    _clean(monkeypatch)
    _prepare_local_model_caches()
    from_main = (os.environ["HF_HOME"], os.environ["MODELSCOPE_CACHE"])

    _clean(monkeypatch)
    root = smoke.prepare_model_cache_env()
    from_script = (os.environ["HF_HOME"], os.environ["MODELSCOPE_CACHE"])

    assert from_script == from_main, (
        "hai chỗ gọi cache model đã trôi khỏi nhau: "
        f"{from_script!r} != {from_main!r}"
    )
    assert root == from_main[0]


def test_huggingface_hub_reads_hf_home_at_import_time(tmp_path):
    """Cơ chế thật, đo bằng một tiến trình mới: chỉ có `HF_HOME`, không gì khác."""
    pytest.importorskip("huggingface_hub")

    root = tmp_path / "hf-home"
    env = dict(os.environ, HF_HOME=str(root))
    env.pop("HF_HUB_CACHE", None)  # biến này sẽ thắng HF_HOME nếu còn sót lại
    child = "import huggingface_hub.constants as c; print(c.HF_HUB_CACHE)"

    result = subprocess.run([sys.executable, "-B", "-c", child],
                            capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr

    cache = pathlib.Path(result.stdout.strip())
    assert cache == root / "hub", (
        "huggingface_hub phải đọc HF_HOME lúc import; nếu không thì "
        "`download_root=` một mình vẫn để model về ổ C:"
    )
