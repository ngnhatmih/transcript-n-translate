"""Qwen2.5 qua Ollama: HTTP tới một tiến trình RIÊNG, nên VRAM do Ollama quản.

Khác OPUS-MT (nạp model vào chính tiến trình này), engine này chỉ nói HTTP. Vì vậy
`release()` chỉ làm MỘT việc: gửi `keep_alive: 0` để Ollama đổ model. Task 12 đăng
ký thẳng `engine.release` với governor, nên KHÔNG có hook bên trong `release()`:
cho người gọi nhét việc vào đường đổ model là mở đúng chỗ không nên có side effect.

`release()` BẮT BUỘC idempotent, và "chưa nạp gì" phải là NO-OP THẬT (không gửi
HTTP): governor gọi nó ở mọi lần thoát và mọi lần đổi phase, kể cả những phase chưa
từng dịch câu nào.

Hình dạng phản hồi viết theo SỐ ĐO, không theo giả định — Ollama 0.34.4,
`POST /api/chat` với `stream: false`, `format: "json"`:

    {"message": {"role": "assistant", "content": "{\\"translations\\":[...]}"},
     "done": true, "done_reason": "stop", "total_duration": 1796970500,
     "prompt_eval_count": 47, "eval_count": 13, ...}

Nội dung nằm ở `message.content`; `prompt_eval_count`/`eval_count` là số token;
`total_duration` là NANÔ giây. Phản hồi của lượt ĐỔ model (`keep_alive: 0`) chỉ có
`done_reason: "unload"` — thiếu hết các khoá số — nên việc đọc chúng không được
phép ném khi thiếu.
"""
from __future__ import annotations

import httpx

from app.adapters.mt.prompts import (PROMPT_VERSION, parse_batch_response,
                                     system_prompt, user_prompt)
from app.config import OLLAMA_DEFAULT_BASE_URL
from app.domain.models import CallStats, Segment, Term
from app.domain.mt import MtOpts

#: Khớp `model_ref` của engine `qwen2.5-3b` trong `backend/registry.json`. Task 12
#: truyền `spec.model_ref` vào; mặc định này chỉ để dựng được engine trong test.
DEFAULT_MODEL = "qwen2.5:3b-instruct-q4_K_M"
#: M-10: ĐIỂM RƠI cho người gọi không truyền `base_url` (test, script) — KHÔNG
#: phải địa chỉ của production. Địa chỉ thật do `app/main.py` truyền vào từ
#: `app.config.resolve_ollama_base_url` (nguồn duy nhất đọc `OLLAMA_HOST`), nên
#: adapter cố ý KHÔNG đọc env ở đây: đọc env trong lúc dựng engine sẽ làm mọi
#: test dựng engine trực tiếp phụ thuộc môi trường của máy đang chạy.
#: Hằng số này trỏ về `app.config` thay vì chép lại chuỗi (bản cũ chép, và đó là
#: chỗ mã hoá endpoint thứ tư của M-10).
DEFAULT_BASE_URL = OLLAMA_DEFAULT_BASE_URL
DEFAULT_KEEP_ALIVE = "30m"

#: Rộng rãi: đo được 1,80 s cho một lô 13 token, nhưng phần lớn thời gian đó là NẠP
#: model, và một lô dài có thể sinh hàng nghìn token.
_TIMEOUT_S = 300.0

#: Đổ model là một lệnh nhỏ. Nó chạy trên đường thoát phase, nên không được phép
#: treo lâu như một lượt dịch.
_UNLOAD_TIMEOUT_S = 30.0

#: Thấp: đây là dịch thuật, không phải sáng tác.
_TEMPERATURE = 0.1


def _engine_id_from_model(model: str) -> str:
    """`qwen2.5:3b-instruct-q4_K_M` -> `qwen2.5-3b`, khớp `id` trong registry.json.

    ĐIỂM RƠI, không phải nguồn: người gọi ĐÃ BIẾT id registry thì phải truyền
    `engine_id=` vào `OllamaMtEngine` (Task 12 truyền `spec.id`), và giá trị đó
    THẮNG. Hàm này chỉ để dựng được engine khi người gọi không có spec trong tay
    (test, script) — xem `__init__`.

    KHÔNG dùng `model.split(":")[0]`: `model_ref` của registry là
    `qwen2.5:3b-instruct-q4_K_M`, nên cách đó cho ra `qwen2.5` — lệch `id` engine
    (`qwen2.5-3b`) và lệch khoá `PROMPT_VERSION`, làm `prompt_version` rơi về
    "unknown" rồi bị đóng dấu SAI vào `translations`/`llm_calls`.

    Phần đuôi lượng tử hoá (`instruct-q4_K_M`) không thuộc định danh engine: bỏ nó đi
    thì `qwen2.5:7b-instruct-q4_K_M` cho đúng `qwen2.5-7b`, id mà cả registry.json
    lẫn `PROMPT_VERSION` đã có sẵn.

    GIỚI HẠN: quy tắc này hiệu chỉnh cho tag của Qwen. `hy-mt1.5-7b:q4_K_M` (id
    registry `hy-mt-1.5-7b`) sẽ cho ra `hy-mt1.5-7b-q4_K_M`, tức quy tắc này
    KHÔNG phục vụ được HY-MT. Fix round 1 (I-2) đóng lớp lỗi đó ở ĐÚNG chỗ nó
    phát sinh: `engine_id` nay là THAM SỐ của `OllamaMtEngine`, và composition
    root truyền `spec.id` — nên id hợp lệ không còn phụ thuộc vào việc quy tắc suy
    diễn có tái tạo được tag hay không.
    """
    name, _, tag = model.partition(":")
    if not tag:
        return name
    return f"{name}-{tag.split('-')[0]}"


def _nanos_to_ms(total_duration_ns: object) -> int | None:
    """`total_duration` của Ollama là NANÔ giây (đo: 1796970500 cho 1,80 s).

    Thiếu khoá hoặc `0` ⇒ `None`, KHÔNG phải `0`: "chưa đo được" khác "nhanh bằng
    không", và `translations.duration_ms` phải phân biệt được hai thứ đó.
    """
    if not total_duration_ns:
        return None
    return int(total_duration_ns) // 1_000_000


class OllamaMtEngine:
    def __init__(self, model: str = DEFAULT_MODEL, *, base_url: str = DEFAULT_BASE_URL,
                 keep_alive: str = DEFAULT_KEEP_ALIVE, client: object | None = None,
                 supports_glossary: bool = True,
                 engine_id: str | None = None) -> None:
        self._model = model
        # Fix round 1 (I-2): id engine là THAM SỐ, không phải thứ luôn được SUY ra.
        # `spec.id` của registry là nguồn chân lý, và composition root truyền nó
        # vào; quy tắc suy từ tag chỉ là ĐIỂM RƠI cho người gọi không có spec
        # (test, script). Vì sao cần: tag của HY-MT (`hy-mt1.5-7b:q4_K_M`) suy ra
        # `hy-mt1.5-7b-q4_K_M` trong khi id registry là `hy-mt-1.5-7b`, nên để
        # adapter tự suy thì `prompt_version` tra theo một id không tồn tại và bị
        # đóng dấu "unknown" vào `translations`/`llm_calls`. Giữ điểm rơi để test
        # dựng engine không kèm id vẫn chạy.
        self._engine_id = engine_id if engine_id else _engine_id_from_model(model)
        self._base_url = base_url.rstrip("/")
        self._keep_alive = keep_alive
        # Client được TIÊM vào: test chạy được khi Ollama tắt. Chỉ dựng client thật
        # khi người gọi không đưa cái nào.
        self._client = client if client is not None else httpx.Client()
        #: DỮ LIỆU, không phải hằng `True`: nguồn sự thật là
        #: `spec.capabilities["glossary_prompt"]` trong registry.json, và adapter
        #: không có spec nên Task 12 truyền cờ vào. QA dùng cờ này để gắn
        #: `engine_no_glossary`, nên hardcode là nói dối về một engine khác.
        self._supports_glossary = supports_glossary
        #: `True` = "ta TIN model đang nằm trong VRAM". Chỉ đặt sau một lần gọi
        #: THÀNH CÔNG, và hạ xuống TRƯỚC khi gửi lệnh đổ — nên một lần đổ hỏng
        #: không bị thử lại (xem `release`).
        self._loaded = False
        self.last_stats: CallStats | None = None

    @property
    def engine_id(self) -> str:
        return self._engine_id

    @property
    def model_ref(self) -> str:
        """Tag model gửi cho Ollama — giá trị ghi vào `llm_calls.model_ref`.

        Cùng lý do với `OpusMtEngine.model_ref`: người ghi số liệu không được
        chạm vào trường nội bộ `_model`, vì mỗi adapter đặt tên nó một khác.
        """
        return self._model

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION.get(self.engine_id, "unknown")

    def supports_glossary(self) -> bool:
        return self._supports_glossary

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        if not batch:
            return []
        body = {
            "model": self._model,
            "stream": False,               # ta đọc MỘT đối tượng JSON, không stream
            "format": "json",              # đo được: Ollama ép đầu ra là JSON sạch
            "keep_alive": self._keep_alive,
            "options": {"temperature": _TEMPERATURE},
            "messages": [
                {"role": "system",
                 # Cờ và prompt phải nói CÙNG một điều. QA gắn `engine_no_glossary`
                 # theo `spec.capabilities["glossary_prompt"]` (Task 12 truyền cờ
                 # vào) — nếu prompt cứ áp glossary thì bản ghi tự mâu thuẫn: nhãn
                 # nói "không glossary", prompt thì có. `registry.json` đã khai
                 # `hy-mt-1.5-7b` với `runtime: "ollama"` + `glossary_prompt:
                 # false`, nên đây là tổ hợp Task 12 dựng thật, không phải nhánh chết.
                 "content": system_prompt(glossary if self._supports_glossary else [],
                                          target_lang=opts.target_lang)},
                {"role": "user",
                 "content": user_prompt(batch, source_lang=opts.source_lang,
                                        target_lang=opts.target_lang)},
            ],
        }
        resp = self._client.post(f"{self._base_url}/api/chat", json=body,
                                 timeout=_TIMEOUT_S)
        # Lỗi HTTP và lỗi vận chuyển đều PHẢI nổi lên: Task 11 phân biệt chúng để
        # quyết định thử lại hay lùi về từng segment. Nuốt ở đây là mất khả năng đó.
        resp.raise_for_status()
        data = resp.json()
        # Model đã thực sự nạp NGAY khi Ollama trả lời — kể cả khi ta parse hỏng.
        self._loaded = True
        self.last_stats = CallStats(
            tokens_in=data.get("prompt_eval_count"),
            tokens_out=data.get("eval_count"),
            duration_ms=_nanos_to_ms(data.get("total_duration")),
        )
        # Thân dị dạng phải thành chuỗi RỖNG ở ĐÂY, trước `parse_batch_response`.
        # Hợp đồng lỗi của adapter chỉ có `ValueError` (parse), `AlignmentProblem`
        # (lệch) và lỗi HTTP/vận chuyển; một `AttributeError` nổi lên từ tầng này là
        # loại lỗi thứ tư mà tầng thử lại của Task 11 không lường được, nên nó không
        # quyết định được thử lại hay lùi về từng segment. Ba hình dạng đã đo: thiếu
        # khoá `message`, `message` không phải dict, `content` không phải chuỗi.
        #
        # KHÔNG dùng `str(raw)`: `str([{...}])` tình cờ parse được thành JSON, tức
        # nhận một thứ chưa hề qua kiểm.
        message = data.get("message")
        raw = message.get("content") if isinstance(message, dict) else None
        content = raw if isinstance(raw, str) else ""
        return parse_batch_response(content, batch)

    def release(self) -> None:
        """Đổ model khỏi VRAM. Chưa nạp gì ⇒ NO-OP, không gửi gì cả.

        Idempotent theo hợp đồng `MtEngine`: governor gọi nó ở mọi lần thoát và mọi
        lần đổi phase, nên đường "chưa nạp" phải không có side effect nào.
        """
        if not self._loaded:
            return
        # Hạ trạng thái TRƯỚC khi gửi: nếu lệnh đổ hỏng thì lần gọi sau không thử
        # lại (mỗi lần đổi phase lại thêm một vòng HTTP hỏng là tệ hơn việc để
        # `keep_alive` tự thu hồi).
        self._loaded = False
        try:
            # Thân yêu cầu chép nguyên từ lần ĐO đã làm `ollama ps` rỗng — có
            # `messages: []`. Không đọc phản hồi, nên không cần `stream: False`.
            self._client.post(
                f"{self._base_url}/api/chat",
                json={"model": self._model, "messages": [], "keep_alive": 0},
                timeout=_UNLOAD_TIMEOUT_S,
            )
        except Exception:
            # Không đổ được thì đừng giết luồng đang chạy: VRAM sẽ được Ollama thu
            # hồi theo `keep_alive` đã đặt ở lượt dịch.
            pass
