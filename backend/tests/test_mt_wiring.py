"""Nối dây MT vào composition root, qua chính `build_components()` THẬT.

Không chép lại wiring trong fixture: Giai đoạn 1a đã trả giá đúng ở đây khi
fixture tự dựng lại assembly của `main.py` rồi TRÔI khỏi nó mà không test nào
bắt (`PhaseQueueWorker` dựng thiếu `publish=` nên SSE câm suốt). Cùng lớp lỗi
với task này là dựng `TranslateHandler` mà quên `mt_engines`, hoặc quên
`governor.register(...)` — nên mọi bài ở đây gọi `main.build_components()` và
`main.build_app()` thật, chỉ thay ĐÚNG hai adapter nặng (engine ASR, engine MT)
và đường dẫn, y như `tests/test_api_sources.py` và `tests/test_e2e_fake.py` đã
làm.

`ensure_dirs()` closure trên biến toàn cục của `app.config`, nên fixture phải
vá CẢ `app.config` lẫn `main`: vá mỗi `main` thì `build_components()` vẫn tạo
`data/` THẬT của repo (Q5 của review Task 19), và `_assert_repo_data_untouched`
dưới đây biến lời hứa đó thành thứ chạy được.

`ollama_available` được vá TƯỜNG MINH trong fixture (mặc định: sống, đã pull mọi
`model_ref` của registry thật) để suite không phụ thuộc việc Ollama có đang chạy
trên máy hay không; RIÊNG `test_real_probe_tolerates_both_answers` gọi
`build_components()` mà KHÔNG vá nó, đúng yêu cầu "phải chịu được cả hai giá trị".

Fix round 1 (I-1): phép dò trả về TÊN model đã pull (`set()` khi không dùng
được), nên bộ vá ở đây trả về một `set` — không còn `bool`. "Ollama sống" và
"model đã pull" là HAI câu hỏi khác nhau, và fixture này điều khiển cả hai.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

from app.adapters.registry_file import load_default_asr, load_default_mt, load_registry
from app.domain import job_state as js
from app.domain.models import Job, Segment
from app.pipeline.translate import TranslateHandler
from app.registry import by_id, of_kind

TARGET_LANG = "vi"


class _RecordingMtEngine:
    """Engine dịch GIẢ cắm vào ĐÚNG chỗ `main.py` dựng adapter thật.

    Nó KHÔNG thay thế việc ráp dây: chính `main.py` quyết định spec nào có
    engine, khoá dict là `spec.id` (không phải `engine.engine_id` — cố ý khác
    nhau cho `opus-mt`), và releaser nào được đăng ký với governor.

    `translate` chỉ đổi `text` qua `dataclasses.replace`, không dựng
    `Segment(...)` bằng tay (13 trường, hai task trong phase này đã nuốt 7
    trường bằng cách dựng tay).
    """

    def __init__(self, model_ref: str, *, supports_glossary: bool = False,
                 engine_id: str | None = None) -> None:
        self.model_ref = model_ref
        self._supports_glossary = supports_glossary
        self.releases = 0
        self.batches: list[list[int]] = []
        self.last_stats = None
        #: Fix round 1 (I-2): ghi lại ĐÚNG thứ `_build_mt_engines` truyền vào.
        #: `None` = "không truyền gì", nên `main.py` bỏ tham số là bài ghim dây
        #: nối đỏ ngay, chứ không âm thầm rơi về điểm rơi suy từ tag.
        self.received_engine_id = engine_id

    @property
    def engine_id(self) -> str:
        # Cố ý KHÁC `spec.id` của `opus-mt`/`hy-mt-1.5-7b`: nếu `main.py` đánh
        # khoá `mt_engines` theo thuộc tính này thì khoá sẽ trượt khỏi id mà job
        # mang theo, và phép đỏ là `KeyError` lúc chạy.
        return f"engine-id-cua-{self.model_ref}"

    def supports_glossary(self) -> bool:
        return self._supports_glossary

    def translate(self, batch, glossary, opts):
        self.batches.append([s.i for s in batch])
        return [dataclasses.replace(s, text=f"[{opts.target_lang}] {s.text}")
                for s in batch]

    def release(self) -> None:
        self.releases += 1


class _FakeAsrEngine:
    def __init__(self) -> None:
        self.released = 0

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        return [Segment(i=0, start=0.0, end=2.0, text="你好"),
                Segment(i=1, start=2.0, end=4.0, text="世界")]

    def release(self) -> None:
        self.released += 1


def _repo_data_dirs() -> list[pathlib.Path]:
    """Bốn thư mục mà `ensure_dirs()` tạo cho cấu hình THẬT của repo.

    Đường dẫn suy từ `config.__file__`, KHÔNG từ `config.DATA_DIR`: chính
    `DATA_DIR` là thứ fixture vá, nên hỏi nó là hỏi kẻ vừa bị đổi.
    """
    from app import config

    root = pathlib.Path(config.__file__).resolve().parents[2] / "data"
    return [root, root / "media", root / "logs", root / "output"]


def _snapshot() -> dict[pathlib.Path, bool]:
    return {d: d.exists() for d in _repo_data_dirs()}


def _all_real_model_refs() -> set[str]:
    """Mọi `model_ref` của registry THẬT — cái một máy "đủ điều kiện" phải có.

    Dùng làm mặc định của bộ vá `ollama_available` (fix round 1, I-1): mặc định
    của suite là "Ollama sống VÀ đã pull mọi thứ registry khai", tức mọi engine
    đều phục vụ được. Quét từ registry thật chứ không viết tay danh sách: thêm
    một engine Ollama mới vào `registry.json` mà quên đây thì fixture tự nhiên
    coi nó "chưa pull", và mọi bài dùng harness đỏ vì một lý do không liên quan.
    """
    from app.adapters.registry_file import load_registry

    return {s.model_ref for s in of_kind(load_registry(), "mt")
            if s.runtime == "ollama"}


def _assert_repo_data_untouched(before: dict[pathlib.Path, bool]) -> None:
    created = [str(d) for d, existed in before.items() if not existed and d.exists()]
    assert not created, (
        "build_components() đã tạo thư mục THẬT trong repo: " + ", ".join(created)
        + ". Phải vá `app.config` (nơi `ensure_dirs()` đọc biến), không chỉ vá "
          "tên đã import vào `main` (M7/RU-04)."
    )


class _Harness:
    """Bộ vá dùng chung: đường dẫn vào `tmp_path`, adapter nặng thành giả."""

    def __init__(self, tmp_path, monkeypatch) -> None:
        from app import config, main

        self.main = main
        self.before = _snapshot()
        data = tmp_path / "data"
        for module in (config, main):
            monkeypatch.setattr(module, "DATA_DIR", data, raising=False)
            monkeypatch.setattr(module, "MEDIA_DIR", data / "media", raising=False)
            monkeypatch.setattr(module, "LOG_DIR", data / "logs", raising=False)
            monkeypatch.setattr(module, "OUTPUT_DIR", data / "output", raising=False)
        monkeypatch.setattr(main, "DB_PATH", data / "app.db")

        self.data = data
        # Fix round 1 (I-1): phép dò nay trả về TÊN model đã pull. Hai nút điều
        # khiển TÁCH BIỆT, vì "Ollama sống" ≠ "model này đã pull":
        # `ollama_alive` là tiến trình, `pulled` là tập model trong `/api/tags`.
        # Mặc định: sống + đã pull MỌI `model_ref` của registry thật (quét ở
        # `_all_real_model_refs`), tức "máy đủ điều kiện chạy mọi engine" — còn
        # các bài về từng nửa của I-1 tự hạ một trong hai nút.
        self.ollama_alive = True
        self.pulled = _all_real_model_refs()
        monkeypatch.setattr(main, "ollama_available",
                            lambda *a, **k: set(self.pulled) if self.ollama_alive
                            else set())
        self.mt_engines: list[_RecordingMtEngine] = []

        def mt_factory(*args, **kwargs):
            engine = _RecordingMtEngine(*args, **kwargs)
            self.mt_engines.append(engine)
            return engine

        # Vá ĐÚNG chỗ `main.py` dựng adapter (giống `_engine_factory` và
        # `SingleGpuGovernor` ở các suite khác): logic ráp dây vẫn là production.
        monkeypatch.setattr(main, "OllamaMtEngine", mt_factory)
        monkeypatch.setattr(main, "OpusMtEngine", mt_factory)
        self.asr = _FakeAsrEngine()
        monkeypatch.setattr(main, "_engine_factory", lambda spec: self.asr)

    def build(self):
        built = self.main.build_components()
        _assert_repo_data_untouched(self.before)
        return built


@pytest.fixture()
def harness(tmp_path, monkeypatch) -> _Harness:
    return _Harness(tmp_path, monkeypatch)


# ---------------------------------------------------------------------------
# Hình dạng của `build_components()` — tuple 5 phần tử, `mt_engines` ở CUỐI
# ---------------------------------------------------------------------------

def test_build_components_returns_a_five_tuple_with_mt_engines_last(harness):
    built = harness.build()
    assert isinstance(built, tuple) and len(built) == 5, (
        "correction A: giữ tuple và thêm `mt_engines` vào CUỐI, không đổi sang "
        f"dataclass; nhận được {type(built).__name__} {len(built)} phần tử"
    )
    repos, specs, worker, broker, mt_engines = built
    assert isinstance(mt_engines, dict)
    assert callable(broker.publish) and worker.handlers


def test_mt_engines_are_keyed_by_registry_spec_id_not_engine_id(harness):
    """Correction D: khoá theo `spec.id`, không theo `engine.engine_id`.

    Đo ở Task 10: quy tắc suy `engine_id` từ tag KHÔNG tái tạo được id registry
    cho HY-MT, nên đánh khoá theo `engine.engine_id` sẽ `KeyError` khi có người
    chọn HY-MT. Engine giả ở đây cố ý có `engine_id` khác `spec.id`.
    """
    harness.ollama_alive = True
    _repos, specs, _worker, _broker, mt_engines = harness.build()

    available = {s.id for s in of_kind(specs, "mt") if s.capabilities.get("available")}
    assert set(mt_engines) == available
    assert "opus-mt" in mt_engines, "engine in-process luôn sẵn sàng, phải có mặt"
    for engine_id, engine in mt_engines.items():
        assert by_id(specs, engine_id).id == engine_id
        assert engine.engine_id != engine_id, (
            "engine giả cố ý có engine_id khác spec.id; nếu bằng nhau thì bài "
            "này không còn chứng minh được điều D nói"
        )
        # Fix round 1 (I-2): với engine Ollama, `spec.id` phải được TRUYỀN vào
        # adapter (`engine_id=`), không phải để nó tự suy từ tag — tag HY-MT suy
        # ra một id không có trong registry. `opus-mt` dựng qua `OpusMtEngine`,
        # không có tham số này (id của nó là dữ liệu cố định của adapter).
        spec = by_id(specs, engine_id)
        if spec.runtime == "ollama":
            assert engine.received_engine_id == engine_id, (
                f"{engine_id}: composition root phải truyền THẲNG `spec.id` vào "
                f"OllamaMtEngine(engine_id=...), nhận được "
                f"{engine.received_engine_id!r}"
            )
            # Fix round 2 (I-9): vế còn lại của cùng dây nối. `engine_id` ĐÃ được
            # ghim ở trên, nhưng tham số vị trí đầu (`spec.model_ref`) thì không:
            # `OllamaMtEngine(spec.id, ...)` từng để CẢ SUITE xanh, trong khi
            # `ollama_mt.py:139` đặt thẳng tham số này vào `"model"` của
            # `POST /api/chat` — sai thì cả ba engine Ollama chết `404 model not
            # found` ở tận worker. Kỳ vọng đọc từ CHÍNH `spec` của registry mà
            # `build_components()` vừa dùng, không hard-code tag (cùng kỷ luật với
            # phép ghim `opus-mt` ở `test_e2e_translate.py`).
            assert engine.model_ref == spec.model_ref, (
                f"{engine_id}: composition root phải truyền THẲNG "
                f"`spec.model_ref` vào OllamaMtEngine(...), nhận được "
                f"{engine.model_ref!r} thay vì {spec.model_ref!r} — tag đó đi "
                f"thẳng vào `POST /api/chat` (`ollama_mt.py:139`)"
            )


def test_ollama_availability_is_probed_here_and_now_not_hardcoded(harness):
    """Correction B + Step 4: `available` là DỮ LIỆU DÒ SỐNG, không hardcode.

    Hardcode `true` cho một engine Ollama chưa cài thì job sẽ chết trong worker
    thay vì bị từ chối sớm (I-3 của 1a).

    Fix round 1 (I-1): đây là NỬA THỨ NHẤT — tiến trình Ollama TẮT. Nửa thứ hai
    (tiến trình sống nhưng model CHƯA pull) nằm ở
    `test_an_alive_ollama_without_the_model_is_not_available`: bản cũ của bài
    này chỉ có nửa thứ nhất, nên nó xanh với một phép dò chỉ hỏi "Ollama có sống".
    """
    harness.ollama_alive = False
    _repos, specs_down, _worker, _broker, engines_down = harness.build()
    assert set(engines_down) == {"opus-mt"}, (
        f"Ollama tắt thì chỉ engine in-process được dựng: {sorted(engines_down)}"
    )
    for spec in of_kind(specs_down, "mt"):
        assert spec.capabilities.get("available") is (spec.runtime == "inprocess"), (
            f"{spec.id} ({spec.runtime}) khai available sai khi Ollama tắt"
        )

    harness.ollama_alive = True
    _repos, specs_up, _worker, _broker, engines_up = harness.build()
    assert set(engines_up) == {s.id for s in of_kind(specs_up, "mt")}, (
        "Ollama sống VÀ đã pull mọi model_ref thì mọi engine sẵn sàng và phải có "
        f"engine: {sorted(engines_up)}"
    )
    for spec in of_kind(specs_up, "mt"):
        assert spec.capabilities["available"] is True


def test_an_alive_ollama_without_the_model_is_not_available(harness):
    """Fix round 1 (I-1), NỬA QUAN TRỌNG NHẤT: "Ollama sống" KHÔNG ĐỦ.

    Đây là lớp lỗi I-3 của GĐ1a, đo được trên chính máy này: chỉ
    `qwen2.5:3b-instruct-q4_K_M` được pull, nhưng `GET /api/registry` vẫn khai
    `available: true` cho `qwen2.5-7b` và `hy-mt-1.5-7b`. Người dùng chọn một
    engine mà API nói đã sẵn sàng, rồi job chết ở tận worker.

    Tiến trình SỐNG, `/api/tags` trả về ĐÚNG một model: ba engine còn lại phải
    thành KHÔNG sẵn sàng, và không engine nào trong số đó được dựng hay đăng ký
    với governor.
    """
    only_three_b = by_id(load_registry(), "qwen2.5-3b").model_ref
    harness.ollama_alive = True
    harness.pulled = {only_three_b}

    _repos, specs, worker, _broker, mt_engines = harness.build()

    ollama_specs = [s for s in of_kind(specs, "mt") if s.runtime == "ollama"]
    assert len(ollama_specs) >= 2, (
        "registry.json phải còn ít nhất hai engine ollama để bài này có nghĩa"
    )
    for spec in ollama_specs:
        expected = spec.model_ref == only_three_b
        assert spec.capabilities["available"] is expected, (
            f"{spec.id}: ollama sống nhưng đã pull {sorted(harness.pulled)}; "
            f"available phải là {expected}, không phải "
            f"{spec.capabilities['available']}"
        )
        assert (spec.id in mt_engines) is expected, (
            f"{spec.id}: available={spec.capabilities['available']} nhưng "
            f"có trong mt_engines: {spec.id in mt_engines}"
        )

    assert mt_engines, "engine có model đã pull phải được dựng"
    assert "opus-mt" in mt_engines, "engine in-process không phụ thuộc Ollama"
    registered = set(worker.governor._loaded)  # noqa: SLF001 - chính dây nối
    for spec in ollama_specs:
        assert (spec.phase_key in registered) is (spec.model_ref == only_three_b), (
            f"{spec.id}: giai đoạn {'phải' if spec.model_ref == only_three_b else 'không được'}"
            f" đăng ký với governor: {sorted(registered)}"
        )


def test_an_engine_with_the_pulled_model_is_available(harness):
    """Nửa ĐỐI CHỨNG của I-1: đủ điều kiện (sống + đã pull) thì PHẢI sẵn sàng.

    Không có bài này thì `available` ghim cứng `False` cũng xanh các bài còn lại.
    """
    harness.ollama_alive = True
    harness.pulled = {"qwen2.5:7b-instruct-q4_K_M"}     # đúng model_ref của 7b
    _repos, specs, _worker, _broker, mt_engines = harness.build()

    seven = by_id(specs, "qwen2.5-7b")
    assert seven.model_ref in harness.pulled, "bài này phải pull ĐÚNG model_ref"
    assert seven.capabilities["available"] is True
    assert "qwen2.5-7b" in mt_engines
    assert by_id(specs, "qwen2.5-3b").capabilities["available"] is False
    assert "qwen2.5-3b" not in mt_engines


def test_inprocess_availability_does_not_depend_on_ollama(harness):
    """I-1, nhánh `runtime == "inprocess"`: engine dựng tại chỗ phục vụ được job
    mà không cần tiến trình ngoài nào, nên `available` là True kể cả khi Ollama
    tắt và chưa pull gì.

    Đối chứng nằm ngay trong bài: CÙNG lần dựng đó, mọi engine `ollama` đều
    không sẵn sàng. Thiếu vế thứ hai thì một `_mark_availability` trả `True` cho
    TẤT CẢ mọi engine vẫn xanh bài này.
    """
    harness.ollama_alive = False
    harness.pulled = set()
    _repos, specs, _worker, _broker, mt_engines = harness.build()

    inprocess = [s for s in of_kind(specs, "mt") if s.runtime == "inprocess"]
    assert inprocess, "registry.json phải còn engine in-process (opus-mt)"
    for spec in inprocess:
        assert spec.capabilities["available"] is True, (
            f"{spec.id} in-process không có tiến trình ngoài nào để hỏi"
        )
        assert spec.id in mt_engines

    ollama_specs = [s for s in of_kind(specs, "mt") if s.runtime == "ollama"]
    assert ollama_specs, "registry.json phải còn engine ollama để đối chứng"
    assert all(s.capabilities["available"] is False for s in ollama_specs), (
        "cùng lần dựng: Ollama chết thì engine ollama phải KHÔNG sẵn sàng"
    )


def test_real_probe_tolerates_both_answers(tmp_path, monkeypatch):
    """Correction G: Ollama ĐANG chạy trên máy này nên `available` sẽ là True.

    Bài này cố ý KHÔNG vá `ollama_available`, nên nó phải xanh trên cả máy có
    Ollama lẫn máy không có — không được hardcode giá trị nào.

    Fix round 1 (I-1): phép dò nay trả TÊN model đã pull (có thể là `set()`), nên
    khẳng định dưới đây bám vào quan hệ `available ⇔ id có trong mt_engines`,
    đúng cả khi máy này chỉ pull một phần registry.
    """
    from app import config, main

    before = _snapshot()
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(config, "LOG_DIR", data / "logs")
    monkeypatch.setattr(config, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "DB_PATH", data / "app.db")
    monkeypatch.setattr(main, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(main, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "LOG_DIR", data / "logs")
    # Adapter nặng vẫn phải thay: dựng `OllamaMtEngine` thật là chuyện của
    # `test_real_mt_engines_are_constructible_from_the_shipped_registry`.
    monkeypatch.setattr(main, "OllamaMtEngine", _RecordingMtEngine)
    monkeypatch.setattr(main, "OpusMtEngine", _RecordingMtEngine)

    _repos, specs, _worker, _broker, engines = main.build_components()
    _assert_repo_data_untouched(before)

    ollama_specs = [s for s in of_kind(specs, "mt") if s.runtime == "ollama"]
    assert ollama_specs, "registry.json phải còn engine ollama để bài này có nghĩa"
    assert all(s.capabilities.get("available") in (True, False) for s in ollama_specs)
    for spec in ollama_specs:
        assert (spec.id in engines) is spec.capabilities["available"], (
            f"{spec.id}: available={spec.capabilities['available']} nhưng "
            f"có trong mt_engines: {spec.id in engines}"
        )


# ---------------------------------------------------------------------------
# Handler + governor: hai dây nối mà Giai đoạn 1a đã từng quên một cái
# ---------------------------------------------------------------------------

def test_translate_handler_is_registered_with_the_same_engines_dict(harness):
    """Quên `mt_engines` khi dựng `TranslateHandler` là lớp lỗi của 1a.

    So `is` chứ không so nội dung: một dict chép lại vẫn "trông đúng" nhưng
    engine nạp trong handler sẽ không phải engine mà governor đổ model.
    """
    _repos, specs, worker, _broker, mt_engines = harness.build()

    handler = worker.handlers.get("translate")
    assert isinstance(handler, TranslateHandler), (
        f"composition root phải đăng ký TranslateHandler: {sorted(worker.handlers)}"
    )
    assert handler.handles() == "translate"
    assert handler._engines is mt_engines, (  # noqa: SLF001 - chính dây nối
        "handler phải nhận ĐÚNG dict mt_engines của build_components()"
    )
    assert set(mt_engines) == {s.id for s in of_kind(specs, "mt")
                               if s.capabilities.get("available")}


def test_governor_has_a_releaser_for_every_mt_phase(harness):
    """Thiếu vòng `governor.register(spec.phase_key, engine.release)` là bản sao
    của lỗi 1a: model dịch nằm mãi trong VRAM khi đổi giai đoạn, im lặng.
    """
    _repos, specs, worker, _broker, mt_engines = harness.build()
    governor = worker.governor

    for engine_id, engine in mt_engines.items():
        spec = by_id(specs, engine_id)
        phase = js.phase_of("translate", engine_id)
        assert phase == spec.phase_key, (
            f"khoá giai đoạn phải là {phase!r} (qua `spec.phase_key`), "
            f"không phải 'mt:{engine_id}'"
        )
        releaser = governor._loaded.get(phase)  # noqa: SLF001 - chính dây nối
        assert releaser is not None, f"governor không có releaser cho {phase!r}"
        assert getattr(releaser, "__self__", None) is engine, (
            "releaser đã đăng ký không phải `release` của engine trong mt_engines"
        )
        releaser()
        assert engine.releases == 1


def test_real_mt_engines_are_constructible_from_the_shipped_registry(tmp_path, monkeypatch):
    """Adapter THẬT, registry THẬT: dựng được và `release()` idempotent.

    Cờ glossary là DỮ LIỆU của `spec.capabilities["glossary_prompt"]` (correction
    B), không phải hằng số của adapter. Không lượt HTTP nào chạy ở đây: dựng
    `OllamaMtEngine` chỉ tạo client, và `release()` lúc chưa nạp là no-op.
    """
    from app import config, main
    from app.adapters.mt.ollama_mt import OllamaMtEngine
    from app.adapters.mt.opus_mt import OpusMtEngine

    before = _snapshot()
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(config, "LOG_DIR", data / "logs")
    monkeypatch.setattr(config, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "DB_PATH", data / "app.db")
    monkeypatch.setattr(main, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(main, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "LOG_DIR", data / "logs")
    # Fix round 1 (I-1): phép dò trả về TÊN model đã pull; ở đây pull ĐÚNG mọi
    # `model_ref` của registry để bài này dựng được adapter THẬT cho mọi engine.
    monkeypatch.setattr(main, "ollama_available", lambda *a, **k: _all_real_model_refs())

    _repos, specs, _worker, _broker, engines = main.build_components()
    _assert_repo_data_untouched(before)

    assert isinstance(engines["opus-mt"], OpusMtEngine)
    assert engines["opus-mt"].engine_id == "opus-mt"
    assert engines["opus-mt"].supports_glossary() is False

    three_b = engines["qwen2.5-3b"]
    assert isinstance(three_b, OllamaMtEngine)
    assert three_b.supports_glossary() is True, (
        "qwen2.5-3b khai glossary_prompt=true trong registry.json"
    )
    assert by_id(specs, "hy-mt-1.5-7b").capabilities["glossary_prompt"] is False
    assert engines["hy-mt-1.5-7b"].supports_glossary() is False, (
        "hy-mt-1.5-7b khai glossary_prompt=false: QA gắn engine_no_glossary theo "
        "cờ này, hardcode True là nói dối về engine"
    )
    for engine in engines.values():
        engine.release()        # chưa nạp gì: phải là no-op thật
        engine.release()
        assert isinstance(engine.supports_glossary(), bool)


def test_app_exposes_the_same_mt_engines_object(harness):
    repos, specs, worker, broker, mt_engines = harness.build()
    app = harness.main.build_app(repos, specs, worker, broker, mt_engines)
    assert app.state.mt_engines is mt_engines


# ---------------------------------------------------------------------------
# Hành vi mà review sẽ thử nặng nhất: bóc băng xong THẬT SỰ đẻ ra một job dịch
# với payload mà handler ăn được — đi qua `PhaseQueueWorker` + `SqliteRepos`
# ---------------------------------------------------------------------------

def test_a_finished_transcription_enqueues_a_translation_the_handler_consumes(
        harness, tmp_path):
    """Đường THẬT: `build_components()` -> worker thật -> repos thật -> handler thật.

    Không gán thẳng `job.cancel_requested` kiểu tự thoả mãn (F1 của Task 11),
    cũng không tự ráp lại `PhaseQueueWorker`: mọi dây là của production, chỉ
    adapter model là giả.
    """
    repos, specs, worker, _broker, mt_engines = harness.build()

    assert repos.get_setting("auto_forward") == "1", (
        "correction E: nay ĐÃ có handler `translate` nên mặc định phải BẬT"
    )

    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    sid = repos.add_source(kind="file", origin="a.mp4", media_path=str(wav),
                           lang="zh", audio_path=str(wav), duration=4.0)
    asr_engine = load_default_asr()
    repos.add_job(Job(id=None, workspace=1, type="asr", engine=asr_engine,
                      phase=js.phase_of("asr", asr_engine),
                      payload={"source_id": sid}))

    while worker.tick():
        pass

    transcript = repos.list_transcripts()[0]
    jobs = repos.list_jobs()
    translate_jobs = [j for j in jobs if j.type == "translate"]
    assert len(translate_jobs) == 1, (
        f"bóc băng xong phải có ĐÚNG một job dịch, nhận được "
        f"{[(j.type, j.state) for j in jobs]}"
    )
    job = translate_jobs[0]
    mt_engine_id = load_default_mt()

    assert set(job.payload) == {"translation_id", "transcript_id", "engine_id",
                                "source_lang", "target_lang"}, (
        "payload phải mang ĐÚNG những khoá `TranslateHandler.run` đọc; thừa/"
        f"thiếu khoá là job chết bằng KeyError ở tận worker: {job.payload}"
    )
    assert job.payload["transcript_id"] == transcript.id
    assert job.payload["engine_id"] == mt_engine_id
    assert job.payload["source_lang"] == "zh"
    assert job.payload["target_lang"] == TARGET_LANG
    assert job.engine == mt_engine_id
    assert job.phase == js.phase_of("translate", mt_engine_id)
    assert job.workspace == 2

    # Hàng `translations` phải được tạo TRƯỚC job, và trỏ ĐÚNG version nguồn.
    translation = repos.get_translation(job.payload["translation_id"])
    assert translation.transcript_id == transcript.id
    assert translation.transcript_version == transcript.version == 1, (
        "ghi nhầm 'version hiện tại' thay vì version đã dịch từ đó thì mọi bản "
        "dịch vừa xong đều trông lệch thời"
    )
    assert translation.target_lang == TARGET_LANG

    # Và đường dịch đã chạy THẬT qua handler của composition root.
    assert job.state == "done", (
        f"job dịch phải chạy xong qua TranslateHandler thật, trạng thái {job.state!r}: "
        f"{job.error}"
    )
    assert translation.status == "done", translation.status
    assert [s.i for s in translation.segments] == [s.i for s in transcript.segments]
    assert [s.text for s in translation.segments] == ["[vi] 你好", "[vi] 世界"]
    assert mt_engines[mt_engine_id].batches == [[0, 1]], (
        "engine dịch của chính composition root phải là cái đã được gọi"
    )


def test_auto_forward_default_is_on_but_a_user_choice_is_not_overwritten(harness):
    """Correction E: chỉ ghi khi CHƯA ai đặt."""
    repos, _specs, _worker, _broker, _engines = harness.build()
    assert repos.get_setting("auto_forward") == "1"

    repos.set_setting("auto_forward", "0")
    repos2, specs2, worker2, _broker2, _engines2 = harness.build()
    assert repos2.get_setting("auto_forward") == "0", (
        "build_components() không được đè lựa chọn của người dùng"
    )

    wav = harness.data / "media" / "b.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF")
    sid = repos2.add_source(kind="file", origin="b.mp4", media_path=str(wav),
                            lang="zh", audio_path=str(wav), duration=4.0)
    engine_id = load_default_asr()
    repos2.add_job(Job(id=None, workspace=1, type="asr", engine=engine_id,
                       phase=js.phase_of("asr", engine_id),
                       payload={"source_id": sid}))
    while worker2.tick():
        pass
    assert [j for j in repos2.list_jobs() if j.type == "translate"] == [], (
        "auto_forward='0' thì KHÔNG được đẻ job dịch"
    )


def test_translation_records_the_version_at_forward_time_not_one(harness):
    """M14 · `transcript_version=transcript.version` là dòng CHƯA BỊ BẮT BẺ.

    Review Task 12 đo được: hardcode `transcript_version=1` để **cả ba** bài liên
    quan xanh (`3 passed`), vì mọi bài đều chuyển tiếp một transcript còn ở
    version 1 — ở đó `1` và `transcript.version` là CÙNG một giá trị, nên phép
    khẳng định không phân biệt được hai thứ.

    Bài này tạo đúng chỗ hai giá trị TÁCH NHAU: thêm transcript (v1), SỬA nó qua
    `update_transcript_segments` (v2), rồi mới chuyển tiếp. Giá trị đúng là 2;
    hardcode `1` là đỏ.

    Vì sao đây không phải chi tiết vụn: `transcript_version` là cơ chế DUY NHẤT
    khiến một bản dịch cũ thành lỗi thời (`is_stale`). Ghim nhầm về 1 nghĩa là
    một bản dịch sinh ra từ bản đã sửa vẫn được coi là khớp thời, và người dùng
    không bao giờ được nhắc dịch lại.
    """
    repos, _specs, _worker, _broker, _engines = harness.build()
    handler = _worker.handlers["asr"]

    wav = harness.data / "media" / "v.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF")
    sid = repos.add_source(kind="file", origin="v.mp4", media_path=str(wav),
                           lang="zh", audio_path=str(wav), duration=4.0)
    tid = repos.add_transcript(
        source_id=sid, engine=load_default_asr(), lang="zh",
        segments=[Segment(i=0, start=0.0, end=1.0, text="你好")],
    )
    assert repos.get_transcript(tid).version == 1, "điểm xuất phát phải là v1"

    new_version = repos.update_transcript_segments(
        tid, [Segment(i=0, start=0.0, end=1.0, text="你好 (đã sửa)")])
    assert new_version == 2, f"update_transcript_segments phải tăng version: {new_version}"

    handler._forward_to_translation(tid, "zh")  # noqa: SLF001 - chính đường thật

    mt_jobs = [j for j in repos.list_jobs() if j.type == "translate"]
    assert len(mt_jobs) == 1, mt_jobs
    translation = repos.get_translation(mt_jobs[0].payload["translation_id"])
    assert translation.transcript_version == 2, (
        "bản dịch phải ghim version của transcript TẠI THỜI ĐIỂM chuyển tiếp "
        f"(2), không phải hằng số 1: nhận được {translation.transcript_version}"
    )
    assert translation.transcript_version == repos.get_transcript(tid).version, (
        "giá trị ghi vào hàng `translations` phải là version ĐỌC TỪ REPO"
    )


def test_a_forwarded_translation_records_the_glossary_version(harness):
    """M-4 · đường auto-forward phải GHIM `glossary_version`, không để NULL.

    `translations.glossary_version` có HAI người ghi cho cùng một trạng thái
    (hàng `queued`, 0 segment, job chưa chạy): `POST /api/translations` truyền
    `repos.glossary_version()`, còn `_forward_to_translation` thì KHÔNG truyền —
    `add_translation` nhận mặc định `None` và cột thành NULL. Nghĩa của cột vì
    thế phụ thuộc vào ĐƯỜNG NÀO tạo ra hàng, không phải vào dữ liệu.

    Đặt `glossary_version` = 7 TRƯỚC khi chuyển tiếp: mặc định là 0, và `0` không
    phân biệt được "ghi đúng nguồn" với "hardcode 0".

    Đo ở ĐÚNG MỘT nhịp worker: `tick()` chạy đúng một job, nên sau nhịp này hàng
    `translations` đã được đường forward ghi, còn job `translate` vẫn `queued` —
    chưa bị `TranslateHandler` (`set_translation_status(..., glossary_version=…)`)
    ghi đè. Chạy hết hàng đợi rồi mới đọc thì cả một bản vá để NULL cũng xanh.
    """
    repos, _specs, worker, _broker, _engines = harness.build()
    assert repos.get_setting("auto_forward") == "1", (
        "bài này đo đường auto-forward, nên nó phải đang BẬT"
    )
    repos.set_setting("glossary_version", "7")

    wav = harness.data / "media" / "g.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF")
    sid = repos.add_source(kind="file", origin="g.mp4", media_path=str(wav),
                           lang="zh", audio_path=str(wav), duration=4.0)
    asr_engine = load_default_asr()
    asr_job = Job(id=None, workspace=1, type="asr", engine=asr_engine,
                  phase=js.phase_of("asr", asr_engine), payload={"source_id": sid})
    asr_job.id = repos.add_job(asr_job)

    assert worker.tick() is True, "nhịp này phải chạy job bóc băng"
    assert repos.get_job(asr_job.id).state == "done", (
        f"job bóc băng phải xong ở nhịp này: {repos.get_job(asr_job.id).state}"
    )

    mt_jobs = [j for j in repos.list_jobs() if j.type == "translate"]
    assert len(mt_jobs) == 1, f"bóc băng xong phải có ĐÚNG một job dịch: {mt_jobs}"
    assert mt_jobs[0].state == "queued", (
        "job dịch chưa được chạy ở nhịp này — nếu nó đã `done` thì phép đo dưới "
        "đây đang đọc giá trị do TranslateHandler ghi, không phải của đường forward"
    )

    translation = repos.get_translation(mt_jobs[0].payload["translation_id"])
    assert translation.glossary_version == 7, (
        "hàng `translations` do auto-forward tạo phải ghim `glossary_version` "
        f"lúc tạo (7), không phải NULL: nhận được {translation.glossary_version!r}"
    )
    assert translation.glossary_version == repos.glossary_version(), (
        "giá trị phải lấy từ CÙNG nguồn với đường API (`repos.glossary_version()`)"
    )


# ---------------------------------------------------------------------------
# registry.json: correction C nói KHÔNG sửa — nên phải ghim rằng nó đã đủ
# ---------------------------------------------------------------------------

def test_shipped_registry_already_declares_every_mt_engine_this_wiring_needs():
    """Correction C: `registry.json` không có khoá `engines`, nó có `asr`/`mt`.

    Mảng `mt` đã đủ bốn engine kèm `capabilities`, và `default_mt` đã là
    `opus-mt` — nên Step 3 của brief là NHÂN BẢN ENTRY, không được làm.
    """
    from app import config

    raw = json.loads(pathlib.Path(config.REGISTRY_PATH).read_text(encoding="utf-8"))
    assert "engines" not in raw, "registry.json không có khoá `engines` (correction C)"
    assert raw["default_mt"] == "opus-mt"
    ids = [entry["id"] for entry in raw["mt"]]
    assert ids == ["opus-mt", "qwen2.5-3b", "qwen2.5-7b", "hy-mt-1.5-7b"], ids
    for entry in raw["mt"]:
        assert "available" not in entry, (
            "`available` là thứ DÒ LÚC DỰNG (correction B), không phải hằng số "
            "viết tay trong registry.json"
        )
        assert entry["runtime"] in ("inprocess", "ollama")
        assert entry["model_ref"]
