from __future__ import annotations

import json

import pytest

from app.adapters.registry_file import load_registry
from app.domain import job_state as js
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
    assert all(s.phase_key.startswith(("asr:", "translate:")) for s in specs)
    # Moonshine KHÔNG được có mặt: nó không sinh timestamp (spec §6)
    assert not any("moonshine" in s.id.lower() for s in specs)


def test_shipped_registry_declares_the_default_asr_engine():
    """I-3 · engine ASR mặc định là DỮ LIỆU của registry, không phải literal.

    `ingest.py` từng có `DEFAULT_ASR_ENGINE = "fw-large-v3-turbo"` là thứ DUY NHẤT
    quyết định engine của mọi job ASR do upload sinh ra, nên một registry không có
    id đó vẫn tạo ra job chết (`KeyError` tận worker). Bài này ghim nguồn dữ liệu.

    Đổi `fw-large-v3-turbo` -> `fw-large-v3` là quyết định SẢN PHẨM (chính xác hơn
    turbo, đổi 1600 MB VRAM lấy 3200 MB), nên bài này ghim đúng id đã ship.
    """
    from app.adapters.registry_file import load_default_asr

    declared = load_default_asr()
    assert declared == "fw-large-v3"
    assert declared in {s.id for s in load_registry()}, (
        "registry.json phải khai báo một engine asr CÓ THẬT trong danh sách"
    )


def test_default_asr_engine_is_registry_data_and_is_proven_to_exist(tmp_path):
    """I-3 · chọn mặc định từ dữ liệu, và TỪ CHỐI id không có trong registry.

    Đây đúng hình dạng repro đã đo được: một registry chỉ có `fw-tiny` mà vẫn
    khai báo mặc định `fw-large-v3-turbo` phải hỏng NGAY và NÓI RÕ, thay vì để
    job asr chết ở tận worker.
    """
    from app.adapters.registry_file import load_default_asr
    from app.registry import default_asr_engine

    data = {
        "default_asr": "fw-tiny",
        "asr": [{"id": "fw-tiny", "label": "tiny", "runtime": "inprocess",
                 "model_ref": "tiny", "vram_mb": 200, "langs": ["zh"],
                 "capabilities": {}, "opts": {}}],
        "mt": [],
    }
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    specs = load_registry(p)

    assert load_default_asr(p) == "fw-tiny", "mặc định phải đọc từ registry"
    assert default_asr_engine(specs, declared=load_default_asr(p)) == "fw-tiny"

    # Setting của người dùng thắng khai báo, nhưng vẫn phải có thật.
    assert default_asr_engine(specs, declared="fw-tiny", configured="fw-tiny") == "fw-tiny"
    with pytest.raises(KeyError, match="khong-co") as excinfo:
        default_asr_engine(specs, declared="fw-tiny", configured="khong-co")
    assert "fw-tiny" in str(excinfo.value), (
        "lỗi phải liệt kê các engine asr ĐANG CÓ để người vận hành sửa được ngay"
    )


def test_default_asr_engine_falls_back_and_refuses_a_registry_without_it(tmp_path):
    """I-3 · khoá `default_asr` vắng ⇒ giữ hành vi cũ, nhưng VẪN phải có thật."""
    from app.registry import default_asr_engine

    data = {"asr": [{"id": "fw-tiny", "label": "tiny", "runtime": "inprocess",
                     "model_ref": "tiny", "vram_mb": 200, "langs": ["zh"],
                     "capabilities": {}, "opts": {}}], "mt": []}
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    specs = load_registry(p)

    with pytest.raises(KeyError, match="fw-large-v3-turbo"):
        default_asr_engine(specs)


def test_default_mt_engine_refuses_a_declared_id_that_is_not_in_the_registry(specs):
    """WQ-02/F3 · `default_mt` gõ sai phải hỏng kèm id + nguồn + danh sách có thật.

    `default_mt_engine` từng trả thẳng id đã khai báo mà không đối chiếu `specs`,
    nên một lần gõ sai trong `registry.json` trở thành engine của MỌI job
    `translate` mà không ai thấy: GĐ1a chưa có handler `translate`, nên job chỉ
    `FAILED` ở tận worker. Đây là bất đối xứng với `default_asr_engine`, thứ vốn
    đã từ chối NGAY lúc dựng (`main.py`).
    """
    from app.registry import default_mt_engine

    with pytest.raises(KeyError, match="opus-mt-go-nham") as excinfo:
        default_mt_engine(specs, declared="opus-mt-go-nham")
    assert "qwen2.5-7b" in str(excinfo.value), (
        "lỗi phải liệt kê các engine mt ĐANG CÓ để người vận hành sửa được ngay"
    )

    # Setting của người dùng cũng phải có thật, y như nhánh `configured` của ASR.
    with pytest.raises(KeyError, match="cung-sai"):
        default_mt_engine(specs, declared="qwen2.5-7b", configured="cung-sai")


def test_default_mt_engine_keeps_the_legacy_order_fallback(specs):
    """WQ-02/F3 · registry KHÔNG khai báo gì ⇒ điểm rơi theo thứ tự mảng giữ nguyên.

    Đây là HỢP ĐỒNG CÔNG KHAI của `default_mt_engine` (registry không có khoá
    `default_mt` vẫn phải chạy), không phải code chết — dù cấu hình đã ship luôn
    truyền `declared` nên không đường sản xuất nào tới được nhánh này.
    """
    from app.registry import default_mt_engine

    assert default_mt_engine(specs) == "qwen2.5-7b"
    assert default_mt_engine(specs, declared=None) == "qwen2.5-7b"
    assert default_mt_engine(of_kind(specs, "asr")) is None


def test_shipped_registry_declares_the_default_mt_engine():
    """R58/WQ-02 · engine DỊCH mặc định là DỮ LIỆU, không phải thứ tự mảng `mt`.

    `TranscribeHandler._default_mt_engine` từng lấy thẳng `mt_specs[0].id`, nên
    đảo thứ tự mảng `mt` trong `registry.json` — hoặc thêm một model Ollama
    5200 MB lên đầu — là đổi engine mặc định của cả pipeline một cách im lặng,
    không test nào ghim. Bài này khoá dấu hiệu tường minh `default_mt`.
    """
    from app.adapters.registry_file import load_default_mt
    from app.registry import default_mt_engine

    declared = load_default_mt()
    assert declared == "deepseek-web"
    assert declared in {s.id for s in load_registry()}, (
        "registry.json phải khai báo một engine mt CÓ THẬT trong danh sách"
    )

    # Đảo thứ tự mảng `mt`: model Ollama 5200 MB (`hy-mt-1.5-7b`) lên đầu, y như
    # một lần sửa `registry.json` vô ý. Mặc định tường minh KHÔNG được đổi theo.
    specs = load_registry()
    mt = [s for s in specs if s.kind == "mt"]
    asr = [s for s in specs if s.kind == "asr"]
    reordered = asr + [mt[-1]] + mt[:-1]
    assert reordered[len(asr)].id != mt[0].id, (
        "mutation tự kiểm của chính test: thứ tự mảng `mt` phải đã đổi"
    )
    assert default_mt_engine(reordered, declared=declared) == "deepseek-web", (
        "mặc định phải đến từ khoá `default_mt`, không từ vị trí dòng"
    )


# Loại job THẬT của từng kind (plan §"JOB_TYPES"): job dịch tên là `translate`,
# KHÔNG phải `mt`. Bảng này cố ý viết lại tại đây thay vì import từ app.registry,
# để test bắt được cả trường hợp bảng ánh xạ trong code bị đổi sai.
_JOB_TYPE_OF_KIND = {"asr": "asr", "mt": "translate"}


def test_phase_key_matches_job_state_phase_of_for_every_shipped_engine():
    """`phase_key` phải bằng đúng chuỗi mà `Job.phase` thực sự lưu.

    Dựng `phase_key` từ `self.kind` là tự quy chiếu: `kind` của engine dịch là
    `"mt"` còn job type là `"translate"`, nên 4 engine mt sẽ không bao giờ khớp
    một phase đã lưu. `next_queued_for_phase` tra bằng EQUALITY nên lỗi này âm
    thầm treo hàng đợi thay vì ném exception.
    """
    for spec in load_registry():
        job_type = _JOB_TYPE_OF_KIND[spec.kind]
        assert spec.phase_key == js.phase_of(job_type, spec.id), spec.id


def test_shipped_registry_pins_every_engine_and_its_vram():
    """Ghim đủ 10 engine + vram_mb: con số này điều khiển VRAM arbitration.

    Sai một số, hoặc mất một entry, là lỗi thật mà các test khác không bắt được.
    `fw-large-v3` (3 200 MB) được thêm sau khi đo: timed mean CER trên 84 caption
    OCR là 0,049750 so với 0,065835 của turbo — cùng adapter, cùng reference.
    `deepseek-web` là engine `runtime: "http"` (chạy ở máy KHÁC), nên `vram_mb: 0` là con
    số ĐÚNG chứ không phải thiếu: nó không chiếm VRAM của card này, và bộ điều phối không
    được đổ model nào cho nó. Hàng đó chỉ được khai sau khi đo trên endpoint thật.
    """
    specs = load_registry()
    assert {s.id: s.vram_mb for s in specs} == {
        "fw-large-v3-turbo": 1600,
        "fw-large-v3": 3200,
        "fw-medium": 1500,
        "fw-small": 500,
        "sensevoice-small": 1000,
        "opus-mt": 0,
        "qwen2.5-3b": 2500,
        "qwen2.5-7b": 5200,
        "hy-mt-1.5-7b": 5200,
        "deepseek-web": 0,
    }
