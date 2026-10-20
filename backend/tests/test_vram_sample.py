"""Đo VRAM của `scripts/smoke_echo_guard.py` — phần THUẦN và phần CỜ TẮT.

Vì sao có tệp này
    Lượt đo trước báo "peak 6830 MiB, headroom 1362, steady ~6433, model 100% GPU"
    mà KHÔNG tệp nào trên đĩa chứa những số đó. Phép đo mới ghi từng mẫu
    `nvidia-smi memory.used` vào artifact, để con số trích dẫn được. Hai thứ dưới
    đây phải đúng trước khi tin bất kỳ con số nào của lượt chạy thật:

    (a) cách biến dãy mẫu thành `{idle, peak, steady, samples}` — ghim bằng mảng
        GIẢ, không GPU: nền phẳng rồi bàn ổn định, một gai đơn lẻ, và mảng rỗng;
    (b) cờ `--sample-vram` TẮT thì artifact KHÔNG có khoá `vram` và không có lời
        gọi `nvidia-smi` nào — đường mặc định của driver phải giữ nguyên.

Vì sao không có bài nào cần GPU hay mạng
    Hàm `summarize_vram` chỉ nhận một dãy số nguyên. Bài (b) dựng `run_one` với
    engine GIẢ và `_loaded_models` giả, nên nó chạy được trên máy không có
    Ollama; `_gpu_used_mib`/`_smi_mib` bị thay bằng một hàm NÉM, nên nếu đường
    mặc định lỡ chạm `nvidia-smi` thì bài đỏ ngay chứ không im lặng bỏ qua.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "smoke_echo_guard.py"


def _load_driver():
    assert SCRIPT.exists(), "brief yêu cầu driver backend/scripts/smoke_echo_guard.py"
    spec = importlib.util.spec_from_file_location("smoke_echo_guard_vram", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_vram_summary_separates_idle_peak_steady_and_count():
    """`[... MiB ...]` -> `{idle, peak, steady, samples}` bằng ba mảng GIẢ.

    Ba điều được ghim, đúng ba câu mà artifact phải trả lời:

    * **idle** là mức TRƯỚC khi nạp model, không phải mức thấp nhất của cả lượt;
    * **peak** là max của phần ĐÃ NẠP (một gai trong bàn ổn định vẫn là một đỉnh
      VRAM thật), còn **steady** là MODE của phần đó — nên gai không đẩy nó đi;
    * mảng RỖNG thì mọi trường đo là None, không phải 0: "không đo được" và "0
      MiB" là hai chuyện khác nhau.
    """
    driver = _load_driver()

    # (a) nền phẳng rồi bàn ổn định: 5 mẫu idle rồi model đã nạp.
    plate = [1790, 1792, 1791, 1790, 1793,
             6410, 6408, 6412, 6409, 6411, 6410]
    block = driver.summarize_vram(plate, 8192)
    assert block["idle_mib"] == 1791           # trung vị 5 mẫu đầu
    assert block["idle_samples"] == 5
    assert block["loaded_at"] == 5             # mẫu đầu vượt nền + 512 MiB
    assert block["loaded_samples"] == 6
    assert block["peak_mib"] == 6412
    assert block["steady_mib"] == 6410         # 6410 xuất hiện 2 lần
    assert block["headroom_mib"] == 8192 - 6412
    assert block["samples"] == len(plate)
    assert block["raw_mib"] == plate, "chuỗi thô phải được giữ để kiểm lại được"

    # (b) một gai ĐƠN LẺ trong bàn ổn định: peak bắt nó, steady thì không.
    spike = [1800, 1800, 1800, 1800, 1800, 6400, 6400, 6900, 6400, 6400]
    block = driver.summarize_vram(spike, 8192)
    assert block["idle_mib"] == 1800
    assert block["loaded_at"] == 5
    assert block["peak_mib"] == 6900
    assert block["steady_mib"] == 6400, (
        "mode của phần đã nạp: một khung hình nặng không được làm mức ổn định "
        "nhảy 500 MiB"
    )
    assert block["headroom_mib"] == 8192 - 6900

    # (b') gai đơn lẻ trong NỀN IDLE không được đọc thành "đã nạp model": mẫu
    #     6900 không có mẫu KẾ TIẾP trên ngưỡng, nên không có peak/steady nào.
    blip = [1800, 1800, 6900, 1800, 1800]
    block = driver.summarize_vram(blip, 8192)
    assert block["loaded_at"] is None
    assert block["peak_mib"] is None and block["steady_mib"] is None
    assert block["idle_mib"] == 1800

    # (c) mảng rỗng: không có số nào, và KHÔNG được là 0.
    empty = driver.summarize_vram([], 8192)
    assert empty["samples"] == 0
    assert empty["raw_mib"] == []
    assert empty["idle_samples"] == 0
    for key in ("idle_mib", "peak_mib", "steady_mib", "headroom_mib"):
        assert empty[key] is None, key


class _FakeSpec:
    """`EngineSpec` tối thiểu mà `run_one` đọc (id/model_ref/capabilities)."""

    id = "fake-engine"
    model_ref = "fake:model"
    capabilities = {"glossary_prompt": True}


class _FakeEngine:
    """Engine GIẢ: không HTTP, không model, và CẤM bị gọi dịch."""

    engine_id = _FakeSpec.id
    model_ref = _FakeSpec.model_ref
    last_stats = None

    def supports_glossary(self) -> bool:
        return True

    def translate(self, batch, glossary, opts):
        raise AssertionError("cờ tắt không được sinh lời gọi engine")

    def release(self) -> None:
        pass


class _FakeHandler:
    """Handler GIẢ: `run_one` chỉ cần nó dựng được và chạy xong."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def translate(self, **kwargs):
        return None


def test_the_vram_block_is_absent_from_the_artifact_when_the_flag_is_off(
        tmp_path, monkeypatch):
    """Cờ TẮT ⇒ artifact KHÔNG có khoá `vram`, và không chạm `nvidia-smi`.

    Đây là điều kiện "đường mặc định không đổi": lượt chia đôi lô
    (`smoke_echo_halving.run_one`) và mọi artifact cũ đi qua đúng hàm này với
    `sample_vram=False`, nên một khoá `vram: null` cũng đã là thay đổi artifact.
    """
    driver = _load_driver()
    touched: list[str] = []

    def _no_gpu(*args, **kwargs):
        touched.append("nvidia-smi")
        raise AssertionError(
            "cờ --sample-vram TẮT thì không được chạm nvidia-smi")

    monkeypatch.setattr(driver, "_gpu_used_mib", _no_gpu)
    monkeypatch.setattr(driver, "_smi_mib", _no_gpu)
    monkeypatch.setattr(driver, "_ollama_ps_text", _no_gpu)
    monkeypatch.setattr(driver, "_loaded_models", lambda: [])
    monkeypatch.setattr(driver.smoke, "_engine_and_capabilities",
                        lambda _engine_id: (_FakeSpec(), _FakeEngine()))

    transcript = tmp_path / "clip.json"
    transcript.write_text(json.dumps({"segments": [
        {"start": 0.0, "end": 2.5, "text": "烟台山的螺钿"},
    ]}, ensure_ascii=False), encoding="utf-8")
    glossary = tmp_path / "glossary.json"
    glossary.write_text(json.dumps([{
        "lang": "zh", "term": "烟台山", "translation": "Yên Đài Sơn",
        "approved": True,
    }], ensure_ascii=False), encoding="utf-8")

    out_dir = tmp_path / "out"
    result = driver.run_one(transcript, glossary, out_dir, 30,
                            handler_cls=_FakeHandler)

    artifact_path = out_dir / "batch-30.json"
    assert artifact_path.exists(), "run_one phải ghi artifact như trước"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert "vram" not in artifact
    assert "vram" not in result
    assert touched == [], "đường mặc định không được gọi nvidia-smi"
