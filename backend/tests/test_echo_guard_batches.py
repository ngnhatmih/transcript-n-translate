"""`--batches` của `scripts/smoke_echo_guard.py` — cờ phải THẮNG, không im lặng.

Vì sao có tệp này
    Lượt đo `--batches 15 --configs A` ghi ra artifact `batch_items: 30` với bốn
    lô đúng hình dạng 30 (3×30 + 25 mục cuối): `main()` tự gán cứng 30 cho MỌI
    lượt có `--configs`, nên cờ trông như đã có tác dụng mà không có. Đó đúng loại
    hỏng repo này coi là lỗi, và nó chỉ lộ ra khi mở artifact — không bài test nào
    đỏ, không dòng log nào khác thường. Bốn bài dưới đây ghim cờ ở ĐÚNG chỗ giao
    nhau giữa CLI và artifact, gồm cả lượt bị hỏng (`--configs`) và lượt nhiều lô
    trên cùng một cấu hình (nếu không tách tên tệp thì lượt sau ghi đè lượt trước:
    một dạng im lặng thứ hai của cùng lỗi).

Vì sao không cần model hay mạng
    Cùng cách `tests/test_vram_sample.py`: engine và handler đều GIẢ, và
    `_loaded_models` giả nên không chạm `ollama ps`. `main()` chỉ trao lô xuống
    `run_one`, còn `run_one` mới là nơi ghi artifact, nên bài test gọi `main()`
    THẬT với `run_one` được bọc lại để nhận handler giả — nó kiểm đúng đường
    CLI -> plan -> handler -> artifact, không kiểm một bản sao của đường đó.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "smoke_echo_guard.py"


def _load_driver():
    assert SCRIPT.exists(), "brief yêu cầu driver backend/scripts/smoke_echo_guard.py"
    spec = importlib.util.spec_from_file_location("smoke_echo_guard_batches", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        raise AssertionError("handler giả không được sinh lời gọi engine")

    def release(self) -> None:
        pass


def _fake_handler_cls(seen: list[int | None]):
    """Handler GIẢ, ghi lại `batch_items` mà `run_one` truyền xuống.

    Artifact ghi `batch_items` từ cùng tham số đó, nên hai nguồn này khớp nhau
    nghĩa là con số trong artifact đúng là con số đã dùng để dựng handler.
    """

    class _FakeHandler:
        def __init__(self, *args, **kwargs) -> None:
            seen.append(kwargs.get("batch_items"))

        def translate(self, **kwargs):
            return None

    return _FakeHandler


def _prepare(monkeypatch, driver, tmp_path):
    """Dựng clip/glossary tối thiểu + đường `main()` không model, không mạng."""
    seen: list[int | None] = []
    real_run_one = driver.run_one

    def _run_one_with_fake_handler(*args, **kwargs):
        # `main()` luôn gọi đường ship (`handler_cls` mặc định = `TranslateHandler`);
        # ở đây chỉ đổi đúng tham số đó, phần còn lại vẫn là `run_one` THẬT để
        # artifact được ghi bởi chính nó.
        kwargs["handler_cls"] = _fake_handler_cls(seen)
        return real_run_one(*args, **kwargs)

    monkeypatch.setattr(driver, "run_one", _run_one_with_fake_handler)
    monkeypatch.setattr(driver.smoke, "_engine_and_capabilities",
                        lambda _engine_id: (_FakeSpec(), _FakeEngine()))
    monkeypatch.setattr(driver, "_loaded_models", lambda: [])

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
    return seen, transcript, glossary, out_dir


def _artifacts(out_dir: pathlib.Path) -> dict[str, dict]:
    return {path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in out_dir.glob("*.json") if path.name != "summary.json"}


def _main(driver, transcript, glossary, out_dir, *extra: str) -> int:
    return driver.main(["--transcript", str(transcript),
                        "--glossary", str(glossary),
                        "--out-dir", str(out_dir), *extra])


def test_batches_15_sets_the_call_size_without_configs(monkeypatch, tmp_path):
    """`--batches 15` ⇒ artifact `batch-15.json` với `batch_items == 15`."""
    driver = _load_driver()
    seen, transcript, glossary, out_dir = _prepare(monkeypatch, driver, tmp_path)

    assert _main(driver, transcript, glossary, out_dir, "--batches", "15") == 0

    artifacts = _artifacts(out_dir)
    assert list(artifacts) == ["batch-15.json"], "mỗi lô một tệp, tên theo lô"
    assert artifacts["batch-15.json"]["batch_items"] == 15
    assert seen == [15], "lô trong artifact phải là lô đã dựng handler"


def test_two_batch_sizes_write_one_artifact_per_size(monkeypatch, tmp_path):
    """`--batches 15 30` ⇒ HAI artifact, mỗi tệp một trần số mục."""
    driver = _load_driver()
    seen, transcript, glossary, out_dir = _prepare(monkeypatch, driver, tmp_path)

    assert _main(driver, transcript, glossary, out_dir,
                 "--batches", "15", "30") == 0

    artifacts = _artifacts(out_dir)
    assert sorted(artifacts) == ["batch-15.json", "batch-30.json"], (
        "hai lô phải ra hai tệp — một tệp duy nhất nghĩa là lượt sau ghi đè lượt "
        "trước và phép đo mất một nửa số")
    assert artifacts["batch-15.json"]["batch_items"] == 15
    assert artifacts["batch-30.json"]["batch_items"] == 30
    assert seen == [15, 30]


def test_batches_wins_over_configs_the_original_silent_bug(monkeypatch, tmp_path):
    """`--batches 15 --configs A` ⇒ `config-A.json` với `batch_items == 15`.

    Đây là lượt đã hỏng: cờ `--batches` bị bảng `CONFIGS` nuốt, artifact ghi 30 và
    các lô là 3×30 + 25 mục cuối. Bảng `CONFIGS` chỉ khai `style` và
    `first_batch_items` — lô là biến của phép đo, nên CLI phải là nguồn DUY NHẤT.
    """
    driver = _load_driver()
    seen, transcript, glossary, out_dir = _prepare(monkeypatch, driver, tmp_path)

    assert _main(driver, transcript, glossary, out_dir,
                 "--batches", "15", "--configs", "A") == 0

    artifacts = _artifacts(out_dir)
    assert list(artifacts) == ["config-A.json"], "tên tệp của lượt MỘT lô giữ nguyên"
    assert artifacts["config-A.json"]["batch_items"] == 15, (
        "cờ --batches bị bỏ qua: con số này từng là 30 và không ai thấy")
    assert seen == [15]


def test_configs_with_two_batch_sizes_do_not_overwrite_each_other(
        monkeypatch, tmp_path):
    """`--batches 15 30 --configs A` ⇒ hai tệp; cùng cấu hình không ghi đè nhau."""
    driver = _load_driver()
    seen, transcript, glossary, out_dir = _prepare(monkeypatch, driver, tmp_path)

    assert _main(driver, transcript, glossary, out_dir,
                 "--batches", "15", "30", "--configs", "A") == 0

    artifacts = _artifacts(out_dir)
    assert sorted(artifacts) == ["config-A-batch-15.json",
                                 "config-A-batch-30.json"]
    assert artifacts["config-A-batch-15.json"]["batch_items"] == 15
    assert artifacts["config-A-batch-30.json"]["batch_items"] == 30
    assert seen == [15, 30]

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert sorted(summary["echo_by_batch"]) == ["A-15", "A-30"], (
        "bảng theo lô trong summary.json cũng phải tách theo lô, không gộp một "
        "khoá 'A' cho hai lượt")
