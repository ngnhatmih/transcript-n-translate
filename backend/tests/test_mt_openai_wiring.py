"""Nối dây engine `runtime == "http"`: dò endpoint, dựng adapter, nhãn prompt.

Ba câu hỏi, mỗi câu một nhóm bài:

* **Endpoint này phục vụ được job NGAY BÂY GIỜ không** — `available` phải là câu
  trả lời thật (endpoint trả lời VÀ khai đúng `model_ref` VÀ khoá API có trong
  biến môi trường), không phải "dòng cấu hình có tồn tại". Cùng lớp lỗi I-3 mà
  engine ASR và Ollama đã trả giá: khai sẵn sàng rồi job chết ở tận worker.
* **Dựng engine từ ĐÚNG hàng registry** — endpoint, hợp đồng, khoá đọc từ
  `opts`; không hard-code, và một hàng thiếu `base_url` phải ỒN.
* **Nhãn `prompt_version`** — engine `http` không có tên trong `PROMPT_VERSION`,
  nên rơi về "unknown" là ghi một nhãn SAI cho một prompt có tên.
"""
import dataclasses

import pytest

from app import main
from app.adapters.mt.openai_chat_mt import OpenAiChatMt
from app.adapters.mt.prompts import PROMPT_VERSION
from app.registry import EngineSpec, openai_models_available


def http_spec(**over) -> EngineSpec:
    base = dict(
        id="api-dich", label="API dịch", kind="mt", runtime="http",
        model_ref="deepseek-chat", vram_mb=0, langs=("zh", "en"),
        capabilities={"glossary_prompt": True},
        opts={"base_url": "https://api.example.test/v1", "contract": "lines"},
    )
    base.update(over)
    return EngineSpec(**base)


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _Client:
    def __init__(self, resp):
        self.resp = resp
        self.requests = []

    def get(self, url, headers=None):
        self.requests.append({"url": url, "headers": headers})
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


# -- dò endpoint ------------------------------------------------------------
def test_models_are_read_from_the_openai_data_list():
    client = _Client(_Resp({"object": "list",
                            "data": [{"id": "deepseek-chat"},
                                     {"id": "deepseek-reasoner"}]}))
    names = openai_models_available("https://api.example.test/v1", client=client)
    assert names == {"deepseek-chat", "deepseek-reasoner"}
    assert client.requests[0]["url"] == "https://api.example.test/v1/models"


def test_api_key_travels_in_the_header_only():
    client = _Client(_Resp({"data": [{"id": "m"}]}))
    openai_models_available("https://api.example.test/v1", api_key="sk-x",
                            client=client)
    assert client.requests[0]["headers"]["Authorization"] == "Bearer sk-x"
    assert "sk-x" not in client.requests[0]["url"]


@pytest.mark.parametrize("resp", [
    _Resp({"data": [{"id": "m"}]}, status=401),
    _Resp({"data": "không phải list"}),
    _Resp(ValueError("JSON hỏng")),
    RuntimeError("cổng đóng"),
])
def test_any_failure_means_empty_set_never_an_exception(resp):
    """"Không trả lời được" và "trả lời nhưng không có model" cho CÙNG câu trả
    lời — cả hai đều nghĩa là engine chưa phục vụ được."""
    assert openai_models_available("https://api.example.test/v1",
                                   client=_Client(resp)) == set()


# -- available --------------------------------------------------------------
def _mark(monkeypatch, specs, *, models):
    calls = []

    def fake_probe(base_url, api_key=None, timeout=1.5, client=None):
        calls.append(base_url)
        return set(models)

    monkeypatch.setattr(main, "openai_models_available", fake_probe)
    main._mark_availability(specs)
    return calls


def test_http_engine_is_available_when_the_endpoint_declares_its_model(monkeypatch):
    spec = http_spec()
    calls = _mark(monkeypatch, [spec], models={"deepseek-chat"})
    assert spec.capabilities["available"] is True
    assert calls == ["https://api.example.test/v1"]


def test_http_engine_is_not_available_when_the_model_is_missing(monkeypatch):
    spec = http_spec()
    _mark(monkeypatch, [spec], models={"deepseek-reasoner"})
    assert spec.capabilities["available"] is False


def test_missing_base_url_is_unavailable_and_does_not_raise(monkeypatch):
    """Một dòng cấu hình chưa điền đủ thì engine "chưa sẵn sàng", không phải
    lý do để cả tiến trình không dựng được: người dùng còn engine khác."""
    spec = http_spec(opts={})
    _mark(monkeypatch, [spec], models={"deepseek-chat"})
    assert spec.capabilities["available"] is False


def test_missing_api_key_environment_variable_is_unavailable(monkeypatch):
    monkeypatch.delenv("SPIKE_TEST_KEY", raising=False)
    spec = http_spec(opts={"base_url": "https://api.example.test/v1",
                           "api_key_env": "SPIKE_TEST_KEY"})
    _mark(monkeypatch, [spec], models={"deepseek-chat"})
    assert spec.capabilities["available"] is False


def test_present_api_key_environment_variable_makes_it_available(monkeypatch):
    monkeypatch.setenv("SPIKE_TEST_KEY", "sk-x")
    spec = http_spec(opts={"base_url": "https://api.example.test/v1",
                           "api_key_env": "SPIKE_TEST_KEY"})
    _mark(monkeypatch, [spec], models={"deepseek-chat"})
    assert spec.capabilities["available"] is True


def test_two_rows_on_the_same_endpoint_are_probed_once(monkeypatch):
    first = http_spec()
    second = http_spec(id="api-dich-2")
    calls = _mark(monkeypatch, [first, second], models={"deepseek-chat"})
    assert calls == ["https://api.example.test/v1"]
    assert first.capabilities["available"] is second.capabilities["available"] is True


def test_inprocess_stays_available_without_any_probe(monkeypatch):
    spec = dataclasses.replace(http_spec(), id="opus-2", runtime="inprocess",
                               opts={}, capabilities={})
    calls = _mark(monkeypatch, [spec], models=set())
    assert spec.capabilities["available"] is True
    assert calls == []


# -- dựng engine ------------------------------------------------------------
def _available(spec) -> EngineSpec:
    spec.capabilities["available"] = True
    return spec


def test_engine_is_built_from_the_registry_row(monkeypatch):
    spec = _available(http_spec())
    engines = main._build_mt_engines([spec])
    engine = engines["api-dich"]
    assert isinstance(engine, OpenAiChatMt)
    assert engine.engine_id() == "api-dich"
    assert engine.model_ref() == "deepseek-chat"
    assert engine.prompt_version() == "openai-lines-p1"
    assert engine.supports_glossary() is True       # từ `capabilities.glossary_prompt`


def test_contract_defaults_to_json_when_the_row_does_not_say(monkeypatch):
    spec = _available(http_spec(opts={"base_url": "https://api.example.test/v1"}))
    engine = main._build_mt_engines([spec])["api-dich"]
    assert engine.prompt_version() == "openai-json-p1"


def test_missing_base_url_is_loud_when_building(monkeypatch):
    spec = _available(http_spec(opts={}))
    with pytest.raises(RuntimeError, match="base_url"):
        main._build_mt_engines([spec])


def test_missing_key_is_loud_when_building(monkeypatch):
    monkeypatch.delenv("SPIKE_TEST_KEY", raising=False)
    spec = _available(http_spec(opts={"base_url": "https://api.example.test/v1",
                                      "api_key_env": "SPIKE_TEST_KEY"}))
    with pytest.raises(RuntimeError, match="SPIKE_TEST_KEY"):
        main._build_mt_engines([spec])


def test_unknown_runtime_is_loud_instead_of_falling_back_to_opus(monkeypatch):
    """Một runtime lạ mà lặng lẽ thành `opus-mt` là chạy một model khác với cái
    registry khai — đúng loại âm thầm mà `default_mt_engine` đã bịt."""
    spec = _available(http_spec(runtime="grpc"))
    with pytest.raises(RuntimeError, match="grpc"):
        main._build_mt_engines([spec])


def test_unavailable_engine_is_not_built(monkeypatch):
    spec = http_spec()
    spec.capabilities["available"] = False
    assert main._build_mt_engines([spec]) == {}


# -- nhãn prompt_version ----------------------------------------------------
def test_http_prompt_version_follows_the_contract():
    assert main._prompt_version_of(http_spec()) == "openai-lines-p1"
    assert main._prompt_version_of(
        http_spec(opts={"base_url": "u", "contract": "json"})) == "openai-json-p1"


def test_measured_engines_still_read_the_measured_table():
    spec = http_spec(id="hy-mt-1.5-7b", runtime="ollama")
    assert main._prompt_version_of(spec) == PROMPT_VERSION["hy-mt-1.5-7b"]


def test_an_engine_nothing_measured_is_honestly_unknown():
    spec = http_spec(id="chua-do", runtime="ollama")
    assert main._prompt_version_of(spec) == "unknown"
