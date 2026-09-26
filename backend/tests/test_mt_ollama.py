"""`OllamaMtEngine`: HTTP tới tiến trình Ollama, JSON, token count, release idempotent.

Client HTTP được TIÊM vào nên cả suite chạy được khi Ollama TẮT, và không bài nào
chạm mạng. Hình dạng phản hồi dưới đây chép từ phản hồi THẬT đã đo (Ollama 0.34.4,
`POST /api/chat` với `stream: false`, `format: "json"`):

    {"model":"qwen2.5:3b-instruct-q4_K_M","created_at":"...",
     "message":{"role":"assistant","content":"{\\"translations\\":[...]}"},
     "done":true,"done_reason":"stop","total_duration":1796970500,
     "load_duration":1673775100,"prompt_eval_count":47,"prompt_eval_cached_count":0,
     "prompt_eval_duration":38314000,"eval_count":13,"eval_duration":82710000}

Ba hệ quả được ghim ở đây chứ không phải giả định: nội dung nằm ở `message.content`;
số token ở `prompt_eval_count`/`eval_count`; `total_duration` là NANÔ giây. Và phản
hồi ĐỔ model (`keep_alive: 0`) chỉ có `done_reason: "unload"` — không token, không
thời lượng — nên parser phải chịu được payload thiếu khoá.
"""
import dataclasses

import pytest

from app.adapters.mt.ollama_mt import OllamaMtEngine
from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term, Word
from app.domain.mt import MtOpts

#: Đúng `model_ref` của engine `qwen2.5-3b` trong `backend/registry.json`. Test dùng
#: chính chuỗi này chứ không dùng mặc định của adapter, để mặc định đổi mà không
#: khớp registry thì có bài đỏ.
REGISTRY_MODEL_REF = "qwen2.5:3b-instruct-q4_K_M"

#: `total_duration` đo được của lần gọi đầu (1,80 s, trong đó 1,67 s là nạp model).
MEASURED_TOTAL_DURATION_NS = 1_796_970_500


class _Resp:
    """Tối thiểu những gì engine dùng: `raise_for_status()` và `json()`."""

    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    """Ghi lại ĐÚNG những gì engine gửi đi, trả lần lượt `replies`.

    Gọi HTTP ngoài kịch bản (hết `replies`) là NÉM kèm mô tả, không trả bừa: đó là
    cách `release()` lúc chưa nạp bị bắt quả tang nếu nó lỡ POST.
    """

    def __init__(self, replies=(), *, fail_on=(), error=None):
        self._replies = list(replies)
        self._fail_on = set(fail_on)          # số thứ tự lượt gọi (1-based) sẽ NÉM
        self._error = error or RuntimeError("mạng hỏng")
        self.bodies: list[dict] = []
        self.calls = 0

    def post(self, url, json=None, timeout=None):
        self.calls += 1
        self.bodies.append({"url": url, "json": json, "timeout": timeout})
        if self.calls in self._fail_on:
            raise self._error
        if not self._replies:
            raise AssertionError(
                f"engine gọi HTTP ngoài kịch bản (lượt {self.calls}): {url} {json!r}")
        # Payload trần được bọc thành phản hồi; `_Resp` dựng sẵn (ca lỗi HTTP) thì
        # giữ nguyên, để bài 500 kiểm được `raise_for_status` của chính nó.
        reply = self._replies.pop(0)
        return reply if isinstance(reply, _Resp) else _Resp(reply)


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text, speaker="S1")


def reply(content: str, *, pin=11, pout=22, total=MEASURED_TOTAL_DURATION_NS) -> dict:
    """Phản hồi `/api/chat` theo SỐ ĐO. `total=None` để bỏ hẳn khoá thời lượng."""
    payload = {
        "model": REGISTRY_MODEL_REF,
        "created_at": "2026-09-26T12:06:08.9371063Z",
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": "stop",
        "load_duration": 1673775100,
        "prompt_eval_count": pin,
        "prompt_eval_cached_count": 0,
        "prompt_eval_duration": 38314000,
        "eval_count": pout,
        "eval_duration": 82710000,
    }
    if total is not None:
        payload["total_duration"] = total
    return payload


def unload_reply() -> dict:
    """Phản hồi thật của lượt đổ model — không token, không thời lượng."""
    return {"model": REGISTRY_MODEL_REF,
            "message": {"role": "assistant", "content": ""},
            "done": True, "done_reason": "unload"}


def engine(client: object, **kw) -> OllamaMtEngine:
    return OllamaMtEngine(model=REGISTRY_MODEL_REF, client=client, **kw)


def one_batch_reply(text: str = "x") -> dict:
    return reply('{"translations":[{"i":1,"text":"' + text + '"}]}')


def unload_bodies(client: _FakeClient) -> list[dict]:
    return [b for b in client.bodies if b["json"].get("keep_alive") == 0]


# --- định danh engine: KHÔNG được suy từ `split(":")[0]` ------------------------

def test_engine_id_comes_from_the_registry_model_ref():
    """`registry.json` ghi model_ref `qwen2.5:3b-instruct-q4_K_M`, còn `id` engine là
    `qwen2.5-3b`. `model.split(":")[0]` — cách bản plan viết — cho ra `qwen2.5`, tức
    lệch cả id registry lẫn khoá `PROMPT_VERSION`."""
    assert engine(_FakeClient()).engine_id == "qwen2.5-3b"


def test_engine_id_scales_to_the_7b_sibling():
    """Cùng lớp này phục vụ `qwen2.5-7b` (registry.json và PROMPT_VERSION đều có id
    đó), nên id phải SUY từ tag chứ không được là hằng số."""
    eng = OllamaMtEngine(model="qwen2.5:7b-instruct-q4_K_M", client=_FakeClient())
    assert eng.engine_id == "qwen2.5-7b"


def test_hy_mt_tag_is_not_reproducible_so_callers_must_key_by_spec_id():
    """GIỚI HẠN đã biết của quy tắc suy id: nó hiệu chỉnh cho tag của Qwen. Tag thật
    của HY-MT (`registry.json:84` ghi id `hy-mt-1.5-7b`) KHÔNG tái tạo được, nên
    `prompt_version` rơi về "unknown".

    Bài này ghim giới hạn đó bằng TEST chứ không để nó sống trong docstring: Task 12
    PHẢI đánh khoá `mt_engines` bằng `spec.id`, và KHÔNG được dùng `engine_id` hay
    `prompt_version` làm khoá cho `translations`/`llm_calls`."""
    eng = OllamaMtEngine(model="hy-mt1.5-7b:q4_K_M", client=_FakeClient())
    assert eng.engine_id == "hy-mt1.5-7b-q4_K_M"      # số đo, không phải suy đoán
    assert eng.engine_id != "hy-mt-1.5-7b", "quy tắc lại tái tạo được id registry?"
    assert eng.prompt_version == "unknown", (
        "đóng dấu prompt_version lạ vào translations là nói dối về engine")


def test_prompt_version_resolves_instead_of_falling_back_to_unknown():
    """`prompt_version` là thứ được đóng dấu vào `translations`/`llm_calls`; tra
    bằng chuỗi sai thì nó lặng lẽ thành "unknown" và không phân biệt được bản dịch
    cũ với mới khi prompt đổi."""
    assert engine(_FakeClient()).prompt_version == "qwen-json-p1"


# --- năng lực glossary là DỮ LIỆU, không phải hằng True -------------------------

def test_supports_glossary_is_data_from_the_constructor_not_a_constant():
    """Nguồn sự thật là `spec.capabilities["glossary_prompt"]`; adapter không có
    spec nên Task 12 truyền cờ vào. Phải ghim CẢ HAI giá trị: một bài chỉ khẳng
    định `True` vẫn xanh với `return True` cứng."""
    assert engine(_FakeClient()).supports_glossary() is True
    eng = OllamaMtEngine(model=REGISTRY_MODEL_REF, client=_FakeClient(),
                         supports_glossary=False)
    assert eng.supports_glossary() is False


# --- dịch ----------------------------------------------------------------------

def test_translate_parses_json_and_preserves_timing():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"Xin chào"}]}')])
    out = engine(client).translate([seg(1, "你好")], [], MtOpts(source_lang="zh"))
    assert out[0].text == "Xin chào"
    assert (out[0].i, out[0].start, out[0].end, out[0].speaker) == (1, 1.0, 2.0, "S1")


def test_translate_keeps_every_field_it_does_not_own():
    """Dịch CHỈ được đổi `text`. Dựng tay `Segment(...)` làm rơi 7/13 trường — lỗi
    đã xảy ra hai lần trong giai đoạn này — nên đầu ra phải bằng `replace` của đầu
    vào, và `words` phải là CÙNG một đối tượng list, không phải bản sao."""
    client = _FakeClient([reply('{"translations":[{"i":3,"text":"vi"}]}')])
    src = Segment(i=3, start=3.0, end=4.0, text="a", words=[Word("a", 3.0, 4.0)],
                  emotion="angry", events=["music"], speaker="S2", avg_logprob=-0.5,
                  no_speech_prob=0.1, suspect=True, t="orig", qa=["check"])
    out = engine(client).translate([src], [], MtOpts(source_lang="zh"))[0]
    assert out.words is src.words
    assert out == dataclasses.replace(src, text="vi")
    assert out.to_json() == {**src.to_json(), "text": "vi"}


def test_request_body_matches_the_measured_contract():
    """Ghim nguyên yêu cầu gửi đi: URL (đã cắt `/` cuối), model, và các cờ mà số đo
    cho thấy Ollama cần để trả JSON sạch."""
    client = _FakeClient([one_batch_reply()])
    eng = engine(client, base_url="http://127.0.0.1:9999/", keep_alive="30m")
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    sent = client.bodies[0]
    assert sent["url"] == "http://127.0.0.1:9999/api/chat"
    assert sent["timeout"] is not None, "không có timeout thì Ollama treo là treo worker"
    body = sent["json"]
    assert body["model"] == REGISTRY_MODEL_REF
    assert body["stream"] is False
    assert body["format"] == "json"
    assert body["keep_alive"] == "30m"
    assert body["options"]["temperature"] == 0.1
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_user_message_carries_every_segment_and_both_languages():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"x"},'
                                '{"i":2,"text":"y"}]}')])
    eng = engine(client)
    eng.translate([seg(1, "你好"), seg(2, "再见")], [],
                  MtOpts(source_lang="zh", target_lang="vi"))
    user = client.bodies[0]["json"]["messages"][1]["content"]
    assert "你好" in user and "再见" in user
    assert "từ zh sang vi" in user, "chiều dịch phải là source → target, không được đảo"


def test_glossary_reaches_the_system_message():
    client = _FakeClient([one_batch_reply()])
    eng = engine(client)
    terms = [Term(id=None, lang="zh", term="龙", translation="rồng", approved=True)]
    eng.translate([seg(1, "龙")], terms, MtOpts(source_lang="zh"))
    sent = client.bodies[0]["json"]["messages"]
    assert sent[0]["role"] == "system"
    assert "rồng" in sent[0]["content"]


def test_no_glossary_text_in_the_prompt_when_the_engine_does_not_support_it():
    """Cờ và prompt phải nói CÙNG một điều, nếu không bản ghi mâu thuẫn: QA gắn
    `engine_no_glossary` theo `supports_glossary()`, còn prompt thì vẫn áp glossary.

    Đây không phải nhánh chết: `registry.json:87` khai `hy-mt-1.5-7b` với
    `runtime: "ollama"` và `capabilities.glossary_prompt: false`, nên Task 12 dựng
    ĐÚNG tổ hợp `OllamaMtEngine(supports_glossary=False)` với glossary truyền vào.
    Phải ghim CẢ HAI chiều: một bài chỉ khẳng định chiều `False` vẫn xanh nếu
    adapter bỏ hẳn glossary khỏi mọi prompt."""
    terms = [Term(id=None, lang="zh", term="龙", translation="rồng", approved=True)]

    client_no = _FakeClient([one_batch_reply()])
    eng_no = engine(client_no, supports_glossary=False)
    eng_no.translate([seg(1, "龙")], terms, MtOpts(source_lang="zh"))
    sent_no = client_no.bodies[0]["json"]["messages"]
    assert sent_no[0]["role"] == "system"
    assert "rồng" not in sent_no[0]["content"], "cờ False mà prompt vẫn áp glossary"

    client_yes = _FakeClient([one_batch_reply()])
    eng_yes = engine(client_yes, supports_glossary=True)
    eng_yes.translate([seg(1, "龙")], terms, MtOpts(source_lang="zh"))
    sent_yes = client_yes.bodies[0]["json"]["messages"]
    assert "rồng" in sent_yes[0]["content"], "cờ True thì glossary phải vào prompt"


# --- số đo của lần gọi ---------------------------------------------------------

def test_stats_come_from_the_measured_keys():
    client = _FakeClient([one_batch_reply()])
    eng = engine(client)
    assert eng.last_stats is None, "chưa gọi thì chưa có gì để báo"
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    assert (eng.last_stats.tokens_in, eng.last_stats.tokens_out) == (11, 22)
    assert eng.last_stats.duration_ms == 1796, (
        "`total_duration` là NANÔ giây: 1796970500 ns = 1796 ms")


def test_missing_measured_keys_become_none_instead_of_crashing():
    """Phản hồi thật của lượt ĐỔ model chỉ có `done_reason: "unload"`, và một
    Ollama khác phiên bản có thể bỏ `total_duration`. Thiếu khoá phải là `None` —
    "chưa đo được" khác "nhanh bằng 0"."""
    payload = reply('{"translations":[{"i":1,"text":"x"}]}', total=None)
    payload.pop("prompt_eval_count")
    payload.pop("eval_count")
    client = _FakeClient([payload])
    eng = engine(client)
    out = eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    assert out[0].text == "x"
    assert eng.last_stats.tokens_in is None
    assert eng.last_stats.tokens_out is None
    assert eng.last_stats.duration_ms is None


# --- đường hỏng ----------------------------------------------------------------

def test_alignment_failure_is_raised_not_hidden():
    client = _FakeClient([reply('{"translations":[]}')])
    eng = engine(client)
    with pytest.raises(AlignmentProblem):
        eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))


def test_non_string_content_raises_the_error_contract_not_attribute_error():
    """Hợp đồng lỗi của `MtEngine` chỉ có `ValueError` (parse), `AlignmentProblem`
    (lệch) và lỗi HTTP/vận chuyển. `content` không phải chuỗi từng ném
    `AttributeError` từ `prompts.py:63` — loại thứ tư mà tầng thử lại Task 11 không
    lường được, nên nó không quyết định được thử lại hay lùi về từng segment.

    Thân dị dạng phải được ép về chuỗi rỗng TRƯỚC `parse_batch_response`, để lỗi ra
    đúng `ValueError` của hợp đồng. KHÔNG được `str(raw)`: `str([{...}])` tình cờ
    parse được thành JSON, tức nhận một thứ chưa hề qua kiểm."""
    payload = reply('{"translations":[{"i":1,"text":"x"}]}')
    payload["message"]["content"] = [{"i": 1, "text": "x"}]
    client = _FakeClient([payload])
    with pytest.raises(ValueError):
        engine(client).translate([seg(1, "a")], [], MtOpts(source_lang="zh"))


def test_http_error_response_is_raised():
    client = _FakeClient([_Resp({}, status=500)])
    eng = engine(client)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))


def test_a_failed_call_propagates_and_leaves_the_engine_unloaded():
    """Lỗi vận chuyển KHÔNG được nuốt, và chỉ một lần gọi thành công mới được coi
    là "model đang nằm trong VRAM" — nếu không thì `release()` sau đó sẽ gửi một
    lệnh đổ cho một model chưa từng nạp."""
    client = _FakeClient([], fail_on=(1,), error=RuntimeError("connection refused"))
    eng = engine(client)
    with pytest.raises(RuntimeError, match="connection refused"):
        eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    assert eng.last_stats is None
    eng.release()
    assert client.calls == 1, "chưa nạp được gì thì release phải là no-op"


def test_empty_batch_makes_no_http_call():
    client = _FakeClient([])
    eng = engine(client)
    assert eng.translate([], [], MtOpts(source_lang="zh")) == []
    assert client.bodies == []


# --- release: đổ model, idempotent, và NO-OP khi chưa nạp ----------------------

def test_release_before_anything_is_loaded_sends_nothing():
    """Governor gọi `release()` ở MỌI lần thoát/đổi phase, kể cả phase chưa từng
    nạp model. Nếu `release()` cứ POST `keep_alive: 0` thì mỗi lần đổi phase là một
    vòng HTTP tới Ollama — đúng chỗ không được có side effect. Client ở đây không
    có kịch bản trả lời, nên một lần POST lỡ là bài này ném ngay."""
    client = _FakeClient([])
    eng = engine(client)
    eng.release()
    eng.release()
    assert client.bodies == []


def test_release_after_translate_unloads_once_with_keep_alive_zero():
    """Số đo: `POST /api/chat` với `keep_alive: 0` làm `ollama ps` RỖNG. Lần gọi
    thứ hai phải là no-op — model đã đổ rồi."""
    client = _FakeClient([one_batch_reply(), unload_reply()])
    eng = engine(client)
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    eng.release()
    eng.release()
    unloads = unload_bodies(client)
    assert len(unloads) == 1, "release lần hai phải là no-op"
    assert unloads[0]["json"] == {"model": REGISTRY_MODEL_REF, "messages": [],
                                  "keep_alive": 0}
    assert unloads[0]["url"] == "http://127.0.0.1:11434/api/chat"


def test_a_failing_unload_is_swallowed_and_not_retried():
    """Đổ model hỏng thì KHÔNG được giết luồng đang chạy: VRAM sẽ do `keep_alive`
    tự thu hồi. Nhưng trạng thái nội bộ đã hạ, nên lần `release` sau không thử lại
    — nếu không, mỗi lần đổi phase lại có thêm một vòng HTTP hỏng."""
    client = _FakeClient([one_batch_reply()], fail_on=(2,),
                         error=RuntimeError("ollama tắt"))
    eng = engine(client)
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    eng.release()
    eng.release()
    assert client.calls == 2, "lượt 1 là dịch, lượt 2 là đổ model hỏng; không thử lại"
