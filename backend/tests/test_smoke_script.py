"""Hợp đồng của `scripts/smoke_asr.py` (R17, R60, R62/R68).

Script này tải model ~1,6 GB và cần GPU nên KHÔNG thuộc bộ pytest ⇒ nó không có
RED kiểu "chạy script rồi đỏ". Hai thứ nó PHẢI làm thì vẫn kiểm được mà không
cần model:

* R17 · ép UTF-8 cho stdout trước khi in bất cứ thứ gì (console Windows cp1252
  + chuỗi tiếng Việt/Trung = `UnicodeEncodeError` ngay lần chạy thật đầu tiên).
* R60 · đây là chỗ gọi `FasterWhisperEngine` **thứ hai** (cùng họ với
  `main.py:_engine_factory`) và nó từng thiếu `download_root` ⇒ model rơi vào
  cache mặc định trên ổ C:.
* R62/R68 · **0 đoạn KHÔNG được tính là đạt.** Script này là thứ được dùng để
  nghiệm thu bước 5 ("ít nhất 1 đoạn có start/end"), mà bản trước in
  `[3/3] 0 đoạn ... RTF = nan` rồi vẫn in `OK` và thoát 0 — tức là nó báo xanh
  cho đúng thất bại mà nó tồn tại để bắt. Bài ở dưới lái `main()` bằng một
  engine giả và đòi mã thoát KHÁC 0, không có dòng `OK`.
"""
from __future__ import annotations

import importlib.util
import io
import os
import pathlib

import pytest

from app.domain.models import Segment

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


# ---------------------------------------------------------------------------
# R62/R68 — 0 đoạn là THẤT BẠI, không phải "OK"
# ---------------------------------------------------------------------------

class _StubEngine:
    """Engine giả: `transcribe()` trả ĐÚNG danh sách đoạn được dặn.

    Không nạp weight nào, nên bài này kiểm được phán quyết của `main()` mà
    không cần GPU — đúng thứ đã hỏng ở vòng trước (`0 đoạn` + `OK` + thoát 0).
    """

    def __init__(self, segments):
        self.segments = list(segments)
        self.loaded = False
        self.released = False

    def _load(self):
        self.loaded = True

    def transcribe(self, audio_path, lang):
        return list(self.segments)

    def release(self):
        self.released = True


def _drive_main(monkeypatch, tmp_path, segments):
    """Lái `main()` tới hết đường bóc băng, không chạm model thật."""
    from app.registry import EngineSpec

    smoke = _load_smoke()
    audio = tmp_path / "silence.wav"
    audio.write_bytes(b"RIFF")
    monkeypatch.setattr(smoke.sys, "argv", ["smoke_asr.py", str(audio), "zh", "fw-tiny"])

    engine = _StubEngine(segments)
    monkeypatch.setattr(smoke, "build_engine", lambda spec: engine)
    # `main()` import hai hàm này BÊN TRONG thân hàm, nên phải vá ở module nguồn.
    monkeypatch.setattr("app.adapters.registry_file.load_registry", lambda: [])
    monkeypatch.setattr("app.registry.by_id", lambda specs, engine_id: EngineSpec(
        id=engine_id, label="FW tiny", kind="asr", runtime="inprocess",
        model_ref="tiny", vram_mb=200, langs=("zh", "en"),
        capabilities={}, opts={},
    ))
    return smoke, engine


def test_smoke_script_fails_loudly_with_zero_segments(monkeypatch, tmp_path, capsys):
    """R62/R68 · đúng ca đã lọt: 0 đoạn, RTF = nan, và script vẫn báo đạt."""
    smoke, engine = _drive_main(monkeypatch, tmp_path, segments=[])
    code = smoke.main()
    out = capsys.readouterr().out

    assert code != 0, (
        "0 đoạn phải làm smoke test THẤT BẠI (mã thoát khác 0); bản trước trả 0 "
        "và in OK, nên nó không cưỡng chế được nghiệm thu 'ít nhất 1 đoạn'"
    )
    assert "OK" not in out, f"0 đoạn thì KHÔNG được có dòng OK:\n{out}"
    assert "0 đoạn" in out or "không sinh" in out, (
        f"phải nói rõ vì sao hỏng:\n{out}"
    )
    assert engine.released, "engine vẫn phải được giải phóng trên nhánh hỏng"


def test_smoke_script_still_reports_ok_with_at_least_one_segment(monkeypatch, tmp_path, capsys):
    """Chiều ngược lại: có đoạn thật thì vẫn `OK` + thoát 0."""
    segments = [Segment(i=0, start=0.0, end=2.5, text="xin chào")]
    smoke, _engine = _drive_main(monkeypatch, tmp_path, segments=segments)
    code = smoke.main()
    out = capsys.readouterr().out

    assert code == 0, f"có đoạn thì phải thoát 0:\n{out}"
    assert "OK" in out, f"có đoạn thì phải có dòng OK:\n{out}"
    assert "1 đoạn" in out, f"phải in số đoạn thật:\n{out}"
