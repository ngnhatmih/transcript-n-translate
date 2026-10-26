"""Dịch qua MỘT endpoint OpenAI-compatible (`POST /chat/completions`).

Vì sao adapter này tồn tại
    `MtEngine` là một port, và registry đã có hai kiểu runtime sống chung:
    `inprocess` (`opus-mt`, Marian trên CPU) và `ollama` (ba engine LLM). Một
    endpoint HTTP không phải kiến trúc mới — nó là giá trị `runtime` thứ ba, và
    là đường để (a) dùng API chính thức khi cần chất lượng, (b) thử một cổng nội
    bộ. Adapter này KHÔNG được khai trong `registry.json` cho tới khi có số đo;
    người dùng duy nhất hiện tại là `scripts/spike_openai_mt.py`.

Hai hợp đồng đầu ra, và vì sao phải chọn
    * `json` — giống hệt đường Ollama. Chỉ nên dùng khi endpoint BẢO ĐẢM JSON:
      API chính thức có `response_format`, Ollama native có `format: "json"`
      (grammar-constrained decoding).
    * `lines` — mỗi dòng `<i>` TAB `<bản dịch>`. Dùng cho endpoint KHÔNG có
      grammar. Đo được (cùng `hy-mt`, cùng clip, cùng lô 30, qua Ollama `/v1`
      tức không có `format: "json"`): hợp đồng JSON hỏng 5/33 lời gọi — mất dấu
      phẩy, `"text", "..."` thay vì `"text": "..."` — và hỏng cả ở lô 1. Artifact:
      `data/experiments/accuracy-pipelines/20261025-spike-openai-mt/`.

Ba tham số KHÔNG được gửi trừ khi có yêu cầu rõ ràng
    `temperature`, `max_tokens`, `response_format`. Một cổng web (ví dụ
    `whalegate`) không có tương đương cho cả ba; gửi chúng là hứa một thứ mình
    không điều khiển được, và một artifact ghi "temperature=0" trong khi endpoint
    bỏ qua nó là artifact nói dối. Mặc định: không gửi.

`release()`
    No-op, và đây không phải chỗ làm biếng: `MtEngine.release()` có nghĩa "đổ
    model khỏi GPU CỦA TIẾN TRÌNH NÀY". Endpoint ở đầu dây bên kia tự quản VRAM
    (Ollama theo `keep_alive`, API theo hạ tầng của họ); một lời gọi "unload" từ
    đây chỉ có thể làm hỏng phiên của người khác.
"""

from __future__ import annotations

import time

import httpx

from app.adapters.mt.prompts import (parse_batch_response, parse_lines_response,
                                    system_prompt, system_prompt_lines,
                                    user_prompt, user_prompt_lines)
from app.domain.models import CallStats, Segment, Term
from app.domain.mt import MtOpts

#: Thời gian chờ mặc định. Rộng hơn Ollama (một lô 30 mục có thể 20-30 s) vì
#: endpoint có thể xếp hàng ở phía họ; hết giờ là lỗi của lượt gọi, và
#: `TranslateHandler` đã có đường thử lại.
DEFAULT_TIMEOUT_S = 600.0

CONTRACTS = ("json", "lines")


def prompt_version_for(contract: str) -> str:
    """Nhãn `prompt_version` của một hợp đồng đầu ra.

    Có hàm này để composition root ghi được nhãn MÀ KHÔNG dựng engine (nó tính
    `prompt_versions` trước, và một engine `http` cần khoá API để dựng). Nhãn phải
    nói đúng thứ đã viết ra bản dịch: `openai-lines-p1` khác `openai-json-p1`, và
    cả hai khác bộ `V0..V3` của đường Ollama — trộn chúng là trộn hai biến số
    trong cùng một cột artifact.
    """
    if contract not in CONTRACTS:
        raise ValueError(f"hợp đồng lạ: {contract!r} (chỉ nhận {list(CONTRACTS)})")
    return f"openai-{contract}-p1"


class OpenAiChatMt:
    """`MtEngine` trên `/v1/chat/completions`; mọi thứ khác do handler lo.

    Adapter này cố ý KHÔNG biết gì về batching, alignment hay QA: nó nhận một
    `batch`, trả về đúng bấy nhiêu `Segment` (hoặc ném), và để phần còn lại cho
    `TranslateHandler` — cùng chính sách với `OllamaMtEngine`.
    """

    def __init__(self, model: str, *, base_url: str, engine_id: str,
                 api_key: str | None = None,
                 contract: str = "json",
                 json_mode: str = "none",
                 temperature: float | None = None,
                 max_tokens: int | None = None,
                 reasoning_effort: str | None = None,
                 supports_glossary: bool = True,
                 timeout_s: float = DEFAULT_TIMEOUT_S,
                 client: httpx.Client | None = None) -> None:
        if contract not in CONTRACTS:
            raise ValueError(f"hợp đồng lạ: {contract!r} (chỉ nhận {list(CONTRACTS)})")
        if json_mode not in ("none", "object"):
            raise ValueError(f"json_mode lạ: {json_mode!r} (chỉ nhận 'none', 'object')")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._engine_id = engine_id
        self._api_key = api_key
        self._contract = contract
        self._json_mode = json_mode
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._reasoning_effort = reasoning_effort
        self._supports_glossary = supports_glossary
        self._timeout_s = timeout_s
        self._client = client if client is not None else httpx.Client()
        #: `MtEngine` cho phép đọc số đo của lượt gọi vừa rồi; `None` = chưa gọi.
        self.last_stats: CallStats | None = None

    # -- hợp đồng `MtEngine` ----------------------------------------------------
    # ⚠️ BA thuộc tính dưới đây là `@property`, KHÔNG phải method — và đây là một
    # lỗi đã ĐO ĐƯỢC chứ không phải chuyện hình thức: `TranslateHandler._record_call`
    # đọc `getattr(engine, "model_ref", None)` rồi ghi vào cột `llm_calls.model_ref`
    # của sqlite. Khi bản đầu khai `def model_ref(self)` (thiếu `@property`) thì
    # `getattr` trả về một BOUND METHOD, và mọi job `translate` bằng engine này chết
    # ngay lô đầu:
    #   sqlite3.InterfaceError: Error binding parameter 2 - probably unsupported type.
    # `chimera.py` thì tệ hơn: nó `str(getattr(engine, "prompt_version", ...))` nên
    # ghi "<bound method ...>" vào phiên Chimera mà KHÔNG hề báo lỗi.
    # Vì sao 63 test của chính adapter này vẫn xanh: chúng gọi theo hình dạng SAI
    # (`engine.model_ref()`), còn spike thì chạy trên repo GIẢ trong bộ nhớ nên bound
    # method không bao giờ chạm sqlite. Hình dạng đúng là hình dạng `OpusMtEngine` và
    # `OllamaMtEngine` đang dùng, và nay được ghim bởi
    # `tests/test_mt_engine_contract.py`.
    @property
    def engine_id(self) -> str:
        return self._engine_id

    @property
    def model_ref(self) -> str:
        return self._model

    @property
    def prompt_version(self) -> str:
        """Không tra `PROMPT_VERSION` được: prompt của hợp đồng `lines` KHÔNG đi
        qua `experiment_prompt_style` và không thuộc bộ `V0..V3` đã đo. Trả tên
        hợp đồng thay vì bịa một phiên bản chưa từng đo."""
        return prompt_version_for(self._contract)

    def supports_glossary(self) -> bool:
        return self._supports_glossary

    def release(self) -> None:
        """No-op có chủ ý — xem docstring của module."""

    # -- một lượt gọi -----------------------------------------------------------
    def chat(self, system: str, user: str, *,
             temperature: float | None = None) -> str:
        """MỘT lượt gọi; trả `choices[0].message.content`.

        `content` rỗng được coi là LỖI, không phải bản dịch rỗng: một lô 30 mục
        trả chuỗi rỗng là engine hỏng, còn "câu này dịch ra rỗng" thì đã có QA
        của đường dịch lo.
        """
        body: dict = {
            "model": self._model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if self._max_tokens is not None:
            body["max_tokens"] = self._max_tokens
        if self._json_mode == "object":
            body["response_format"] = {"type": "json_object"}
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort
        bat_dau = time.perf_counter()
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        response = self._client.post(f"{self._base_url}/chat/completions",
                                     json=body, headers=headers,
                                     timeout=self._timeout_s)
        giay = time.perf_counter() - bat_dau
        # `raise_for_status` TRƯỚC khi đọc `json()`: một 500 kèm HTML hay kèm
        # `{"error": ...}` sẽ ném ở đây với nội dung phản hồi, thay vì ném
        # `JSONDecodeError` — hai loại lỗi đó phải phân biệt được khi đọc log.
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices")
        message = choices[0].get("message") if choices else None
        content = message.get("content") if isinstance(message, dict) else None
        usage = data.get("usage") or {}
        self.last_stats = CallStats(
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            # Endpoint OpenAI-compatible KHÔNG trả `total_duration` như Ollama, nên thời lượng
            # phải do CHÍNH adapter đo — nếu không thì cột `llm_calls.duration_ms` (và tổng
            # `translations.duration_ms` suy từ nó) LUÔN NULL cho mọi job `http`: đo được trên
            # DB thật, 18 lời gọi `deepseek-web` có token đủ mà `ms` rỗng hết.
            duration_ms=int(giay * 1000),
        )
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"engine trả `content` rỗng: {str(data)[:300]}")
        return content

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        if not batch:
            return []
        terms = glossary if self._supports_glossary else []
        if self._contract == "lines":
            system = system_prompt_lines(terms, target_lang=opts.target_lang)
            user = user_prompt_lines(batch, source_lang=opts.source_lang,
                                     target_lang=opts.target_lang)
        else:
            system = system_prompt(terms, target_lang=opts.target_lang)
            user = user_prompt(batch, source_lang=opts.source_lang,
                               target_lang=opts.target_lang)
        content = self.chat(
            system, user,
            # Nhiệt độ của lượt gọi THẮNG mặc định của engine; cả hai đều `None`
            # nghĩa là không gửi gì. Một engine cấu hình `temperature=0.0` mà
            # lượt gọi không truyền gì thì vẫn phải ra 0.0 — nếu không, cấu hình
            # đó là cấu hình chết.
            temperature=(opts.temperature if opts.temperature is not None
                         else self._temperature))
        if self._contract == "lines":
            return parse_lines_response(content, batch)
        return parse_batch_response(content, batch)
