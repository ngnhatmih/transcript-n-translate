"""HÌNH DẠNG của cổng `MtEngine`: ba THUỘC TÍNH và một METHOD.

Sự cố ĐO ĐƯỢC (stack thật, engine `deepseek-web` là hàng `runtime: http` đầu tiên):
`OpenAiChatMt` khai `engine_id`/`model_ref`/`prompt_version` là **method**, trong khi
`OpusMtEngine` và `OllamaMtEngine` khai chúng là **`@property`**. Hai chỗ đọc chúng theo
kiểu thuộc tính nên nhận về BOUND METHOD:

* `TranslateHandler._record_call`: `getattr(engine, "model_ref", None)` → ghi vào cột
  `llm_calls.model_ref` ⇒

      sqlite3.InterfaceError: Error binding parameter 2 - probably unsupported type.

  tức MỌI job `translate` bằng engine đó chết ngay lô đầu (đo được: job #1 `failed`, 0/60
  đoạn, log `LỖI: Error binding parameter 2 - probably unsupported type.`);
* `chimera.py`: `str(getattr(engine, "prompt_version", ...))` ⇒ ghi
  `"<bound method ...>"` vào phiên Chimera mà **không** báo lỗi.

🔴 Vì sao 63 bài test của chính adapter đó vẫn XANH: chúng gọi theo hình dạng SAI
(`engine.model_ref()`), và spike đo trên một repo GIẢ trong bộ nhớ nên bound method không
bao giờ chạm sqlite. Một bài ghim HÌNH DẠNG (bài này) là thứ duy nhất bắt được lớp lỗi đó,
vì "test xanh" ở đây chỉ nói rằng test đồng ý với lỗi.
"""
from __future__ import annotations

import inspect

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.mt.chimera_merge import OllamaMergeEngine
from app.adapters.mt.ollama_mt import OllamaMtEngine
from app.adapters.mt.openai_chat_mt import OpenAiChatMt
from app.adapters.mt.opus_mt import OpusMtEngine
from app.adapters.persist.sqlite_repos import SqliteRepos

#: Mọi adapter MT của sản phẩm. Thêm engine mới thì thêm vào đây — đó là chỗ duy nhất
#: liệt kê chúng, và một adapter lọt khỏi danh sách này là một adapter không được ghim.
ADAPTERS = (OpusMtEngine, OllamaMtEngine, OllamaMergeEngine, OpenAiChatMt)

#: Ba thành viên mà người đọc coi là THUỘC TÍNH (`getattr(engine, ...)`, không gọi).
#: `prompt_version` là TUỲ CHỌN (OpusMtEngine không khai: nó không có prompt), nhưng khai
#: thì phải khai đúng hình dạng.
THUOC_TINH = ("engine_id", "model_ref", "prompt_version")
#: Thành viên DUY NHẤT phải là method — mọi chỗ gọi đều gọi nó: `engine.supports_glossary()`.
METHOD = "supports_glossary"


@pytest.mark.parametrize("cls", ADAPTERS, ids=lambda c: c.__name__)
def test_ba_thanh_vien_la_thuoc_tinh_chu_khong_phai_method(cls):
    for ten in THUOC_TINH:
        raw = inspect.getattr_static(cls, ten, None)
        if raw is None:
            assert ten != "engine_id" and ten != "model_ref", (
                f"{cls.__name__} phải khai `{ten}` — hai chỗ trong handler đọc nó bằng "
                "`getattr`, nên thiếu nó thì không có gì để đọc"
            )
            continue  # `prompt_version` tuỳ chọn
        assert isinstance(raw, property), (
            f"{cls.__name__}.{ten} phải là `@property`, đang là {type(raw).__name__}. "
            "Hai chỗ đọc nó KHÔNG gọi: `TranslateHandler._record_call` (ghi "
            "`llm_calls.model_ref`) và `chimera.py` (`str(getattr(engine, "
            "`prompt_version`, ...))`). Một method ở đây làm job translate chết với "
            "`sqlite3.InterfaceError: Error binding parameter 2`."
        )


@pytest.mark.parametrize("cls", ADAPTERS, ids=lambda c: c.__name__)
def test_supports_glossary_la_method(cls):
    raw = inspect.getattr_static(cls, METHOD, None)
    assert raw is not None, f"{cls.__name__} phải khai `{METHOD}`"
    assert not isinstance(raw, property), (
        f"{cls.__name__}.{METHOD} phải là METHOD: mọi chỗ gọi đều gọi nó "
        "(`engine.supports_glossary()`), nên một `@property` ở đây sẽ ném "
        "`TypeError: 'bool' object is not callable`."
    )


def test_engine_http_doc_duoc_bang_getattr_va_ghi_duoc_vao_sqlite(tmp_path):
    """Đúng đường đã chết: `getattr(engine, "model_ref")` rồi bind vào cột sqlite.

    Bài này KHÔNG gọi `engine.model_ref()`. Nó đi đúng đường của `_record_call`, nên nó
    đỏ trên bản `def model_ref(self)` dù mọi bài khác của adapter vẫn xanh.
    """
    engine = OpenAiChatMt("deepseek-web", base_url="http://127.0.0.1:1/v1",
                          engine_id="deepseek-web", supports_glossary=False)
    assert isinstance(engine.model_ref, str) and engine.model_ref == "deepseek-web"
    assert isinstance(engine.prompt_version, str) and engine.prompt_version
    assert engine.engine_id == "deepseek-web"
    # `supports_glossary` ĐI THEO cờ được truyền vào (`capabilities.glossary_prompt` của
    # hàng registry), không phải cờ cứng trong adapter.
    assert engine.supports_glossary() is False

    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    repos.add_llm_call(
        job_id=None, engine=engine.engine_id,
        model_ref=getattr(engine, "model_ref", None),
        prompt_version=getattr(engine, "prompt_version", None),
        tokens_in=1, tokens_out=1, duration_ms=None, ok=True, error=None,
    )
    calls = repos.list_llm_calls()
    assert calls[0]["model_ref"] == "deepseek-web", (
        f"`llm_calls.model_ref` phải là TÊN MODEL, đo được {calls[0]['model_ref']!r}"
    )
