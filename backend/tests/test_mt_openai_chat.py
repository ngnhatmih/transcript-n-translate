"""`OpenAiChatMt`: giao thức, hợp đồng đầu ra, và những gì nó KHÔNG gửi.

Ba nhóm được ghim ở đây, mỗi nhóm vì một cách sai khác nhau:

* **Thân yêu cầu** — endpoint OpenAI-compatible nhận `model`/`messages`/`stream`;
  `temperature`, `max_tokens`, `response_format` chỉ được gửi khi có yêu cầu rõ
  ràng, vì một cổng web không có tương đương cho chúng. Một artifact ghi
  "temperature=0" trong khi endpoint bỏ qua tham số đó là artifact nói dối.
* **Phân loại lỗi** — `raise_for_status()` phải chạy TRƯỚC `json()`, để một 500
  kèm thân lỗi ném ra HTTPStatusError (đọc được trong log) thay vì JSONDecodeError.
* **Hai hợp đồng** — `json` đi qua `parse_batch_response`, `lines` đi qua
  `parse_lines_response`; chọn sai hợp đồng phải ồn ngay ở constructor.
"""
import pytest

from app.adapters.mt.openai_chat_mt import OpenAiChatMt
from app.adapters.mt.prompts import (parse_batch_response,
                                     parse_lines_response)
from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term
from app.domain.mt import MtOpts

BASE_URL = "http://127.0.0.1:8790/v1"
MODEL = "deepseek-chat"


class _Resp:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            request = httpx.Request("POST", BASE_URL + "/chat/completions")
            response = httpx.Response(self.status_code, request=request,
                                      text=self.text)
            raise httpx.HTTPStatusError("HTTP %d" % self.status_code,
                                        request=request, response=response)

    def json(self):
        return self._payload


class _FakeClient:
    """Ghi lại đúng thân/lời gọi đã gửi; hết kịch bản là NÉM, không trả bừa."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.requests = []

    def post(self, url, *, json=None, headers=None, timeout=None):
        self.requests.append({"url": url, "json": json, "headers": headers,
                              "timeout": timeout})
        if not self._replies:
            raise AssertionError("engine gọi HTTP ngoài kịch bản của bài test")
        return self._replies.pop(0)


def reply(content: str, *, pin=120, pout=60) -> _Resp:
    return _Resp({"choices": [{"message": {"role": "assistant",
                                           "content": content}}],
                  "usage": {"prompt_tokens": pin, "completion_tokens": pout}})


def seg(i: int, text: str = "nguồn") -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text, speaker="S1")


def engine(client, **kwargs) -> OpenAiChatMt:
    return OpenAiChatMt(MODEL, base_url=BASE_URL, engine_id="openai-compat-spike",
                        client=client, **kwargs)


# -- thân yêu cầu -----------------------------------------------------------
def test_request_hits_the_chat_completions_path_with_the_configured_model():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"một"}]}')])
    engine(client).translate([seg(1)], [], MtOpts(source_lang="zh"))
    assert client.requests[0]["url"] == BASE_URL + "/chat/completions"
    assert client.requests[0]["json"]["model"] == MODEL
    assert client.requests[0]["json"]["stream"] is False


def test_no_sampling_or_format_parameters_are_sent_by_default():
    """Cổng web không có tương đương cho ba tham số này; gửi chúng là hứa một thứ
    mình không điều khiển được."""
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"một"}]}')])
    engine(client).translate([seg(1)], [], MtOpts(source_lang="zh"))
    body = client.requests[0]["json"]
    for key in ("temperature", "max_tokens", "response_format"):
        assert key not in body


def test_parameters_are_sent_when_explicitly_asked_for():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"một"}]}')])
    eng = engine(client, json_mode="object", max_tokens=1024,
                 temperature=0.0, reasoning_effort="none")
    eng.translate([seg(1)], [], MtOpts(source_lang="zh"))
    body = client.requests[0]["json"]
    assert body["max_tokens"] == 1024
    assert body["response_format"] == {"type": "json_object"}
    assert body["reasoning_effort"] == "none"
    assert body["temperature"] == 0.0


def test_api_key_becomes_a_bearer_header_and_never_enters_the_body():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"một"}]}')])
    engine(client, api_key="sk-test").translate([seg(1)], [], MtOpts(source_lang="zh"))
    request = client.requests[0]
    assert request["headers"]["Authorization"] == "Bearer sk-test"
    assert "sk-test" not in str(request["json"])


def test_without_api_key_there_is_no_authorization_header():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"một"}]}')])
    engine(client).translate([seg(1)], [], MtOpts(source_lang="zh"))
    assert "Authorization" not in client.requests[0]["headers"]


# -- hai hợp đồng -----------------------------------------------------------
def test_json_contract_goes_through_the_json_parser():
    payload = '{"translations":[{"i":1,"text":"một"}]}'
    client = _FakeClient([reply(payload)])
    out = engine(client).translate([seg(1)], [], MtOpts(source_lang="zh"))
    assert [s.text for s in out] == ["một"]
    # Cùng chuỗi phản hồi, cùng parser: đây là đường đang ship.
    assert [s.text for s in parse_batch_response(payload, [seg(1)])] == ["một"]


def test_lines_contract_goes_through_the_lines_parser_and_its_prompt():
    client = _FakeClient([reply("1\tmột\n2\thai")])
    eng = engine(client, contract="lines")
    out = eng.translate([seg(1), seg(2)], [], MtOpts(source_lang="zh"))
    assert [s.text for s in out] == ["một", "hai"]
    user_message = client.requests[0]["json"]["messages"][1]["content"]
    assert "1\tnguồn" in user_message          # khối dữ liệu cũng bằng dòng
    assert "JSON" not in user_message
    assert [s.text for s in parse_lines_response("1\tmột\n2\thai",
                                                 [seg(1), seg(2)])] == ["một", "hai"]


def test_lines_contract_rejects_json_shaped_output_loudly():
    """Model tự trả JSON khi prompt đòi dòng: mọi dòng đều không mang id → thiếu
    dòng → `AlignmentProblem`, không phải một bản dịch rỗng."""
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"một"}]}')])
    with pytest.raises(AlignmentProblem):
        engine(client, contract="lines").translate([seg(1)], [],
                                                   MtOpts(source_lang="zh"))


def test_unknown_contract_or_json_mode_is_loud_at_construction():
    client = _FakeClient([])
    with pytest.raises(ValueError):
        engine(client, contract="yaml")
    with pytest.raises(ValueError):
        engine(client, json_mode="strict")


# -- lỗi --------------------------------------------------------------------
def test_http_error_is_raised_as_http_status_error_not_json_error():
    import httpx
    client = _FakeClient([_Resp({}, status=500, text='{"error":"boom"}')])
    with pytest.raises(httpx.HTTPStatusError):
        engine(client).translate([seg(1)], [], MtOpts(source_lang="zh"))


def test_empty_content_is_an_error():
    client = _FakeClient([reply("   ")])
    with pytest.raises(ValueError):
        engine(client).translate([seg(1)], [], MtOpts(source_lang="zh"))


def test_stats_carry_token_counts_from_the_usage_block():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"một"}]}',
                                pin=111, pout=47)])
    eng = engine(client)
    eng.translate([seg(1)], [], MtOpts(source_lang="zh"))
    assert eng.last_stats is not None
    assert (eng.last_stats.tokens_in, eng.last_stats.tokens_out) == (111, 47)
    # Thời lượng phải do CHÍNH adapter đo: endpoint OpenAI-compatible không trả
    # `total_duration` như Ollama, nên trước bản vá này `llm_calls.duration_ms` LUÔN NULL cho
    # mọi job `http` — đo được trên DB thật: 18 lời gọi `deepseek-web` có token đủ mà `ms`
    # rỗng hết, tức nửa "chi phí" của engine đó không đọc được.
    assert isinstance(eng.last_stats.duration_ms, int), (
        f"duration_ms phải là số mili giây, đo được {eng.last_stats.duration_ms!r}")
    assert eng.last_stats.duration_ms >= 0


def test_empty_batch_never_touches_the_network():
    client = _FakeClient([])
    assert engine(client).translate([], [], MtOpts(source_lang="zh")) == []
    assert client.requests == []


def test_release_is_a_noop_that_sends_nothing():
    """Endpoint tự quản VRAM của nó; gửi 'unload' từ đây chỉ có thể làm hỏng phiên
    của người khác."""
    client = _FakeClient([])
    engine(client).release()
    assert client.requests == []


# -- hợp đồng `MtEngine` ----------------------------------------------------
def test_engine_identity_comes_from_the_constructor():
    eng = engine(_FakeClient([]))
    assert eng.engine_id == "openai-compat-spike"
    assert eng.model_ref == MODEL
    assert eng.prompt_version == "openai-json-p1"
    assert eng.supports_glossary() is True


def test_lines_contract_has_its_own_prompt_version():
    """Prompt của hợp đồng `lines` không thuộc bộ `V0..V3` đã đo, nên nó không được
    mang nhãn của bộ đó."""
    eng = engine(_FakeClient([]), contract="lines")
    assert eng.prompt_version == "openai-lines-p1"


def test_glossary_can_be_switched_off_per_engine():
    term = Term(id="t1", lang="zh", term="烟台山",
                translation="Yên Đài Sơn")
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"một"}]}')])
    engine(client, supports_glossary=False).translate([seg(1)], [term],
                                                      MtOpts(source_lang="zh"))
    assert "烟台山" not in str(client.requests[0]["json"]["messages"])
